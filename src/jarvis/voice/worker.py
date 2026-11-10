"""Local Pipecat speech services over stdin/stdout. No credentials or PC tools.

Run by the desktop with the separate Python 3.13 voice environment. Microphone
capture, playback, model calls and action approvals remain in the desktop.
"""

# Optional speech packages are checked separately with the Python 3.13 runtime.
# pyright: reportMissingImports=false

import asyncio
import base64
import contextlib
import os
import sys
import tempfile
from pathlib import Path

from jarvis.voice.endpointer import SpeechEndpointer
from jarvis.voice.protocol import (
    MAX_LINE,
    VOICES,
    decode,
    encode,
    spoken_text,
    unpack_audio,
)


def emit(kind: str, **values) -> None:
    sys.stdout.buffer.write(encode({"type": kind, **values}))
    sys.stdout.buffer.flush()


class SpeechRuntime:
    def __init__(self, root: Path):
        self.root = root
        self.epoch = 0
        self.capture_epoch = 0
        self.tts_job: asyncio.Task | None = None
        self.stt_job: asyncio.Task | None = None
        self.pending: dict[str, dict] = {}
        self.endpoint = None
        self.accepting_audio = False
        self.turn_analyzer = None
        self.smart_turn_unavailable = False
        # A cancelled coroutine can leave native inference running. Locks live
        # inside the jobs, and jobs finish naturally before the next inference.
        self.tts_lock = asyncio.Lock()
        self.stt_lock = asyncio.Lock()

    def submit(self, kind: str, message: dict) -> None:
        name = "tts_job" if kind == "speak" else "stt_job"
        job = getattr(self, name)
        if job is not None and not job.done():
            self.pending[kind] = message
            return
        operation = self.speak if kind == "speak" else self.transcribe
        job = asyncio.create_task(operation(message))
        setattr(self, name, job)
        job.add_done_callback(lambda completed: self._completed(kind))

    def _completed(self, kind: str) -> None:
        message = self.pending.pop(kind, None)
        current = self.epoch if kind == "speak" else self.capture_epoch
        generation = "epoch" if kind == "speak" else "capture_epoch"
        if message is not None and message.get(generation) == current:
            self.submit(kind, message)

    async def load(self) -> None:
        temporary = self.root / ".voice-models" / "runtime-tmp"
        temporary.mkdir(parents=True, exist_ok=True)
        tempfile.tempdir = str(temporary)
        # These imports must never enter the main Python 3.14 desktop runtime.
        import numpy as np
        from loguru import logger

        logger.remove()
        logger.add(sys.stderr, level="WARNING")
        from pipecat.clocks.system_clock import SystemClock
        from pipecat.frames.frames import TTSAudioRawFrame
        from pipecat.pipeline.pipeline import Pipeline
        from pipecat.pipeline.worker import PipelineWorker
        from pipecat.processors.frame_processor import FrameProcessorSetup
        from pipecat.services.kokoro.tts import KokoroTTSService
        from pipecat.services.whisper.stt import WhisperSTTService
        from pipecat.transcriptions.language import Language
        from pipecat.utils.asyncio.task_manager import TaskManager

        self.np = np
        files = self.root / ".voice-models"
        required = [files / "kokoro-v1.0.int8.onnx", files / "voices-v1.0.bin"]
        required.extend(files / "whisper-base.en" / name for name in ("model.bin", "config.json", "tokenizer.json", "vocabulary.txt"))
        if any(not file.is_file() for file in required):
            raise RuntimeError("Voice models are missing. Run scripts/setup_voice.ps1, then enable voice again.")
        self.tts = KokoroTTSService(
            model_path=str(required[0]), voices_path=str(required[1]), sample_rate=24000,
            settings=KokoroTTSService.Settings(voice="bm_george", language=Language.EN_GB, speed=1.0),
        )
        self.stt = WhisperSTTService(
            settings=WhisperSTTService.Settings(model=str(files / "whisper-base.en"), language=Language.EN,
                                                no_speech_prob=0.3),
            device="cpu", compute_type="int8",
        )
        # Public Pipecat service setup, shared clock and lifecycle. The desktop
        # supplies explicit utterance boundaries for this push-to-talk stage.
        self.pipeline = PipelineWorker(Pipeline([self.stt, self.tts]), enable_rtvi=False, idle_timeout_secs=None)
        self.manager = TaskManager()
        setup = FrameProcessorSetup(clock=SystemClock(), task_manager=self.manager, pipeline_worker=self.pipeline)
        await self.tts.setup(setup)
        await self.stt.setup(setup)
        # Prepare the phonemizer and first Kokoro inference before the user
        # speaks. The warm-up audio is discarded inside the local worker.
        with contextlib.suppress(Exception):
            await self.tts._update_settings(KokoroTTSService.Settings(language=Language.EN_GB))
            async with contextlib.aclosing(self.tts.run_tts("Ready.", "warmup")) as frames:
                async for frame in frames:
                    if isinstance(frame, TTSAudioRawFrame):
                        break
        emit("ready", voices=list(VOICES))

    async def speak(self, message: dict) -> None:
        from pipecat.frames.frames import ErrorFrame, TTSAudioRawFrame
        from pipecat.services.kokoro.tts import KokoroTTSService
        from pipecat.transcriptions.language import Language

        epoch = message["epoch"]
        try:
            async with self.tts_lock:
                if epoch != self.epoch:
                    return
                emit("synthesis_start", epoch=epoch)
                voice = message.get("voice", "bm_george")
                speed = float(message.get("speed", 1.0))
                if voice not in VOICES or not 0.7 <= speed <= 1.4:
                    raise ValueError("Unsupported voice or speaking speed.")
                await self.tts._update_settings(KokoroTTSService.Settings(
                    voice=voice, language=Language.EN_US if voice.startswith("a") else Language.EN_GB, speed=speed,
                ))
                async for frame in self.tts.run_tts(spoken_text(str(message.get("text", ""))), str(epoch)):
                    if epoch != self.epoch:
                        break
                    if isinstance(frame, ErrorFrame):
                        raise RuntimeError(frame.error)  # noqa: TRY004
                    if isinstance(frame, TTSAudioRawFrame):
                        # Small messages keep Stop responsive, even for long audio.
                        for start in range(0, len(frame.audio), 9600):
                            if epoch != self.epoch:
                                break
                            emit("audio", epoch=epoch, rate=24000,
                                 audio=base64.b64encode(frame.audio[start:start + 9600]).decode("ascii"))
                            await asyncio.sleep(0)
        except Exception as exc:  # noqa: BLE001 - isolate optional speech failures from the desktop
            if epoch == self.epoch:
                emit("error", epoch=epoch, message=f"Speech output: {exc}")
        finally:
            if epoch == self.epoch:
                emit("speech_done", epoch=epoch)

    def normalize_audio(self, message: dict) -> bytes:
        import soxr
        pcm = unpack_audio(message)
        dtype, scale = {"s16": ("<i2", 32768.0), "s32": ("<i4", 2147483648.0), "f32": ("<f4", 1.0)}[message["format"]]
        audio = self.np.frombuffer(pcm, dtype=dtype).astype(self.np.float32) / scale
        audio = audio.reshape(-1, message["channels"]).mean(axis=1)
        audio = self.np.nan_to_num(audio)
        if message["rate"] != 16000:
            audio = soxr.resample(audio, message["rate"], 16000)
        return (self.np.clip(audio, -1, 0.9999) * 32768).astype("<i2").tobytes()

    async def start_listening(self):
        from pipecat.audio.vad.silero import SileroVADAnalyzer
        from pipecat.audio.vad.vad_analyzer import VADParams
        if self.endpoint is not None:
            self.accepting_audio = True
            return
        if self.turn_analyzer is None and not self.smart_turn_unavailable:
            try:
                from pipecat.audio.turn.smart_turn.local_smart_turn_v3 import (
                    LocalSmartTurnAnalyzerV3,
                )
                self.turn_analyzer = LocalSmartTurnAnalyzerV3(sample_rate=16000,cpu_count=2)
                self.turn_analyzer.set_sample_rate(16000)
            except Exception:  # noqa: BLE001 -- keep voice usable if the optional local model fails
                self.smart_turn_unavailable = True
                emit("status",message="Natural turn detection is unavailable; using pause detection.")
        analyzer = SileroVADAnalyzer(sample_rate=16000, params=VADParams(start_secs=0.12, stop_secs=0.48, min_volume=0.4))
        analyzer.set_sample_rate(16000)
        self.endpoint = SpeechEndpointer(analyzer,self.turn_analyzer)
        self.accepting_audio = True

    async def stop_listening(self):
        self.accepting_audio = False
        if self.endpoint is not None:
            await self.endpoint.close()
            self.endpoint = None
            self.turn_analyzer = None

    async def listen_audio(self, message):
        if self.endpoint is None or not self.accepting_audio:
            return
        pcm = self.normalize_audio(message)
        started, segment = await self.endpoint.feed(pcm)
        if self.endpoint.turn_failed:
            self.turn_analyzer = None;self.smart_turn_unavailable = True
            emit("status",message="Natural turn detection stopped; continuing with pause detection.")
        if started:
            emit("speech_detected", capture_epoch=self.capture_epoch)
        if segment is not None:
            # Retain the warmed VAD and end-of-turn model for the next
            # utterance. Ignore mic packets while transcription is in flight.
            self.accepting_audio = False
            emit("utterance", capture_epoch=self.capture_epoch)
            self.submit("transcribe", {"capture_epoch": self.capture_epoch, "audio": base64.b64encode(segment).decode("ascii"),
                                       "rate": 16000, "channels": 1, "format": "s16"})

    async def transcribe(self, message: dict) -> None:
        from pipecat.frames.frames import ErrorFrame, TranscriptionFrame

        capture_epoch = message["capture_epoch"]
        try:
            async with self.stt_lock:
                if capture_epoch != self.capture_epoch:
                    return
                pcm = self.normalize_audio(message)
                audio = self.np.frombuffer(pcm, dtype="<i2").astype(self.np.float32) / 32768
                # Measure sustained energy over 20 ms frames. A single click
                # should not make an otherwise silent recording a voice turn.
                frame_samples = 320
                frames = audio[:len(audio) // frame_samples * frame_samples].reshape(-1, frame_samples)
                active_frames = self.np.count_nonzero(self.np.mean(frames ** 2, axis=1) >= 0.003 ** 2)
                if len(audio) < 3200 or active_frames < 6:
                    emit("transcript", capture_epoch=capture_epoch, text="")
                    return
                audio = (self.np.clip(audio, -1, 0.9999) * 32768).astype("<i2").tobytes()
                text = []
                async for frame in self.stt.run_stt(audio):
                    if isinstance(frame, ErrorFrame):
                        raise RuntimeError(frame.error)  # noqa: TRY004
                    if isinstance(frame, TranscriptionFrame):
                        text.append(frame.text.strip())
                if capture_epoch == self.capture_epoch:
                    emit("transcript", capture_epoch=capture_epoch, text=" ".join(text))
        except Exception as exc:  # noqa: BLE001 - isolate optional speech failures from the desktop
            if capture_epoch == self.capture_epoch:
                emit("error", capture_epoch=capture_epoch, message=f"Speech recognition: {exc}")

    async def close(self) -> None:
        self.epoch += 1
        self.capture_epoch += 1
        await self.stop_listening()
        jobs = [job for job in (self.tts_job, self.stt_job) if job is not None]
        for job in jobs:
            job.cancel()
        await asyncio.gather(*jobs, return_exceptions=True)
        if hasattr(self, "tts"):
            await self.tts.cleanup()
        if hasattr(self, "stt"):
            await self.stt.cleanup()


async def main() -> None:
    runtime = SpeechRuntime(Path(__file__).resolve().parents[3])
    try:
        await runtime.load()
        while True:
            line = await asyncio.to_thread(sys.stdin.buffer.readline, MAX_LINE + 1)
            if not line:
                break
            capture_command = False
            try:
                message = decode(line)
                kind = message["type"]
                if kind == "shutdown":
                    break
                capture_command = kind in {"listen_start", "listen_audio", "transcribe"}
                if capture_command or kind == "stop":
                    generation = message.get("capture_epoch")
                    if not isinstance(generation, int) or generation < runtime.capture_epoch:
                        continue
                    runtime.capture_epoch = generation
                if not capture_command:
                    epoch = message.get("epoch")
                    if not isinstance(epoch, int) or epoch < runtime.epoch:
                        continue
                    runtime.epoch = epoch
                if kind in {"speak", "transcribe"}:
                    # One active inference plus the latest replacement. Old
                    # native inference finishes safely; its events are dropped.
                    runtime.submit(kind, message)
                elif kind == "stop":
                    runtime.pending.clear()
                    await runtime.stop_listening()
                elif kind == "interrupt_speech":
                    # Epoch invalidates old TTS; preserve the active VAD segment
                    # and microphone so the user's interrupting words survive.
                    runtime.pending.pop("speak", None)
                elif kind == "listen_start":
                    await runtime.start_listening()
                elif kind == "listen_audio":
                    await runtime.listen_audio(message)
                elif kind != "stop":
                    raise ValueError("Unknown voice command.")
            except (ValueError, TypeError, KeyError) as exc:
                emit("error", **({"capture_epoch": runtime.capture_epoch} if capture_command else {"epoch": runtime.epoch}),
                     message=str(exc))
    except Exception as exc:  # noqa: BLE001 - report startup failures over IPC
        emit("error", message=f"Voice could not start: {exc}")
    finally:
        with contextlib.suppress(Exception):
            await runtime.close()


if __name__ == "__main__":
    # Local model paths only. Runtime never fetches models or sends audio away.
    os.environ["HF_HUB_OFFLINE"] = "1"
    os.environ["HF_HUB_DISABLE_TELEMETRY"] = "1"
    asyncio.run(main())
