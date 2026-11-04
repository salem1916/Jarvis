"""Opt-in live clipboard + first-link + speaker-safe voice redirection check.

Uses generated microphone audio, muted Chromium playback, an isolated browser
on public example/IANA pages. A held provider simulates an in-flight AI request;
the observed first-link/back operations themselves require no cloud calls.
"""
import os
import subprocess
import time
import wave
from pathlib import Path
from threading import Event

from PySide6.QtWidgets import QApplication

from jarvis.bootstrap import build_application
from jarvis.core.config import JarvisSettings
from jarvis.core.request_control import check_cancelled
from jarvis.models.base import ModelProvider
from jarvis.security.capabilities import Capability
from jarvis.security.policy import PermissionDecision
from jarvis.tools.browser_mcp import BrowserMCPTool
from jarvis.ui.pages.chat_page import ChatPage


def main():
    root = Path(__file__).resolve().parents[1]
    work = root / "workspace" / "voice-redirection-check"
    work.mkdir(parents=True, exist_ok=True)
    microphone = work / "generated-interruption.wav"
    os.environ["QTWEBENGINE_CHROMIUM_FLAGS"] = (
        "--use-fake-device-for-media-stream --autoplay-policy=no-user-gesture-required "
        f"--use-file-for-fake-audio-capture={microphone}")
    qt = QApplication.instance() or QApplication([])
    app = build_application(JarvisSettings(workspace_dir=work))
    page = ChatPage(app, "You are Jarvis. Complete the actual request with real observed results.")
    voice = page.voice_panel.controller
    browser = app.tool_service.registry.get("browser_mcp")
    assert isinstance(browser, BrowserMCPTool)
    class DelayedProvider(ModelProvider):
        name = "held-test-provider"
        model = "fixture"
        hold = False
        started = Event()
        def generate(self, request):
            if self.hold:
                self.hold = False
                self.started.set()
                while True:
                    check_cancelled()
                    time.sleep(0.01)
            raise AssertionError("An observed first-link/back operation unexpectedly requested an AI reply.")
    delayed = DelayedProvider()
    app.cloud_provider = delayed
    app.tool_service.executor.policy.set_decision(Capability.USE_BROWSER, PermissionDecision.ALLOW)

    def wait(predicate, limit=90):
        deadline = time.monotonic() + limit
        while time.monotonic() < deadline:
            qt.processEvents()
            if predicate():
                return
            time.sleep(0.005)
        raise AssertionError("Timed out: " + page.activity_message.text() + " / " + page.details_view.toPlainText()[-500:])

    try:
        initial = browser.execute({"action":"navigate", "url":"https://example.com/"})
        app.interaction.focus_url = initial["url"]
        app.screen_control_enabled = True
        result = app.interact("Open the first link")
        print("First link:", result.kind, result.message, flush=True)
        assert result.kind == "action" and "iana.org" in browser.last["url"], result.details
        assert not any(event.tool == "open_application" for event in result.events)
        page._handle_reply(result)
        page.copy_reply_button.click()
        copied = subprocess.run(["powershell.exe", "-NoProfile", "-Command",
            "[Console]::OutputEncoding=[System.Text.Encoding]::UTF8; Get-Clipboard -Raw"], capture_output=True, encoding="utf-8", check=False)
        assert copied.returncode == 0 and result.message in copied.stdout
        print("PASS: actual Copy reply button -> another Windows process clipboard read.", flush=True)

        app.screen_control_enabled = False  # This check uses the owned browser, not private screens.
        voice._start_playback = lambda:None
        voice.enable(True)
        wait(lambda:voice.ready)
        voice.say("No, wait. Go back.")
        wait(lambda:voice._synthesis_done and bool(voice._playback))
        with wave.open(str(microphone), "wb") as output:
            output.setnchannels(1)
            output.setsampwidth(2)
            output.setframerate(24000)
            output.writeframes(b"\0" * (24000 * 2 * 6) + bytes(voice._playback) + b"\0" * (24000 * 2 * 90))
        voice.interrupt()
        transcripts, interruptions = [], []
        audio_states = []
        voice.status.connect(lambda text:audio_states.append((round(time.monotonic(),2),text)))
        original_receive = voice._receive
        audio_epochs = set()
        def trace_audio(message):
            kind = message["type"]
            if kind in {"synthesis_start","speech_done","error"} or kind == "audio" and message.get("epoch") not in audio_epochs:
                print("Audio event:",kind,"epoch",message.get("epoch"),"current",voice.epoch,"time",round(time.monotonic(),2),flush=True)
                if kind == "audio":audio_epochs.add(message.get("epoch"))
            original_receive(message)
        voice._receive = trace_audio
        voice.transcript.connect(transcripts.append)
        voice.speech_started.connect(lambda:interruptions.append(bool(page.worker and page.worker.control.paused.is_set())))
        page.voice_panel.mode.setCurrentIndex(page.voice_panel.mode.findData("hands_free"))
        voice.toggle_listening()
        assert voice.duplex is not None and voice.duplex.page is not None
        voice.duplex.page.setAudioMuted(True)  # No physical speaker output.
        wait(lambda:voice.duplex is not None and voice.duplex.listening)
        assert voice.duplex.settings.get("echoCancellation") in {True,"all"}
        delayed.hold = True
        page.input_box.setText("browser: Read the current page and explain its purpose")
        page._send_message()
        # Supply one controlled far-end utterance below. Extra progress speech
        # would replace it, making the overlap timing depend on thread delivery.
        page._spoken_progress_at = time.monotonic()
        wait(delayed.started.is_set)
        voice.say("I'm reading the current page. You can tell me to stop or go somewhere else while I check this information.")
        wait(lambda:voice._duplex_playing or bool(interruptions), 10)
        assert voice._duplex_playing and voice.duplex.listening and not interruptions, str(audio_states[-12:])
        wait(lambda:bool(transcripts), 30)
        print("Spoken interruption recognized:", transcripts[-1], flush=True)
        assert "back" in transcripts[-1].casefold() and any(interruptions)
        wait(lambda:page.worker_thread is None and page._reply is not None and page._reply.kind == "action")
        final = page._reply
        assert final is not None
        assert "example.com" in browser.last["url"], final.details
        assert voice.continuous and voice.duplex.listening and voice.source is None
        print("Redirected reply:", final.message, flush=True)
        print("PASS: echo-cancelling microphone stayed on during TTS/work; speech paused the worker, "
              "cancelled the old turn, preserved browser context and navigated back.", flush=True)
    finally:
        voice.stop_session()
        page._stop_request()
        wait(lambda:page.worker_thread is None, 40)
        page.close()
        app.shutdown()
        qt.processEvents()


if __name__ == "__main__":
    main()
