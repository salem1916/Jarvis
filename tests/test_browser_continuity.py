"""Exercise the application boundary, not only the planner's scripted actions."""
import json
from types import SimpleNamespace

import pytest

from jarvis.bootstrap import build_application
from jarvis.core.config import JarvisSettings
from jarvis.core.request_control import RequestControl
from jarvis.models.base import ModelProvider, ModelResponse
from jarvis.models.connection_errors import ProviderConnectionError
from jarvis.security.capabilities import Capability
from jarvis.security.policy import PermissionDecision


@pytest.fixture
def qapp():
    from PySide6.QtWidgets import QApplication
    return QApplication.instance() or QApplication([])


class Browser:
    def __init__(self):
        self.url = "https://example.com/start"
        self.history = []
        self.calls = []
        self.fail_click = False

    def call(self, name, arguments):
        self.calls.append((name, arguments))
        if name == "browser_navigate":
            self.history.append(self.url)
            self.url = arguments["url"].replace("/redirect", "/canonical")
        elif name == "browser_navigate_back" and self.history:
            self.url = self.history.pop()
        elif name == "browser_click" and self.fail_click:
            raise ValueError("The server timed out after dispatch")
        return (f'Page URL: {self.url}\nPage Title: Example page\n'
                '- link "Documentation" [ref=e1]:\n  - /url: /docs\n'
                '  - heading "Documentation" [level=3]\n'
                '- button "Show details" [ref=e2]\n')

    def close(self):
        pass


class Model(ModelProvider):
    name = "fixture"
    model = "fixture"

    def __init__(self):
        self.requests = []
        self.error = None
        self.cancel = None
        self.action = "finish"

    def generate(self, request):
        self.requests.append(request)
        if self.error:
            raise self.error
        if self.cancel:
            self.cancel.set()
        if "You operate the connected browser" in (request.system_prompt or ""):
            text = json.dumps({"action": self.action, "target": "e2",
                               "answer": "The observed page has a Documentation link."})
        else:
            text = "SQL is a language for querying databases."
        return ModelResponse(text=text, provider=self.name, model=self.model)


@pytest.fixture
def assistant(tmp_path, monkeypatch):
    app = build_application(JarvisSettings(workspace_dir=tmp_path, state_dir=tmp_path / "state"))
    browser, model = Browser(), Model()
    app.tool_service.registry.get("browser_mcp").client = browser
    app.cloud_provider = app.local_worker_provider = model
    monkeypatch.setattr("jarvis.tools.browser_mcp.public_url", lambda url: url.startswith("https://example.com/"))
    monkeypatch.setattr("webbrowser.open", lambda *_a, **_k: pytest.fail("Opened the user's personal browser"))
    for cap in (Capability.USE_BROWSER, Capability.CLICK_UI, Capability.TYPE_TEXT, Capability.KEYBOARD_ACTION):
        app.tool_service.executor.policy.set_decision(cap, PermissionDecision.ALLOW)
    try:
        yield app, browser, model
    finally:
        app.shutdown()


@pytest.mark.parametrize("source", ["text", "voice"])
def test_open_followup_back_and_direct_answer_share_one_session(assistant, monkeypatch, source):
    app, browser, model = assistant
    control = lambda: RequestControl(input_source=source)
    opened = app.interact("Open https://example.com/start", request_control=control())
    assert opened.kind == "action" and not model.requests
    assert app.interaction.focus_url == browser.url
    with monkeypatch.context() as local:
        local.setattr(app, "_route_agent_request", lambda *_a, **_k: pytest.fail("Simple navigation contacted AI"))
        clicked = app.interact("Open the first result", request_control=control())
        assert clicked.kind == "action" and browser.url == "https://example.com/docs"
        back = app.interact("No, wait, go back", request_control=control())
        assert back.kind == "action" and browser.url == "https://example.com/start"
    assert len([call for call in browser.calls if call[0] == "browser_navigate"]) == 2
    count = len(browser.calls)
    assert app.interact("What is SQL?", request_control=control()).kind == "answer"
    assert len(browser.calls) == count and len(model.requests) == 1


