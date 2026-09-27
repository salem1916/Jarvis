from collections.abc import Mapping
from typing import ClassVar

from jarvis.security.capabilities import Capability
from jarvis.tools.application_catalog import ApplicationCatalog
from jarvis.tools.base import Tool


class ListApplicationsTool(Tool):
    """
    List application names JARVIS can safely open.

    This is read-only discovery.

    It returns names only rather than executable paths.
    """

    name = "list_applications"

    description = (
        "List installed Windows applications that JARVIS can "
        "safely open. Use this when the user asks what apps are "
        "available or when the exact application name is unknown."
    )

    required_capability = Capability.READ_SYSTEM_INFO

    parameters_schema: ClassVar[
        dict[
            str,
            object,
        ]
    ] = {
        "type": "object",
        "properties": {},
        "additionalProperties": False,
    }

    def __init__(
        self,
        catalog: ApplicationCatalog,
    ) -> None:
        self.catalog = catalog

    def execute(
        self,
        arguments: Mapping[str, object],
    ) -> object:
        """
        Return discovered application names.
        """

        if arguments:
            raise ValueError(
                "list_applications does not accept arguments."
            )

        return list(
            self.catalog.names()
        )