"""Shared, observable presentation state. It never grants tools or starts capture."""
from PySide6.QtCore import QObject, Signal

PHASES = {"idle":"Ready", "listening":"Listening", "thinking":"Thinking", "speaking":"Speaking",
          "approval":"Your approval", "paused":"Paused", "stopped":"Stopped", "error":"Needs attention"}


class AssistantPresence(QObject):
    changed = Signal()
    level_changed = Signal(float)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.phase = "idle"
        self.caption = "What would you like to do?"
        self.microphone = False
        self.screen = False
        self.motion = True
        self.particles = True
        self.captions = True

    def update_state(self, *, phase=None, caption=None, microphone=None, screen=None, motion=None, particles=None, captions=None):
        if phase is not None and phase not in PHASES:
            raise ValueError("Unknown assistant presentation state")
        updates = {"phase":phase,"caption":caption,"microphone":microphone,"screen":screen,"motion":motion,
                   "particles":particles,"captions":captions}
        changed = False
        for key, value in updates.items():
            if value is not None and getattr(self,key) != value:
                setattr(self,key,value)
                changed = True
        if changed:
            self.changed.emit()

    def set_level(self, value):
        self.level_changed.emit(max(0.0,min(1.0,float(value))))
