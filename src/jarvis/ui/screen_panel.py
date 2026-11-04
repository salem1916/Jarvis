"""One explicit screen-access switch; follow the active app without an app picker."""

from PySide6.QtCore import QTimer, Signal
from PySide6.QtWidgets import QCheckBox, QLabel, QVBoxLayout, QWidget


class ScreenPanel(QWidget):
    changed = Signal()

    def __init__(self, jarvis, parent=None):
        super().__init__(parent)
        self.jarvis = jarvis
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        self.enabled = QCheckBox("Allow Jarvis to see my screen")
        layout.addWidget(self.enabled)
        self.notice = QLabel()
        self.notice.setWordWrap(True)
        self.notice.setObjectName("mutedText")
        layout.addWidget(self.notice)
        self.timer = QTimer(self)
        self.timer.setInterval(300)
        self.timer.timeout.connect(self._track)
        self.enabled.toggled.connect(self._change)
        self._update_notice()

    def _change(self):
        enabled = self.enabled.isChecked()
        self.jarvis.screen_control_enabled = enabled
        screen = self.jarvis.tool_service.registry.get("observe_screen")
        screen.enabled = enabled
        screen.follow_active = enabled
        if enabled:
            self.timer.start()
            self._track()
        else:
            self.timer.stop()
            screen.window_handle = 0
        self._update_notice()
        self.changed.emit()

    def _track(self):
        screen = self.jarvis.tool_service.registry.get("observe_screen")
        if screen.enabled:
            screen.resolve_window()

    def _update_notice(self):
        self.notice.setText("Screen access on · follows your active app. Screenshots go to the selected AI only when needed. Uncheck to stop."
                            if self.enabled.isChecked() else "Screen access off · local opening and searching still work. Enable this to let Jarvis inspect the active app or display.")
