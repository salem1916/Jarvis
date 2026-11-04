"""Non-blocking background updates and read-only drafts on a chosen display."""

from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtGui import QGuiApplication
from PySide6.QtWidgets import (
    QAbstractItemView,
    QCheckBox,
    QComboBox,
    QDialog,
    QHBoxLayout,
    QLabel,
    QPlainTextEdit,
    QPushButton,
    QScrollArea,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from jarvis.core.application import JarvisApplication


class UpdatesPage(QWidget):
    unread_changed = Signal(int)
    attention = Signal(str)

    def __init__(self, jarvis: JarvisApplication) -> None:
        super().__init__()
        self.jarvis = jarvis
        self.inbox = jarvis.assistant_inbox
        self._snapshot: object = None
        self._previews: list[QDialog] = []
        outer = QVBoxLayout(self);outer.setContentsMargins(0,0,0,0)
        scroll = QScrollArea();scroll.setWidgetResizable(True);scroll.setFrameShape(QScrollArea.Shape.NoFrame)
        content = QWidget();scroll.setWidget(content);outer.addWidget(scroll)
        layout = QVBoxLayout(content);layout.setContentsMargins(24,24,24,24);layout.setSpacing(14)
        title = QLabel("Updates")
        title.setObjectName("pageTitle")
        layout.addWidget(title)
        description = QLabel("Background agents bring completed drafts here for your review. Reviewing never publishes, deploys, sends, or edits anything.")
        description.setWordWrap(True)
        layout.addWidget(description)
        self.quiet = QCheckBox("Quiet mode · keep updates here without interrupting Chat")
        self.quiet.setChecked(self.inbox.quiet())
        self.quiet.toggled.connect(self.inbox.set_quiet)
        layout.addWidget(self.quiet)
        self.summary = QLabel()
        layout.addWidget(self.summary)
        self.table = QTableWidget(0, 3)
        self.table.setMinimumHeight(180)
        self.table.setHorizontalHeaderLabels(["State", "Agent", "Update"])
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.itemSelectionChanged.connect(self._show_update)
        layout.addWidget(self.table, 1)
        self.details = QPlainTextEdit()
        self.details.setMinimumHeight(120)
        self.details.setReadOnly(True)
        self.details.setPlaceholderText("No updates yet. Assign a draft in Tasks or use: delegate to agent: your task")
        layout.addWidget(self.details, 1)
        row = QHBoxLayout()
        self.review = QPushButton("Mark reviewed")
        self.review.clicked.connect(lambda: self._transition("reviewed"))
        self.dismiss = QPushButton("Dismiss")
        self.dismiss.clicked.connect(lambda: self._transition("dismissed"))
        self.display_selector = QComboBox()
        self.preview = QPushButton("Open draft on display")
        self.preview.clicked.connect(self._preview)
        for widget in (self.review, self.dismiss):
            row.addWidget(widget)
        row.addStretch()
        layout.addLayout(row)
        row = QHBoxLayout()
        row.addWidget(QLabel("Preview on"))
        row.addWidget(self.display_selector,1)
        row.addWidget(self.preview)
        layout.addLayout(row)
        self.status = QLabel("Work continues while JARVIS is open. Sales, client systems, voice, and phone channels are not connected in this stage.")
        self.status.setWordWrap(True)
        layout.addWidget(self.status)
        app = QGuiApplication.instance()
        assert isinstance(app, QGuiApplication)
        app.screenAdded.connect(lambda _: self._screens())
        app.screenRemoved.connect(lambda _: self._screens())
        self._screens()
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.refresh_view)
        self.timer.start(1000)
        self.refresh_view()

    def _screens(self) -> None:
        selected = self.display_selector.currentText()
        self.display_selector.clear()
        for index, screen in enumerate(QGuiApplication.screens()):
            self.display_selector.addItem(f"Display {index + 1} · {screen.name()}", screen.name())
        index = self.display_selector.findText(selected)
        self.display_selector.setCurrentIndex(index if index >= 0 else min(1, self.display_selector.count() - 1))

    def _selected(self) -> str:
        row = self.table.currentRow()
        item = self.table.item(row, 0) if row >= 0 else None
        return str(item.data(Qt.ItemDataRole.UserRole)) if item is not None else ""

    def refresh_view(self) -> None:
        self.quiet.blockSignals(True)
        self.quiet.setChecked(self.inbox.quiet())
        self.quiet.blockSignals(False)
        created = self.inbox.collect(self.jarvis.agent_team.jobs())
        updates = self.inbox.updates()
        unread = self.inbox.unread_count()
        self.unread_changed.emit(unread)
        self.summary.setText(f"{unread} new · {len(updates)} updates. Draft output needs review and may contain mistakes.")
        snapshot = tuple((u.update_id, u.state) for u in updates)
        if snapshot != self._snapshot:
            selected = self._selected()
            self.table.blockSignals(True)
            self.table.setRowCount(len(updates))
            for row, update in enumerate(updates):
                for col, value in enumerate((update.state, update.agent, update.title)):
                    item = QTableWidgetItem(value)
                    item.setData(Qt.ItemDataRole.UserRole, update.update_id)
                    self.table.setItem(row, col, item)
                if update.update_id == selected:
                    self.table.selectRow(row)
            self.table.blockSignals(False)
            self._snapshot = snapshot
            self._show_update()
        if created and not self.inbox.quiet():
            self.attention.emit(f"{len(created)} background update(s) ready. Open Updates when convenient.")

    def _show_update(self) -> None:
        selected = self._selected()
        update = next((u for u in self.inbox.updates() if u.update_id == selected), None)
        self.details.setPlainText(f"{update.title}\nTask: {update.job_id} · {update.outcome}\n\n{update.body}" if update else "")
        for button in (self.review, self.dismiss, self.preview):
            button.setEnabled(update is not None)

    def _transition(self, state: str) -> None:
        if self._selected():
            self.inbox.transition(self._selected(), state)
            self.status.setText("Review state saved. No changes were applied.")
            self.refresh_view()

    def _preview(self) -> None:
        selected = self._selected()
        update = next((u for u in self.inbox.updates() if u.update_id == selected), None)
        if not update:
            return
        screens = QGuiApplication.screens()
        screen = next((s for s in screens if s.name() == self.display_selector.currentData()), None)
        if screen is None:
            self._screens()
            self.status.setText("That display is no longer connected. Choose an available display.")
            return
        dialog = QDialog(self)
        dialog.setModal(False)
        dialog.setWindowTitle("JARVIS draft · review only")
        box = QVBoxLayout(dialog)
        box.addWidget(QLabel(update.title))
        text = QPlainTextEdit()
        text.setReadOnly(True)
        text.setPlainText(update.body)
        box.addWidget(text)
        close = QPushButton("Close preview")
        close.clicked.connect(dialog.close)
        box.addWidget(close)
        area = screen.availableGeometry()
        dialog.resize(min(900, area.width()), min(650, area.height()))
        dialog.move(area.x() + (area.width() - dialog.width()) // 2,
                    area.y() + (area.height() - dialog.height()) // 2)
        self._previews.append(dialog)
        dialog.finished.connect(lambda _: self._release_preview(dialog))
        dialog.show()
        self.status.setText("Read-only draft opened. No website or file was changed.")

    def _release_preview(self, dialog: QDialog) -> None:
        if dialog in self._previews:
            self._previews.remove(dialog)
        dialog.deleteLater()
