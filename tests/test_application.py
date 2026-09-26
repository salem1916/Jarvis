from pathlib import Path

import pytest

from jarvis.bootstrap import build_application
from jarvis.core.config import JarvisSettings
from jarvis.core.tool_request import ToolRequest
from jarvis.tools.executor import PermissionDeniedError


def test_application_reads_file_when_permission_is_enabled(
    tmp_path: Path,
):
    file_path = tmp_path / "hello.txt"
    file_path.write_text("Hello Salem", encoding="utf-8")

    settings = JarvisSettings(
        workspace_dir=tmp_path,
        allow_read_file=True,
    )

    app = build_application(settings)

    request = ToolRequest(
        tool_name="read_file",
        arguments={"path": "hello.txt"},
    )

    result = app.execute_tool(request)

    assert result == "Hello Salem"


def test_application_blocks_file_read_by_default(
    tmp_path: Path,
):
    file_path = tmp_path / "hello.txt"
    file_path.write_text("Secret", encoding="utf-8")

    settings = JarvisSettings(
        workspace_dir=tmp_path,
        allow_read_file=False,
    )

    app = build_application(settings)

    request = ToolRequest(
        tool_name="read_file",
        arguments={"path": "hello.txt"},
    )

    with pytest.raises(PermissionDeniedError):
        app.execute_tool(request)