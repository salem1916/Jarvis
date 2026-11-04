"""Local speech smoke test, no microphone or speaker access. Run with desktop Python.

Starts the actual Qt process bridge, synthesizes and recognizes a command,
tests stale-event cancellation, and exits. Downloads nothing and uses no API.
"""

import base64
import os
import sys
import time
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from PySide6.QtWidgets import QApplication

from jarvis.ui.voice_panel import VoiceController


def main() -> None:
    qt = QApplication.instance() or QApplication([])
    voice = VoiceController()
    events, transcripts = [], []
    voice.status.connect(events.append)
    voice.transcript.connect(transcripts.append)
    first_audio = []
    # Collect generated PCM without opening any physical output device.
    def collect():
        if not first_audio:
            first_audio.append(time.perf_counter())
    voice._start_playback = collect

    def wait(predicate, seconds=20):
        deadline = time.monotonic() + seconds
        while time.monotonic() < deadline:
            qt.processEvents()
            if predicate():
                return
            time.sleep(0.005)
        raise AssertionError("Voice test timed out: " + str(events[-4:]))

    try:
        started = time.perf_counter()
        voice.enable(True)
        wait(lambda: voice.ready, 90)
        print(f"Startup: {time.perf_counter() - started:.2f}s")
        assert voice.source is None and voice.sink is None, "Startup must not open microphone or speakers"
        for text in ("Hello.", "Open Google.", "Find a video about learning SQL."):
            voice.interrupt()
            first_audio.clear()
            started = time.perf_counter()
            voice.say(text)
            wait(lambda: voice._synthesis_done and bool(first_audio))
            print(f"First audio for {text!r}: {first_audio[0] - started:.2f}s")
            pcm = bytes(voice._playback)
            voice.interrupt()
            voice._send("transcribe", audio=base64.b64encode(pcm).decode(), rate=24000, channels=1, format="s16")
            count = len(transcripts)
            started = time.perf_counter()
            wait(lambda previous=count: len(transcripts) > previous)
            print(f"Recognized in {time.perf_counter() - started:.2f}s: {transcripts[-1]}")
            if text == "Open Google.":
                assert "open google" in transcripts[-1].casefold()
            if "SQL" in text:
                assert "video" in transcripts[-1].casefold() and "sql" in transcripts[-1].casefold()
        # The same bridge also accepts live audio chunks and ends a hands-free
        # utterance after a pause, without touching the physical microphone.
        voice.interrupt()
        voice._send("listen_start")
        count = len(transcripts)
        stream = b"\0" * 12000 + pcm + b"\0" * 48000
        for start in range(0, len(stream), 1536):
            voice._send("listen_audio", audio=base64.b64encode(stream[start:start + 1536]).decode(),
                        rate=24000, channels=1, format="s16")
            qt.processEvents()
        wait(lambda: len(transcripts) > count)
        assert "video" in transcripts[-1].casefold() and "sql" in transcripts[-1].casefold()
        print("PASS: hands-free pause detection through the actual Qt speech bridge.")
        # Interrupt a real generation, then request a new utterance before the
        # old native inference finishes. Only the replacement may be delivered.
        voice.interrupt()
        first_audio.clear()
        voice.say("This is the old reply. " * 30)
        qt.processEvents()
        voice.interrupt()
        voice.say("Ready.")
        wait(lambda: voice._synthesis_done and bool(voice._playback))
        assert voice.source is None and voice.sink is None
        assert not any("failed" in item.casefold() or "error" in item.casefold() for item in events)
        print("PASS: local speech, process bridge, recognition, replacement and microphone-off checks.")
    finally:
        process = voice.process
        voice.shutdown()
        if process is not None:
            process.waitForFinished(3000)
        qt.processEvents()


if __name__ == "__main__":
    main()
