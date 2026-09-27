from collections.abc import Mapping
from typing import ClassVar

from jarvis.security.capabilities import Capability
from jarvis.tools.base import Tool
from jarvis.tools.ui_automation import UiElementCatalog
from jarvis.tools.window_catalog import WindowCatalog


class ListUiElementsTool(Tool):
    """
    Inspect named visible controls inside one visible window.

    Internal UI locators are never exposed to the model.
    """

    name = "list_ui_elements"

    description = (
        "List named visible UI controls inside a specific "
        "open Windows application window. Returns control names, "
        "control types, and enabled state. Use this before "
        "click_ui_element when the exact control name is unknown."
    )

    required_capability = Capability.INSPECT_UI

    parameters_schema: ClassVar[
        dict[str, object]
    ] = {
        "type": "object",
        "properties": {
            "window": {
                "type": "string",
                "description": (
                    "Visible window title or a unique portion "
                    "of its title."
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
        window_catalog: WindowCatalog,
        ui_catalog: UiElementCatalog,
    ) -> None:
        self.window_catalog = window_catalog
        self.ui_catalog = ui_catalog

    def execute(
        self,
        arguments: Mapping[str, object],
    ) -> object:
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

        window = self.window_catalog.resolve(
            raw_window
        )

        # Prevent the AI from inspecting JARVIS's own UI.
        #
        # This protects permission controls and confirmation
        # surfaces from self-automation.
        if (
            "jarvis"
            in window.title.casefold()
        ):
            raise ValueError(
                "JARVIS cannot inspect its own application UI."
            )

        entries = self.ui_catalog.entries(
            window.handle
        )

        return [
            {
                "name": entry.name,
                "control_type": entry.control_type,
                "enabled": entry.enabled,
            }
            for entry in entries
        ]