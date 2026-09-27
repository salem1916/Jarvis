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

    This page displays and modifies REAL application
    permission state.

    The UI does not keep an independent fake copy.

    Security remains enforced by:

        PermissionPolicy
            +
        FilesystemScopePolicy
    """

    def __init__(
        self,
        jarvis: JarvisApplication,
    ) -> None:
        super().__init__()

        self.jarvis = jarvis

        self._build_interface()
        self._refresh_filesystem_scopes()

    def _build_interface(self) -> None:
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
        # PAGE HEADER
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
            "require your approval. Permission decisions are "
            "enforced by the JARVIS security layer."
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
        # SCROLLABLE PAGE CONTENT
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

        scope_section = QWidget()

        scope_section.setObjectName(
            "permissionSection"
        )

        scope_layout = QVBoxLayout(
            scope_section
        )

        scope_layout.setContentsMargins(
            18,
            18,
            18,
            18,
        )

        scope_layout.setSpacing(
            10
        )

        scope_title = QLabel(
            "Filesystem Scopes"
        )

        scope_title.setObjectName(
            "sectionHeading"
        )

        scope_layout.addWidget(
            scope_title
        )

        scope_description = QLabel(
            "JARVIS may access only the folders listed below. "
            "A capability such as Write Files or Delete Files "
            "does not give access outside these approved scopes."
        )

        scope_description.setWordWrap(
            True
        )

        scope_description.setObjectName(
            "mutedText"
        )

        scope_layout.addWidget(
            scope_description
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

        scope_layout.addWidget(
            persistence_notice
        )

        # -------------------------------------------------
        # Approved folder list
        # -------------------------------------------------

        self.scope_list = QListWidget()

        self.scope_list.setObjectName(
            "scopeList"
        )

        self.scope_list.currentItemChanged.connect(
            self._update_remove_button
        )

        scope_layout.addWidget(
            self.scope_list
        )

        # -------------------------------------------------
        # Folder controls
        # -------------------------------------------------

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

        scope_layout.addLayout(
            button_row
        )

        content_layout.addWidget(
            scope_section
        )

        # =================================================
        # FILESYSTEM CAPABILITIES
        # =================================================

        content_layout.addWidget(
            self._build_filesystem_capability_section()
        )

        # =================================================
        # SYSTEM CAPABILITIES
        # =================================================

        content_layout.addWidget(
            self._build_static_permission_section(
                "System & Applications",
                [
                    (
                        "Read system information",
                        Capability.READ_SYSTEM_INFO,
                    ),
                    (
                        "Open applications",
                        Capability.OPEN_APPLICATION,
                    ),
                    (
                        "Control applications",
                        Capability.CONTROL_APPLICATION,
                    ),
                    (
                        "Run commands",
                        Capability.RUN_COMMAND,
                    ),
                ],
            )
        )

        # =================================================
        # NETWORK / EXTERNAL ACTIONS
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
        # SAFE LOCAL COMPUTATION
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

    def _build_filesystem_capability_section(
        self,
    ) -> QWidget:
        """
        Build the filesystem capability section.

        READ_FILE is currently configured elsewhere and shown
        as a read-only status.

        WRITE_FILE and DELETE_FILE support user-selectable
        permission modes.
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
            "Automatic write/delete access still applies only "
            "inside the approved filesystem scopes above."
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
        # READ FILE
        # -------------------------------------------------

        read_label = QLabel(
            "Read files"
        )

        read_status = self._build_status_label(
            self.jarvis.permission_decision(
                Capability.READ_FILE
            )
        )

        grid.addWidget(
            read_label,
            0,
            0,
        )

        grid.addWidget(
            read_status,
            0,
            1,
        )

        # -------------------------------------------------
        # WRITE FILE
        # -------------------------------------------------

        write_label = QLabel(
            "Write files"
        )

        self.write_mode_combo = self._build_permission_mode_combo(
            Capability.WRITE_FILE
        )

        grid.addWidget(
            write_label,
            1,
            0,
        )

        grid.addWidget(
            self.write_mode_combo,
            1,
            1,
        )

        # -------------------------------------------------
        # DELETE FILE
        # -------------------------------------------------

        delete_label = QLabel(
            "Delete files"
        )

        self.delete_mode_combo = self._build_permission_mode_combo(
            Capability.DELETE_FILE
        )

        grid.addWidget(
            delete_label,
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

    def _build_permission_mode_combo(
        self,
        capability: Capability,
    ) -> QComboBox:
        """
        Build one editable permission-mode dropdown.

        The actual security state remains inside
        JarvisApplication.
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

        # Connect AFTER setting the initial selection so
        # opening the page does not accidentally modify policy.
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
        Apply a user-selected permission mode.

        Persistent automatic access receives an additional
        warning before being enabled.
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
        # ALWAYS ALLOW WARNING
        # -------------------------------------------------

        if new_mode is PermissionMode.ALWAYS_ALLOW:
            action_name = self._capability_display_name(
                capability
            )

            if capability is Capability.DELETE_FILE:
                warning_text = (
                    f"You are about to permanently configure "
                    f'"{action_name}" for automatic execution.\n\n'
                    "JARVIS will no longer ask before moving "
                    "files to the Recycle Bin inside approved "
                    "filesystem scopes.\n\n"
                    "This setting will survive application "
                    "restarts.\n\n"
                    "Continue?"
                )

            else:
                warning_text = (
                    f"You are about to permanently configure "
                    f'"{action_name}" for automatic execution.\n\n'
                    "JARVIS will no longer ask before performing "
                    "this capability inside approved filesystem "
                    "scopes.\n\n"
                    "This setting will survive application "
                    "restarts.\n\n"
                    "Continue?"
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
        # Apply to the REAL JARVIS security policy.
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
    def _set_combo_mode(
        combo: QComboBox,
        mode: PermissionMode,
    ) -> None:
        """
        Change a combo selection without triggering its
        permission-change callback.
        """

        index = combo.findData(
            mode.value
        )

        if index < 0:
            return

        previous_state = combo.blockSignals(
            True
        )

        combo.setCurrentIndex(
            index
        )

        combo.blockSignals(
            previous_state
        )

    @staticmethod
    def _capability_display_name(
        capability: Capability,
    ) -> str:
        """
        Human-readable capability names.
        """

        names = {
            Capability.WRITE_FILE:
                "Write files",

            Capability.DELETE_FILE:
                "Delete files",
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
        Human-readable permission-mode names.
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

    def _build_static_permission_section(
        self,
        title: str,
        permissions: list[
            tuple[str, Capability]
        ],
    ) -> QWidget:
        """
        Build a read-only capability section.

        More capabilities can become configurable later
        using the same PermissionMode architecture.
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
            name_label = QLabel(
                label
            )

            decision = self.jarvis.permission_decision(
                capability
            )

            status_label = self._build_status_label(
                decision
            )

            grid.addWidget(
                name_label,
                row,
                0,
            )

            grid.addWidget(
                status_label,
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
        Reload approved folders from the actual
        FilesystemScopePolicy.
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
        Ask the human to select a folder and explicitly
        approve it as a filesystem scope.
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
        Revoke one user-approved filesystem scope.
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
    # STATIC STATUS BADGES
    # =====================================================

    @staticmethod
    def _build_status_label(
        decision: PermissionDecision,
    ) -> QLabel:
        """
        Convert low-level policy state to a visible badge.
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