"""Scientific theme: colours, fonts and the global stylesheet.
"""

from PySide6.QtGui import QColor, QFont

# --------------------------------------------------------------------------- palette
BG = "#f3f5f7"
PANEL = "#ffffff"
PANEL_ALT = "#f7f9fb"
BORDER = "#d3dae2"
BORDER_SOFT = "#e3e8ee"
GRID = "#e7ebf0"
TEXT = "#23313f"
TEXT_MUT = "#63717f"
TEXT_DIM = "#8f9ba8"
ACCENT = "#1f5f8b"
ACCENT_DARK = "#15496c"
ACCENT_TEXT = "#ffffff"
ACCENT_BG = "#e8f1f8"
LINK = "#2d7db8"

OK = "#2f8f52"
OK_BG = "#e9f6ee"
WARN = "#b87714"
WARN_BG = "#fbf3e0"
ERR = "#c93a3a"
ERR_BG = "#fbeaea"
INFO = "#2d7db8"
INFO_BG = "#eaf3fa"

CHART_BG = "#ffffff"
CHART_PLOT = "#fbfcfe"
CHART_GRID = "#e9edf2"
CHART_AXIS = "#97a3b0"
CHART_TITLE = "#23313f"
CHART_LABEL = "#4c5a69"
CHART_CAPTION = "#8f9ba8"

C_SEE = "#3b9e5f"          # green - crescent seen
C_UNSEE = "#d64747"        # red - not seen
C_CRIT = "#c07817"         # amber - criterion / limit lines
C_BOUND = "#8e6fc2"        # purple - equation boundary curve
C_TODAY = "#2c7fb8"        # blue - current / highlighted evening
C_SERIES1 = "#2c7fb8"
C_SERIES2 = "#8e6fc2"
C_MOON_LIT = "#fdfeff"
C_MOON_DARK = "#b9c3cf"
C_SUN = "#f2a63b"
C_ORBIT = "#94a3b5"

FAMILY = "Segoe UI"
MONO = "Consolas"
HEADING = "Segoe UI Semibold"


def font(size=10, bold=False, mono=False, family=None):
    f = QFont(mono and MONO or (family or FAMILY), size)
    f.setBold(bold)
    return f


