import json
from pathlib import Path

import pytest

from jarvis.bootstrap import build_application
from jarvis.core.config import JarvisSettings
from jarvis.core.fast_command_router import FastCommandRouter
from jarvis.core.interaction import (
    AssistantEvent,
    Choice,
    InteractionSession,
    short_reply,
)
from jarvis.core.request_control import RequestControl
from jarvis.models.base import ModelProvider, ModelResponse
from jarvis.security.capabilities import Capability
from jarvis.security.policy import PermissionDecision


class Model(ModelProvider):
    name = "test"
    model = "test"
    def __init__(self):
        self.requests = []
    def generate(self, request):
        self.requests.append(request)
        if request.system_prompt and "You operate the connected browser" in request.system_prompt:
            data = json.loads(request.prompt)
            if "contact" not in data["page"]["url"]:
                text = '{"action":"follow_link","link_index":1}'
            else:
                text = '{"action":"finish","answer":"Contact: help@example.com. The contact page contains the support address."}'
        else:
            text = "SQL lets you query structured data. It is useful for working with databases."
        return ModelResponse(text=text, provider=self.name, model=self.model)


class Browser:
    def __init__(self):
        self.calls = []
        self.url = ""
    def call(self, name, arguments):
        self.calls.append((name, arguments))
        if name == "browser_navigate":
            self.url = arguments["url"]
        return (f'### Page\n- Page URL: {self.url}\n### Snapshot\n- heading "Example"\n'
                '- link "Contact" [ref=e1]:\n  - /url: /contact\n- paragraph: help@example.com\n')
    def close(self):
        pass


@pytest.fixture
def assistant(tmp_path: Path, monkeypatch):
    app = build_application(JarvisSettings(workspace_dir=tmp_path))
    model, browser, opened = Model(), Browser(), []
    app.cloud_provider = model
    app.local_worker_provider = model
    app.tool_service.executor.policy.set_decision(Capability.USE_BROWSER, PermissionDecision.ALLOW)
    app.tool_service.executor.policy.set_decision(Capability.OPEN_APPLICATION, PermissionDecision.ALLOW)
    monkeypatch.setattr(app.tool_service.registry.get("open_url"), "_opener", lambda url: opened.append(url) or True)
    monkeypatch.setattr(app.tool_service.registry.get("browser_mcp"), "client", browser)
    monkeypatch.setattr("jarvis.tools.browser_mcp.public_url", lambda url: url.startswith("https://example.com"))
    try:
        yield app, model, browser, opened
    finally:
        app.shutdown()


def test_action_followup_reuses_page_then_direct_question_stays_conversational(assistant):
    app, model, browser, opened = assistant
    events = []
    first = app.interact("Open https://example.com", request_control=RequestControl(on_event=events.append))
    assert first.kind == "action" and first.message == "Opened example.com."
    assert len(opened) == 1 and not model.requests
    assert [event.stage for event in events] == ["thinking", "working", "action_done"]
    second = app.interact("Find its contact information")
    assert second.kind == "action" and "help@example.com" in second.message
    assert app.interaction.focus_url == "https://example.com/contact"
    count = sum(name == "browser_navigate" for name, _ in browser.calls)
    third = app.interact("Summarize that page")
    assert third.kind == "action"
    assert sum(name == "browser_navigate" for name, _ in browser.calls) == count
    data = json.loads(model.requests[-1].prompt)
    assert any("Find its contact information" in m["content"] for m in data["recent_conversation"])
    assert "Pages observed:" in third.details and "Pages observed:" not in third.spoken_text
    calls = len(browser.calls)
    fourth = app.interact("What is SQL?")
    assert fourth.kind == "answer" and fourth.message.startswith("SQL lets")
    assert not model.requests[-1].tools and len(browser.calls) == calls
    assert "last_opened_page" in model.requests[-1].messages[0].content


def test_natural_website_request_needs_no_browser_prefix(assistant):
    app, _, browser, _ = assistant
    reply = app.interact("Could you open https://example.com and find contact information?")
    assert reply.kind == "action" and "help@example.com" in reply.details
    assert browser.calls[0] == ("browser_navigate", {"url":"https://example.com"})


def test_ambiguous_request_clarifies_then_executes_literal_answer(assistant, monkeypatch):
    app, model, _, _ = assistant
    launched = []
    def launch(arguments):
        launched.append(arguments)
        return {"ok":True, "application":"Chrome"}
    monkeypatch.setattr(app.tool_service.registry.get("open_application"), "execute", launch)
    assert app.interact("Open").message == "What would you like me to open?"
    reply = app.interact("Chrome")
    assert reply.kind == "action" and reply.message == "Chrome is opening."
    assert launched == [{"application":"Chrome"}] and not model.requests


def test_question_after_clarification_does_not_launch_an_application(assistant):
    app, model, _, opened = assistant
    app.interact("Open")
    reply = app.interact("What is SQL?")
    assert reply.kind == "answer" and model.requests and not opened


@pytest.mark.parametrize("text", ["Open the other one", "Read it", "Find its contact information"])
def test_missing_context_is_not_guessed(assistant, text):
    app, model, browser, opened = assistant
    reply = app.interact(text)
    assert reply.kind == "clarification"
    assert not model.requests and not browser.calls and not opened


