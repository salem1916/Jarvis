from PySide6.QtWidgets import (
    QLabel,
    QVBoxLayout,
    QWidget,
)


class PlaceholderPage(QWidget):
    """
    Temporary page used for features whose backend
    has not been implemented yet.

    We expose the navigation structure now without
    pretending unfinished systems already exist.
    """

    def __init__(
        self,
        title: str,
        description: str,
    ) -> None:
        super().__init__()

        layout = QVBoxLayout(
            self
        )

        layout.setContentsMargins(
            24,
            24,
            24,
            24,
        )

        title_label = QLabel(
            title
        )

        title_label.setObjectName(
            "pageTitle"
        )

        layout.addWidget(
            title_label
        )

        description_label = QLabel(
            description
        )

        description_label.setWordWrap(
            True
        )

        description_label.setObjectName(
            "mutedText"
        )

        layout.addWidget(
            description_label
        )

        layout.addStretch()