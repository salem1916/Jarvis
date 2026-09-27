from pathlib import Path

import pytest

from jarvis.security.capabilities import Capability
from jarvis.tools import trash_file
from jarvis.tools.trash_file import TrashFileTool


def test_trash_file_uses_delete_capability(
    tmp_path: Path,
) -> None:
    """
    File deletion must use the dedicated DELETE_FILE
    capability.
    """

    workspace = tmp_path / "workspace"

    workspace.mkdir()

    tool = TrashFileTool(
        workspace
    )

    assert (
        tool.required_capability
        is Capability.DELETE_FILE
    )


def test_trash_file_sends_file_to_recycle_bin(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """
    The tool should call send2trash instead of permanently
    unlinking the file itself.
    """

    workspace = tmp_path / "workspace"

    workspace.mkdir()

    target = workspace / "remove-me.txt"

    target.write_text(
        "temporary",
        encoding="utf-8",
    )

    sent_paths: list[str] = []

    def fake_send2trash(
        path: str,
    ) -> None:
        sent_paths.append(
            path
        )

    monkeypatch.setattr(
        trash_file,
        "send2trash",
        fake_send2trash,
    )

    tool = TrashFileTool(
        workspace
    )

    result = tool.execute(
        {
            "path": "remove-me.txt",
        }
    )

    assert isinstance(
        result,
        dict,
    )

    assert sent_paths == [
        str(
            target.resolve()
        )
    ]

    assert result["action"] == "moved_to_recycle_bin"


def test_trash_file_rejects_outside_scope(
    tmp_path: Path,
) -> None:
    """
    DELETE_FILE does not permit arbitrary filesystem access.
    """

    workspace = tmp_path / "workspace"
    outside = tmp_path / "outside"

    workspace.mkdir()
    outside.mkdir()

    target = outside / "secret.txt"

    target.write_text(
        "do not touch",
        encoding="utf-8",
    )

    tool = TrashFileTool(
        workspace
    )

    with pytest.raises(
        ValueError,
        match="outside the allowed filesystem scopes",
    ):
        tool.execute(
            {
                "path": str(
                    target
                ),
            }
        )


def test_trash_file_refuses_directories(
    tmp_path: Path,
) -> None:
    """
    Directory deletion is intentionally not supported yet.
    """

    workspace = tmp_path / "workspace"

    workspace.mkdir()

    folder = workspace / "folder"

    folder.mkdir()

    tool = TrashFileTool(
        workspace
    )

    with pytest.raises(
        IsADirectoryError,
    ):
        tool.execute(
            {
                "path": "folder",
            }
        )