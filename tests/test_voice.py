"""Speech boundaries, cancellation, privacy and reuse of the real conversation flow."""

import asyncio
import base64
import os
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtCore import QByteArray
from PySide6.QtWidgets import QApplication

from jarvis.bootstrap import build_application
from jarvis.core.config import JarvisSettings
from jarvis.core.interaction import AssistantReply
from jarvis.security.capabilities import Capability
from jarvis.security.policy import PermissionDecision
from jarvis.ui.pages.chat_page import ChatPage
from jarvis.ui.voice_panel import VoiceController, VoicePanel
from jarvis.voice.protocol import (
    MAX_LINE,
    MAX_SECONDS,
    decode,
    encode,
    spoken_text,
    unpack_audio,
)
from jarvis.voice.worker import SpeechRuntime


@pytest.fixture
def qt():
    return QApplication.instance() or QApplication([])


def test_protocol_bounds_and_version():
    assert decode(encode({"type": "stop", "epoch": 2}))["epoch"] == 2
    for data in (b"[]", b'{"v":2,"type":"stop"}', b"x" * (MAX_LINE + 1)):
        with pytest.raises(ValueError):
            decode(data)


def test_audio_limits_alignment_and_type():
    message = {"rate": 16000, "channels": 1, "format": "s16", "audio": "AAA="}
    assert unpack_audio(message) == b"\0\0"
    for update in ({"rate": 0}, {"channels": 3}, {"format": "code"}, {"audio": "!invalid!"}, {"audio": "AA=="},
                   {"audio": base64.b64encode(b"\0" * (MAX_SECONDS * 32000 + 2)).decode()}):
        with pytest.raises(ValueError):
            unpack_audio({**message, **update})


def test_spoken_text_omits_sources_and_markup():
    assert spoken_text("**Opened** [Python](https://python.org). [1]\n\nSources read: private details") == "Opened Python."
    assert len(spoken_text("word " * 2000)) <= 1201


def test_voice_is_off_and_does_not_open_devices_on_start(qt):
    panel = VoicePanel()
    assert not panel.enabled.isChecked()
    assert not panel.controller.enabled and not panel.controller.ready
    assert panel.controller.process is None and panel.controller.source is None and panel.controller.sink is None
    assert not panel.talk.isEnabled()
    panel.controller.shutdown()
    panel.close()


def test_interrupt_drops_stale_transcripts_and_audio(qt, monkeypatch):
    voice = VoiceController()
    transcripts, played, messages = [], [], []
    voice.transcript.connect(transcripts.append)
    voice.status.connect(messages.append)
    monkeypatch.setattr(voice, "_start_playback", lambda: played.append(True))
    previous = voice.epoch
    voice._playback.extend(b"\0\0")
    voice.interrupt()
    voice._receive({"type": "transcript", "epoch": previous, "text": "open google"})
    voice._receive({"type": "audio", "epoch": previous, "rate": 24000, "audio": "AAA="})
    voice._receive({"type": "error", "epoch": previous, "message": "old error"})
    assert not transcripts and not played and not voice._playback and not messages
    voice._receive({"type": "transcript", "epoch": voice.epoch, "text": "Open Google."})
    assert transcripts == ["Open Google."]
    voice._receive({"type": "transcript", "epoch": voice.epoch, "text": ""})
    assert len(transcripts) == 1
    voice.shutdown()


def test_release_bounds_recording_and_never_writes_audio(qt, monkeypatch):
    voice = VoiceController()
    voice.ready = voice.enabled = True
    from PySide6.QtMultimedia import QAudioFormat
    voice._format.setSampleRate(16000)
    voice._format.setChannelCount(1)
    voice._format.setSampleFormat(QAudioFormat.SampleFormat.Int16)
    class Source:
        def stop(self): pass
        def deleteLater(self): pass
    class Mic:
        def readAll(self): return QByteArray(b"\0" * (MAX_SECONDS * 32000 + 2000))
    monkeypatch.setattr(voice, "source", Source())
    monkeypatch.setattr(voice, "mic", Mic())
    sent = []
    monkeypatch.setattr(voice, "_send", lambda kind, **kw: sent.append((kind, kw)))
    voice.finish_recording()
    assert voice.source is None and not voice._recording and not voice._limit.isActive()
    assert len(unpack_audio(sent[0][1])) == MAX_SECONDS * 32000
    voice.finish_recording()
    assert len(sent) == 1
    voice.shutdown()


