"""Explicitly authorized real-device echo test. Audio exists only in memory."""
import argparse
import base64
import json
import math
import os
import time
from array import array
from difflib import SequenceMatcher

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication

from jarvis.ui.duplex_audio import DuplexAudio
from jarvis.ui.voice_panel import VoiceController


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--real-devices", action="store_true")
    if not parser.parse_args().real_devices:
        parser.error("This opens real audio devices. Obtain explicit approval, then pass --real-devices.")
    if "fake" in os.environ.get("QTWEBENGINE_CHROMIUM_FLAGS", "").casefold():
        raise RuntimeError("Fake-media flags are set; refusing to label this a real-device test.")
    qt = QApplication.instance() or QApplication([])
    voice = VoiceController()
    audio = DuplexAudio()
    errors, baseline, captured, transcripts, vad_events, played = [], bytearray(), bytearray(), [], [], []
    state = {"phase":"baseline", "rate":0, "capturing":False, "play_started":0.0}
    audio.error.connect(errors.append)
    audio.played.connect(played.append)
    def receive_pcm(encoded, rate):
        state["rate"] = rate
        target = baseline if state["phase"] == "baseline" else captured
        if len(target) < rate * 2 * 12:
            target.extend(base64.b64decode(encoded, validate=True))
        if state["capturing"]:
            voice._send("listen_audio",audio=encoded,rate=rate,channels=1,format="s16")
    audio.audio.connect(receive_pcm)
    def transcript(text):
        transcripts.append(text)
        if state["capturing"]:
            voice._send("listen_start")
    voice.transcript.connect(transcript)
    original_receive = voice._receive
    def observe_events(message):
        if message["type"] == "speech_detected":
            vad_events.append({"phase":state["phase"],"time":round(time.monotonic()-state["play_started"],2) if state["play_started"] else None})
        if message["type"] == "transcript" and message.get("epoch") == voice.epoch and state["phase"] == "analysis":
            # Silence is the expected successful echo result. VoiceController
            # intentionally emits no command signal for an empty transcript.
            transcripts.append(str(message.get("text", "")))
        original_receive(message)
    voice._receive = observe_events
    voice._start_playback = lambda:None  # Synthesize reference silently first.
    guard = QTimer()
    guard.setSingleShot(True)
    guard.timeout.connect(audio.stop)

    def wait(predicate, seconds: float = 20):
        end = time.monotonic() + seconds
        while time.monotonic() < end:
            qt.processEvents()
            if errors:
                raise RuntimeError(errors[-1])
            if predicate():
                return
            time.sleep(0.005)
        raise TimeoutError("Real-device check exceeded its bounded wait.")
    def duration(seconds):
        end = time.monotonic() + seconds
        wait(lambda:time.monotonic() >= end, seconds+2)
    def rms(pcm):
        samples = array("h", pcm)
        return math.sqrt(sum(sample*sample for sample in samples)/len(samples))/32768 if samples else 0
    try:
        print("Preparing local test speech; microphone off.",flush=True)
        voice.enable(True)
        wait(lambda:voice.ready, 90)
        sentence = "This is Jarvis. The speaker and microphone test is running now."
        voice.say(sentence)
        wait(lambda:voice._synthesis_done and bool(voice._playback))
        reference = bytes(voice._playback)
        voice.interrupt()
        voice._send("listen_start")
        state["capturing"] = True
        print("Starting approved physical audio capture (12-second maximum).",flush=True)
        audio.start(voice.input_device.description(), voice.output_device.description())
        wait(lambda:audio.listening, 15)
        guard.start(12000)
        assert audio.settings.get("echoCancellation") in {True,"all"}
        duration(0.8)
        state["phase"] = "playback"
        state["play_started"] = time.monotonic()
        print("Playing test sentence.",flush=True)
        for start in range(0,len(reference),9600):
            audio.push(base64.b64encode(reference[start:start+9600]).decode(), 1)
        audio.finish(1)
        wait(lambda:1 in played, min(10,len(reference)/48000+3))
        duration(1.0)
        audio.stop()
        state["capturing"] = False
        print("Microphone stopped; analyzing captured audio locally.",flush=True)
        guard.stop()
        duration(0.5)
        assert baseline and captured and state["rate"], "No physical microphone frames arrived."
        # VAD monitored the actual stream live, including quiet startup. ASR
        # checks the captured playback locally; no agent or tools are connected.
        voice.interrupt()
        transcripts.clear()
        state["phase"] = "analysis"
        voice._send("transcribe",audio=base64.b64encode(captured).decode(),rate=state["rate"],channels=1,format="s16")
        wait(lambda:bool(transcripts),30)
        normalized = " ".join(transcripts[-1].casefold().split())
        expected = " ".join(sentence.casefold().split())
        keywords = {"jarvis","speaker","microphone","test","running"}
        overlap = len(keywords.intersection(normalized.replace(".", "").replace(",", "").split()))
        echo_match = overlap >= 3 or SequenceMatcher(None,normalized,expected).ratio() > 0.5
        result = {"real_devices":True,"echo_cancellation":audio.settings.get("echoCancellation"),
            "playback_echo_reference":audio.settings.get("playbackEchoReference","direct"),
            "input_device":voice.input_device.description(),"output_device":voice.output_device.description(),
            "sample_rate":state["rate"],"baseline_seconds":round(len(baseline)/(state["rate"]*2),2),
            "captured_seconds":round(len(captured)/(state["rate"]*2),2),
            "baseline_rms":round(rms(baseline),6),"playback_rms":round(rms(captured),6),
            "speech_detector_triggered":any(event["phase"] == "playback" for event in vad_events),
            "startup_speech_detector_triggered":any(event["phase"] == "baseline" for event in vad_events),
            "speech_detection_times":[event["time"] for event in vad_events if event["phase"] == "playback"],
            "test_sentence_recognized_from_microphone":echo_match,
            "playback_finished":bool(played),"microphone_stopped":not audio.active,
            "audio_saved":False,"ambient_transcript_saved":False}
        print(json.dumps(result,indent=2),flush=True)
    finally:
        guard.stop()
        audio.shutdown()
        voice.shutdown()
        baseline.clear()
        captured.clear()
        transcripts.clear()
        for _ in range(30):
            qt.processEvents()
            time.sleep(0.01)


if __name__ == "__main__":
    main()
