"""Verified Unicode copying, including the actual Windows clipboard."""
import sys
import time


def copy_text(text: str) -> None:
    if not text:
        raise ValueError("There is no response to copy yet.")
    if sys.platform != "win32":
        from PySide6.QtWidgets import QApplication
        QApplication.clipboard().setText(text)
        return
    import pywintypes
    import win32clipboard
    import win32con
    last_error = None
    for _ in range(5):
        try:
            win32clipboard.OpenClipboard()
            try:
                win32clipboard.EmptyClipboard()
                win32clipboard.SetClipboardText(text, win32con.CF_UNICODETEXT)
                if win32clipboard.GetClipboardData(win32con.CF_UNICODETEXT) != text:
                    raise OSError("Windows did not retain the copied text.")
            finally:
                win32clipboard.CloseClipboard()
            return
        except (OSError, pywintypes.error) as error:
            last_error = error
            time.sleep(0.015)
    raise OSError("Windows clipboard is busy. Try Copy again.") from last_error
