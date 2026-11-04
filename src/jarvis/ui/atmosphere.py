"""Subtle native background dots; no textures, browser or GPU dependency."""
import math

from PySide6.QtCore import QElapsedTimer, QPointF, QTimer
from PySide6.QtGui import QColor, QPainter
from PySide6.QtWidgets import QFrame


class AtmosphereFrame(QFrame):
    def __init__(self, presence):
        super().__init__()
        self.presence = presence
        self.clock = QElapsedTimer();self.clock.start()
        self.timer = QTimer(self);self.timer.setInterval(80)
        self.timer.timeout.connect(self.update)
        presence.changed.connect(self._sync)

    def _sync(self):
        if self.isVisible() and self.presence.motion and self.presence.particles:
            if not self.timer.isActive():self.timer.start()
        else:self.timer.stop()
        self.update()

    def showEvent(self, event):
        super().showEvent(event);self._sync()

    def hideEvent(self, event):
        self.timer.stop();super().hideEvent(event)

    def paintEvent(self, event):
        super().paintEvent(event)
        if not self.presence.particles:return
        painter = QPainter(self);painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        t = self.clock.elapsed()/1000 if self.presence.motion else 0
        for index in range(56):
            x = (index*0.618034%1)*self.width()
            y = ((index*0.414214%1)+0.008*math.sin(t*0.23+index))*self.height()
            color = QColor(155,184,222,round(16+14*(0.5+0.5*math.sin(t*0.6+index))))
            painter.setPen(color);painter.setBrush(color)
            painter.drawEllipse(QPointF(x,y),0.8,0.8)
