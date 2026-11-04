import asyncio
import json
import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication

from jarvis.agents.screen_workflow import action_request, run_screen
from jarvis.bootstrap import build_application
from jarvis.core.config import JarvisSettings
from jarvis.core.fast_command_router import FastCommandRouter
from jarvis.core.interaction import AssistantReply, InteractionSession
from jarvis.core.request_control import RequestControl, request_scope
from jarvis.models.base import (
    ModelMessage,
    ModelProvider,
    ModelRequest,
    ModelResponse,
    ModelToolCall,
)
from jarvis.models.gemini import GeminiProvider
from jarvis.models.openai_compatible import OpenAICompatibleProvider
from jarvis.security.capabilities import Capability
from jarvis.security.policy import PermissionDecision
from jarvis.tools.screen_observation import ScreenObservationTool
from jarvis.ui.pages.chat_page import ChatPage
from jarvis.ui.voice_panel import VoicePanel
from jarvis.voice.endpointer import SpeechEndpointer


class Script(ModelProvider):
    name = "fixture"
    def __init__(self, plans):
        self.plans = iter(plans)
        self.requests = []
    def generate(self, request):
        self.requests.append(request)
        plan = next(self.plans)
        return ModelResponse(text=json.dumps(plan), provider="fixture", model="fixture")


@pytest.fixture
def qt():
    return QApplication.instance() or QApplication([])


@pytest.mark.parametrize("goal", ["show me the stock market", "check the weather in Munich", "find a recipe with chickpeas", "compare headphones under 100 euros"])
def test_compound_browser_goal_preserves_full_task(goal):
    turn = InteractionSession().prepare("Open Google and " + goal, FastCommandRouter(), "")
    assert turn.prompt == "browser: Open https://www.google.com/ and " + goal
    assert not turn.opening and not turn.clarification


def test_first_result_resumes_the_actual_search_page():
    session = InteractionSession(focus_url="https://www.google.com/search?q=learning+python")
    turn = session.prepare("Open the first result", FastCommandRouter(), "")
    assert turn.prompt == "browser: Open https://www.google.com/search?q=learning+python and Open the first result"


@pytest.mark.parametrize("text", ["Open Google and show the forecast", "You have to search", "Can you read this page?", "Click the first result", "What is on my screen?"])
def test_screen_intents_are_operation_based(text):
    assert action_request(text)


@pytest.mark.parametrize("text", ["Do not open Google", "Explain SQL joins", "Remember my name is Salem"])
def test_conversation_and_negative_instructions_do_not_trigger_screen_actions(text):
    assert not action_request(text)


def test_screen_loop_observes_after_each_action_and_sends_images():
    provider = Script([{"tool":"list_ui_elements", "arguments":{"window":"Fixture"}},
                       {"tool":"click_ui_element", "arguments":{"window":"Fixture", "element":"Documentation", "control_type":"Hyperlink"}},
                       {"action":"finish", "status":"complete", "answer":"The documentation page is open."},
                       {"satisfied":True,"missing":""}])
    observations, calls = [], []
    def observe():
        image = "image-" + str(len(observations))
        observations.append(image)
        return {"window":"Fixture", "image":image}
    def execute(name, arguments):
        calls.append((name, arguments))
        return {"ok":True, "elements":[{"name":"Documentation", "control_type":"Hyperlink"}]}
    answer = run_screen(provider, execute, observe, [], "Open the documentation link", [], {"click_ui_element":"ALLOW"})
    assert len(observations) == 3 and len(calls) == 2
    assert [r.images for r in provider.requests] == [[image] for image in observations] + [[observations[-1]]]
    assert json.loads(provider.requests[-2].prompt)["permissions"]["click_ui_element"] == "ALLOW"
    assert answer == "The documentation page is open."


