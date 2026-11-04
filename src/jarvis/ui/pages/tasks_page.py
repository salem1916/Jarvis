"""Assign independent jobs without blocking the desktop chat."""

from typing import cast

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import (
    QAbstractItemView,
    QComboBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPlainTextEdit,
    QPushButton,
    QScrollArea,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from jarvis.agents.team import Backend, WorkerDefinition
from jarvis.core.application import JarvisApplication


class TasksPage(QWidget):
    def __init__(self, jarvis: JarvisApplication) -> None:
        super().__init__()
        self.jarvis = jarvis
        self._snapshot: object = None
        outer = QVBoxLayout(self);outer.setContentsMargins(0,0,0,0)
        scroll = QScrollArea();scroll.setWidgetResizable(True);scroll.setFrameShape(QScrollArea.Shape.NoFrame)
        content = QWidget();scroll.setWidget(content);outer.addWidget(scroll)
        layout = QVBoxLayout(content);layout.setContentsMargins(24,24,24,24);layout.setSpacing(14)
        title = QLabel("Agent team")
        title.setObjectName("pageTitle")
        layout.addWidget(title)
        description = QLabel(
            "Assign independent tasks to your connected models or Hermes. "
            "Up to three jobs run together. Completed drafts appear in Updates for review. PC actions stay in Chat."
        )
        description.setWordWrap(True)
        layout.addWidget(description)
        connection = QLabel("Connect providers in Settings. ChatGPT plan usage and OpenAI API billing are separate choices.")
        connection.setWordWrap(True)
        layout.addWidget(connection)
        configure = QPushButton("Configure agents")
        configure.setCheckable(True)
        layout.addWidget(configure)
        configuration = QWidget();configuration.hide()
        configure.toggled.connect(configuration.setVisible)
        config_layout = QVBoxLayout(configuration);config_layout.setContentsMargins(0,8,0,8)
        layout.addWidget(configuration)
        row = QHBoxLayout()
        self.agent_name = QLineEdit()
        self.agent_name.setPlaceholderText("Agent name, e.g. coder")
        self.backend = QComboBox()
        self.backend.addItems(["plan", "groq", "gemini", "openrouter_free", "chatgpt", "local", "hermes"])
        self.model = QLineEdit()
        self.model.setPlaceholderText("Model override (optional)")
        row.addWidget(self.agent_name)
        row.addWidget(self.backend)
        row.addWidget(self.model)
        config_layout.addLayout(row)
        self.instructions = QLineEdit()
        self.instructions.setPlaceholderText("Worker instructions, e.g. explain Java clearly and include examples")
        config_layout.addWidget(self.instructions)
        save = QPushButton("Save agent")
        save.clicked.connect(self._save_agent)
        config_layout.addWidget(save)
        row = QHBoxLayout()
        self.agent = QComboBox()
        self.agent.currentTextChanged.connect(self._load_agent)
        row.addWidget(QLabel("Assign to"))
        row.addWidget(self.agent, 1)
        layout.addLayout(row)
        self.prompt = QPlainTextEdit()
        self.prompt.setPlaceholderText("Describe this agent's task. Assign another task to run them in parallel.")
        self.prompt.setMaximumHeight(100)
        layout.addWidget(self.prompt)
        row = QHBoxLayout()
        submit = QPushButton("Assign task")
        submit.clicked.connect(self._submit)
        cancel = QPushButton("Cancel selected queued task")
        cancel.clicked.connect(self._cancel)
        row.addWidget(submit)
        row.addWidget(cancel)
        layout.addLayout(row)
        self.status = QLabel("")
        self.status.setWordWrap(True)
        layout.addWidget(self.status)
        self.table = QTableWidget(0, 4)
        self.table.setMinimumHeight(180)
        self.table.setHorizontalHeaderLabels(["Task", "Agent", "Status", "Assignment"])
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.itemSelectionChanged.connect(self._show_result)
        self.table.horizontalHeader().setStretchLastSection(True)
        layout.addWidget(self.table, 1)
        self.result = QPlainTextEdit()
        self.result.setMinimumHeight(120)
        self.result.setReadOnly(True)
        self.result.setPlaceholderText("Select a task to read its result. Completed tasks survive restarts.")
        layout.addWidget(self.result, 1)
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.refresh_view)
        self.timer.start(500)
        self.refresh_view()

    def refresh_view(self) -> None:
        names = [a.name for a in self.jarvis.agent_team.agents()]
        if names != [self.agent.itemText(i) for i in range(self.agent.count())]:
            selected = self.agent.currentText()
            self.agent.clear()
            self.agent.addItems(names)
            self.agent.setCurrentText(selected or names[0])
        jobs = self.jarvis.agent_team.jobs()
        snapshot = tuple((j.job_id, j.status) for j in jobs)
        if snapshot == self._snapshot:
            return
        selected_id = self._selected_id()
        self.table.blockSignals(True)
        self.table.setRowCount(len(jobs))
        for row, job in enumerate(jobs):
            for col, value in enumerate((job.job_id, job.agent, job.status, job.prompt[:100])):
                self.table.setItem(row, col, QTableWidgetItem(value))
            if job.job_id == selected_id:
                self.table.selectRow(row)
        self.table.blockSignals(False)
        self._snapshot = snapshot
        self._show_result()

    def _load_agent(self, name: str) -> None:
        definition = next((a for a in self.jarvis.agent_team.agents() if a.name == name), None)
        if definition:
            self.agent_name.setText(definition.name)
            self.backend.setCurrentText(definition.backend)
            self.instructions.setText(definition.instructions)
            self.model.setText(definition.model)

    def _save_agent(self) -> None:
        try:
            name = self.agent_name.text().strip().casefold()
            if self.backend.currentText() == "hermes" and self.model.text().strip():
                raise ValueError("Hermes uses its own model configuration; leave the model override empty.")
            self.jarvis.agent_team.configure(WorkerDefinition(
                name, cast(Backend, self.backend.currentText()),
                self.instructions.text(), self.model.text().strip(),
            ))
            self.refresh_view()
            self.agent.setCurrentText(name)
            self.status.setText("Agent saved. Existing jobs keep their original assignment.")
        except ValueError as exc:
            self.status.setText(str(exc))

    def _submit(self) -> None:
        try:
            job = self.jarvis.agent_team.submit(self.agent.currentText(), self.prompt.toPlainText())
            self.prompt.clear()
            self.status.setText(f"Assigned {job.job_id} to {job.agent}.")
            self.refresh_view()
            self.table.selectRow(0)
        except (ValueError, RuntimeError) as exc:
            self.status.setText(str(exc))

    def _selected_id(self) -> str | None:
        item = self.table.item(self.table.currentRow(), 0)
        return item.text() if item else None

    def _show_result(self) -> None:
        job_id = self._selected_id()
        if job_id:
            job = self.jarvis.agent_team.job(job_id)
            self.result.setPlainText(
                f"{job.agent} · {job.backend} · {job.status} · {job.duration:.1f}s\n\n"
                f"Task: {job.prompt}\n\n{job.result or 'Waiting for a result…'}"
            )

    def _cancel(self) -> None:
        job_id = self._selected_id()
        if job_id:
            cancelled = self.jarvis.agent_team.cancel(job_id)
            self.status.setText("Task cancelled." if cancelled else
                                "Only queued tasks can be cancelled. Running requests use the provider timeout.")
            self.refresh_view()
