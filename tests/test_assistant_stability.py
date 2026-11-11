import json
import os
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import httpx
import pytest
from PySide6.QtWidgets import QApplication

from jarvis.bootstrap import build_application
from jarvis.core.config import JarvisSettings
from jarvis.core.interaction import AssistantEvent, AssistantReply, build_reply
from jarvis.core.request_control import RequestControl, request_scope
from jarvis.core.runtime_identity import runtime_facts
from jarvis.models.base import ModelProvider, ModelRequest, ModelToolDefinition
from jarvis.models.chatgpt_account import ChatGPTAccount
from jarvis.models.chatgpt_plan import ChatGPTPlanProvider
from jarvis.models.connection_errors import ProviderConnectionError
from jarvis.models.openai_compatible import OpenAICompatibleProvider
from jarvis.models.retry import retry_guard
from jarvis.security.capabilities import Capability
from jarvis.security.credential_vault import CredentialVault
from jarvis.security.policy import PermissionDecision
from jarvis.tools.desktop_context import DesktopContext, is_jarvis_window
from jarvis.tools.screen_observation import ScreenObservationTool
from jarvis.ui.pages.chat_page import ChatPage
from jarvis.ui.voice_panel import VoiceController


class Unavailable(ModelProvider):
    name = "unavailable"
    def generate(self, request):
        raise AssertionError("A local action or microphone status must not call any AI service")


@pytest.fixture
def qt():
    return QApplication.instance() or QApplication([])


@pytest.mark.parametrize("prompt,expected", [("Open Google", "https://www.google.com/"),
                                              ("Search Google for Python documentation", "https://www.google.com/search?q=Python+documentation")])
@pytest.mark.parametrize("screen_on", [False, True])
def test_local_open_and_search_survive_unavailable_ai_and_no_screen_target(tmp_path, monkeypatch, prompt, expected, screen_on):
    app = build_application(JarvisSettings(workspace_dir=tmp_path))
    app.cloud_provider = Unavailable()
    app.model_provider = Unavailable()
    app.screen_control_enabled = screen_on
    screen = app.tool_service.registry.get("observe_screen")
    assert isinstance(screen, ScreenObservationTool)
    monkeypatch.setattr(screen, "enabled", screen_on)
    monkeypatch.setattr(screen, "capture", lambda _:pytest.fail("Simple local action captured the screen"))
    app.tool_service.executor.policy.set_decision(Capability.USE_BROWSER, PermissionDecision.ALLOW)
    opened = []
    monkeypatch.setattr(app.tool_service.registry.get("open_url"), "_opener", lambda url:opened.append(url) or True)
    try:
        reply = app.interact(prompt)
        assert reply.kind == "action" and opened == [expected]
        assert not any(event.tool == "observe_screen" for event in reply.events)
    finally:
        app.shutdown()


def test_voice_health_uses_real_input_channel_and_no_model(qt, tmp_path, monkeypatch):
    from test_assistant_interruption import spin
    app = build_application(JarvisSettings(workspace_dir=tmp_path))
    app.cloud_provider = Unavailable()
    page = ChatPage(app, "Be helpful")
    spoken = []
    monkeypatch.setattr(page.voice_panel.controller, "say", spoken.append)
    try:
        page._voice_prompt("Can you hear me clearly?")
        spin(qt, lambda:page.worker_thread is None)
        assert page._reply is not None and page._reply.message == "Yes, I heard you. Your words came through."
        assert spoken == [page._reply.message]
        typed = app.interact("Can you hear me clearly?", request_control=RequestControl(input_source="text"))
        assert "typed message" in typed.message
    finally:
        page._stop_request()
        spin(qt, lambda:page.worker_thread is None)
        page.voice_panel.controller.shutdown()
        page.close()
        app.shutdown()


