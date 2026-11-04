import json
from pathlib import Path
from unittest.mock import patch
from urllib.parse import parse_qs, urlsplit

import pytest

from jarvis.agents.hermes import HermesAgentEngine
from jarvis.bootstrap import build_application
from jarvis.core.agent_service import AgentService
from jarvis.core.application import JarvisApplication
from jarvis.core.config import JarvisSettings
from jarvis.core.fast_command_router import FastCommandRouter
from jarvis.core.personal_memory import PersonalMemory
from jarvis.models.base import ModelProvider, ModelRequest, ModelResponse, ModelToolCall
from jarvis.runtime.intelligence import IntelligenceHub
from jarvis.runtime.profile import AgentEngineId, RuntimeMode
from jarvis.security.capabilities import Capability
from jarvis.security.policy import PermissionDecision, PermissionPolicy
from jarvis.tools.executor import PermissionDeniedError, ToolExecutor
from jarvis.tools.open_url import OpenUrlTool
from jarvis.tools.registry import ToolRegistry
from jarvis.tools.service import ToolService


class RecordingModel(ModelProvider):
    name = "test"
    model = "test-model"

    def __init__(self):
        self.requests = []

    def generate(self, request):
        self.requests.append(request)
        return ModelResponse(text="A reasoned answer", provider=self.name, model=self.model)


def browser_app(opened):
    registry = ToolRegistry()
    registry.register(OpenUrlTool(opener=lambda url: opened.append(url) or True))
    return JarvisApplication(tool_service=ToolService(registry, ToolExecutor(PermissionPolicy(allowed={Capability.USE_BROWSER}))),
                             model_provider=RecordingModel())


@pytest.mark.parametrize("prompt,engine,query", [
    ("search for how can i make money fast in the google you opened", "www.google.com", "how can i make money fast"),
    ("could you search for Spring Boot and SQL on Google", "www.google.com", "Spring Boot and SQL"),
    ("search youtube for Java tutorials", "www.youtube.com", "Java tutorials"),
    ("google C++ & C#", "www.google.com", "C++ & C#"),
    ("open google and search for part time jobs", "www.google.com", "part time jobs"),
])
def test_browser_search_is_a_zero_model_trusted_command(prompt, engine, query):
    request = FastCommandRouter().route(prompt)
    assert request is not None and request.tool_name == "open_url"
    url = urlsplit(str(request.arguments["url"]))
    assert url.hostname == engine
    assert query in [values[0] for values in parse_qs(url.query).values()]


@pytest.mark.parametrize("prompt", ["search for it", "search in my files for invoices",
                                  "search for laptops and compare the results", "research Java salaries in Germany"])
def test_ambiguous_or_research_tasks_do_not_become_a_simple_url(prompt):
    assert FastCommandRouter().route(prompt) is None


def test_browser_followup_uses_last_opened_search_site_and_enters_chat_history():
    opened = []
    app = browser_app(opened)
    try:
        app.ask_with_tools("open youtube")
        response = app.ask_with_tools("search for Java classes in the tab you opened")
        assert opened[-1] == "https://www.youtube.com/results?search_query=Java+classes"
        assert "Youtube search" in response
        assert isinstance(app.model_provider, RecordingModel)
        assert not app.model_provider.requests
        assert [m.role for m in app.conversation.snapshot()] == ["user", "assistant", "user", "assistant"]
        assert "open youtube" in str(app.conversation.snapshot())
    finally:
        app.shutdown()


def test_local_fast_actions_are_visible_to_next_cloud_reasoning_turn(tmp_path: Path):
    app = build_application(JarvisSettings(workspace_dir=tmp_path))
    cloud = RecordingModel()
    app.cloud_provider = cloud
    app.tool_service.executor.policy.set_decision(Capability.USE_BROWSER, PermissionDecision.ALLOW)
    with patch("webbrowser.open", return_value=True):
        app.ask_with_tools("open google")
    app.ask_with_tools("What did you just open?")
    assert "open google" in str(cloud.requests[-1].messages)
    assert "https://www.google.com/" in str(cloud.requests[-1].messages)
    app.shutdown()


def test_browser_fast_path_does_not_bypass_permission_denial():
    app = browser_app([])
    app.tool_service.executor.policy.set_decision(Capability.USE_BROWSER, PermissionDecision.DENY)
    try:
        with pytest.raises(PermissionDeniedError):
            app.ask_with_tools("search for Java")
    finally:
        app.shutdown()


