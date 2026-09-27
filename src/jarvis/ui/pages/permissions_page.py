from PySide6.QtWidgets import (
    QFrame,
    QGridLayout,
    QLabel,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from jarvis.core.application import JarvisApplication
from jarvis.security.capabilities import Capability
from jarvis.security.policy import PermissionDecision


class PermissionsPage(QWidget):
    """
    Read-only view of JARVIS's current security policy.

    This page does NOT maintain a second permission state.

    Every status shown here is obtained from the real
    PermissionPolicy through JarvisApplication.

    Editable permissions come in the next security stage.
    """

    def __init__(
        self,
        jarvis: JarvisApplication,
    ) -> None:
        super().__init__()

        self.jarvis = jarvis

        self._build_interface()

    def _build_interface(self) -> None:
        """
        Build the permissions dashboard.
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
            "These are the permissions currently enforced "
            "by the JARVIS security policy. "
            "They are read-only in this version."
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

        scope_notice = QLabel(
            "Current filesystem scope: "
            "READ_FILE is restricted to the JARVIS workspace. "
            "Broader folder scopes will be added later."
        )

        scope_notice.setWordWrap(
            True
        )

        scope_notice.setObjectName(
            "infoBox"
        )

        root_layout.addWidget(
            scope_notice
        )

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

        content_layout.addWidget(
            self._build_section(
                "Filesystem",
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
            self._build_section(
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
            self._build_section(
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
            self._build_section(
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

    def _build_section(
        self,
        title: str,
        permissions: list[
            tuple[str, Capability]
        ],
    ) -> QWidget:
        """
        Build one group of permission rows.
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

    @staticmethod
    def _build_status_label(
        decision: PermissionDecision,
    ) -> QLabel:
        """
        Convert the security policy decision into
        a human-readable status badge.
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