"""Navigate an already selected Chrome tab through its verified address bar."""
import re
import time
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass

import comtypes
import pywintypes
import win32con
import win32gui
from pywinauto import Desktop
from pywinauto.uia_defines import IUIA

from jarvis.core.browser_navigation import browser_executable
from jarvis.core.request_control import check_cancelled
from jarvis.tools.desktop_context import DesktopContext, is_jarvis_window


@dataclass(frozen=True)
class ChromeTab:
    window: int
    tab_id: tuple[int, ...]


class ChromeTabNavigation:
    def __init__(self, windows, keyboard, text):
        self.windows, self.keyboard, self.text = windows, keyboard, text
        self.expected: ContextVar[ChromeTab | None] = ContextVar("jarvis_expected_chrome_tab", default=None)

    @staticmethod
    def _candidate_window():
        foreground = win32gui.GetForegroundWindow()
        if DesktopContext._usable(foreground):
            return foreground
        if is_jarvis_window(foreground):
            candidates = []
            win32gui.EnumWindows(lambda handle, _: candidates.append(handle) or True, None)
            return next((handle for handle in candidates if DesktopContext._usable(handle)), 0)
        return 0

    def selected(self):
        check_cancelled()
        handle = self._candidate_window()
        if not handle or browser_executable(handle) != "chrome.exe":
            raise ValueError("Switch to your regular Chrome tab, then return to Jarvis and try again.")
        comtypes.CoInitialize()
        try:
            root = Desktop(backend="uia").window(handle=handle).wrapper_object()
            toolbars = root.descendants(control_type="ToolBar", class_name="ToolbarView", depth=8)
            avatars = [child.element_info for toolbar in toolbars for child in toolbar.children()
                       if child.element_info.class_name == "AvatarToolbarButton"]
            profile_suffix = root.element_info.name.removeprefix(win32gui.GetWindowText(handle))
            profile_labels = " ".join([profile_suffix, *(avatar.name for avatar in avatars)])
            if re.search(r"\b(?:incognito|inkognito|inprivate|guest|gast|privado|privada|privée|privato|gizli)\b",
                         profile_labels, re.I):
                raise ValueError("Switch to a regular Chrome tab. Jarvis skips Incognito and Guest windows.")
            tabs = root.descendants(control_type="TabItem", class_name="Tab", depth=10)
            selected = [tuple(tab.element_info.element.GetRuntimeId()) for tab in tabs
                        if tab.element_info.automation_id == "view_20" and tab.iface_selection_item.CurrentIsSelected]
            if len(selected) == 1 and len(avatars) == 1:
                return ChromeTab(handle, selected[0])
        except (OSError, AttributeError, RuntimeError, comtypes.COMError):
            pass
        finally:
            comtypes.CoUninitialize()
        raise ValueError("I couldn't verify the active tab in Chrome. Bring a regular Chrome tab forward and try again.")

    @contextmanager
    def keep_tab(self, tab):
        token = self.expected.set(tab)
        try:
            yield
        finally:
            self.expected.reset(token)

    @staticmethod
    def _require_address_bar(tab):
        deadline = time.monotonic() + 0.4
        while win32gui.GetForegroundWindow() == tab.window:
            check_cancelled()
            focus = IUIA().iuia.GetFocusedElement()
            if focus.CurrentClassName == "OmniboxViewViews" and focus.CurrentAutomationId == "view_1012":
                return
            if time.monotonic() >= deadline:
                break
            time.sleep(0.015)
        raise ValueError("Chrome's address bar lost focus. I stopped before continuing.")

    def navigate(self, url):
        tab = self.selected()
        expected = self.expected.get()
        if expected is not None and expected != tab:
            raise ValueError("The selected Chrome tab changed while I was working. Return to it and try again.")
        # Worker threads need a Windows message queue before they can transfer focus.
        win32gui.PeekMessage(None, 0, 0, win32con.PM_NOREMOVE)
        try:
            self.windows.focus(tab.window)
        except pywintypes.error as error:
            raise ValueError("Windows couldn't focus Chrome. Switch to the regular Chrome tab and try again.") from error
        if self.selected() != tab or win32gui.GetForegroundWindow() != tab.window:
            raise ValueError("The selected Chrome tab changed. I stopped before sending the URL.")
        comtypes.CoInitialize()
        try:
            self.keyboard.perform((win32con.VK_CONTROL, ord("L")))
            self._require_address_bar(tab)
            self.text.type_text(url)
            self._require_address_bar(tab)
            self.keyboard.perform((win32con.VK_RETURN,))
        finally:
            comtypes.CoUninitialize()
        return {"ok": True, "url": url, "current_tab": True}