def test_automatic_uses_previously_selected_gemini_after_fast_actions(tmp_path: Path):
    app = build_application(JarvisSettings(workspace_dir=tmp_path, gemini_api_key="fake-key"))
    hub = app.intelligence
    assert hub is not None
    hub.save_preferences("gemini", "gemini-3.1-flash-lite", True, "dark")
    hub.save_preferences("auto", "", True, "dark")
    cloud, local = RecordingModel(), RecordingModel()
    app.local_worker_provider = local
    with patch.object(hub, "provider", return_value=cloud) as factory:
        assert app.ask_with_tools("Explain SQL joins") == "A reasoned answer"
        factory.assert_called_once_with("gemini")
    assert not local.requests and not cloud.requests[0].tools
    decision = app.last_route_decision()
    assert decision is not None and decision.source == "gemini"
    app.shutdown()


def test_local_only_still_blocks_automatic_cloud(tmp_path: Path):
    app = build_application(JarvisSettings(workspace_dir=tmp_path, gemini_api_key="fake-key"))
    hub = app.intelligence
    assert hub is not None
    hub.save_preferences("gemini", "gemini-3.1-flash-lite", True, "dark")
    hub.save_preferences("auto", "", True, "dark")
    app.set_runtime_mode(RuntimeMode.LOCAL)
    local = RecordingModel()
    app.local_worker_provider = local
    with patch.object(hub, "provider", side_effect=AssertionError("Cloud selected")):
        app.ask_with_tools("Explain SQL joins")
    assert local.requests
    app.shutdown()


def test_explicit_hermes_engine_is_not_overridden_by_automatic_api(tmp_path: Path):
    app = build_application(JarvisSettings(workspace_dir=tmp_path, gemini_api_key="fake-key"))
    hub = app.intelligence
    assert hub is not None
    hub.save_preferences("gemini", "test-model", True, "dark")
    hub.save_preferences("auto", "", True, "dark")
    app.set_agent_engine(AgentEngineId.HERMES)
    with patch.object(app, "_ensure_engine_available"):
        assert app._route_agent_request("Explain Java") is app.hermes_local_agent_engine
    app.shutdown()


def test_automatic_does_not_discover_or_spend_a_new_key_or_paid_plan():
    hub = IntelligenceHub(JarvisSettings(gemini_api_key="fake-key", openai_api_key="fake-paid-key"), PersonalMemory())
    assert hub.automatic_connection() is None
    hub.save_preferences("openai", "paid-model", True, "dark")
    hub.save_preferences("auto", "", True, "dark")
    assert hub.automatic_connection() is None
    hub.save_preferences("gemini", "free-tier-model", True, "dark")
    hub.steward.configure(enabled=True, commercial=False, auto_review=True, allow_failover=False, daily_limit=100)
    assert hub.automatic_connection() is None  # A previous selection cannot bypass management approval.


def test_invented_tool_is_returned_as_feedback_and_agent_can_recover():
    opened = []
    app = browser_app(opened)
    class RecoveringModel(RecordingModel):
        def generate(self, request: ModelRequest):
            self.requests.append(request)
            count = len(self.requests)
            if count == 1:
                calls = [ModelToolCall(name="google_search", arguments={"query": "Java"})]
            elif count == 2:
                feedback = next(m.content for m in request.messages if m.role == "tool")
                assert not json.loads(feedback)["ok"] and "open_url" in feedback
                calls = [ModelToolCall(name="open_url", arguments={"url": "https://www.google.com/search?q=Java"})]
            else:
                return ModelResponse(text="Opened search", provider="test", model="test")
            return ModelResponse(text="", provider="test", model="test", tool_calls=calls)
    model = RecoveringModel()
    try:
        agent = AgentService(model, app.tool_service)
        assert agent.run("Search for Java") == "Opened search"
        assert opened == ["https://www.google.com/search?q=Java"]
        assert len(model.requests) == 3
    finally:
        app.shutdown()


def test_automatic_uses_configured_cloud_hermes_for_complex_actions(tmp_path: Path):
    app = build_application(JarvisSettings(workspace_dir=tmp_path, gemini_api_key="fake-key"))
    hub = app.intelligence
    assert hub is not None
    hub.save_preferences("gemini", "test-model", True, "dark")
    hub.save_preferences("auto", "", True, "dark")
    hermes = app.hermes_cloud_agent_engine
    assert isinstance(hermes, HermesAgentEngine)
    hermes.provider, hermes.model = "groq", "configured-model"
    with patch.object(hermes, "is_available", return_value=True):
        assert app._route_agent_request("Open the browser then analyze the page and then click the relevant button") is hermes
    hub.steward.configure(enabled=True, auto_review=True, commercial=False, allow_failover=False, daily_limit=100)
    # Managed mode cannot silently delegate to an externally configured cloud runtime.
    with patch.object(hermes, "is_available", return_value=True), patch.object(app, "_ensure_engine_available"):
        assert app._route_agent_request("Open the browser then analyze the page and then click the relevant button") is not hermes
    app.shutdown()