def test_screen_blocker_is_not_reported_as_completion():
    model = Script([{"action":"finish", "status":"blocked", "answer":"The account is not connected."}])
    answer = run_screen(model, lambda *_:None, lambda:{"window":"Fixture", "image":"png"}, [], "Read my totals", [], {})
    assert answer.startswith("Task not completed.")


def test_pre_action_speech_does_not_repeat_unverified_model_claims():
    model = Script([{"tool":"click_ui_element", "arguments":{"window":"Fixture", "element":"Details"},
                     "spoken":"I already clicked it. Your balance is 100."},
                    {"action":"finish", "status":"complete", "answer":"Details are open."},
                    {"satisfied":True,"missing":""}])
    control = RequestControl()
    with request_scope(control):
        run_screen(model, lambda *_:{"ok":True}, lambda:{"window":"Fixture", "image":"png"}, [], "Open details", [], {})
    narration = [event.message for event in control.events if event.stage == "narration"]
    assert narration == ["Working in Fixture…"]


def test_finish_cannot_skip_requested_action_or_omit_requested_information():
    model = Script([
        {"action":"finish", "status":"complete", "answer":"The panel is closed."},
        {"tool":"click_ui_element", "arguments":{"window":"Fixture", "element":"Details"}},
        {"action":"finish", "status":"complete", "answer":"Details are open."},
        {"satisfied":False,"missing":"The user also asked for the displayed reference. Read and report it."},
        {"action":"finish", "status":"complete", "answer":"Reference: TEST-42."},
        {"satisfied":True,"missing":""},
    ])
    calls = []
    def execute(name, arguments):
        calls.append(name)
        return {"ok":True}
    answer = run_screen(model, execute, lambda:{"window":"Fixture", "controls":[{"name":"Reference: TEST-42"}]}, [],
                        "Click Details and read its reference", [], {}, use_images=False)
    assert answer == "Reference: TEST-42." and calls == ["click_ui_element"]
    assert "completion_rejected" in model.requests[1].prompt
    assert "also asked for the displayed reference" in model.requests[4].prompt
    review = json.loads(model.requests[-1].prompt)
    assert review["proposed_speech"] == "Reference: TEST-42."


def test_groq_screen_actions_use_native_functions_and_verify_the_result():
    class GroqScript(ModelProvider):
        name = "groq"
        def __init__(self):
            self.requests = []
        def generate(self, request):
            self.requests.append(request)
            if request.json_output:
                return ModelResponse(text='{"satisfied":true,"missing":""}', provider="groq", model="fixture")
            assert request.tool_choice == "required"
            assert "finish_screen_task" in [tool.name for tool in request.tools]
            assert "tools" not in json.loads(request.prompt)
            if len(self.requests) == 1:
                call = ModelToolCall(call_id="one", name="click_ui_element", arguments={"window":"Fixture", "element":"Details"})
            else:
                call = ModelToolCall(call_id="two", name="finish_screen_task", arguments={"status":"complete", "answer":"Reference: TEST-42", "spoken":"Reference: TEST-42"})
            return ModelResponse(text="", provider="groq", model="fixture", tool_calls=[call])
    calls = []
    model = GroqScript()
    tools = [{"name":"click_ui_element", "description":"Click a named control", "parameters":{"type":"object"}}]
    answer = run_screen(model, lambda name,args:calls.append(name) or {"ok":True},
        lambda:{"window":"Fixture", "controls":[{"name":"Reference: TEST-42"}]}, tools,
        "Click Details and read its reference", [], {}, use_images=False)
    assert answer == "Reference: TEST-42" and calls == ["click_ui_element"]


def test_unavailable_screen_action_is_never_executed():
    model = Script([{"tool":"run_command", "arguments":{"command":"unsafe"}}])
    calls = []
    with pytest.raises(ValueError, match="unavailable"):
        run_screen(model, lambda *args:calls.append(args), lambda:{"window":"Fixture", "image":"png"}, [], "Read page", [], {})
    assert not calls


