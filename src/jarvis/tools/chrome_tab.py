"""Navigate an already selected Chrome tab through its verified address bar."""
import re
import time
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass
from urllib.parse import parse_qs, parse_qsl, urlsplit

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

    def same_page(self, other):
        return self.tab == other.tab and _page_key(self.url) == _page_key(other.url)


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


def _is_on_site(url, site):
    host = urlsplit(url).hostname or ""
    return host == site or host.endswith("." + site)


def _page_key(url):
    key = _url_key(url)
    if _is_on_site(url, "youtube.com"):
        # YouTube updates this theme parameter while loading the same page.
        query = tuple(pair for pair in parse_qsl(key[3], keep_blank_values=True) if pair[0] != "themeRefresh")
        return (*key[:3], query, key[4])
    return key


def _video_key(url):
    """Identify a playable URL so thumbnail and title links count once."""
    parsed = urlsplit(url)
    if _is_on_site(url, "youtube.com"):
        if parsed.path == "/watch":
            video_id = parse_qs(parsed.query).get("v", [""])[0]
        else:
            parts = parsed.path.strip("/").split("/")
            video_id = parts[1] if len(parts) == 2 and parts[0] in {"shorts", "live", "embed"} else ""
        return ("youtube", video_id) if video_id else None
    if parsed.hostname == "youtu.be" and re.fullmatch(r"/[\w-]+", parsed.path):
        return ("youtube", parsed.path[1:])
    if _is_on_site(url, "vimeo.com"):
        match = re.fullmatch(r"/(?:video/)?(\d+)/?", parsed.path)
        return ("vimeo", match[1]) if match else None
    if parsed.path.casefold().endswith((".mp4", ".webm", ".m4v", ".mov", ".ogv")):
        return ("file", _url_key(url))
    return None


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
        for attempt in range(3):
            check_cancelled()
            if attempt and self._candidate_window() != handle:
                raise ValueError("The selected Chrome window changed. Select the intended window and try again.")
            try:
                with _automation():
                    tabs = self._regular_tab_items(handle)
                    selected = [tuple(tab.element_info.element.GetRuntimeId()) for tab in tabs
                                if tab.iface_selection_item.CurrentIsSelected]
                    if len(selected) == 1:
                        return ChromeTab(handle, selected[0])
            except (OSError, AttributeError, RuntimeError, comtypes.COMError):
                pass
            if attempt < 2:
                time.sleep(0.1)
        raise ValueError("I couldn't verify the active tab in Chrome. Bring a regular Chrome tab forward and try again.")

    @staticmethod
    def _regular_tab_items(handle):
        root = Desktop(backend="uia").window(handle=handle).wrapper_object()
        toolbars = root.descendants(control_type="ToolBar", class_name="ToolbarView", depth=8)
        avatars = [child.element_info for toolbar in toolbars for child in toolbar.children()
                   if child.element_info.class_name == "AvatarToolbarButton"]
        profile_suffix = root.element_info.name.removeprefix(win32gui.GetWindowText(handle))
        profile_labels = " ".join([profile_suffix, *(avatar.name for avatar in avatars)])
        if re.search(r"\b(?:incognito|inkognito|inprivate|guest|gast|privado|privada|privée|privato|gizli)\b",
                     profile_labels, re.IGNORECASE):
            raise ValueError("Switch to a regular Chrome tab. Jarvis skips Incognito and Guest windows.")
        if len(avatars) != 1:
            return []
        return [tab for tab in root.descendants(control_type="TabItem", class_name="Tab", depth=10)
                if tab.element_info.automation_id == "view_20"]

    def list_tabs(self):
        check_cancelled()
        current = self._candidate_window()
        groups = []
        windows = sorted(self.windows.list_windows(), key=lambda window: window.handle != current)
        with _automation():
            for window in windows:
                check_cancelled()
                if browser_executable(window.handle) != "chrome.exe":
                    continue
                try:
                    tabs = [
                        {"title": " ".join(tab.element_info.name.split())[:240] or "Untitled tab",
                         "selected": bool(tab.iface_selection_item.CurrentIsSelected)}
                        for tab in self._regular_tab_items(window.handle)
                    ]
                except (ValueError, OSError, AttributeError, RuntimeError, comtypes.COMError):
                    continue
                if tabs:
                    groups.append(tabs)
        return {"ok": True, "windows": groups}

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
        expected_changed = (not expected.same_page(page) if isinstance(expected, ChromePage)
                            else expected is not None and expected != tab)
        if expected_changed:
            raise ValueError("The selected Chrome tab or page changed while I was working. Return to it and try again.")
        if win32gui.GetForegroundWindow() == tab.window:
            return
        # Worker threads need a Windows message queue before they can transfer focus.
        win32gui.PeekMessage(None, 0, 0, win32con.PM_NOREMOVE)
        try:
            self.windows.focus(tab.window)
        except pywintypes.error as error:
            raise ValueError("Windows couldn't focus Chrome. Switch to the regular Chrome tab and try again.") from error
        if not page.same_page(self.current_page()) or win32gui.GetForegroundWindow() != tab.window:
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

    def follow(self, index, kind, site=""):
        page = self.current_page()
        if site and not _is_on_site(page.url, site):
            raise ValueError(f"Select a tab on {site} first, then ask for the video again.")
        destination = self._numbered_link(page, index, kind)
        if kind == "video" and not destination:
            # Video cards can arrive just after Chrome reports the page loaded.
            deadline = time.monotonic() + 2
            while not destination and time.monotonic() < deadline:
                check_cancelled()
                time.sleep(0.15)
                current = self.current_page()
                if current.tab != page.tab or current.url and not page.same_page(current):
                    raise ValueError("The selected Chrome tab or page changed while I was looking for the video.")
                if current.url:
                    destination = self._numbered_link(page, index, kind)
        if not destination:
            if kind == "video":
                raise ValueError("I couldn't verify that numbered video in the visible page. Scroll to the videos or give me its URL.")
            raise ValueError("I couldn't verify that numbered link in your Chrome tab. Tell me the link name or URL.")
        with self.keep_tab(page):
            result = self.navigate(destination)
        if kind == "video" and _video_key(result["url"]) != _video_key(destination):
            raise ValueError("Chrome reached a different page before the requested video could be verified.")
        return result

    def _numbered_link(self, page, index, kind):
        found = set()
        with _automation():
            document = self._document(page.tab)
            if document is None:
                return ""
            # Search Chrome's accessibility tree, including deeply nested
            # video cards. Offscreen controls never count toward an ordinal.
            links = document.descendants(control_type="Hyperlink")
            for link in links:
                check_cancelled()
                try:
                    element = link.element_info.element
                    if element.CurrentIsOffscreen or not link.is_enabled():
                        continue
                    if kind == "result" and not _heading_link(link, document):
                        continue
                    url = _web_url(link.iface_value.CurrentValue)
                except (OSError, AttributeError, RuntimeError, comtypes.COMError):
                    continue
                key = _video_key(url) if url and kind == "video" else url
                if key and key not in found:
                    found.add(key)
                    if len(found) == index:
                        return url
        return ""


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
    description = "List open regular Chrome tabs or navigate to a verified visible link or video."
    required_capability = Capability.USE_BROWSER
    internal_only = True

    def __init__(self, navigation):
        self.navigation = navigation

    def execute(self, arguments):
        action = arguments.get("action")
        if action == "list_tabs":
            return self.navigation.list_tabs()
        if action == "back":
            return self.navigation.back()
        index = arguments.get("link_index")
        kind = arguments.get("link_kind")
        if action != "follow_link" or type(index) is not int or not 1 <= index <= 5 or kind not in {"result", "link", "video"}:
            raise ValueError("Choose Back or an observed numbered link or video in Chrome.")
        if kind == "video":
            site = arguments.get("site", "")
            if site not in {"", "youtube.com", "vimeo.com"}:
                raise ValueError("Select the intended video site in Chrome first.")
            return self.navigation.follow(index, kind, site)
        return self.navigation.follow(index, kind)
