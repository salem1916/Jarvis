from __future__ import annotations

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QComboBox,
    QFrame,
    QGridLayout,
    QLabel,
    QLayout,
    QPushButton,
    QScrollArea,
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
    JARVIS model/provider/agent configuration page.

    The page talks only to JarvisApplication.

    Provider credentials and model construction remain outside
    the UI.
    """

    runtime_changed = Signal()

    def __init__(
        self,
        jarvis: JarvisApplication,
    ) -> None:
        super().__init__()

        self.jarvis = jarvis
        self._updating_ui = False

        self._provider_status: dict[
            str,
            str,
        ] = {}

        self._build_interface()
        self._sync_from_runtime()

    # =================================================
    # UI
    # =================================================

    def _build_interface(
        self,
    ) -> None:
        outer_layout = QVBoxLayout(
            self
        )

        outer_layout.setContentsMargins(
            0,
            0,
            0,
            0,
        )

        scroll_area = QScrollArea()

        scroll_area.setWidgetResizable(
            True
        )

        scroll_area.setFrameShape(
            QFrame.Shape.NoFrame
        )

        content = QWidget()

        content.setObjectName(
            "modelsPageContent"
        )

        root = QVBoxLayout(
            content
        )

        root.setSizeConstraint(
            QLayout.SizeConstraint.SetMinimumSize
        )

        root.setContentsMargins(
            28,
            24,
            28,
            28,
        )

        root.setSpacing(
            18
        )

        scroll_area.setWidget(
            content
        )

        outer_layout.addWidget(
            scroll_area
        )

        # =================================================
        # TITLE
        # =================================================

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
            "Configure how JARVIS thinks. Providers and models "
            "are independent from the trusted JARVIS tool and "
            "security layer. Local and cloud models can be "
            "changed without changing the PC-control system."
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

        runtime_card.setObjectName(
            "modelCard"
        )

        runtime_layout = QGridLayout(
            runtime_card
        )

        runtime_layout.setContentsMargins(
            20,
            18,
            20,
            20,
        )

        runtime_layout.setHorizontalSpacing(
            24
        )

        runtime_layout.setVerticalSpacing(
            14
        )

        runtime_layout.setColumnStretch(
            1,
            1,
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
            "Local Only",
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
            "Auto will eventually choose models using privacy, "
            "latency, cost, capabilities and task difficulty. "
            "Local Only prevents cloud routing."
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
            "Hermes",
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
            "Native JARVIS talks directly to the selected MAIN "
            "model. Hermes handles more agentic workflows while "
            "Windows actions remain behind JARVIS's trusted MCP "
            "bridge and permission layer."
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
        # PROVIDER HUB
        # =================================================

        provider_card = QFrame()

        provider_card.setObjectName(
            "modelCard"
        )

        provider_layout = QGridLayout(
            provider_card
        )

        provider_layout.setContentsMargins(
            20,
            18,
            20,
            20,
        )

        provider_layout.setHorizontalSpacing(
            18
        )

        provider_layout.setVerticalSpacing(
            14
        )

        provider_layout.setColumnStretch(
            1,
            1,
        )

        provider_heading = QLabel(
            "PROVIDER HUB"
        )

        provider_heading.setObjectName(
            "sectionTitle"
        )

        provider_layout.addWidget(
            provider_heading,
            0,
            0,
            1,
            3,
        )

        provider_label = QLabel(
            "Provider"
        )

        provider_layout.addWidget(
            provider_label,
            1,
            0,
        )

        self.provider_combo = QComboBox()

        self.provider_combo.currentIndexChanged.connect(
            self._on_provider_changed
        )

        provider_layout.addWidget(
            self.provider_combo,
            1,
            1,
        )

        self.refresh_provider_button = QPushButton(
            "Refresh Provider"
        )

        self.refresh_provider_button.clicked.connect(
            self._refresh_selected_provider
        )

        provider_layout.addWidget(
            self.refresh_provider_button,
            1,
            2,
        )

        discovery_label = QLabel(
            "Discovery"
        )

        provider_layout.addWidget(
            discovery_label,
            2,
            0,
        )

        self.refresh_all_button = QPushButton(
            "Refresh All Providers"
        )

        self.refresh_all_button.clicked.connect(
            self._refresh_all_providers
        )

        provider_layout.addWidget(
            self.refresh_all_button,
            2,
            1,
            1,
            2,
        )

        self.provider_detail_label = QLabel()

        self.provider_detail_label.setObjectName(
            "mutedText"
        )

        self.provider_detail_label.setWordWrap(
            True
        )

        provider_layout.addWidget(
            self.provider_detail_label,
            3,
            1,
            1,
            2,
        )

        self.provider_catalog_label = QLabel()

        self.provider_catalog_label.setWordWrap(
            True
        )

        provider_layout.addWidget(
            self.provider_catalog_label,
            4,
            0,
            1,
            3,
        )

        root.addWidget(
            provider_card
        )

        # =================================================
        # MAIN MODEL
        # =================================================

        model_card = QFrame()

        model_card.setObjectName(
            "modelCard"
        )

        model_layout = QGridLayout(
            model_card
        )

        model_layout.setContentsMargins(
            20,
            18,
            20,
            20,
        )

        model_layout.setHorizontalSpacing(
            24
        )

        model_layout.setVerticalSpacing(
            14
        )

        model_layout.setColumnStretch(
            1,
            1,
        )

        model_heading = QLabel(
            "MAIN MODEL"
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

        self.main_model_help = QLabel()

        self.main_model_help.setObjectName(
            "mutedText"
        )

        self.main_model_help.setWordWrap(
            True
        )

        model_layout.addWidget(
            self.main_model_help,
            2,
            1,
        )

        root.addWidget(
            model_card
        )

        # =================================================
        # SPECIALIZED BRAINS
        # =================================================

        role_card = QFrame()

        role_card.setObjectName(
            "modelCard"
        )

        role_layout = QGridLayout(
            role_card
        )

        role_layout.setContentsMargins(
            20,
            18,
            20,
            20,
        )

        role_layout.setHorizontalSpacing(
            24
        )

        role_layout.setVerticalSpacing(
            14
        )

        role_layout.setColumnStretch(
            1,
            1,
        )

        role_heading = QLabel(
            "SPECIALIZED BRAINS"
        )

        role_heading.setObjectName(
            "sectionTitle"
        )

        role_layout.addWidget(
            role_heading,
            0,
            0,
            1,
            2,
        )

        worker_label = QLabel(
            "Worker"
        )

        role_layout.addWidget(
            worker_label,
            1,
            0,
        )

        self.worker_combo = QComboBox()

        self.worker_combo.addItem(
            "Auto — Agent Router milestone"
        )

        self.worker_combo.setEnabled(
            False
        )

        role_layout.addWidget(
            self.worker_combo,
            1,
            1,
        )

        coding_label = QLabel(
            "Coding"
        )

        role_layout.addWidget(
            coding_label,
            2,
            0,
        )

        self.coding_combo = QComboBox()

        self.coding_combo.addItem(
            "Auto — specialized coding agent"
        )

        self.coding_combo.setEnabled(
            False
        )

        role_layout.addWidget(
            self.coding_combo,
            2,
            1,
        )

        research_label = QLabel(
            "Research"
        )

        role_layout.addWidget(
            research_label,
            3,
            0,
        )

        self.research_combo = QComboBox()

        self.research_combo.addItem(
            "Auto — specialized research agent"
        )

        self.research_combo.setEnabled(
            False
        )

        role_layout.addWidget(
            self.research_combo,
            3,
            1,
        )

        role_help = QLabel(
            "These roles become active with the Model Router "
            "and Multi-Agent Orchestrator. Each specialist can "
            "eventually use a different model."
        )

        role_help.setObjectName(
            "mutedText"
        )

        role_help.setWordWrap(
            True
        )

        role_layout.addWidget(
            role_help,
            4,
            1,
        )

        root.addWidget(
            role_card
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
        self._sync_from_runtime()

    def _sync_from_runtime(
        self,
    ) -> None:
        self._updating_ui = True

        try:
            profile = (
                self.jarvis.runtime_profile()
            )

            self._select_combo_value(
                self.mode_combo,
                profile.mode.value,
            )

            self._select_combo_value(
                self.agent_combo,
                profile.agent_engine.value,
            )

            self._populate_providers()
            self._populate_main_models()
            self._update_provider_details()
            self._update_provider_catalog()

        finally:
            self._updating_ui = False

    def _populate_providers(
        self,
    ) -> None:
        current_provider = (
            self.provider_combo.currentData()
        )

        main_selection = (
            self.jarvis.model_selection(
                ModelRole.MAIN
            )
        )

        target_provider: str | None = None

        if isinstance(
            current_provider,
            str,
        ):
            target_provider = (
                current_provider
            )

        elif main_selection is not None:
            target_provider = (
                main_selection.provider_id
            )

        self.provider_combo.blockSignals(
            True
        )

        try:
            self.provider_combo.clear()

            providers = sorted(
                self.jarvis.model_providers(),
                key=lambda provider: (
                    provider.display_name.lower()
                ),
            )

            known_ids: set[str] = set()

            for provider in providers:
                known_ids.add(
                    provider.provider_id
                )

                display = (
                    f"{provider.display_name} "
                    f"— {provider.location.value}"
                )

                self.provider_combo.addItem(
                    display,
                    provider.provider_id,
                )

            if (
                (
                    target_provider is None
                    or target_provider not in known_ids
                )
                and main_selection is not None
            ):
                target_provider = (
                    main_selection.provider_id
                )

            if target_provider is not None:
                self._select_combo_value(
                    self.provider_combo,
                    target_provider,
                )

        finally:
            self.provider_combo.blockSignals(
                False
            )

    def _populate_main_models(
        self,
    ) -> None:
        provider_id = (
            self._selected_provider_id()
        )

        current = (
            self.jarvis.model_selection(
                ModelRole.MAIN
            )
        )

        self.main_model_combo.blockSignals(
            True
        )

        try:
            self.main_model_combo.clear()

            if provider_id is None:
                self.main_model_combo.addItem(
                    "No provider selected"
                )

                self.main_model_combo.setEnabled(
                    False
                )

                return

            models = sorted(
                self.jarvis.models_for_provider(
                    provider_id
                ),
                key=lambda model: (
                    model.display_name.lower()
                ),
            )

            if not models:
                self.main_model_combo.addItem(
                    "No discovered models — refresh provider"
                )

                self.main_model_combo.setEnabled(
                    False
                )

                self.main_model_help.setText(
                    "No models are currently known for this "
                    "provider. Configure it if necessary and "
                    "press Refresh Provider."
                )

                return

            self.main_model_combo.setEnabled(
                True
            )

            current_model_id: (
                str
                | None
            ) = None

            if (
                current is not None
                and current.provider_id
                == provider_id
            ):
                current_model_id = (
                    current.model_id
                )

            known_ids: set[str] = set()

            for model in models:
                known_ids.add(
                    model.model_id
                )

                location = (
                    model.location.value
                )

                if location == "local":
                    if model.installed:
                        state = "installed"
                    else:
                        state = "known"

                else:
                    state = "discovered"

                display = (
                    f"{model.display_name} "
                    f"— {location}, {state}"
                )

                self.main_model_combo.addItem(
                    display,
                    model.model_id,
                )

            if (
                current_model_id is not None
                and current_model_id
                not in known_ids
            ):
                self.main_model_combo.addItem(
                    (
                        f"{current_model_id} "
                        "— currently selected"
                    ),
                    current_model_id,
                )

            if current_model_id is not None:
                self._select_combo_value(
                    self.main_model_combo,
                    current_model_id,
                )

            provider_name = (
                self._provider_display_name(
                    provider_id
                )
            )

            self.main_model_help.setText(
                "Selecting a model here changes JARVIS's "
                "active Native MAIN model immediately. "
                f"Current provider: {provider_name}."
            )

        finally:
            self.main_model_combo.blockSignals(
                False
            )

    def _update_provider_details(
        self,
    ) -> None:
        provider_id = (
            self._selected_provider_id()
        )

        if provider_id is None:
            self.provider_detail_label.setText(
                "No provider selected."
            )

            return

        provider = None

        for candidate in (
            self.jarvis.model_providers()
        ):
            if (
                candidate.provider_id
                == provider_id
            ):
                provider = candidate
                break

        if provider is None:
            self.provider_detail_label.setText(
                "Provider metadata is unavailable."
            )

            return

        models = (
            self.jarvis.models_for_provider(
                provider_id
            )
        )

        auth_text = (
            "API key required"
            if provider.requires_api_key
            else "No API key required"
        )

        compatibility = (
            "OpenAI-compatible"
            if provider.openai_compatible
            else "Native JARVIS adapter"
        )

        status = (
            self._provider_status.get(
                provider_id,
                "Not checked this session",
            )
        )

        self.provider_detail_label.setText(
            f"{provider.display_name} · "
            f"{provider.location.value} · "
            f"{auth_text} · "
            f"{compatibility} · "
            f"{len(models)} known model(s) · "
            f"{status}"
        )

    def _update_provider_catalog(
        self,
    ) -> None:
        lines: list[str] = []

        providers = sorted(
            self.jarvis.model_providers(),
            key=lambda provider: (
                provider.display_name.lower()
            ),
        )

        for provider in providers:
            models = (
                self.jarvis.models_for_provider(
                    provider.provider_id
                )
            )

            status = (
                self._provider_status.get(
                    provider.provider_id,
                    "Not checked",
                )
            )

            lines.append(

                    f"{provider.display_name} · "
                    f"{provider.location.value} · "
                    f"{len(models)} model(s) · "
                    f"{status}"

            )

        lines.append(
            ""
        )

        lines.append(
            "Hermes / Codex is an agent-runtime path and "
            "remains separate from the Native provider list."
        )

        self.provider_catalog_label.setText(
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

        raw_mode = (
            self.mode_combo.currentData()
        )

        if not isinstance(
            raw_mode,
            str,
        ):
            return

        mode = RuntimeMode(
            raw_mode
        )

        try:
            self.jarvis.set_runtime_mode(
                mode
            )

        except (
            RuntimeError,
            ValueError,
        ) as exc:
            self.status_label.setText(
                "Could not change AI mode: "
                f"{exc}"
            )

            self._sync_from_runtime()

            return

        self.status_label.setText(
            "AI mode saved: "
            f"{mode.value}."
        )

        self.runtime_changed.emit()

    def _on_agent_engine_changed(
        self,
        _index: int,
    ) -> None:
        if self._updating_ui:
            return

        raw_engine = (
            self.agent_combo.currentData()
        )

        if not isinstance(
            raw_engine,
            str,
        ):
            return

        engine = AgentEngineId(
            raw_engine
        )

        try:
            self.jarvis.set_agent_engine(
                engine
            )

        except (
            RuntimeError,
            ValueError,
        ) as exc:
            self.status_label.setText(
                "Could not switch agent engine: "
                f"{exc}"
            )

            self._sync_from_runtime()

            return

        if engine is AgentEngineId.HERMES:
            message = (
                "Hermes activated. Agentic Windows actions "
                "continue through JARVIS's trusted MCP tools "
                "and permission system."
            )

        elif engine is AgentEngineId.NATIVE:
            message = (
                "Native JARVIS activated."
            )

        else:
            message = (
                "Auto agent mode activated."
            )

        self.status_label.setText(
            message
        )

        self.runtime_changed.emit()

    def _on_provider_changed(
        self,
        _index: int,
    ) -> None:
        if self._updating_ui:
            return

        self._updating_ui = True

        try:
            self._populate_main_models()
            self._update_provider_details()

        finally:
            self._updating_ui = False

    def _on_main_model_changed(
        self,
        _index: int,
    ) -> None:
        if self._updating_ui:
            return

        provider_id = (
            self._selected_provider_id()
        )

        model_id = (
            self.main_model_combo.currentData()
        )

        if (
            provider_id is None
            or not isinstance(
                model_id,
                str,
            )
            or not model_id
        ):
            return

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
                "Could not switch MAIN model: "
                f"{exc}"
            )

            self._sync_from_runtime()

            return

        provider_name = (
            self._provider_display_name(
                provider_id
            )
        )

        self.status_label.setText(
            "MAIN model switched to "
            f"{provider_name} / {model_id}."
        )

        self._update_provider_details()

        self.runtime_changed.emit()

    def _refresh_selected_provider(
        self,
    ) -> None:
        provider_id = (
            self._selected_provider_id()
        )

        if provider_id is None:
            self.status_label.setText(
                "No provider selected."
            )

            return

        self.refresh_provider_button.setEnabled(
            False
        )

        self.refresh_all_button.setEnabled(
            False
        )

        provider_name = (
            self._provider_display_name(
                provider_id
            )
        )

        self.status_label.setText(
            "Checking "
            f"{provider_name}..."
        )

        try:
            models = (
                self.jarvis.refresh_models(
                    provider_id
                )
            )

        except (
            KeyError,
            RuntimeError,
            TypeError,
            ValueError,
        ) as exc:
            self._provider_status[
                provider_id
            ] = (
                "Unavailable or not configured"
            )

            self.status_label.setText(
                f"{provider_name}: {exc}"
            )

        else:
            count = len(
                models
            )

            self._provider_status[
                provider_id
            ] = (
                f"Available — {count} model(s)"
            )

            self.status_label.setText(
                f"{provider_name} refresh complete. "
                f"{count} model(s) discovered."
            )

        finally:
            self.refresh_provider_button.setEnabled(
                True
            )

            self.refresh_all_button.setEnabled(
                True
            )

        self._updating_ui = True

        try:
            self._populate_main_models()
            self._update_provider_details()
            self._update_provider_catalog()

        finally:
            self._updating_ui = False

    def _refresh_all_providers(
        self,
    ) -> None:
        self.refresh_provider_button.setEnabled(
            False
        )

        self.refresh_all_button.setEnabled(
            False
        )

        self.status_label.setText(
            "Refreshing model providers..."
        )

        success_count = 0
        failure_count = 0
        discovered_count = 0

        providers = (
            self.jarvis.model_providers()
        )

        for provider in providers:
            try:
                models = (
                    self.jarvis.refresh_models(
                        provider.provider_id
                    )
                )

            except (
                KeyError,
                RuntimeError,
                TypeError,
                ValueError,
            ):
                failure_count += 1

                self._provider_status[
                    provider.provider_id
                ] = (
                    "Unavailable or not configured"
                )

                continue

            count = len(
                models
            )

            success_count += 1
            discovered_count += count

            self._provider_status[
                provider.provider_id
            ] = (
                f"Available — {count} model(s)"
            )

        self.refresh_provider_button.setEnabled(
            True
        )

        self.refresh_all_button.setEnabled(
            True
        )

        self._updating_ui = True

        try:
            self._populate_main_models()
            self._update_provider_details()
            self._update_provider_catalog()

        finally:
            self._updating_ui = False

        self.status_label.setText(
            "Provider refresh finished. "
            f"{success_count} available, "
            f"{failure_count} unavailable/not configured, "
            f"{discovered_count} model(s) discovered."
        )

    # =================================================
    # HELPERS
    # =================================================

    def _selected_provider_id(
        self,
    ) -> str | None:
        provider_id = (
            self.provider_combo.currentData()
        )

        if not isinstance(
            provider_id,
            str,
        ):
            return None

        provider_id = (
            provider_id.strip()
        )

        if not provider_id:
            return None

        return provider_id

    def _provider_display_name(
        self,
        provider_id: str,
    ) -> str:
        for provider in (
            self.jarvis.model_providers()
        ):
            if (
                provider.provider_id
                == provider_id
            ):
                return (
                    provider.display_name
                )

        return provider_id

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