def test_screen_tool_requires_explicit_session_enable():
    calls = []
    tool = ScreenObservationTool(capture=lambda handle:calls.append(handle) or "png")
    with pytest.raises(PermissionError, match="off"):
        tool.execute({})
    assert not calls


def test_screen_images_cannot_escape_into_ordinary_text_tool_history(tmp_path, monkeypatch):
    app = build_application(JarvisSettings(workspace_dir=tmp_path))
    try:
        tool = app.tool_service.registry.get("observe_screen")
        monkeypatch.setattr(tool, "enabled", True)
        calls = []
        monkeypatch.setattr(tool, "capture", lambda handle:calls.append(handle) or "image")
        assert tool not in app.tool_service.registry.tools()
        with pytest.raises(PermissionError, match="trusted screen workflow"):
            tool.execute({})
        assert not calls
    finally:
        app.shutdown()


def test_application_screen_permission_and_ephemeral_images(tmp_path, monkeypatch):
    import win32gui
    app = build_application(JarvisSettings(workspace_dir=tmp_path))
    screen = app.tool_service.registry.get("observe_screen")
    monkeypatch.setattr(screen, "capture", lambda _handle:"private-image-data")
    monkeypatch.setattr(screen, "window_handle", 123)
    monkeypatch.setattr(screen, "enabled", True)
    monkeypatch.setattr(win32gui, "IsWindow", lambda handle:handle == 123)
    monkeypatch.setattr(win32gui, "GetForegroundWindow", lambda:123)
    monkeypatch.setattr(win32gui, "GetWindowText", lambda _handle:"Fixture app")
    app.screen_control_enabled = True
    provider = Script([{"action":"finish", "status":"complete", "answer":"The page says Welcome."},
                       {"satisfied":True,"missing":""}])
    app.cloud_provider = provider
    try:
        app.tool_service.executor.policy.set_decision(Capability.INSPECT_UI, PermissionDecision.DENY)
        denied = app.interact("Read this page")
        assert denied.kind == "failed" and not provider.requests
        assert "Inspect Ui" in denied.message
        app.tool_service.executor.policy.set_decision(Capability.INSPECT_UI, PermissionDecision.ALLOW)
        reply = app.interact("Read this page")
        assert reply.kind == "action" and "Welcome" in reply.message
        assert provider.requests[0].images == ["private-image-data"]
        assert "private-image-data" not in str(app.conversation.snapshot())
    finally:
        app.shutdown()


def test_provider_adapters_attach_images_to_current_user_only():
    request = ModelRequest(prompt="Read this", system_prompt="Be accurate", images=["base64png"], messages=[
        ModelMessage(role="user", content="Earlier"), ModelMessage(role="assistant", content="Okay"), ModelMessage(role="user", content="Read this")])
    compatible = OpenAICompatibleProvider(provider_name="fixture", model="x", base_url="https://example.com", api_key="key")
    messages = compatible._build_messages(request)
    assert messages[0]["content"] == "Earlier"
    parts = messages[-1]["content"]
    assert isinstance(parts, list)
    assert parts[-1] == {"type":"image_url", "image_url":{"url":"data:image/png;base64,base64png"}}
    gemini = GeminiProvider(provider_name="gemini", model="x", base_url="https://example.com", api_key="key")
    payload = gemini._native_payload(request)
    assert payload["contents"][-1]["parts"][-1] == {"inlineData":{"mimeType":"image/png", "data":"base64png"}}
    assert request.messages[-1].content == "Read this" and "base64png" not in repr(request)


