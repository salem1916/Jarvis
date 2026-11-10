"""Navigate an already selected Chrome tab through its verified address bar."""
import re
import time
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass
from urllib.parse import urlsplit

import comtypes
import pywintypes
import win32con
import win32gui
from pywinauto import Desktop
from pywinauto.uia_defines import IUIA

from jarvis.core.browser_navigation import browser_executable
from jarvis.core.request_control import check_cancelled
from jarvis.security.capabilities import Capability
from jarvis.tools.base import Tool
from jarvis.tools.desktop_context import DesktopContext, is_jarvis_window


@contextmanager
def _automation():
    initialized = False
    try:
        try:
            comtypes.CoInitializeEx(comtypes.COINIT_MULTITHREADED)
            initialized = True
        except OSError as error:
            if getattr(error, "winerror", None) != -2147417850:
                raise
        yield
    finally:
        if initialized:
            comtypes.CoUninitialize()


@dataclass(frozen=True)
class ChromeTab:
    window: int
    tab_id: tuple[int, ...]


@dataclass(frozen=True)
class ChromePage:
    tab: ChromeTab
    url: str


def _web_url(value):
    try:
        url = urlsplit(value or "")
        if (url.scheme in {"http", "https"} and url.hostname and url.username is None and url.password is None
                and not any(ord(char) < 32 for char in value)):
            return value
    except ValueError:
        pass
    return ""


def _url_key(value):
    url = urlsplit(value)
    return (url.scheme, url.netloc.casefold(), url.path or "/", url.query, url.fragment)