def test_latest_replacement_waits_without_overlapping_native_inference():
    async def exercise():
        runtime = SpeechRuntime(Path("unused"))
        entered, release = asyncio.Event(), asyncio.Event()
        calls = []
        async def speak(message):
            calls.append(message["epoch"])
            if message["epoch"] == 0:
                entered.set()
                await release.wait()
        runtime.speak = speak
        runtime.submit("speak", {"epoch": 0})
        await entered.wait()
        runtime.epoch = 1
        runtime.submit("speak", {"epoch": 1})
        runtime.epoch = 2
        runtime.submit("speak", {"epoch": 2})
        assert calls == [0] and len(runtime.pending) == 1
        release.set()
        for _ in range(5):
            await asyncio.sleep(0)
        assert calls == [0, 2]
        await runtime.close()
    asyncio.run(exercise())


def test_voice_prompt_uses_existing_router_and_preserves_draft(qt, tmp_path, monkeypatch):
    from test_assistant_interruption import spin
    app = build_application(JarvisSettings(workspace_dir=tmp_path))
    app.tool_service.executor.policy.set_decision(Capability.USE_BROWSER, PermissionDecision.ALLOW)
    opened = []
    monkeypatch.setattr(app.tool_service.registry.get("open_url"), "_opener", lambda url: opened.append(url) or True)
    page = ChatPage(app, "Be helpful")
    spoken = []
    monkeypatch.setattr(page.voice_panel.controller, "say", spoken.append)
    try:
        page.input_box.setText("My unsent draft")
        page._voice_prompt("Open Google.")
        spin(qt, lambda: page.worker_thread is None)
        assert opened == ["https://www.google.com/"]
        assert spoken == ["Opened Google."]
        assert page.input_box.text() == "My unsent draft"
        assert "Open Google." in page.chat_view.toPlainText()
    finally:
        page._stop_request()
        spin(qt, lambda: page.worker_thread is None)
        page.voice_panel.controller.shutdown()
        page.close()
        app.shutdown()


def test_cancelled_reply_is_never_spoken(qt, tmp_path, monkeypatch):
    app = build_application(JarvisSettings(workspace_dir=tmp_path))
    page = ChatPage(app, "Be helpful")
    spoken = []
    monkeypatch.setattr(page.voice_panel.controller, "say", spoken.append)
    page._handle_reply(AssistantReply("cancelled", "Stopped", "Stopped", "Stopped"))
    assert not spoken
    page.voice_panel.controller.shutdown()
    page.close()
    app.shutdown()


def test_stop_voice_silences_current_reply_without_cancelling_chat(qt, tmp_path, monkeypatch):
    app = build_application(JarvisSettings(workspace_dir=tmp_path))
    page = ChatPage(app, "Be helpful")
    spoken = []
    monkeypatch.setattr(page.voice_panel.controller, "say", spoken.append)
    page.voice_panel.stop.click()
    page._handle_reply(AssistantReply("answer", "Here is your answer.", "Here is your answer.", ""))
    assert not spoken
    assert page.activity_message.text() == "Here is your answer."
    page.voice_panel.controller.shutdown()
    page.close()
    app.shutdown()


