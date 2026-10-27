"""Visible, editable personal context. Memory is stored only on this PC."""

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import (
    QAbstractItemView,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from jarvis.core.application import JarvisApplication


class MemoryPage(QWidget):
    def __init__(self, jarvis: JarvisApplication) -> None:
        super().__init__()
        self.jarvis = jarvis
        self._snapshot: object = None
        layout = QVBoxLayout(self)
        title = QLabel("Personal memory")
        title.setObjectName("pageTitle")
        layout.addWidget(title)
        description = QLabel(
            "Save your preferences and facts here, or say 'remember response_style = concise'. "
            "Memories stay on this PC and relevant context is included when you use a cloud agent. "
            "The last 12 chat exchanges are kept as recent context. Do not store passwords or API keys."
        )
        description.setWordWrap(True)
        layout.addWidget(description)
        row = QHBoxLayout()
        self.name = QLineEdit()
        self.name.setPlaceholderText("Name, e.g. learning_goal")
        self.value = QLineEdit()
        self.value.setPlaceholderText("Value, e.g. Spring Boot and SQL")
        row.addWidget(self.name)
        row.addWidget(self.value, 2)
        save = QPushButton("Save memory")
        save.clicked.connect(self._save)
        row.addWidget(save)
        layout.addLayout(row)
        self.table = QTableWidget(0, 2)
        self.table.setHorizontalHeaderLabels(["Name", "Value"])
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.itemSelectionChanged.connect(self._select)
        layout.addWidget(self.table, 1)
        row = QHBoxLayout()
        remove = QPushButton("Forget selected")
        remove.clicked.connect(self._forget)
        clear = QPushButton("Clear all personal memory and recent context")
        clear.clicked.connect(self._clear)
        row.addWidget(remove)
        row.addWidget(clear)
        layout.addLayout(row)
        self.status = QLabel("")
        layout.addWidget(self.status)
        layout.addWidget(QLabel("Recent chat context"))
        self.recent = QPlainTextEdit()
        self.recent.setReadOnly(True)
        layout.addWidget(self.recent, 1)
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.refresh_view)
        self.timer.start(1000)
        self.refresh_view()

    def refresh_view(self) -> None:
        facts = self.jarvis.personal_memory.facts()
        turns = self.jarvis.personal_memory.recent_turns()
        snapshot = (tuple(facts.items()), tuple(turns))
        if snapshot == self._snapshot:
            return
        self._snapshot = snapshot
        self.table.setRowCount(len(facts))
        for row, (name, value) in enumerate(facts.items()):
            self.table.setItem(row, 0, QTableWidgetItem(name))
            self.table.setItem(row, 1, QTableWidgetItem(value))
        self.recent.setPlainText("\n\n".join(f"You: {p}\nJARVIS: {a}" for p, a in turns))

    def _select(self) -> None:
        name = self.table.item(self.table.currentRow(), 0)
        value = self.table.item(self.table.currentRow(), 1)
        if name and value:
            self.name.setText(name.text())
            self.value.setText(value.text())

    def _save(self) -> None:
        try:
            self.jarvis.personal_memory.remember(self.name.text(), self.value.text())
            self.status.setText("Memory saved.")
            self.refresh_view()
        except ValueError as exc:
            self.status.setText(str(exc))

    def _forget(self) -> None:
        name = self.table.item(self.table.currentRow(), 0)
        if name:
            self.jarvis.personal_memory.forget(name.text())
            self.jarvis.conversation.clear()
            self.refresh_view()

    def _clear(self) -> None:
        if QMessageBox.question(self, "Clear memory", "Delete all saved personal facts and recent chat context?") == QMessageBox.StandardButton.Yes:
            self.jarvis.personal_memory.clear()
            self.jarvis.conversation.clear()
            self.refresh_view()