@pytest.mark.parametrize(("prompt", "url"), [
    ("Google, Google, I told you to open Google.", "https://www.google.com/"),
    ("Can you open ExampleMedia?", "https://www.google.com/search?q=ExampleMedia"),
    ("Could you open examples.org?", "https://examples.org"),
])
def test_voice_open_bypasses_stale_search_and_shared_screen(tmp_path, monkeypatch, prompt, url):
    from jarvis.tools.application_catalog import ApplicationNotFoundError

    app = build_application(JarvisSettings(workspace_dir=tmp_path))
    app.screen_control_enabled = True
    app.interaction.search_memory.pending_engine = "youtube"
    app.interaction.search_memory.pending_request = "Find a video"
    app.tool_service.executor.policy.set_decision(Capability.USE_BROWSER, PermissionDecision.ALLOW)
    opened = []
    monkeypatch.setattr(app, "_route_agent_request", lambda *_: pytest.fail("Opening contacted AI"))
    monkeypatch.setattr(app.tool_service.registry.get("open_url"), "_opener", lambda url: opened.append(url) or True)
    catalog = app.tool_service.registry.get("open_application").catalog
    def not_installed(name):
        raise ApplicationNotFoundError(name)
    monkeypatch.setattr(catalog, "resolve", not_installed)
    try:
        reply = app.interact(prompt, request_control=RequestControl(input_source="voice"))
        assert reply.kind == "action" and opened == [url]
        assert app.interaction.search_memory.pending_engine == ""
    finally:
        app.shutdown()


def test_groq_wait_survives_provider_recreation_and_leaves_local_open_available(tmp_path, monkeypatch):
    from types import SimpleNamespace

    clock = [100.0]
    monkeypatch.setattr("jarvis.models.connection_errors.time", SimpleNamespace(monotonic=lambda: clock[0]))
    app = build_application(JarvisSettings(workspace_dir=tmp_path, groq_api_key="fixture"))
    assert app.intelligence is not None
    calls = []
    def rate_limited(request):
        calls.append(request)
        return httpx.Response(429, headers={"Retry-After": "33"})
    try:
        provider = app.intelligence.provider("groq")
        assert isinstance(provider, OpenAICompatibleProvider)
        provider.transport = httpx.MockTransport(rate_limited)
        with pytest.raises(ProviderConnectionError) as first:
            provider.generate(ModelRequest(prompt="Question"))
        reply = build_reply(str(first.value), (), error=first.value)
        assert "33 seconds" in reply.message and "Local commands are still available" in reply.message
        assert any(event.operation == "provider_limit" for event in reply.events)
        clock[0] += 8
        other = app.intelligence.provider("groq")
        assert isinstance(other, OpenAICompatibleProvider)
        other.transport = httpx.MockTransport(rate_limited)
        with pytest.raises(ProviderConnectionError) as second:
            other.generate(ModelRequest(prompt="Another question"))
        assert second.value.retry_after == 25 and len(calls) == 1
        app.tool_service.executor.policy.set_decision(Capability.USE_BROWSER, PermissionDecision.ALLOW)
        monkeypatch.setattr(app.tool_service.registry.get("open_url"), "_opener", lambda _: True)
        assert app.interact("Open Google").kind == "action" and len(calls) == 1
        clock[0] += 26
        with pytest.raises(ProviderConnectionError):
            other.generate(ModelRequest(prompt="After reset"))
        assert len(calls) == 2
    finally:
        app.shutdown()


def test_active_app_tracking_survives_jarvis_taking_focus(monkeypatch):
    import win32gui
    import win32process
    current = [1]
    monkeypatch.setattr(win32gui, "IsWindow", lambda handle:handle in {1,2,9})
    monkeypatch.setattr(win32gui, "IsWindowVisible", lambda _:True)
    monkeypatch.setattr(win32gui, "IsIconic", lambda _:False)
    monkeypatch.setattr(win32gui, "GetWindowText", lambda handle:{1:"Browser",2:"Editor",9:"JARVIS"}[handle])
    monkeypatch.setattr(win32gui, "GetForegroundWindow", lambda:current[0])
    monkeypatch.setattr(win32process, "GetWindowThreadProcessId", lambda handle:(1,os.getpid() if handle==9 else os.getpid()+1))
    context = DesktopContext()
    assert context.current_window() == 1
    current[0] = 9
    assert context.current_window() == 1
    current[0] = 2
    assert context.current_window() == 2
    current[0] = 9
    assert context.current_window() == 2
    assert not is_jarvis_window(1, "Jarvis project on GitHub")
    assert is_jarvis_window(9, "Voice settings")


