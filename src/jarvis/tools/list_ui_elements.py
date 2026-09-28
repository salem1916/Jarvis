from collections.abc import Mapping
from typing import ClassVar

from jarvis.security.capabilities import Capability
from jarvis.tools.base import Tool
from jarvis.tools.ui_automation import UiElementCatalog
from jarvis.tools.window_catalog import WindowCatalog


class ListUiElementsTool(Tool):
    """
    Inspect named visible controls inside matching windows.

    Duplicate top-level windows with the same visible title are
    allowed for read-only inspection.

    Their visible controls are merged and deduplicated.

    Internal handles and UI locators are never exposed.
    """

    name = "list_ui_elements"

    description = (
        "List named visible UI controls inside a specific open "
        "Windows application window. If Windows exposes multiple "
        "top-level windows with the same title, JARVIS safely "
        "inspects all matching windows and merges duplicate "
        "controls. Returns control names, types, and enabled "
        "state. Use this before click_ui_element when the exact "
        "control is unknown."
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

        windows = self.window_catalog.matching_entries(
            raw_window
        )

        # -------------------------------------------------
        # SELF-PROTECTION
        # -------------------------------------------------

        if any(
            "jarvis"
            in window.title.casefold()
            for window in windows
        ):
            raise ValueError(
                "JARVIS cannot inspect its own application UI."
            )

        # -------------------------------------------------
        # READ-ONLY MERGE
        #
        # Modern Windows applications may expose two or more
        # top-level windows with identical visible titles.
        #
        # Inspection is read-only, so inspecting all title
        # matches is safe.
        #
        # We deduplicate equivalent named controls before
        # exposing them to the model.
        # -------------------------------------------------

        merged: dict[
            tuple[
                str,
                str,
                bool,
            ],
            dict[
                str,
                object,
            ],
        ] = {}

        for window in windows:
            entries = self.ui_catalog.entries(
                window.handle
            )

            for entry in entries:
                key = (
                    entry.name.casefold(),
                    entry.control_type.casefold(),
                    entry.enabled,
                )

                if key in merged:
                    continue

                merged[key] = {
                    "name": entry.name,
                    "control_type": entry.control_type,
                    "enabled": entry.enabled,
                }

        return list(
            merged.values()
        )