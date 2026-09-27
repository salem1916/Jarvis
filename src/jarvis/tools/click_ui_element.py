from collections.abc import Mapping
from typing import ClassVar

from jarvis.security.capabilities import Capability
from jarvis.tools.base import Tool
from jarvis.tools.ui_automation import UiElementCatalog
from jarvis.tools.window_catalog import WindowCatalog


class ClickUiElementTool(Tool):
    """
    Click one named UI Automation element.

    SECURITY MODEL

    The AI supplies:

        window name
        visible element name
        optional control type

    It does NOT supply:

        X coordinate
        Y coordinate
        native window handle
        native UI Automation locator

    JARVIS resolves all of those through trusted code.
    """

    name = "click_ui_element"

    description = (
        "Click one named visible UI control inside a specific "
        "open Windows application window. JARVIS resolves the "
        "actual UI Automation element; the model cannot provide "
        "screen coordinates. Use list_ui_elements first when "
        "the exact control name or type is unknown."
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
                    "Hyperlink. Use it when names are ambiguous."
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

        window = self.window_catalog.resolve(
            raw_window
        )

        # -------------------------------------------------
        # CRITICAL SELF-PROTECTION
        #
        # JARVIS must not use its own automation tools to
        # manipulate:
        #
        #     Permissions
        #     approval dialogs
        #     settings
        #
        # Human security decisions stay human-controlled.
        # -------------------------------------------------

        if (
            "jarvis"
            in window.title.casefold()
        ):
            raise ValueError(
                "JARVIS cannot automate its own application UI."
            )

        element = self.ui_catalog.resolve(
            window_handle=window.handle,
            requested_name=raw_element,
            requested_control_type=raw_control_type,
        )

        if not element.enabled:
            raise ValueError(
                "The selected UI element is disabled."
            )

        # Focus the trusted target window first.
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