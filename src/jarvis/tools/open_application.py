import os
from collections.abc import Mapping
from typing import ClassVar

from jarvis.security.capabilities import Capability
from jarvis.tools.application_catalog import ApplicationCatalog
from jarvis.tools.base import Tool


class OpenApplicationTool(Tool):
    """
    Open an installed Windows application safely.

    SECURITY MODEL

    The model supplies only a friendly application name.

    The model cannot supply:

        executable paths
        shortcut paths
        command-line arguments
        shell commands

    ApplicationCatalog resolves the friendly name to a trusted
    Windows executable or Start Menu shortcut.
    """

    name = "open_application"

    description = (
        "Open an installed Windows application by friendly "
        "name. Examples include Notepad, Calculator, File "
        "Explorer, Google Chrome, Visual Studio Code, Discord, "
        "Telegram, or other applications discovered from the "
        "Windows Start Menu. Command interpreters such as CMD, "
        "PowerShell, Windows Terminal, and WSL are intentionally "
        "blocked. Use list_applications if the correct installed "
        "application name is unknown."
    )

    required_capability = Capability.OPEN_APPLICATION

    parameters_schema: ClassVar[
        dict[
            str,
            object,
        ]
    ] = {
        "type": "object",
        "properties": {
            "application": {
                "type": "string",
                "description": (
                    "Friendly installed application name. "
                    "Examples: 'notepad', 'chrome', "
                    "'VS Code', 'Discord', or 'Telegram'."
                ),
            },
        },
        "required": [
            "application",
        ],
        "additionalProperties": False,
    }

    def __init__(
        self,
        catalog: ApplicationCatalog | None = None,
    ) -> None:
        self.catalog = (
            catalog
            if catalog is not None
            else ApplicationCatalog()
        )

    def execute(
        self,
        arguments: Mapping[str, object],
    ) -> object:
        """
        Open exactly one catalog-approved application.
        """

        raw_application = arguments.get(
            "application"
        )

        if not isinstance(
            raw_application,
            str,
        ):
            raise TypeError(
                "'application' must be a string."
            )

        entry = self.catalog.resolve(
            raw_application
        )

        try:
            # os.startfile asks Windows to launch the trusted
            # executable or Start Menu shortcut.
            #
            # The path comes entirely from ApplicationCatalog,
            # never from model input.
            os.startfile(  # type: ignore[attr-defined]
                str(
                    entry.launch_path
                )
            )

        except OSError as exc:
            raise OSError(
                f"Could not open {entry.name}."
            ) from exc

        return {
            "ok": True,
            "action": "application_opened",
            "application": entry.name,
            "source": entry.source,
        }