def test_selected_research_page_is_grounded_and_other_one_is_unambiguous(assistant):
    app, model, _, opened = assistant
    choices = (Choice("Official guide", "https://example.com/guide"), Choice("Project docs", "https://example.com/docs"))
    app.interaction.choices = choices
    reply = app.interact("Open the other one")
    assert reply.kind == "clarification" and reply.choices == choices
    app.interact("second")
    app.interact("Open the other one")
    assert opened == [choices[1].url, choices[0].url] and not model.requests
    assert app.interact("Open the fifth one").kind == "clarification"


def test_changed_browser_page_asks_before_using_a_new_target(assistant):
    app, model, browser, _ = assistant
    app.interact("Open https://example.com and find contact information")
    count = len(model.requests)
    browser.url = "https://example.com/changed"
    reply = app.interact("Summarize that page")
    assert reply.kind == "clarification" and len(model.requests) == count
    assert {c.url for c in reply.choices} == {"https://example.com/contact", "https://example.com/changed"}
    assert browser.calls[-1][0] == "browser_snapshot"


def test_denied_action_has_no_acknowledged_success_and_keeps_previous_focus(assistant):
    app, _, _, opened = assistant
    app.interact("open google")
    app.tool_service.executor.policy.set_decision(Capability.USE_BROWSER, PermissionDecision.DENY)
    reply = app.interact("open github")
    assert reply.kind == "failed"
    assert not any(e.stage == "action_done" for e in reply.events)
    assert len(opened) == 1 and app.interaction.focus_url == "https://www.google.com/"


def test_false_tool_result_is_never_recorded_as_opened(assistant, monkeypatch):
    app, _, _, _ = assistant
    monkeypatch.setattr(app.tool_service.registry.get("open_url"), "execute", lambda _: {"ok":False})
    reply = app.interact("open google")
    assert reply.kind == "failed" and not app.interaction.focus_url
    assert not any(e.stage == "action_done" for e in reply.events)


@pytest.mark.parametrize("text", ["Don't open Google", "Do not launch Chrome", "Never delete that file", "Could you not open Google?"])
def test_negative_instruction_performs_no_action(assistant, text):
    app, model, browser, opened = assistant
    assert app.interact(text).message == "Okay. No action taken."
    assert not model.requests and not browser.calls and not opened


def test_fresh_conversation_drops_ephemeral_targets_and_choices(assistant):
    app, model, _, opened = assistant
    app.interact("open google")
    app.interaction.choices = (Choice("Google", opened[0]),)
    app.new_conversation()
    assert app.interact("Read it").kind == "clarification"
    assert not app.interaction.focus_url and not app.interaction.choices and not model.requests


@pytest.mark.parametrize("text", ["Check this code", "Tell me about this error", "What does it mean?", "How do I open Chrome?"])
def test_discussion_is_not_converted_to_browser_work(text):
    session = InteractionSession(focus_url="https://example.com", last_kind="action")
    assert session.prepare(text, FastCommandRouter(), "https://example.com").prompt == text


def test_short_spoken_text_has_no_sources_dump_or_markdown():
    text = "**Found it.** Read the [official guide](https://example.com/guide). [1]\n\nSources read:\n[1] A long source list"
    assert short_reply(text) == "Found it. Read the official guide."


def test_only_reviewed_source_events_become_page_choices():
    session = InteractionSession()
    from jarvis.core.interaction import build_reply
    choice = Choice("Observed source", "https://example.com")
    session.record(build_reply("Result", [AssistantEvent("sources", "Read", choices=(choice,))]))
    assert session.choices == (choice,)


def test_search_engine_compound_keeps_search_and_inspection_in_visible_browser(assistant, monkeypatch):
    app, _, browser, opened = assistant
    class SearchModel(ModelProvider):
        name = "test"
        def generate(self, request):
            data = json.loads(request.prompt)
            assert "current processor benchmarks" in data["goal"]
            page = data["page"]["url"]
            plan = ({"action":"navigate", "url":"https://www.google.com/search?q=current+processor+benchmarks"}
                    if page == "https://www.google.com/" else
                    {"action":"navigate", "url":"https://example.com/benchmarks"} if "google.com/search" in page else
                    {"action":"finish", "answer":"Observed benchmark results."})
            return ModelResponse(text=json.dumps(plan), provider="test", model="test")
    app.cloud_provider = SearchModel()
    monkeypatch.setattr("jarvis.tools.browser_mcp.public_url", lambda url: url.startswith("https://"))
    reply = app.interact("Open Google and check current processor benchmarks")
    navigations = [args["url"] for name, args in browser.calls if name == "browser_navigate"]
    assert not opened and navigations == ["https://www.google.com/", "https://www.google.com/search?q=current+processor+benchmarks", "https://example.com/benchmarks"]
    assert reply.kind == "action" and "Observed benchmark results" in reply.message


