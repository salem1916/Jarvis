from collections.abc import Mapping
from pathlib import Path
from typing import ClassVar

from jarvis.security.capabilities import Capability
from jarvis.tools.base import Tool


class ReadFileTool(Tool):
    """
    Tool for reading the real contents of a UTF-8 text
    file inside the authorized JARVIS workspace.
    """

    name = "read_file"

    # This description is shown to the AI.
    #
    # The model should use this after it knows which
    # specific file needs to be inspected.
    description = (
        "Read the real contents of a UTF-8 text file inside "
        "the authorized JARVIS workspace. Use this when the "
        "user asks what a known file contains. If the filename "
        "is not known yet, use list_directory first."
    )

    required_capability = Capability.READ_FILE

    parameters_schema: ClassVar[dict[str, object]] = {
        "type": "object",
        "properties": {
            "path": {
                "type": "string",
                "description": (
                    "Path to the file relative to the "
                    "authorized workspace."
                ),
            },
        },
        "required": [
            "path",
        ],
        "additionalProperties": False,
    }

    def __init__(
        self,
        allowed_root: Path,
    ) -> None:
        self.allowed_root = allowed_root.resolve()

    def execute(
        self,
        arguments: Mapping[str, object],
    ) -> object:
        requested_path = arguments.get(
            "path"
        )

        if not isinstance(
            requested_path,
            str,
        ):
            raise TypeError(
                "'path' must be a string."
            )

        target = (
            self.allowed_root
            / requested_path
        ).resolve()

        # Security boundary:
        #
        # "../" and similar path traversal attempts
        # cannot escape the authorized workspace.
        if not target.is_relative_to(
            self.allowed_root
        ):
            raise ValueError(
                "Path is outside the allowed directory."
            )

        return target.read_text(
            encoding="utf-8",
        )