"""Native styling for the assistant workspace and settings."""


def stylesheet_for(theme: str = "dark") -> str:
    palette = ({"window": "#f5f5f7", "sidebar": "#ececf1", "card": "#ffffff",
                "input": "#f8f8fa", "text": "#1d1d1f", "muted": "#73737c", "border": "#dfdfe6",
                "hover": "#e5e5ec", "selected": "#dcecff", "accent": "#007aff", "onaccent":"#ffffff"}
               if theme == "light" else
               {"window": "#0e1118", "sidebar": "#141821", "card": "#141923",
                "input": "#191f2a", "text": "#eef1f8", "muted": "#929eaf", "border": "#2c3442",
                "hover": "#242e3d", "selected": "#28384b", "accent": "#a9c7ea", "onaccent":"#152131"})
    style = """
QMainWindow, QDialog { background: @window; }
QWidget { color: @text; font-family: "Segoe UI"; font-size: 14px; }
QWidget#sidebar { background: @sidebar; border: 1px solid @border; border-radius: 18px; }
QStackedWidget#pageStack, QWidget#settingsContent { background: @window; border: none; }
QLabel#brandTitle { font-size: 21px; font-weight: 600; color: @text; letter-spacing: 2px; }
QLabel#pageTitle { font-size: 22px; font-weight: 500; }
QLabel#sectionHeading { font-size: 16px; font-weight: 600; }
QLabel#sectionTitle { font-size: 11px; font-weight: 600; color: @muted; }
QLabel#mutedText { font-size: 12px; color: @muted; }
QFrame#settingsCard, QFrame#modelCard, QWidget#permissionSection {
 background: @card; border: 1px solid @border; border-radius: 14px;
}
QFrame#assistantCard { background: @card; border: none; border-radius: 18px; }
QScrollArea#assistantCardScroll { background: @card; border: 1px solid @border; border-radius: 24px; }
QLabel#assistantState { color: @accent; font-size: 12px; font-weight: 500; letter-spacing: 2px; }
QLabel#assistantMessage { font-size: 22px; font-weight: 400; padding: 10px 22px; }
QLabel#infoBox { background: @selected; border-radius: 10px; padding: 12px; }
QWidget#commandCenterPanel { background: @card; border: 1px solid @border; border-radius: 12px; }
QPushButton { background: @card; border: 1px solid @border; border-radius: 9px;
 padding: 8px 14px; min-height: 22px; }
QPushButton:hover { background: @hover; }
QPushButton:pressed { background: @selected; }
QPushButton:disabled { color: @muted; }
QPushButton#primaryButton { background: @accent; color: @onaccent; border: none; font-weight: 600; }
QPushButton#primaryButton:hover { background: #2588ef; }
QPushButton#linkButton { color: @accent; background: transparent; border: none; text-align: left; padding-left: 0; }
QPushButton#navButton { text-align: left; background: transparent; border: none; padding: 10px 13px; border-radius: 10px; }
QPushButton#navButton:hover { background: @hover; }
QPushButton#navButton:checked { background: @selected; color: @accent; font-weight: 600; }
QPushButton#quickActionButton { padding: 6px 10px; }
QLineEdit, QPlainTextEdit, QTextEdit, QSpinBox { background: @input; border: 1px solid @border;
 border-radius: 11px; padding: 10px; selection-background-color: @selected; }
QPlainTextEdit, QTextEdit { padding: 16px; }
QLineEdit:focus, QPlainTextEdit:focus { border-color: @accent; }
QComboBox { background: @input; border: 1px solid @border; border-radius: 9px;
 padding: 8px 10px; min-height: 22px; }
QComboBox::drop-down { border: none; width: 22px; }
QComboBox QAbstractItemView { background: @card; color: @text; selection-background-color: @selected; }
QCheckBox { spacing: 8px; }
QCheckBox::indicator { width: 36px; height: 22px; border-radius: 11px; border: 1px solid @border; background: @hover; }
QCheckBox::indicator:checked { background: @accent; border-color: @accent; }
QScrollArea { background: transparent; border: none; }
QScrollArea > QWidget > QWidget { background: transparent; }
QScrollBar:vertical { background: transparent; width: 8px; margin: 2px; }
QScrollBar::handle:vertical { background: @border; border-radius: 3px; min-height: 30px; }
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }
QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical { background: transparent; }
QTableWidget { background: @input; color: @text; border: 1px solid @border; border-radius: 10px;
 gridline-color: @border; selection-background-color: @selected; selection-color: @text; }
QHeaderView, QHeaderView::section, QTableCornerButton::section {
 background: @card; color: @muted; border: none; padding: 7px;
}
QProgressBar { border: none; background: @border; border-radius: 2px; }
QProgressBar::chunk { background: @accent; border-radius: 2px; }
QTabWidget::pane { border: 1px solid @border; border-radius: 12px; background: @card; }
QTabBar::tab { background: transparent; color: @muted; padding: 12px 14px; border: none; }
QTabBar::tab:selected { color: @text; background: @selected; border-radius: 8px; }
QScrollBar:vertical { background: transparent; width: 9px; margin: 4px 1px; }
QScrollBar::handle:vertical { background: @border; border-radius: 4px; min-height: 32px; }
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }
QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical { background: transparent; }
QLabel#permissionEnabled { color: #36b978; }
QLabel#permissionAsk { color: #c89d44; }
QLabel#permissionDisabled { color: #d97c7c; }
"""
    for key, value in palette.items():
        style = style.replace("@" + key, value)
    return style
