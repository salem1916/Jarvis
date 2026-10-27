from pathlib import Path

import pytest
import win32con

from jarvis.security.capabilities import Capability
from jarvis.tools.keyboard_action import KeyboardActionTool
from jarvis.tools.window_catalog import (
    WindowCatalog,
    WindowEntry,
)


class FakeWindowBackend:
    """
    Records window focus actions without touching Windows.
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


class FakeKeyboardBackend:
    """
    Records trusted keyboard chords without sending real input.
    """

    def __init__(
        self,
    ) -> None:
        self.performed: list[
            tuple[int, ...]
        ] = []

    def perform(
        self,
        keys: tuple[int, ...],
    ) -> None:
        self.performed.append(
            keys
        )


def test_keyboard_action_uses_separate_capability(
    tmp_path: Path,
) -> None:
    del tmp_path

    tool = KeyboardActionTool(
        catalog=WindowCatalog(
            FakeWindowBackend(
                ()
            )
        ),
        keyboard_backend=FakeKeyboardBackend(),
    )

    assert (
        tool.required_capability
        is Capability.KEYBOARD_ACTION
    )


@pytest.mark.parametrize(
    (
        "action",
        "expected_keys",
    ),
    [
        (
            "select_all",
            (
                win32con.VK_CONTROL,
                ord("A"),
            ),
        ),
        (
            "copy",
            (
                win32con.VK_CONTROL,
                ord("C"),
            ),
        ),
        (
            "paste",
            (
                win32con.VK_CONTROL,
                ord("V"),
            ),
        ),
        (
            "save",
            (
                win32con.VK_CONTROL,
                ord("S"),
            ),
        ),
        (
            "undo",
            (
                win32con.VK_CONTROL,
                ord("Z"),
            ),
        ),
        (
            "redo",
            (
                win32con.VK_CONTROL,
                ord("Y"),
            ),
        ),
        (
            "enter",
            (
                win32con.VK_RETURN,
            ),
        ),
        (
            "escape",
            (
                win32con.VK_ESCAPE,
            ),
        ),
        (
            "tab",
            (
                win32con.VK_TAB,
            ),
        ),
        (
            "close_tab",
            (
                win32con.VK_CONTROL,
                ord("W"),
            ),
        ),
    ],
)
def test_keyboard_action_maps_trusted_actions(
    action: str,
    expected_keys: tuple[int, ...],
) -> None:
    window_backend = FakeWindowBackend(
        (
            WindowEntry(
                handle=44,
                title="Untitled - Notepad",
            ),
        )
    )

    keyboard_backend = FakeKeyboardBackend()

    tool = KeyboardActionTool(
        catalog=WindowCatalog(
            window_backend
        ),
        keyboard_backend=keyboard_backend,
    )

    result = tool.execute(
        {
            "window": "Notepad",
            "action": action,
        }
    )

    assert window_backend.actions == [
        (
            "focus",
            44,
        )
    ]

    assert keyboard_backend.performed == [
        expected_keys,
    ]

    assert isinstance(
        result,
        dict,
    )

    assert result[
        "action"
    ] == action


def test_keyboard_action_rejects_arbitrary_hotkey(
    tmp_path: Path,
) -> None:
    del tmp_path

    window_backend = FakeWindowBackend(
        (
            WindowEntry(
                handle=44,
                title="Notepad",
            ),
        )
    )

    keyboard_backend = FakeKeyboardBackend()

    tool = KeyboardActionTool(
        catalog=WindowCatalog(
            window_backend
        ),
        keyboard_backend=keyboard_backend,
    )

    with pytest.raises(
        ValueError,
        match="Unsupported keyboard action",
    ):
        tool.execute(
            {
                "window": "Notepad",
                "action": "alt+f4",
            }
        )

    # Invalid model input must not focus or modify anything.
    assert window_backend.actions == []
    assert keyboard_backend.performed == []
