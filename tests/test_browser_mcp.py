from pathlib import Path
from unittest.mock import patch

import pytest

from jarvis.agents.browser_workflow import browser_task, run_browser
from jarvis.models.base import ModelProvider, ModelResponse
from jarvis.tools.browser_mcp import (
    BrowserMCPTool,
    PlaywrightMCP,
    load_snapshot,
    parse_snapshot,
)

PAGE = '### Page\n- Page URL: https://example.com/\n### Snapshot\n- link "Contact" [ref=e1]:\n  - /url: /contact\n'


class Client:
    def __init__(self):
        self.calls = []
        self.page = PAGE
    def call(self, name, arguments):
        self.calls.append((name, arguments))
        return self.page
    def close(self):
        pass


def test_snapshot_links_are_resolved_and_labels_preserved():
    snapshot = parse_snapshot(PAGE + '- link "General contact" [ref=e2]:\n  - /url: /contact\n')
    assert snapshot["links"] == [{"label": "Contact / General contact", "url": "https://example.com/contact"}]


def test_follow_link_only_uses_observed_url_and_rechecks_page():
    client = Client()
    tool = BrowserMCPTool(client)
    with patch("jarvis.tools.browser_mcp.public_url", return_value=True):
        tool.execute({"action": "snapshot"})
        tool.execute({"action": "follow_link", "link_index": 1})
    assert client.calls[-1] == ("browser_navigate", {"url": "https://example.com/contact"})
    assert client.calls[-2][0] == "browser_snapshot"


def test_changed_page_rejects_stale_link():
    client = Client()
    tool = BrowserMCPTool(client)
    tool.last = parse_snapshot(PAGE)
    client.page = PAGE.replace("https://example.com/", "https://different.example/")
    with pytest.raises(ValueError, match="page changed"):
        tool.execute({"action": "follow_link", "link_index": 1})
    assert not any(name == "browser_navigate" for name, _ in client.calls)


@pytest.mark.parametrize("action", ["browser_evaluate", "click", "fill", "upload", "install"])
def test_unexposed_actions_never_reach_the_server(action):
    client = Client()
    with pytest.raises(ValueError):
        BrowserMCPTool(client).execute({"action": action})
    assert not client.calls
    with pytest.raises(ValueError):
        PlaywrightMCP().call(action, {})


def test_private_navigation_is_rejected_before_mcp_call():
    client = Client()
    with pytest.raises(ValueError):
        BrowserMCPTool(client).execute({"action": "navigate", "url": "https://127.0.0.1/"})
    assert not client.calls


def test_snapshot_file_reference_cannot_read_arbitrary_file(tmp_path: Path):
    path = tmp_path / "secret.yml"
    path.write_text("SECRET", encoding="utf-8")
    text = f"[Snapshot]({path})"
    assert load_snapshot(text) == text


def test_workflow_selects_observed_link_and_reports_observed_pages():
    class Model(ModelProvider):
        name = "test"
        count = 0
        def generate(self, request):
            self.count += 1
            return ModelResponse(text='{"action":"follow_link","link_index":1}' if self.count == 1 else
                                 '{"action":"finish","answer":"Contact information read."}', provider="test", model="test")
    calls = []
    def execute(arguments):
        calls.append(arguments)
        return {"url": "https://example.com/" if len(calls) == 1 else "https://example.com/contact", "snapshot": "observed page", "links": [{"label":"Contact","url":"https://example.com/contact"}]}
    answer = run_browser(Model(), execute, "Open https://example.com and find contact information")
    assert calls[1] == {"action": "follow_link", "link_index": 1}
    assert "https://example.com/contact" in answer


def test_browser_task_routes_only_explicit_browser_workflows():
    assert browser_task("browser: read this page")
    assert browser_task("Open https://example.com and find information")
    assert browser_task("open google") is None
    assert browser_task("research Java") is None


