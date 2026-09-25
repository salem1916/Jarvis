from pathlib import Path

import pytest

from jarvis.core.tool_request import ToolRequest
from jarvis.security.capabilities import Capability
from jarvis.security.policy import PermissionPolicy
from jarvis.tools.executor import PermissionDeniedError, ToolExecutor
from jarvis.tools.read_file import ReadFileTool
from jarvis.tools.registry import ToolRegistry
from jarvis.tools.service import ToolService


def test_tool_service_executes_registered_allowed_tool(tmp_path: Path):
    allowed_root = tmp_path / "allowed"
    allowed_root.mkdir()

    file_path = allowed_root / "hello.txt"
    file_path.write_text("Hello from JARVIS", encoding="utf-8")

    registry = ToolRegistry()
    registry.register(ReadFileTool(allowed_root))

    policy = PermissionPolicy(
        allowed={Capability.READ_FILE},
    )

    executor = ToolExecutor(policy)
    service = ToolService(registry, executor)

    request = ToolRequest(
        tool_name="read_file",
        arguments={"path": "hello.txt"},
    )

    result = service.execute(request)

    assert result == "Hello from JARVIS"


def test_tool_service_blocks_denied_tool(tmp_path: Path):
    allowed_root = tmp_path / "allowed"
    allowed_root.mkdir()

    file_path = allowed_root / "hello.txt"
    file_path.write_text("secret", encoding="utf-8")

    registry = ToolRegistry()
    registry.register(ReadFileTool(allowed_root))

    policy = PermissionPolicy()

    executor = ToolExecutor(policy)
    service = ToolService(registry, executor)

    request = ToolRequest(
        tool_name="read_file",
        arguments={"path": "hello.txt"},
    )

    with pytest.raises(PermissionDeniedError):
        service.execute(request)


def test_tool_service_rejects_unknown_tool():
    registry = ToolRegistry()
    policy = PermissionPolicy()

    executor = ToolExecutor(policy)
    service = ToolService(registry, executor)

    request = ToolRequest(
        tool_name="does_not_exist",
    )

    with pytest.raises(KeyError):
        service.execute(request)