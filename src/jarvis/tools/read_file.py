from collections.abc import Mapping
from pathlib import Path
from typing import ClassVar

from jarvis.security.capabilities import Capability
from jarvis.security.filesystem_scope import FilesystemScopePolicy
from jarvis.tools.base import Tool


class ReadFileTool(Tool):
    """
    Read a UTF-8 text file from an approved filesystem scope.

    The model never receives unrestricted filesystem access.

    Every requested path first passes through
    FilesystemScopePolicy.
    """

    name = "read_file"

    description = (
        "Read the contents of a text file from a filesystem "
        "location that JARVIS is allowed to access. "
        "Use this when you know the filename. "
        "If you do not know which files exist, use "
        "list_directory first."
    )

    required_capability = Capability.READ_FILE

    parameters_schema: ClassVar[dict[str, object]] = {
        "type": "object",
        "properties": {
            "path": {
                "type": "string",
                "description": (
                    "Path of the text file to read. "
                    "Relative paths refer to the JARVIS workspace. "
                    "Absolute paths must be inside an approved "
                    "filesystem scope."
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
        workspace_root: Path,
        scope_policy: FilesystemScopePolicy | None = None,
    ) -> None:
        self.workspace_root = workspace_root.expanduser().resolve()

        # Existing tests/tools can still construct ReadFileTool
        # with only a workspace root.
        #
        # In the real application bootstrap passes one shared
        # scope policy to all filesystem tools.
        self.scope_policy = (
            scope_policy
            if scope_policy is not None
            else FilesystemScopePolicy(
                self.workspace_root
            )
        )

    def execute(
        self,
        arguments: Mapping[str, object],
    ) -> object:
        """
        Read one approved text file.
        """

        path = arguments.get(
            "path"
        )

        if not isinstance(
            path,
            str,
        ):
            raise TypeError(
                "'path' must be a string."
            )

        resolved_path = self.scope_policy.resolve_path(
            path
        )

        if not resolved_path.exists():
            raise FileNotFoundError(
                resolved_path
            )

        if not resolved_path.is_file():
            raise FileNotFoundError(
                resolved_path
            )

        return resolved_path.read_text(
            encoding="utf-8"
        )