def test_redirect_receipt_remembers_the_observed_destination(assistant):
    app, browser, model = assistant
    assert app.interact("Open https://example.com/redirect").kind == "action"
    assert app.interaction.focus_url == browser.url == "https://example.com/canonical"
    assert not model.requests


@pytest.mark.parametrize("failure", [None, "bad_link", "bad_evidence", "quota", "cancel"])
@pytest.mark.parametrize("system_browser", [False, True])
def test_grounded_desktop_route(assistant, monkeypatch, failure, system_browser):
    pytest.importorskip("pydantic_ai")
    pytest.importorskip("groq")
    import httpx

    from jarvis.models.openai_compatible import OpenAICompatibleProvider
    from jarvis.tools.chrome_tab import ChromePage, ChromeTab

    app, browser, standard_model = assistant
    visible_opens = []
    if system_browser:
        browser.mode = "system"
        browser.url = "about:blank"
        chrome_tab = app.tool_service.registry.get("browser_mcp").chrome_tab
        def navigate_current_tab(url):
            visible_opens.append(url)
            return {"ok": True, "url": url, "current_tab": True}

        monkeypatch.setattr(chrome_tab, "navigate", navigate_current_tab)
        monkeypatch.setattr(chrome_tab, "current_page", lambda: ChromePage(
            ChromeTab(1, (1,)), visible_opens[-1]))
    control = RequestControl(input_source="voice")
    requests = []

    def respond(request):
        payload = json.loads(request.content)
        requests.append(payload)
        schema = payload["response_format"]["json_schema"]["schema"]
        assert schema["additionalProperties"] is False
        assert schema["properties"]["evidence"]["items"]["enum"]
        assert not payload["stream"] and not payload.get("tools")
        if failure == "quota":
            return httpx.Response(429, headers={"Retry-After": "20"}, json={"error": {}})
        if len(requests) == 1:
            decision = {"kind": "open_link", "index": 99 if failure == "bad_link" else 1,
                        "text": "", "evidence": []}
            if failure == "cancel":
                control.cancelled.set()
        else:
            decision = {"kind": "reply", "index": 0, "text": "The page shows Documentation.",
                        "evidence": [99 if failure == "bad_evidence" else 1]}
        return httpx.Response(200, json={"choices": [{"message": {"content": json.dumps(decision)}}]})

    provider = OpenAICompatibleProvider(provider_name="groq", model="openai/gpt-oss-20b",
                                        base_url="https://api.groq.test/openai/v1", api_key="fixture",
                                        transport=httpx.MockTransport(respond))
    app.integrations.grounded_planner = True
    monkeypatch.setattr(app, "_route_agent_request", lambda *_a, **_k: pytest.fail("Local command contacted AI"))
    assert app.interact("Open https://example.com/start").kind == "action"
    assert not requests
    if system_browser:
        assert browser.calls == [] and visible_opens == ["https://example.com/start"]
    from jarvis.agents.reasoning import ReasoningAgentEngine
    if system_browser:
        monkeypatch.setattr(app.intelligence, "browser_provider", lambda: provider)
    else:
        monkeypatch.setattr(app, "_route_agent_request", lambda *_a, **_k: ReasoningAgentEngine(provider))
    reply = app.interact("browser: Show me the documentation and describe the page.", request_control=control)
    assert len(requests) == (2 if failure in {None, "bad_evidence"} else 1)
    if failure == "cancel":
        assert reply.kind == "cancelled"
    elif failure:
        assert reply.kind == "partial"
        if failure == "quota":
            assert "usage limit" in reply.message
    else:
        assert reply.message == "The page shows Documentation."
        assert "https://example.com/docs" in reply.details
    assert browser.url.endswith("/docs" if failure in {None, "bad_evidence"} else "/start")
    if system_browser:
        assert visible_opens == (["https://example.com/start", "https://example.com/docs"]
                                 if failure in {None, "bad_evidence"} else ["https://example.com/start"])
        assert any(event.stage == "observed" for event in reply.events)
        return
    app.integrations.grounded_planner = False
    monkeypatch.setattr(app, "_route_agent_request", lambda *_a, **_k: ReasoningAgentEngine(standard_model))
    assert "Documentation" in app.interact("browser: Describe the page.").details
    assert len(standard_model.requests) == 1


