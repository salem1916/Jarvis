"""Track the user's active app without capturing images or changing focus."""

import os

import win32gui
import win32process


def is_jarvis_window(handle: int, title: str = "") -> bool:
    if not win32gui.IsWindow(handle):
        return title.strip().casefold().startswith("jarvis")
    try:
        process = win32process.GetWindowThreadProcessId(handle)[1]
        return process == os.getpid() if process else title.strip().casefold().startswith("jarvis")
    except Exception:  # noqa: BLE001 - a stale Windows handle must not break context tracking
        return title.strip().casefold().startswith("jarvis")


class DesktopContext:
    def __init__(self):
        self.last_app = 0

    def current_window(self) -> int:
        current = win32gui.GetForegroundWindow()
        if self._usable(current):
            self.last_app = current
        if self._usable(self.last_app):
            return self.last_app
        found = []
        def visit(handle, _extra):
            if self._usable(handle):
                found.append(handle)
            return True
        win32gui.EnumWindows(visit, None)
        self.last_app = found[0] if found else 0
        return self.last_app

    @staticmethod
    def _usable(handle):
        if not handle or not win32gui.IsWindow(handle) or not win32gui.IsWindowVisible(handle) or win32gui.IsIconic(handle):
            return False
        title = win32gui.GetWindowText(handle).strip()
        return bool(title and title not in {"Program Manager", "Windows Input Experience"} and not is_jarvis_window(handle, title))