def test_screen_switch_needs_no_app_picker_or_image_capture(qt, tmp_path, monkeypatch):
    app = build_application(JarvisSettings(workspace_dir=tmp_path))
    page = ChatPage(app, "Help")
    screen = app.tool_service.registry.get("observe_screen")
    assert isinstance(screen, ScreenObservationTool)
    monkeypatch.setattr(screen.context, "current_window", lambda:123)
    monkeypatch.setattr(screen, "capture", lambda _:pytest.fail("Switching on captured an image"))
    try:
        page.screen_panel.enabled.setChecked(True)
        assert app.screen_control_enabled and screen.follow_active and screen.window_handle == 123
        assert not hasattr(page.screen_panel, "window_choice")
        page.screen_panel.enabled.setChecked(False)
        assert not screen.enabled and not page.screen_panel.timer.isActive()
    finally:
        page.voice_panel.controller.shutdown()
        page.close()
        app.shutdown()


def test_groq_planner_requests_json_output_without_native_tools_or_images():
    captured = []
    def handle(request):
        data = json.loads(request.content)
        captured.append(data)
        assert data["response_format"]["type"] == "json_schema"
        assert data["response_format"]["json_schema"]["strict"] is True
        assert "tools" not in data and isinstance(data["messages"][-1]["content"], str)
        return httpx.Response(200, json={"choices":[{"message":{"content":json.dumps({"result_json":'{"action":"finish"}'})}}]})
    provider = OpenAICompatibleProvider(provider_name="groq", model="openai/gpt-oss-20b", base_url="https://example.com", api_key="test", transport=httpx.MockTransport(handle))
    reply = provider.generate(ModelRequest(prompt="Return JSON for the next action", json_output=True))
    assert json.loads(reply.text) == {"action":"finish"}
    assert len(captured) == 1


def test_plan_sends_image_and_stops_reading_after_authoritative_completion():
    class CompletedStream(httpx.SyncByteStream):
        def __iter__(self):
            yield b'data: {"type":"response.output_text.delta","delta":"Visible result"}\n\n'
            yield b'data: {"type":"response.completed"}\n\n'
            raise AssertionError("The provider read the idle tail after completion")
    def handle(request):
        data = json.loads(request.content)
        parts = data["input"][-1]["content"]
        assert "json" in parts[0]["text"].casefold()
        assert parts[-1] == {"type":"input_image", "image_url":"data:image/png;base64,fixture-image"}
        assert data["text"]["format"]["type"] == "json_object"
        return httpx.Response(200, headers={"content-type":"text/event-stream"}, stream=CompletedStream())
    account = ChatGPTAccount(CredentialVault(), httpx.MockTransport(handle))
    with patch.object(account, "access_token", return_value="test"):
        reply = ChatGPTPlanProvider(account, "gpt-6.1-sol").generate(ModelRequest(prompt='{"goal":"Read the reference"}', system_prompt="Return JSON", images=["fixture-image"], json_output=True))
    assert reply.text == "Visible result"


def test_hands_free_discards_recent_playback_echo_but_allows_short_commands(qt):
    voice = VoiceController()
    voice.enabled = voice.ready = voice.continuous = True
    received = []
    voice.transcript.connect(received.append)
    voice.say("I could not finish that request. Please try again.")
    assert not voice._is_playback_echo("I could not finish that request.")
    voice._playing_text = voice._speech_text
    voice._receive({"type":"transcript", "epoch":voice.epoch, "text":"I could not finish that request."})
    assert not received
    voice.say("Opened Google.")
    voice._playing_text = voice._speech_text
    voice._receive({"type":"transcript", "epoch":voice.epoch, "text":"Opened Google."})
    assert not received
    voice._receive({"type":"transcript", "epoch":voice.epoch, "text":"Jarvis, Open Google"})
    assert received == ["Open Google"]
    voice.shutdown()


def test_failed_reply_pauses_hands_free_instead_of_restarting(qt, tmp_path, monkeypatch):
    app = build_application(JarvisSettings(workspace_dir=tmp_path))
    page = ChatPage(app, "Help")
    voice = page.voice_panel.controller
    voice.continuous = voice.ready = True
    spoken = []
    monkeypatch.setattr(voice, "say", spoken.append)
    try:
        page._handle_reply(AssistantReply("failed", "Groq returned HTTP 503.", "Groq returned HTTP 503.", "Service is busy"))
        assert not voice.continuous and voice.session_paused and not voice._resume_timer.isActive()
        assert spoken == ["Groq returned HTTP 503."]
        monkeypatch.setattr(voice, "begin_recording", lambda:pytest.fail("Failed session resumed automatically"))
        voice._resume_listening()
    finally:
        voice.shutdown()
        page.close()
        app.shutdown()


