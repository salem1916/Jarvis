"""Explicit installation step; runtime never downloads models or audio."""

import hashlib
from pathlib import Path
from urllib.request import urlopen

ROOT = Path(__file__).resolve().parents[1] / ".voice-models"
WHISPER_REVISION = "3d3d5dee26484f91867d81cb899cfcf72b96be6c"


def download(url: str, target: Path) -> None:
    if target.is_file() and target.stat().st_size > 0:
        return
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = target.with_suffix(target.suffix + ".part")
    print(f"Downloading {target.name}…", flush=True)
    with urlopen(url, timeout=60) as response, temporary.open("wb") as output:
        while chunk := response.read(1024 * 1024):
            output.write(chunk)
    temporary.replace(target)


def main() -> None:
    for name in ("kokoro-v1.0.int8.onnx", "voices-v1.0.bin"):
        download("https://github.com/thewh1teagle/kokoro-onnx/releases/download/model-files-v1.0/" + name, ROOT / name)
    for name in ("config.json", "model.bin", "tokenizer.json", "vocabulary.txt"):
        download(f"https://huggingface.co/Systran/faster-whisper-base.en/resolve/{WHISPER_REVISION}/{name}", ROOT / "whisper-base.en" / name)
    for file in sorted(ROOT.rglob("*")):
        if file.is_file() and ".cache" not in file.parts:
            with file.open("rb") as stream:
                print(file.relative_to(ROOT), hashlib.file_digest(stream, "sha256").hexdigest())


if __name__ == "__main__":
    main()
