from collections.abc import Mapping
from typing import ClassVar

from jarvis.security.capabilities import Capability
from jarvis.tools.base import Tool
from jarvis.tools.window_catalog import WindowCatalog


class ListOpenWindowsTool(Tool):
    """
    List visible top-level Windows windows.

    This is read-only discovery and does not modify any
    application.
    """

    name = "list_open_windows"

    description = (
        "List the currently visible open Windows application "
        "windows. Use this when the user asks what is open, "
        "or before controlling a window when its exact title "
        "is unknown."
    )

    required_capability = Capability.READ_SYSTEM_INFO

    parameters_schema: ClassVar[
        dict[str, object]
    ] = {
        "type": "object",
        "properties": {},
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
        if arguments:
            raise ValueError(
                "list_open_windows does not accept arguments."
            )

        return list(
            self.catalog.titles()
        )