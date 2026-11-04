"""Human approval inbox for provider discovery and account-owned connections."""

from __future__ import annotations

import webbrowser
from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any

from PySide6.QtCore import QThread, QTimer, Signal
from PySide6.QtWidgets import (
    QAbstractItemView,
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFrame,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QPlainTextEdit,
    QProgressBar,
    QPushButton,
    QScrollArea,
    QSpinBox,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from jarvis.core.application import JarvisApplication
from jarvis.runtime.profile import RuntimeMode
from jarvis.runtime.provider_steward import SPECS
from jarvis.ui.pages.settings_page import SettingsOperation
from jarvis.ui.toggle import ToggleSwitch


class ProviderAssistantPage(QWidget):
    activated = Signal(str, str)
    policy_changed = Signal()

    def __init__(self, jarvis: JarvisApplication) -> None:
        super().__init__()
        assert jarvis.intelligence is not None
        self.jarvis = jarvis
        self.hub = jarvis.intelligence
        self.steward = self.hub.steward
        self.operation_thread: QThread | None = None
        self.operation_worker: SettingsOperation | None = None
        self._success: Callable[[Any], None] = lambda value: None
        self._account_models: dict[str, list[dict[str, str]]] = {}
        self._model_source = ""
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        content = QWidget()
        scroll.setWidget(content)
        outer.addWidget(scroll)
        layout = QVBoxLayout(content)
        layout.setContentsMargins(24, 20, 24, 20)
        title = QLabel("API assistant")
        title.setObjectName("pageTitle")
        layout.addWidget(title)
        description = QLabel("Research → approve → connect → test & enable. New accounts, terms, and billing always remain your choice.")
        description.setWordWrap(True)
        description.setObjectName("mutedText")
        layout.addWidget(description)
        card = QFrame()
        card.setObjectName("settingsCard")
        controls = QVBoxLayout(card)
        self.enabled, self.auto_review, self.failover, self.commercial = (ToggleSwitch() for _ in range(4))
        for label, toggle in (
            ("Manage API connections with approvals", self.enabled),
            ("Refresh official offers daily while JARVIS is open", self.auto_review),
            ("Allow approved fallbacks, then local inference", self.failover),
            ("Product preview · customer-owned keys only", self.commercial),
        ):
            row = QHBoxLayout()
            text = QLabel(label)
            text.setWordWrap(True)
            toggle.setAccessibleName(label)
            row.addWidget(text, 1)
            row.addWidget(toggle)
            controls.addLayout(row)
        row = QHBoxLayout()
        limit_label = QLabel("Daily requests per provider");limit_label.setWordWrap(True)
        row.addWidget(limit_label, 1)
        self.daily_limit = QSpinBox()
        self.daily_limit.setRange(1, 5000)
        row.addWidget(self.daily_limit)
        self.save_policy_button = QPushButton("Save policy")
        self.save_policy_button.clicked.connect(self._save_policy)
        row.addWidget(self.save_policy_button)
        controls.addLayout(row)
        note = QLabel("This is a request cap, not a provider billing cap. Free-tier account status and commercial terms must be checked by the owner. Personal ChatGPT is excluded from product mode and automatic fallback.")
        note.setWordWrap(True)
        note.setObjectName("mutedText")
        controls.addWidget(note)
        layout.addWidget(card)

        row = QHBoxLayout()
        self.research_button = QPushButton("Research offers")
        self.research_button.setObjectName("primaryButton")
        self.research_button.clicked.connect(self._research)
        row.addWidget(self.research_button)
        self.approve_button = QPushButton("Review connection")
        self.approve_button.clicked.connect(self._approve)
        row.addWidget(self.approve_button)
        self.revoke_button = QPushButton("Revoke")
        self.revoke_button.clicked.connect(self._revoke)
        row.addWidget(self.revoke_button)
        layout.addLayout(row)
        self.table = QTableWidget(0, 4)
        self.table.setHorizontalHeaderLabels(["Provider", "Access", "Research", "Approval"])
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setMinimumHeight(210)
        self.table.verticalHeader().hide()
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.itemSelectionChanged.connect(self._selection_changed)
        layout.addWidget(self.table, 1)
        self.details = QPlainTextEdit()
        self.details.setReadOnly(True)
        self.details.setMaximumHeight(120)
        layout.addWidget(self.details)
        row = QHBoxLayout()
        docs = QPushButton("Documentation ↗")
        docs.clicked.connect(lambda: self._open("documentation"))
        terms = QPushButton("Terms ↗")
        terms.clicked.connect(lambda: self._open("terms"))
        setup = QPushButton("Account setup ↗")
        setup.clicked.connect(lambda: self._open("console"))
        row.addWidget(docs)
        row.addWidget(terms)
        row.addWidget(setup)
        layout.addLayout(row)
        row = QHBoxLayout()
        self.key_input = QLineEdit()
        self.key_input.setEchoMode(QLineEdit.EchoMode.Password)
        self.key_input.setPlaceholderText("API key from the approved account")
        row.addWidget(self.key_input, 1)
        self.save_key_button = QPushButton("Save key")
        save_key = self.save_key_button
        save_key.clicked.connect(self._save_key)
        row.addWidget(save_key)
        self.load_button = QPushButton("Load models")
        self.load_button.clicked.connect(self._load_models)
        row.addWidget(self.load_button)
        layout.addLayout(row)
        row = QHBoxLayout()
        self.model = QComboBox()
        self.model.setEditable(True)
        row.addWidget(self.model, 1)
        self.activate_button = QPushButton("Test & enable")
        self.activate_button.setObjectName("primaryButton")
        self.activate_button.clicked.connect(self._activate)
        row.addWidget(self.activate_button)
        layout.addLayout(row)
        self.progress = QProgressBar()
        self.progress.setRange(0, 0)
        self.progress.setMaximumHeight(4)
        self.progress.hide()
        layout.addWidget(self.progress)
        self.status = QLabel("The assistant researches supported adapters and model catalogs. It does not download or execute integration code from websites.")
        self.status.setWordWrap(True)
        layout.addWidget(self.status)
        # Keep results visible even when the setup form needs scrolling.
        layout.removeWidget(self.progress)
        layout.removeWidget(self.status)
        footer = QVBoxLayout()
        footer.setContentsMargins(24, 4, 24, 12)
        footer.addWidget(self.progress)
        footer.addWidget(self.status)
        outer.addLayout(footer)
        policy = self.steward.policy()
        self.enabled.setChecked(policy["enabled"])
        self.auto_review.setChecked(policy["auto_review"])
        self.commercial.setChecked(policy["commercial"])
        self.failover.setChecked(policy["allow_failover"])
        self.daily_limit.setValue(policy["daily_limit"])
        self.timer = QTimer(self)
        self.timer.timeout.connect(self._automatic_review)
        self.timer.start(60000)
        self.refresh_view()
        self.initial_review_timer = QTimer(self)
        self.initial_review_timer.setSingleShot(True)
        self.initial_review_timer.timeout.connect(self._automatic_review)
        self.initial_review_timer.start(1000)

    def _source(self) -> str:
        row = self.table.currentRow()
        return list(SPECS)[row] if 0 <= row < len(SPECS) else ""

    def refresh_view(self) -> None:
        selected = self.table.currentRow()
        self.table.blockSignals(True)
        self.table.setRowCount(len(SPECS))
        for row, (source, spec) in enumerate(SPECS.items()):
            offer, approval = self.steward.offer(source), self.steward.approval(source)
            access = "Free tier: owner confirmation" if spec.access == "free_tier" else "Zero-price catalog" if spec.access == "zero_price_catalog" else "Paid / unverified"
            checked = "Not researched"
            if offer.get("checked_at"):
                checked = datetime.fromtimestamp(offer["checked_at"], UTC).astimezone().strftime("%d %b %H:%M")
            if offer.get("error"):
                checked += " · refresh failed"
            state = "Needs approval"
            try:
                self.steward.require_connection(source)
                state = "Active" if approval.get("active") else "Approved · connect account"
            except ValueError:
                pass
            for col, value in enumerate((spec.name, access, checked, state)):
                self.table.setItem(row, col, QTableWidgetItem(value))
        self.table.selectRow(max(0, selected))
        self.table.blockSignals(False)
        self._selection_changed()

    def _selection_changed(self) -> None:
        source = self._source()
        if not source:
            return
        spec, offer, approval = SPECS[source], self.steward.offer(source), self.steward.approval(source)
        expires = datetime.fromtimestamp(approval["expires_at"], UTC).astimezone().strftime("%d %b %H:%M") if approval.get("expires_at") else "—"
        self.details.setPlainText(
            f"{spec.name}\n{offer.get('summary', 'Research official evidence before connecting.')}\n"
            f"Zero-price catalog models: {offer.get('model_count', 0)} · Approval expires: {expires}\n"
            f"{offer.get('error', '')}\nDocumentation: {spec.documentation}\nTerms: {spec.terms}"
        )
        index = self.model.currentIndex()
        previous = ((self.model.currentData() if index >= 0 and self.model.currentText() == self.model.itemText(index)
                     else self.model.currentText().strip()) if self._model_source == source else "")
        self.model.clear()
        if source in self._account_models:
            for model in self._account_models[source]:
                self.model.addItem(model["name"], model["id"])
        elif source == "openrouter_free":
            self.model.addItem("Free models router", "openrouter/free")
            for model in offer.get("models", []):
                self.model.addItem(model["name"], model["id"])
        else:
            self.model.setEditText(str(approval.get("model") or self.hub.model_for(source)))
        selected = self.model.findData(previous or approval.get("model"))
        if selected >= 0:
            self.model.setCurrentIndex(selected)
        elif previous:
            self.model.setEditText(str(previous))
        if self._model_source != source:
            self.key_input.clear()
        self._model_source = source
        self.approve_button.setEnabled(spec.access != "paid_or_unverified" and self.operation_thread is None)
        self.activate_button.setEnabled(spec.access != "paid_or_unverified" and self.operation_thread is None)

    def _save_policy(self) -> None:
        self.steward.configure(enabled=self.enabled.isChecked(), auto_review=self.auto_review.isChecked(),
                               commercial=self.commercial.isChecked(), allow_failover=self.failover.isChecked(),
                               daily_limit=self.daily_limit.value())
        self.enabled.setChecked(self.steward.policy()["enabled"])
        self.policy_changed.emit()
        self.status.setText("Policy saved. Managed execution starts locally until you approve and enable a provider. Existing keys and your personal ChatGPT connection were kept separate.")
        self.refresh_view()

    def _operate(self, function: Callable[[], Any], success: Callable[[Any], None], text: str) -> None:
        if self.operation_thread is not None:
            return
        self._success = success
        self.status.setText(text)
        self.progress.show()
        self.table.setEnabled(False)
        for control in (self.research_button, self.approve_button, self.activate_button, self.load_button, self.save_policy_button, self.save_key_button, self.model):
            control.setEnabled(False)
        thread, worker = QThread(self), SettingsOperation(function)
        self.operation_thread, self.operation_worker = thread, worker
        worker.moveToThread(thread)
        thread.started.connect(worker.run)
        worker.done.connect(self._operation_done)
        worker.failed.connect(self.status.setText)
        worker.done.connect(thread.quit)
        worker.failed.connect(thread.quit)
        worker.done.connect(worker.deleteLater)
        worker.failed.connect(worker.deleteLater)
        thread.finished.connect(self._operation_finished)
        thread.finished.connect(thread.deleteLater)
        thread.start()

    def _operation_done(self, value: Any) -> None:
        self._success(value)

    def _operation_finished(self) -> None:
        self.operation_thread = self.operation_worker = None
        self.progress.hide()
        self.table.setEnabled(True)
        for control in (self.research_button, self.load_button, self.save_policy_button, self.save_key_button, self.model):
            control.setEnabled(True)
        self.refresh_view()

    def _research(self) -> None:
        self._operate(self.steward.review,
                      lambda offers: self.status.setText("Official evidence refreshed. New or changed connections require review; nothing was subscribed or activated."),
                      "Checking official provider documentation and the live free-model catalog…")

    def _automatic_review(self) -> None:
        policy = self.steward.policy()
        if (policy["enabled"] and policy["auto_review"] and self.steward.review_due()
                and self.operation_thread is None and self.jarvis.runtime_profile().mode != RuntimeMode.LOCAL):
            self._research()

    def _approve(self) -> None:
        source = self._source()
        if not source:
            return
        spec = SPECS[source]
        dialog = QDialog(self)
        dialog.setWindowTitle(f"Approve {spec.name} connection")
        dialog.resize(620, 340)
        layout = QVBoxLayout(dialog)
        description = QLabel(
            f"Connect {spec.name} using your own account. This approval lasts seven days and pauses if reviewed documentation changes.\n\n"
            "Requests can include your prompt and relevant JARVIS memory. No account is created, no terms are accepted, and no credit purchase or billing upgrade is performed by JARVIS.\n\n"
            "For free-tier APIs, JARVIS cannot independently verify your account's billing tier. Check it in the provider console."
        )
        description.setWordWrap(True)
        layout.addWidget(description)
        free = QCheckBox("I checked that this account/model uses the free tier or zero-price route.")
        terms = QCheckBox("I reviewed the provider terms for my intended personal or commercial use.")
        fallback = QCheckBox("Allow this connection to receive work automatically if another approved source fails.")
        for control in (free, terms, fallback):
            layout.addWidget(control)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.button(QDialogButtonBox.StandardButton.Ok).setText("Approve connection")
        buttons.button(QDialogButtonBox.StandardButton.Ok).setEnabled(False)
        def ready() -> None:
            buttons.button(QDialogButtonBox.StandardButton.Ok).setEnabled(free.isChecked() and terms.isChecked())
        free.toggled.connect(ready)
        terms.toggled.connect(ready)
        buttons.accepted.connect(dialog.accept)
        buttons.rejected.connect(dialog.reject)
        layout.addWidget(buttons)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            try:
                self.steward.approve_connection(source, free_account_confirmed=free.isChecked(),
                                                terms_reviewed=terms.isChecked(), allow_fallback=fallback.isChecked())
                self.status.setText("Connection approved. Open the provider console, create or choose your key, then load models and Test & enable.")
                self.refresh_view()
            except ValueError as exc:
                self.status.setText(str(exc))

    def _open(self, field: str) -> None:
        source = self._source()
        if not source:
            return
        try:
            if field == "console":
                self.steward.require_connection(source)
            webbrowser.open(getattr(SPECS[source], field))
        except ValueError as exc:
            self.status.setText(str(exc))

    def _save_key(self) -> None:
        try:
            if not self.key_input.text().strip():
                raise ValueError("Enter the key from the approved account.")
            self.hub.save_api_key(self._source(), self.key_input.text())
            self.key_input.clear()
            self._load_models()
        except (ValueError, RuntimeError) as exc:
            self.status.setText(str(exc))

    def _load_models(self) -> None:
        source = self._source()
        def loaded(models: list[dict[str, str]]) -> None:
            self._account_models[source] = models
            self.model.clear()
            for model in models:
                self.model.addItem(model["name"], model["id"])
            preferred = self.model.findData(self.hub.model_for(source))
            if source == "gemini" and preferred < 0:
                preferred = self.model.findData("gemini-flash-latest")
            if preferred >= 0:
                self.model.setCurrentIndex(preferred)
            self.status.setText(f"{SPECS[source].name}: key accepted · {len(models)} models loaded. Choose one, then Test connection & enable model. No inference was made.")
        self._operate(lambda: self.hub.list_models(source), loaded, "Checking the approved account's model catalog…")

    def _activate(self) -> None:
        source = self._source()
        index = self.model.currentIndex()
        model = (self.model.currentData() if index >= 0 and self.model.currentText() == self.model.itemText(index)
                 else self.model.currentText().strip())
        if not model:
            self.status.setText("Choose an available model first.")
            return
        def enabled(value: Any) -> None:
            self.activated.emit(source, model)
            self.status.setText("Model catalog verified and connection enabled. Real inference will consume quota only when you assign work.")
        self._operate(lambda: self.hub.activate_managed(source, model), enabled, "Verifying the selected model against your account…")

    def _revoke(self) -> None:
        if self._source():
            self.steward.revoke(self._source())
            self.status.setText("Approval revoked. The stored key was kept encrypted; new managed requests are blocked.")
            self.refresh_view()
