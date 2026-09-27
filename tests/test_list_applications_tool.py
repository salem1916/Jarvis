from pathlib import Path

from jarvis.security.capabilities import Capability
from jarvis.tools.application_catalog import ApplicationCatalog
from jarvis.tools.list_applications import ListApplicationsTool


def test_list_applications_returns_catalog_names(
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
        / "Telegram.lnk"
    ).write_bytes(
        b"fake"
    )

    catalog = ApplicationCatalog(
        windows_root=tmp_path,
        start_menu_roots=(
            start_menu,
        ),
    )

    tool = ListApplicationsTool(
        catalog
    )

    result = tool.execute(
        {}
    )

    assert result == [
        "Discord",
        "Telegram",
    ]


def test_list_applications_is_read_only_system_info(
    tmp_path: Path,
) -> None:
    catalog = ApplicationCatalog(
        windows_root=tmp_path,
        start_menu_roots=(),
    )

    tool = ListApplicationsTool(
        catalog
    )

    assert (
        tool.required_capability
        is Capability.READ_SYSTEM_INFO
    )
    