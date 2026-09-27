from pathlib import Path

import pytest

from jarvis.security.capabilities import Capability
from jarvis.tools import open_application
from jarvis.tools.application_catalog import ApplicationCatalog
from jarvis.tools.open_application import OpenApplicationTool


def test_open_application_uses_correct_capability(
    tmp_path: Path,
) -> None:
    catalog = ApplicationCatalog(
        windows_root=tmp_path,
        start_menu_roots=(),
    )

    tool = OpenApplicationTool(
        catalog
    )

    assert (
        tool.required_capability
        is Capability.OPEN_APPLICATION
    )


def test_open_application_launches_discovered_app(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    windows = tmp_path / "Windows"

    windows.mkdir()

    start_menu = tmp_path / "StartMenu"

    start_menu.mkdir()

    chrome = (
        start_menu
        / "Google Chrome.lnk"
    )

    chrome.write_bytes(
        b"fake shortcut"
    )

    catalog = ApplicationCatalog(
        windows_root=windows,
        start_menu_roots=(
            start_menu,
        ),
    )

    launched: list[
        str
    ] = []

    def fake_startfile(
        path: str,
    ) -> None:
        launched.append(
            path
        )

    monkeypatch.setattr(
        open_application.os,
        "startfile",
        fake_startfile,
        raising=False,
    )

    tool = OpenApplicationTool(
        catalog
    )

    result = tool.execute(
        {
            "application": "chrome",
        }
    )

    assert isinstance(
        result,
        dict,
    )

    assert launched == [
        str(
            chrome.resolve()
        )
    ]

    assert (
        result[
            "application"
        ]
        == "Google Chrome"
    )


def test_open_application_supports_vscode_alias(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    start_menu = tmp_path / "StartMenu"

    start_menu.mkdir()

    vscode = (
        start_menu
        / "Visual Studio Code.lnk"
    )

    vscode.write_bytes(
        b"fake"
    )

    catalog = ApplicationCatalog(
        windows_root=tmp_path,
        start_menu_roots=(
            start_menu,
        ),
    )

    launched: list[
        str
    ] = []

    monkeypatch.setattr(
        open_application.os,
        "startfile",
        lambda path:
            launched.append(
                path
            ),
        raising=False,
    )

    tool = OpenApplicationTool(
        catalog
    )

    tool.execute(
        {
            "application": "VS Code",
        }
    )

    assert launched == [
        str(
            vscode.resolve()
        )
    ]


def test_open_application_blocks_command_prompt(
    tmp_path: Path,
) -> None:
    start_menu = tmp_path / "StartMenu"

    start_menu.mkdir()

    # Even if Windows has a Command Prompt shortcut,
    # OPEN_APPLICATION must exclude it.
    command_prompt = (
        start_menu
        / "Command Prompt.lnk"
    )

    command_prompt.write_bytes(
        b"fake"
    )

    catalog = ApplicationCatalog(
        windows_root=tmp_path,
        start_menu_roots=(
            start_menu,
        ),
    )

    tool = OpenApplicationTool(
        catalog
    )

    with pytest.raises(
        ValueError,
        match="intentionally blocked",
    ):
        tool.execute(
            {
                "application": "cmd.exe",
            }
        )


def test_open_application_does_not_accept_arbitrary_path(
    tmp_path: Path,
) -> None:
    catalog = ApplicationCatalog(
        windows_root=tmp_path,
        start_menu_roots=(),
    )

    tool = OpenApplicationTool(
        catalog
    )

    with pytest.raises(
        ValueError,
    ):
        tool.execute(
            {
                "application":
                    r"C:\Windows\System32\cmd.exe",
            }
        )