from collections.abc import Mapping
from typing import ClassVar, Protocol

import win32con
import win32gui

from jarvis.security.capabilities import Capability
from jarvis.tools.base import Tool
from jarvis.tools.window_catalog import WindowCatalog


class CloseWindowBackend(Protocol):
    """
    Interface for requesting that one native Windows window
    close normally.

    This is intentionally NOT process termination.
    """

    def request_close(
        self,
        handle: int,
    ) -> None:
        ...


class Win32CloseWindowBackend:
    """
    Real Windows implementation.

    WM_CLOSE is the normal Windows close request.

    Applications may:

        close normally
        show a Save dialog
        ask for confirmation
        refuse or delay closing

    We deliberately do NOT terminate the process.
    """

    def request_close(
        self,
        handle: int,
    ) -> None:
        if not win32gui.IsWindow(
            handle
        ):
            raise ValueError(
                "The selected window no longer exists."
            )

        win32gui.PostMessage(
            handle,
            win32con.WM_CLOSE,
            0,
            0,
        )


class CloseWindowTool(Tool):
    """
    Ask one existing visible Windows window to close normally.

    SECURITY MODEL

    This tool performs a graceful close request only.

    It does NOT:

        kill a process
        terminate a process
        bypass Save dialogs
        click confirmation dialogs
        run commands

    Force termination will be implemented later as a
    completely separate higher-risk capability.
    """

    name = "close_window"

    description = (
        "Request that an existing visible Windows application "
        "window close normally. The application may show a Save "
        "or confirmation dialog before closing. This tool does "
        "not force-kill processes and cannot bypass application "
        "prompts. Use list_open_windows when the exact window "
        "title is unknown."
    )

    required_capability = Capability.CLOSE_APPLICATION

    parameters_schema: ClassVar[
        dict[str, object]
    ] = {
        "type": "object",
        "properties": {
            "window": {
                "type": "string",
                "description": (
                    "Human-readable title or unique portion "
                    "of the visible window title."
                ),
            },
        },
        "required": [
            "window",
        ],
        "additionalProperties": False,
    }

    def __init__(
        self,
        catalog: WindowCatalog,
        backend: CloseWindowBackend,
    ) -> None:
        self.catalog = catalog
        self.backend = backend

    def execute(
        self,
        arguments: Mapping[str, object],
    ) -> object:
        """
        Request graceful closing of exactly one resolved
        visible window.
        """

        # Defensive validation in addition to the model's
        # JSON schema.
        unexpected_arguments = (
            set(
                arguments
            )
            - {
                "window",
            }
        )

        if unexpected_arguments:
            raise ValueError(
                "close_window accepts only the 'window' "
                "argument. Force closing is not supported."
            )

        raw_window = arguments.get(
            "window"
        )

        if not isinstance(
            raw_window,
            str,
        ):
            raise TypeError(
                "'window' must be a string."
            )

        entry = self.catalog.resolve(
            raw_window
        )

        self.backend.request_close(
            entry.handle
        )

        return {
            "ok": True,
            "action": "close_requested",
            "window": entry.title,
        }