import threading
import time
from types import SimpleNamespace

import pytest
from PySide6.QtWidgets import QApplication

from jarvis.agents.browser_workflow import run_browser
from jarvis.bootstrap import build_application
from jarvis.core.config import JarvisSettings
from jarvis.core.fast_command_router import FastCommandRouter
from jarvis.core.interaction import InteractionSession
from jarvis.core.navigation_reference import navigation_reference
from jarvis.core.request_control import RequestCancelledError, RequestControl
from jarvis.tools.browser_mcp import parse_snapshot
from jarvis.ui.pages.chat_page import ChatPage
from jarvis.ui.voice_panel import VoiceController


@pytest.fixture
def qt():
    return QApplication.instance() or QApplication([])


@pytest.mark.parametrize("text", ["open the first link", "Click the second result", "No, wait, go back", "go back", "Please go back"])
def test_navigation_references_are_page_relative(text):
    assert navigation_reference(text)


def test_current_browser_is_preserved_for_ordinal_and_back():
    session = InteractionSession(focus_url="https://example.com/results")
    for text in ("open the first link", "No, wait, go back"):
        prepared = session.prepare(text, FastCommandRouter(), session.focus_url)
        assert prepared.kind == "navigation" and prepared.resume_url == session.focus_url
        assert prepared.prompt == "browser: " + text


def test_barge_in_cancels_speech_without_stopping_microphone(qt, monkeypatch):
    voice = VoiceController()
    voice.ready = voice.enabled = voice.continuous = voice.duplex_enabled = True
    calls = []
    voice.duplex = SimpleNamespace(active=True, listening=True, silence=lambda epoch:calls.append(("silence",epoch)), stop=lambda:pytest.fail("Microphone stopped"))
    monkeypatch.setattr(voice, "_send", lambda kind, **_:calls.append((kind,voice.epoch)))
    started, recognized = [], []
    voice.speech_started.connect(lambda:started.append(True))
    voice.transcript.connect(recognized.append)
    old = voice.epoch
    capture = voice.capture_epoch
    voice._receive({"type":"speech_detected", "capture_epoch":capture})
    assert started == [True] and voice.epoch > old
    assert ("interrupt_speech",voice.epoch) in calls and voice.continuous
    assert voice.capture_epoch == capture and voice._visual_phase == "hearing"
    voice._receive({"type":"audio", "epoch":old, "rate":24000, "audio":"AAA="})
    assert not voice._playback
    voice._receive({"type":"utterance", "capture_epoch":capture})
    voice._receive({"type":"transcript", "capture_epoch":capture, "text":"No, wait, go back"})
    assert recognized == ["No, wait, go back"] and calls[-1][0] == "listen_start"
    voice.duplex = None
    voice.shutdown()


def test_voice_starts_speaking_a_streamed_sentence_and_only_queues_the_remainder(qt, tmp_path, monkeypatch):
    from jarvis.core.interaction import AssistantReply

    app = build_application(JarvisSettings(workspace_dir=tmp_path))
    page = ChatPage(app, "Help")
    voice = page.voice_panel.controller
    voice.enabled = voice.ready = True
    page.worker = SimpleNamespace(control=RequestControl(input_source="voice"))
    spoken, queued = [], []
    monkeypatch.setattr(voice, "say", spoken.append)
    monkeypatch.setattr(voice, "say_after_current", queued.append)
    try:
        first, second = "SQLite stores data in a file.", "It works without a separate database server."
        page._handle_delta(first + " It works")
        page._flush_delta()
        assert spoken == [first]
        final = first + " " + second
        page._handle_reply(AssistantReply("answer", final, final, final))
        assert spoken == [first] and queued == [second]
    finally:
        page.worker = None
        page.close()
        app.shutdown()


def test_voice_interrupt_discards_the_queued_remainder(qt, monkeypatch):
    voice = VoiceController()
    voice.enabled = voice.ready = voice.continuous = voice.duplex_enabled = True
    voice.duplex = SimpleNamespace(active=True, listening=True, silence=lambda _: None)
    monkeypatch.setattr(voice, "_send", lambda *_a, **_k: None)
    voice.say("This is the first sentence.")
    voice.say_after_current("This is the rest.")
    assert voice._queued_speech
    voice._receive({"type": "speech_detected", "capture_epoch": voice.capture_epoch})
    assert voice._queued_speech == ""
    voice.duplex = None
    voice.shutdown()


