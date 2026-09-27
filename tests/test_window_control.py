from pathlib import Path

import pytest

from jarvis.security.capabilities import Capability
from jarvis.tools.control_window import ControlWindowTool
from jarvis.tools.list_open_windows import ListOpenWindowsTool
from jarvis.tools.window_catalog import (
    WindowCatalog,
    WindowEntry,
)


class FakeWindowBackend:
    """
    Deterministic window backend used by tests.

    No real desktop windows are changed.
    """

    def __init__(
        self,
        windows: tuple[
            WindowEntry,
            ...,
        ],
    ) -> None:
        self.windows = windows

        self.actions: list[
            tuple[
                str,
                int,
            ]
        ] = []

    def list_windows(
        self,
    ) -> tuple[
        WindowEntry,
        ...,
    ]:
        return self.windows

    def focus(
        self,
        handle: int,
    ) -> None:
        self.actions.append(
            (
                "focus",
                handle,
            )
        )

    def minimize(
        self,
        handle: int,
    ) -> None:
        self.actions.append(
            (
                "minimize",
                handle,
            )
        )

    def maximize(
        self,
        handle: int,
    ) -> None:
        self.actions.append(
            (
                "maximize",
                handle,
            )
        )

    def restore(
        self,
        handle: int,
    ) -> None:
        self.actions.append(
            (
                "restore",
                handle,
            )
        )


def test_list_open_windows_returns_titles(
    tmp_path: Path,
) -> None:
    del tmp_path

    backend = FakeWindowBackend(
        (
            WindowEntry(
                handle=101,
                title="Discord",
            ),
            WindowEntry(
                handle=102,
                title="Visual Studio Code",
            ),
        )
    )

    tool = ListOpenWindowsTool(
        WindowCatalog(
            backend
        )
    )

    assert tool.execute(
        {}
    ) == [
        "Discord",
        "Visual Studio Code",
    ]


def test_list_open_windows_is_read_only(
    tmp_path: Path,
) -> None:
    del tmp_path

    backend = FakeWindowBackend(
        ()
    )

    tool = ListOpenWindowsTool(
        WindowCatalog(
            backend
        )
    )

    assert (
        tool.required_capability
        is Capability.READ_SYSTEM_INFO
    )


def test_control_window_uses_control_capability(
    tmp_path: Path,
) -> None:
    del tmp_path

    backend = FakeWindowBackend(
        ()
    )

    tool = ControlWindowTool(
        WindowCatalog(
            backend
        )
    )

    assert (
        tool.required_capability
        is Capability.CONTROL_APPLICATION
    )


@pytest.mark.parametrize(
    (
        "action",
        "expected_action",
    ),
    [
        (
            "focus",
            "focus",
        ),
        (
            "minimize",
            "minimize",
        ),
        (
            "maximize",
            "maximize",
        ),
        (
            "restore",
            "restore",
        ),
    ],
)
def test_control_window_executes_supported_actions(
    action: str,
    expected_action: str,
) -> None:
    backend = FakeWindowBackend(
        (
            WindowEntry(
                handle=777,
                title="Discord",
            ),
        )
    )

    tool = ControlWindowTool(
        WindowCatalog(
            backend
        )
    )

    result = tool.execute(
        {
            "window": "Discord",
            "action": action,
        }
    )

    assert backend.actions == [
        (
            expected_action,
            777,
        )
    ]

    assert isinstance(
        result,
        dict,
    )

    assert result[
        "window"
    ] == "Discord"


def test_window_catalog_resolves_unique_partial_match(
    tmp_path: Path,
) -> None:
    del tmp_path

    catalog = WindowCatalog(
        FakeWindowBackend(
            (
                WindowEntry(
                    handle=1,
                    title="README.md - Visual Studio Code",
                ),
            )
        )
    )

    result = catalog.resolve(
        "Visual Studio Code"
    )

    assert result.handle == 1


def test_window_catalog_rejects_ambiguous_match(
    tmp_path: Path,
) -> None:
    del tmp_path

    catalog = WindowCatalog(
        FakeWindowBackend(
            (
                WindowEntry(
                    handle=1,
                    title="Google - Google Chrome",
                ),
                WindowEntry(
                    handle=2,
                    title="GitHub - Google Chrome",
                ),
            )
        )
    )

    with pytest.raises(
        ValueError,
        match="ambiguous",
    ):
        catalog.resolve(
            "Chrome"
        )


def test_control_window_rejects_close_action(
    tmp_path: Path,
) -> None:
    del tmp_path

    backend = FakeWindowBackend(
        (
            WindowEntry(
                handle=1,
                title="Notepad",
            ),
        )
    )

    tool = ControlWindowTool(
        WindowCatalog(
            backend
        )
    )

    with pytest.raises(
        ValueError,
        match="Unsupported window action",
    ):
        tool.execute(
            {
                "window": "Notepad",
                "action": "close",
            }
        )

    assert backend.actions == []