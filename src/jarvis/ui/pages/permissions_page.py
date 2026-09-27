from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
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
from jarvis.security.policy import PermissionDecision


class PermissionsPage(QWidget):
    """
    JARVIS permissions and filesystem-scope dashboard.

    Permission state comes from the real PermissionPolicy.

    Filesystem read scopes also come from the real
    FilesystemScopePolicy through JarvisApplication.

    The UI does not maintain its own fake permission state.
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
            "Control what JARVIS is allowed to access. "
            "Capability permissions and filesystem scopes "
            "are enforced by the real JARVIS security layer."
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
            "Filesystem Read Scopes"
        )

        scope_title.setObjectName(
            "sectionHeading"
        )

        scope_layout.addWidget(
            scope_title
        )

        scope_description = QLabel(
            "JARVIS may read only the directories listed below. "
            "Adding a folder grants read access only. "
            "It does not grant write or delete permission."
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

        session_notice = QLabel(
            "These additional folder permissions currently "
            "last only until JARVIS is closed. Persistent "
            "permission settings will be added later."
        )

        session_notice.setWordWrap(
            True
        )

        session_notice.setObjectName(
            "infoBox"
        )

        scope_layout.addWidget(
            session_notice
        )

        # -------------------------------------------------
        # List of approved folders
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
        # Add / remove buttons
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
        # CAPABILITY SECTIONS
        # =================================================

        content_layout.addWidget(
            self._build_permission_section(
                "Filesystem Capabilities",
                [
                    (
                        "Read files",
                        Capability.READ_FILE,
                    ),
                    (
                        "Write files",
                        Capability.WRITE_FILE,
                    ),
                    (
                        "Delete files",
                        Capability.DELETE_FILE,
                    ),
                ],
            )
        )

        content_layout.addWidget(
            self._build_permission_section(
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

        content_layout.addWidget(
            self._build_permission_section(
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

        content_layout.addWidget(
            self._build_permission_section(
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

    def _build_permission_section(
        self,
        title: str,
        permissions: list[
            tuple[str, Capability]
        ],
    ) -> QWidget:
        """
        Build one group of capability permission rows.
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

    def _refresh_filesystem_scopes(self) -> None:
        """
        Refresh the folder list from the REAL
        FilesystemScopePolicy.

        No folder path is stored only in the UI.
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

            # Store the actual path separately from
            # the human-readable display text.
            item.setData(
                Qt.ItemDataRole.UserRole,
                str(scope),
            )

            # Workspace scope is permanent.
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

    def _add_folder(self) -> None:
        """
        Ask the user to explicitly select a directory.

        Selecting the directory constitutes the user's
        permission to add it to the current read scopes.
        """

        selected = QFileDialog.getExistingDirectory(
            self,
            "Allow JARVIS to Read Folder",
        )

        # User cancelled the dialog.
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
                str(exc),
            )

            return

        self._refresh_filesystem_scopes()

        QMessageBox.information(
            self,
            "Folder Access Granted",
            (
                "JARVIS may now read files inside:\n\n"
                f"{path}\n\n"
                "Write and delete permissions were NOT granted."
            ),
        )

    def _remove_selected_folder(self) -> None:
        """
        Remove the currently selected user-granted scope.

        The workspace cannot be removed.
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
                "Remove JARVIS read access to:\n\n"
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
                str(exc),
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

    @staticmethod
    def _build_status_label(
        decision: PermissionDecision,
    ) -> QLabel:
        """
        Convert one real PermissionDecision into
        a visible status badge.
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