def test_current_chrome_back_and_numbered_link_stay_local(assistant, monkeypatch):
    app, browser, _ = assistant
    browser.mode = "system"
    chrome = app.integrations.browser.chrome_tab
    calls = []
    def action(*args):
        calls.append(args)
        return {"ok": True, "url": "https://example.com/docs", "current_tab": True}

    monkeypatch.setattr(chrome, "back", action)
    monkeypatch.setattr(chrome, "follow", action)
    monkeypatch.setattr(app, "_route_agent_request", lambda *_a, **_k: pytest.fail("Used AI for local navigation"))
    monkeypatch.setattr(app.intelligence, "browser_provider", lambda: pytest.fail("Used Groq for local navigation"))
    assert app.interact("No, wait, go back", request_control=RequestControl(input_source="voice")).kind == "action"
    assert app.interact("Open the first result").kind == "action"
    assert calls == [(), (1, "result")]
    assert not browser.calls


@pytest.mark.parametrize(("prompt", "site"), [
    ("open the first vd", ""),
    ("first video on youtube", "youtube.com"),
    ("play the first clip", ""),
])
def test_video_ordinal_routes_to_current_chrome_before_app_lookup(assistant, monkeypatch, prompt, site):
    app, browser, _ = assistant
    browser.mode = "system"
    calls = []
    def follow(*args):
        calls.append(args)
        return {"ok": True, "url": "https://www.youtube.com/watch?v=fixture", "current_tab": True}

    monkeypatch.setattr(app.integrations.browser.chrome_tab, "follow", follow)
    monkeypatch.setattr(app, "_route_agent_request", lambda *_a, **_k: pytest.fail("Used AI for a local video command"))
    monkeypatch.setattr(app.intelligence, "browser_provider", lambda: pytest.fail("Used Groq for a local video command"))
    reply = app.interact(prompt, request_control=RequestControl(input_source="voice"))
    assert reply.kind == "action" and "video" in reply.message
    assert calls == [(1, "video", site)]
    assert not browser.calls


def test_chrome_tab_list_stays_out_of_model_and_memory(assistant, monkeypatch):
    app, browser, _ = assistant
    browser.mode = "system"
    monkeypatch.setattr(app.integrations.browser.chrome_tab, "list_tabs", lambda: {
        "ok": True, "windows": [[{"title": "Private work title", "selected": True},
                                 {"title": "Public guide", "selected": False}]],
    })
    monkeypatch.setattr(app, "ask_with_tools", lambda *_a, **_k: pytest.fail("Sent tab inventory through chat routing"))
    reply = app.interact("what tabs do i have open in chrome ?")
    assert reply.kind == "answer" and "Private work title (selected)" in reply.message
    assert "Public guide" in reply.message and "2 open Chrome tabs" in reply.spoken_text
    assert "Private work title" not in reply.spoken_text
    assert not app.conversation.snapshot() and not app.personal_memory.recent_turns()
    assert not browser.calls


def test_read_this_page_after_tab_switch_uses_the_observed_url(assistant, monkeypatch):
    app, browser, _ = assistant
    browser.mode = "system"
    app.interaction.focus_url = "https://example.com/old-tab"
    app.integrations.grounded_planner = True
    from jarvis.tools.chrome_tab import ChromePage, ChromeTab
    page = ChromePage(ChromeTab(2, (3,)), "https://example.com/current-tab")
    monkeypatch.setattr(app.integrations.browser.chrome_tab, "current_page", lambda: page)
    from types import SimpleNamespace
    provider = SimpleNamespace(supports_grounded_planner=True, name="groq", model="fixture")
    monkeypatch.setattr(app.intelligence, "browser_provider", lambda: provider)
    reads = []
    def run(_provider, _execute, _task, **kwargs):
        reads.append(kwargs["public_read_url"])
        assert kwargs["show_page"] is None
        return "Read the selected page."

    monkeypatch.setattr("jarvis.core.application.run_browser", run)
    assert app.interact("Read this page").message == "Read the selected page."
    assert reads == [page.url]


