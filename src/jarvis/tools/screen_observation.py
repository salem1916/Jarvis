"""Explicitly enabled, in-memory observation of one visible Windows window."""

import base64
import ctypes
from collections.abc import Mapping
from contextlib import contextmanager
from contextvars import ContextVar
from ctypes import wintypes
from typing import ClassVar

import win32api
import win32con
import win32gui
import win32ui
from PySide6.QtCore import QBuffer, QByteArray, QIODevice, Qt
from PySide6.QtGui import QImage, QImageWriter

from jarvis.security.capabilities import Capability
from jarvis.tools.base import Tool
from jarvis.tools.desktop_context import DesktopContext, is_jarvis_window

_capture_owner: ContextVar[object | None] = ContextVar("jarvis_capture_owner", default=None)


def encode_image(image: QImage) -> str:
    if image.width() > 1440 or image.height() > 1000:
        image = image.scaled(1440, 1000, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation)
    data = QByteArray()
    buffer = QBuffer(data)
    buffer.open(QIODevice.OpenModeFlag.WriteOnly)
    writer = QImageWriter(buffer, QByteArray(b"PNG"))
    if not writer.write(image):
        raise ValueError("The shared-window image could not be encoded.")
    return base64.b64encode(data.data()).decode("ascii")


def capture_window(handle: int) -> str:
    if win32gui.IsIconic(handle) or not win32gui.IsWindowVisible(handle):
        raise ValueError("The shared window is minimized or hidden. Restore it before observing.")
    left, top, right, bottom = win32gui.GetWindowRect(handle)
    return capture_region((left, top, right, bottom), handle)


def capture_desktop() -> str:
    monitor = win32api.MonitorFromWindow(win32gui.GetForegroundWindow(), 2)
    return capture_region(win32api.GetMonitorInfo(monitor)["Monitor"])


def capture_region(rect, handle=0) -> str:
    left, top, right, bottom = rect
    width, height = right - left, bottom - top
    if not 1 <= width <= 12000 or not 1 <= height <= 12000 or width * height > 40_000_000:
        raise ValueError("The selected window has unsupported screen dimensions.")
    screen = win32gui.GetDC(0)
    source = win32ui.CreateDCFromHandle(screen)
    target = source.CreateCompatibleDC()
    bitmap = win32ui.CreateBitmap()
    try:
        bitmap.CreateCompatibleBitmap(source, width, height)
        target.SelectObject(bitmap)
        if not handle or win32gui.GetForegroundWindow() == handle:
            target.BitBlt((0, 0), (width, height), source, (left, top), win32con.SRCCOPY)
        else:
            # Approval controls can cover the shared app. Capture that app's own
            # rendered window instead of pixels from the approval window.
            print_window = ctypes.windll.user32.PrintWindow
            print_window.argtypes = (wintypes.HWND, wintypes.HDC, wintypes.UINT)
            print_window.restype = wintypes.BOOL
            if not print_window(handle, target.GetSafeHdc(), 2):
                raise ValueError("Windows could not render the shared window. Bring it to the front and retry.")
        raw = bitmap.GetBitmapBits(True)
        image = QImage(raw, width, height, width * 4, QImage.Format.Format_RGB32).copy()
        return encode_image(image)
    finally:
        win32gui.DeleteObject(bitmap.GetHandle())
        target.DeleteDC()
        source.DeleteDC()
        win32gui.ReleaseDC(0, screen)


class ScreenObservationTool(Tool):
    internal_only = True
    name = "observe_screen"
    description = "Observe the selected, visible foreground window as an image. Only available after the user enables screen mode."
    required_capability = Capability.INSPECT_UI
    parameters_schema: ClassVar[dict[str, object]] = {"type": "object", "properties": {
        "scope": {"type": "string", "enum": ["active_app", "desktop"]}}, "additionalProperties": False}

    def __init__(self, capture=None):
        self.enabled = False
        self.window_handle = 0
        self.follow_active = False
        self.context = DesktopContext()
        self.capture = capture or capture_window

    def execute(self, arguments: Mapping[str, object]) -> object:
        if not self.enabled:
            raise PermissionError("Screen mode is off. Enable Share a window in Chat before screen observation.")
        if _capture_owner.get() is not self:
            raise PermissionError("Screen images are only available to the trusted screen workflow, never ordinary text tools.")
        handle = self.resolve_window()
        if arguments.get("scope") == "desktop" or not handle:
            return {"ok": True, "window": "Current display", "image": capture_desktop()}
        if not win32gui.IsWindow(handle):
            raise ValueError("The app window closed. Bring the app you want to use forward and retry.")
        title = win32gui.GetWindowText(handle)
        if is_jarvis_window(handle, title):
            raise ValueError("Choose the app you want to work in, rather than Jarvis itself.")
        return {"ok": True, "window": title, "image": self.capture(handle)}

    def resolve_window(self):
        if self.follow_active:
            self.window_handle = self.context.current_window()
        return self.window_handle

    @contextmanager
    def capture_scope(self):
        token = _capture_owner.set(self)
        try:
            yield
        finally:
            _capture_owner.reset(token)
