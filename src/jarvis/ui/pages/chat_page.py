from PySide6.QtCore import (
    QObject,
    QThread,
    Signal,
)
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPlainTextEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from jarvis.core.application import JarvisApplication


class AskWorker(QObject):
    """
    Execute one JARVIS request outside the GUI thread.

    Ollama/model inference can take several seconds.

    Running it directly inside the Qt main thread would
    freeze the user interface.

    Therefore:

        ChatPage
            ↓
        QThread
            ↓
        AskWorker
            ↓
        JarvisApplication
    """

    finished = Signal(str)
    failed = Signal(str)

    def __init__(
        self,
        jarvis: JarvisApplication,
        prompt: str,
        system_prompt: str,
    ) -> None:
        super().__init__()

        self.jarvis = jarvis
        self.prompt = prompt
        self.system_prompt = system_prompt

    def run(self) -> None:
        """
        Send the request through the real JARVIS core.
        """

        try:
            response = self.jarvis.ask_with_tools(
                prompt=self.prompt,
                system_prompt=self.system_prompt,
            )

        except Exception as exc:  # noqa: BLE001
            # UI v0.2 still uses a general error boundary.
            #
            # Later we will expose structured error types
            # to the desktop interface.
            self.failed.emit(
                str(exc)
            )

            return

        self.finished.emit(
            response
        )


class ChatPage(QWidget):
    """
    Main conversational page.

    This page owns only presentation and interaction.

    Conversation state still belongs to
    JarvisApplication.
    """

    message_count_changed = Signal(int)
    busy_changed = Signal(bool)

    def __init__(
        self,
        jarvis: JarvisApplication,
        system_prompt: str,
    ) -> None:
        super().__init__()

        self.jarvis = jarvis
        self.system_prompt = system_prompt

        self.worker_thread: QThread | None = None
        self.worker: AskWorker | None = None

        self.request_in_progress = False

        self._build_interface()

    def _build_interface(self) -> None:
        """
        Build the conversation page.
        """

        layout = QVBoxLayout(
            self
        )

        layout.setContentsMargins(
            24,
            24,
            24,
            24,
        )

        layout.setSpacing(
            12
        )

        title = QLabel(
            "Conversation"
        )

        title.setObjectName(
            "pageTitle"
        )

        layout.addWidget(
            title
        )

        subtitle = QLabel(
            "Talk to JARVIS using the local AI agent."
        )

        subtitle.setObjectName(
            "mutedText"
        )

        layout.addWidget(
            subtitle
        )

        # -------------------------------------------------
        # Chat history
        #
        # Plain text is intentional.
        #
        # User/model output must not be interpreted as
        # arbitrary HTML.
        # -------------------------------------------------

        self.chat_view = QPlainTextEdit()

        self.chat_view.setReadOnly(
            True
        )

        self.chat_view.setPlaceholderText(
            "Start a conversation with JARVIS."
        )

        layout.addWidget(
            self.chat_view,
            stretch=1,
        )

        # -------------------------------------------------
        # Message input
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

        layout.addWidget(
            input_container
        )

        self.status_label = QLabel(
            "Ready"
        )

        self.status_label.setObjectName(
            "mutedText"
        )

        layout.addWidget(
            self.status_label
        )

        self.input_box.setFocus()

    def _send_message(self) -> None:
        """
        Send the current input to the real JARVIS agent.
        """

        if self.request_in_progress:
            return

        prompt = self.input_box.text().strip()

        if not prompt:
            return

        self._append_message(
            "You",
            prompt,
        )

        self.input_box.clear()

        self._set_busy(
            True
        )

        # -------------------------------------------------
        # Create one worker/thread for this request.
        # -------------------------------------------------

        thread = QThread()

        worker = AskWorker(
            jarvis=self.jarvis,
            prompt=prompt,
            system_prompt=self.system_prompt,
        )

        self.worker_thread = thread
        self.worker = worker

        worker.moveToThread(
            thread
        )

        thread.started.connect(
            worker.run
        )

        worker.finished.connect(
            self._handle_response
        )

        worker.failed.connect(
            self._handle_error
        )

        worker.finished.connect(
            thread.quit
        )

        worker.failed.connect(
            thread.quit
        )

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
        Append a plain-text conversation message.
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

        scrollbar = self.chat_view.verticalScrollBar()

        scrollbar.setValue(
            scrollbar.maximum()
        )

    def _handle_response(
        self,
        response: str,
    ) -> None:
        """
        Display a successful model response.
        """

        self._append_message(
            "JARVIS",
            response,
        )

        self.message_count_changed.emit(
            self.jarvis.conversation_message_count()
        )

        self._set_busy(
            False
        )

    def _handle_error(
        self,
        error: str,
    ) -> None:
        """
        Display a recoverable application error.
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
        Update controls while a request is running.
        """

        self.request_in_progress = busy

        self.input_box.setDisabled(
            busy
        )

        self.send_button.setDisabled(
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

        self.busy_changed.emit(
            busy
        )

    def start_new_conversation(self) -> None:
        """
        Reset both the real conversation state
        and visible chat.
        """

        if self.request_in_progress:
            return

        self.jarvis.new_conversation()

        self.chat_view.clear()

        self.status_label.setText(
            "Started a new conversation."
        )

        self.message_count_changed.emit(
            0
        )

        self.input_box.setFocus()

    def _clear_worker_references(self) -> None:
        """
        Release references after the QThread has stopped.
        """

        self.worker = None
        self.worker_thread = None