from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QComboBox,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from jarvis.core.application import JarvisApplication
from jarvis.runtime.profile import (
    AgentEngineId,
    ModelRole,
    RuntimeMode,
)


class ModelsPage(QWidget):
    """
    Runtime model and agent configuration page.

    This page talks only to JarvisApplication.

    It never creates providers directly and never stores
    credentials.
    """

    runtime_changed = Signal()

    def __init__(
        self,
        jarvis: JarvisApplication,
    ) -> None:
        super().__init__()

        self.jarvis = jarvis
        self._updating_ui = False

        self._build_interface()
        self._sync_from_runtime()

    # =================================================
    # UI
    # =================================================

    def _build_interface(
        self,
    ) -> None:
        root = QVBoxLayout(
            self
        )

        root.setContentsMargins(
            28,
            24,
            28,
            24,
        )

        root.setSpacing(
            18
        )

        title = QLabel(
            "Models & Agents"
        )

        title.setObjectName(
            "pageTitle"
        )

        root.addWidget(
            title
        )

        description = QLabel(
            "Choose how JARVIS thinks. Local models run on "
            "this computer. Cloud providers and Hermes can "
            "be added without changing the trusted JARVIS "
            "tool and permission layer."
        )

        description.setObjectName(
            "mutedText"
        )

        description.setWordWrap(
            True
        )

        root.addWidget(
            description
        )

        # =================================================
        # RUNTIME
        # =================================================

        runtime_card = QFrame()

        runtime_layout = QGridLayout(
            runtime_card
        )

        runtime_layout.setContentsMargins(
            18,
            18,
            18,
            18,
        )

        runtime_layout.setHorizontalSpacing(
            18
        )

        runtime_layout.setVerticalSpacing(
            12
        )

        runtime_heading = QLabel(
            "RUNTIME"
        )

        runtime_heading.setObjectName(
            "sectionTitle"
        )

        runtime_layout.addWidget(
            runtime_heading,
            0,
            0,
            1,
            2,
        )

        # -------------------------------------------------
        # AI mode
        # -------------------------------------------------

        mode_label = QLabel(
            "AI mode"
        )

        runtime_layout.addWidget(
            mode_label,
            1,
            0,
        )

        self.mode_combo = QComboBox()

        self.mode_combo.addItem(
            "Auto",
            RuntimeMode.AUTO.value,
        )

        self.mode_combo.addItem(
            "Local",
            RuntimeMode.LOCAL.value,
        )

        self.mode_combo.addItem(
            "Smart",
            RuntimeMode.SMART.value,
        )

        self.mode_combo.addItem(
            "Maximum",
            RuntimeMode.MAXIMUM.value,
        )

        self.mode_combo.currentIndexChanged.connect(
            self._on_mode_changed
        )

        runtime_layout.addWidget(
            self.mode_combo,
            1,
            1,
        )

        mode_help = QLabel(
            "The preference is saved now. Automatic model "
            "routing will consume this setting when the "
            "ModelRouter is added."
        )

        mode_help.setObjectName(
            "mutedText"
        )

        mode_help.setWordWrap(
            True
        )

        runtime_layout.addWidget(
            mode_help,
            2,
            1,
        )

        # -------------------------------------------------
        # Agent engine
        # -------------------------------------------------

        agent_label = QLabel(
            "Agent engine"
        )

        runtime_layout.addWidget(
            agent_label,
            3,
            0,
        )

        self.agent_combo = QComboBox()

        self.agent_combo.addItem(
            "Auto",
            AgentEngineId.AUTO.value,
        )

        self.agent_combo.addItem(
            "Native JARVIS",
            AgentEngineId.NATIVE.value,
        )

        self.agent_combo.addItem(
            "Hermes — not connected yet",
            AgentEngineId.HERMES.value,
        )

        self.agent_combo.currentIndexChanged.connect(
            self._on_agent_engine_changed
        )

        runtime_layout.addWidget(
            self.agent_combo,
            3,
            1,
        )

        agent_help = QLabel(
            "Native JARVIS is available now. Hermes will be "
            "connected through the AgentEngine abstraction "
            "in the next agent-runtime milestone."
        )

        agent_help.setObjectName(
            "mutedText"
        )

        agent_help.setWordWrap(
            True
        )

        runtime_layout.addWidget(
            agent_help,
            4,
            1,
        )

        root.addWidget(
            runtime_card
        )

        # =================================================
        # MODEL ROLES
        # =================================================

        model_card = QFrame()

        model_layout = QGridLayout(
            model_card
        )

        model_layout.setContentsMargins(
            18,
            18,
            18,
            18,
        )

        model_layout.setHorizontalSpacing(
            18
        )

        model_layout.setVerticalSpacing(
            12
        )

        model_heading = QLabel(
            "MODEL ROLES"
        )

        model_heading.setObjectName(
            "sectionTitle"
        )

        model_layout.addWidget(
            model_heading,
            0,
            0,
            1,
            2,
        )

        main_label = QLabel(
            "Main brain"
        )

        model_layout.addWidget(
            main_label,
            1,
            0,
        )

        self.main_model_combo = QComboBox()

        self.main_model_combo.currentIndexChanged.connect(
            self._on_main_model_changed
        )

        model_layout.addWidget(
            self.main_model_combo,
            1,
            1,
        )

        main_help = QLabel(
            "Changing this model takes effect immediately "
            "for new JARVIS requests."
        )

        main_help.setObjectName(
            "mutedText"
        )

        main_help.setWordWrap(
            True
        )

        model_layout.addWidget(
            main_help,
            2,
            1,
        )

        worker_label = QLabel(
            "Worker brain"
        )

        model_layout.addWidget(
            worker_label,
            3,
            0,
        )

        self.worker_combo = QComboBox()

        self.worker_combo.addItem(
            "Auto — router coming next"
        )

        self.worker_combo.setEnabled(
            False
        )

        model_layout.addWidget(
            self.worker_combo,
            3,
            1,
        )

        coding_label = QLabel(
            "Coding brain"
        )

        model_layout.addWidget(
            coding_label,
            4,
            0,
        )

        self.coding_combo = QComboBox()

        self.coding_combo.addItem(
            "Auto — specialized routing coming later"
        )

        self.coding_combo.setEnabled(
            False
        )

        model_layout.addWidget(
            self.coding_combo,
            4,
            1,
        )

        research_label = QLabel(
            "Research brain"
        )

        model_layout.addWidget(
            research_label,
            5,
            0,
        )

        self.research_combo = QComboBox()

        self.research_combo.addItem(
            "Auto — specialized routing coming later"
        )

        self.research_combo.setEnabled(
            False
        )

        model_layout.addWidget(
            self.research_combo,
            5,
            1,
        )

        root.addWidget(
            model_card
        )

        # =================================================
        # LOCAL MODELS
        # =================================================

        local_card = QFrame()

        local_layout = QVBoxLayout(
            local_card
        )

        local_layout.setContentsMargins(
            18,
            18,
            18,
            18,
        )

        local_layout.setSpacing(
            12
        )

        local_header = QHBoxLayout()

        local_heading = QLabel(
            "LOCAL MODELS"
        )

        local_heading.setObjectName(
            "sectionTitle"
        )

        local_header.addWidget(
            local_heading
        )

        local_header.addStretch()

        self.refresh_button = QPushButton(
            "Refresh Ollama"
        )

        self.refresh_button.clicked.connect(
            self._refresh_ollama
        )

        local_header.addWidget(
            self.refresh_button
        )

        local_layout.addLayout(
            local_header
        )

        self.local_models_label = QLabel()

        self.local_models_label.setWordWrap(
            True
        )

        local_layout.addWidget(
            self.local_models_label
        )

        root.addWidget(
            local_card
        )

        # =================================================
        # STATUS
        # =================================================

        self.status_label = QLabel(
            "Ready."
        )

        self.status_label.setObjectName(
            "mutedText"
        )

        self.status_label.setWordWrap(
            True
        )

        root.addWidget(
            self.status_label
        )

        root.addStretch()

    # =================================================
    # SYNCHRONIZATION
    # =================================================

    def refresh_view(
        self,
    ) -> None:
        """
        Refresh the UI from trusted runtime state without
        contacting external providers.
        """

        self._sync_from_runtime()

    def _sync_from_runtime(
        self,
    ) -> None:
        self._updating_ui = True

        try:
            profile = self.jarvis.runtime_profile()

            self._select_combo_value(
                self.mode_combo,
                profile.mode.value,
            )

            self._select_combo_value(
                self.agent_combo,
                profile.agent_engine.value,
            )

            self._populate_main_models()

            self._update_local_models_text()

        finally:
            self._updating_ui = False

    def _populate_main_models(
        self,
    ) -> None:
        current = self.jarvis.model_selection(
            ModelRole.MAIN
        )

        current_key: str | None = None

        if current is not None:
            current_key = self._model_key(
                current.provider_id,
                current.model_id,
            )

        self.main_model_combo.blockSignals(
            True
        )

        try:
            self.main_model_combo.clear()

            known_keys: set[str] = set()

            for model in self.jarvis.available_models():
                key = self._model_key(
                    model.provider_id,
                    model.model_id,
                )

                known_keys.add(
                    key
                )

                if model.installed:
                    status = "installed"
                else:
                    status = "not verified"

                display = (
                    f"{model.display_name}  "
                    f"— {model.provider_id} "
                    f"({status})"
                )

                self.main_model_combo.addItem(
                    display,
                    key,
                )

            if (
                current is not None
                and current_key not in known_keys
            ):
                self.main_model_combo.addItem(
                    (
                        f"{current.model_id} — "
                        f"{current.provider_id} "
                        "(currently selected, not detected)"
                    ),
                    current_key,
                )

            if current_key is not None:
                self._select_combo_value(
                    self.main_model_combo,
                    current_key,
                )

        finally:
            self.main_model_combo.blockSignals(
                False
            )

    def _update_local_models_text(
        self,
    ) -> None:
        models = self.jarvis.models_for_provider(
            "ollama"
        )

        if not models:
            self.local_models_label.setText(
                "No local Ollama models are currently known. "
                "Start Ollama and press Refresh Ollama."
            )

            return

        lines: list[str] = []

        for model in models:
            if model.installed:
                status = "Installed ✓"
            else:
                status = "Configured · not verified"

            lines.append(
                f"{model.display_name}    {status}"
            )

        self.local_models_label.setText(
            "\n".join(
                lines
            )
        )

    # =================================================
    # USER ACTIONS
    # =================================================

    def _on_mode_changed(
        self,
        _index: int,
    ) -> None:
        if self._updating_ui:
            return

        raw_mode = self.mode_combo.currentData()

        if not isinstance(
            raw_mode,
            str,
        ):
            return

        mode = RuntimeMode(
            raw_mode
        )

        self.jarvis.set_runtime_mode(
            mode
        )

        self.status_label.setText(
            f"AI mode preference saved: {mode.value}."
        )

        self.runtime_changed.emit()

    def _on_agent_engine_changed(
        self,
        _index: int,
    ) -> None:
        if self._updating_ui:
            return

        raw_engine = self.agent_combo.currentData()

        if not isinstance(
            raw_engine,
            str,
        ):
            return

        engine = AgentEngineId(
            raw_engine
        )

        if engine is AgentEngineId.HERMES:
            self.status_label.setText(
                "Hermes is visible in the architecture, but "
                "its runtime adapter is not connected yet. "
                "JARVIS remains on the current agent engine."
            )

            self._sync_from_runtime()

            return

        self.jarvis.set_agent_engine(
            engine
        )

        self.status_label.setText(
            "Agent engine preference saved: "
            f"{engine.value}."
        )

        self.runtime_changed.emit()

    def _on_main_model_changed(
        self,
        _index: int,
    ) -> None:
        if self._updating_ui:
            return

        raw_key = self.main_model_combo.currentData()

        if not isinstance(
            raw_key,
            str,
        ):
            return

        parsed = self._parse_model_key(
            raw_key
        )

        if parsed is None:
            self.status_label.setText(
                "Could not understand the selected model."
            )

            return

        provider_id, model_id = parsed

        try:
            self.jarvis.set_model_for_role(
                ModelRole.MAIN,
                provider_id,
                model_id,
            )

        except (
            KeyError,
            RuntimeError,
            ValueError,
        ) as exc:
            self.status_label.setText(
                f"Could not switch model: {exc}"
            )

            self._sync_from_runtime()

            return

        self.status_label.setText(
            "Main model switched to "
            f"{provider_id} / {model_id}."
        )

        self.runtime_changed.emit()

    def _refresh_ollama(
        self,
    ) -> None:
        self.refresh_button.setEnabled(
            False
        )

        self.status_label.setText(
            "Checking local Ollama models..."
        )

        try:
            models = self.jarvis.refresh_models(
                "ollama"
            )

        except (
            RuntimeError,
            TypeError,
            ValueError,
        ) as exc:
            self.status_label.setText(
                "Could not reach Ollama. "
                f"{exc}"
            )

            return

        finally:
            self.refresh_button.setEnabled(
                True
            )

        self._sync_from_runtime()

        count = len(
            models
        )

        self.status_label.setText(
            f"Ollama refresh complete. "
            f"{count} installed model(s) found."
        )

    # =================================================
    # HELPERS
    # =================================================

    @staticmethod
    def _model_key(
        provider_id: str,
        model_id: str,
    ) -> str:
        """
        Use a separator that normal Ollama model IDs do not
        require us to parse around.
        """

        return (
            f"{provider_id}\0"
            f"{model_id}"
        )

    @staticmethod
    def _parse_model_key(
        key: str,
    ) -> tuple[
        str,
        str,
    ] | None:
        if "\0" not in key:
            return None

        provider_id, model_id = key.split(
            "\0",
            1,
        )

        if (
            not provider_id
            or not model_id
        ):
            return None

        return (
            provider_id,
            model_id,
        )

    @staticmethod
    def _select_combo_value(
        combo: QComboBox,
        value: str,
    ) -> None:
        index = combo.findData(
            value
        )

        if index >= 0:
            combo.setCurrentIndex(
                index
            )