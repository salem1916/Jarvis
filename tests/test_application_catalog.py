from pathlib import Path

import pytest

from jarvis.tools.application_catalog import ApplicationCatalog


def test_catalog_discovers_start_menu_shortcuts(
    tmp_path: Path,
) -> None:
    start_menu = tmp_path / "StartMenu"

    start_menu.mkdir()

    (
        start_menu
        / "Discord.lnk"
    ).write_bytes(
        b"fake"
    )

    (
        start_menu
        / "Google Chrome.lnk"
    ).write_bytes(
        b"fake"
    )

    catalog = ApplicationCatalog(
        windows_root=tmp_path,
        start_menu_roots=(
            start_menu,
        ),
    )

    assert catalog.names() == (
        "Discord",
        "Google Chrome",
    )


def test_catalog_discovers_nested_shortcuts(
    tmp_path: Path,
) -> None:
    start_menu = tmp_path / "StartMenu"

    nested = (
        start_menu
        / "Development"
    )

    nested.mkdir(
        parents=True
    )

    (
        nested
        / "Visual Studio Code.lnk"
    ).write_bytes(
        b"fake"
    )

    catalog = ApplicationCatalog(
        windows_root=tmp_path,
        start_menu_roots=(
            start_menu,
        ),
    )

    assert (
        "Visual Studio Code"
        in catalog.names()
    )


def test_catalog_resolves_unique_partial_name(
    tmp_path: Path,
) -> None:
    start_menu = tmp_path / "StartMenu"

    start_menu.mkdir()

    shortcut = (
        start_menu
        / "Google Chrome.lnk"
    )

    shortcut.write_bytes(
        b"fake"
    )

    catalog = ApplicationCatalog(
        windows_root=tmp_path,
        start_menu_roots=(
            start_menu,
        ),
    )

    entry = catalog.resolve(
        "chrome"
    )

    assert (
        entry.name
        == "Google Chrome"
    )

    assert (
        entry.launch_path
        == shortcut.resolve()
    )


def test_catalog_rejects_ambiguous_name(
    tmp_path: Path,
) -> None:
    start_menu = tmp_path / "StartMenu"

    start_menu.mkdir()

    (
        start_menu
        / "Visual Studio Code.lnk"
    ).write_bytes(
        b"fake"
    )

    (
        start_menu
        / "Visual Studio Installer.lnk"
    ).write_bytes(
        b"fake"
    )

    catalog = ApplicationCatalog(
        windows_root=tmp_path,
        start_menu_roots=(
            start_menu,
        ),
    )

    with pytest.raises(
        ValueError,
        match="ambiguous",
    ):
        catalog.resolve(
            "Visual Studio"
        )


def test_catalog_excludes_command_interpreters(
    tmp_path: Path,
) -> None:
    start_menu = tmp_path / "StartMenu"

    start_menu.mkdir()

    (
        start_menu
        / "Command Prompt.lnk"
    ).write_bytes(
        b"fake"
    )

    (
        start_menu
        / "Windows PowerShell.lnk"
    ).write_bytes(
        b"fake"
    )

    (
        start_menu
        / "Discord.lnk"
    ).write_bytes(
        b"fake"
    )

    catalog = ApplicationCatalog(
        windows_root=tmp_path,
        start_menu_roots=(
            start_menu,
        ),
    )

    names = catalog.names()

    assert "Discord" in names
    assert "Command Prompt" not in names
    assert "Windows PowerShell" not in names