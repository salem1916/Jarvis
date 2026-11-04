import time
from contextlib import suppress
from dataclasses import dataclass
from typing import Protocol

import pywintypes
import win32api
import win32con
import win32gui
import win32process


def _normalize_window_title(
    value: str,
) -> str:
    """
    Normalize a window title for deterministic matching.
    """

    return " ".join(
        value.strip().casefold().split()
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
        windows: list[WindowEntry] = []

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
                key=lambda entry: (
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

        if win32gui.GetForegroundWindow() == handle:
            return
        try:
            win32gui.BringWindowToTop(handle)
            win32gui.SetForegroundWindow(handle)
            self._wait_for_focus(handle)
        except pywintypes.error:
            pass
        if win32gui.GetForegroundWindow() != handle:
            # Hands-free operation can leave the browser owning foreground
            # input. Temporarily join its input queue for this requested focus
            # operation; always detach and never send guessed keys.
            foreground = win32gui.GetForegroundWindow()
            foreground_thread = win32process.GetWindowThreadProcessId(foreground)[0]
            current_thread = win32api.GetCurrentThreadId()
            attached = current_thread != foreground_thread
            try:
                if attached:
                    win32process.AttachThreadInput(current_thread, foreground_thread, True)
                win32gui.BringWindowToTop(handle)
                win32gui.SetForegroundWindow(handle)
                self._wait_for_focus(handle)
            finally:
                if attached:
                    with suppress(pywintypes.error):
                        win32process.AttachThreadInput(current_thread, foreground_thread, False)
        if win32gui.GetForegroundWindow() != handle:
            raise ValueError("Windows did not focus the requested app. No keyboard or mouse input was sent.")

    @staticmethod
    def _wait_for_focus(handle: int) -> None:
        # Foreground activation is asynchronous across Windows input queues.
        # A successful API return is not yet proof that keystrokes have a target.
        from jarvis.core.request_control import check_cancelled
        deadline = time.monotonic() + 0.4
        while win32gui.GetForegroundWindow() != handle and time.monotonic() < deadline:
            check_cancelled()
            time.sleep(0.01)

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

    Normal application tools use resolve(), which requires one
    unambiguous window.

    Structured UI Automation may use matching_entries(), because
    duplicate top-level Windows windows can legitimately have the
    same human-visible title.

    UI tools must perform additional deterministic resolution
    before taking a side effect.
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

    def matching_entries(
        self,
        requested_title: str,
    ) -> tuple[WindowEntry, ...]:
        """
        Return all deterministic matches for a title.

        Matching order:

            exact matches, if any
                ↓
            partial matches, if no exact matches exist
                ↓
            missing-window error

        Unlike resolve(), this method intentionally does NOT
        reject multiple matches.

        This is useful for trusted higher-level resolvers such
        as UI Automation, which can safely distinguish duplicate
        title windows using actual controls inside each window.
        """

        normalized = _normalize_window_title(
            requested_title
        )

        if not normalized:
            raise ValueError(
                "Window title cannot be empty."
            )

        entries = self.entries()

        exact_matches = tuple(
            entry
            for entry in entries
            if (
                _normalize_window_title(
                    entry.title
                )
                == normalized
            )
        )

        if exact_matches:
            return exact_matches

        partial_matches = tuple(
            entry
            for entry in entries
            if normalized
            in _normalize_window_title(
                entry.title
            )
        )

        if partial_matches:
            return partial_matches

        raise ValueError(
            "No open window matched "
            f"'{requested_title}'. "
            "Use list_open_windows to discover the "
            "currently available windows."
        )

    def resolve(
        self,
        requested_title: str,
    ) -> WindowEntry:
        """
        Resolve exactly one window safely.

        Ordinary window-control tools continue to require one
        unambiguous target.

        Duplicate windows are NEVER selected arbitrarily.
        """

        matches = self.matching_entries(
            requested_title
        )

        if len(
            matches
        ) == 1:
            return matches[0]

        titles = ", ".join(
            entry.title
            for entry in matches[:10]
        )

        raise ValueError(
            "Window title is ambiguous. "
            f"Matches: {titles}."
        )
