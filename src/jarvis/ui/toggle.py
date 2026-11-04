"""An accessible native checkbox presented as a small animated switch."""

from PySide6.QtCore import Property, QPropertyAnimation, QRectF, Qt
from PySide6.QtGui import QColor, QPainter
from PySide6.QtWidgets import QCheckBox


class ToggleSwitch(QCheckBox):
    def __init__(self) -> None:
        super().__init__()
        self.setFixedSize(44, 26)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self._position = 0.0
        self._animation = QPropertyAnimation(self, b"position", self)
        self._animation.setDuration(120)
        self.toggled.connect(self._toggle)

    def _get_position(self) -> float:
        return self._position

    def _set_position(self, value: float) -> None:
        self._position = value
        self.update()

    position = Property(float, _get_position, _set_position)

    def _toggle(self, checked: bool) -> None:
        self._animation.stop()
        if not self.isVisible():
            self._set_position(float(checked))
            return
        self._animation.setStartValue(self._position)
        self._animation.setEndValue(float(checked))
        self._animation.start()

    def hitButton(self, pos) -> bool:
        return self.rect().contains(pos)

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setOpacity(1.0 if self.isEnabled() else 0.45)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor("#1685fb" if self.isChecked() else "#9898a1"))
        painter.drawRoundedRect(QRectF(1, 1, 42, 24), 12, 12)
        painter.setBrush(QColor("white"))
        painter.drawEllipse(QRectF(3 + self._position * 18, 3, 20, 20))
        if self.hasFocus():
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.setPen(QColor("#1685fb"))
            painter.drawRoundedRect(QRectF(0.5, 0.5, 43, 25), 12, 12)
