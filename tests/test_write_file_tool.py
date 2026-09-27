from pathlib import Path

import pytest

from jarvis.security.capabilities import Capability
from jarvis.security.filesystem_scope import FilesystemScopePolicy
from jarvis.tools.write_file import WriteFileTool


def test_write_file_creates_new_text_file(
    tmp_path: Path,
) -> None:
    """
    A new UTF-8 file should be created inside an approved
    filesystem scope.
    """

    workspace = tmp_path / "workspace"

    workspace.mkdir()

    policy = FilesystemScopePolicy(
        workspace
    )

    tool = WriteFileTool(
        workspace,
        scope_policy=policy,
    )

    result = tool.execute(
        {
            "path": "hello.txt",
            "content": "Hello from JARVIS",
        }
    )

    assert isinstance(
        result,
        dict,
    )

    created_file = workspace / "hello.txt"

    assert created_file.read_text(
        encoding="utf-8"
    ) == "Hello from JARVIS"

    assert result["action"] == "created"


def test_write_file_refuses_accidental_overwrite(
    tmp_path: Path,
) -> None:
    """
    Existing files must not be silently replaced.
    """

    workspace = tmp_path / "workspace"

    workspace.mkdir()

    existing = workspace / "important.txt"

    existing.write_text(
        "original",
        encoding="utf-8",
    )

    tool = WriteFileTool(
        workspace
    )

    with pytest.raises(
        FileExistsError,
        match="File already exists",
    ):
        tool.execute(
            {
                "path": "important.txt",
                "content": "replacement",
            }
        )

    assert existing.read_text(
        encoding="utf-8"
    ) == "original"


def test_write_file_can_explicitly_overwrite(
    tmp_path: Path,
) -> None:
    """
    Explicit overwrite=true allows replacement.

    Permission confirmation is enforced separately by
    ToolExecutor.
    """

    workspace = tmp_path / "workspace"

    workspace.mkdir()

    existing = workspace / "notes.txt"

    existing.write_text(
        "old",
        encoding="utf-8",
    )

    tool = WriteFileTool(
        workspace
    )

    result = tool.execute(
        {
            "path": "notes.txt",
            "content": "new",
            "overwrite": True,
        }
    )

    assert isinstance(
        result,
        dict,
    )

    assert existing.read_text(
        encoding="utf-8"
    ) == "new"

    assert result["action"] == "overwritten"


def test_write_file_rejects_path_outside_scope(
    tmp_path: Path,
) -> None:
    """
    WRITE_FILE capability does not imply access to arbitrary
    locations on the computer.
    """

    workspace = tmp_path / "workspace"
    outside = tmp_path / "outside"

    workspace.mkdir()
    outside.mkdir()

    tool = WriteFileTool(
        workspace
    )

    with pytest.raises(
        ValueError,
        match="outside the allowed filesystem scopes",
    ):
        tool.execute(
            {
                "path": str(
                    outside / "blocked.txt"
                ),
                "content": "must not be written",
            }
        )


def test_write_file_uses_write_capability(
    tmp_path: Path,
) -> None:
    """
    The tool must be protected by WRITE_FILE rather than
    READ_FILE.
    """

    workspace = tmp_path / "workspace"

    workspace.mkdir()

    tool = WriteFileTool(
        workspace
    )

    assert (
        tool.required_capability
        is Capability.WRITE_FILE
    )