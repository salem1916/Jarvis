from collections.abc import Mapping
from pathlib import Path
from typing import ClassVar

from jarvis.security.capabilities import Capability
from jarvis.security.filesystem_scope import FilesystemScopePolicy
from jarvis.tools.base import Tool


class WriteFileTool(Tool):
    """
    Create or overwrite a UTF-8 text file.

    SECURITY MODEL

    A write requires BOTH:

        1. The target location must belong to an approved
           FilesystemScopePolicy root.

        2. WRITE_FILE capability must be approved through
           JARVIS's confirmation system.

    Adding Desktop/Documents/etc. as an approved filesystem
    scope does NOT by itself grant write permission.

    WRITE_FILE remains a separate capability requiring
    explicit human confirmation.
    """

    name = "write_file"

    description = (
        "Create or write a UTF-8 text file inside a filesystem "
        "location already approved by JARVIS. Use this when the "
        "user explicitly asks to create, save, or write a text "
        "file. This action requires human confirmation. "
        "Set overwrite=true only when the user wants an existing "
        "file replaced."
    )

    required_capability = Capability.WRITE_FILE

    parameters_schema: ClassVar[dict[str, object]] = {
        "type": "object",
        "properties": {
            "path": {
                "type": "string",
                "description": (
                    "Destination file path. "
                    "Examples: 'notes.txt', "
                    "'Desktop\\\\notes.txt', or an absolute path "
                    "inside an approved filesystem scope."
                ),
            },
            "content": {
                "type": "string",
                "description": (
                    "Exact UTF-8 text content to write."
                ),
            },
            "overwrite": {
                "type": "boolean",
                "description": (
                    "Whether an existing file may be replaced. "
                    "Defaults to false."
                ),
                "default": False,
            },
        },
        "required": [
            "path",
            "content",
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
        Write exactly one text file.
        """

        raw_path = arguments.get(
            "path"
        )

        content = arguments.get(
            "content"
        )

        overwrite = arguments.get(
            "overwrite",
            False,
        )

        if not isinstance(
            raw_path,
            str,
        ):
            raise TypeError(
                "'path' must be a string."
            )

        if not isinstance(
            content,
            str,
        ):
            raise TypeError(
                "'content' must be a string."
            )

        if not isinstance(
            overwrite,
            bool,
        ):
            raise TypeError(
                "'overwrite' must be a boolean."
            )

        # The scope policy handles:
        #
        # - workspace-relative paths
        # - Desktop/Documents aliases
        # - absolute approved paths
        # - path traversal protection
        # - approved-root enforcement
        target = self.scope_policy.resolve_path(
            raw_path
        )

        parent = target.parent

        if not parent.exists():
            raise FileNotFoundError(
                f"Parent directory does not exist: {parent}"
            )

        if not parent.is_dir():
            raise NotADirectoryError(
                parent
            )

        if target.exists() and target.is_dir():
            raise IsADirectoryError(
                target
            )

        # -------------------------------------------------
        # SAFE CREATE
        #
        # "x" means:
        #
        # create the file only if it does NOT already exist.
        #
        # This prevents accidental overwriting.
        # -------------------------------------------------

        if not overwrite:
            try:
                with target.open(
                    "x",
                    encoding="utf-8",
                ) as file:
                    file.write(
                        content
                    )

            except FileExistsError as exc:
                raise FileExistsError(
                    "File already exists. "
                    "Set overwrite=true only if replacing it "
                    "was explicitly requested."
                ) from exc

            action = "created"

        # -------------------------------------------------
        # EXPLICIT OVERWRITE
        #
        # The human confirmation system still has to approve
        # WRITE_FILE before ToolExecutor allows this code to run.
        # -------------------------------------------------

        else:
            # We must check BEFORE writing.
            #
            # After write_text(), the file obviously exists,
            # so checking target.exists() afterwards would
            # incorrectly always report "overwritten".
            existed_before = target.exists()

            target.write_text(
                content,
                encoding="utf-8",
            )

            action = (
                "overwritten"
                if existed_before
                else "created"
            )

        return {
            "ok": True,
            "action": action,
            "path": str(
                target
            ),
            "bytes_written": len(
                content.encode(
                    "utf-8"
                )
            ),
        }