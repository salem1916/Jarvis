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
    font-size: 15px;
}

QWidget#sidebar {
    background: #181b22;
    border-radius: 12px;
}

QStackedWidget#pageStack {
    background: #181b22;
    border-radius: 12px;
}

QWidget#modelsPageContent {
    background: transparent;
}

QLabel#brandTitle {
    color: #65c8ff;
    font-size: 24px;
    font-weight: bold;
}

QLabel#pageTitle {
    font-size: 22px;
    font-weight: bold;
}

QLabel#sectionHeading {
    font-size: 16px;
    font-weight: bold;
}

QLabel#sectionTitle {
    color: #9ea6b8;
    font-size: 12px;
    font-weight: bold;
}

QLabel#mutedText {
    color: #9aa2b3;
    font-size: 14px;
}

QLabel#infoBox {
    background: #151e26;
    border: 1px solid #29455a;
    border-radius: 8px;
    padding: 12px;
    color: #a9cbe0;
}

QWidget#commandCenterPanel {
    background: #101217;
    border: 1px solid #2b303b;
    border-radius: 8px;
}

QPushButton#quickActionButton {
    text-align: center;
    padding: 8px 10px;
    min-height: 20px;
}

QFrame#modelCard {
    background: #14171d;
    border: 1px solid #2b303b;
    border-radius: 10px;
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
    min-height: 20px;
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
    padding: 9px 16px;
    min-height: 22px;
}

QPushButton:hover {
    background: #303744;
    border-color: #465061;
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
    min-height: 22px;
}

QLineEdit:focus {
    border: 1px solid #65c8ff;
}

QComboBox {
    background: #171b22;
    border: 1px solid #343b48;
    border-radius: 7px;
    padding: 7px 10px;
    min-height: 24px;
}

QComboBox:hover {
    border: 1px solid #4b5667;
}

QComboBox:focus {
    border: 1px solid #65c8ff;
}

QComboBox::drop-down {
    border: none;
    width: 28px;
}

QComboBox#permissionModeCombo {
    min-width: 170px;
}

QComboBox QAbstractItemView {
    background: #181b22;
    border: 1px solid #343b48;
    selection-background-color: #253747;
    selection-color: #e7eaf0;
    padding: 4px;
    outline: none;
}

QComboBox QAbstractItemView::item {
    min-height: 28px;
    padding: 5px;
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

QScrollArea > QWidget > QWidget {
    background: transparent;
}

QScrollBar:vertical {
    background: #14171d;
    width: 10px;
    margin: 2px;
    border-radius: 5px;
}

QScrollBar::handle:vertical {
    background: #343b48;
    min-height: 32px;
    border-radius: 5px;
}

QScrollBar::handle:vertical:hover {
    background: #465061;
}

QScrollBar::add-line:vertical,
QScrollBar::sub-line:vertical {
    height: 0px;
}

QScrollBar::add-page:vertical,
QScrollBar::sub-page:vertical {
    background: transparent;
}

QTableWidget {
    background: #101217;
    alternate-background-color: #181b22;
    color: #e7eaf0;
    gridline-color: #2b303b;
    border: 1px solid #2b303b;
    border-radius: 6px;
    selection-background-color: #253747;
    selection-color: #e7eaf0;
}

QHeaderView {
    background: #242a34;
}

QHeaderView::section, QTableCornerButton::section {
    background: #242a34;
    color: #9ea6b8;
    border: none;
    border-right: 1px solid #343b48;
    padding: 6px;
}
"""