def test_explicit_browser_goal_is_not_reinterpreted_as_search_intent(assistant):
    app, browser, model = assistant
    app.interact("Open https://example.com/start")
    reply = app.interact("browser: Search this page for documentation and tell me the result")
    assert reply.kind == "action" and len(model.requests) == 1
    assert json.loads(model.requests[0].prompt)["page"]["url"] == browser.url


def test_navigation_failure_never_falls_through_to_an_ai_agent(assistant, monkeypatch):
    app, browser, model = assistant
    monkeypatch.setattr(browser, "call", lambda *_: "No loaded page was observed")
    reply = app.interact("Open https://example.com/start")
    assert reply.kind == "failed" and "can't verify" in reply.message
    assert not model.requests and not app.interaction.focus_url


def test_changed_page_clarifies_an_ordinal_but_explicit_back_uses_current_history(assistant):
    app, browser, model = assistant
    app.interact("Open https://example.com/start")
    browser.history.append(browser.url)
    browser.url = "https://example.com/manually-changed"
    assert app.interact("Open the first result").kind == "clarification"
    assert browser.url.endswith("manually-changed")
    assert app.interact("Go back").kind == "action"
    assert browser.url.endswith("/start") and not model.requests


@pytest.mark.parametrize("status", [429, 503])
def test_provider_outage_keeps_verified_work_and_concise_spoken_reply(assistant, status):
    app, browser, model = assistant
    model.error = ProviderConnectionError(f"provider HTTP {status}: service unavailable", status_code=status)
    reply = app.interact("Open https://example.com/start and find contact details")
    assert reply.kind == "partial" and browser.url.endswith("/start")
    assert "page is open" in reply.spoken_text and "couldn't finish" in reply.spoken_text
    assert "HTTP" not in reply.spoken_text and browser.url in reply.details
    assert app.interact("Open the first result").kind == "action"
    assert browser.url.endswith("/docs") and len(model.requests) == 1


def test_interruption_discards_a_late_model_action_and_accepts_a_correction(assistant):
    app, browser, model = assistant
    app.interact("Open https://example.com/start")
    control = RequestControl(input_source="voice")
    model.cancel, model.action = control.cancelled, "click"
    reply = app.interact("Read that page", request_control=control)
    assert reply.kind == "cancelled" and not any(name == "browser_click" for name, _ in browser.calls)
    assert app.interact("No, wait, go back").kind == "action"
    assert len(model.requests) == 1


def test_uncertain_click_is_not_replayed_or_marked_as_success(assistant):
    app, browser, model = assistant
    app.interact("Open https://example.com/start")
    model.action, browser.fail_click = "click", True
    reply = app.interact("Read that page")
    assert reply.kind == "partial" and "without repeating" in reply.spoken_text
    assert len([name for name, _ in browser.calls if name == "browser_click"]) == 1
    assert not any(event.tool == "browser_click" and event.stage == "action_done" for event in reply.events)
    assert app.interaction.retry_turn is None
    assert app.interact("Try again").kind == "clarification"


def test_permission_denial_leaves_the_page_and_context_unchanged(assistant):
    app, browser, model = assistant
    app.interact("Open https://example.com/start")
    app.tool_service.executor.policy.set_decision(Capability.USE_BROWSER, PermissionDecision.DENY)
    before = len(browser.calls)
    assert app.interact("Open the first result").kind == "failed"
    assert len(browser.calls) == before and not model.requests
    assert app.interaction.focus_url == browser.url


