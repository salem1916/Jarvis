"""Grouped native settings with explicit account and inference-source controls."""

from __future__ import annotations

import webbrowser
from collections.abc import Callable
from threading import Event
from typing import Any

from PySide6.QtCore import QObject, QThread, Signal
from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPlainTextEdit,
    QProgressBar,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from jarvis.core.application import JarvisApplication
from jarvis.models.chatgpt_account import USAGE_URL
from jarvis.runtime.intelligence import API_SOURCES, SOURCES
from jarvis.runtime.profile import AgentEngineId, RuntimeMode
from jarvis.tools.browser_mcp import BrowserMCPTool
from jarvis.ui.pages.models_page import ModelsPage
from jarvis.ui.toggle import ToggleSwitch


class SettingsOperation(QObject):
    done = Signal(object)
    failed = Signal(str)

    def __init__(self, operation: Callable[[], Any]) -> None:
        super().__init__()
        self.operation = operation

    def run(self) -> None:
        try:
            result = self.operation()
        except Exception as exc:  # noqa: BLE001 -- no network errors may escape a Qt worker
            self.failed.emit(str(exc) if isinstance(exc, ValueError) else
                             "The connection did not finish. Check your network and try again.")
        else:
            self.done.emit(result)


class SettingsPage(QWidget):
    runtime_changed = Signal()
    appearance_changed = Signal(str)

    def __init__(self, jarvis: JarvisApplication) -> None:
        super().__init__()
        self.jarvis = jarvis
        assert jarvis.intelligence is not None
        self.hub = jarvis.intelligence
        self.operation_thread: QThread | None = None
        self.operation_worker: SettingsOperation | None = None
        self.cancel_operation = Event()
        self._on_success: Callable[[Any], None] = lambda result: None
        self._plan_models: list[dict[str, str]] = []
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        content = QWidget()
        content.setObjectName("settingsContent")
        layout = QVBoxLayout(content)
        layout.setContentsMargins(28, 24, 28, 28)
        layout.setSpacing(18)
        title = QLabel("Settings")
        title.setObjectName("pageTitle")
        layout.addWidget(title)
        subtitle = QLabel("Make JARVIS feel like yours.")
        subtitle.setObjectName("mutedText")
        layout.addWidget(subtitle)

        account = self._card(layout, "ChatGPT account")
        self.account_label = QLabel()
        self.account_label.setWordWrap(True)
        account.addWidget(self.account_label)
        self.account_combo = QComboBox()
        self.account_combo.currentIndexChanged.connect(self._select_account)
        account.addWidget(self.account_combo)
        row = QHBoxLayout()
        self.connect_button = QPushButton("Continue with ChatGPT")
        self.connect_button.setObjectName("primaryButton")
        self.connect_button.clicked.connect(lambda: self._sign_in(False))
        self.add_button = QPushButton("Add account")
        self.add_button.clicked.connect(lambda: self._sign_in(True))
        self.signout_button = QPushButton("Sign out")
        self.signout_button.clicked.connect(self._sign_out)
        for button in (self.connect_button, self.add_button, self.signout_button):
            row.addWidget(button)
        account.addLayout(row)
        usage = QPushButton("Manage ChatGPT usage and credits ↗")
        usage.setObjectName("linkButton")
        usage.clicked.connect(lambda: webbrowser.open(USAGE_URL))
        account.addWidget(usage)
        note = QLabel("Plan access is optional and depends on your account. Signing in does not connect your ChatGPT conversations or memories. Credit permissions stay in ChatGPT.")
        note.setWordWrap(True)
        note.setObjectName("mutedText")
        account.addWidget(note)

        intelligence = self._card(layout, "Intelligence")
        self.source = QComboBox()
        for key, name in SOURCES.items():
            self.source.addItem(name, key)
        self._row(intelligence, "Default connection", "Automatic keeps simple actions local, then uses your previously selected API for reasoning.", self.source)
        self.model = QComboBox()
        self.model.setEditable(True)
        self.model.setPlaceholderText("Choose or enter a model")
        self._row(intelligence, "Model", "ChatGPT choices come from your signed-in account.", self.model)
        self.load_models_button = QPushButton("Load available models")
        self.load_models_button.clicked.connect(self._load_models)
        intelligence.addWidget(self.load_models_button)
        self.local_only = ToggleSwitch()
        self._row(intelligence, "Local only", "Blocks cloud models, including assigned agents.", self.local_only)
        self.concise = ToggleSwitch()
        self._row(intelligence, "Concise replies", "Short answers by default; uses a lower thinking budget on supported Gemini text models.", self.concise)
        self.source.currentIndexChanged.connect(self._source_changed)

        api = self._card(layout, "API connections")
        self.key_source = QComboBox()
        for source in API_SOURCES:
            self.key_source.addItem(SOURCES[source], source)
        self._row(api, "Provider", "Free tiers have limits. Check the provider's own billing settings.", self.key_source)
        self.key_input = QLineEdit()
        self.key_input.setEchoMode(QLineEdit.EchoMode.Password)
        self.key_input.setPlaceholderText("Paste an API key here")
        self._row(api, "API key", "Saved encrypted for your Windows account.", self.key_input)
        self.key_status = QLabel()
        api.addWidget(self.key_status)
        self.key_button = QPushButton("Save key & load models")
        key_button = self.key_button
        key_button.clicked.connect(self._save_key)
        api.addWidget(key_button)
        self.usage_view = QPlainTextEdit()
        self.usage_view.setReadOnly(True)
        self.usage_view.setMaximumHeight(160)
        api.addWidget(self.usage_view)
        refresh_usage = QPushButton("Refresh usage / available balance")
        refresh_usage.clicked.connect(self._refresh_usage)
        api.addWidget(refresh_usage)
        dashboard = QPushButton("Open provider quota / credits dashboard ↗")
        dashboard.clicked.connect(self._usage_dashboard)
        api.addWidget(dashboard)
        self.key_source.currentIndexChanged.connect(self._key_status)

        integrations = self._card(layout,"Browser & desktop integrations")
        self.browser_mode = QComboBox()
        self.browser_mode.addItem("Current Chrome tab","system")
        if jarvis.integrations is None or not jarvis.integrations.chrome_tab_only:
            self.browser_mode.addItem("My Chrome tabs · Playwright extension","extension")
            self.browser_mode.addItem("Separate Jarvis browser","isolated")
        self._row(integrations,"Browser connection","Use the selected tab in regular Chrome. Public pages can be read in the background.",self.browser_mode)
        self.browser_profile = QLineEdit();self.browser_profile.setPlaceholderText("Automatic, Default, or Profile 1")
        self._row(integrations,"Chrome profile","Optional Chrome profile directory name. Leave empty to use the last active profile.",self.browser_profile)
        self.windows_mcp = ToggleSwitch()
        self._row(integrations,"Windows-MCP","Local desktop tools. Screen access and action permissions still apply.",self.windows_mcp)
        self.integration_apply = QPushButton("Apply integration settings")
        self.integration_apply.clicked.connect(self._apply_integrations)
        integrations.addWidget(self.integration_apply)
        self.windows_check = QPushButton("Check Windows-MCP connection")
        self.windows_check.clicked.connect(self._check_windows_mcp)
        integrations.addWidget(self.windows_check)
        if jarvis.integrations is not None:
            values = jarvis.integrations.status()
            self.browser_mode.setCurrentIndex(self.browser_mode.findData(values["browser_mode"]))
            self.browser_profile.setText(values["profile"])
            self.windows_mcp.setChecked(values["windows_enabled"])
            if jarvis.integrations.grounded_planner_available:
                grounded = ToggleSwitch()
                grounded.setChecked(jarvis.integrations.grounded_planner)
                grounded.toggled.connect(self._set_grounded_planner)
                self._row(integrations, "Grounded browser planner (trial)",
                          "Uses the saved Groq connection for public-page analysis. Your chat provider is separate.",
                          grounded)

        web = self._card(layout, "Web research")
        web_status = QLabel("Tavily · free keyless search and extraction. JARVIS plans queries, checks source relevance, and retries at most once. Rate limits apply; no account or paid upgrade is enabled.")
        web_status.setWordWrap(True)
        web.addWidget(web_status)
        web_details = QPushButton("Search service details ↗")
        web_details.clicked.connect(lambda: webbrowser.open("https://docs.tavily.com/documentation/keyless"))
        web.addWidget(web_details)
        web_control = QLabel("Playwright can inspect, navigate, click and fill observed browser controls. Choose your browser connection above. Search uses the selected reasoning model and browser permission.")
        web_control.setWordWrap(True)
        web.addWidget(web_control)
        mcp_check = QPushButton("Check browser tool server")
        mcp_check.clicked.connect(self._check_browser_mcp)
        web.addWidget(mcp_check)
        example = QLabel("Try in Chat: browser: Open https://www.python.org and find its contact information")
        example.setWordWrap(True)
        web.addWidget(example)


        appearance = self._card(layout, "Appearance & interaction")
        self.theme = QComboBox()
        self.theme.addItem("Dark", "dark")
        self.theme.addItem("Light", "light")
        self._row(appearance, "Appearance", "A quiet interface with rounded controls and grouped settings.", self.theme)
        voice = QLabel("Voice uses local Whisper and Kokoro, with Pipecat turn detection. Open Controls → Voice to choose devices and listening mode.")
        voice.setWordWrap(True)
        voice.setObjectName("mutedText")
        appearance.addWidget(voice)
        advanced = QPushButton("Advanced model roles…")
        advanced.clicked.connect(self._advanced)
        appearance.addWidget(advanced)

        self.apply_button = QPushButton("Apply preferences")
        self.apply_button.setObjectName("primaryButton")
        self.apply_button.clicked.connect(self._apply)
        layout.addWidget(self.apply_button)
        self.progress = QProgressBar()
        self.progress.setRange(0, 0)
        self.progress.setFixedHeight(4)
        self.progress.hide()
        layout.addWidget(self.progress)
        self.cancel_button = QPushButton("Cancel connection")
        self.cancel_button.clicked.connect(self.cancel_operation.set)
        self.cancel_button.hide()
        layout.addWidget(self.cancel_button)
        self.status = QLabel("")
        self.status.setWordWrap(True)
        layout.addWidget(self.status)
        layout.addStretch()
        scroll.setWidget(content)
        root.addWidget(scroll, 1)
        # Keep connection progress and Apply visible while the settings scroll.
        for control in (self.apply_button, self.progress, self.cancel_button, self.status):
            layout.removeWidget(control)
        footer = QWidget()
        footer_layout = QVBoxLayout(footer)
        footer_layout.setContentsMargins(28, 8, 28, 16)
        footer_layout.addWidget(self.progress)
        actions = QHBoxLayout()
        actions.addWidget(self.status, 1)
        actions.addWidget(self.cancel_button)
        actions.addWidget(self.apply_button)
        footer_layout.addLayout(actions)
        root.addWidget(footer)
        prefs = self.hub.preferences()
        self.source.setCurrentIndex(self.source.findData(prefs["source"]))
        if prefs["source"] != "auto":
            self.model.setEditText(prefs.get("model", ""))
        else:
            self._source_changed()
        self.concise.setChecked(prefs.get("concise", True))
        self.theme.setCurrentIndex(self.theme.findData(prefs.get("theme", "dark")))
        self.local_only.setChecked(self.jarvis.runtime_profile().mode == RuntimeMode.LOCAL)
        self.refresh_view()

    @staticmethod
    def _card(parent: QVBoxLayout, title: str) -> QVBoxLayout:
        frame = QFrame()
        frame.setObjectName("settingsCard")
        box = QVBoxLayout(frame)
        box.setContentsMargins(20, 18, 20, 18)
        box.setSpacing(14)
        heading = QLabel(title)
        heading.setObjectName("sectionHeading")
        box.addWidget(heading)
        parent.addWidget(frame)
        return box

    @staticmethod
    def _row(parent: QVBoxLayout, title: str, description: str, control: QWidget) -> None:
        row = QHBoxLayout()
        labels = QVBoxLayout()
        labels.setSpacing(3)
        labels.addWidget(QLabel(title))
        detail = QLabel(description)
        detail.setObjectName("mutedText")
        detail.setWordWrap(True)
        labels.addWidget(detail)
        row.addLayout(labels, 1)
        control.setMaximumWidth(350)
        control.setAccessibleName(title)
        row.addWidget(control, 1 if isinstance(control, (QComboBox, QLineEdit)) else 0)
        parent.addLayout(row)

    def refresh_view(self) -> None:
        session = self.hub.account.session()
        self.account_label.setText(
            f"{session['email']} · " + ("Plan usage allowed" if session.get("sharing") else "Plan usage not enabled")
            if session.get("connected") else "Connect your ChatGPT plan to use its included usage in JARVIS."
        )
        self.signout_button.setEnabled(bool(session.get("connected")))
        self.account_combo.blockSignals(True)
        self.account_combo.clear()
        for index, profile in enumerate(self.hub.account.profiles(), start=1):
            self.account_combo.addItem(f"Connection {index} · {profile['email']}", profile["id"])
        selected = self.account_combo.findData(session.get("id"))
        if selected >= 0:
            self.account_combo.setCurrentIndex(selected)
        self.account_combo.blockSignals(False)
        self.account_combo.setVisible(self.account_combo.count() > 0)
        commercial = self.hub.steward.policy()["commercial"]
        self.connect_button.setEnabled(not commercial and self.operation_thread is None)
        self.add_button.setEnabled(not commercial and self.operation_thread is None)
        if commercial:
            self.account_label.setText("Personal ChatGPT plan access is excluded from product preview. Connect a customer-owned, approved provider in API assistant.")
        self._key_status()

    def _apply_integrations(self):
        mode,profile,enabled = self.browser_mode.currentData(),self.browser_profile.text(),self.windows_mcp.isChecked()
        def apply():
            if self.jarvis.integrations is None:raise ValueError("Integrations are unavailable.")
            self.jarvis.integrations.apply(mode,profile,enabled)
            if mode == "system":
                return "Integration settings saved. Links use your current Chrome tab. Public pages are read in the background."
            return ("Integration settings saved. Chrome may ask you to select a tab on the first connection." if mode == "extension"
                    else "Integration settings saved. Jarvis will use its separate browser; no Chrome extension is needed.")
        self._operate(apply,self.status.setText,"Applying local integration settings…")

    def _set_grounded_planner(self, enabled):
        self.jarvis.integrations.grounded_planner = enabled
        self.status.setText("Grounded browser planner enabled." if enabled else "Standard browser planner enabled.")

    def _check_windows_mcp(self):
        def connect():
            if self.jarvis.integrations is None:raise ValueError("Integrations are unavailable.")
            return "Windows-MCP connected · " + ", ".join(self.jarvis.integrations.windows.client.connect())
        self._operate(connect,self.status.setText,"Checking local Windows-MCP tools. No screen is captured…")

    def _check_browser_mcp(self) -> None:
        def connect():
            tool = self.jarvis.tool_service.registry.get("browser_mcp")
            assert isinstance(tool, BrowserMCPTool)
            if tool.client.mode == "system":
                tool.chrome_tab.current_page()
                tool.client.connect()
                return "Current Chrome tab verified. The background public-page reader is ready."
            return "Browser tool server ready · " + ", ".join(tool.client.connect()) + (
                ". Chrome will request a tab connection on the first browser action." if tool.client.mode == "extension" else ". Using a separate Jarvis browser.")
        self._operate(connect, self.status.setText, "Connecting to Playwright MCP and discovering browser tools…")

    def _refresh_usage(self) -> None:
        source = self.key_source.currentData()
        self._operate(lambda: self.hub.usage_report(source, refresh=True), self.usage_view.setPlainText,
                      "Refreshing usage. Only providers with a supported balance endpoint are queried.")

    def _usage_dashboard(self) -> None:
        urls = {"gemini": "https://aistudio.google.com/usage", "groq": "https://console.groq.com/settings/limits",
                "openrouter_free": "https://openrouter.ai/activity", "openai": "https://platform.openai.com/usage"}
        webbrowser.open(urls[self.key_source.currentData()])

    def _key_status(self) -> None:
        if hasattr(self, "usage_view"):
            source = self.key_source.currentData()
            self.usage_view.setPlainText(self.hub.usage_report(source))
        self.key_status.setText("Key configured" if self.hub.api_key(self.key_source.currentData()) else "No key configured")

    def _source_changed(self) -> None:
        source = self.source.currentData()
        self.model.clear()
        if source == "chatgpt_plan":
            self._models_loaded(self._plan_models)
        elif source in API_SOURCES:
            self.model.setEditText(self.hub.model_for(source))
        elif source == "auto":
            connection = self.hub.automatic_connection()
            if connection:
                self.model.addItem(f"Automatic reasoning: {connection[0]} / {connection[1]}", "")
            else:
                self.model.addItem("No connected automatic AI yet · local fallback", "")

    def _model_id(self) -> str:
        if self.model.currentIndex() >= 0 and self.model.currentText() == self.model.itemText(self.model.currentIndex()):
            return self.model.currentData() or self.model.currentText().strip()
        return self.model.currentText().strip()

    def _apply(self) -> None:
        try:
            source, model = self.source.currentData(), self._model_id()
            if source == "chatgpt_plan" and (not self.hub.account.session().get("sharing") or not model):
                raise ValueError("Connect ChatGPT, allow plan usage, and load a model first.")
            if source in API_SOURCES or source == "chatgpt_plan":
                if model and self.model.findData(model) < 0 and model != self.hub.model_for(source):
                    raise ValueError("Load available models and select one from this provider's list.")
            self.hub.save_preferences(source, model, self.concise.isChecked(), self.theme.currentData())
            self.jarvis.set_agent_engine(AgentEngineId.AUTO)
            self.jarvis.set_runtime_mode(RuntimeMode.LOCAL if self.local_only.isChecked() else RuntimeMode.AUTO)
            self.appearance_changed.emit(self.theme.currentData())
            self.runtime_changed.emit()
            self.status.setText("Preferences applied. No paid fallback will be selected if this connection fails.")
        except ValueError as exc:
            self.status.setText(str(exc))

    def _save_key(self) -> None:
        try:
            if not self.key_input.text().strip():
                raise ValueError("Paste a key before saving. Existing keys were kept.")
            self.hub.save_api_key(self.key_source.currentData(), self.key_input.text())
            self.key_input.clear()
            self._key_status()
            source = self.key_source.currentData()
            if self.hub.steward.policy()["enabled"]:
                self.status.setText("Key saved securely. Finish model verification and activation in API assistant.")
                return
            def checked(models: list[dict[str, str]]) -> None:
                self.source.setCurrentIndex(self.source.findData(source))
                self._models_loaded(models)
                if not models:
                    self.status.setText("Key saved, but no models were returned. Check this account's model access.")
                    return
                preferred = self.model.findData(self.hub.model_for(source))
                if source == "gemini" and preferred < 0:
                    preferred = self.model.findData("gemini-flash-latest")
                if preferred >= 0:
                    self.model.setCurrentIndex(preferred)
                self.status.setText(f"{source}: key accepted · {len(models)} models loaded. Choose a model, then Apply preferences to use it. No inference was made.")
            self._operate(lambda: self.hub.list_models(source), checked, f"Key saved. Checking {source} and loading available models…")
        except (ValueError, RuntimeError) as exc:
            self.status.setText(str(exc))

    def _operate(self, operation: Callable[[], Any], success: Callable[[Any], None], text: str) -> None:
        if self.operation_thread is not None:
            return
        self.cancel_operation.clear()
        self._on_success = success
        self.status.setText(text)
        self.progress.show()
        self.cancel_button.show()
        for control in (self.apply_button, self.connect_button, self.add_button,
                        self.signout_button, self.account_combo, self.load_models_button, self.source, self.key_button, self.key_source, self.model):
            control.setEnabled(False)
        thread, worker = QThread(self), SettingsOperation(operation)
        self.operation_thread, self.operation_worker = thread, worker
        worker.moveToThread(thread)
        thread.started.connect(worker.run)
        worker.done.connect(self._operation_done)
        worker.failed.connect(self._operation_failed)
        worker.done.connect(thread.quit)
        worker.failed.connect(thread.quit)
        worker.done.connect(worker.deleteLater)
        worker.failed.connect(worker.deleteLater)
        thread.finished.connect(self._operation_finished)
        thread.finished.connect(thread.deleteLater)
        thread.start()

    def _operation_done(self, result: Any) -> None:
        self._on_success(result)

    def _operation_failed(self, message: str) -> None:
        self.refresh_view()
        self.status.setText(message)

    def _operation_finished(self) -> None:
        self.operation_worker = self.operation_thread = None
        self.progress.hide()
        self.cancel_button.hide()
        for control in (self.apply_button, self.connect_button, self.add_button,
                        self.account_combo, self.load_models_button, self.source, self.key_button, self.key_source, self.model):
            control.setEnabled(True)
        self.refresh_view()

    def _sign_in(self, new_profile: bool) -> None:
        if self.hub.steward.policy()["commercial"]:
            self.status.setText("Personal ChatGPT sign-in is separate from commercial product access.")
            return
        def connect() -> list[dict[str, str]]:
            self.hub.account.sign_in(new_profile=new_profile, cancel=self.cancel_operation)
            return self.hub.account.list_models() if self.hub.account.session().get("sharing") else []

        def connected(models: list[dict[str, str]]) -> None:
            self._plan_models = models
            self.refresh_view()
            if self.source.currentData() == "chatgpt_plan":
                self._models_loaded(models)
            self.status.setText("ChatGPT connected. Choose ChatGPT plan below, select a model, and Apply preferences."
                                if self.hub.account.session().get("sharing") else
                                "Signed in, but plan access was not granted. Reconnect to review that permission.")

        self._operate(connect, connected, "Finish ChatGPT sign-in in your browser. JARVIS will wait here.")

    def _select_account(self) -> None:
        profile = self.account_combo.currentData()
        if profile:
            self.hub.account.select(profile)
            self._plan_models = []
            if self.source.currentData() == "chatgpt_plan":
                self.model.clear()
            self.refresh_view()
            self.status.setText("Account selected. Load its available models before applying ChatGPT plan usage.")

    def _sign_out(self) -> None:
        def signed_out(revoked: bool) -> None:
            self._plan_models = []
            self.refresh_view()
            self.status.setText("Signed out." if revoked else
                                "Signed out locally. Remote revocation was not confirmed; disconnect JARVIS in ChatGPT Settings.")
        self._operate(self.hub.account.sign_out, signed_out, "Signing out…")

    def _load_models(self) -> None:
        source = self.source.currentData()
        self._operate(lambda: self.hub.list_models(source), self._models_loaded, "Loading available models…")

    def _models_loaded(self, models: list[dict[str, str]]) -> None:
        selected = self._model_id()
        self.model.clear()
        for model in models:
            self.model.addItem(model["name"], model["id"])
        index = self.model.findData(selected)
        if index >= 0:
            self.model.setCurrentIndex(index)
        self.status.setText(f"{len(models)} models available." if models else "No models loaded for this connection.")

    def _advanced(self) -> None:
        if self.hub.steward.policy()["enabled"]:
            self.status.setText("Use API assistant for managed connections. Legacy provider roles remain available in personal mode with API management off.")
            return
        dialog = QDialog(self)
        dialog.setWindowTitle("Advanced model roles")
        dialog.resize(1000, 800)
        layout = QVBoxLayout(dialog)
        page = ModelsPage(self.jarvis)
        page.runtime_changed.connect(self.runtime_changed)
        layout.addWidget(page)
        dialog.exec()