@pytest.mark.parametrize("prompt", ["browser: Open https://example.com and read the page", "browser: find contact information"])
def test_denied_browser_workflow_does_not_call_mcp(tmp_path: Path, prompt):
    from jarvis.bootstrap import build_application
    from jarvis.core.config import JarvisSettings
    from jarvis.security.capabilities import Capability
    from jarvis.security.policy import PermissionDecision
    from jarvis.tools.executor import PermissionDeniedError
    app = build_application(JarvisSettings(workspace_dir=tmp_path))
    app.tool_service.executor.policy.set_decision(Capability.USE_BROWSER, PermissionDecision.DENY)
    tool = app.tool_service.registry.get("browser_mcp")
    try:
        with patch.object(tool, "execute", side_effect=AssertionError("MCP called")), pytest.raises(PermissionDeniedError):
            app.ask_with_tools(prompt)
    finally:
        app.shutdown()


def test_stop_interrupts_pending_mcp_call():
    from threading import Timer
    from types import SimpleNamespace

    from jarvis.core.request_control import (
        RequestCancelledError,
        RequestControl,
        request_scope,
    )
    client = PlaywrightMCP()
    pending = []
    control = RequestControl()
    client.tools = ["browser_snapshot"]
    client.loop = SimpleNamespace(call_soon_threadsafe=lambda callback, value: callback(value))
    client.queue = SimpleNamespace(put_nowait=lambda command: pending.append(command[2]))
    timer = Timer(0.1, control.cancelled.set)
    try:
        with patch.object(client, "_start"), request_scope(control), pytest.raises(RequestCancelledError):
            timer.start()
            client.call("browser_snapshot", {})
        assert len(pending) == 1 and pending[0].cancelled()
    finally:
        timer.join()


@pytest.mark.parametrize("prefix", ["", "  ", "1. ", "2) ", "- ", "* ", "+ "])
def test_browser_task_accepts_copied_list_formatting(prefix):
    goal = "Open https://www.python.org and find its contact information."
    assert browser_task(prefix + "browser: " + goal + "  ") == goal
    assert browser_task(prefix + goal) == goal


def test_numbered_browser_request_uses_native_gemini_and_mcp(tmp_path: Path):
    import json

    import httpx

    from jarvis.bootstrap import build_application
    from jarvis.core.config import JarvisSettings
    from jarvis.models.gemini import GeminiProvider
    from jarvis.security.capabilities import Capability
    from jarvis.security.policy import PermissionDecision

    app = build_application(JarvisSettings(workspace_dir=tmp_path, gemini_api_key="test-key"))
    assert app.intelligence is not None
    app.intelligence.save_preferences("gemini", "gemini-3.1-flash-lite", True, "dark")
    app.tool_service.executor.policy.set_decision(Capability.USE_BROWSER, PermissionDecision.ALLOW)
    client = Client()
    tool = app.tool_service.registry.get("browser_mcp")
    assert isinstance(tool, BrowserMCPTool)
    tool.client = client
    calls = []
    def handle(request):
        calls.append(request)
        assert request.url.path.endswith(":generateContent")
        payload = json.loads(request.content)
        assert "tools" not in payload
        assert "contact information" in payload["contents"][0]["parts"][0]["text"]
        return httpx.Response(200, json={"candidates": [{"content": {"parts": [{"text": '{"action":"finish","answer":"Contact link found on the observed page."}'}]}, "finishReason": "STOP"}]})
    provider = GeminiProvider(provider_name="gemini", model="gemini-3.1-flash-lite", api_key="test-key",
                              base_url="https://generativelanguage.googleapis.com/v1beta/openai", transport=httpx.MockTransport(handle))
    try:
        with patch.object(app.intelligence, "provider", return_value=provider), patch("jarvis.tools.browser_mcp.public_url", return_value=True):
            answer = app.ask_with_tools("1. browser: Open https://www.python.org and find its contact information.")
        assert "Pages observed:" in answer
        assert len(calls) == 1
        assert client.calls[0] == ("browser_navigate", {"url": "https://www.python.org"})
        assert app.conversation.snapshot()[0].content.startswith("1. browser:")
    finally:
        app.shutdown()
