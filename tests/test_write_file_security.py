from pathlib import Path

import pytest

from jarvis.bootstrap import build_application
from jarvis.core.config import JarvisSettings
from jarvis.core.tool_request import ToolRequest
from jarvis.tools.executor import ConfirmationRequiredError


def test_write_file_requires_confirmation_before_execution(
    tmp_path: Path,
) -> None:
    """
    Full JARVIS integration test.

    WRITE_FILE must not execute before confirmation.

    After trusted confirmed=True, the exact request may run.
    """

    workspace = tmp_path / "workspace"

    workspace.mkdir()

    settings = JarvisSettings(
        workspace_dir=workspace,
        allow_read_file=True,
        persist_filesystem_scopes=False,
    )

    app = build_application(
        settings
    )

    request = ToolRequest(
        tool_name="write_file",
        arguments={
            "path": "created.txt",
            "content": "Confirmed by human",
        },
    )

    target = workspace / "created.txt"

    # First attempt must STOP.
    with pytest.raises(
        ConfirmationRequiredError,
    ):
        app.execute_tool(
            request
        )

    assert not target.exists()

    # Trusted confirmation permits this exact execution.
    app.execute_tool(
        request,
        confirmed=True,
    )

    assert target.read_text(
        encoding="utf-8"
    ) == "Confirmed by human"