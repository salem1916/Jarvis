from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QComboBox,
    QFileDialog,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from jarvis.core.application import JarvisApplication
from jarvis.security.capabilities import Capability
from jarvis.security.permission_mode import PermissionMode
from jarvis.security.policy import PermissionDecision


class PermissionsPage(QWidget):
    """
    JARVIS permissions dashboard.

    This page reads and modifies the REAL JARVIS security
    policy rather than maintaining a separate UI-only copy.

    Security is enforced by multiple independent layers:

        PermissionMode / PermissionPolicy
                +
        FilesystemScopePolicy
                +
        Tool-specific validation

    Therefore "Always allow" never means unrestricted access
    to the entire computer.
    """

    def __init__(
        self,
        jarvis: JarvisApplication,
    ) -> None:
        super().__init__()

        self.jarvis = jarvis

        self._build_interface()
        self._refresh_filesystem_scopes()

    def _build_interface(
        self,
    ) -> None:
        """
        Build the complete permissions dashboard.
        """

        root_layout = QVBoxLayout(
            self
        )

        root_layout.setContentsMargins(
            24,
            24,
            24,
            24,
        )

        root_layout.setSpacing(
            12
        )

        # =================================================
        # HEADER
        # =================================================

        title = QLabel(
            "Permissions"
        )

        title.setObjectName(
            "pageTitle"
        )

        root_layout.addWidget(
            title
        )

        description = QLabel(
            "Control what JARVIS may access and which actions "
            "require your approval. Security decisions are "
            "enforced by the JARVIS core."
        )

        description.setWordWrap(
            True
        )

        description.setObjectName(
            "mutedText"
        )

        root_layout.addWidget(
            description
        )

        self.permission_change_label = QLabel(
            "Changes take effect immediately."
        )

        self.permission_change_label.setObjectName(
            "mutedText"
        )

        root_layout.addWidget(
            self.permission_change_label
        )

        # =================================================
        # SCROLLABLE CONTENT
        # =================================================

        scroll = QScrollArea()

        scroll.setWidgetResizable(
            True
        )

        scroll.setFrameShape(
            QFrame.Shape.NoFrame
        )

        content = QWidget()

        content_layout = QVBoxLayout(
            content
        )

        content_layout.setContentsMargins(
            0,
            8,
            0,
            8,
        )

        content_layout.setSpacing(
            14
        )

        # =================================================
        # FILESYSTEM SCOPES
        # =================================================

        content_layout.addWidget(
            self._build_filesystem_scope_section()
        )

        # =================================================
        # FILESYSTEM CAPABILITIES
        # =================================================

        content_layout.addWidget(
            self._build_filesystem_capability_section()
        )

        # =================================================
        # APPLICATION / SYSTEM CAPABILITIES
        # =================================================

        content_layout.addWidget(
            self._build_system_capability_section()
        )

        # =================================================
        # EXTERNAL CAPABILITIES
        # =================================================

        content_layout.addWidget(
            self._build_static_permission_section(
                "Browser & External Actions",
                [
                    (
                        "Use browser",
                        Capability.USE_BROWSER,
                    ),
                    (
                        "Install software",
                        Capability.INSTALL_SOFTWARE,
                    ),
                    (
                        "Send email",
                        Capability.SEND_EMAIL,
                    ),
                    (
                        "Deploy applications",
                        Capability.DEPLOY_APPLICATION,
                    ),
                ],
            )
        )

        # =================================================
        # LOCAL UTILITIES
        # =================================================

        content_layout.addWidget(
            self._build_static_permission_section(
                "Local Computation",
                [
                    (
                        "Calculator",
                        Capability.CALCULATE,
                    ),
                ],
            )
        )

        content_layout.addStretch()

        scroll.setWidget(
            content
        )

        root_layout.addWidget(
            scroll,
            stretch=1,
        )

    # =====================================================
    # FILESYSTEM SCOPES
    # =====================================================

    def _build_filesystem_scope_section(
        self,
    ) -> QWidget:
        """
        Build approved filesystem-folder management.
        """

        section = QWidget()

        section.setObjectName(
            "permissionSection"
        )

        layout = QVBoxLayout(
            section
        )

        layout.setContentsMargins(
            18,
            18,
            18,
            18,
        )

        layout.setSpacing(
            10
        )

        heading = QLabel(
            "Filesystem Scopes"
        )

        heading.setObjectName(
            "sectionHeading"
        )

        layout.addWidget(
            heading
        )

        explanation = QLabel(
            "JARVIS may access only the folders listed below. "
            "Write and delete permissions do not grant access "
            "outside these approved scopes."
        )

        explanation.setWordWrap(
            True
        )

        explanation.setObjectName(
            "mutedText"
        )

        layout.addWidget(
            explanation
        )

        persistence_notice = QLabel(
            "Approved folders are remembered across JARVIS "
            "restarts until you remove them."
        )

        persistence_notice.setWordWrap(
            True
        )

        persistence_notice.setObjectName(
            "infoBox"
        )

        layout.addWidget(
            persistence_notice
        )

        self.scope_list = QListWidget()

        self.scope_list.setObjectName(
            "scopeList"
        )

        self.scope_list.currentItemChanged.connect(
            self._update_remove_button
        )

        layout.addWidget(
            self.scope_list
        )

        button_row = QHBoxLayout()

        self.add_folder_button = QPushButton(
            "+ Add Folder"
        )

        self.add_folder_button.clicked.connect(
            self._add_folder
        )

        button_row.addWidget(
            self.add_folder_button
        )

        self.remove_folder_button = QPushButton(
            "Remove Selected"
        )

        self.remove_folder_button.setDisabled(
            True
        )

        self.remove_folder_button.clicked.connect(
            self._remove_selected_folder
        )

        button_row.addWidget(
            self.remove_folder_button
        )

        button_row.addStretch()

        layout.addLayout(
            button_row
        )

        return section

    # =====================================================
    # FILESYSTEM CAPABILITIES
    # =====================================================

    def _build_filesystem_capability_section(
        self,
    ) -> QWidget:
        """
        Build filesystem permissions.

        READ_FILE remains read-only in the UI for now.

        WRITE_FILE and DELETE_FILE use configurable modes.
        """

        section = QWidget()

        section.setObjectName(
            "permissionSection"
        )

        layout = QVBoxLayout(
            section
        )

        layout.setContentsMargins(
            18,
            18,
            18,
            18,
        )

        layout.setSpacing(
            10
        )

        heading = QLabel(
            "Filesystem Capabilities"
        )

        heading.setObjectName(
            "sectionHeading"
        )

        layout.addWidget(
            heading
        )

        explanation = QLabel(
            "Automatic write or delete access still applies "
            "only inside approved filesystem scopes."
        )

        explanation.setWordWrap(
            True
        )

        explanation.setObjectName(
            "mutedText"
        )

        layout.addWidget(
            explanation
        )

        grid = QGridLayout()

        grid.setColumnStretch(
            0,
            1,
        )

        # -------------------------------------------------
        # READ
        # -------------------------------------------------

        grid.addWidget(
            QLabel(
                "Read files"
            ),
            0,
            0,
        )

        grid.addWidget(
            self._build_status_label(
                self.jarvis.permission_decision(
                    Capability.READ_FILE
                )
            ),
            0,
            1,
        )

        # -------------------------------------------------
        # WRITE
        # -------------------------------------------------

        self.write_mode_combo = (
            self._build_permission_mode_combo(
                Capability.WRITE_FILE
            )
        )

        grid.addWidget(
            QLabel(
                "Write files"
            ),
            1,
            0,
        )

        grid.addWidget(
            self.write_mode_combo,
            1,
            1,
        )

        # -------------------------------------------------
        # DELETE
        # -------------------------------------------------

        self.delete_mode_combo = (
            self._build_permission_mode_combo(
                Capability.DELETE_FILE
            )
        )

        grid.addWidget(
            QLabel(
                "Delete files"
            ),
            2,
            0,
        )

        grid.addWidget(
            self.delete_mode_combo,
            2,
            1,
        )

        layout.addLayout(
            grid
        )

        return section

    # =====================================================
    # APPLICATION / SYSTEM CAPABILITIES
    # =====================================================

    def _build_system_capability_section(
        self,
    ) -> QWidget:
        """
        Build system/application permissions.

        OPEN_APPLICATION is now user-configurable.

        CONTROL_APPLICATION and RUN_COMMAND remain disabled
        until their corresponding secure tools exist.
        """

        section = QWidget()

        section.setObjectName(
            "permissionSection"
        )

        layout = QVBoxLayout(
            section
        )

        layout.setContentsMargins(
            18,
            18,
            18,
            18,
        )

        layout.setSpacing(
            10
        )

        heading = QLabel(
            "System & Applications"
        )

        heading.setObjectName(
            "sectionHeading"
        )

        layout.addWidget(
            heading
        )

        explanation = QLabel(
            "Application launching uses the trusted installed-"
            "application catalog. Command interpreters such as "
            "CMD, PowerShell, WSL, and Windows Terminal remain "
            "blocked even when Open Applications is set to "
            "Always allow."
        )

        explanation.setWordWrap(
            True
        )

        explanation.setObjectName(
            "mutedText"
        )

        layout.addWidget(
            explanation
        )

        grid = QGridLayout()

        grid.setColumnStretch(
            0,
            1,
        )

        # -------------------------------------------------
        # SYSTEM INFO
        # -------------------------------------------------

        grid.addWidget(
            QLabel(
                "Read system information"
            ),
            0,
            0,
        )

        grid.addWidget(
            self._build_status_label(
                self.jarvis.permission_decision(
                    Capability.READ_SYSTEM_INFO
                )
            ),
            0,
            1,
        )

        # -------------------------------------------------
        # OPEN APPLICATION
        # -------------------------------------------------

        self.open_application_mode_combo = (
            self._build_permission_mode_combo(
                Capability.OPEN_APPLICATION
            )
        )

        grid.addWidget(
            QLabel(
                "Open applications"
            ),
            1,
            0,
        )

        grid.addWidget(
            self.open_application_mode_combo,
            1,
            1,
        )

        # -------------------------------------------------
        # CONTROL APPLICATION
        # -------------------------------------------------

        grid.addWidget(
            QLabel(
                "Control applications"
            ),
            2,
            0,
        )

        grid.addWidget(
            self._build_status_label(
                self.jarvis.permission_decision(
                    Capability.CONTROL_APPLICATION
                )
            ),
            2,
            1,
        )

        # -------------------------------------------------
        # RUN COMMAND
        # -------------------------------------------------

        grid.addWidget(
            QLabel(
                "Run commands"
            ),
            3,
            0,
        )

        grid.addWidget(
            self._build_status_label(
                self.jarvis.permission_decision(
                    Capability.RUN_COMMAND
                )
            ),
            3,
            1,
        )

        layout.addLayout(
            grid
        )

        return section

    # =====================================================
    # PERMISSION MODE DROPDOWNS
    # =====================================================

    def _build_permission_mode_combo(
        self,
        capability: Capability,
    ) -> QComboBox:
        """
        Build a user-editable capability mode dropdown.

        The AI model cannot call this API.

        Only trusted UI code may modify permission modes.
        """

        combo = QComboBox()

        combo.setObjectName(
            "permissionModeCombo"
        )

        combo.addItem(
            "Deny",
            PermissionMode.DENY.value,
        )

        combo.addItem(
            "Ask every time",
            PermissionMode.ASK.value,
        )

        combo.addItem(
            "Allow this session",
            PermissionMode.ALLOW_SESSION.value,
        )

        combo.addItem(
            "Always allow",
            PermissionMode.ALWAYS_ALLOW.value,
        )

        current_mode = self.jarvis.permission_mode(
            capability
        )

        index = combo.findData(
            current_mode.value
        )

        if index >= 0:
            combo.setCurrentIndex(
                index
            )

        # Connect only after initial state is selected.
        combo.currentIndexChanged.connect(
            lambda _index,
            selected_capability=capability,
            selected_combo=combo:
                self._permission_mode_changed(
                    selected_capability,
                    selected_combo,
                )
        )

        return combo

    def _permission_mode_changed(
        self,
        capability: Capability,
        combo: QComboBox,
    ) -> None:
        """
        Apply a capability permission change immediately.
        """

        raw_mode = combo.currentData()

        if not isinstance(
            raw_mode,
            str,
        ):
            return

        try:
            new_mode = PermissionMode(
                raw_mode
            )

        except ValueError:
            return

        old_mode = self.jarvis.permission_mode(
            capability
        )

        if new_mode is old_mode:
            return

        # -------------------------------------------------
        # ALWAYS ALLOW requires an additional warning.
        # -------------------------------------------------

        if new_mode is PermissionMode.ALWAYS_ALLOW:
            action_name = self._capability_display_name(
                capability
            )

            warning_text = self._always_allow_warning(
                capability=capability,
                action_name=action_name,
            )

            result = QMessageBox.question(
                self,
                "Enable Always Allow?",
                warning_text,
                QMessageBox.StandardButton.Yes
                | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            )

            if result != QMessageBox.StandardButton.Yes:
                self._set_combo_mode(
                    combo,
                    old_mode,
                )

                return

        # -------------------------------------------------
        # Change the real security policy.
        # -------------------------------------------------

        self.jarvis.set_permission_mode(
            capability,
            new_mode,
        )

        self.permission_change_label.setText(
            
                f"{self._capability_display_name(capability)}: "
                f"{self._mode_display_name(new_mode)}"
            
        )

    @staticmethod
    def _always_allow_warning(
        capability: Capability,
        action_name: str,
    ) -> str:
        """
        Produce capability-specific persistent-access warnings.
        """

        if capability is Capability.DELETE_FILE:
            return (
                f'You are about to set "{action_name}" to '
                "automatic execution.\n\n"
                "JARVIS will no longer ask before moving files "
                "to the Recycle Bin inside approved filesystem "
                "scopes.\n\n"
                "This setting survives JARVIS restarts.\n\n"
                "Continue?"
            )

        if capability is Capability.WRITE_FILE:
            return (
                f'You are about to set "{action_name}" to '
                "automatic execution.\n\n"
                "JARVIS will no longer ask before creating or "
                "overwriting files inside approved filesystem "
                "scopes.\n\n"
                "This setting survives JARVIS restarts.\n\n"
                "Continue?"
            )

        if capability is Capability.OPEN_APPLICATION:
            return (
                f'You are about to set "{action_name}" to '
                "automatic execution.\n\n"
                "JARVIS will be able to launch applications "
                "from its trusted application catalog without "
                "asking each time.\n\n"
                "Command interpreters such as CMD, PowerShell, "
                "WSL, and Windows Terminal remain blocked by "
                "the application catalog.\n\n"
                "This setting survives JARVIS restarts.\n\n"
                "Continue?"
            )

        return (
            f'You are about to set "{action_name}" to '
            "automatic execution.\n\n"
            "JARVIS will no longer ask before performing this "
            "capability.\n\n"
            "This setting survives JARVIS restarts.\n\n"
            "Continue?"
        )

    @staticmethod
    def _set_combo_mode(
        combo: QComboBox,
        mode: PermissionMode,
    ) -> None:
        """
        Restore a combo selection without triggering its
        permission callback.
        """

        index = combo.findData(
            mode.value
        )

        if index < 0:
            return

        old_signal_state = combo.blockSignals(
            True
        )

        combo.setCurrentIndex(
            index
        )

        combo.blockSignals(
            old_signal_state
        )

    @staticmethod
    def _capability_display_name(
        capability: Capability,
    ) -> str:
        """
        Convert internal capability names to UI labels.
        """

        names = {
            Capability.WRITE_FILE:
                "Write files",

            Capability.DELETE_FILE:
                "Delete files",

            Capability.OPEN_APPLICATION:
                "Open applications",
        }

        return names.get(
            capability,
            capability.value,
        )

    @staticmethod
    def _mode_display_name(
        mode: PermissionMode,
    ) -> str:
        """
        Convert permission mode to UI text.
        """

        names = {
            PermissionMode.DENY:
                "Deny",

            PermissionMode.ASK:
                "Ask every time",

            PermissionMode.ALLOW_SESSION:
                "Allow this session",

            PermissionMode.ALWAYS_ALLOW:
                "Always allow",
        }

        return names[
            mode
        ]

    # =====================================================
    # STATIC CAPABILITY SECTIONS
    # =====================================================

    def _build_static_permission_section(
        self,
        title: str,
        permissions: list[
            tuple[
                str,
                Capability,
            ]
        ],
    ) -> QWidget:
        """
        Build a read-only permission section.

        These capabilities will become configurable when their
        actual secure tools are implemented.
        """

        section = QWidget()

        section.setObjectName(
            "permissionSection"
        )

        layout = QVBoxLayout(
            section
        )

        layout.setContentsMargins(
            18,
            18,
            18,
            18,
        )

        layout.setSpacing(
            10
        )

        heading = QLabel(
            title
        )

        heading.setObjectName(
            "sectionHeading"
        )

        layout.addWidget(
            heading
        )

        grid = QGridLayout()

        grid.setColumnStretch(
            0,
            1,
        )

        for row, (
            label,
            capability,
        ) in enumerate(
            permissions
        ):
            grid.addWidget(
                QLabel(
                    label
                ),
                row,
                0,
            )

            grid.addWidget(
                self._build_status_label(
                    self.jarvis.permission_decision(
                        capability
                    )
                ),
                row,
                1,
            )

        layout.addLayout(
            grid
        )

        return section

    # =====================================================
    # FILESYSTEM SCOPE MANAGEMENT
    # =====================================================

    def _refresh_filesystem_scopes(
        self,
    ) -> None:
        """
        Reload approved folders from the actual scope policy.
        """

        self.scope_list.clear()

        scopes = self.jarvis.filesystem_read_scopes()

        if not scopes:
            return

        workspace = scopes[0]

        for scope in scopes:
            is_workspace = (
                scope == workspace
            )

            if is_workspace:
                display_text = (
                    f"Workspace — {scope}"
                )

            else:
                display_text = (
                    f"Allowed folder — {scope}"
                )

            item = QListWidgetItem(
                display_text
            )

            item.setData(
                Qt.ItemDataRole.UserRole,
                str(
                    scope
                ),
            )

            # True means the scope may be removed.
            item.setData(
                Qt.ItemDataRole.UserRole + 1,
                not is_workspace,
            )

            self.scope_list.addItem(
                item
            )

        self.remove_folder_button.setDisabled(
            True
        )

    def _add_folder(
        self,
    ) -> None:
        """
        Add one explicitly selected filesystem scope.
        """

        selected = QFileDialog.getExistingDirectory(
            self,
            "Allow JARVIS to Access Folder",
        )

        if not selected:
            return

        path = Path(
            selected
        )

        try:
            self.jarvis.add_filesystem_read_scope(
                path
            )

        except (
            FileNotFoundError,
            NotADirectoryError,
            ValueError,
        ) as exc:
            QMessageBox.warning(
                self,
                "Could Not Add Folder",
                str(
                    exc
                ),
            )

            return

        self._refresh_filesystem_scopes()

        QMessageBox.information(
            self,
            "Folder Access Granted",
            (
                "JARVIS may now operate inside:\n\n"
                f"{path}\n\n"
                "Actual operations remain controlled by "
                "their capability permission modes."
            ),
        )

    def _remove_selected_folder(
        self,
    ) -> None:
        """
        Revoke one user-added filesystem scope.
        """

        item = self.scope_list.currentItem()

        if item is None:
            return

        removable = bool(
            item.data(
                Qt.ItemDataRole.UserRole + 1
            )
        )

        if not removable:
            QMessageBox.information(
                self,
                "Permanent Workspace",
                (
                    "The JARVIS workspace is the permanent "
                    "minimum filesystem scope and cannot "
                    "be removed."
                ),
            )

            return

        raw_path = item.data(
            Qt.ItemDataRole.UserRole
        )

        if not isinstance(
            raw_path,
            str,
        ):
            return

        path = Path(
            raw_path
        )

        confirmation = QMessageBox.question(
            self,
            "Remove Folder Access",
            (
                "Remove JARVIS access to:\n\n"
                f"{path}?"
            ),
            QMessageBox.StandardButton.Yes
            | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )

        if confirmation != QMessageBox.StandardButton.Yes:
            return

        try:
            self.jarvis.remove_filesystem_read_scope(
                path
            )

        except ValueError as exc:
            QMessageBox.warning(
                self,
                "Could Not Remove Folder",
                str(
                    exc
                ),
            )

            return

        self._refresh_filesystem_scopes()

    def _update_remove_button(
        self,
        current: QListWidgetItem | None,
        previous: QListWidgetItem | None,
    ) -> None:
        """
        Enable Remove only for user-added scopes.
        """

        del previous

        if current is None:
            self.remove_folder_button.setDisabled(
                True
            )

            return

        removable = bool(
            current.data(
                Qt.ItemDataRole.UserRole + 1
            )
        )

        self.remove_folder_button.setEnabled(
            removable
        )

    # =====================================================
    # STATUS BADGES
    # =====================================================

    @staticmethod
    def _build_status_label(
        decision: PermissionDecision,
    ) -> QLabel:
        """
        Convert low-level PermissionDecision into a badge.
        """

        if decision is PermissionDecision.ALLOW:
            label = QLabel(
                "ENABLED"
            )

            label.setObjectName(
                "permissionEnabled"
            )

            return label

        if decision is PermissionDecision.REQUIRE_CONFIRMATION:
            label = QLabel(
                "ASK"
            )

            label.setObjectName(
                "permissionAsk"
            )

            return label

        label = QLabel(
            "DISABLED"
        )

        label.setObjectName(
            "permissionDisabled"
        )

        return label