@pytest.mark.parametrize("phrase", ["Blue balloon.", "Blue balloons."])
def test_audio_check_hears_interruption_without_sending_it_to_chat(qt, monkeypatch, phrase):
    voice = VoiceController()
    voice.enabled = voice.ready = True
    device = SimpleNamespace(isNull=lambda: False)
    voice.input_device = voice.output_device = device
    messages, chat, paused = [], [], []
    voice.audio_check_status.connect(messages.append)
    voice.transcript.connect(chat.append)
    voice.speech_started.connect(lambda: paused.append(True))
    stops = []
    duplex = SimpleNamespace(active=True, listening=True, push=lambda *_: None,
                             silence=lambda *_: None, stop=lambda: stops.append(True))
    def start():
        voice.duplex = duplex
        voice._duplex_ready(True)

    monkeypatch.setattr(voice, "_start_duplex", start)
    monkeypatch.setattr(voice, "_send", lambda *_a, **_k: None)
    try:
        voice.start_audio_check()
        assert voice.audio_check_active and voice.continuous and voice._audio_check_timer.isActive()
        voice._receive({"type": "audio", "epoch": voice.epoch, "rate": 24000, "audio": "AAA="})
        assert "blue balloon" in messages[-1]
        capture = voice.capture_epoch
        voice._receive({"type": "speech_detected", "capture_epoch": capture})
        assert not stops and not paused and voice.capture_epoch == capture
        voice._receive({"type": "transcript", "capture_epoch": capture, "text": phrase})
        assert not chat and stops and messages[-1].startswith("Passed.")
        assert not voice.audio_check_active and not voice.continuous and not voice.duplex_enabled
        assert not voice._audio_check_timer.isActive()
    finally:
        voice.duplex = None
        voice.shutdown()


def test_pause_blocks_next_operation_and_cancel_releases_it():
    control = RequestControl()
    control.paused.set()
    result = []
    def task():
        try:
            control.check()
            result.append("action")
        except RequestCancelledError:
            result.append("cancelled")
    worker = threading.Thread(target=task)
    worker.start()
    time.sleep(0.05)
    assert not result
    control.cancelled.set()
    worker.join(1)
    assert result == ["cancelled"] and not worker.is_alive()


def test_voice_onset_pauses_worker_and_rejected_echo_resumes_it(qt, tmp_path):
    app = build_application(JarvisSettings(workspace_dir=tmp_path))
    page = ChatPage(app, "Help")
    control = RequestControl()
    page.worker = SimpleNamespace(control=control)
    try:
        page._pause_for_voice()
        assert control.paused.is_set() and not control.cancelled.is_set()
        page._resume_after_voice()
        assert not control.paused.is_set()
    finally:
        page.worker = None
        page.close()
        app.shutdown()


def test_clipboard_error_is_visible(qt, tmp_path, monkeypatch):
    app = build_application(JarvisSettings(workspace_dir=tmp_path))
    page = ChatPage(app, "Help")
    def busy(_):
        raise OSError("Windows clipboard is busy")
    monkeypatch.setattr("jarvis.ui.pages.chat_page.copy_text", busy)
    try:
        page._copy_reply()
        assert "clipboard is busy" in page.status_label.text()
        assert page.copy_reply_button.text() == "Copy reply"
    finally:
        page.close()
        app.shutdown()


def test_wait_and_continue_keep_the_same_task_without_replaying_it(qt, tmp_path):
    app = build_application(JarvisSettings(workspace_dir=tmp_path))
    page = ChatPage(app, "Help")
    control = RequestControl()
    worker = SimpleNamespace(control=control)
    page.worker = worker
    try:
        page._voice_prompt("Wait")
        assert control.paused.is_set() and not control.cancelled.is_set()
        page._resume_after_voice()  # Rejected background echo cannot release an explicit hold.
        assert control.paused.is_set()
        page._voice_prompt("Continue")
        assert not control.paused.is_set() and page.worker is worker
        assert not control.cancelled.is_set()
    finally:
        page.worker = None
        page.close()
        app.shutdown()


def test_ctrl_c_selected_chat_uses_verified_clipboard(qt, tmp_path, monkeypatch):
    from PySide6.QtCore import Qt
    from PySide6.QtTest import QTest
    app = build_application(JarvisSettings(workspace_dir=tmp_path))
    page = ChatPage(app, "Help")
    copied = []
    monkeypatch.setattr("jarvis.ui.pages.chat_page.copy_text", copied.append)
    try:
        page.chat_view.setPlainText("First line\nSecond line")
        page.chat_view.selectAll()
        QTest.keyClick(page.chat_view, Qt.Key.Key_C, Qt.KeyboardModifier.ControlModifier)
        assert copied == ["First line\nSecond line"]
    finally:
        page.close()
        app.shutdown()


def test_first_link_is_one_observed_navigation_not_a_repeating_planner_goal():
    calls = []
    def execute(arguments):
        calls.append(arguments)
        return {"url":"https://example.com/next" if arguments["action"] == "follow_link" else "https://example.com/", "title":"Next page", "links":[{"url":"https://example.com/next"}]}
    class NoModel:
        def generate(self, _):
            pytest.fail("A simple observed ordinal should not need AI planning")
    answer = run_browser(NoModel(), execute, "Open the first link", resume_url="https://example.com/")
    assert [call["action"] for call in calls] == ["snapshot","follow_link"] and "Next page" in answer


