"""Native, soft animated graphics; no video, browser or model calls."""
import math

from PySide6.QtCore import QElapsedTimer, QPointF, QRectF, Qt, QTimer
from PySide6.QtGui import (
    QColor,
    QLinearGradient,
    QPainter,
    QPainterPath,
    QPen,
    QRadialGradient,
)
from PySide6.QtWidgets import QWidget

COLORS = {"idle":("#91beed","#ceaff0","#cdece5"), "listening":("#77e1c1","#80c9e8","#c6f8d8"),
          "thinking":("#a995ed","#94bafa","#ddd4ff"), "speaking":("#f1b7cc","#a5bdf4","#f5dac5"),
          "approval":("#e6c485","#efaa8e","#f8e8c4"), "paused":("#8794ab","#a9bad4","#c7d2e3"),
          "error":("#ec9aab","#c4a2cc","#f6c0b6")}
COLORS["stopped"] = COLORS["paused"]
COLORS["hearing"] = ("#63ecc6", "#6db9f5", "#dbffe6")


class AssistantOrb(QWidget):
    def __init__(self, presence, parent=None, *, size=184):
        super().__init__(parent)
        self.presence = presence
        self.setFixedSize(size,size)
        self.setAccessibleName("Jarvis assistant status")
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self.clock = QElapsedTimer()
        self.clock.start()
        self.level = self.target = 0.0
        self._palette_colors = [QColor(color) for color in COLORS[presence.phase]]
        self.target_palette = list(self._palette_colors)
        self.timer = QTimer(self)
        self.timer.setInterval(33)
        self.timer.timeout.connect(self._tick)
        presence.changed.connect(self._state_changed)
        presence.level_changed.connect(self._level)

    def _state_changed(self):
        self.setAccessibleDescription(self.presence.phase)
        self.target_palette = [QColor(color) for color in COLORS[self.presence.phase]]
        if not self.presence.motion:self._palette_colors = list(self.target_palette)
        if self.isVisible() and self.presence.motion:
            if not self.timer.isActive():self.timer.start()
        else:
            self.timer.stop()
        self.update()

    def _level(self, value):
        self.target = value

    def _tick(self):
        self.level = self.level*0.8 + self.target*0.2
        self.target *= 0.93
        self._palette_colors = [QColor(*(round(getattr(old,channel)()*0.8+getattr(new,channel)()*0.2)
                                  for channel in ("red","green","blue"))) for old,new in zip(self._palette_colors,self.target_palette,strict=True)]
        self.update()

    def showEvent(self, event):
        super().showEvent(event)
        self._state_changed()

    def hideEvent(self, event):
        self.timer.stop()
        super().hideEvent(event)

    def paintEvent(self, event):
        del event
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        t = self.clock.elapsed()/1000 if self.presence.motion else 0.0
        speaking = self.presence.phase == "speaking"
        active = speaking or self.presence.phase in {"listening", "hearing"}
        # Playback can arrive in buffered bursts. Keep a visible speaking pulse
        # between level samples, without presenting synthetic microphone levels.
        strength = max(self.level, 0.32+0.20*math.sin(t*6)**2 if speaking else 0.06) if active else 0.08
        speed = 2.4 if speaking else 1.6 if active else 0.7
        cx,cy = self.width()/2,self.height()/2
        radius = min(cx,cy)*0.59*(1+0.025*math.sin(t*2.4)+0.12*strength)
        a,b,c = self._palette_colors
        if self.presence.particles:
            painter.setPen(Qt.PenStyle.NoPen)
            for index in range(28):
                angle = index*2.39996 + t*(0.035 if index%2 else -0.025)
                distance = min(cx,cy)*(0.73+0.20*(index%7)/6)
                tint = QColor(a);tint.setAlpha(round(30+40*(0.5+0.5*math.sin(t+index))))
                painter.setBrush(tint)
                painter.drawEllipse(QPointF(cx+math.cos(angle)*distance,cy+math.sin(angle)*distance),1.0,1.0)
        if active:
            painter.setBrush(Qt.BrushStyle.NoBrush)
            for index in range(2):
                pulse = ((t*0.6+index*0.5)%1) if self.presence.motion else 0.4
                tint = QColor(a);tint.setAlpha(round(60*(1-pulse)))
                painter.setPen(QPen(tint,1.2))
                ring = radius*(1.04+pulse*0.46)
                painter.drawEllipse(QPointF(cx,cy),ring,ring)
        halo = QRadialGradient(QPointF(cx,cy),radius*1.48)
        tint = QColor(a);tint.setAlpha(46)
        halo.setColorAt(0,tint);halo.setColorAt(0.65,tint);halo.setColorAt(1,QColor(0,0,0,0))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(halo)
        painter.drawEllipse(QPointF(cx,cy),radius*1.48,radius*1.48)
        shape = QPainterPath()
        for i in range(97):
            angle = i*math.tau/96
            wobble = 1+(0.035+strength*0.055)*math.sin(3*angle+t*speed)+(0.02+strength*0.025)*math.sin(5*angle-t*speed*1.2)
            point = QPointF(cx+radius*wobble*math.cos(angle),cy+radius*wobble*math.sin(angle))
            if i == 0:shape.moveTo(point)
            else:shape.lineTo(point)
        shape.closeSubpath()
        base = QLinearGradient(cx-radius,cy-radius,cx+radius,cy+radius)
        base.setColorAt(0,c);base.setColorAt(0.48,a);base.setColorAt(1,b)
        painter.setBrush(base);painter.drawPath(shape)
        painter.save();painter.setClipPath(shape)
        for index,color in enumerate((b,c,a,QColor("#ffffff"))):
            x = cx+math.sin(t*(0.45+index*0.08)+index*2)*radius*0.58
            y = cy+math.cos(t*(0.4+index*0.06)+index)*radius*0.5
            gradient = QRadialGradient(QPointF(x,y),radius*(0.78+0.04*index))
            center = QColor(color);center.setAlpha(155 if index<3 else 105)
            edge = QColor(color);edge.setAlpha(0)
            gradient.setColorAt(0,center);gradient.setColorAt(1,edge)
            painter.setBrush(gradient)
            painter.drawEllipse(QRectF(cx-radius*1.3,cy-radius*1.3,radius*2.6,radius*2.6))
        shine = QRadialGradient(QPointF(cx-radius*0.27,cy-radius*0.4),radius*1.1)
        shine.setColorAt(0,QColor(255,255,255,110));shine.setColorAt(0.55,QColor(255,255,255,5));shine.setColorAt(1,QColor(0,0,0,36))
        painter.setBrush(shine);painter.drawPath(shape);painter.restore()
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.setPen(QPen(QColor(255,255,255,70),0.8));painter.drawPath(shape)
