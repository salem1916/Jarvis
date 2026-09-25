from collections.abc import Mapping
from pathlib import Path

from jarvis.security.capabilities import Capability
from jarvis.tools.base import Tool


class ReadFileTool(Tool):
    name = "read_file"
    description = "Read a UTF-8 text file from an allowed directory."
    required_capability = Capability.READ_FILE

    def __init__(self, allowed_root: Path) -> None:
        self.allowed_root = allowed_root.resolve()

    def execute(self, arguments: Mapping[str, object]) -> object:
        requested_path = arguments.get("path")

        if not isinstance(requested_path, str):
            raise ValueError("'path' must be a string.")

        target = (self.allowed_root / requested_path).resolve()

        if not target.is_relative_to(self.allowed_root):
            raise ValueError("Path is outside the allowed directory.")

        return target.read_text(encoding="utf-8")