def test_search_result_order_excludes_non_heading_navigation_links():
    page = parse_snapshot('''Page URL: https://example.com/search
- link "Navigation":
  - /url: /nav
- link "First result":
  - /url: /first
  - heading "First result" [level=3]
- heading "Second result" [level=2]:
  - link "Second result":
    - /url: /second
''')
    assert [link["url"] for link in page["result_links"]] == ["https://example.com/first","https://example.com/second"]


def test_screen_relative_navigation_stops_after_one_confirmed_click():
    import json

    from jarvis.agents.screen_workflow import run_screen
    from jarvis.models.base import ModelResponse
    class Planner:
        name = "fixture"
        calls = 0
        def generate(self, request):
            self.calls += 1
            assert self.calls == 1, "The first-link request repeated on the next page"
            return ModelResponse(text=json.dumps({"tool":"click_ui_element", "arguments":{"window":"Browser", "element":"Observed first result"}}), provider="fixture", model="fixture")
    calls = []
    answer = run_screen(Planner(), lambda n,a:calls.append(n) or {"ok":True},
        lambda:{"window":"Browser", "controls":[]}, [], "Open the first link", [], {}, use_images=False, single_navigation=True)
    assert calls == ["click_ui_element"] and "Observed first result" in answer


def test_old_request_failure_does_not_drop_a_spoken_interruption(qt, tmp_path):
    from jarvis.core.interaction import AssistantReply
    app = build_application(JarvisSettings(workspace_dir=tmp_path))
    page = ChatPage(app, "Help")
    voice = page.voice_panel.controller
    voice.continuous = True
    try:
        page._pause_for_voice()
        page._handle_reply(AssistantReply("partial", "Old request failed", "Old request failed", "An earlier service failure"))
        assert voice.continuous and not voice.session_paused
    finally:
        page.close()
        app.shutdown()


def test_final_duplex_reply_replaces_audio_that_is_still_playing(qt, monkeypatch):
    voice = VoiceController()
    voice.enabled = voice.ready = voice.continuous = voice.duplex_enabled = True
    voice._duplex_playing = True
    silenced = []
    voice.duplex = SimpleNamespace(active=True, silence=silenced.append)
    monkeypatch.setattr(voice, "_send", lambda *_args, **_kwargs:None)
    old = voice.epoch
    voice.say("Here is the result.")
    assert voice.epoch > old and silenced == [voice.epoch] and not voice._duplex_playing
    voice.duplex = None
    voice.shutdown()


def test_native_clipboard_retries_actual_windows_busy_error(monkeypatch):
    import pywintypes
    import win32clipboard

    from jarvis.ui.clipboard import copy_text
    opened, stored = [], []
    def busy_then_open():
        opened.append(True)
        if len(opened) < 3:
            raise pywintypes.error(5, "OpenClipboard", "Access is denied.")
    monkeypatch.setattr(win32clipboard, "OpenClipboard", busy_then_open)
    monkeypatch.setattr(win32clipboard, "EmptyClipboard", lambda:None)
    monkeypatch.setattr(win32clipboard, "CloseClipboard", lambda:None)
    monkeypatch.setattr(win32clipboard, "SetClipboardText", lambda text,format:stored.append(text))
    monkeypatch.setattr(win32clipboard, "GetClipboardData", lambda format:stored[-1])
    copy_text("Copied ✓")
    assert len(opened) == 3 and stored == ["Copied ✓"]


def test_corrective_back_in_active_app_is_local_and_permission_gated(qt, tmp_path, monkeypatch):
    import win32gui

    from jarvis.security.capabilities import Capability
    from jarvis.security.policy import PermissionDecision
    app = build_application(JarvisSettings(workspace_dir=tmp_path))
    app.screen_control_enabled = True
    screen = app.tool_service.registry.get("observe_screen")
    screen.enabled = True
    screen.window_handle = 123
    calls = []
    monkeypatch.setattr(win32gui, "IsWindow", lambda _:True)
    monkeypatch.setattr(win32gui, "GetWindowText", lambda _:"Test Browser")
    monkeypatch.setattr(app.tool_service.registry.get("keyboard_action"), "execute", lambda args:calls.append(args) or {"ok":True})
    app.tool_service.executor.policy.set_decision(Capability.KEYBOARD_ACTION, PermissionDecision.ALLOW)
    try:
        reply = app.interact("No, wait, go back")
        assert reply.kind == "action" and calls == [{"window":"Test Browser","action":"browser_back"}]
        app.tool_service.executor.policy.set_decision(Capability.KEYBOARD_ACTION, PermissionDecision.DENY)
        denied = app.interact("go back")
        assert denied.kind == "failed" and len(calls) == 1
    finally:
        app.shutdown()
