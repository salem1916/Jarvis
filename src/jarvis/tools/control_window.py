from collections.abc import Mapping
from typing import ClassVar

from jarvis.security.capabilities import Capability
from jarvis.tools.base import Tool
from jarvis.tools.window_catalog import WindowCatalog


class ControlWindowTool(Tool):
    """
    Control the state of one existing Windows window.

    SAFE FIRST VERSION

    Supported:

        focus
        minimize
        maximize
        restore

    Deliberately NOT supported yet:

        close
        kill
        click
        type
        execute commands

    Those operations carry different risks and will be added
    separately.
    """

    name = "control_window"

    description = (
        "Control an existing visible Windows application window. "
        "Supported actions are focus, minimize, maximize, and "
        "restore. Use list_open_windows when the exact window "
        "title is unknown. Closing applications, clicking, typing, "
        "and command execution are not supported by this tool."
    )

    required_capability = Capability.CONTROL_APPLICATION

    parameters_schema: ClassVar[
        dict[str, object]
    ] = {
        "type": "object",
        "properties": {
            "window": {
                "type": "string",
                "description": (
                    "Human-readable title or unique part of "
                    "the open window title."
                ),
            },
            "action": {
                "type": "string",
                "enum": [
                    "focus",
                    "minimize",
                    "maximize",
                    "restore",
                ],
                "description": (
                    "Window action to perform."
                ),
            },
        },
        "required": [
            "window",
            "action",
        ],
        "additionalProperties": False,
    }

    def __init__(
        self,
        catalog: WindowCatalog,
    ) -> None:
        self.catalog = catalog

    def execute(
        self,
        arguments: Mapping[str, object],
    ) -> object:
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

        supported_actions = {
            "focus",
            "minimize",
            "maximize",
            "restore",
        }

        if action not in supported_actions:
            raise ValueError(
                "Unsupported window action. "
                "Supported actions: focus, minimize, "
                "maximize, restore."
            )

        entry = self.catalog.resolve(
            raw_window
        )

        backend = self.catalog.backend

        if action == "focus":
            backend.focus(
                entry.handle
            )

        elif action == "minimize":
            backend.minimize(
                entry.handle
            )

        elif action == "maximize":
            backend.maximize(
                entry.handle
            )

        else:
            backend.restore(
                entry.handle
            )

        return {
            "ok": True,
            "action": action,
            "window": entry.title,
        }