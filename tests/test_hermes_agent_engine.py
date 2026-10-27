import subprocess
from unittest.mock import patch

import pytest

from jarvis.agents.hermes import (
    HermesAgentEngine,
    HermesAgentError,
)


def test_hermes_engine_name() -> None:
    engine = HermesAgentEngine()

    assert engine.name == "hermes"


def test_hermes_engine_rejects_empty_prompt() -> None:
    engine = HermesAgentEngine()

    with pytest.raises(
        ValueError,
        match="prompt cannot be empty",
    ):
        engine.run("   ")


@patch(
    "jarvis.agents.hermes.shutil.which",
    return_value=r"C:\hermes\hermes.exe",
)
@patch(
    "jarvis.agents.hermes.subprocess.run",
)
def test_hermes_engine_runs_restricted_oneshot(
    run_mock,
    which_mock,
) -> None:
    del which_mock

    run_mock.return_value = subprocess.CompletedProcess(
        args=[],
        returncode=0,
        stdout="HERMES RESPONSE\n",
        stderr="",
    )

    engine = HermesAgentEngine()

    result = engine.run(
        prompt="Explain this task.",
        system_prompt="You are JARVIS.",
    )

    assert result == "HERMES RESPONSE"

    command = run_mock.call_args.args[
        0
    ]

    assert command[
        0
    ] == "hermes"

    assert "-z" in command
    assert "--ignore-rules" in command
    assert "--no-restore-cwd" in command
    assert "--toolsets" in command

    toolsets_index = command.index(
        "--toolsets"
    )

    assert command[
        toolsets_index + 1
    ] == "todo"

    # Security regression checks.
    assert "terminal" not in command
    assert "browser" not in command
    assert "computer_use" not in command
    assert "file" not in command


@patch(
    "jarvis.agents.hermes.shutil.which",
    return_value=None,
)
def test_hermes_engine_requires_installed_runtime(
    which_mock,
) -> None:
    del which_mock

    engine = HermesAgentEngine()

    with pytest.raises(
        HermesAgentError,
        match="not installed",
    ):
        engine.run(
            "Hello"
        )


@patch(
    "jarvis.agents.hermes.shutil.which",
    return_value=r"C:\hermes\hermes.exe",
)
@patch(
    "jarvis.agents.hermes.subprocess.run",
)
def test_hermes_engine_reports_process_failure(
    run_mock,
    which_mock,
) -> None:
    del which_mock

    run_mock.return_value = subprocess.CompletedProcess(
        args=[],
        returncode=1,
        stdout="",
        stderr="provider failed",
    )

    engine = HermesAgentEngine()

    with pytest.raises(
        HermesAgentError,
        match="provider failed",
    ):
        engine.run(
            "Hello"
        )


@patch(
    "jarvis.agents.hermes.shutil.which",
    return_value=r"C:\hermes\hermes.exe",
)
@patch(
    "jarvis.agents.hermes.subprocess.run",
)
def test_hermes_engine_reports_timeout(
    run_mock,
    which_mock,
) -> None:
    del which_mock

    run_mock.side_effect = subprocess.TimeoutExpired(
        cmd=[
            "hermes",
        ],
        timeout=180,
    )

    engine = HermesAgentEngine()

    with pytest.raises(
        HermesAgentError,
        match="timeout",
    ):
        engine.run(
            "Hello"
        )