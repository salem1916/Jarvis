from pathlib import Path

import pytest

from jarvis.security.capabilities import Capability
from jarvis.tools.close_window import CloseWindowTool
from jarvis.tools.window_catalog import (
    WindowCatalog,
    WindowEntry,
)


class FakeWindowCatalogBackend:
    """
    Read-only fake backend for WindowCatalog.
    """

    def __init__(
        self,
        windows: tuple[
            WindowEntry,
            ...,
        ],
    ) -> None:
        self.windows = windows

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
        del handle

    def minimize(
        self,
        handle: int,
    ) -> None:
        del handle

    def maximize(
        self,
        handle: int,
    ) -> None:
        del handle

    def restore(
        self,
        handle: int,
    ) -> None:
        del handle


class FakeCloseBackend:
    """
    Records graceful close requests without touching real
    Windows applications.
    """

    def __init__(
        self,
    ) -> None:
        self.closed_handles: list[
            int
        ] = []

    def request_close(
        self,
        handle: int,
    ) -> None:
        self.closed_handles.append(
            handle
        )


def test_close_window_uses_separate_capability(
    tmp_path: Path,
) -> None:
    del tmp_path

    catalog = WindowCatalog(
        FakeWindowCatalogBackend(
            ()
        )
    )

    tool = CloseWindowTool(
        catalog=catalog,
        backend=FakeCloseBackend(),
    )

    assert (
        tool.required_capability
        is Capability.CLOSE_APPLICATION
    )


def test_close_window_requests_normal_close(
    tmp_path: Path,
) -> None:
    del tmp_path

    catalog = WindowCatalog(
        FakeWindowCatalogBackend(
            (
                WindowEntry(
                    handle=500,
                    title="Untitled - Notepad",
                ),
            )
        )
    )

    close_backend = FakeCloseBackend()

    tool = CloseWindowTool(
        catalog=catalog,
        backend=close_backend,
    )

    result = tool.execute(
        {
            "window": "Notepad",
        }
    )

    assert close_backend.closed_handles == [
        500,
    ]

    assert isinstance(
        result,
        dict,
    )

    assert result[
        "action"
    ] == "close_requested"

    assert result[
        "window"
    ] == "Untitled - Notepad"


def test_close_window_rejects_force_argument(
    tmp_path: Path,
) -> None:
    del tmp_path

    catalog = WindowCatalog(
        FakeWindowCatalogBackend(
            (
                WindowEntry(
                    handle=500,
                    title="Notepad",
                ),
            )
        )
    )

    close_backend = FakeCloseBackend()

    tool = CloseWindowTool(
        catalog=catalog,
        backend=close_backend,
    )

    with pytest.raises(
        ValueError,
        match="Force closing is not supported",
    ):
        tool.execute(
            {
                "window": "Notepad",
                "force": True,
            }
        )

    assert close_backend.closed_handles == []