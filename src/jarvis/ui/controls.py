"""Roomy controls, kept separate from the conversation and its input."""
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)


class AssistantControls(QDialog):
    def __init__(self, parent):
        super().__init__(parent)
        self.setWindowTitle("Jarvis controls")
        self.setObjectName("assistantControls")
        self.setModal(False)
        self.resize(620, 560)
        self.setMinimumSize(480, 340)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 20, 24, 20)
        heading = QLabel("Make Jarvis yours");heading.setObjectName("pageTitle")
        layout.addWidget(heading)
        self.tabs = QTabWidget();layout.addWidget(self.tabs, 1)
        footer = QHBoxLayout();footer.addStretch()
        close = QPushButton("Done");close.clicked.connect(self.hide)
        footer.addWidget(close);layout.addLayout(footer)

    def section(self, title, description):
        content = QWidget();layout = QVBoxLayout(content)
        layout.setContentsMargins(18, 20, 18, 20);layout.setSpacing(18)
        note = QLabel(description);note.setWordWrap(True);note.setObjectName("mutedText")
        layout.addWidget(note)
        scroll = QScrollArea();scroll.setWidgetResizable(True)
        scroll.setFrameShape(QScrollArea.Shape.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setWidget(content);self.tabs.addTab(scroll, title)
        return layout

    def reveal(self):
        parent = self.parentWidget()
        screen = parent.screen() if parent is not None else None
        if screen:
            bounds = screen.availableGeometry()
            self.resize(min(620,bounds.width()-48),min(560,bounds.height()-64))
        self.show();self.raise_();self.activateWindow()
