import os
import subprocess
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import ClassVar

from jarvis.security.capabilities import Capability
from jarvis.tools.base import Tool


@dataclass(
    frozen=True,
    slots=True,
)
class ApplicationDefinition:
    """
    Trusted definition of one application JARVIS may launch.

    The model provides only a friendly application name.

    It does NOT provide:

        executable paths
        command-line arguments
        shell commands
    """

    name: str
    relative_executable: Path


class OpenApplicationTool(Tool):
    """
    Open a trusted Windows application.

    SECURITY MODEL

    This deliberately does NOT accept an arbitrary executable
    path or command from the AI model.

    Instead:

        model asks for "notepad"
                ↓
        trusted alias lookup
                ↓
        known executable
                ↓
        OPEN_APPLICATION policy
                ↓
        launch

    Arbitrary command execution belongs to RUN_COMMAND,
    which will have a separate and stricter security policy.
    """

    name = "open_application"

    description = (
        "Open a supported Windows application. "
        "Currently supported applications are Notepad, "
        "Calculator, and File Explorer. Use this tool when "
        "the user explicitly asks to open or launch one of "
        "these applications. Do not use shell commands."
    )

    required_capability = Capability.OPEN_APPLICATION

    parameters_schema: ClassVar[dict[str, object]] = {
        "type": "object",
        "properties": {
            "application": {
                "type": "string",
                "description": (
                    "Friendly application name, such as "
                    "'notepad', 'calculator', or "
                    "'file explorer'."
                ),
            },
        },
        "required": [
            "application",
        ],
        "additionalProperties": False,
    }

    _APPLICATIONS: ClassVar[
        dict[str, ApplicationDefinition]
    ] = {
        # -----------------------------
        # Notepad
        # -----------------------------
        "notepad": ApplicationDefinition(
            name="Notepad",
            relative_executable=Path(
                "System32"
            )
            / "notepad.exe",
        ),
        "text editor": ApplicationDefinition(
            name="Notepad",
            relative_executable=Path(
                "System32"
            )
            / "notepad.exe",
        ),

        # -----------------------------
        # Calculator
        # -----------------------------
        "calculator": ApplicationDefinition(
            name="Calculator",
            relative_executable=Path(
                "System32"
            )
            / "calc.exe",
        ),
        "calc": ApplicationDefinition(
            name="Calculator",
            relative_executable=Path(
                "System32"
            )
            / "calc.exe",
        ),

        # -----------------------------
        # File Explorer
        # -----------------------------
        "file explorer": ApplicationDefinition(
            name="File Explorer",
            relative_executable=Path(
                "explorer.exe"
            ),
        ),
        "explorer": ApplicationDefinition(
            name="File Explorer",
            relative_executable=Path(
                "explorer.exe"
            ),
        ),
    }

    def __init__(
        self,
        windows_root: Path | None = None,
    ) -> None:
        """
        Use the real Windows directory by default.

        Tests may inject a temporary fake Windows directory.
        """

        if windows_root is None:
            windows_directory = os.environ.get(
                "WINDIR"
            )

            if windows_directory is None:
                raise RuntimeError(
                    "Windows directory could not be determined."
                )

            windows_root = Path(
                windows_directory
            )

        self.windows_root = (
            windows_root
            .expanduser()
            .resolve()
        )

    def execute(
        self,
        arguments: Mapping[str, object],
    ) -> object:
        """
        Launch exactly one trusted application.
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

        normalized_name = " ".join(
            raw_application
            .strip()
            .casefold()
            .split()
        )

        if not normalized_name:
            raise ValueError(
                "'application' cannot be empty."
            )

        definition = self._APPLICATIONS.get(
            normalized_name
        )

        if definition is None:
            supported = (
                "Notepad, Calculator, File Explorer"
            )

            raise ValueError(
                "Unsupported application. "
                f"Currently supported: {supported}."
            )

        executable = (
            self.windows_root
            / definition.relative_executable
        ).resolve()

        # The executable comes from our trusted internal
        # catalog, not from model-generated input.
        if not executable.is_file():
            raise FileNotFoundError(
                "Application executable was not found: "
                f"{executable}"
            )

        try:
            process = subprocess.Popen(
                [
                    str(
                        executable
                    )
                ],
                shell=False,
            )

        except OSError as exc:
            raise OSError(
                f"Could not open {definition.name}."
            ) from exc

        return {
            "ok": True,
            "action": "application_opened",
            "application": definition.name,
            "executable": str(
                executable
            ),
            "pid": process.pid,
        }
    