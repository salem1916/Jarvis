"""Bounded utterance detection around a Pipecat VAD analyzer."""
import contextlib


class SpeechEndpointer:
    def __init__(self, analyzer, turn_analyzer=None):
        self.analyzer = analyzer
        self.turn_analyzer = turn_analyzer
        self.pre_roll = bytearray()
        self.segment = bytearray()
        self.speaking = False
        self.quiet_samples = 0
        self.checked_at = 0
        self.turn_failed = False

    async def feed(self, pcm: bytes) -> tuple[bool, bytes | None]:
        state = await self.analyzer.analyze_audio(pcm)
        # Compare names so this coordinator needs no speech dependencies in the
        # desktop environment; the actual analyzer is Pipecat Silero.
        active = state.name in {"SPEAKING", "STOPPING"}
        speech = state.name in {"SPEAKING","STARTING"}
        if self.turn_analyzer is not None:
            self.turn_analyzer.append_audio(pcm,is_speech=speech)
        if speech:self.quiet_samples = self.checked_at = 0
        else:self.quiet_samples += len(pcm)//2
        started = active and not self.speaking
        if started:
            self.speaking = True
            self.segment.extend(self.pre_roll)
            self.pre_roll.clear()
        if self.speaking:
            self.segment.extend(pcm)
            ended = state.name == "QUIET"
            if ended and self.turn_analyzer is not None and self.quiet_samples<24000:
                if self.checked_at == 0 or self.quiet_samples-self.checked_at>=8000:
                    try:
                        turn,_metrics = await self.turn_analyzer.analyze_end_of_turn()
                        self.checked_at = self.quiet_samples
                        ended = turn.name == "COMPLETE"
                    except Exception:  # noqa: BLE001 -- optional inference failure must not stop the microphone
                        self.turn_failed = True
                        with contextlib.suppress(Exception):await self.turn_analyzer.cleanup()
                        self.turn_analyzer = None
                        ended = True
                else:ended = False
            if ended or len(self.segment) >= 20 * 32000:
                audio = bytes(self.segment[:20 * 32000])
                self.segment.clear()
                self.speaking = False
                if self.turn_analyzer is not None:self.turn_analyzer.clear()
                return started, audio
        else:
            self.pre_roll.extend(pcm)
            self.pre_roll = self.pre_roll[-12800:]
        return started, None

    async def close(self):
        self.segment.clear()
        self.pre_roll.clear()
        if self.turn_analyzer is not None:
            self.turn_analyzer.clear()
            await self.turn_analyzer.cleanup()
        await self.analyzer.cleanup()