def test_spoken_yes_cannot_approve_a_pending_action(qt, tmp_path, monkeypatch):
    from test_assistant_interruption import spin
    app = build_application(JarvisSettings(workspace_dir=tmp_path))
    app.tool_service.executor.policy.set_decision(Capability.USE_BROWSER, PermissionDecision.REQUIRE_CONFIRMATION)
    opened = []
    monkeypatch.setattr(app.tool_service.registry.get("open_url"), "_opener", lambda url: opened.append(url) or True)
    page = ChatPage(app, "Be helpful")
    try:
        page._voice_prompt("Open Google.")
        spin(qt, lambda: page._approval_token is not None)
        # A voice transcript is conversational input, never a trusted approval.
        page._voice_prompt("yes")
        page._stop_request()
        spin(qt, lambda: page.worker_thread is None)
        assert not opened
    finally:
        page._stop_request()
        spin(qt, lambda: page.worker_thread is None)
        page.voice_panel.controller.shutdown()
        page.close()
        app.shutdown()


def test_audio_playback_handles_partial_writes_and_waits_for_drain(qt, monkeypatch):
    from PySide6.QtMultimedia import QtAudio
    voice = VoiceController()
    writes = []
    class Sink:
        current_state = QtAudio.State.ActiveState
        stopped = False
        def error(self): return QtAudio.Error.NoError
        def bytesFree(self): return 4
        def state(self): return self.current_state
        def stop(self): self.stopped = True
        def deleteLater(self): pass
    class Output:
        def write(self, data):
            writes.append(data.data()[:2])
            return 2
    sink = Sink()
    monkeypatch.setattr(voice, "sink", sink)
    monkeypatch.setattr(voice, "output", Output())
    voice._playback.extend(b"123456")
    voice._synthesis_done = True
    for _ in range(3):
        voice._pump()
    assert b"".join(writes) == b"123456" and not voice._playback
    assert not sink.stopped
    sink.current_state = QtAudio.State.IdleState
    voice._pump()
    assert sink.stopped and voice.sink is None and voice.output is None
    voice.shutdown()


def test_real_qt_no_error_does_not_close_microphone(qt, monkeypatch):
    from PySide6.QtMultimedia import QAudioFormat, QAudioSource
    voice = VoiceController()
    fmt = QAudioFormat()
    fmt.setSampleRate(16000)
    fmt.setChannelCount(1)
    fmt.setSampleFormat(QAudioFormat.SampleFormat.Int16)
    # Constructing a source does not open or record from the microphone.
    source = QAudioSource(voice.input_device, fmt)
    monkeypatch.setattr(voice, "source", source)
    messages = []
    voice.status.connect(messages.append)
    voice._capture_state()
    assert voice.source is source and not messages
    voice.shutdown()


def test_real_qt_no_error_does_not_stop_playback(qt, monkeypatch):
    from PySide6.QtMultimedia import QAudioFormat, QAudioSink
    voice = VoiceController()
    fmt = QAudioFormat()
    fmt.setSampleRate(24000)
    fmt.setChannelCount(1)
    fmt.setSampleFormat(QAudioFormat.SampleFormat.Int16)
    # This sink remains unopened. Its real QtAudio error enum exposes the old
    # QAudio-vs-QtAudio mismatch without using speakers during unit tests.
    sink = QAudioSink(voice.output_device, fmt)
    monkeypatch.setattr(voice, "sink", sink)
    monkeypatch.setattr(voice, "output", object())
    voice._synthesis_done = False
    messages = []
    voice.status.connect(messages.append)
    voice._pump()
    assert voice.sink is sink and not messages
    voice.shutdown()


def test_voice_settings_open_windows_controls(qt, monkeypatch):
    from PySide6.QtGui import QDesktopServices
    opened = []
    monkeypatch.setattr(QDesktopServices, "openUrl", lambda url: opened.append(url.toString()) or True)
    panel = VoicePanel()
    panel.microphone_access.click()
    panel.sound_settings.click()
    assert opened == ["ms-settings:privacy-microphone", "ms-settings:sound"]
    assert panel.controller.source is None
    panel.controller.shutdown()
    panel.close()
