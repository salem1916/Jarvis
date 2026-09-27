from collections.abc import Mapping
from typing import ClassVar

from jarvis.security.capabilities import Capability
from jarvis.security.filesystem_scope import FilesystemScopePolicy
from jarvis.tools.base import Tool


class ListFilesystemScopesTool(Tool):
    """
    Tell the AI which filesystem locations JARVIS is
    currently allowed to read.

    This does NOT grant any new permission.

    It only exposes the paths that the user has already
    approved through FilesystemScopePolicy.

    Example result:

        [
            {
                "path": "C:\\Users\\salem\\Jarvis\\workspace",
                "kind": "workspace",
            },
            {
                "path": "C:\\Users\\salem\\Desktop",
                "kind": "approved_folder",
            },
        ]

    This allows the model to resolve natural requests such as:

        "read learn.txt on my Desktop"

    without guessing that "Desktop" is inside the workspace.
    """

    name = "list_filesystem_scopes"

    description = (
        "List the filesystem folders that JARVIS currently has "
        "permission to read. Use this before read_file or "
        "list_directory when the user refers to a location such "
        "as Desktop, Documents, Downloads, a custom folder, or "
        "another approved location but the exact absolute path "
        "is not known. This tool does not grant new access."
    )

    required_capability = Capability.READ_FILE

    parameters_schema: ClassVar[dict[str, object]] = {
        "type": "object",
        "properties": {},
        "additionalProperties": False,
    }

    def __init__(
        self,
        scope_policy: FilesystemScopePolicy,
    ) -> None:
        self.scope_policy = scope_policy

    def execute(
        self,
        arguments: Mapping[str, object],
    ) -> object:
        """
        Return all currently approved read scopes.

        The first scope is always the permanent
        JARVIS workspace.
        """

        del arguments

        workspace = self.scope_policy.workspace_root

        return [
            {
                "path": str(root),
                "kind": (
                    "workspace"
                    if root == workspace
                    else "approved_folder"
                ),
            }
            for root in self.scope_policy.allowed_roots
        ]