class ChromeTabNavigation:
    def __init__(self, windows, keyboard, text):
        self.windows, self.keyboard, self.text = windows, keyboard, text
        self.expected: ContextVar[ChromeTab | ChromePage | None] = ContextVar("jarvis_expected_chrome_tab", default=None)
        self._foreground = 0
        self._previous_app = 0

    def track_foreground(self):
        foreground = win32gui.GetForegroundWindow()
        if foreground != self._foreground:
            self._foreground = foreground
            if DesktopContext._usable(foreground):
                self._previous_app = foreground
        return foreground

    def _candidate_window(self):
        foreground = self.track_foreground()
        if DesktopContext._usable(foreground):
            return foreground
        if is_jarvis_window(foreground):
            if DesktopContext._usable(self._previous_app) and browser_executable(self._previous_app) == "chrome.exe":
                return self._previous_app
            candidates = []
            def visit(handle, _):
                if DesktopContext._usable(handle) and browser_executable(handle) == "chrome.exe":
                    candidates.append(handle)
                return True
            win32gui.EnumWindows(visit, None)
            if len(candidates) == 1:
                return candidates[0]
        return 0

    def selected(self):
        check_cancelled()
        handle = self._candidate_window()
        if not handle or browser_executable(handle) != "chrome.exe":
            raise ValueError("Switch to your regular Chrome tab, then return to Jarvis and try again.")
        try:
            with _automation():
                root = Desktop(backend="uia").window(handle=handle).wrapper_object()
                toolbars = root.descendants(control_type="ToolBar", class_name="ToolbarView", depth=8)
                avatars = [child.element_info for toolbar in toolbars for child in toolbar.children()
                           if child.element_info.class_name == "AvatarToolbarButton"]
                profile_suffix = root.element_info.name.removeprefix(win32gui.GetWindowText(handle))
                profile_labels = " ".join([profile_suffix, *(avatar.name for avatar in avatars)])
                if re.search(r"\b(?:incognito|inkognito|inprivate|guest|gast|privado|privada|privée|privato|gizli)\b",
                             profile_labels, re.IGNORECASE):
                    raise ValueError("Switch to a regular Chrome tab. Jarvis skips Incognito and Guest windows.")
                tabs = root.descendants(control_type="TabItem", class_name="Tab", depth=10)
                selected = [tuple(tab.element_info.element.GetRuntimeId()) for tab in tabs
                            if tab.element_info.automation_id == "view_20" and tab.iface_selection_item.CurrentIsSelected]
                if len(selected) == 1 and len(avatars) == 1:
                    return ChromeTab(handle, selected[0])
        except (OSError, AttributeError, RuntimeError, comtypes.COMError):
            pass
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

    @staticmethod
    def _document(tab):
        root = Desktop(backend="uia").window(handle=tab.window).wrapper_object()
        for document in root.descendants(control_type="Document", depth=12):
            if document.is_visible():
                return document
        return None

    def current_page(self):
        tab = self.selected()
        with _automation():
            try:
                document = self._document(tab)
                url = _web_url(document.iface_value.CurrentValue) if document is not None else ""
            except (OSError, AttributeError, RuntimeError, comtypes.COMError):
                url = ""
        if self.selected() != tab:
            raise ValueError("The selected Chrome tab changed. Select it again and retry.")
        return ChromePage(tab, url)

    def _focus(self, page):
        tab = page.tab
        expected = self.expected.get()
        if expected is not None and expected not in (tab, page):
            raise ValueError("The selected Chrome tab or page changed while I was working. Return to it and try again.")
        if win32gui.GetForegroundWindow() == tab.window:
            return
        # Worker threads need a Windows message queue before they can transfer focus.
        win32gui.PeekMessage(None, 0, 0, win32con.PM_NOREMOVE)
        try:
            self.windows.focus(tab.window)
        except pywintypes.error as error:
            raise ValueError("Windows couldn't focus Chrome. Switch to the regular Chrome tab and try again.") from error
        if self.current_page() != page or win32gui.GetForegroundWindow() != tab.window:
            raise ValueError("The selected Chrome tab changed. I stopped before sending the URL.")

    def _wait_for_page(self, before, requested=""):
        deadline = time.monotonic() + 5
        while time.monotonic() < deadline:
            check_cancelled()
            page = self.current_page()
            if page.tab != before.tab:
                raise ValueError("The selected Chrome tab changed while navigation was in progress.")
            if page.url and (page.url != before.url or requested and _url_key(page.url) == _url_key(requested)):
                return {"ok": True, "url": page.url, "current_tab": True}
            time.sleep(0.08)
        raise ValueError("Chrome received the command, but I couldn't verify that the destination loaded.")

    def navigate(self, url):
        expected = self.expected.get()
        if isinstance(expected, ChromeTab) and self.selected() != expected:
            raise ValueError("The selected Chrome tab changed while I was working. Return to it and try again.")
        page = self.current_page()
        self._focus(page)
        with _automation():
            self.keyboard.perform((win32con.VK_CONTROL, ord("L")))
            self._require_address_bar(page.tab)
            self.text.type_text(url)
            if self.selected() != page.tab:
                raise ValueError("The selected Chrome tab changed before I submitted the URL.")
            self._require_address_bar(page.tab)
            self.keyboard.perform((win32con.VK_RETURN,))
        return self._wait_for_page(page, url)

    def back(self):
        page = self.current_page()
        self._focus(page)
        check_cancelled()
        self.keyboard.perform((win32con.VK_MENU, win32con.VK_LEFT))
        return self._wait_for_page(page)

    def follow(self, index, kind):
        page = self.current_page()
        with _automation():
            document = self._document(page.tab)
            links = []
            if document is not None:
                for link in document.descendants(control_type="Hyperlink", depth=20):
                    check_cancelled()
                    element = link.element_info.element
                    if element.CurrentIsOffscreen or not link.is_enabled():
                        continue
                    if kind == "result" and not _heading_link(link, document):
                        continue
                    try:
                        url = _web_url(link.iface_value.CurrentValue)
                    except (OSError, AttributeError, RuntimeError, comtypes.COMError):
                        continue
                    if url and url not in links:
                        links.append(url)
                        if len(links) == index:
                            break
        if len(links) < index:
            raise ValueError("I couldn't verify that numbered link in your Chrome tab. Tell me the link name or URL.")
        with self.keep_tab(page):
            return self.navigate(links[index - 1])


def _heading_link(link, document):
    definitions = IUIA().UIA_dll
    def is_heading(item):
        value = item.element_info.element.GetCurrentPropertyValue(definitions.UIA_HeadingLevelPropertyId)
        return isinstance(value, int) and definitions.HeadingLevel1 <= value <= definitions.HeadingLevel9

    if is_heading(link) or any(is_heading(child) for child in link.descendants(depth=3)):
        return True
    parent = link.parent()
    while parent is not None and parent != document:
        if is_heading(parent):
            return True
        parent = parent.parent()
    return False


class ChromeTabTool(Tool):
    name = "current_chrome_navigation"
    description = "Use Back or follow a visible numbered link in the active regular Chrome tab."
    required_capability = Capability.USE_BROWSER
    internal_only = True

    def __init__(self, navigation):
        self.navigation = navigation

    def execute(self, arguments):
        if arguments.get("action") == "back":
            return self.navigation.back()
        index = arguments.get("link_index")
        kind = arguments.get("link_kind")
        if arguments.get("action") != "follow_link" or type(index) is not int or not 1 <= index <= 5 or kind not in {"result", "link"}:
            raise ValueError("Choose Back or an observed numbered link in Chrome.")
        return self.navigation.follow(index, kind)
