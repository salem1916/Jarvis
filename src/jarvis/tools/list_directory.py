from collections.abc import Mapping
from pathlib import Path
from typing import ClassVar

from jarvis.security.capabilities import Capability
from jarvis.security.filesystem_scope import FilesystemScopePolicy
from jarvis.tools.base import Tool


class ListDirectoryTool(Tool):
    """
    List files and folders inside an approved filesystem scope.

    This tool is useful when the model does not yet know the
    filename it needs.

    FilesystemScopePolicy remains the authority over which
    locations may be inspected.
    """

    name = "list_directory"

    description = (
        "List files and folders inside a directory that JARVIS "
        "is allowed to access. Use this to discover available "
        "files when you do not know the filename before using "
        "read_file."
    )

    required_capability = Capability.READ_FILE

    parameters_schema: ClassVar[dict[str, object]] = {
        "type": "object",
        "properties": {
            "path": {
                "type": "string",
                "description": (
                    "Directory to list. "
                    "Use '.' for the JARVIS workspace. "
                    "Absolute paths must be inside an approved "
                    "filesystem scope."
                ),
                "default": ".",
            },
        },
        "additionalProperties": False,
    }

    def __init__(
        self,
        workspace_root: Path,
        scope_policy: FilesystemScopePolicy | None = None,
    ) -> None:
        self.workspace_root = workspace_root.expanduser().resolve()

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
        Return sorted names from one approved directory.
        """

        path = arguments.get(
            "path",
            ".",
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
            raise NotADirectoryError(
                resolved_path
            )

        if not resolved_path.is_dir():
            raise NotADirectoryError(
                resolved_path
            )

        return sorted(
            child.name
            for child in resolved_path.iterdir()
        )