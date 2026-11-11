"""Explicit microphone controls and cancellable local speech, owned by the GUI."""

import base64
import re
import time
from array import array
from collections import deque
from difflib import SequenceMatcher
from pathlib import Path

from PySide6.QtCore import (
    QByteArray,
    QObject,
    QProcess,
    QProcessEnvironment,
    QTimer,
    QUrl,
    Signal,
    Slot,
)
from PySide6.QtGui import QDesktopServices
from PySide6.QtMultimedia import (
    QAudioDevice,
    QAudioFormat,
    QAudioSink,
    QAudioSource,
    QMediaDevices,
    QtAudio,
)
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from jarvis.voice.protocol import (
    MAX_LINE,
    MAX_SECONDS,
    VOICES,
    decode,
    encode,
    spoken_text,
)


class VoiceController(QObject):
    status = Signal(str)
    ready_changed = Signal(bool)
    transcript = Signal(str)
    interrupted = Signal()
    speech_started = Signal()
    speech_rejected = Signal()
    phase_changed = Signal(str)
    caption_changed = Signal(str)
    privacy_changed = Signal()
    level_changed = Signal(float)
    audio_check_status = Signal(str)

    def __init__(self, parent: QObject | None = None, root: Path | None = None):
        super().__init__(parent)
        self.root = root or Path(__file__).resolve().parents[3]
        self.enabled = False
        self._visual_phase = "idle"
        self.ready = False
        self.epoch = 0
        self.capture_epoch = 0
        self.recognizing = False
        self.continuous = False
        self.duplex_enabled = False
        self.duplex = None
        self._duplex_playing = False
        self.chat_busy = False
        self.session_paused = False
        self._listen_after = 0.0
        self._recent_speech = deque(maxlen=3)
        self.process: QProcess | None = None
        self.source: QAudioSource | None = None
        self.sink: QAudioSink | None = None
        self.mic = None
        self.output = None
        self.input_device = QMediaDevices.defaultAudioInput()
        self.output_device = QMediaDevices.defaultAudioOutput()
        self.voice = "bm_george"
        self.speed = 1.0
        self._incoming = bytearray()
        self._recording = bytearray()
        self._playback = bytearray()
        self._synthesis_done = True
        self._queued_speech = ""
        self._last_error = ""
        self._format = QAudioFormat()
        self._watchdog = QTimer(self)
        self._watchdog.setSingleShot(True)
        self._watchdog.setInterval(90000)
        self._watchdog.timeout.connect(self._startup_timeout)
        self._limit = QTimer(self)
        self._limit.setSingleShot(True)
        self._limit.setInterval(MAX_SECONDS * 1000)
        self._limit.timeout.connect(self.finish_recording)
        self._pump_timer = QTimer(self)
        self._pump_timer.setInterval(20)
        self._pump_timer.timeout.connect(self._pump)
        self._resume_timer = QTimer(self)
        self._resume_timer.setInterval(150)
        self._resume_timer.timeout.connect(self._resume_listening)
        self._audio_check = ""
        self._audio_check_previous_duplex = False
        self._audio_check_timer = QTimer(self)
        self._audio_check_timer.setSingleShot(True)
        self._audio_check_timer.timeout.connect(self._audio_check_timed_out)

    @property
    def capture_active(self):
        return self.source is not None or bool(self.duplex is not None and getattr(self.duplex,"listening",False))

    @property
    def audio_check_active(self):
        return bool(self._audio_check)

    def _phase(self, phase):
        if self._visual_phase != phase:
            self._visual_phase = phase
            self.phase_changed.emit(phase)

    def _level(self, pcm):
        if len(pcm)>=2 and len(pcm)%2==0:
            values = array("h",pcm)[::8]
            self.level_changed.emit(min(1.0,(sum(value*value for value in values)/max(1,len(values)))**0.5/32768*10))

    def enable(self, enabled: bool) -> None:
        if not enabled:
            self.shutdown()
            return
        if self.process is not None:
            return
        runtime = self.root / ".voice-venv" / "Scripts" / "python.exe"
        if not runtime.is_file():
            self.status.emit("Voice needs setup: run scripts/setup_voice.ps1.")
            self.ready_changed.emit(False)
            return
        self.enabled = True
        self._incoming.clear()
        self._last_error = ""
        self.status.emit("Loading local voice models… The microphone is off.")
        process = QProcess(self)
        self.process = process
        # Speech has no need for the app's API keys or provider environment.
        environment = QProcessEnvironment()
        system = QProcessEnvironment.systemEnvironment()
        for name in ("PATH", "SystemRoot", "WINDIR", "TEMP", "TMP", "USERPROFILE", "APPDATA", "LOCALAPPDATA", "PROGRAMFILES", "PROGRAMFILES(X86)"):
            if system.contains(name):
                environment.insert(name, system.value(name))
        environment.insert("PYTHONPATH", str(self.root / "src"))
        environment.insert("PYTHONNOUSERSITE", "1")
        environment.insert("PYTHONIOENCODING", "utf-8")
        environment.insert("HF_HUB_OFFLINE", "1")
        process.setProcessEnvironment(environment)
        process.setWorkingDirectory(str(self.root))
        process.setProgram(str(runtime))
        process.setArguments(["-u", "-m", "jarvis.voice.worker"])
        process.readyReadStandardOutput.connect(self._read)
        # Always drain diagnostics so a full stderr pipe cannot stall inference.
        process.readyReadStandardError.connect(lambda: process.readAllStandardError())
        process.errorOccurred.connect(self._process_error)
        process.finished.connect(lambda code, state: self._exited(process))
        self._watchdog.start()
        process.start()

    def _send(self, kind: str, **values) -> None:
        if self.process is not None and self.process.state() == QProcess.ProcessState.Running:
            if kind in {"stop", "listen_start", "listen_audio", "transcribe"}:
                values["capture_epoch"] = self.capture_epoch
            self.process.write(QByteArray(encode({"type": kind, "epoch": self.epoch, **values})))

    def _read(self) -> None:
        if self.process is None:
            return
        self._incoming.extend(self.process.readAllStandardOutput().data())
        try:
            while b"\n" in self._incoming:
                line, _, rest = self._incoming.partition(b"\n")
                self._incoming = bytearray(rest)
                self._receive(decode(bytes(line)))
            if len(self._incoming) > MAX_LINE:
                raise ValueError("Voice returned too much data.")
        except (ValueError, TypeError, KeyError) as exc:
            self.shutdown()
            self.status.emit(f"Voice stopped: {exc}")

    def _receive(self, message: dict) -> None:
        kind = message["type"]
        if kind == "ready":
            self._watchdog.stop()
            self.ready = True
            self.ready_changed.emit(True)
            if self._audio_check == "loading":
                self._begin_audio_check()
            else:
                self.status.emit("Voice ready · microphone off. Choose your voice mode, then start talking.")
            return
        if "capture_epoch" in message:
            if message["capture_epoch"] != self.capture_epoch:
                return
        elif message.get("epoch", self.epoch) != self.epoch:
            return
        if kind == "error":
            self._last_error = str(message.get("message", "Voice failed."))
            if self._audio_check:
                self._finish_audio_check(self._last_error)
            else:
                self.stop_session()
            self.recognizing = False
            self._synthesis_done = True
            self._phase("error")
            self.status.emit(self._last_error)
        elif kind == "status":
            self.status.emit(str(message.get("message","")))
        elif kind == "synthesis_start":
            self._synthesis_done = False
        elif kind == "speech_detected":
            if self._audio_check:
                if self._audio_check == "playing":
                    self._audio_check = "interrupted"
                    self.silence()
                    self.audio_check_status.emit("Playback stopped. Checking what you said…")
                self._phase("hearing")
                return
            if self.continuous and self.duplex_enabled:
                self.silence()
                self.speech_started.emit()
            self._phase("hearing")
            self.caption_changed.emit("Listening…")
            self.status.emit("Listening… pause briefly to send your message.")
        elif kind == "utterance":
            self.recognizing = True
            self._stop_capture()
            self._phase("processing")
            self.status.emit("Transcribing locally…")
        elif kind == "transcript":
            self.recognizing = False
            self._phase("listening" if self.capture_active else "idle")
            text = str(message.get("text", "")).strip()
            if self._audio_check:
                self._check_test_transcript(text)
                return
            if self.continuous and self._is_playback_echo(text):
                self.status.emit("Waiting for your voice…")
                self.speech_rejected.emit()
                self._send("listen_start")
                return
            if text:
                self.status.emit("Heard: " + text)
                self.transcript.emit(text)
            else:
                self.status.emit("I didn't catch speech. Hold Talk and try again.")
                self.speech_rejected.emit()
            if self.continuous and self.duplex_enabled:
                self._send("listen_start")
        elif kind == "audio":
            if message.get("rate") != 24000:
                raise ValueError("Unsupported speech output format.")
            pcm = base64.b64decode(message.get("audio", ""), validate=True)
            self._phase("speaking")
            if self.continuous and self.duplex_enabled and self.duplex is not None and self.duplex.listening:
                self._duplex_playing = True
                self.duplex.push(message.get("audio", ""), self.epoch)
                if self._audio_check == "preparing":
                    self._audio_check = "playing"
                    self.audio_check_status.emit('Say “blue balloon” now, while Jarvis is speaking.')
                return
            if len(pcm) % 2 or len(self._playback) + len(pcm) > 8_000_000:
                raise ValueError("Speech output exceeded its buffer limit.")
            self._playback.extend(pcm)
            if not self._pump_timer.isActive():
                self._start_playback()
        elif kind == "speech_done":
            self._synthesis_done = True
            if self._duplex_playing and self.duplex is not None:
                self.duplex.finish(self.epoch)
                return
            if not self._pump_timer.isActive():
                if self._continue_speech():
                    return
                self._phase("listening" if self.capture_active else "idle")
                self.status.emit("Listening paused after a problem. Press Listen to try again." if self.session_paused else "Voice ready · microphone off.")

    def interrupt(self, *, keep_listening=False) -> None:
        if self.sink is not None:
            self._listen_after = time.monotonic() + 0.65
        self.epoch += 1
        self._queued_speech = ""
        if not keep_listening:
            if self._audio_check:
                self._end_audio_check("Audio check stopped.")
            self.capture_epoch += 1
            self.recognizing = False
            self._stop_capture()
            if self.duplex is not None:
                self.duplex.stop()
        self._pump_timer.stop()
        self._playback.clear()
        self._synthesis_done = True
        self._duplex_playing = False
        if self.sink is not None:
            self.sink.stop()
            self.sink.deleteLater()
            self.sink = None
        self.output = None
        if self.duplex is not None:
            self.duplex.silence(self.epoch)
        self._send("interrupt_speech" if keep_listening else "stop")
        self._phase("listening" if self.capture_active else "idle")
        self.privacy_changed.emit()

    def silence(self):
        self.interrupt(keep_listening=bool(self.continuous and self.duplex_enabled and self.duplex is not None and self.duplex.active))

    def _start_duplex(self):
        if self.duplex is None:
            from jarvis.ui.duplex_audio import DuplexAudio
            self.duplex = DuplexAudio(self)
            self.duplex.audio.connect(self._duplex_pcm)
            self.duplex.listening_changed.connect(self._duplex_ready)
            self.duplex.error.connect(self._duplex_error)
            self.duplex.played.connect(self._duplex_played)
            self.duplex.output_level.connect(self._duplex_level)
        if not self.duplex.active:
            self.status.emit("Starting hands-free audio with speaker echo cancellation…")
            self.duplex.start(self.input_device.description(), self.output_device.description())

    def _duplex_pcm(self, encoded, rate):
        if self._visual_phase != "speaking":
            self._level(base64.b64decode(encoded))
        if self.continuous and not self.recognizing:
            self._send("listen_audio", audio=encoded, rate=rate, channels=1, format="s16")

    def _duplex_ready(self, ready):
        self.privacy_changed.emit()
        if ready and self.continuous:
            self._phase("listening")
            self._send("listen_start")
            if self._audio_check == "connecting":
                self._audio_check = "preparing"
                self.audio_check_status.emit("Wait for the sample to start.")
                self.say("This is Jarvis testing your audio. Speak over this sentence when the instructions say to. "
                         "I will keep talking for a few more seconds so you have time to try.")
            else:
                self.status.emit("Listening · echo cancellation on. Speak to interrupt Jarvis.")

    def _duplex_level(self, level, epoch):
        if epoch == self.epoch and self._duplex_playing:
            self.level_changed.emit(level)

    def _duplex_error(self, message):
        if self._audio_check:
            self._finish_audio_check("Hands-free audio: " + message)
        else:
            self.stop_session()
        self.status.emit("Hands-free audio: " + message)

    def _duplex_played(self, epoch):
        if epoch == self.epoch:
            self._duplex_playing = False
            if self._audio_check == "playing":
                self._finish_audio_check("The sample finished without an interruption. Check your microphone or try again.")
                return
            if self._continue_speech():
                return
            self._phase("listening" if self.capture_active else "idle")
            if self.continuous:
                self.status.emit("Listening · speak to interrupt or give another instruction.")

    def start_audio_check(self):
        if self._audio_check:
            return
        if (self.chat_busy or self.continuous or self.capture_active or self.recognizing
                or not self._synthesis_done or self._duplex_playing or self.sink is not None):
            self.audio_check_status.emit("Finish the current task or stop voice before running the audio check.")
            return
        self._audio_check_previous_duplex = self.duplex_enabled
        self._audio_check = "loading"
        self.audio_check_status.emit("Preparing your microphone and speaker test…")
        if self.ready:
            self._begin_audio_check()
        else:
            self.enable(True)
            if self.process is None:
                self._finish_audio_check("Voice setup is required before the audio check can start.")

    def _begin_audio_check(self):
        if self.input_device.isNull() or self.output_device.isNull():
            self._finish_audio_check("Select a microphone and speaker in Voice settings, then try again.")
            return
        self._audio_check = "connecting"
        self.duplex_enabled = self.continuous = True
        self._audio_check_timer.start(25_000)
        try:
            self._start_duplex()
        except (OSError, RuntimeError) as error:
            self._finish_audio_check(f"Could not start hands-free audio. {error}")

    def _check_test_transcript(self, text):
        if self._audio_check != "interrupted":
            if self._audio_check:
                self._send("listen_start")
            return
        if re.search(r"\bblue balloons?\b", text, re.IGNORECASE):
            self._finish_audio_check("Passed. Jarvis stopped speaking and heard the test phrase.")
        elif not re.search(r"\w", text):
            self._finish_audio_check("Playback stopped, but Jarvis couldn't hear the phrase clearly. Try speaking closer to the microphone.")
        elif self._is_playback_echo(text):
            self._finish_audio_check("Jarvis heard its own playback. Lower speaker volume or move the microphone farther from the speaker and retry.")
        else:
            self._finish_audio_check('Playback stopped, but Jarvis heard a different phrase. Try again and say “blue balloon”.')

    def _audio_check_timed_out(self):
        if self._audio_check:
            self._finish_audio_check("Audio check timed out. Check your selected devices and Windows microphone access.")

    def _end_audio_check(self, message):
        self._audio_check = ""
        self.continuous = False
        self.duplex_enabled = self._audio_check_previous_duplex
        self._audio_check_timer.stop()
        self.audio_check_status.emit(message)

    def _finish_audio_check(self, message):
        self._end_audio_check(message)
        self.stop_session()
        self.status.emit(message + " Microphone off.")

    def begin_recording(self) -> None:
        if self.continuous and self.duplex_enabled:
            self._start_duplex()
            return
        if not self.ready or self.source is not None:
            return
        self.session_paused = False
        if self.input_device.isNull():
            self.stop_session()
            self.status.emit("No microphone is available. Connect one, then refresh devices.")
            return
        self.interrupt()
        self.interrupted.emit()
        desired = QAudioFormat()
        desired.setSampleRate(16000)
        desired.setChannelCount(1)
        desired.setSampleFormat(QAudioFormat.SampleFormat.Int16)
        self._format = desired if self.input_device.isFormatSupported(desired) else self.input_device.preferredFormat()
        if self._format.channelCount() not in (1, 2) or self._format.sampleFormat() not in (
            QAudioFormat.SampleFormat.Int16, QAudioFormat.SampleFormat.Int32, QAudioFormat.SampleFormat.Float,
        ):
            self.status.emit("Select a microphone with mono or stereo PCM audio support.")
            self.stop_session()
            return
        self._recording.clear()
        source = QAudioSource(self.input_device, self._format, self)
        self.source = source
        source.stateChanged.connect(self._capture_state)
        self.mic = source.start()
        if self.source is None or self.mic is None or source.error() != QtAudio.Error.NoError:
            error = source.error().name
            self.stop_session()
            self.status.emit(f"Microphone could not start ({error}). Open Voice settings to check your device and Windows microphone access.")
            return
        self.mic.readyRead.connect(self._capture)
        self._phase("listening")
        self.privacy_changed.emit()
        if self.continuous:
            self._send("listen_start")
            self.status.emit("Listening hands-free… speak, then pause to send. Stop voice ends the session.")
        else:
            self._limit.start(MAX_SECONDS * 1000)
            self.status.emit("Listening… release Talk to send. Maximum 20 seconds.")

    @Slot()
    def _capture_state(self) -> None:
        # Qt 6.11 returns QtAudio enums; legacy QAudio enums have the same names
        # and values but compare unequal. NoError must never close a healthy mic.
        if self.source is not None and self.source.error() != QtAudio.Error.NoError:
            error = self.source.error().name
            self.stop_session()
            self.status.emit(f"Microphone interrupted ({error}). Check your device in Voice settings.")

    def _capture(self) -> None:
        if self.mic is None:
            return
        data = self.mic.readAll().data()
        if self._format.sampleFormat() == QAudioFormat.SampleFormat.Int16:
            self._level(data)
        if self.continuous:
            if data:
                self._send("listen_audio", **self._audio_message(data))
            return
        size = self._format.bytesPerFrame()
        limit = min(MAX_SECONDS * size * self._format.sampleRate(), (MAX_LINE - 2048) // 4 * 3)
        limit = limit // size * size
        self._recording.extend(data[:max(0, limit - len(self._recording))])
        if len(self._recording) >= limit:
            self._limit.start(1)

    def finish_recording(self) -> None:
        if self.source is None:
            return
        self._capture()
        if self.source is None:
            return
        data = bytes(self._recording)
        fmt = self._format
        self._stop_capture()
        if len(data) < fmt.bytesPerFrame() * fmt.sampleRate() // 5:
            self.status.emit("Hold Talk while speaking, then release to send.")
            return
        size = fmt.bytesPerFrame()
        data = data[:len(data) // size * size]
        self.recognizing = True
        self.status.emit("Transcribing locally…")
        self._send("transcribe", audio=base64.b64encode(data).decode("ascii"), rate=fmt.sampleRate(),
                   channels=fmt.channelCount(), format={QAudioFormat.SampleFormat.Int16: "s16",
                   QAudioFormat.SampleFormat.Int32: "s32", QAudioFormat.SampleFormat.Float: "f32"}[fmt.sampleFormat()])

    def _audio_message(self, data):
        return {"audio": base64.b64encode(data).decode("ascii"), "rate": self._format.sampleRate(),
                "channels": self._format.channelCount(), "format": {QAudioFormat.SampleFormat.Int16: "s16",
                QAudioFormat.SampleFormat.Int32: "s32", QAudioFormat.SampleFormat.Float: "f32"}[self._format.sampleFormat()]}

    def toggle_listening(self):
        if self.continuous:
            self.stop_session()
            self.status.emit("Stopped · microphone off.")
        elif self.ready:
            self.session_paused = False
            self.continuous = True
            self._resume_timer.start()
            self.begin_recording()

    def _resume_listening(self):
        if self.continuous and self.ready and self.duplex_enabled:
            self._start_duplex()
            return
        if self.continuous and self.ready and not self.chat_busy and not self.recognizing and self.source is None and self.sink is None and self._synthesis_done and time.monotonic() >= self._listen_after:
            self.begin_recording()

    def _is_playback_echo(self, text):
        normalized = " ".join(re.findall(r"\w+", text.casefold()))
        words = len(normalized.split())
        if words < 2:
            return False
        return any(time.monotonic() - when < 5 and (normalized == spoken or
                   (words >= 4 and (normalized in spoken or SequenceMatcher(None, normalized, spoken).ratio() > 0.93)))
                   for when, spoken in self._recent_speech)

    def pause_after_error(self):
        self.stop_session()
        self.session_paused = True
        self.status.emit("Listening paused after a problem. Press Listen to try again.")

    def stop_session(self):
        self.continuous = False
        self._resume_timer.stop()
        self.interrupt()

    def _stop_capture(self) -> None:
        self._limit.stop()
        source, self.source = self.source, None
        self.mic = None
        if source is not None:
            source.stop()
            source.deleteLater()
        self._recording.clear()
        self.privacy_changed.emit()

    def say(self, text: str) -> None:
        text = spoken_text(text)
        if not self.enabled or not self.ready or not text or self.source is not None:
            return
        if not self._synthesis_done or self.sink is not None or self._playback or self._duplex_playing:
            # The final result supersedes progress speech. Give it a fresh
            # generation so late progress audio/completion cannot replace it.
            self.silence()
        self._recent_speech.append((time.monotonic(), " ".join(re.findall(r"\w+", text.casefold()))))
        self._synthesis_done = False
        self.caption_changed.emit(text)
        self._phase("preparing")
        self.status.emit("Preparing spoken reply…")
        self._send("speak", text=text, voice=self.voice, speed=self.speed)

    def say_after_current(self, text: str) -> None:
        if not self._synthesis_done or self._duplex_playing or self.sink is not None:
            self._queued_speech = text
        else:
            self.say(text)

    def _continue_speech(self) -> bool:
        if not self._queued_speech:
            return False
        text, self._queued_speech = self._queued_speech, ""
        self.say(text)
        return True

    def _start_playback(self) -> None:
        if self.output_device.isNull():
            self.interrupt()
            self.status.emit("No speaker or headphones available. Select an output device.")
            return
        fmt = QAudioFormat()
        fmt.setSampleRate(24000)
        fmt.setChannelCount(1)
        fmt.setSampleFormat(QAudioFormat.SampleFormat.Int16)
        self.sink = QAudioSink(self.output_device, fmt, self)
        self.output = self.sink.start()
        if self.output is None or self.sink.error() != QtAudio.Error.NoError:
            error = self.sink.error().name
            self.interrupt()
            self.status.emit(f"Audio output could not start ({error}). Select your speaker or headphones in Voice settings.")
            return
        self.status.emit("Speaking · hold Talk or press Stop voice to interrupt.")
        self._phase("speaking")
        self._pump_timer.start()
        self._pump()

    def _pump(self) -> None:
        if self.sink is None or self.output is None:
            self._pump_timer.stop()
            return
        if self.sink.error() not in (QtAudio.Error.NoError, QtAudio.Error.UnderrunError):
            self.interrupt()
            self.status.emit("Audio output interrupted. Check your output device.")
            return
        count = min(len(self._playback), self.sink.bytesFree())
        if count > 0:
            written = self.output.write(QByteArray(bytes(self._playback[:count])))
            if written > 0:
                self._level(self._playback[:written])
                del self._playback[:written]
        if not self._playback and self._synthesis_done and self.sink.state() == QtAudio.State.IdleState:
            if self._continue_speech():
                return
            self.interrupt()
            self.status.emit("Listening paused after a problem. Press Listen to try again." if self.session_paused else "Voice ready · microphone off.")

    def _process_error(self, error) -> None:
        if error == QProcess.ProcessError.FailedToStart:
            self.shutdown()
            self.status.emit("Voice runtime could not start. Run scripts/setup_voice.ps1.")

    def _exited(self, process: QProcess) -> None:
        if self.process is process:
            self.process = None
            self.interrupt()
            self.ready = False
            self.enabled = False
            self._watchdog.stop()
            self.ready_changed.emit(False)
            self.status.emit(self._last_error or "Voice is off. Enable it again to retry.")
        process.deleteLater()

    def _startup_timeout(self) -> None:
        self.shutdown()
        self.status.emit("Voice took too long to start. Toggle voice off and on, or run setup again.")

    def shutdown(self) -> None:
        if self.duplex is not None:
            self.duplex.shutdown()
            self.duplex = None
        self.stop_session()
        self._watchdog.stop()
        self.enabled = False
        self.ready = False
        self.ready_changed.emit(False)
        process, self.process = self.process, None
        if process is not None:
            # The speech process owns no files or desktop actions. Killing it
            # also releases native model threads without blocking the GUI.
            process.kill()
            process.finished.connect(process.deleteLater)
        self.status.emit("Voice off · microphone off.")


class VoicePanel(QWidget):
    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self.controller = VoiceController(self)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        row = QHBoxLayout()
        self.enabled = QCheckBox("Voice replies")
        self.mode = QComboBox()
        self.mode.addItem("Click to talk", "click")
        self.mode.addItem("Hold to talk", "hold")
        self.mode.addItem("Hands-free · pause to send", "hands_free")
        self.barge_in = QCheckBox("Interrupt by speaking · speaker echo cancellation")
        self.barge_in.setChecked(True)
        self.controller.duplex_enabled = True
        self.barge_in.toggled.connect(self._duplex_changed)
        self.talk = QPushButton("Talk")
        self.talk.setEnabled(False)
        self.stop = QPushButton("Stop voice")
        self.options = QPushButton("Voice settings")
        for widget in (self.enabled, self.talk, self.stop, self.options):
            row.addWidget(widget)
        layout.addLayout(row)
        self.label = QLabel("Microphone off · English voice")
        self.label.setWordWrap(True)
        self.label.setObjectName("mutedText")
        layout.addWidget(self.label)
        self.settings = QDialog(self)
        self.settings.setWindowTitle("Jarvis · Voice settings")
        self.settings.setMinimumWidth(540)
        grid = QGridLayout(self.settings)
        grid.addWidget(QLabel("Voice mode"), 0, 0)
        grid.addWidget(self.mode, 0, 1)
        self.inputs, self.outputs, self.voices, self.speeds = (QComboBox() for _ in range(4))
        for combo in (self.inputs,self.outputs,self.voices,self.speeds,self.mode):
            combo.setSizeAdjustPolicy(QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon)
            combo.setMinimumContentsLength(14)
            combo.setMinimumWidth(0)
        for index, (title, combo) in enumerate((("Microphone", self.inputs), ("Speaker / headphones", self.outputs), ("Voice", self.voices), ("Speed", self.speeds)), start=1):
            grid.addWidget(QLabel(title), index, 0)
            grid.addWidget(combo, index, 1)
        for key, title in VOICES.items():
            self.voices.addItem(title, key)
        for value in (0.85, 1.0, 1.15, 1.3):
            self.speeds.addItem(f"{value:g}×", value)
        self.speeds.setCurrentIndex(1)
        refresh, preview = QPushButton("Refresh devices"), QPushButton("Test voice")
        grid.addWidget(refresh, 5, 0)
        grid.addWidget(preview, 5, 1)
        self.microphone_access = QPushButton("Windows microphone access")
        self.sound_settings = QPushButton("Windows sound settings")
        self.microphone_access.clicked.connect(lambda: QDesktopServices.openUrl(QUrl("ms-settings:privacy-microphone")))
        self.sound_settings.clicked.connect(lambda: QDesktopServices.openUrl(QUrl("ms-settings:sound")))
        grid.addWidget(self.microphone_access, 6, 0)
        grid.addWidget(self.sound_settings, 6, 1)
        help_text = QLabel("Windows microphone access: allow microphone access for desktop apps. Choose your devices above, then test voice. Jarvis action permissions are separate.")
        help_text.setWordWrap(True)
        help_text.setMinimumHeight(55)
        grid.addWidget(help_text, 7, 0, 1, 2)
        note = QLabel("Click mode: Talk, then Send. Hands-free: Listen, speak, then pause. Stop voice ends listening. Audio stays local; recognized text uses your selected model.")
        note.setWordWrap(True)
        note.setMinimumHeight(55)
        grid.addWidget(note, 8, 0, 1, 2)
        grid.addWidget(self.barge_in, 9, 0, 1, 2)
        note.setText("Hands-free: Listen once, then speak naturally. With interruption enabled, you can redirect Jarvis while it talks or works. Stop voice ends microphone access.")
        self.settings.hide()
        self.options.clicked.connect(lambda: self.settings.setVisible(not self.settings.isVisible()))
        self.enabled.toggled.connect(self.controller.enable)
        self.talk.pressed.connect(self._talk_pressed)
        self.talk.released.connect(self._talk_released)
        self.talk.clicked.connect(self._talk_clicked)
        self.mode.currentIndexChanged.connect(self._mode_changed)
        self.stop.clicked.connect(self.controller.stop_session)
        self.stop.clicked.connect(lambda: self.label.setText("Stopped · microphone off."))
        self.stop.clicked.connect(self._update_talk)
        self.controller.ready_changed.connect(self.talk.setEnabled)
        self.controller.ready_changed.connect(self._ready_changed)
        self.audio_check = QPushButton("Check microphone and speaker")
        self.audio_check.clicked.connect(self.controller.start_audio_check)
        grid.addWidget(self.audio_check, 10, 0, 1, 2)
        self.audio_check_result = QLabel('When the sample plays, say “blue balloon” to interrupt it.')
        self.audio_check_result.setWordWrap(True)
        grid.addWidget(self.audio_check_result, 11, 0, 1, 2)
        self.controller.audio_check_status.connect(self.audio_check_result.setText)
        self.controller.status.connect(self.label.setText)
        self.controller.status.connect(self._update_talk)
        self.voices.currentIndexChanged.connect(lambda: setattr(self.controller, "voice", self.voices.currentData()))
        self.speeds.currentIndexChanged.connect(lambda: setattr(self.controller, "speed", self.speeds.currentData()))
        self.inputs.currentIndexChanged.connect(self._select_input)
        self.outputs.currentIndexChanged.connect(self._select_output)
        refresh.clicked.connect(self.refresh_devices)
        preview.clicked.connect(self._preview)
        self.refresh_devices()

    def _mode_changed(self) -> None:
        self.controller.stop_session()
        self._update_talk()

    def _duplex_changed(self, enabled):
        self.controller.stop_session()
        self.controller.duplex_enabled = enabled
        self._update_talk()

    def _talk_pressed(self) -> None:
        if self.mode.currentData() == "hold":
            self.controller.begin_recording()

    def _talk_released(self) -> None:
        if self.mode.currentData() == "hold":
            self.controller.finish_recording()

    def _talk_clicked(self) -> None:
        if self.mode.currentData() == "hands_free":
            self.controller.toggle_listening()
        elif self.mode.currentData() == "click":
            if self.controller.source is None:
                self.controller.begin_recording()
                if self.controller.source is not None:
                    self.label.setText("Listening… click Send when finished. Maximum 20 seconds.")
            else:
                self.controller.finish_recording()
        self._update_talk()

    def _update_talk(self, *_args) -> None:
        self.talk.setText(("Stop" if self.controller.continuous else "Listen") if self.mode.currentData() == "hands_free" else "Hold" if self.mode.currentData() == "hold" else "Send" if self.controller.source is not None else "Talk")

    def _ready_changed(self, ready: bool) -> None:
        if ready or not self.controller.enabled:
            self.enabled.blockSignals(True)
            self.enabled.setChecked(ready)
            self.enabled.blockSignals(False)

    def refresh_devices(self) -> None:
        for combo, devices, default in ((self.inputs, QMediaDevices.audioInputs(), QMediaDevices.defaultAudioInput()),
                                        (self.outputs, QMediaDevices.audioOutputs(), QMediaDevices.defaultAudioOutput())):
            combo.blockSignals(True)
            selected = combo.currentData()
            selected_id = selected.id() if isinstance(selected, QAudioDevice) else default.id()
            combo.clear()
            for device in devices:
                combo.addItem(device.description(), device)
                if device.id() == selected_id:
                    combo.setCurrentIndex(combo.count() - 1)
            combo.blockSignals(False)
        self._select_input()
        self._select_output()

    def _select_input(self) -> None:
        device = self.inputs.currentData()
        if isinstance(device, QAudioDevice):
            self.controller.interrupt()
            self.controller.input_device = device

    def _select_output(self) -> None:
        device = self.outputs.currentData()
        if isinstance(device, QAudioDevice):
            self.controller.interrupt()
            self.controller.output_device = device

    def _preview(self) -> None:
        if self.controller.ready:
            self.controller.interrupt()
            self.controller.say("Hello Salem. I'm Jarvis. Click Talk to speak, and Send when you're done. Hands-free mode is also available in Voice settings.")
        else:
            self.label.setText("Enable Voice replies first, then wait for Voice ready.")
