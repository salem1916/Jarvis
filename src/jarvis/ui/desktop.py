import sys

from PySide6.QtCore import QObject, QThread, Signal
from PySide6.QtGui import QCloseEvent, QFont
from PySide6.QtWidgets import (
    QApplication,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QPlainTextEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from jarvis.bootstrap import build_application
from jarvis.core.application import JarvisApplication
from jarvis.core.config import JarvisSettings, load_settings
from jarvis.core.system_prompt import build_system_prompt


class AskWorker(QObject):
    """
    Run one JARVIS request in a background thread.

    Ollama inference may take several seconds.

    If we called the model directly from the Qt GUI thread,
    the entire desktop window would freeze until the model
    finished responding.

    Instead:

        GUI thread
            ↓
        AskWorker
            ↓
        background QThread
            ↓
        JarvisApplication
    """

    finished = Signal(str)
    failed = Signal(str)

    def __init__(
        self,
        app: JarvisApplication,
        prompt: str,
        system_prompt: str,
    ) -> None:
        super().__init__()

        self.app = app
        self.prompt = prompt
        self.system_prompt = system_prompt

    def run(self) -> None:
        """
        Send the user's request through the real JARVIS core.
        """

        try:
            result = self.app.ask_with_tools(
                prompt=self.prompt,
                system_prompt=self.system_prompt,
            )

        except Exception as exc:  # noqa: BLE001
            # Desktop UI v0.1 keeps error handling simple.
            #
            # Later we will introduce structured application
            # errors and dedicated UI error messages.
            self.failed.emit(
                str(exc)
            )

            return

        self.finished.emit(
            result
        )


class JarvisWindow(QMainWindow):
    """
    First real JARVIS desktop application.

    This window is only an interface.

    It does NOT contain model logic, tool logic,
    permission logic, or conversation logic.

    Those remain inside the existing JARVIS core.
    """

    def __init__(self) -> None:
        super().__init__()

        # -------------------------------------------------
        # Load JARVIS configuration.
        # -------------------------------------------------

        self.settings: JarvisSettings = load_settings()

        self.settings.workspace_dir.mkdir(
            parents=True,
            exist_ok=True,
        )

        # -------------------------------------------------
        # Build the SAME JarvisApplication used by the CLI.
        # -------------------------------------------------

        self.jarvis = build_application(
            self.settings
        )

        self.system_prompt = build_system_prompt(
            self.jarvis.tool_service.registry
        )

        # -------------------------------------------------
        # Background request state.
        # -------------------------------------------------

        self.worker_thread: QThread | None = None
        self.worker: AskWorker | None = None

        self.request_in_progress = False

        # -------------------------------------------------
        # Window configuration.
        # -------------------------------------------------

        self.setWindowTitle(
            "JARVIS"
        )

        self.resize(
            1100,
            720,
        )

        self.setMinimumSize(
            820,
            560,
        )

        self._build_interface()
        self._apply_style()

    def _build_interface(self) -> None:
        """
        Build the initial JARVIS layout.

        Structure:

            ┌──────────────┬─────────────────────────┐
            │ Sidebar      │ Conversation            │
            │              │                         │
            │ New Chat     │ Messages                │
            │ Model        │                         │
            │ Provider     │                         │
            │              │                         │
            │ Status       │ Input            Send   │
            └──────────────┴─────────────────────────┘
        """

        central_widget = QWidget()

        self.setCentralWidget(
            central_widget
        )

        root_layout = QHBoxLayout(
            central_widget
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
            220
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
            14
        )

        # -------------------------------------------------
        # JARVIS title
        # -------------------------------------------------

        title = QLabel(
            "JARVIS"
        )

        title.setObjectName(
            "jarvisTitle"
        )

        title_font = QFont()

        title_font.setPointSize(
            22
        )

        title_font.setBold(
            True
        )

        title.setFont(
            title_font
        )

        sidebar_layout.addWidget(
            title
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

        # -------------------------------------------------
        # New conversation button
        # -------------------------------------------------

        self.new_chat_button = QPushButton(
            "New Chat"
        )

        self.new_chat_button.clicked.connect(
            self._start_new_conversation
        )

        sidebar_layout.addWidget(
            self.new_chat_button
        )

        # -------------------------------------------------
        # Model information
        # -------------------------------------------------

        model_title = QLabel(
            "MODEL"
        )

        model_title.setObjectName(
            "sectionTitle"
        )

        sidebar_layout.addWidget(
            model_title
        )

        self.model_label = QLabel(
            self.settings.ollama_model
        )

        sidebar_layout.addWidget(
            self.model_label
        )

        provider_title = QLabel(
            "PROVIDER"
        )

        provider_title.setObjectName(
            "sectionTitle"
        )

        sidebar_layout.addWidget(
            provider_title
        )

        provider_label = QLabel(
            self.settings.model_provider
        )

        sidebar_layout.addWidget(
            provider_label
        )

        # Fill the empty sidebar space.
        sidebar_layout.addStretch()

        # -------------------------------------------------
        # Conversation information
        # -------------------------------------------------

        self.message_count_label = QLabel(
            "Messages: 0"
        )

        self.message_count_label.setObjectName(
            "mutedText"
        )

        sidebar_layout.addWidget(
            self.message_count_label
        )

        core_status = QLabel(
            "JARVIS Core v0.1\nLocal-first"
        )

        core_status.setObjectName(
            "mutedText"
        )

        sidebar_layout.addWidget(
            core_status
        )

        root_layout.addWidget(
            sidebar
        )

        # =================================================
        # CHAT AREA
        # =================================================

        chat_container = QWidget()

        chat_container.setObjectName(
            "chatContainer"
        )

        chat_layout = QVBoxLayout(
            chat_container
        )

        chat_layout.setContentsMargins(
            20,
            20,
            20,
            20,
        )

        chat_layout.setSpacing(
            12
        )

        # -------------------------------------------------
        # Conversation heading
        # -------------------------------------------------

        conversation_title = QLabel(
            "Conversation"
        )

        conversation_font = QFont()

        conversation_font.setPointSize(
            15
        )

        conversation_font.setBold(
            True
        )

        conversation_title.setFont(
            conversation_font
        )

        chat_layout.addWidget(
            conversation_title
        )

        # -------------------------------------------------
        # Chat history display
        #
        # QPlainTextEdit intentionally uses plain text.
        #
        # We do not interpret model/user output as HTML.
        # -------------------------------------------------

        self.chat_view = QPlainTextEdit()

        self.chat_view.setReadOnly(
            True
        )

        self.chat_view.setPlaceholderText(
            "Start a conversation with JARVIS."
        )

        chat_layout.addWidget(
            self.chat_view,
            stretch=1,
        )

        # -------------------------------------------------
        # Input row
        # -------------------------------------------------

        input_container = QWidget()

        input_layout = QHBoxLayout(
            input_container
        )

        input_layout.setContentsMargins(
            0,
            0,
            0,
            0,
        )

        input_layout.setSpacing(
            10
        )

        self.input_box = QLineEdit()

        self.input_box.setPlaceholderText(
            "Ask JARVIS..."
        )

        # Pressing Enter performs the same action
        # as clicking Send.
        self.input_box.returnPressed.connect(
            self._send_message
        )

        input_layout.addWidget(
            self.input_box,
            stretch=1,
        )

        self.send_button = QPushButton(
            "Send"
        )

        self.send_button.clicked.connect(
            self._send_message
        )

        input_layout.addWidget(
            self.send_button
        )

        chat_layout.addWidget(
            input_container
        )

        # -------------------------------------------------
        # Request status
        # -------------------------------------------------

        self.status_label = QLabel(
            "Ready"
        )

        self.status_label.setObjectName(
            "mutedText"
        )

        chat_layout.addWidget(
            self.status_label
        )

        root_layout.addWidget(
            chat_container,
            stretch=1,
        )

        self.input_box.setFocus()

    def _apply_style(self) -> None:
        """
        Apply a simple dark JARVIS theme.

        This is intentionally only a v0.1 visual layer.

        Later we can build a full design system with:
        - reusable components
        - animations
        - navigation pages
        - icons
        - status indicators
        - richer chat bubbles
        """

        self.setStyleSheet(
            """
            QMainWindow {
                background: #111318;
            }

            QWidget {
                color: #e8eaf0;
                font-size: 14px;
            }

            QWidget#sidebar {
                background: #181b22;
                border-radius: 12px;
            }

            QWidget#chatContainer {
                background: #181b22;
                border-radius: 12px;
            }

            QLabel#jarvisTitle {
                color: #65c8ff;
            }

            QLabel#sectionTitle {
                color: #8d94a5;
                font-size: 11px;
                font-weight: bold;
            }

            QLabel#mutedText {
                color: #8d94a5;
            }

            QPlainTextEdit {
                background: #101217;
                border: 1px solid #2b303b;
                border-radius: 10px;
                padding: 12px;
                selection-background-color: #355b72;
            }

            QLineEdit {
                background: #101217;
                border: 1px solid #2b303b;
                border-radius: 9px;
                padding: 11px;
            }

            QLineEdit:focus {
                border: 1px solid #65c8ff;
            }

            QPushButton {
                background: #242a34;
                border: 1px solid #343b48;
                border-radius: 8px;
                padding: 10px 16px;
            }

            QPushButton:hover {
                background: #303744;
            }

            QPushButton:pressed {
                background: #1d222a;
            }

            QPushButton:disabled {
                color: #656b77;
                background: #1b1f26;
            }
            """
        )

    def _send_message(self) -> None:
        """
        Send the current input to JARVIS.
        """

        # Only allow one AI request at a time.
        if self.request_in_progress:
            return

        prompt = self.input_box.text().strip()

        if not prompt:
            return

        # -------------------------------------------------
        # Display the user's message immediately.
        # -------------------------------------------------

        self._append_message(
            "You",
            prompt,
        )

        self.input_box.clear()

        self._set_busy(
            True
        )

        # -------------------------------------------------
        # Create a new worker thread for this request.
        # -------------------------------------------------

        thread = QThread()

        worker = AskWorker(
            app=self.jarvis,
            prompt=prompt,
            system_prompt=self.system_prompt,
        )

        self.worker_thread = thread
        self.worker = worker

        worker.moveToThread(
            thread
        )

        # Start the AI request when the thread starts.
        thread.started.connect(
            worker.run
        )

        # Handle result/error.
        worker.finished.connect(
            self._handle_response
        )

        worker.failed.connect(
            self._handle_error
        )

        # Stop the thread after completion.
        worker.finished.connect(
            thread.quit
        )

        worker.failed.connect(
            thread.quit
        )

        # Schedule Qt object cleanup.
        worker.finished.connect(
            worker.deleteLater
        )

        worker.failed.connect(
            worker.deleteLater
        )

        thread.finished.connect(
            thread.deleteLater
        )

        thread.finished.connect(
            self._clear_worker_references
        )

        thread.start()

    def _append_message(
        self,
        speaker: str,
        message: str,
    ) -> None:
        """
        Add one plain-text message to the chat view.
        """

        self.chat_view.appendPlainText(
            f"{speaker}:"
        )

        self.chat_view.appendPlainText(
            message
        )

        self.chat_view.appendPlainText(
            ""
        )

        # Move the scrollbar to the newest message.
        scrollbar = self.chat_view.verticalScrollBar()

        scrollbar.setValue(
            scrollbar.maximum()
        )

    def _handle_response(
        self,
        response: str,
    ) -> None:
        """
        Display a successful JARVIS response.
        """

        self._append_message(
            "JARVIS",
            response,
        )

        self._update_message_count()

        self._set_busy(
            False
        )

    def _handle_error(
        self,
        error: str,
    ) -> None:
        """
        Display an error without crashing the desktop app.
        """

        self._append_message(
            "JARVIS error",
            error,
        )

        self._set_busy(
            False
        )

    def _set_busy(
        self,
        busy: bool,
    ) -> None:
        """
        Update controls while JARVIS is processing.
        """

        self.request_in_progress = busy

        self.input_box.setDisabled(
            busy
        )

        self.send_button.setDisabled(
            busy
        )

        self.new_chat_button.setDisabled(
            busy
        )

        if busy:
            self.status_label.setText(
                "JARVIS is thinking..."
            )

        else:
            self.status_label.setText(
                "Ready"
            )

            self.input_box.setFocus()

    def _start_new_conversation(self) -> None:
        """
        Reset the real conversation state and clear
        the visible conversation.
        """

        if self.request_in_progress:
            return

        self.jarvis.new_conversation()

        self.chat_view.clear()

        self._update_message_count()

        self.status_label.setText(
            "Started a new conversation."
        )

        self.input_box.setFocus()

    def _update_message_count(self) -> None:
        """
        Display the number of internal conversation messages.

        This includes user messages, assistant messages,
        and tool-result messages.
        """

        count = self.jarvis.conversation_message_count()

        self.message_count_label.setText(
            f"Messages: {count}"
        )

    def _clear_worker_references(self) -> None:
        """
        Remove references after the background request
        has completely finished.
        """

        self.worker = None
        self.worker_thread = None

    def closeEvent(
        self,
        event: QCloseEvent,
    ) -> None:
        """
        Do not destroy JARVIS while a model request is active.

        Proper request cancellation will be added later.
        """

        if self.request_in_progress:
            self.status_label.setText(
                "Wait for the current request to finish "
                "before closing JARVIS."
            )

            event.ignore()

            return

        event.accept()


def main() -> None:
    """
    Start the JARVIS desktop application.
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