import base64
from types import SimpleNamespace

import pytest
from PySide6.QtWidgets import QApplication

from jarvis.bootstrap import build_application
from jarvis.core.config import JarvisSettings
from jarvis.core.interaction import AssistantReply
from jarvis.ui.companion import DesktopCompanion
from jarvis.ui.orb import AssistantOrb
from jarvis.ui.pages.chat_page import ChatPage
from jarvis.ui.presence import AssistantPresence
from jarvis.ui.voice_panel import VoiceController


@pytest.fixture
def qt():
    return QApplication.instance() or QApplication([])


def test_opening_desktop_companion_does_not_request_capture(qt):
    state = AssistantPresence()
    companion = DesktopCompanion(state)
    requested = []
    companion.microphone_requested.connect(lambda:requested.append("microphone"))
    companion.screen_requested.connect(requested.append)
    companion.show();companion.set_expanded(True);qt.processEvents()
    try:
        assert not requested and not state.microphone and not state.screen
        assert companion.mic.text() == "Start listening" and companion.screen_button.text() == "Screen off"
    finally:
        companion.close()


def test_companion_screen_prompt_needs_explicit_allow(qt):
    state = AssistantPresence()
    companion = DesktopCompanion(state)
    changes = []
    companion.screen_requested.connect(changes.append)
    companion.show();companion.set_expanded(True)
    try:
        companion.screen_button.click()
        assert companion.share_prompt.isVisible() and not changes and not state.screen
        companion._deny_screen()
        assert not changes and not companion.share_prompt.isVisible()
        companion.screen_button.click();companion._allow_screen()
        assert changes == [True]
        state.update_state(screen=True)
        companion.screen_button.click()
        assert changes == [True,False]
    finally:
        companion.close()


def test_actual_audio_drives_speaking_not_merely_queued_text(qt, monkeypatch):
    voice = VoiceController()
    voice.enabled = voice.ready = True
    monkeypatch.setattr(voice,"_send",lambda *_a,**_k:None)
    monkeypatch.setattr(voice,"_start_playback",lambda:None)
    phases, captions = [], []
    voice.phase_changed.connect(phases.append);voice.caption_changed.connect(captions.append)
    try:
        voice.say("Here is the result.")
        assert phases == ["preparing"] and captions == ["Here is the result."]
        voice._receive({"type":"audio","epoch":voice.epoch,"rate":24000,"audio":base64.b64encode(b"\0\0"*100).decode()})
        assert phases[-1] == "speaking"
        voice.interrupt()
        assert phases[-1] == "idle"
    finally:
        voice.shutdown()


def test_voice_failure_stops_active_microphone_and_reports_error(qt):
    voice = VoiceController();voice.continuous = True
    stopped = []
    voice.duplex = SimpleNamespace(listening=True, active=True, stop=lambda:stopped.append(True), silence=lambda _:None)
    voice._receive({"type":"error","epoch":voice.epoch,"message":"Microphone failed"})
    assert stopped and not voice.continuous and voice._visual_phase == "error"
    voice.duplex = None;voice.shutdown()


def test_provider_error_remains_visible_after_worker_finishes(qt,tmp_path):
    app = build_application(JarvisSettings(workspace_dir=tmp_path));page = ChatPage(app,"Help")
    try:
        page._handle_reply(AssistantReply("failed","Provider HTTP 400","Provider HTTP 400","Provider rejected the payload"))
        page._handle_response("Provider HTTP 400")
        assert page.presence.phase == "error" and page.activity_state.text() == "Needs attention"
        assert "400" in page.presence.caption
        assert not page.presence.microphone and not page.presence.screen
    finally:
        page.close();app.shutdown()


def test_hidden_or_reduced_motion_orb_stops_its_timer(qt):
    state = AssistantPresence();orb = AssistantOrb(state)
    orb.show();qt.processEvents()
    assert orb.timer.isActive()
    state.update_state(motion=False)
    assert not orb.timer.isActive()
    state.update_state(motion=True)
    assert orb.timer.isActive()
    orb.hide();qt.processEvents()
    assert not orb.timer.isActive()
    orb.close()


def test_native_orb_changes_frames_and_static_mode_stays_still(qt):
    from PySide6.QtTest import QTest
    state = AssistantPresence();orb = AssistantOrb(state)
    orb.show();qt.processEvents()
    try:
        first = orb.grab().toImage()
        QTest.qWait(120)
        assert first != orb.grab().toImage()
        state.update_state(motion=False)
        first = orb.grab().toImage();QTest.qWait(70)
        assert first == orb.grab().toImage()
    finally:
        orb.close()


def test_cancelled_voice_start_cannot_activate_mic_after_load(qt,tmp_path,monkeypatch):
    app = build_application(JarvisSettings(workspace_dir=tmp_path));page = ChatPage(app,"Help")
    voice = page.voice_panel.controller;started = []
    page.voice_panel.enabled.blockSignals(True)
    monkeypatch.setattr(voice,"toggle_listening",lambda:started.append(True))
    try:
        page._companion_voice_toggle()
        assert page._companion_mic_pending and not page.presence.microphone
        page._companion_voice_toggle()
        page._companion_voice_ready(True)
        assert not started and not page._companion_mic_pending
    finally:
        page.close();app.shutdown()


def test_companion_can_be_recalled_and_all_animation_stops_on_close(qt,tmp_path):
    app = build_application(JarvisSettings(workspace_dir=tmp_path));page = ChatPage(app,"Help")
    try:
        page.desktop_button.setChecked(True)
        companion = page.companion
        assert companion is not None and companion.isVisible()
        recalled = []
        page.open_main_requested.connect(lambda:recalled.append(True))
        companion.set_expanded(True);companion.open_button.click()
        assert recalled == [True]
        page.desktop_button.setChecked(False)
        assert not companion.isVisible() and not companion.bubble.timer.isActive()
    finally:
        page.close();app.shutdown()
