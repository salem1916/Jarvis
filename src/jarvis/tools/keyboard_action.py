import logging
from collections.abc import Mapping
from typing import ClassVar, Protocol

import win32api
import win32con

from jarvis.security.capabilities import Capability
from jarvis.tools.base import Tool
from jarvis.tools.window_catalog import WindowCatalog

logger = logging.getLogger(
    __name__
)


class KeyboardActionBackend(Protocol):
    """
    Platform abstraction for trusted keyboard actions.

    Tests use a fake backend.

    The real Windows application uses Win32KeyboardActionBackend.
    """

    def perform(
        self,
        keys: tuple[int, ...],
    ) -> None:
        ...


class Win32KeyboardActionBackend:
    """
    Perform one trusted keyboard chord through Windows.

    The AI never supplies virtual-key codes.

    It only selects a named action from KeyboardActionTool's
    internal allowlist.
    """

    def perform(
        self,
        keys: tuple[int, ...],
    ) -> None:
        """
        Press one trusted key combination.

        Example:

            (
                VK_CONTROL,
                ord("S"),
            )

        becomes:

            Ctrl down
            S down
            S up
            Ctrl up

        If Windows fails partway through, JARVIS attempts to
        release any keys that may still be held down.
        """

        if not keys:
            raise ValueError(
                "Keyboard action contains no keys."
            )

        pressed: list[int] = []

        try:
            # =============================================
            # KEY DOWN
            # =============================================

            for key in keys:
                win32api.keybd_event(
                    key,
                    0,
                    0,
                    0,
                )

                pressed.append(
                    key
                )

            # =============================================
            # KEY UP
            # =============================================
            #
            # Release in reverse order:
            #
            # Ctrl down
            # S down
            # S up
            # Ctrl up
            # =============================================

            for key in reversed(
                keys
            ):
                win32api.keybd_event(
                    key,
                    0,
                    win32con.KEYEVENTF_KEYUP,
                    0,
                )

                pressed.remove(
                    key
                )

        finally:
            # =============================================
            # DEFENSIVE CLEANUP
            # =============================================
            #
            # If Windows raises while sending a chord, keys
            # might otherwise remain logically pressed.
            #
            # Cleanup failures are logged instead of silently
            # swallowed. They must not replace the original
            # keyboard-input exception.
            # =============================================

            for key in reversed(
                pressed
            ):
                try:
                    win32api.keybd_event(
                        key,
                        0,
                        win32con.KEYEVENTF_KEYUP,
                        0,
                    )

                except Exception:
                    logger.exception(
                        "Failed to release virtual key %s "
                        "during keyboard-action cleanup.",
                        key,
                    )


class KeyboardActionTool(Tool):
    """
    Perform one predefined keyboard action in a specific
    visible Windows window.

    SECURITY MODEL

    The model supplies:

        window
        named action

    It does NOT supply:

        virtual-key codes
        arbitrary key combinations
        shell commands
        native window handles

    The allowed action catalog is trusted JARVIS code.
    """

    name = "keyboard_action"

    description = (
        "Perform one predefined keyboard action in a specific "
        "visible Windows window. Supported actions are "
        "select_all, copy, paste, save, undo, redo, enter, "
        "escape, and tab. JARVIS resolves and focuses the target "
        "window first. Arbitrary keyboard combinations are not "
        "supported."
    )

    required_capability = Capability.KEYBOARD_ACTION

    parameters_schema: ClassVar[
        dict[str, object]
    ] = {
        "type": "object",
        "properties": {
            "window": {
                "type": "string",
                "description": (
                    "Visible window title or a unique portion "
                    "of the title."
                ),
            },
            "action": {
                "type": "string",
                "enum": [
                    "select_all",
                    "copy",
                    "paste",
                    "save",
                    "undo",
                    "redo",
                    "enter",
                    "escape",
                    "tab",
                ],
                "description": (
                    "Trusted keyboard action to perform."
                ),
            },
        },
        "required": [
            "window",
            "action",
        ],
        "additionalProperties": False,
    }

    # =====================================================
    # TRUSTED KEYBOARD ACTION ALLOWLIST
    # =====================================================
    #
    # The model chooses only one of these names.
    #
    # It cannot provide arbitrary virtual-key values or build
    # arbitrary keyboard combinations.
    # =====================================================

    _ACTIONS: ClassVar[
        dict[
            str,
            tuple[int, ...],
        ]
    ] = {
        "select_all": (
            win32con.VK_CONTROL,
            ord("A"),
        ),

        "copy": (
            win32con.VK_CONTROL,
            ord("C"),
        ),

        "paste": (
            win32con.VK_CONTROL,
            ord("V"),
        ),

        "save": (
            win32con.VK_CONTROL,
            ord("S"),
        ),

        "undo": (
            win32con.VK_CONTROL,
            ord("Z"),
        ),

        "redo": (
            win32con.VK_CONTROL,
            ord("Y"),
        ),

        "enter": (
            win32con.VK_RETURN,
        ),

        "escape": (
            win32con.VK_ESCAPE,
        ),

        "tab": (
            win32con.VK_TAB,
        ),
    }

    def __init__(
        self,
        catalog: WindowCatalog,
        keyboard_backend: KeyboardActionBackend,
    ) -> None:
        self.catalog = catalog
        self.keyboard_backend = keyboard_backend

    def execute(
        self,
        arguments: Mapping[str, object],
    ) -> object:
        """
        Focus one resolved window and perform one trusted
        keyboard action.
        """

        raw_window = arguments.get(
            "window"
        )

        raw_action = arguments.get(
            "action"
        )

        if not isinstance(
            raw_window,
            str,
        ):
            raise TypeError(
                "'window' must be a string."
            )

        if not isinstance(
            raw_action,
            str,
        ):
            raise TypeError(
                "'action' must be a string."
            )

        action = (
            raw_action
            .strip()
            .casefold()
        )

        keys = self._ACTIONS.get(
            action
        )

        if keys is None:
            supported = ", ".join(
                self._ACTIONS
            )

            raise ValueError(
                "Unsupported keyboard action. "
                f"Supported actions: {supported}."
            )

        # -------------------------------------------------
        # Resolve the target through trusted window discovery.
        # -------------------------------------------------

        entry = self.catalog.resolve(
            raw_window
        )

        # -------------------------------------------------
        # Focus the trusted resolved window.
        # -------------------------------------------------

        self.catalog.backend.focus(
            entry.handle
        )

        # -------------------------------------------------
        # Execute only the internally defined key sequence.
        # -------------------------------------------------

        self.keyboard_backend.perform(
            keys
        )

        return {
            "ok": True,
            "action": action,
            "window": entry.title,
        }