def test_provider_cooldown_does_not_pause_the_microphone(qt, tmp_path, monkeypatch):
    app = build_application(JarvisSettings(workspace_dir=tmp_path))
    page = ChatPage(app, "Help")
    voice = page.voice_panel.controller
    voice.continuous = voice.ready = True
    monkeypatch.setattr(voice, "say", lambda _: None)
    try:
        error = ProviderConnectionError("Groq limit", status_code=429, retry_after=33, provider="groq")
        page._handle_reply(build_reply(str(error), (), error=error))
        assert voice.continuous and not voice.session_paused
    finally:
        voice.shutdown()
        page.close()
        app.shutdown()


def test_spoken_result_keeps_requested_value_after_two_sentences():
    text = "Details are open. The test finished. The reference is LIME-27."
    reply = build_reply(text, [AssistantEvent("action_done", "Clicked Show details.", tool="click_ui_element"), AssistantEvent("summary", text)])
    assert "LIME-27" in reply.spoken_text


def test_runtime_identity_is_derived_from_current_permissions(tmp_path):
    app = build_application(JarvisSettings(workspace_dir=tmp_path))
    try:
        app.tool_service.executor.policy.set_decision(Capability.USE_BROWSER, PermissionDecision.ALLOW)
        facts = runtime_facts(app, "voice")
        assert facts["input"] == "voice" and facts["tools"]["open_url"] == "ALLOW" and facts["screen_access"] is False
        app.screen_control_enabled = True
        assert runtime_facts(app)["screen_access"] is True
    finally:
        app.shutdown()


def test_provider_problem_is_named_in_the_main_reply():
    reply = build_reply("Details", [], error=ProviderConnectionError("groq · HTTP 503: Service is temporarily busy.", status_code=503))
    assert "groq" in reply.message and "503" in reply.message and "busy" in reply.message


def test_plan_stream_failure_reports_the_actual_reason():
    def handle(request):
        event = {"type":"response.failed", "response":{"error":{"message":"The selected model is temporarily unavailable."}}}
        return httpx.Response(200, text="data: " + json.dumps(event) + "\n\n")
    account = ChatGPTAccount(CredentialVault(), httpx.MockTransport(handle))
    with (
        patch.object(account, "access_token", return_value="test"),
        pytest.raises(ProviderConnectionError, match="selected model is temporarily unavailable"),
    ):
        ChatGPTPlanProvider(account, "gpt-6.1-sol").generate(ModelRequest(prompt="Hello"))


def test_windows_focus_waits_for_async_activation(monkeypatch):
    import win32gui

    from jarvis.tools.window_catalog import Win32WindowBackend
    foreground = [1]
    monkeypatch.setattr(win32gui, "IsWindow", lambda _:True)
    monkeypatch.setattr(win32gui, "IsIconic", lambda _:False)
    monkeypatch.setattr(win32gui, "GetForegroundWindow", lambda:foreground[0])
    monkeypatch.setattr(win32gui, "BringWindowToTop", lambda _:None)
    monkeypatch.setattr(win32gui, "SetForegroundWindow", lambda _:None)
    waits = []
    def activate(handle):
        waits.append(handle)
        foreground[0] = handle
    backend = Win32WindowBackend()
    monkeypatch.setattr(backend, "_wait_for_focus", activate)
    backend.focus(5)
    assert waits == [5] and foreground[0] == 5


def test_windows_focus_failure_detaches_the_input_queue(monkeypatch):
    import win32api
    import win32gui
    import win32process

    from jarvis.tools.window_catalog import Win32WindowBackend
    monkeypatch.setattr(win32gui, "IsWindow", lambda _:True)
    monkeypatch.setattr(win32gui, "IsIconic", lambda _:False)
    monkeypatch.setattr(win32gui, "GetForegroundWindow", lambda:1)
    monkeypatch.setattr(win32gui, "BringWindowToTop", lambda _:None)
    monkeypatch.setattr(win32gui, "SetForegroundWindow", lambda _:None)
    monkeypatch.setattr(win32api, "GetCurrentThreadId", lambda:10)
    monkeypatch.setattr(win32process, "GetWindowThreadProcessId", lambda _:(20, 30))
    attached = []
    monkeypatch.setattr(win32process, "AttachThreadInput", lambda a,b,enabled:attached.append((a,b,enabled)))
    backend = Win32WindowBackend()
    monkeypatch.setattr(backend, "_wait_for_focus", lambda _:None)
    with pytest.raises(ValueError, match="No keyboard or mouse input was sent"):
        backend.focus(5)
    assert attached == [(10,20,True), (10,20,False)]