# --------------------------------------------------------------------------- stylesheet
STYLE = """
QWidget {
    background: %(bg)s;
    color: %(text)s;
    font-family: "Segoe UI";
    font-size: 13px;
    selection-background-color: %(accent)s;
    selection-color: white;
}

QMainWindow, QDialog { background: %(bg)s; }

QMenuBar {
    background: %(panel)s;
    border-bottom: 1px solid %(border)s;
    padding: 2px 4px;
}
QMenuBar::item { padding: 4px 10px; background: transparent; border-radius: 4px; }
QMenuBar::item:selected { background: %(accent_bg)s; color: %(accent)s; }

QMenu {
    background: %(panel)s;
    border: 1px solid %(border)s;
    padding: 4px;
}
QMenu::item { padding: 5px 22px 5px 14px; border-radius: 4px; }
QMenu::item:selected { background: %(accent_bg)s; color: %(accent)s; }
QMenu::separator { height: 1px; background: %(border_soft)s; margin: 4px 8px; }

QToolBar {
    background: %(panel)s;
    border: none;
    border-bottom: 1px solid %(border)s;
    padding: 4px 6px;
    spacing: 4px;
}
QToolBar QToolButton {
    background: transparent;
    border: 1px solid transparent;
    border-radius: 6px;
    padding: 5px 9px;
    color: %(text_mut)s;
}
QToolBar QToolButton:hover { background: %(accent_bg)s; }
QToolBar QToolButton:checked {
    background: %(accent)s;
    color: white;
    border-color: %(accent)s;
}
QToolBar QToolButton:pressed { background: %(accent_dark)s; }

QTabWidget::pane {
    border: 1px solid %(border)s;
    background: %(panel)s;
    border-radius: 6px;
    top: -1px;
}
QTabBar::tab {
    background: transparent;
    color: %(text_mut)s;
    padding: 7px 14px;
    border: 1px solid transparent;
    border-bottom: 2px solid transparent;
    margin-right: 2px;
    font-size: 13px;
}
QTabBar::tab:selected {
    color: %(accent)s;
    border-bottom-color: %(accent)s;
    background: white;
}
QTabBar::tab:hover:!selected { color: %(link)s; }

QGroupBox {
    background: %(panel)s;
    border: 1px solid %(border)s;
    border-radius: 6px;
    margin-top: 14px;
    padding: 10px 10px 8px 10px;
    font-weight: 600;
    color: %(text)s;
}
QGroupBox::title {
    subcontrol-origin: margin;
    left: 10px;
    padding: 0 5px;
    background: %(panel)s;
    color: %(accent)s;
    font-size: 11px;
}

QPushButton {
    background: %(panel)s;
    border: 1px solid %(border)s;
    border-radius: 5px;
    padding: 5px 14px;
    color: %(text)s;
}
QPushButton:hover { border-color: %(accent)s; color: %(accent)s; }
QPushButton:pressed { background: %(accent_bg)s; }
QPushButton:default, QPushButton[primary="true"] {
    background: %(accent)s;
    border: 1px solid %(accent)s;
    color: white;
}
QPushButton:default:hover, QPushButton[primary="true"]:hover {
    background: %(accent_dark)s; border-color: %(accent_dark)s; color: white;
}
QPushButton:disabled { color: %(text_dim)s; border-color: %(border_soft)s; background: %(panel_alt)s; }

QLineEdit, QDoubleSpinBox, QSpinBox, QDateEdit, QComboBox {
    background: white;
    border: 1px solid %(border)s;
    border-radius: 5px;
    padding: 4px 8px;
    min-height: 22px;
}
QLineEdit:focus, QDoubleSpinBox:focus, QSpinBox:focus, QDateEdit:focus, QComboBox:focus {
    border-color: %(accent)s;
}
QComboBox::drop-down { border: none; width: 22px; }
QComboBox QAbstractItemView {
    background: white;
    border: 1px solid %(border)s;
    selection-background-color: %(accent_bg)s;
    selection-color: %(accent)s;
    outline: none;
}
QDateEdit::drop-down, QDoubleSpinBox::up-button, QDoubleSpinBox::down-button,
QSpinBox::up-button, QSpinBox::down-button { width: 18px; border: none; background: transparent; }

QTableView, QTableWidget {
    background: white;
    alternate-background-color: %(panel_alt)s;
    gridline-color: %(border_soft)s;
    border: 1px solid %(border)s;
    border-radius: 5px;
    selection-background-color: %(accent_bg)s;
    selection-color: %(accent)s;
    color: %(text)s;
}
QTableView QHeaderView::section {
    background: %(panel_alt)s;
    color: %(text_mut)s;
    border: none;
    border-bottom: 1px solid %(border)s;
    border-right: 1px solid %(border_soft)s;
    padding: 5px 6px;
    font-weight: 600;
}
QTableView QTableCornerButton::section {
    background: %(panel_alt)s;
    border: none;
    border-bottom: 1px solid %(border)s;
}

QScrollArea { border: none; background: transparent; }
QScrollBar:vertical { background: transparent; width: 12px; margin: 2px; }
QScrollBar::handle:vertical { background: #c6cde0; border-radius: 4px; min-height: 26px; }
QScrollBar::handle:vertical:hover { background: #aeb7cc; }
QScrollBar::add-line, QScrollBar::sub-line { height: 0; width: 0; }
QScrollBar:horizontal { background: transparent; height: 12px; margin: 2px; }
QScrollBar::handle:horizontal { background: #c6cde0; border-radius: 4px; min-width: 26px; }

QStatusBar {
    background: white;
    border-top: 1px solid %(border)s;
    color: %(text_mut)s;
}
QStatusBar QLabel { color: %(text_mut)s; padding: 0 4px; }
QStatusBar QLabel[chip="ok"] { color: %(ok)s; }
QStatusBar QLabel[chip="warn"] { color: %(warn)s; }
QStatusBar QLabel[chip="err"] { color: %(err)s; }

QToolTip {
    background: %(panel)s;
    color: %(text)s;
    border: 1px solid %(border)s;
    padding: 4px 8px;
}

QSplitter::handle { background: transparent; width: 6px; }

QLabel[section="true"] {
    color: %(accent)s;
    font-weight: 600;
}
""" % {
    "bg": BG, "panel": PANEL, "panel_alt": PANEL_ALT, "border": BORDER,
    "border_soft": BORDER_SOFT, "text": TEXT, "text_mut": TEXT_MUT,
    "text_dim": TEXT_DIM, "accent": ACCENT, "accent_dark": ACCENT_DARK,
    "accent_bg": ACCENT_BG, "link": LINK, "ok": OK, "warn": WARN, "err": ERR,
}


def chip_color(kind):
    """Return a suitable QColor for a status word."""
    return QColor({"visible": OK, "borderline": WARN, "not": ERR,
                   "ok": OK, "warn": WARN, "error": ERR, "stale": WARN,
                   "info": INFO, "no": ERR}.get(kind, TEXT_MUT))