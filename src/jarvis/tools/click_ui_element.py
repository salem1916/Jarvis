from collections.abc import Mapping
from typing import ClassVar

from jarvis.security.capabilities import Capability
from jarvis.tools.base import Tool
from jarvis.tools.ui_automation import (
    UiElementCatalog,
    UiElementEntry,
)
from jarvis.tools.window_catalog import (
    WindowCatalog,
    WindowEntry,
)


class ClickUiElementTool(Tool):
    """
    Click one named UI Automation element.

    The model never supplies:

        raw coordinates
        native window handles
        UI Automation locators

    Duplicate title windows are resolved using the requested
    real UI control.

    Side effects are allowed only when exactly one deterministic
    window/control pair remains.
    """

    name = "click_ui_element"

    description = (
        "Click one named visible UI control inside an open Windows "
        "application. JARVIS resolves the actual UI Automation "
        "element and never accepts raw screen coordinates. If "
        "Windows exposes duplicate windows with the same title, "
        "JARVIS searches the requested control across them and "
        "clicks only when exactly one deterministic target exists. "
        "Use list_ui_elements first when the control name or type "
        "is unknown."
    )

    required_capability = Capability.CLICK_UI

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
            "element": {
                "type": "string",
                "description": (
                    "Visible name of the UI element to click."
                ),
            },
            "control_type": {
                "type": "string",
                "description": (
                    "Optional UI Automation control type such "
                    "as Button, Edit, CheckBox, ListItem, or "
                    "Hyperlink."
                ),
            },
        },
        "required": [
            "window",
            "element",
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

        raw_element = arguments.get(
            "element"
        )

        raw_control_type = arguments.get(
            "control_type"
        )

        if not isinstance(
            raw_window,
            str,
        ):
            raise TypeError(
                "'window' must be a string."
            )

        if not isinstance(
            raw_element,
            str,
        ):
            raise TypeError(
                "'element' must be a string."
            )

        if (
            raw_control_type is not None
            and not isinstance(
                raw_control_type,
                str,
            )
        ):
            raise TypeError(
                "'control_type' must be a string when provided."
            )

        windows = self.window_catalog.matching_entries(
            raw_window
        )

        # -------------------------------------------------
        # CRITICAL SELF-PROTECTION
        # -------------------------------------------------

        if any(
            "jarvis"
            in window.title.casefold()
            for window in windows
        ):
            raise ValueError(
                "JARVIS cannot automate its own application UI."
            )

        # -------------------------------------------------
        # RESOLVE ACROSS DUPLICATE WINDOWS
        #
        # Example:
        #
        # Windows may expose:
        #
        #     Calculator
        #     Calculator
        #
        # The model asks:
        #
        #     element = "7"
        #     control_type = "Button"
        #
        # We search the real UI tree in every matching window.
        #
        # Exactly ONE window/control pair must remain before
        # anything is clicked.
        # -------------------------------------------------

        targets: list[
            tuple[
                WindowEntry,
                UiElementEntry,
            ]
        ] = []

        for window in windows:
            element_matches = (
                self.ui_catalog.matching_entries(
                    window_handle=window.handle,
                    requested_name=raw_element,
                    requested_control_type=raw_control_type,
                )
            )

            for element in element_matches:
                targets.append(
                    (
                        window,
                        element,
                    )
                )

        if not targets:
            raise ValueError(
                "No visible UI element matched "
                f"'{raw_element}' in the matching "
                f"'{raw_window}' window or windows. "
                "Use list_ui_elements to inspect the "
                "available controls."
            )

        if len(
            targets
        ) > 1:
            descriptions = ", ".join(
                (
                    f"{element.name} "
                    f"({element.control_type}) "
                    f"in {window.title}"
                )
                for window, element
                in targets[:10]
            )

            raise ValueError(
                "UI target is ambiguous. "
                f"Matches: {descriptions}."
            )

        window, element = targets[0]

        if not element.enabled:
            raise ValueError(
                "The selected UI element is disabled."
            )

        # Focus only AFTER deterministic resolution succeeds.
        self.window_catalog.backend.focus(
            window.handle
        )

        self.ui_catalog.backend.click(
            window_handle=window.handle,
            locator=element.locator,
        )

        return {
            "ok": True,
            "action": "ui_element_clicked",
            "window": window.title,
            "element": element.name,
            "control_type": element.control_type,
        }