def test_hermes_plans_without_its_own_browser_or_action_bridge(assistant, monkeypatch):
    from jarvis.agents.hermes import HermesAgentEngine
    app, browser, _model = assistant
    engine = HermesAgentEngine(tool_service=app.tool_service)
    calls = []
    def plan(self, prompt, system_prompt=None, **_):
        assert self.tool_service is None
        calls.append(json.loads(prompt))
        return json.dumps({"action":"finish","answer":"The page contains a Documentation link."})
    monkeypatch.setattr(HermesAgentEngine, "run", plan)
    monkeypatch.setattr(app, "_route_agent_request", lambda *_: engine)
    reply = app.interact("Open https://example.com/start and read the page")
    assert reply.kind == "action" and calls[0]["page"]["url"] == browser.url
    assert engine.tool_service is app.tool_service


def test_hermes_failure_keeps_opened_page_and_reports_partial_work(assistant, monkeypatch):
    from jarvis.agents.hermes import HermesAgentEngine, HermesAgentError
    app, browser, _model = assistant
    def unavailable(*_a, **_k):
        raise HermesAgentError("Hermes gateway unavailable")
    monkeypatch.setattr(HermesAgentEngine, "run", unavailable)
    monkeypatch.setattr(app, "_route_agent_request", lambda *_: HermesAgentEngine())
    reply = app.interact("Open https://example.com/start and read the page")
    assert reply.kind == "partial" and "page is open" in reply.message
    assert browser.url == app.interaction.focus_url


def test_hermes_planner_is_cancellable_even_without_streaming_callbacks(monkeypatch):
    from jarvis.agents.hermes import HermesAgentEngine
    from jarvis.agents.research import json_reply
    from jarvis.agents.search_context import ReadOnlyIntentProvider
    from jarvis.core.request_control import RequestCancelledError, request_scope
    engine = HermesAgentEngine()
    control = RequestControl()
    calls = []
    monkeypatch.setattr(engine, "is_available", lambda: True)
    def cancel(command, environment, child_control):
        calls.append(child_control)
        control.cancelled.set()
        child_control.check()
    monkeypatch.setattr(engine, "_cancellable_process", cancel)
    with request_scope(control), pytest.raises(RequestCancelledError):
        json_reply(ReadOnlyIntentProvider(engine), "Return one JSON action.", {"goal":"Read the page"})
    assert len(calls) == 1 and calls[0].on_delta is None


def test_voice_redirect_queues_latest_instruction_without_starting_a_second_worker(qapp, assistant, monkeypatch):
    from jarvis.ui.pages.chat_page import ChatPage
    app, _browser, _model = assistant
    page = ChatPage(app, "Help")
    control = RequestControl()
    page.worker = SimpleNamespace(control=control, resolve_confirmation=lambda _: None)
    page.worker_thread = object()
    page.request_in_progress = True
    try:
        page._pause_for_voice()
        page._voice_prompt("Open the first result")
        assert control.cancelled.is_set() and control.paused.is_set()
        page._voice_prompt("No, wait, go back")
        assert page._pending_prompt == "No, wait, go back"
        assert page._pending_input_source == "voice"
        queued = []
        monkeypatch.setattr(page, "_send_message", lambda: queued.append(page.input_box.text()))
        page.worker = page.worker_thread = None
        page.request_in_progress = False
        page._start_pending()
        assert queued == ["No, wait, go back"]
    finally:
        page.worker = page.worker_thread = None
        page.close()


def test_typed_wait_and_continue_hold_the_same_request(qapp, assistant):
    from jarvis.ui.pages.chat_page import ChatPage
    app, _browser, _model = assistant
    page = ChatPage(app, "Help")
    control = RequestControl()
    worker = SimpleNamespace(control=control)
    page.worker, page.worker_thread, page.request_in_progress = worker, object(), True
    try:
        page.input_box.setText("Wait")
        page._send_message()
        assert control.paused.is_set() and not control.cancelled.is_set()
        assert not page._pending_prompt
        page.input_box.setText("Continue")
        page._send_message()
        assert not control.paused.is_set() and not control.cancelled.is_set()
        assert page.worker is worker and not page._pending_prompt
    finally:
        page.worker = page.worker_thread = None
        page.close()
