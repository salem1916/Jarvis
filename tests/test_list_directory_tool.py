from pathlib import Path

import pytest

from jarvis.tools.list_directory import ListDirectoryTool


def test_list_directory_lists_files_and_folders(tmp_path: Path):
    allowed_root = tmp_path / "allowed"
    allowed_root.mkdir()

    (allowed_root / "hello.txt").write_text("hello", encoding="utf-8")
    (allowed_root / "notes.txt").write_text("notes", encoding="utf-8")
    (allowed_root / "projects").mkdir()

    tool = ListDirectoryTool(allowed_root)

    result = tool.execute({"path": "."})

    assert result == ["hello.txt", "notes.txt", "projects"]


def test_list_directory_lists_subdirectory(tmp_path: Path):
    allowed_root = tmp_path / "allowed"
    allowed_root.mkdir()

    documents = allowed_root / "documents"
    documents.mkdir()
    (documents / "report.txt").write_text("report", encoding="utf-8")

    tool = ListDirectoryTool(allowed_root)

    result = tool.execute({"path": "documents"})

    assert result == ["report.txt"]


def test_list_directory_rejects_path_outside_allowed_root(tmp_path: Path):
    allowed_root = tmp_path / "allowed"
    allowed_root.mkdir()

    outside = tmp_path / "outside"
    outside.mkdir()

    tool = ListDirectoryTool(allowed_root)

    with pytest.raises(ValueError):
        tool.execute({"path": "../outside"})


def test_list_directory_rejects_file_path(tmp_path: Path):
    allowed_root = tmp_path / "allowed"
    allowed_root.mkdir()

    file_path = allowed_root / "hello.txt"
    file_path.write_text("hello", encoding="utf-8")

    tool = ListDirectoryTool(allowed_root)

    with pytest.raises(NotADirectoryError):
        tool.execute({"path": "hello.txt"})