"""Resolve explicit same-tab website requests without a model or topic rules."""
import re
from pathlib import PureWindowsPath
from urllib.parse import urlsplit

import win32api
import win32con
import win32process


def same_tab_url(prompt, router):
    match = re.fullmatch(
        r"(.+?)\s+(?:in (?:it|there|this (?:tab|browser)|the (?:same|current) (?:tab|browser))|without (?:opening )?a new tab)[.!?]*",
        prompt.strip(),re.IGNORECASE)
    if not match:return ""
    request = router.route(match[1])
    if request is None or request.tool_name != "open_url":return ""
    url = str(request.arguments.get("url",""))
    try:parsed = urlsplit(url)
    except ValueError:return ""
    if parsed.scheme not in {"https","http"} or not parsed.hostname or parsed.username or parsed.password:
        return ""
    return url


def is_browser_window(handle):
    return browser_executable(handle) in {"chrome.exe","msedge.exe","firefox.exe","brave.exe","opera.exe","vivaldi.exe"}


def browser_executable(handle):
    process = None
    try:
        pid = win32process.GetWindowThreadProcessId(handle)[1]
        process = win32api.OpenProcess(win32con.PROCESS_QUERY_INFORMATION | win32con.PROCESS_VM_READ,False,pid)
        return PureWindowsPath(win32process.GetModuleFileNameEx(process,0)).name.casefold()
    except Exception:  # noqa: BLE001 -- do not type into an unverified app
        return ""
    finally:
        if process is not None:win32api.CloseHandle(process)
