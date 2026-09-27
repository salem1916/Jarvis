from collections.abc import Mapping
from pathlib import Path
from typing import ClassVar

from send2trash import send2trash

from jarvis.security.capabilities import Capability
from jarvis.security.filesystem_scope import FilesystemScopePolicy
from jarvis.tools.base import Tool


class TrashFileTool(Tool):
    """
    Move one file to the operating system's Recycle Bin.

    This is intentionally safer than permanently deleting
    the file with Path.unlink().

    SECURITY MODEL

    The action requires BOTH:

        1. The file must be inside a JARVIS-approved
           filesystem scope.

        2. DELETE_FILE must be approved through the
           human confirmation system.

    The model itself cannot approve the operation.
    """

    name = "trash_file"

    description = (
        "Move a file to the operating system Recycle Bin. "
        "Use this when the user explicitly asks to delete, "
        "remove, or trash a file. The file must be inside an "
        "approved filesystem scope and the action requires "
        "human confirmation. This tool does not delete folders."
    )

    required_capability = Capability.DELETE_FILE

    parameters_schema: ClassVar[dict[str, object]] = {
        "type": "object",
        "properties": {
            "path": {
                "type": "string",
                "description": (
                    "Path of the file to move to the Recycle Bin. "
                    "Examples: 'notes.txt', "
                    "'Desktop\\\\notes.txt', or an absolute path "
                    "inside an approved filesystem scope."
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
        self.workspace_root = (
            workspace_root
            .expanduser()
            .resolve()
        )

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
        Move exactly one approved file to the Recycle Bin.
        """

        raw_path = arguments.get(
            "path"
        )

        if not isinstance(
            raw_path,
            str,
        ):
            raise TypeError(
                "'path' must be a string."
            )

        target = self.scope_policy.resolve_path(
            raw_path
        )

        if not target.exists():
            raise FileNotFoundError(
                target
            )

        # For our first deletion capability we deliberately
        # refuse folders.
        #
        # Recursive directory deletion will be treated as
        # a separate higher-risk operation later.
        if not target.is_file():
            raise IsADirectoryError(
                target
            )

        # send2trash delegates to the operating system's
        # Recycle Bin / Trash rather than permanently
        # unlinking the file.
        send2trash(
            str(
                target
            )
        )

        return {
            "ok": True,
            "action": "moved_to_recycle_bin",
            "path": str(
                target
            ),
        }