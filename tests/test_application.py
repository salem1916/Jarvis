from pathlib import Path

import pytest

from jarvis.bootstrap import build_application
from jarvis.core.config import JarvisSettings
from jarvis.core.tool_request import ToolRequest
from jarvis.runtime.profile import ModelRole
from jarvis.tools.executor import PermissionDeniedError


def test_application_reads_file_when_permission_is_enabled(
    tmp_path: Path,
) -> None:
    file_path = tmp_path / "hello.txt"
    file_path.write_text(
        "Hello Salem",
        encoding="utf-8",
    )

    settings = JarvisSettings(
        workspace_dir=tmp_path,
        allow_read_file=True,
    )

    app = build_application(
        settings
    )

    request = ToolRequest(
        tool_name="read_file",
        arguments={
            "path": "hello.txt",
        },
    )

    result = app.execute_tool(
        request
    )

    assert result == "Hello Salem"


def test_application_blocks_file_read_by_default(
    tmp_path: Path,
) -> None:
    file_path = tmp_path / "hello.txt"
    file_path.write_text(
        "Secret",
        encoding="utf-8",
    )

    settings = JarvisSettings(
        workspace_dir=tmp_path,
        allow_read_file=False,
    )

    app = build_application(
        settings
    )

    request = ToolRequest(
        tool_name="read_file",
        arguments={
            "path": "hello.txt",
        },
    )

    with pytest.raises(
        PermissionDeniedError
    ):
        app.execute_tool(
            request
        )


def test_application_bootstraps_main_model_without_network(
    tmp_path: Path,
) -> None:
    settings = JarvisSettings(
        workspace_dir=tmp_path,
        ollama_model="qwen3.5:4b",
    )

    app = build_application(
        settings
    )

    selection = app.model_selection(
        ModelRole.MAIN
    )

    assert selection is not None

    assert (
        selection.provider_id
        == "ollama"
    )

    assert (
        selection.model_id
        == "qwen3.5:4b"
    )

    providers = app.model_providers()

    provider_ids = {
        provider.provider_id
        for provider in providers
    }

    assert provider_ids == {
        "openai",
        "ollama",
        "openrouter",
        "groq",
        "xai",
        "lm_studio",
    }

    models = app.available_models()

    assert [
        model.model_id
        for model in models
    ] == [
        "qwen3.5:4b"
    ]
