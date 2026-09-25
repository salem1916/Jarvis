from pathlib import Path

import pytest
from jarvis.tools.read_file import ReadFileTool

from jarvis.security.capabilities import Capability
from jarvis.security.policy import PermissionPolicy
from jarvis.tools.executor import ToolExecutor


def test_read_file_reads_allowed_file(tmp_path: Path):
    allowed_root = tmp_path / "allowed"
    allowed_root.mkdir()

    file_path = allowed_root / "hello.txt"
    file_path.write_text("Hello JARVIS", encoding="utf-8")

    tool = ReadFileTool(allowed_root)

    result = tool.execute({"path": "hello.txt"})

    assert result == "Hello JARVIS"


def test_read_file_rejects_path_outside_allowed_root(tmp_path: Path):
    allowed_root = tmp_path / "allowed"
    allowed_root.mkdir()

    secret_file = tmp_path / "secret.txt"
    secret_file.write_text("secret", encoding="utf-8")

    tool = ReadFileTool(allowed_root)

    with pytest.raises(ValueError):
        tool.execute({"path": "../secret.txt"})


def test_read_file_works_through_permission_executor(tmp_path: Path):
    allowed_root = tmp_path / "allowed"
    allowed_root.mkdir()

    file_path = allowed_root / "hello.txt"
    file_path.write_text("Permission granted", encoding="utf-8")

    policy = PermissionPolicy(
        allowed={Capability.READ_FILE},
    )

    executor = ToolExecutor(policy)
    tool = ReadFileTool(allowed_root)

    result = executor.execute(
        tool,
        {"path": "hello.txt"},
    )

    assert result == "Permission granted"