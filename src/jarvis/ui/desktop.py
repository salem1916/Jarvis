import sys

from PySide6.QtCore import QTimer
from PySide6.QtGui import QCloseEvent
from PySide6.QtWidgets import (
    QApplication,
    QButtonGroup,
    QComboBox,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QPushButton,
    QSizePolicy,
    QStackedWidget,
    QTableWidget,
    QVBoxLayout,
    QWidget,
)

from jarvis.bootstrap import build_application
from jarvis.core.config import (
    JarvisSettings,
    load_settings,
)
from jarvis.core.system_prompt import build_system_prompt
from jarvis.runtime.profile import ModelRole, RuntimeMode
from jarvis.ui.appearance import stylesheet_for
from jarvis.ui.pages.chat_page import ChatPage
from jarvis.ui.pages.memory_page import MemoryPage
from jarvis.ui.pages.permissions_page import PermissionsPage
from jarvis.ui.pages.placeholder_page import PlaceholderPage
from jarvis.ui.pages.provider_assistant_page import ProviderAssistantPage
from jarvis.ui.pages.settings_page import SettingsPage
from jarvis.ui.pages.tasks_page import TasksPage
from jarvis.ui.pages.updates_page import UpdatesPage


class JarvisWindow(QMainWindow):
    """
    Main JARVIS desktop shell.

    Responsibilities:

    - application navigation
    - shared sidebar
    - page container
    - top-level window lifecycle

    Feature-specific UI belongs inside individual pages.
    """

    CHAT_PAGE = 0
    TASKS_PAGE = 1
    PERMISSIONS_PAGE = 2
    MODELS_PAGE = 3
    SETTINGS_PAGE = 4
    LOGS_PAGE = 5
    PROVIDERS_PAGE = 6
    UPDATES_PAGE = 7

    def __init__(self) -> None:
        super().__init__()

        # -------------------------------------------------
        # Build the real JARVIS application.
        # -------------------------------------------------

        self.settings: JarvisSettings = load_settings()

        self.settings.workspace_dir.mkdir(
            parents=True,
            exist_ok=True,
        )

        self.jarvis = build_application(
            self.settings
        )

        self.system_prompt = build_system_prompt(
            self.jarvis.tool_service.registry
        )

        # -------------------------------------------------
        # Window configuration.
        # -------------------------------------------------

        self.setWindowTitle(
            "JARVIS"
        )

        self.resize(
            1180,
            760,
        )

        self.setMinimumSize(
            900,
            600,
        )

        theme = self.jarvis.intelligence.preferences().get("theme", "dark") if self.jarvis.intelligence else "dark"
        self.setStyleSheet(stylesheet_for(theme))

        self._build_interface()

        self._refresh_runtime_sidebar()
        self.chat_page.open_main_requested.connect(self._open_from_companion)
        self.chat_page.desktop_button.setChecked(True)

    def _open_from_companion(self):
        self._navigate_to(self.CHAT_PAGE)
        self.showNormal()
        self.raise_()
        self.activateWindow()
        self.chat_page.input_box.setFocus()

    def _build_interface(self) -> None:
        """
        Build the desktop shell and navigation.
        """

        central = QWidget()

        self.setCentralWidget(
            central
        )

        root_layout = QHBoxLayout(
            central
        )

        root_layout.setContentsMargins(
            16,
            16,
            16,
            16,
        )

        root_layout.setSpacing(
            16
        )

        # =================================================
        # SIDEBAR
        # =================================================

        sidebar = QWidget()

        sidebar.setObjectName(
            "sidebar"
        )

        sidebar.setFixedWidth(
            196
        )

        sidebar_layout = QVBoxLayout(
            sidebar
        )

        sidebar_layout.setContentsMargins(
            18,
            18,
            18,
            18,
        )

        sidebar_layout.setSpacing(
            8
        )

        brand = QLabel(
            "JARVIS"
        )

        brand.setObjectName(
            "brandTitle"
        )

        sidebar_layout.addWidget(
            brand
        )

        subtitle = QLabel(
            "Personal assistant"
        )

        subtitle.setObjectName(
            "mutedText"
        )

        sidebar_layout.addWidget(
            subtitle
        )

        sidebar_layout.addSpacing(
            12
        )

        # -------------------------------------------------
        # New chat
        # -------------------------------------------------

        self.new_chat_button = QPushButton(
            "+ New conversation"
        )

        self.new_chat_button.clicked.connect(
            self._start_new_chat
        )

        sidebar_layout.addWidget(
            self.new_chat_button
        )

        sidebar_layout.addSpacing(
            12
        )

        # -------------------------------------------------
        # Navigation
        # -------------------------------------------------

        self.navigation_group = QButtonGroup(
            self
        )

        self.navigation_group.setExclusive(
            True
        )

        self._add_navigation_button(
            sidebar_layout,
            "Assistant",
            self.CHAT_PAGE,
            checked=True,
        )

        self._add_navigation_button(
            sidebar_layout,
            "Tasks",
            self.TASKS_PAGE,
        )
        self._add_navigation_button(sidebar_layout, "API assistant", self.PROVIDERS_PAGE)
        self._add_navigation_button(sidebar_layout, "Updates", self.UPDATES_PAGE)

        self._add_navigation_button(
            sidebar_layout,
            "Permissions",
            self.PERMISSIONS_PAGE,
        )

        self._add_navigation_button(
            sidebar_layout,
            "Settings",
            self.MODELS_PAGE,
        )

        self._add_navigation_button(
            sidebar_layout,
            "Memory",
            self.SETTINGS_PAGE,
        )

        self._add_navigation_button(
            sidebar_layout,
            "Logs",
            self.LOGS_PAGE,
        )

        self.navigation_group.idClicked.connect(
            self._navigate_to
        )

        sidebar_layout.addStretch()

        # -------------------------------------------------
        # Runtime information
        # -------------------------------------------------

        model_heading = QLabel(
            "MODEL"
        )

        model_heading.setObjectName(
            "sectionTitle"
        )

        sidebar_layout.addWidget(
            model_heading
        )

        self.model_label = QLabel(
            "Loading..."
        )

        self.model_label.setWordWrap(
            True
        )

        sidebar_layout.addWidget(
            self.model_label
        )

        provider_heading = QLabel(
            "PROVIDER"
        )

        provider_heading.setObjectName(
            "sectionTitle"
        )

        sidebar_layout.addWidget(
            provider_heading
        )

        self.provider_label = QLabel(
            "Loading..."
        )

        self.provider_label.setWordWrap(
            True
        )

        sidebar_layout.addWidget(
            self.provider_label
        )

        agent_heading = QLabel(
            "AGENT"
        )

        agent_heading.setObjectName(
            "sectionTitle"
        )

        sidebar_layout.addWidget(
            agent_heading
        )

        self.agent_label = QLabel(
            "Loading..."
        )

        sidebar_layout.addWidget(
            self.agent_label
        )

        mode_heading = QLabel(
            "MODE"
        )

        mode_heading.setObjectName(
            "sectionTitle"
        )

        sidebar_layout.addWidget(
            mode_heading
        )

        self.mode_label = QLabel(
            "Loading..."
        )

        sidebar_layout.addWidget(
            self.mode_label
        )

        self.message_count_label = QLabel(
            "Messages: 0"
        )

        self.message_count_label.setObjectName(
            "mutedText"
        )

        sidebar_layout.addWidget(
            self.message_count_label
        )

        version = QLabel(
            "Your personal workspace"
        )

        version.setObjectName(
            "mutedText"
        )

        sidebar_layout.addWidget(
            version
        )
        for item in (model_heading,self.model_label,provider_heading,self.provider_label,
                     agent_heading,self.agent_label,mode_heading,self.mode_label,self.message_count_label):
            item.hide()

        root_layout.addWidget(
            sidebar
        )

        # =================================================
        # APPLICATION PAGES
        # =================================================

        self.pages = QStackedWidget()

        self.pages.setObjectName(
            "pageStack"
        )

        self.chat_page = ChatPage(
            jarvis=self.jarvis,
            system_prompt=self.system_prompt,
        )

        self.tasks_page = TasksPage(self.jarvis)

        self.permissions_page = PermissionsPage(
            jarvis=self.jarvis,
        )

        self.models_page = SettingsPage(
            jarvis=self.jarvis,
        )

        self.settings_page = MemoryPage(self.jarvis)
        self.provider_assistant_page = ProviderAssistantPage(self.jarvis)

        self.logs_page = PlaceholderPage(
            title="Logs",
            description=(
                "Agent actions, tool calls, security "
                "decisions, and system events will "
                "eventually be visible here."
            ),
        )

        self.pages.addWidget(
            self.chat_page
        )

        self.pages.addWidget(
            self.tasks_page
        )

        self.pages.addWidget(
            self.permissions_page
        )

        self.pages.addWidget(
            self.models_page
        )

        self.pages.addWidget(
            self.settings_page
        )

        self.pages.addWidget(
            self.logs_page
        )
        self.pages.addWidget(self.provider_assistant_page)
        self.updates_page = UpdatesPage(self.jarvis)
        self.pages.addWidget(self.updates_page)
        self.updates_page.unread_changed.connect(lambda count: self.navigation_group.button(self.UPDATES_PAGE).setText(f"Updates ({count})" if count else "Updates"))
        self.updates_page.attention.connect(lambda text: self.statusBar().showMessage(text, 12000))
        self.updates_page.refresh_view()
        for page in (self.tasks_page,self.permissions_page,self.models_page,self.settings_page,
                     self.provider_assistant_page,self.updates_page,self.logs_page):
            page_layout = page.layout()
            if page_layout:
                margin = 0 if page in (self.tasks_page,self.updates_page,self.models_page,self.provider_assistant_page) else 24
                page_layout.setContentsMargins(margin,margin,margin,margin)
                page_layout.setSpacing(14)
            for label in page.findChildren(QLabel):
                label.setWordWrap(True)
            for combo in page.findChildren(QComboBox):
                combo.setSizeAdjustPolicy(QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon)
                combo.setMinimumContentsLength(14)
                combo.setSizePolicy(QSizePolicy.Policy.Expanding,QSizePolicy.Policy.Fixed)
            for table in page.findChildren(QTableWidget):
                table.verticalHeader().setDefaultSectionSize(38)
                table.verticalHeader().hide()
                table.setAlternatingRowColors(True)
                table.setShowGrid(False)
                table.setMinimumHeight(max(140,table.minimumHeight()))
        self.provider_assistant_page.activated.connect(self._use_approved_provider)
        self.provider_assistant_page.policy_changed.connect(self._provider_policy_changed)

        root_layout.addWidget(
            self.pages,
            stretch=1,
        )

        # -------------------------------------------------
        # Cross-page signals
        # -------------------------------------------------

        self.chat_page.message_count_changed.connect(
            self._set_message_count
        )

        self.chat_page.busy_changed.connect(
            self._set_request_busy
        )
        self.chat_page.busy_changed.connect(self.settings_page.setDisabled)
        self.chat_page.busy_changed.connect(self.models_page.setDisabled)

        self.models_page.runtime_changed.connect(
            self._refresh_runtime_sidebar
        )
        self.models_page.appearance_changed.connect(lambda theme: self.setStyleSheet(stylesheet_for(theme)))

    def _add_navigation_button(
        self,
        layout: QVBoxLayout,
        text: str,
        page_id: int,
        *,
        checked: bool = False,
    ) -> None:
        """
        Add one sidebar navigation button.
        """

        button = QPushButton(
            text
        )

        button.setObjectName(
            "navButton"
        )

        button.setCheckable(
            True
        )

        button.setChecked(
            checked
        )

        self.navigation_group.addButton(
            button,
            page_id,
        )

        layout.addWidget(
            button
        )

    def _navigate_to(
        self,
        page_id: int,
    ) -> None:
        """
        Display the requested application page.
        """

        if page_id == self.MODELS_PAGE:
            self.models_page.refresh_view()

        self.pages.setCurrentIndex(
            page_id
        )
        button = self.navigation_group.button(page_id)
        if button is not None:
            button.setChecked(True)

    def _start_new_chat(self) -> None:
        """
        Reset conversation state and return to Chat.
        """

        self.chat_page.start_new_conversation()

        self.pages.setCurrentIndex(
            self.CHAT_PAGE
        )

        chat_button = self.navigation_group.button(
            self.CHAT_PAGE
        )

        if chat_button is not None:
            chat_button.setChecked(
                True
            )

    def _refresh_runtime_sidebar(
        self,
    ) -> None:
        """
        Refresh sidebar runtime information from the trusted
        JARVIS runtime rather than legacy .env defaults.
        """

        profile = self.jarvis.runtime_profile()

        selection = self.jarvis.model_selection(
            ModelRole.MAIN
        )

        if selection is None:
            self.model_label.setText(
                "Auto"
            )

            self.provider_label.setText(
                "Auto"
            )

        else:
            self.model_label.setText(
                selection.model_id
            )

            self.provider_label.setText(
                selection.provider_id
            )

        self.agent_label.setText(
            profile.agent_engine.value
        )

        self.mode_label.setText(
            profile.mode.value
        )
        if self.jarvis.intelligence:
            preferences = self.jarvis.intelligence.preferences()
            if (preferences["source"] == "auto" and profile.mode is not RuntimeMode.LOCAL
                    and (connection := self.jarvis.intelligence.automatic_connection()) is not None):
                self.provider_label.setText(f"auto → {connection[0]}")
                self.model_label.setText(connection[1])
                self.model_label.setWordWrap(True)
            elif preferences["source"] != "auto":
                self.provider_label.setText(preferences["source"].replace("_", " "))
                self.model_label.setText(preferences.get("model") or "Default model")
                self.model_label.setWordWrap(True)

    def _provider_policy_changed(self) -> None:
        hub = self.jarvis.intelligence
        if hub is None:
            return
        policy, preferences = hub.steward.policy(), hub.preferences()
        source = preferences["source"]
        keep = source == "local" or (source == "chatgpt_plan" and not policy["commercial"])
        if policy["enabled"] and not keep:
            try:
                approval = hub.steward.require_connection(source)
                keep = bool(approval.get("active") and approval.get("model") == preferences.get("model"))
            except ValueError:
                keep = False
            if not keep:
                hub.save_preferences("local", "", preferences.get("concise", True), preferences.get("theme", "dark"))
                self.models_page.source.setCurrentIndex(self.models_page.source.findData("local"))
                self.models_page.model.setEditText("")
        self.models_page.refresh_view()
        self._refresh_runtime_sidebar()

    def _use_approved_provider(self, source: str, model: str) -> None:
        self.models_page.source.setCurrentIndex(self.models_page.source.findData(source))
        self.models_page.model.setEditText(model)
        self.models_page.local_only.setChecked(False)
        self.models_page._apply()

    def _set_message_count(
        self,
        count: int,
    ) -> None:
        """
        Update conversation metadata in the sidebar.
        """

        self.message_count_label.setText(
            f"Messages: {count}"
        )

    def _set_request_busy(
        self,
        busy: bool,
    ) -> None:
        """
        Prevent a conversation reset while an agent
        request is still running.
        """

        self.new_chat_button.setDisabled(
            busy
        )
        self.models_page.setDisabled(busy)
        self.provider_assistant_page.setDisabled(busy)

    def closeEvent(
        self,
        event: QCloseEvent,
    ) -> None:
        """
        Protect an active model request from being
        destroyed while its worker thread is running.

        Proper cancellation comes later.
        """

        if (self.chat_page.request_in_progress or self.chat_page.worker_thread is not None or self.jarvis.agent_team.has_active_jobs()
                or self.models_page.operation_thread is not None
                or self.provider_assistant_page.operation_thread is not None):
            self.chat_page.status_label.setText(
                "Wait for the current chat and agent tasks to finish "
                "before closing JARVIS."
            )

            self.pages.setCurrentIndex(
                self.CHAT_PAGE
            )

            event.ignore()

            return

        self.tasks_page.timer.stop()
        self.settings_page.timer.stop()
        self.provider_assistant_page.timer.stop()
        self.updates_page.timer.stop()
        for timer in self.findChildren(QTimer):
            timer.stop()
        self.chat_page.shutdown_ui()
        self.jarvis.shutdown()
        event.accept()


def main() -> None:
    """
    Start JARVIS Desktop.
    """

    qt_app = QApplication(
        sys.argv
    )

    qt_app.setApplicationName(
        "JARVIS"
    )

    window = JarvisWindow()

    window.show()

    raise SystemExit(
        qt_app.exec()
    )


if __name__ == "__main__":
    main()
