import os
from dataclasses import dataclass
from pathlib import Path
from typing import ClassVar


def _normalize_application_name(
    value: str,
) -> str:
    """
    Produce a deterministic application-name representation.

    Examples:

        "Google   Chrome" -> "google chrome"
        "VS CODE"         -> "vs code"
    """

    return " ".join(
        value
        .strip()
        .casefold()
        .split()
    )


@dataclass(
    frozen=True,
    slots=True,
)
class ApplicationEntry:
    """
    One trusted application JARVIS may launch.

    launch_path is discovered by trusted JARVIS code.

    The AI model never supplies this path.
    """

    name: str
    launch_path: Path
    source: str


class ApplicationCatalog:
    """
    Discover applications from trusted Windows locations.

    Sources:

        Windows built-in executables
        Current-user Start Menu
        System-wide Start Menu

    JARVIS exposes friendly application names to the model.

    The model never chooses an executable or shortcut path.
    """

    # -------------------------------------------------
    # Friendly aliases.
    #
    # ClassVar tells Ruff/Pyright that this is intentional
    # shared class-level configuration rather than a mutable
    # dataclass-style instance default.
    # -------------------------------------------------

    _ALIASES: ClassVar[
        dict[
            str,
            str,
        ]
    ] = {
        "calc": "calculator",
        "explorer": "file explorer",
        "vscode": "visual studio code",
        "vs code": "visual studio code",
    }

    # -------------------------------------------------
    # Command interpreters are deliberately excluded from
    # OPEN_APPLICATION.
    #
    # They belong to the future RUN_COMMAND capability,
    # where commands and arguments receive stricter policy.
    #
    # frozenset is used because this is security-sensitive
    # configuration that should not be mutated accidentally.
    # -------------------------------------------------

    _BLOCKED_APPLICATION_NAMES: ClassVar[
        frozenset[str]
    ] = frozenset(
        {
            "cmd",
            "cmd.exe",
            "command prompt",
            "powershell",
            "powershell.exe",
            "windows powershell",
            "powershell ise",
            "windows powershell ise",
            "pwsh",
            "pwsh.exe",
            "terminal",
            "windows terminal",
            "wsl",
            "wsl.exe",
            "git bash",
            "bash",
        }
    )

    def __init__(
        self,
        windows_root: Path | None = None,
        start_menu_roots: tuple[
            Path,
            ...,
        ] | None = None,
    ) -> None:
        """
        Build a Windows application catalog.

        Tests may inject fake Windows and Start Menu folders.
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

        if start_menu_roots is None:
            discovered_roots: list[
                Path
            ] = []

            appdata = os.environ.get(
                "APPDATA"
            )

            if appdata:
                discovered_roots.append(
                    Path(
                        appdata
                    )
                    / "Microsoft"
                    / "Windows"
                    / "Start Menu"
                    / "Programs"
                )

            programdata = os.environ.get(
                "PROGRAMDATA"
            )

            if programdata:
                discovered_roots.append(
                    Path(
                        programdata
                    )
                    / "Microsoft"
                    / "Windows"
                    / "Start Menu"
                    / "Programs"
                )

            start_menu_roots = tuple(
                discovered_roots
            )

        self.start_menu_roots = tuple(
            root
            .expanduser()
            .resolve()
            for root in start_menu_roots
        )

    def entries(
        self,
    ) -> tuple[
        ApplicationEntry,
        ...,
    ]:
        """
        Return the currently discoverable application catalog.

        The catalog is rebuilt on demand so newly installed
        applications can appear without restarting JARVIS.
        """

        discovered: dict[
            str,
            ApplicationEntry,
        ] = {}

        self._add_builtin_applications(
            discovered
        )

        for root in self.start_menu_roots:
            if not root.is_dir():
                continue

            shortcuts = sorted(
                root.rglob(
                    "*.lnk"
                ),
                key=lambda path: str(
                    path
                ).casefold(),
            )

            for shortcut in shortcuts:
                if not shortcut.is_file():
                    continue

                name = shortcut.stem.strip()

                normalized_name = (
                    _normalize_application_name(
                        name
                    )
                )

                if not normalized_name:
                    continue

                if (
                    normalized_name
                    in self._BLOCKED_APPLICATION_NAMES
                ):
                    continue

                # If the same application exists in more than
                # one Start Menu root, retain the first
                # deterministic match.
                discovered.setdefault(
                    normalized_name,
                    ApplicationEntry(
                        name=name,
                        launch_path=shortcut.resolve(),
                        source="start_menu",
                    ),
                )

        return tuple(
            sorted(
                discovered.values(),
                key=lambda entry:
                    entry.name.casefold(),
            )
        )

    def names(
        self,
    ) -> tuple[
        str,
        ...,
    ]:
        """
        Return human-readable application names.
        """

        return tuple(
            entry.name
            for entry in self.entries()
        )

    def resolve(
        self,
        requested_name: str,
    ) -> ApplicationEntry:
        """
        Resolve a human application name safely.

        Resolution order:

            explicit blocked-name check
            alias expansion
            exact match
            unique partial match

        Ambiguous requests are rejected instead of guessing.
        """

        normalized = _normalize_application_name(
            requested_name
        )

        if not normalized:
            raise ValueError(
                "Application name cannot be empty."
            )

        if (
            normalized
            in self._BLOCKED_APPLICATION_NAMES
        ):
            raise ValueError(
                "This application is intentionally blocked "
                "from OPEN_APPLICATION because it is a command "
                "interpreter. Command execution belongs to the "
                "separate RUN_COMMAND capability."
            )

        normalized = self._ALIASES.get(
            normalized,
            normalized,
        )

        entries = self.entries()

        # -------------------------------------------------
        # Exact match first.
        # -------------------------------------------------

        for entry in entries:
            if (
                _normalize_application_name(
                    entry.name
                )
                == normalized
            ):
                return entry

        # -------------------------------------------------
        # Then a unique partial match.
        #
        # "chrome" can therefore resolve to "Google Chrome".
        # -------------------------------------------------

        matches = [
            entry
            for entry in entries
            if normalized
            in _normalize_application_name(
                entry.name
            )
        ]

        if len(
            matches
        ) == 1:
            return matches[0]

        if len(
            matches
        ) > 1:
            match_names = ", ".join(
                entry.name
                for entry in matches[:10]
            )

            raise ValueError(
                "Application name is ambiguous. "
                f"Matches: {match_names}."
            )

        raise ValueError(
            "No installed application matched "
            f"'{requested_name}'. "
            "Use list_applications to discover the "
            "application names JARVIS can safely open."
        )

    def _add_builtin_applications(
        self,
        discovered: dict[
            str,
            ApplicationEntry,
        ],
    ) -> None:
        """
        Add deterministic Windows built-in applications.
        """

        builtins = (
            (
                "Notepad",
                self.windows_root
                / "System32"
                / "notepad.exe",
            ),
            (
                "Calculator",
                self.windows_root
                / "System32"
                / "calc.exe",
            ),
            (
                "File Explorer",
                self.windows_root
                / "explorer.exe",
            ),
        )

        for name, path in builtins:
            resolved_path = path.resolve()

            if not resolved_path.is_file():
                continue

            normalized_name = (
                _normalize_application_name(
                    name
                )
            )

            discovered[
                normalized_name
            ] = ApplicationEntry(
                name=name,
                launch_path=resolved_path,
                source="windows_builtin",
            )