from collections.abc import Mapping
from pathlib import Path
from typing import ClassVar

from jarvis.security.capabilities import Capability
from jarvis.tools.base import Tool


class ListDirectoryTool(Tool):
    name = "list_directory"
    description = "List files and folders inside an allowed directory."
    required_capability = Capability.READ_FILE

    parameters_schema: ClassVar[dict[str, object]] = {
        "type": "object",
        "properties": {
            "path": {
                "type": "string",
                "description": (
                    "Directory path relative to the allowed workspace. "
                    "Use '.' for the workspace root."
                ),
            },
        },
        "additionalProperties": False,
    }

    def __init__(self, allowed_root: Path) -> None:
        self.allowed_root = allowed_root.resolve()

    def execute(
        self,
        arguments: Mapping[str, object],
    ) -> object:
        requested_path = arguments.get("path", ".")

        if not isinstance(requested_path, str):
            raise TypeError("'path' must be a string.")

        target = (self.allowed_root / requested_path).resolve()

        if not target.is_relative_to(self.allowed_root):
            raise ValueError("Path is outside the allowed directory.")

        if not target.is_dir():
            raise NotADirectoryError(str(target))

        return sorted(item.name for item in target.iterdir())