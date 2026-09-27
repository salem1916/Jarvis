import json
import threading

from PySide6.QtCore import (
    QObject,
    Qt,
    QThread,
    Signal,
)
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from jarvis.core.action_confirmation import (
    ActionConfirmationRequest,
)
from jarvis.core.application import JarvisApplication


class AskWorker(QObject):
    """
    Execute one JARVIS request outside the GUI thread.

    The worker ALSO acts as the trusted confirmation handler.

    Important:

        Agent runs in worker thread
                ↓
        action requires confirmation
                ↓
        worker emits confirmation_requested
                ↓
        GUI thread shows dialog
                ↓
        user chooses Approve / Deny
                ↓
        worker continues

    The model never receives direct control over the result.
    """

    finished = Signal(str)
    failed = Signal(str)

    # Carries ActionConfirmationRequest to the GUI thread.
    confirmation_requested = Signal(object)

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

        # Python threading.Event is used because the model
        # worker must wait while the GUI remains responsive.
        self._confirmation_event = threading.Event()

        self._confirmation_result = False

    def run(self) -> None:
        """
        Send the request through the real JARVIS core.
        """

        try:
            response = self.jarvis.ask_with_tools(
                prompt=self.prompt,
                system_prompt=self.system_prompt,

                # This AskWorker implements confirm().
                confirmation_handler=self,
            )

        except Exception as exc:  # noqa: BLE001
            self.failed.emit(
                str(exc)
            )

            return

        self.finished.emit(
            response
        )

    def confirm(
        self,
        request: ActionConfirmationRequest,
    ) -> bool:
        """
        Called by AgentService from the worker thread.

        We cannot open Qt dialogs here.

        Instead we notify the GUI thread and wait for its
        explicit human decision.
        """

        self._confirmation_result = False

        self._confirmation_event.clear()

        self.confirmation_requested.emit(
            request
        )

        # This blocks ONLY the AI worker thread.
        #
        # The Qt GUI event loop remains responsive.
        self._confirmation_event.wait()

        return self._confirmation_result

    def resolve_confirmation(
        self,
        approved: bool,
    ) -> None:
        """
        Called by the GUI after the human makes a decision.
        """

        self._confirmation_result = approved

        self._confirmation_event.set()


class ChatPage(QWidget):
    """
    Main conversational JARVIS page.

    Conversation and tool state remain inside
    JarvisApplication.

    This class handles desktop presentation and interaction.
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
        Build the chat page.
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

        # =================================================
        # CHAT HISTORY
        # =================================================

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

        # =================================================
        # MESSAGE INPUT
        # =================================================

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
        Send the current message through JARVIS.
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

        # =================================================
        # BACKGROUND AGENT THREAD
        # =================================================

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

        # -------------------------------------------------
        # Confirmation requests cross from the worker
        # thread into the Qt GUI thread here.
        # -------------------------------------------------

        worker.confirmation_requested.connect(
            self._handle_confirmation_request
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

    def _handle_confirmation_request(
        self,
        raw_request: object,
    ) -> None:
        """
        Show a human approval dialog on the GUI thread.

        The action does NOT execute until this method sends
        the user's decision back to AskWorker.
        """

        if not isinstance(
            raw_request,
            ActionConfirmationRequest,
        ):
            if self.worker is not None:
                self.worker.resolve_confirmation(
                    False
                )

            return

        request = raw_request

        arguments = dict(
            request.arguments
        )

        # -------------------------------------------------
        # Human-friendly summary
        # -------------------------------------------------

        summary_lines = [
            "JARVIS wants permission to perform an action.",
            "",
            f"Tool: {request.tool_name}",
            f"Capability: {request.capability}",
        ]

        if request.tool_name == "write_file":
            path = arguments.get(
                "path",
                "<unknown>"
            )

            overwrite = arguments.get(
                "overwrite",
                False,
            )

            content = arguments.get(
                "content",
                ""
            )

            mode = (
                "Overwrite existing file if present"
                if overwrite
                else "Create new file only"
            )

            preview = (
                content
                if isinstance(
                    content,
                    str,
                )
                else str(
                    content
                )
            )

            # Keep the main dialog readable.
            #
            # The FULL arguments remain available under
            # "Show Details".
            if len(
                preview
            ) > 700:
                preview = (
                    preview[:700]
                    + "\n...[preview truncated]"
                )

            summary_lines.extend(
                [
                    "",
                    f"Path: {path}",
                    f"Mode: {mode}",
                    "",
                    "Content preview:",
                    preview,
                ]
            )

        message_box = QMessageBox(
            self
        )

        message_box.setWindowTitle(
            "Approve JARVIS Action"
        )

        # Never interpret model/tool arguments as rich HTML.
        message_box.setTextFormat(
            Qt.TextFormat.PlainText
        )

        message_box.setText(
            "\n".join(
                summary_lines
            )
        )

        # Full exact tool arguments are available to inspect.
        message_box.setDetailedText(
            json.dumps(
                arguments,
                ensure_ascii=False,
                indent=2,
                default=str,
            )
        )

        message_box.setIcon(
            QMessageBox.Icon.Warning
        )

        message_box.setStandardButtons(
            QMessageBox.StandardButton.Yes
            | QMessageBox.StandardButton.No
        )

        message_box.setButtonText(
            QMessageBox.StandardButton.Yes,
            "Approve Once",
        )

        message_box.setButtonText(
            QMessageBox.StandardButton.No,
            "Deny",
        )

        message_box.setDefaultButton(
            QMessageBox.StandardButton.No
        )

        result = message_box.exec()

        approved = (
            result
            == QMessageBox.StandardButton.Yes
        )

        if self.worker is not None:
            self.worker.resolve_confirmation(
                approved
            )

    def _append_message(
        self,
        speaker: str,
        message: str,
    ) -> None:
        """
        Add one plain-text chat message.
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
        Display a successful JARVIS response.
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
        Display an application error without crashing Qt.
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
        Update UI controls while JARVIS is working.
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

    def start_new_conversation(
        self,
    ) -> None:
        """
        Reset conversation history without changing
        permissions.
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

    def _clear_worker_references(
        self,
    ) -> None:
        """
        Release worker references after the thread exits.
        """

        self.worker = None
        self.worker_thread = None