def test_vague_open_after_an_unrelated_answer_does_not_reuse_old_target(assistant):
    app, _, _, opened = assistant
    app.interact("open google")
    app.interact("What is SQL?")
    assert app.interact("Open it").kind == "clarification"
    assert len(opened) == 1


def test_correction_prefix_keeps_the_new_instruction_local(assistant):
    app, model, _, opened = assistant
    reply = app.interact("Stop. Open Google instead.")
    assert reply.kind == "action" and opened == ["https://www.google.com/"] and not model.requests


def test_local_override_survives_followup_resolution(assistant, monkeypatch):
    app, model, _, _ = assistant
    app.interact("Open https://example.com")
    routes = []
    original = app._route_agent_request
    def record(prompt, override=None):
        routes.append(override)
        return original(prompt, override)
    monkeypatch.setattr(app, "_route_agent_request", record)
    reply = app.interact("@local Find its contact information")
    assert reply.kind == "action" and "local" in routes and model.requests


def test_application_followup_does_not_reopen_an_old_website(assistant, monkeypatch):
    app, _, _, opened = assistant
    launches = []
    def launch(arguments):
        launches.append(arguments["application"])
        return {"ok":True, "application":"Chrome"}
    monkeypatch.setattr(app.tool_service.registry.get("open_application"), "execute", launch)
    app.interact("open google")
    app.interact("open Chrome")
    app.interact("open it")
    assert launches == ["Chrome", "Chrome"] and len(opened) == 1
    assert not app.interaction.focus_url


def test_unrelated_open_clears_stale_source_choices(assistant):
    app, _, _, _ = assistant
    app.interaction.choices = (Choice("Old source", "https://example.com/old"),)
    app.interact("open google")
    assert not app.interaction.choices
    assert app.interact("open the other one").kind == "clarification"


def test_question_about_observed_work_is_answered_without_an_api_call(assistant):
    app, model, _, _ = assistant
    app.interact("Open https://example.com and find contact information")
    count = len(model.requests)
    reply = app.interact("What did you just read?")
    assert reply.kind == "answer" and "example.com" in reply.message
    assert len(model.requests) == count

    app.interact("Open it")
    assert app.interaction.focus_url == "https://example.com/contact"
    app.new_conversation()
    assert "haven't read" in app.interact("What did you read?").message
    assert len(model.requests) == count


@pytest.mark.parametrize("prefix", ["", "@local "])
def test_try_again_resumes_failed_browser_work_without_reopening(assistant, monkeypatch, prefix):
    from jarvis.models.connection_errors import ProviderConnectionError

    app, model, browser, _ = assistant
    original = model.generate
    original_route = app._route_agent_request
    routes = []
    def route(prompt, override=None):
        routes.append(override)
        return original_route(prompt, override)
    monkeypatch.setattr(app, "_route_agent_request", route)
    count = [0]
    def fail_once(request):
        count[0] += 1
        if count[0] == 1:
            raise ProviderConnectionError("gemini · HTTP 503: Temporarily unavailable", status_code=503)
        return original(request)
    monkeypatch.setattr(model, "generate", fail_once)
    assert app.interact(prefix + "Open https://example.com and find contact information").kind == "partial"
    assert app.interact("Could you try again?").kind == "action"
    navigations = [args["url"] for name, args in browser.calls if name == "browser_navigate"]
    assert navigations == ["https://example.com", "https://example.com/contact"]
    if prefix:
        assert routes == ["local", "local"]


def test_browser_can_return_a_brief_reply_and_separate_full_result(assistant, monkeypatch):
    app, model, _, _ = assistant
    def answer(request):
        return ModelResponse(text=json.dumps({"action":"finish", "answer":"A full observed result with source details.",
                                             "spoken":"I found the information you asked for."}),provider="test",model="test")
    monkeypatch.setattr(model, "generate", answer)
    reply = app.interact("Open https://example.com and read the page")
    assert reply.message == "I found the information you asked for."
    assert "A full observed result" in reply.details and "Pages observed:" in reply.details


@pytest.mark.parametrize("prompt", ["Open", "Open the other one"])
def test_yes_does_not_invent_a_missing_target(assistant, prompt):
    app, model, browser, opened = assistant
    app.interact(prompt)
    assert app.interact("yes").kind == "clarification"
    assert not model.requests and not browser.calls and not opened


def test_file_receipt_replaces_stale_browser_context(assistant, tmp_path: Path):
    from jarvis.core.interaction import build_reply
    from jarvis.core.request_control import request_scope
    from jarvis.core.tool_request import ToolRequest

    app, _, _, _ = assistant
    app.interact("open google")
    (tmp_path / "notes.txt").write_text("Observed file contents.", encoding="utf-8")
    app.tool_service.executor.policy.set_decision(Capability.READ_FILE, PermissionDecision.ALLOW)
    control = RequestControl()
    with request_scope(control):
        content = app.tool_service.execute(ToolRequest(tool_name="read_file", arguments={"path":"notes.txt"}))
    app.interaction.record(build_reply(str(content), control.events))
    resolved = app.interaction.prepare("Read it", app.fast_command_router)
    assert "notes.txt" in resolved.prompt and not resolved.prompt.startswith("browser:")
    assert not app.interaction.focus_url
