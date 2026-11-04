import json
import re
import threading
import time

from PySide6.QtCore import (
    QEvent,
    QObject,
    Qt,
    QThread,
    QTimer,
    Signal,
)
from PySide6.QtGui import QKeyEvent, QKeySequence
from PySide6.QtWidgets import (
    QCheckBox,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLayout,
    QLineEdit,
    QMenu,
    QPlainTextEdit,
    QProgressBar,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from jarvis.core.action_confirmation import (
    ActionConfirmationRequest,
)
from jarvis.core.application import JarvisApplication
from jarvis.core.interaction import AssistantEvent, AssistantReply, action_event
from jarvis.core.request_control import RequestControl
from jarvis.ui.atmosphere import AtmosphereFrame
from jarvis.ui.clipboard import copy_text
from jarvis.ui.controls import AssistantControls
from jarvis.ui.orb import AssistantOrb
from jarvis.ui.presence import PHASES, AssistantPresence
from jarvis.ui.screen_panel import ScreenPanel
from jarvis.ui.voice_panel import VoicePanel


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
    delta = Signal(str)
    progress = Signal(str)
    activity = Signal(object)
    reply_ready = Signal(object)

    # Carries ActionConfirmationRequest to the GUI thread.
    confirmation_requested = Signal(object)

    def __init__(
        self,
        jarvis: JarvisApplication,
        prompt: str,
        system_prompt: str,
        input_source: str = "text",
    ) -> None:
        super().__init__()

        self.jarvis = jarvis
        self.prompt = prompt
        self.system_prompt = system_prompt
        self.control = RequestControl(input_source=input_source, on_delta=self.delta.emit, on_status=self.progress.emit, on_event=self.activity.emit)

        # Python threading.Event is used because the model
        # worker must wait while the GUI remains responsive.
        self._confirmation_event = threading.Event()

        self._confirmation_result = False

    def run(self) -> None:
        """
        Send the request through the real JARVIS core.
        """

        try:
            reply = self.jarvis.interact(
                prompt=self.prompt,
                system_prompt=self.system_prompt,

                # This AskWorker implements confirm().
                confirmation_handler=self,
                request_control=self.control,
            )

        except Exception as exc:  # noqa: BLE001
            self.failed.emit(
                str(exc)
            )

            return

        self.reply_ready.emit(reply)
        self.finished.emit(reply.message)

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
        while not self._confirmation_event.wait(0.1):
            self.control.check()

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
    open_main_requested = Signal()

    def __init__(
        self,
        jarvis: JarvisApplication,
        system_prompt: str,
    ) -> None:
        super().__init__()

        self.jarvis = jarvis
        self.system_prompt = system_prompt
        self.presence = AssistantPresence(self)
        self.companion = None
        self._companion_mic_pending = False
        self._audio_phase = "idle"
        self._visual_error = False

        self.worker_thread: QThread | None = None
        self.worker: AskWorker | None = None

        self.request_in_progress = False
        self._streaming = False
        self._streamed_text = ""
        self._action_turn = False
        self._reply: AssistantReply | None = None
        self._pending_prompt = ""
        self._pending_input_source = "text"
        self._next_input_source = "text"
        self._approval_token = None
        self._approval_worker: AskWorker | None = None
        self._choice_buttons: list[QPushButton] = []
        self._pending_text = ""
        self._voice_reply_suppressed = False
        self._spoken_progress_at = 0.0
        self._voice_hold = False
        self._render_timer = QTimer(self)
        self._render_timer.setInterval(30)
        self._render_timer.timeout.connect(self._flush_delta)

        self._build_interface()
        self._refresh_presence()
        self._presence_labels()

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
            "Jarvis"
        )

        title.setObjectName(
            "pageTitle"
        )

        header = QHBoxLayout();header.addWidget(title);header.addStretch()
        self.history_button = QPushButton("Conversation");self.history_button.setCheckable(True)
        self.desktop_button = QPushButton("Desktop orb");self.desktop_button.setCheckable(True)
        self.desktop_button.toggled.connect(self._toggle_companion)
        header.addWidget(self.history_button);header.addWidget(self.desktop_button)
        layout.addLayout(header)

        subtitle = QLabel(
            "Your personal assistant"
        )

        subtitle.setObjectName(
            "mutedText"
        )

        layout.addWidget(
            subtitle
        )
        subtitle.hide()
        self.connection_label = QLabel()
        self.connection_label.setObjectName("mutedText")
        self.connection_label.setWordWrap(True)
        layout.addWidget(self.connection_label)
        self._connection_timer = QTimer(self)
        self._connection_timer.setInterval(1500)
        self._connection_timer.timeout.connect(self._update_connection_label)
        self._connection_timer.start()
        self._update_connection_label()

        self.controls_button = quick_button = QPushButton("Controls")
        self.controls_dialog = AssistantControls(self)
        quick_layout = self.controls_dialog.section("Actions", "Shortcuts for common tasks. Your conversation stays in place.")
        self._build_command_center(quick_layout)
        quick_layout.addStretch()
        quick_button.clicked.connect(self.controls_dialog.reveal)
        quick_row = QHBoxLayout()
        quick_row.addWidget(quick_button)
        quick_row.addStretch()
        self.copy_reply_button = QPushButton("Copy reply")
        self.copy_chat_button = QPushButton("Copy conversation")
        self.copy_reply_button.clicked.connect(self._copy_reply)
        self.copy_chat_button.clicked.connect(self._copy_conversation)
        quick_row.addWidget(self.copy_reply_button)
        quick_row.addWidget(self.copy_chat_button)
        layout.addLayout(quick_row)

        card = AtmosphereFrame(self.presence)
        self.activity_card = card
        card.setObjectName("assistantCard")
        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(20, 16, 20, 16)
        card_layout.setSizeConstraint(QLayout.SizeConstraint.SetNoConstraint)
        card_layout.addStretch(1)
        self.orb = AssistantOrb(self.presence,size=184)
        card_layout.addWidget(self.orb,alignment=Qt.AlignmentFlag.AlignCenter)
        self.activity_state = QLabel("JARVIS · Ready")
        self.activity_state.setObjectName("assistantState")
        self.activity_message = QLabel("What would you like to do?")
        self.activity_message.setObjectName("assistantMessage")
        self.activity_message.setWordWrap(True)
        self.activity_message.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.activity_state.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.activity_progress = QLabel("Ask a question or give me a task.")
        self.activity_progress.setObjectName("mutedText")
        self.activity_progress.setWordWrap(True)
        self.activity_progress.setAlignment(Qt.AlignmentFlag.AlignCenter)
        card_layout.addWidget(self.activity_state)
        card_layout.addWidget(self.activity_message)
        card_layout.addWidget(self.activity_progress)
        self.activity_bar = QProgressBar()
        self.activity_bar.setRange(0, 0)
        self.activity_bar.setTextVisible(False)
        self.activity_bar.setFixedHeight(3)
        self.activity_bar.hide()
        card_layout.addWidget(self.activity_bar)
        self.approval_panel = QWidget()
        approval_layout = QVBoxLayout(self.approval_panel)
        self.approval_summary = QLabel()
        self.approval_summary.setWordWrap(True)
        self.approval_summary.setTextFormat(Qt.TextFormat.PlainText)
        approval_layout.addWidget(self.approval_summary)
        self.approval_controls = QWidget()
        approvals = QHBoxLayout(self.approval_controls)
        approvals.setContentsMargins(0, 0, 0, 0)
        self.approve_button = QPushButton("Approve once")
        self.approve_button.setObjectName("primaryButton")
        self.deny_button = QPushButton("Deny")
        approvals.addWidget(self.approve_button)
        approvals.addWidget(self.deny_button)
        self.approve_button.clicked.connect(lambda: self._resolve_approval(True, self._approval_token))
        self.deny_button.clicked.connect(lambda: self._resolve_approval(False, self._approval_token))
        self.approval_panel.hide()
        self.approval_controls.hide()
        card_layout.addWidget(self.approval_panel)
        for label in (self.activity_state, self.activity_message, self.activity_progress):
            label.setTextFormat(Qt.TextFormat.PlainText)
            label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse | Qt.TextInteractionFlag.TextSelectableByKeyboard)
            label.installEventFilter(self)
            label.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
            label.customContextMenuRequested.connect(lambda point, target=label:self._copy_menu(target, point))
        self.approval_summary.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse | Qt.TextInteractionFlag.TextSelectableByKeyboard)
        self.choices_layout = QVBoxLayout()
        card_layout.addLayout(self.choices_layout)
        self.details_button = QPushButton("Show details")
        self.details_button.setCheckable(True)
        self.details_button.setObjectName("linkButton")
        self.details_button.toggled.connect(self._toggle_details)
        self.details_view = QPlainTextEdit()
        self.details_view.installEventFilter(self)
        self.details_view.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.details_view.customContextMenuRequested.connect(lambda point:self._copy_menu(self.details_view, point))
        self.details_view.setReadOnly(True)
        self.details_view.setMaximumHeight(190)
        self.details_view.setMinimumHeight(130)
        self.details_view.hide()
        self.details_button.hide()
        card_layout.addWidget(self.details_button)
        card_layout.addWidget(self.details_view)
        card_layout.addStretch(1)
        self.activity_scroll = QScrollArea()
        self.activity_scroll.setObjectName("assistantCardScroll")
        self.activity_scroll.setWidgetResizable(True)
        self.activity_scroll.setFrameShape(QFrame.Shape.NoFrame)
        self.activity_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.activity_scroll.setMinimumHeight(40)
        self.activity_scroll.setMaximumHeight(340)
        self.activity_scroll.setWidget(card)
        layout.addWidget(self.activity_scroll)
        layout.setStretchFactor(self.activity_scroll,1)
        layout.addWidget(self.approval_controls)
        card_layout.removeWidget(self.details_button)
        layout.addWidget(self.details_button)

        # =================================================
        # CHAT HISTORY
        # =================================================

        self.chat_view = QPlainTextEdit()
        self.chat_view.installEventFilter(self)
        self.chat_view.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.chat_view.customContextMenuRequested.connect(lambda point:self._copy_menu(self.chat_view, point))

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
        self.chat_view.hide()
        self.history_button.toggled.connect(self.chat_view.setVisible)
        self.history_button.toggled.connect(lambda _:self._fit_activity())

        self.voice_panel = VoicePanel(self)
        voice_layout = self.controls_dialog.section("Voice", "Listen hands-free, choose your devices and adjust Jarvis’s voice.")
        self.voice_panel.settings.setWindowFlags(Qt.WindowType.Widget)
        self.voice_panel.settings.setMinimumWidth(0)
        self.voice_panel.barge_in.setText("Interrupt when I speak")
        self.voice_panel.barge_in.setToolTip("Uses speaker echo cancellation so Jarvis can listen while speaking.")
        voice_layout.addWidget(self.voice_panel.settings);voice_layout.addStretch()
        self.voice_panel.settings.show()
        self.voice_panel.options.clicked.disconnect()
        self.voice_panel.options.clicked.connect(lambda:(self.controls_dialog.tabs.setCurrentIndex(1),self.controls_dialog.reveal()))
        self.voice_panel.controller.transcript.connect(self._voice_prompt)
        self.voice_panel.controller.interrupted.connect(self._cancel_for_voice)
        self.voice_panel.controller.speech_started.connect(self._pause_for_voice)
        self.voice_panel.controller.speech_rejected.connect(self._resume_after_voice)
        self.voice_panel.controller.phase_changed.connect(self._audio_phase_changed)
        self.voice_panel.controller.caption_changed.connect(self._spoken_caption)
        self.voice_panel.controller.privacy_changed.connect(self._refresh_presence)
        self.voice_panel.controller.level_changed.connect(self.presence.set_level)
        self.voice_panel.controller.ready_changed.connect(self._companion_voice_ready)
        self.busy_changed.connect(lambda busy: setattr(self.voice_panel.controller, "chat_busy", busy))
        self.voice_panel.stop.clicked.connect(self._suppress_voice_reply)
        layout.addWidget(self.voice_panel)
        self.screen_panel = ScreenPanel(self.jarvis, self)
        self.screen_panel.changed.connect(self._screen_changed)
        screen_layout = self.controls_dialog.section("Screen", "Choose whether Jarvis can inspect the app you are using.")
        screen_layout.addWidget(self.screen_panel);screen_layout.addStretch()
        appearance = self.controls_dialog.section("Appearance", "Choose the amount of movement and text in your desktop companion.")
        self.reduce_motion = QCheckBox("Reduce animation")
        self.reduce_motion.toggled.connect(lambda enabled:self.presence.update_state(motion=not enabled))
        appearance.addWidget(self.reduce_motion)
        self.particles_toggle = QCheckBox("Spatial background dots");self.particles_toggle.setChecked(True)
        self.particles_toggle.toggled.connect(lambda enabled:self.presence.update_state(particles=enabled))
        appearance.addWidget(self.particles_toggle)
        self.captions_toggle = QCheckBox("Desktop companion captions");self.captions_toggle.setChecked(True)
        self.captions_toggle.toggled.connect(lambda enabled:self.presence.update_state(captions=enabled))
        appearance.addWidget(self.captions_toggle);appearance.addStretch()
        privacy = QHBoxLayout()
        self.microphone_badge = QLabel("●  Microphone off");self.microphone_badge.setObjectName("mutedText")
        self.screen_badge = QPushButton("Screen access off")
        self.screen_badge.setToolTip("Enable screen access for the selected AI during your tasks. No continuous background capture.")
        self.screen_badge.clicked.connect(lambda:self.screen_panel.enabled.setChecked(not self.screen_panel.enabled.isChecked()))
        privacy.addWidget(self.microphone_badge);privacy.addStretch();privacy.addWidget(self.screen_badge)
        layout.addLayout(privacy)
        self.presence.changed.connect(self._presence_labels)
        self.presence.changed.connect(self._sync_visual_options)
        saved_visuals = self.jarvis.personal_memory.records("assistant_visuals")
        if saved_visuals:
            prefs = saved_visuals[0]
            self.presence.update_state(**{key:prefs[key] for key in ("motion","particles","captions") if isinstance(prefs.get(key),bool)})
        self._sync_visual_options()

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
        self.send_button.setObjectName("primaryButton")
        self.stop_button = QPushButton("Stop")
        self.stop_button.clicked.connect(self._stop_request)
        self.stop_button.setEnabled(False)
        input_layout.addWidget(self.stop_button)

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
        self.status_label.setWordWrap(True)

        layout.addWidget(
            self.status_label
        )

        self.input_box.setFocus()

    def _sync_visual_options(self):
        for toggle, value in ((self.reduce_motion,not self.presence.motion),
                              (self.particles_toggle,self.presence.particles),
                              (self.captions_toggle,self.presence.captions)):
            toggle.blockSignals(True);toggle.setChecked(value);toggle.blockSignals(False)
        values: dict[str,object] = {"motion":self.presence.motion,"particles":self.presence.particles,"captions":self.presence.captions}
        if values != getattr(self,"_saved_visual_options",None):
            self.jarvis.personal_memory.save_record("assistant_visuals","main",values)
            self._saved_visual_options = values

    def _build_command_center(
        self,
        layout: QVBoxLayout,
    ) -> None:
        """
        Add visible one-click command-center actions.
        """

        panel = QWidget()

        panel.setObjectName(
            "commandCenterPanel"
        )

        panel_layout = QVBoxLayout(
            panel
        )

        panel_layout.setContentsMargins(
            12,
            12,
            12,
            12,
        )

        panel_layout.setSpacing(
            10
        )

        heading = QLabel(
            "Command Center"
        )

        heading.setObjectName(
            "sectionHeading"
        )

        panel_layout.addWidget(
            heading
        )

        grid = QGridLayout()

        grid.setContentsMargins(
            0,
            0,
            0,
            0,
        )

        grid.setSpacing(
            8
        )

        actions = [
            (
                "Mission",
                "command center",
            ),
            (
                "Status",
                "jarvis status",
            ),
            (
                "Brief",
                "daily brief",
            ),
            (
                "Can Do",
                "what can you do",
            ),
            (
                "Roadmap",
                "assistant plan",
            ),
            (
                "Desktop Note",
                "create a file in my desktop and say hi in there",
            ),
        ]

        for index, (
            label,
            prompt,
        ) in enumerate(
            actions
        ):
            button = QPushButton(
                label
            )

            button.setObjectName(
                "quickActionButton"
            )

            button.clicked.connect(
                lambda checked=False, value=prompt: (
                    self._send_quick_prompt(
                        value
                    )
                )
            )

            grid.addWidget(
                button,
                index // 3,
                index % 3,
            )

        panel_layout.addLayout(
            grid
        )

        layout.addWidget(
            panel
        )

    def _send_message(self) -> None:
        """
        Send the current message through JARVIS.
        """

        prompt = self.input_box.text().strip()
        input_source, self._next_input_source = self._next_input_source, "text"

        if not prompt:
            return

        self.voice_panel.controller.silence()

        if self._handle_control_prompt(prompt):
            self.input_box.clear()
            return

        if self.request_in_progress or self.worker_thread is not None:
            self.input_box.clear()
            if prompt.casefold().strip(" .!?") in {"status", "what are you doing", "what's happening", "how is it going", "how's it going"}:
                self._append_message("You", prompt)
                self._append_message("JARVIS", self.activity_progress.text() or self.activity_message.text())
                self._resume_after_voice()
                return
            if self._approval_token is not None and prompt.casefold().strip(" .!") in {"no", "deny"}:
                self._resolve_approval(False, self._approval_token)
                return
            if prompt.casefold().strip(" .!") in {"stop", "cancel", "stop please"}:
                self._stop_request(keep_voice=input_source == "voice")
                return
            self._pending_prompt = prompt
            self._pending_input_source = input_source
            if self.worker is not None and self.request_in_progress:
                self._clear_approval()
                self.worker.control.cancelled.set()
                self.worker.resolve_confirmation(False)
                self.activity_state.setText("JARVIS · Switching tasks")
                self.activity_message.setText("I'll stop the current task, then follow your new instruction.")
            self.status_label.setText("Next: " + prompt[:120])
            return

        self._append_message(
            "You",
            prompt,
        )

        self.input_box.clear()
        self._streaming = False
        self._streamed_text = ""
        self._pending_text = ""
        self._render_timer.stop()
        self._action_turn = False
        self._reply = None
        self._voice_reply_suppressed = False
        self._spoken_progress_at = 0.0
        self._clear_choices()
        self.status_label.setToolTip("")
        self.details_view.clear()
        self.details_button.hide()
        self.details_button.setChecked(False)
        self.activity_state.setText("JARVIS · Working")
        self.activity_message.setText("I'm on it.")
        self.activity_progress.setText("You can type a new instruction or press Stop.")

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
            input_source=input_source,
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
        worker.delta.connect(self._handle_delta)
        worker.progress.connect(self._handle_progress)
        worker.activity.connect(self._handle_activity)
        worker.reply_ready.connect(self._handle_reply)

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

    def _send_quick_prompt(
        self,
        prompt: str,
    ) -> None:
        """
        Send a predefined command-center prompt.
        """

        if self.request_in_progress:
            return

        self.input_box.setText(
            prompt
        )

        self._send_message()

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

        if self.worker is None or self.worker.control.cancelled.is_set():
            return

        request = raw_request

        arguments = dict(
            request.arguments
        )

        # -------------------------------------------------
        # Human-friendly summary
        # -------------------------------------------------

        summary_lines = [action_event(request.tool_name, arguments).message, "Review the exact action under Show details."]

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

        self._approval_token = object()
        self._approval_worker = self.worker
        self.activity_state.setText("JARVIS · Waiting for approval")
        self.activity_message.setText("I need your approval for this step.")
        self.approval_summary.setText("\n".join(summary_lines))
        self.details_view.setPlainText(json.dumps(arguments, ensure_ascii=False, indent=2, default=str))
        self.details_button.show()
        self.approval_panel.show()
        self.approval_controls.show()
        self.approve_button.setEnabled(True)
        self.deny_button.setEnabled(True)
        window = self.window()
        if window is not None:
            window.raise_()
            window.activateWindow()
        self._fit_activity()

    def _resolve_approval(self, approved: bool, token: object) -> None:
        worker = self._approval_worker
        if token is None or token is not self._approval_token or worker is None or worker is not self.worker:
            return
        if worker.control.cancelled.is_set():
            approved = False
        self._clear_approval()
        worker.resolve_confirmation(approved)

    def _clear_approval(self) -> None:
        self._approval_token = None
        self._approval_worker = None
        self.approval_panel.hide()
        self.approval_controls.hide()
        self.approve_button.setEnabled(False)
        self.deny_button.setEnabled(False)

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

        self._flush_delta()
        if not self._streaming:
            self._append_message("JARVIS", response)
        else:
            self.chat_view.appendPlainText("\n")
        self._streaming = False

        self.message_count_changed.emit(
            self.jarvis.conversation_message_count()
        )

        self._set_busy(
            False
        )

        self._show_latest_telemetry()
        self._refresh_presence()
        self._presence_labels()

    def _handle_error(
        self,
        error: str,
    ) -> None:
        """
        Display an application error without crashing Qt.
        """

        self._flush_delta()
        self._visual_error = True
        self._clear_approval()
        self._append_message(
            "JARVIS error",
            error,
        )
        self._streaming = False
        self.activity_state.setText("JARVIS · Couldn't finish")
        self.activity_message.setText("I couldn't finish that request. The details are below.")
        self.details_view.setPlainText(error)
        self.details_button.show()

        self._set_busy(
            False
        )

        self._show_latest_telemetry()

    def _set_busy(
        self,
        busy: bool,
    ) -> None:
        """
        Update UI controls while JARVIS is working.
        """

        self.request_in_progress = busy
        if busy:self._visual_error = False
        self.activity_bar.setVisible(busy)

        self.input_box.setEnabled(True)
        self.send_button.setEnabled(True)
        self.send_button.setText("Interrupt & send" if busy else "Send")
        self.input_box.setPlaceholderText("Give a new instruction to switch tasks…" if busy else "Ask JARVIS…")
        self.stop_button.setEnabled(busy)

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
        self._refresh_presence()

    def _show_latest_telemetry(
        self,
    ) -> None:
        """
        Show the latest execution route and latency.
        """

        telemetry = (
            self.jarvis
            .last_execution_telemetry()
        )

        if telemetry is None:
            return

        self.status_label.setToolTip(telemetry.summary())

    def start_new_conversation(
        self,
    ) -> None:
        """
        Reset conversation history without changing
        permissions.
        """

        if self.request_in_progress or self.worker_thread is not None:
            return

        self.voice_panel.controller.interrupt()

        self.jarvis.new_conversation()

        self.chat_view.clear()
        self._reply = None
        self._pending_prompt = ""
        self._clear_choices()
        self.details_view.clear()
        self.details_button.setChecked(False)
        self.details_button.hide()
        self.activity_state.setText("JARVIS · Ready")
        self.activity_message.setText("What would you like to do?")
        self.activity_progress.setText("A fresh conversation.")
        self._fit_activity()

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
        if self._pending_prompt:
            QTimer.singleShot(0, self._start_pending)

    def _handle_delta(self, text: str) -> None:
        if self._action_turn:
            self._streamed_text += text
            return
        self._pending_text += text
        if not self._render_timer.isActive():
            self._render_timer.start()

    def _flush_delta(self) -> None:
        if not self._pending_text:
            self._render_timer.stop()
            return
        text, self._pending_text = self._pending_text, ""
        if not self._streaming:
            self.chat_view.appendPlainText("JARVIS:")
            self._streaming = True
        self._streamed_text += text
        if not self._action_turn:
            self.activity_message.setText(self._streamed_text[:420]+("…" if len(self._streamed_text)>420 else ""))
            self._refresh_presence()
        cursor = self.chat_view.textCursor()
        cursor.movePosition(cursor.MoveOperation.End)
        cursor.insertText(text)
        self.chat_view.setTextCursor(cursor)
        self.chat_view.ensureCursorVisible()
        self.status_label.setText("Replying…")

    def _stop_request(self, *, keep_voice=False) -> None:
        self._voice_reply_suppressed = True
        if keep_voice:
            self.voice_panel.controller.silence()
        else:
            self.voice_panel.controller.stop_session()
        self._pending_prompt = ""
        if self.worker:
            self._clear_approval()
            self.worker.control.cancelled.set()
            self.worker.resolve_confirmation(False)
            self.stop_button.setEnabled(False)
            self.status_label.setText("Stopping… waiting for the current operation to release.")

    def _start_pending(self) -> None:
        if not self._pending_prompt or self.worker_thread is not None:
            return
        prompt, self._pending_prompt = self._pending_prompt, ""
        self._next_input_source = self._pending_input_source
        draft = self.input_box.text()
        self.input_box.setText(prompt)
        self._send_message()
        if draft:
            self.input_box.setText(draft)

    def _handle_progress(self, text: str) -> None:
        self.status_label.setText(text)
        self.activity_progress.setText(text)

    def _handle_activity(self, raw: object) -> None:
        if not isinstance(raw, AssistantEvent):
            return
        if raw.stage == "narration" and not self._voice_reply_suppressed and time.monotonic() - self._spoken_progress_at > 6:
            self._spoken_progress_at = time.monotonic()
            self.voice_panel.controller.say(raw.message)
        if raw.stage in {"working", "action_done", "sources"}:
            self._action_turn = True
        if raw.stage in {"thinking", "working", "action_done", "clarification"}:
            self.activity_message.setText(raw.message)
        self.activity_progress.setText(raw.message)
        self._fit_activity()

    def _handle_reply(self, raw: object) -> None:
        if not isinstance(raw, AssistantReply):
            return
        provider_limited = any(event.stage == "blocked" and event.operation == "provider_limit" for event in raw.events)
        if (raw.kind in {"failed", "partial"} and not provider_limited
                and self.voice_panel.controller.continuous and not self._voice_reply_suppressed):
            self.voice_panel.controller.pause_after_error()
            self.voice_panel._update_talk()
        if not self._voice_reply_suppressed and raw.kind != "cancelled" and not (self.worker and self.worker.control.cancelled.is_set()):
            self.voice_panel.controller.say(raw.spoken_text)
        self._clear_approval()
        self._reply = raw
        self._visual_error = raw.kind in {"failed","partial"}
        self.activity_message.setText(raw.spoken_text)
        self._fit_activity()
        self.activity_progress.setText("Choose a page below." if raw.choices else "")
        actions = "\n".join(event.message for event in raw.events if event.stage == "action_done")
        self.details_view.setPlainText(raw.details + ("\n\nCompleted actions:\n" + actions if actions else ""))
        self.details_button.setVisible(bool(actions or raw.details != raw.message or raw.kind in {"partial", "failed", "cancelled"}))
        self._clear_choices()
        for index, choice in enumerate(raw.choices):
            button = QPushButton(f"{index + 1}. {choice.label[:60]}")
            button.setToolTip(choice.url)
            button.clicked.connect(lambda checked=False, i=index: self._send_quick_prompt(f"open {i + 1}"))
            self.choices_layout.addWidget(button)
            self._choice_buttons.append(button)
        self._fit_activity()

    def _handle_control_prompt(self, text: str) -> bool:
        """Typed and spoken holds/resumes control the same running request."""
        normalized = re.sub(r"[^\w\s]", "", text.casefold()).strip()
        if normalized in {"wait", "no wait", "hold on", "wait a second", "pause", "pause please", "stop for a second"}:
            self._voice_hold = True
            self._pending_prompt = ""
            self._pause_for_voice()
            self._append_message("You", text)
            self.activity_state.setText("JARVIS · Paused")
            self.activity_message.setText("Paused. Tell me what to do next, or say continue.")
            return True
        if normalized in {"continue", "go ahead", "carry on", "resume", "keep going"} and self.worker is not None and not self.worker.control.cancelled.is_set():
            self._voice_hold = False
            self._resume_after_voice()
            self._append_message("You", text)
            self.activity_state.setText("JARVIS · Working")
            return True
        return False

    def _voice_prompt(self, text: str) -> None:
        # Identical core, history and approval handling for typed and spoken
        # instructions. Preserve any unfinished typed draft.
        if self._handle_control_prompt(text):
            return
        self._voice_hold = False
        draft = self.input_box.text()
        self._next_input_source = "voice"
        self.input_box.setText(text)
        self._send_message()
        if draft:
            self.input_box.setText(draft)

    def _update_connection_label(self) -> None:
        hub = self.jarvis.intelligence
        if hub is None:
            self.connection_label.setText("AI: " + str(getattr(self.jarvis.cloud_provider or self.jarvis.model_provider, "name", "local")))
            return
        prefs = hub.preferences()
        source, model = str(prefs.get("source", "auto")), str(prefs.get("model", ""))
        if source == "auto":
            choice = hub.automatic_connection()
            source, model = choice if choice else ("local", "")
        self.connection_label.setText(f"Selected AI: {source.replace('_', ' ')} · {model or 'configured model'} | Local actions work independently")

    def _copy_reply(self) -> None:
        text = self._reply.message if self._reply is not None else self.activity_message.text()
        if self._reply is not None and self._reply.details and self._reply.details != text:
            text += "\n\n" + self._reply.details
        self._copy_text(text, self.copy_reply_button)

    def _audio_phase_changed(self, phase):
        self._audio_phase = phase
        self._refresh_presence()

    def _spoken_caption(self, text):
        self.activity_message.setText(text)
        self._fit_activity()

    def _refresh_presence(self):
        if not hasattr(self,"voice_panel") or not hasattr(self,"activity_message"):
            return
        voice = self.voice_panel.controller
        paused = bool(self.worker is not None and self.worker.control.paused.is_set())
        if self._approval_token is not None:phase="approval"
        elif self._audio_phase == "speaking":phase="speaking"
        elif self._voice_hold:phase="paused"
        elif paused and self._audio_phase != "processing":phase="listening"
        elif self.request_in_progress or self._audio_phase in {"preparing","processing"}:phase="thinking"
        elif self._visual_error or self._audio_phase == "error":phase="error"
        elif voice.capture_active:phase="listening"
        elif self._reply is not None and self._reply.kind == "cancelled":phase="stopped"
        else:phase="idle"
        self.presence.update_state(phase=phase,caption=self.activity_message.text(),
                                  microphone=voice.capture_active,screen=bool(self.jarvis.screen_control_enabled))

    def _presence_labels(self):
        state = self.presence
        self.activity_state.setText(PHASES[state.phase])
        if hasattr(self,"microphone_badge"):
            self.microphone_badge.setText("●  Microphone on" if state.microphone else "○  Microphone off")
            self.microphone_badge.setStyleSheet("color:#81d8bd;" if state.microphone else "")
            self.screen_badge.setText("Screen access on" if state.screen else "Screen access off")
        self.activity_state.setAccessibleDescription(PHASES[state.phase])

    def _toggle_companion(self, visible):
        if visible:
            if self.companion is None:
                from jarvis.ui.companion import DesktopCompanion
                self.companion = DesktopCompanion(self.presence)
                self.companion.microphone_requested.connect(self._companion_voice_toggle)
                self.companion.screen_requested.connect(self.screen_panel.enabled.setChecked)
                self.companion.open_requested.connect(self.open_main_requested.emit)
                self.companion.stop_requested.connect(self._stop_request)
                self.companion.dismissed.connect(lambda:self.desktop_button.setChecked(False))
            self.companion.show()
        elif self.companion is not None:
            self.companion.hide()

    def _companion_voice_toggle(self):
        voice = self.voice_panel.controller
        if self._companion_mic_pending or voice.capture_active or voice.continuous:
            self._companion_mic_pending = False
            voice.stop_session()
        else:
            self.voice_panel.mode.setCurrentIndex(self.voice_panel.mode.findData("hands_free"))
            if voice.ready:voice.toggle_listening()
            else:
                self._companion_mic_pending = True
                self.voice_panel.enabled.setChecked(True)
        self.voice_panel._update_talk()
        self._refresh_presence()

    def _companion_voice_ready(self, ready):
        if ready and self._companion_mic_pending:
            self._companion_mic_pending = False
            self.voice_panel.controller.toggle_listening()
        self._refresh_presence()

    def _copy_conversation(self) -> None:
        self._flush_delta()
        text = self.chat_view.toPlainText()
        if self._reply and self._reply.details and self._reply.details not in text:
            text += "\n\nJARVIS:\n" + self._reply.details
        self._copy_text(text, self.copy_chat_button)

    def _copy_text(self, text: str, button: QPushButton) -> None:
        try:
            copy_text(text)
        except (OSError, ValueError) as error:
            self.status_label.setText(str(error))
            return
        original = "Copy reply" if button is self.copy_reply_button else "Copy conversation"
        button.setText("Copied ✓")
        self.status_label.setText("Copied to the Windows clipboard. Paste with Ctrl+V.")
        QTimer.singleShot(1600, button, lambda: button.setText(original))

    def eventFilter(self, watched, event):
        if event.type() == QEvent.Type.KeyPress and isinstance(event, QKeyEvent) and event.matches(QKeySequence.StandardKey.Copy):
            if isinstance(watched, QLabel):
                text = watched.selectedText()
            elif isinstance(watched, QPlainTextEdit):
                text = watched.textCursor().selectedText().replace("\u2029", "\n")
            else:
                text = ""
            if text:
                self._copy_text(text, self.copy_reply_button)
                return True
        return super().eventFilter(watched, event)

    def _copy_menu(self, widget, point):
        menu = QMenu(widget)
        selected = (widget.selectedText() if isinstance(widget, QLabel) else
                    widget.textCursor().selectedText().replace("\u2029", "\n"))
        action = menu.addAction("Copy selected text", lambda:self._copy_text(selected, self.copy_reply_button))
        action.setEnabled(bool(selected))
        menu.addAction("Copy reply", self._copy_reply)
        menu.addAction("Copy conversation", self._copy_conversation)
        if isinstance(widget, QPlainTextEdit):
            menu.addAction("Select all", widget.selectAll)
        origin = widget.viewport() if isinstance(widget, QPlainTextEdit) else widget
        menu.exec(origin.mapToGlobal(point))

    def _suppress_voice_reply(self) -> None:
        self._voice_reply_suppressed = True

    def _screen_changed(self) -> None:
        self._refresh_presence()
        if self.request_in_progress and self.worker is not None:
            self._stop_request()

    def shutdown_ui(self) -> None:
        self.controls_dialog.close()
        self._connection_timer.stop()
        self._render_timer.stop()
        self.screen_panel.timer.stop()
        self.voice_panel.controller.shutdown()
        if self.companion is not None:
            self.companion.hide()
            self.companion.close()
            self.companion.deleteLater()
            self.companion = None

    def closeEvent(self, event) -> None:
        self.shutdown_ui()
        super().closeEvent(event)

    def _cancel_for_voice(self) -> None:
        continuous = self.voice_panel.controller.continuous
        self._stop_request()
        if continuous:
            self.voice_panel.controller.continuous = True
            self.voice_panel.controller._resume_timer.start()

    def _pause_for_voice(self) -> None:
        self._voice_reply_suppressed = True
        if self.worker is not None:
            self.worker.control.paused.set()
            self.activity_state.setText("JARVIS · Listening")
            self.activity_progress.setText("Task paused while you speak. Your next instruction will redirect it.")

    def _resume_after_voice(self) -> None:
        if self._voice_hold:
            return
        if self.worker is not None:
            self.worker.control.paused.clear()
        self._voice_reply_suppressed = False

    def _clear_choices(self) -> None:
        for button in self._choice_buttons:
            self.choices_layout.removeWidget(button)
            button.deleteLater()
        self._choice_buttons.clear()

    def _toggle_details(self, visible: bool) -> None:
        self.details_view.setVisible(visible)
        self.details_button.setText("Hide details" if visible else "Show details")
        self._fit_activity()
        if visible:
            QTimer.singleShot(0, lambda: self.activity_scroll.ensureWidgetVisible(self.details_view))
        else:
            QTimer.singleShot(0, lambda: self.activity_scroll.verticalScrollBar().setValue(0))

    def _fit_activity(self) -> None:
        self._refresh_presence()
        if not self.history_button.isChecked():
            self.activity_card.setMinimumSize(0,0)
            self.activity_scroll.setMinimumHeight(200)
            self.activity_scroll.setMaximumHeight(16777215)
            return
        width = max(200, self.activity_scroll.viewport().width() - 48)
        self.activity_message.setMinimumHeight(max(28, self.activity_message.heightForWidth(width)))
        layout = self.activity_card.layout()
        if layout is not None:
            layout.activate()
            desired = layout.sizeHint().height() + 4
            self.activity_card.setMinimumSize(0, desired - 4)
            self.activity_card.setMaximumWidth(16777215)
            available = max(150, min(360, int(self.height() * 0.43)))
            page_layout = self.layout()
            if page_layout is not None:
                items = [page_layout.itemAt(i) for i in range(page_layout.count())]
                visible = [item for item in items if item is not None and not item.isEmpty()]
                margins = page_layout.contentsMargins()
                reserved = sum(max(item.minimumSize().height(), item.heightForWidth(width + 48) if item.hasHeightForWidth() else 0)
                               for item in visible if item.widget() is not self.activity_scroll)
                reserved += margins.top() + margins.bottom() + max(0, len(visible) - 1) * page_layout.spacing()
                available = max(40, min(available, self.height() - reserved))
            self.activity_scroll.setFixedHeight(min(available, max(110, desired)))
            if page_layout is not None:
                page_layout.invalidate()
                page_layout.activate()

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        if hasattr(self,"orb"):
            size=max(130,min(230,int(self.height()*0.27)))
            self.orb.setFixedSize(size,size)
        if hasattr(self, "activity_scroll"):
            self.activity_scroll.setMinimumHeight(40)
            self.activity_scroll.setMaximumHeight(max(150, min(360, int(self.height() * 0.43))))
            QTimer.singleShot(0, self._fit_activity)
