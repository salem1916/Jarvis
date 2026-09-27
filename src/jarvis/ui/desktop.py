import sys

from PySide6.QtGui import QCloseEvent
from PySide6.QtWidgets import (
    QApplication,
    QButtonGroup,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QPushButton,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from jarvis.bootstrap import build_application
from jarvis.core.config import (
    JarvisSettings,
    load_settings,
)
from jarvis.core.system_prompt import build_system_prompt
from jarvis.ui.pages.chat_page import ChatPage
from jarvis.ui.pages.permissions_page import PermissionsPage
from jarvis.ui.pages.placeholder_page import PlaceholderPage
from jarvis.ui.theme import APP_STYLESHEET


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

        self.setStyleSheet(
            APP_STYLESHEET
        )

        self._build_interface()

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
            230
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
            "Personal AI System"
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
            "+ New Chat"
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
            "Chat",
            self.CHAT_PAGE,
            checked=True,
        )

        self._add_navigation_button(
            sidebar_layout,
            "Tasks",
            self.TASKS_PAGE,
        )

        self._add_navigation_button(
            sidebar_layout,
            "Permissions",
            self.PERMISSIONS_PAGE,
        )

        self._add_navigation_button(
            sidebar_layout,
            "Models",
            self.MODELS_PAGE,
        )

        self._add_navigation_button(
            sidebar_layout,
            "Settings",
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

        model_label = QLabel(
            self.settings.ollama_model
        )

        sidebar_layout.addWidget(
            model_label
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

        provider_label = QLabel(
            self.settings.model_provider
        )

        sidebar_layout.addWidget(
            provider_label
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
            "JARVIS Core v0.1"
        )

        version.setObjectName(
            "mutedText"
        )

        sidebar_layout.addWidget(
            version
        )

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

        self.tasks_page = PlaceholderPage(
            title="Tasks",
            description=(
                "Persistent and background tasks will "
                "appear here once the JARVIS task engine "
                "is implemented."
            ),
        )

        self.permissions_page = PermissionsPage(
            jarvis=self.jarvis,
        )

        self.models_page = PlaceholderPage(
            title="Models",
            description=(
                "Model selection and the future ModelRouter "
                "will be managed here."
            ),
        )

        self.settings_page = PlaceholderPage(
            title="Settings",
            description=(
                "General JARVIS configuration will be "
                "managed here."
            ),
        )

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

        self.pages.setCurrentIndex(
            page_id
        )

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

    def closeEvent(
        self,
        event: QCloseEvent,
    ) -> None:
        """
        Protect an active model request from being
        destroyed while its worker thread is running.

        Proper cancellation comes later.
        """

        if self.chat_page.request_in_progress:
            self.chat_page.status_label.setText(
                "Wait for the current request to finish "
                "before closing JARVIS."
            )

            self.pages.setCurrentIndex(
                self.CHAT_PAGE
            )

            event.ignore()

            return

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