from pathlib import Path

import pytest

from jarvis.security.capabilities import Capability
from jarvis.tools import open_application
from jarvis.tools.open_application import OpenApplicationTool


class FakeProcess:
    """
    Minimal subprocess replacement used by the tests.
    """

    pid = 12345


def test_open_application_uses_correct_capability(
    tmp_path: Path,
) -> None:
    tool = OpenApplicationTool(
        windows_root=tmp_path
    )

    assert (
        tool.required_capability
        is Capability.OPEN_APPLICATION
    )


def test_open_application_launches_allowlisted_application(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """
    A trusted known application should resolve to its
    internally controlled executable.
    """

    windows = tmp_path / "Windows"

    system32 = windows / "System32"

    system32.mkdir(
        parents=True
    )

    executable = system32 / "notepad.exe"

    executable.write_bytes(
        b"fake"
    )

    launched_commands: list[
        list[str]
    ] = []

    def fake_popen(
        command: list[str],
        *,
        shell: bool,
    ) -> FakeProcess:
        assert shell is False

        launched_commands.append(
            command
        )

        return FakeProcess()

    monkeypatch.setattr(
        open_application.subprocess,
        "Popen",
        fake_popen,
    )

    tool = OpenApplicationTool(
        windows_root=windows
    )

    result = tool.execute(
        {
            "application": "Notepad",
        }
    )

    assert isinstance(
        result,
        dict,
    )

    assert launched_commands == [
        [
            str(
                executable.resolve()
            )
        ]
    ]

    assert result[
        "application"
    ] == "Notepad"

    assert result[
        "pid"
    ] == 12345


def test_open_application_supports_aliases(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """
    Natural aliases such as 'calc' should still resolve
    deterministically.
    """

    windows = tmp_path / "Windows"

    system32 = windows / "System32"

    system32.mkdir(
        parents=True
    )

    executable = system32 / "calc.exe"

    executable.write_bytes(
        b"fake"
    )

    def fake_popen(
        command: list[str],
        *,
        shell: bool,
    ) -> FakeProcess:
        assert command == [
            str(
                executable.resolve()
            )
        ]

        assert shell is False

        return FakeProcess()

    monkeypatch.setattr(
        open_application.subprocess,
        "Popen",
        fake_popen,
    )

    tool = OpenApplicationTool(
        windows_root=windows
    )

    result = tool.execute(
        {
            "application": "calc",
        }
    )

    assert isinstance(
        result,
        dict,
    )

    assert result[
        "application"
    ] == "Calculator"


def test_open_application_rejects_unknown_application(
    tmp_path: Path,
) -> None:
    """
    The model must not be able to turn this tool into an
    arbitrary executable launcher.
    """

    tool = OpenApplicationTool(
        windows_root=tmp_path
    )

    with pytest.raises(
        ValueError,
        match="Unsupported application",
    ):
        tool.execute(
            {
                "application": "cmd.exe",
            }
        )


def test_open_application_rejects_missing_executable(
    tmp_path: Path,
) -> None:
    """
    A catalog entry must still physically exist before it
    can be launched.
    """

    tool = OpenApplicationTool(
        windows_root=tmp_path
    )

    with pytest.raises(
        FileNotFoundError,
    ):
        tool.execute(
            {
                "application": "notepad",
            }
        )