import ctypes
from pathlib import Path

import pytest

from jarvis.security.capabilities import Capability
from jarvis.tools import type_text
from jarvis.tools.type_text import TypeTextTool
from jarvis.tools.window_catalog import (
    WindowCatalog,
    WindowEntry,
)


class FakeWindowBackend:
    """
    Fake trusted window backend.

    Records which window JARVIS focused.
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


class FakeTextBackend:
    """
    Records literal text instead of touching the real
    keyboard.
    """

    def __init__(
        self,
    ) -> None:
        self.typed: list[
            str
        ] = []

    def type_text(
        self,
        text: str,
    ) -> None:
        self.typed.append(
            text
        )


def test_windows_input_structure_has_native_size() -> None:
    """
    Regression test.

    Windows SendInput requires the exact native sizeof(INPUT).

    On 64-bit Windows:

        sizeof(INPUT) == 40 bytes

    On 32-bit Windows:

        sizeof(INPUT) == 28 bytes

    If our ctypes definition is incomplete, Windows may reject
    every keyboard event even though the rest of the tool works.
    """

    expected_size = (
        40
        if ctypes.sizeof(
            ctypes.c_void_p
        ) == 8
        else 28
    )

    assert (
        ctypes.sizeof(
            type_text._Input
        )
        == expected_size
    )


def test_type_text_uses_separate_capability(
    tmp_path: Path,
) -> None:
    del tmp_path

    window_backend = FakeWindowBackend(
        ()
    )

    tool = TypeTextTool(
        catalog=WindowCatalog(
            window_backend
        ),
        text_backend=FakeTextBackend(),
    )

    assert (
        tool.required_capability
        is Capability.TYPE_TEXT
    )


def test_type_text_focuses_target_before_typing(
    tmp_path: Path,
) -> None:
    del tmp_path

    window_backend = FakeWindowBackend(
        (
            WindowEntry(
                handle=123,
                title="Untitled - Notepad",
            ),
        )
    )

    text_backend = FakeTextBackend()

    tool = TypeTextTool(
        catalog=WindowCatalog(
            window_backend
        ),
        text_backend=text_backend,
    )

    result = tool.execute(
        {
            "window": "Notepad",
            "text": "Hello from JARVIS",
        }
    )

    assert window_backend.actions == [
        (
            "focus",
            123,
        )
    ]

    assert text_backend.typed == [
        "Hello from JARVIS",
    ]

    assert isinstance(
        result,
        dict,
    )

    assert result[
        "action"
    ] == "text_typed"


def test_type_text_preserves_unicode_and_newlines(
    tmp_path: Path,
) -> None:
    del tmp_path

    window_backend = FakeWindowBackend(
        (
            WindowEntry(
                handle=10,
                title="Notepad",
            ),
        )
    )

    text_backend = FakeTextBackend()

    tool = TypeTextTool(
        catalog=WindowCatalog(
            window_backend
        ),
        text_backend=text_backend,
    )

    text = (
        "English\n"
        "Deutsch\n"
        "Français\n"
        "مرحبا"
    )

    tool.execute(
        {
            "window": "Notepad",
            "text": text,
        }
    )

    assert text_backend.typed == [
        text,
    ]


def test_type_text_rejects_control_characters_before_focus(
    tmp_path: Path,
) -> None:
    del tmp_path

    window_backend = FakeWindowBackend(
        (
            WindowEntry(
                handle=10,
                title="Notepad",
            ),
        )
    )

    text_backend = FakeTextBackend()

    tool = TypeTextTool(
        catalog=WindowCatalog(
            window_backend
        ),
        text_backend=text_backend,
    )

    with pytest.raises(
        ValueError,
        match="unsupported control character",
    ):
        tool.execute(
            {
                "window": "Notepad",
                "text": "hello\x00world",
            }
        )

    assert window_backend.actions == []
    assert text_backend.typed == []


def test_type_text_rejects_excessive_text(
    tmp_path: Path,
) -> None:
    del tmp_path

    window_backend = FakeWindowBackend(
        (
            WindowEntry(
                handle=10,
                title="Notepad",
            ),
        )
    )

    text_backend = FakeTextBackend()

    tool = TypeTextTool(
        catalog=WindowCatalog(
            window_backend
        ),
        text_backend=text_backend,
    )

    with pytest.raises(
        ValueError,
        match="too long",
    ):
        tool.execute(
            {
                "window": "Notepad",
                "text": "x" * 10_001,
            }
        )

    assert window_backend.actions == []
    assert text_backend.typed == []