def test_copy_buttons_and_selectable_reply(qt, tmp_path, monkeypatch):
    app = build_application(JarvisSettings(workspace_dir=tmp_path))
    page = ChatPage(app, "Be helpful")
    copied = []
    monkeypatch.setattr("jarvis.ui.pages.chat_page.copy_text", copied.append)
    try:
        page._handle_reply(AssistantReply("answer", "Short reply", "Short reply", "Full details"))
        page.copy_reply_button.click()
        assert copied[-1] == "Short reply\n\nFull details"
        page.chat_view.setPlainText("You: hello\nJarvis: hello")
        page.copy_chat_button.click()
        assert copied[-1] == page.chat_view.toPlainText() + "\n\nJARVIS:\nFull details"
        assert page.copy_reply_button.text() == "Copied ✓"
        assert page.activity_message.textInteractionFlags() & Qt.TextInteractionFlag.TextSelectableByMouse
        assert page.activity_message.textInteractionFlags() & Qt.TextInteractionFlag.TextSelectableByKeyboard
    finally:
        page.voice_panel.controller.shutdown()
        page.close()
        app.shutdown()


def test_click_to_talk_does_not_require_holding(qt, monkeypatch):
    panel = VoicePanel()
    calls = []
    def begin():
        calls.append("begin")
        monkeypatch.setattr(panel.controller, "source", object())
    def finish():
        calls.append("finish")
        monkeypatch.setattr(panel.controller, "source", None)
    monkeypatch.setattr(panel.controller, "begin_recording", begin)
    monkeypatch.setattr(panel.controller, "finish_recording", finish)
    panel.talk.setEnabled(True)
    panel.talk.click()
    assert calls == ["begin"] and panel.talk.text() == "Send"
    panel.talk.click()
    assert calls == ["begin", "finish"] and panel.talk.text() == "Talk"
    panel.controller.shutdown()
    panel.close()


def test_hands_free_resumes_only_when_idle(qt, monkeypatch):
    panel = VoicePanel()
    voice = panel.controller
    voice.duplex_enabled = False  # Legacy non-overlapping mode; no real devices.
    voice.continuous = voice.ready = True
    started = []
    monkeypatch.setattr(voice, "begin_recording", lambda:started.append(True))
    voice.chat_busy = True
    voice._resume_listening()
    voice.chat_busy = False
    voice._synthesis_done = False
    voice._resume_listening()
    voice._synthesis_done = True
    voice.recognizing = True
    voice._resume_listening()
    assert not started
    voice.recognizing = False
    voice._resume_listening()
    assert started == [True]
    voice.stop_session()
    voice._resume_listening()
    assert started == [True] and not voice._resume_timer.isActive()
    voice.shutdown()
    panel.close()


def test_endpointer_keeps_pre_roll_and_bounds_silence_and_utterance():
    from enum import Enum
    class State(Enum):
        QUIET = 0
        SPEAKING = 1
    class Analyzer:
        state = State.QUIET
        async def analyze_audio(self, _audio): return self.state
        async def cleanup(self): pass
    async def exercise():
        analyzer = Analyzer()
        endpoint = SpeechEndpointer(analyzer)
        await endpoint.feed(b"\0" * 50000)
        assert len(endpoint.pre_roll) == 12800 and not endpoint.segment
        analyzer.state = State.SPEAKING
        started, segment = await endpoint.feed(b"\1" * 1024)
        assert started and segment is None and len(endpoint.segment) == 13824
        analyzer.state = State.QUIET
        _, segment = await endpoint.feed(b"\0" * 1024)
        assert segment is not None and len(segment) == 14848 and not endpoint.segment
        analyzer.state = State.SPEAKING
        _, segment = await endpoint.feed(b"\1" * (21 * 32000))
        assert segment is not None and len(segment) == 20 * 32000
        await endpoint.close()
    asyncio.run(exercise())


def test_screen_image_encoder_uses_actual_qt_png_writer(qt):
    import base64

    from PySide6.QtGui import QImage

    from jarvis.tools.screen_observation import encode_image
    image = QImage(2000, 1200, QImage.Format.Format_RGB32)
    image.fill(Qt.GlobalColor.white)
    raw = base64.b64decode(encode_image(image))
    assert raw.startswith(b"\x89PNG")
    restored = QImage.fromData(raw)
    assert restored.width() <= 1440 and restored.height() <= 1000
