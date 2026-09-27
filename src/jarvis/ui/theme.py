"""
Central visual theme for JARVIS Desktop.

Presentation rules are kept outside individual pages so the
desktop design can evolve independently from application logic.
"""

APP_STYLESHEET = """
QMainWindow {
    background: #101217;
}

QWidget {
    color: #e7eaf0;
    font-size: 14px;
}

QWidget#sidebar {
    background: #181b22;
    border-radius: 12px;
}

QStackedWidget#pageStack {
    background: #181b22;
    border-radius: 12px;
}

QLabel#brandTitle {
    color: #65c8ff;
    font-size: 24px;
    font-weight: bold;
}

QLabel#pageTitle {
    font-size: 20px;
    font-weight: bold;
}

QLabel#sectionHeading {
    font-size: 15px;
    font-weight: bold;
}

QLabel#sectionTitle {
    color: #8d94a5;
    font-size: 11px;
    font-weight: bold;
}

QLabel#mutedText {
    color: #8d94a5;
}

QLabel#infoBox {
    background: #151e26;
    border: 1px solid #29455a;
    border-radius: 8px;
    padding: 12px;
    color: #a9cbe0;
}

QWidget#permissionSection {
    background: #101217;
    border: 1px solid #2b303b;
    border-radius: 10px;
}

QLabel#permissionEnabled {
    color: #7edc9a;
    font-weight: bold;
}

QLabel#permissionAsk {
    color: #f0ca72;
    font-weight: bold;
}

QLabel#permissionDisabled {
    color: #d07a7a;
    font-weight: bold;
}

QPushButton#navButton {
    text-align: left;
    background: transparent;
    border: none;
    border-radius: 8px;
    padding: 10px 12px;
}

QPushButton#navButton:hover {
    background: #242a34;
}

QPushButton#navButton:checked {
    background: #253747;
    color: #65c8ff;
    font-weight: bold;
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

QComboBox#permissionModeCombo {
    background: #171b22;
    border: 1px solid #343b48;
    border-radius: 7px;
    padding: 7px 10px;
    min-width: 170px;
}

QComboBox#permissionModeCombo:hover {
    border: 1px solid #4b5667;
}

QComboBox#permissionModeCombo:focus {
    border: 1px solid #65c8ff;
}

QComboBox#permissionModeCombo::drop-down {
    border: none;
    width: 24px;
}

QComboBox QAbstractItemView {
    background: #181b22;
    border: 1px solid #343b48;
    selection-background-color: #253747;
    selection-color: #e7eaf0;
    outline: none;
}

QListWidget#scopeList {
    background: #0d0f13;
    border: 1px solid #2b303b;
    border-radius: 8px;
    padding: 6px;
    min-height: 120px;
}

QListWidget#scopeList::item {
    padding: 9px;
    border-radius: 5px;
}

QListWidget#scopeList::item:hover {
    background: #1e242d;
}

QListWidget#scopeList::item:selected {
    background: #253747;
    color: #e7eaf0;
}

QScrollArea {
    background: transparent;
    border: none;
}
"""