def test_rejected_groq_controller_data_is_regenerated_with_shared_budget():
    calls, authorizations = [], []
    def handle(request):
        calls.append(json.loads(request.content))
        if len(calls) == 1:
            return httpx.Response(400, json={"error":{"code":"tool_use_failed", "failed_generation":"untrusted action"}})
        return httpx.Response(200, json={"choices":[{"message":{"content":json.dumps({"result_json":'{"action":"finish"}'})}}]})
    provider = OpenAICompatibleProvider(provider_name="groq", model="openai/gpt-oss-20b", base_url="https://example.com", api_key="test", transport=httpx.MockTransport(handle))
    control = RequestControl()
    with request_scope(control), retry_guard(lambda:authorizations.append(True)):
        result = provider.generate(ModelRequest(prompt="Return JSON", json_output=True))
    assert json.loads(result.text) == {"action":"finish"}
    assert len(calls) == 2 and control.retry_budget.used == 1 and authorizations == [True]
    assert "untrusted action" not in json.dumps(calls)


@pytest.mark.parametrize("status,code,count", [(400,"json_validate_failed",3), (400,"output_parse_failed",3), (401,"invalid_api_key",1), (400,"invalid_request",1)])
def test_groq_format_repair_is_bounded_and_does_not_retry_other_errors(status, code, count):
    calls = []
    def handle(request):
        calls.append(True)
        return httpx.Response(status, json={"error":{"code":code}})
    provider = OpenAICompatibleProvider(provider_name="groq", model="openai/gpt-oss-20b", base_url="https://example.com", api_key="test", transport=httpx.MockTransport(handle))
    with request_scope(RequestControl()), pytest.raises(ProviderConnectionError):
        provider.generate(ModelRequest(prompt="Return JSON", json_output=True))
    assert len(calls) == count


def test_final_speech_replaces_pending_progress_and_ignores_its_completion(qt, monkeypatch):
    voice = VoiceController()
    voice.enabled = voice.ready = True
    sent = []
    monkeypatch.setattr(voice, "_send", lambda kind, **values:sent.append((kind, values)))
    voice.say("Working in the browser.")
    old_epoch = voice.epoch
    voice._playback.extend(b"\0\0")
    voice.say("The status is ready.")
    assert voice.epoch > old_epoch and not voice._playback and not voice._synthesis_done
    voice._receive({"type":"speech_done", "epoch":old_epoch})
    assert not voice._synthesis_done
    assert [kind for kind, _ in sent] == ["speak", "stop", "speak"]
    voice.shutdown()


def test_native_groq_wire_contract_repairs_rejected_proposal_without_running_it():
    payloads = []
    def handle(request):
        data = json.loads(request.content)
        payloads.append(data)
        assert data["tool_choice"] == "required" and data["parallel_tool_calls"] is False
        assert data["reasoning_effort"] == "low" and "response_format" not in data
        if len(payloads) == 1:
            return httpx.Response(400, json={"error":{"code":"output_parse_failed"}})
        return httpx.Response(200, json={"choices":[{"message":{"content":None,"tool_calls":[{
            "id":"actual-call", "type":"function", "function":{"name":"inspect", "arguments":"{}"}}]}}]})
    provider = OpenAICompatibleProvider(provider_name="groq", model="openai/gpt-oss-20b", base_url="https://example.com", api_key="test", transport=httpx.MockTransport(handle))
    reply = provider.generate(ModelRequest(prompt="Inspect the current app", tool_choice="required",
        tools=[ModelToolDefinition(name="inspect", description="Read the app", parameters={"type":"object","properties":{}})]))
    assert len(payloads) == 2 and reply.tool_calls[0].call_id == "actual-call"
    assert "attached function" in payloads[-1]["messages"][-1]["content"]
