"""Movable desktop companion. All microphone/screen actions require a click."""
from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLayout,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from jarvis.ui.orb import AssistantOrb
from jarvis.ui.presence import PHASES


class DesktopCompanion(QWidget):
    microphone_requested = Signal()
    screen_requested = Signal(bool)
    open_requested = Signal()
    stop_requested = Signal()
    dismissed = Signal()

    def __init__(self, presence):
        super().__init__(None,Qt.WindowType.Tool | Qt.WindowType.FramelessWindowHint | Qt.WindowType.WindowStaysOnTopHint)
        self.presence = presence
        self.expanded = False
        self._drag = None
        self._moved = False
        self.setWindowTitle("Jarvis desktop companion")
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
        self.setStyleSheet('''QWidget {color:#edf0f8;font-family:"Segoe UI";font-size:13px;}
          QFrame#companion {background:#171b25;border:1px solid #373d4c;border-radius:22px;}
          QLabel {background:transparent;border:none;} QLabel#companionCaption {color:#c4cad8;font-size:15px;}
          QPushButton {background:#242a37;border:1px solid #3b4354;border-radius:12px;padding:9px 12px;}
          QPushButton:hover {background:#343c4e;} QPushButton#companionOpen {background:#dfe8f7;color:#192232;}
        ''')
        outer = QVBoxLayout(self);outer.setContentsMargins(3,3,3,3)
        self.card = QFrame();self.card.setObjectName("companion")
        outer.addWidget(self.card)
        self.body = QVBoxLayout(self.card);self.body.setContentsMargins(12,10,12,12);self.body.setSpacing(10)
        hero = QHBoxLayout();hero.setContentsMargins(0,0,0,0)
        self.bubble = AssistantOrb(presence,size=76)
        hero.addWidget(self.bubble,alignment=Qt.AlignmentFlag.AlignCenter)
        self.compact = QWidget();compact_layout = QVBoxLayout(self.compact)
        compact_layout.setContentsMargins(0,0,6,0);compact_layout.setSpacing(5)
        self.compact_state = QLabel();compact_layout.addWidget(self.compact_state)
        self.compact_caption = QLabel();self.compact_caption.setWordWrap(True)
        self.compact_caption.setObjectName("companionCaption");self.compact_caption.setMaximumHeight(48)
        compact_layout.addWidget(self.compact_caption)
        hero.addWidget(self.compact,1);self.body.addLayout(hero)
        self.panel = QWidget();layout = QVBoxLayout(self.panel);layout.setContentsMargins(6,0,6,3);layout.setSpacing(12)
        layout.setSizeConstraint(QLayout.SizeConstraint.SetMinimumSize)
        title = QHBoxLayout();title.addWidget(QLabel("J A R V I S"));title.addStretch()
        collapse = QPushButton("−");collapse.setToolTip("Collapse companion");collapse.clicked.connect(lambda:self.set_expanded(False))
        title.addWidget(collapse);layout.addLayout(title)
        self.state_label = QLabel();self.state_label.setAlignment(Qt.AlignmentFlag.AlignCenter);layout.addWidget(self.state_label)
        self.caption = QLabel();self.caption.setObjectName("companionCaption");self.caption.setWordWrap(True)
        self.caption.setTextFormat(Qt.TextFormat.PlainText);self.caption.setMaximumHeight(104)
        self.caption.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        layout.addWidget(self.caption)
        self.captions_toggle = QCheckBox("Show captions")
        self.captions_toggle.setChecked(presence.captions)
        self.captions_toggle.toggled.connect(lambda enabled:presence.update_state(captions=enabled))
        layout.addWidget(self.captions_toggle)
        controls = QHBoxLayout()
        self.mic = QPushButton();self.mic.clicked.connect(self.microphone_requested.emit)
        self.screen_button = QPushButton();self.screen_button.clicked.connect(self._screen_click)
        controls.addWidget(self.mic);controls.addWidget(self.screen_button);layout.addLayout(controls)
        self.share_prompt = QWidget();share = QVBoxLayout(self.share_prompt);share.setContentsMargins(0,0,0,0)
        explanation = QLabel("Share the active app with your selected AI during screen tasks?")
        explanation.setWordWrap(True);share.addWidget(explanation)
        allow = QPushButton("Allow screen access");allow.clicked.connect(self._allow_screen);share.addWidget(allow)
        deny = QPushButton("Keep screen off");deny.clicked.connect(self._deny_screen);share.addWidget(deny)
        self.share_prompt.hide();layout.addWidget(self.share_prompt)
        self.open_button = QPushButton("Open Jarvis");self.open_button.setObjectName("companionOpen")
        self.open_button.clicked.connect(self.open_requested.emit);layout.addWidget(self.open_button)
        stop = QPushButton("Stop task and voice");stop.clicked.connect(self.stop_requested.emit);layout.addWidget(stop)
        self.panel_scroll = QScrollArea();self.panel_scroll.setWidgetResizable(True)
        self.panel_scroll.setFrameShape(QFrame.Shape.NoFrame)
        self.panel_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.panel_scroll.setStyleSheet("QScrollArea, QScrollArea > QWidget > QWidget {background:transparent;border:none;}")
        self.panel_scroll.setWidget(self.panel)
        self.body.addWidget(self.panel_scroll);self.panel_scroll.hide();self.panel.hide()
        self.setFixedSize(310,106)
        presence.changed.connect(self.refresh)
        self.refresh()
        screen = QApplication.primaryScreen()
        if screen:
            area = screen.availableGeometry();self.move(area.right()-self.width()-28,area.bottom()-self.height()-28)

    def refresh(self):
        state = PHASES[self.presence.phase]
        self.state_label.setText(state)
        self.compact_state.setText("JARVIS · " + state)
        text = self.presence.caption
        self.caption.setText(text if len(text)<=260 else text[:257]+"…")
        self.caption.setToolTip(text)
        self.compact_caption.setText(text if len(text)<=76 else text[:73]+"…")
        self.compact_caption.setToolTip(text)
        self.caption.setVisible(self.presence.captions)
        self.compact_caption.setVisible(self.presence.captions)
        self.captions_toggle.blockSignals(True)
        self.captions_toggle.setChecked(self.presence.captions)
        self.captions_toggle.blockSignals(False)
        self.mic.setText("Mic on · stop" if self.presence.microphone else "Start listening")
        self.screen_button.setText("Screen access on" if self.presence.screen else "Screen off")
        self.setToolTip(f"Jarvis · {state}\nMicrophone {'on' if self.presence.microphone else 'off'} · Screen access {'on' if self.presence.screen else 'off'}\nClick to open · drag to move")

    def _screen_click(self):
        if self.presence.screen:self.screen_requested.emit(False)
        else:self.share_prompt.setVisible(not self.share_prompt.isVisible())
        self.set_expanded(True)

    def _allow_screen(self):
        self.screen_requested.emit(True)
        self.share_prompt.hide()
        self.set_expanded(True)

    def _deny_screen(self):
        self.share_prompt.hide()
        self.set_expanded(True)

    def set_expanded(self, expanded):
        old_right,old_bottom = self.geometry().right(),self.geometry().bottom()
        self.expanded = expanded
        self.panel_scroll.setVisible(expanded)
        self.panel.setVisible(expanded)
        self.compact.setVisible(not expanded)
        self.bubble.setFixedSize(124 if expanded else 76,124 if expanded else 76)
        screen = QApplication.screenAt(self.geometry().center()) or QApplication.primaryScreen()
        available = screen.availableGeometry().height()-24 if screen else 700
        self.setFixedSize(350,min(available,650 if self.share_prompt.isVisible() else 500)) if expanded else self.setFixedSize(310,106)
        self.move(old_right-self.width()+1,old_bottom-self.height()+1)
        self._clamp()

    def _clamp(self):
        screen = QApplication.screenAt(self.geometry().center()) or QApplication.primaryScreen()
        if screen:
            bounds = screen.availableGeometry()
            self.move(max(bounds.left()+8,min(self.x(),bounds.right()-self.width()-8)),
                      max(bounds.top()+8,min(self.y(),bounds.bottom()-self.height()-8)))

    def mousePressEvent(self,event):
        if event.button() == Qt.MouseButton.LeftButton:
            self._drag = event.globalPosition().toPoint()-self.pos();self._moved = False;event.accept()

    def mouseMoveEvent(self,event):
        if self._drag is not None:
            destination = event.globalPosition().toPoint()-self._drag
            if (destination-self.pos()).manhattanLength()>3:self._moved=True
            if self._moved:self.move(destination)

    def mouseReleaseEvent(self,event):
        if self._drag is not None:
            self._drag=None
            if not self._moved:self.set_expanded(not self.expanded)
            self._clamp();event.accept()

    def keyPressEvent(self,event):
        if event.key() == Qt.Key.Key_Escape:self.set_expanded(False)
        else:super().keyPressEvent(event)

    def closeEvent(self,event):
        self.dismissed.emit()
        super().closeEvent(event)
