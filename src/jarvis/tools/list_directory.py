from collections.abc import Mapping
from pathlib import Path
from typing import ClassVar

from jarvis.security.capabilities import Capability
from jarvis.tools.base import Tool


class ListDirectoryTool(Tool):
    """
    Tool for discovering which files and folders exist
    inside the authorized JARVIS workspace.
    """

    name = "list_directory"

    # This description is shown directly to the AI.
    #
    # It deliberately explains WHEN the tool should be used,
    # not only what the Python function technically does.
    description = (
        "List real files and folders inside the authorized "
        "JARVIS workspace. Use this when you need to discover "
        "which files exist, when the user does not know a filename, "
        "or before choosing a file to read."
    )

    required_capability = Capability.READ_FILE

    parameters_schema: ClassVar[dict[str, object]] = {
        "type": "object",
        "properties": {
            "path": {
                "type": "string",
                "description": (
                    "Directory relative to the authorized workspace. "
                    "Use '.' for the workspace root."
                ),
            },
        },
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
            "path",
            ".",
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
        # The requested directory must remain inside
        # the configured workspace.
        if not target.is_relative_to(
            self.allowed_root
        ):
            raise ValueError(
                "Path is outside the allowed directory."
            )

        if not target.is_dir():
            raise NotADirectoryError(
                str(target)
            )

        return sorted(
            item.name
            for item in target.iterdir()
        )