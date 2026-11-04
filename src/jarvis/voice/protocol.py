"""Bounded, versioned JSON messages shared by the desktop and speech process."""

import base64
import json
import re

PROTOCOL = 1
MAX_SECONDS = 20
MAX_LINE = 12_000_000
MAX_TEXT = 1200
VOICES = {"bm_george": "George · British", "bm_daniel": "Daniel · British", "af_heart": "Heart · American"}


def encode(message: dict) -> bytes:
    data = (json.dumps({"v": PROTOCOL, **message}, ensure_ascii=True) + "\n").encode("ascii")
    if len(data) > MAX_LINE:
        raise ValueError("Voice message is too large. Keep recordings under 20 seconds.")
    return data


def decode(data: bytes) -> dict:
    if len(data) > MAX_LINE:
        raise ValueError("Voice message is too large.")
    result = json.loads(data)
    if not isinstance(result, dict) or result.get("v") != PROTOCOL or not isinstance(result.get("type"), str):
        raise ValueError("Voice protocol mismatch. Restart Jarvis after updating.")
    return result


def unpack_audio(message: dict) -> bytes:
    rate, channels, fmt = message.get("rate"), message.get("channels"), message.get("format")
    if not isinstance(rate, int) or not 8000 <= rate <= 192000 or channels not in (1, 2):
        raise ValueError("Unsupported microphone format.")
    size = {"s16": 2, "s32": 4, "f32": 4}.get(str(fmt))
    if size is None:
        raise ValueError("Unsupported microphone sample type.")
    audio = base64.b64decode(message.get("audio", ""), validate=True)
    if len(audio) > MAX_SECONDS * rate * channels * size or len(audio) % (channels * size):
        raise ValueError("Recording exceeds the limit or contains incomplete samples.")
    return audio


def spoken_text(text: str) -> str:
    """Speak a short clean response; never read URLs, markup or source lists aloud."""
    text = re.split(r"\n\n(?:Sources read|Pages observed|Research notes):", text, maxsplit=1)[0]
    text = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", text)
    text = re.sub(r"https?://\S+", "the page", text)
    text = re.sub(r"[*#`]+|\[\d+\]", "", text)
    text = " ".join(text.split())
    if len(text) > MAX_TEXT:
        text = text[:MAX_TEXT].rsplit(" ", 1)[0].rstrip(",;:") + "."
    return text
