from dataclasses import dataclass
from typing import Protocol

import win32con
import win32gui


def _normalize_window_title(
    value: str,
) -> str:
    """
    Normalize a window title for deterministic matching.
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
class WindowEntry:
    """
    One visible top-level Windows window.

    The native handle is discovered by trusted JARVIS code.

    The AI model never invents or supplies native handles.
    """

    handle: int
    title: str


class WindowBackend(Protocol):
    """
    Platform interface used by JARVIS window tools.

    Tests can provide a fake implementation.

    The real application uses Win32WindowBackend.
    """

    def list_windows(
        self,
    ) -> tuple[WindowEntry, ...]:
        ...

    def focus(
        self,
        handle: int,
    ) -> None:
        ...

    def minimize(
        self,
        handle: int,
    ) -> None:
        ...

    def maximize(
        self,
        handle: int,
    ) -> None:
        ...

    def restore(
        self,
        handle: int,
    ) -> None:
        ...


class Win32WindowBackend:
    """
    Real Windows implementation.

    Only top-level visible windows with non-empty titles are
    exposed to JARVIS.
    """

    def list_windows(
        self,
    ) -> tuple[WindowEntry, ...]:
        windows: list[
            WindowEntry
        ] = []

        def enum_callback(
            handle: int,
            extra: object,
        ) -> bool:
            del extra

            if not win32gui.IsWindowVisible(
                handle
            ):
                return True

            title = win32gui.GetWindowText(
                handle
            ).strip()

            if not title:
                return True

            windows.append(
                WindowEntry(
                    handle=handle,
                    title=title,
                )
            )

            return True

        win32gui.EnumWindows(
            enum_callback,
            None,
        )

        return tuple(
            sorted(
                windows,
                key=lambda entry:
                    (
                        entry.title.casefold(),
                        entry.handle,
                    ),
            )
        )

    def focus(
        self,
        handle: int,
    ) -> None:
        """
        Restore if minimized, then bring the window forward.
        """

        self._require_valid_window(
            handle
        )

        if win32gui.IsIconic(
            handle
        ):
            win32gui.ShowWindow(
                handle,
                win32con.SW_RESTORE,
            )

        win32gui.BringWindowToTop(
            handle
        )

        win32gui.SetForegroundWindow(
            handle
        )

    def minimize(
        self,
        handle: int,
    ) -> None:
        self._require_valid_window(
            handle
        )

        win32gui.ShowWindow(
            handle,
            win32con.SW_MINIMIZE,
        )

    def maximize(
        self,
        handle: int,
    ) -> None:
        self._require_valid_window(
            handle
        )

        win32gui.ShowWindow(
            handle,
            win32con.SW_MAXIMIZE,
        )

    def restore(
        self,
        handle: int,
    ) -> None:
        self._require_valid_window(
            handle
        )

        win32gui.ShowWindow(
            handle,
            win32con.SW_RESTORE,
        )

    @staticmethod
    def _require_valid_window(
        handle: int,
    ) -> None:
        """
        Reject stale or invalid native window handles.
        """

        if not win32gui.IsWindow(
            handle
        ):
            raise ValueError(
                "The selected window no longer exists."
            )


class WindowCatalog:
    """
    Trusted discovery/resolution layer for open windows.

    The model provides a human-friendly title such as:

        "Discord"
        "Visual Studio Code"
        "Chrome"

    JARVIS resolves it against actual visible windows.

    Ambiguous matches are rejected rather than guessed.
    """

    def __init__(
        self,
        backend: WindowBackend,
    ) -> None:
        self.backend = backend

    def entries(
        self,
    ) -> tuple[WindowEntry, ...]:
        """
        Return current visible top-level windows.
        """

        return self.backend.list_windows()

    def titles(
        self,
    ) -> tuple[str, ...]:
        """
        Return current human-readable window titles.
        """

        return tuple(
            entry.title
            for entry in self.entries()
        )

    def resolve(
        self,
        requested_title: str,
    ) -> WindowEntry:
        """
        Resolve a title safely.

        Resolution:

            exact title match
                ↓
            unique partial match
                ↓
            reject ambiguity / missing window
        """

        normalized = _normalize_window_title(
            requested_title
        )

        if not normalized:
            raise ValueError(
                "Window title cannot be empty."
            )

        entries = self.entries()

        # -------------------------------------------------
        # Exact match
        # -------------------------------------------------

        exact_matches = [
            entry
            for entry in entries
            if (
                _normalize_window_title(
                    entry.title
                )
                == normalized
            )
        ]

        if len(
            exact_matches
        ) == 1:
            return exact_matches[0]

        # -------------------------------------------------
        # Unique partial match
        #
        # Example:
        #
        #     "Discord"
        #
        # can resolve:
        #
        #     "Discord"
        #
        # while:
        #
        #     "Chrome"
        #
        # may be ambiguous if many Chrome windows exist.
        # -------------------------------------------------

        partial_matches = [
            entry
            for entry in entries
            if normalized
            in _normalize_window_title(
                entry.title
            )
        ]

        if len(
            partial_matches
        ) == 1:
            return partial_matches[0]

        if len(
            partial_matches
        ) > 1:
            matches = ", ".join(
                entry.title
                for entry in partial_matches[:10]
            )

            raise ValueError(
                "Window title is ambiguous. "
                f"Matches: {matches}."
            )

        raise ValueError(
            "No open window matched "
            f"'{requested_title}'. "
            "Use list_open_windows to discover the "
            "currently available windows."
        )