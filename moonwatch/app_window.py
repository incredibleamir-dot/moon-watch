"""Main window: menubar, toolbar, tabbed workspaces and status bar."""

from PySide6.QtCore import Qt
from PySide6.QtGui import (QAction, QActionGroup, QIcon, QPainter, QPen,
                           QColor, QPixmap, QPolygonF, QPainterPath)
from PySide6.QtCore import QPointF, QRectF
from PySide6.QtWidgets import QMainWindow, QTabWidget, QLabel, QToolBar

from . import theme
from .controller import AppController, fmt_date, coord_str, app_logo
from .pages import SightingPage, AnalysisPage, VerifyPage, LivePage
from .dialogs import (LocationDateDialog, DatesDialog, AboutDialog,
                      UserGuideDialog, GenerateAnimationDialog)

ICON = "#5a6a7a"
ICON_ON = "#ffffff"

TABS = [
    ("sight", "Sighting", "Moon sighting"),
    ("cond", "Condition", "Condition analysis"),
    ("equa", "Equation", "Equation analysis"),
    ("thres", "Threshold", "Threshold analysis"),
    ("verify", "Verification", "Verify our math (NASA + records)"),
    ("live", "Live", "Live Sun-Earth-Moon view"),
]


# --------------------------------------------------------------------------- icons
def _mk(factory, color):
    pm = QPixmap(20, 20)
    pm.fill(Qt.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.Antialiasing)
    pen = QPen(QColor(color), 1.6)
    pen.setCapStyle(Qt.RoundCap)
    pen.setJoinStyle(Qt.RoundJoin)
    p.setPen(pen)
    p.setBrush(Qt.NoBrush)
    factory(p)
    p.end()
    return QIcon(pm)


def _poly_icon(p, pts):
    p.drawPolygon(QPolygonF([QPointF(x, y) for x, y in pts]))


def _i_prev(p):
    _poly_icon(p, [(12, 4.5), (12, 15.5), (5.5, 10)])
    p.drawLine(16, 4.5, 16, 15.5)


def _i_next(p):
    _poly_icon(p, [(8, 4.5), (8, 15.5), (14.5, 10)])
    p.drawLine(4, 4.5, 4, 15.5)


def _i_today(p):
    p.drawEllipse(QRectF(4, 4, 12, 12))
    p.drawLine(10, 10, 10, 6)
    p.drawLine(10, 10, 13, 12)


def _i_gear(p):
    p.drawEllipse(QRectF(7.5, 7.5, 5, 5))
    import math
    for i in range(8):
        a = math.pi * 2 * i / 8
        p.drawLine(10 + math.cos(a) * 4, 10 + math.sin(a) * 4,
                   10 + math.cos(a) * 7.5, 10 + math.sin(a) * 7.5)


def _i_sight(p):
    path = QPainterPath()
    path.addEllipse(QRectF(4, 3.5, 13, 13))
    path.addEllipse(QRectF(10.5, 1.5, 10, 10))
    path.setFillRule(Qt.OddEvenFill)
    p.fillPath(path, p.pen().color())


def _i_cond(p):
    p.drawLine(3.5, 3.5, 3.5, 16.5)
    p.drawLine(3.5, 16.5, 16.5, 16.5)
    for x, y in ((6.5, 7), (10, 12.5), (12.5, 8), (8.5, 14.5), (15, 13)):
        p.drawEllipse(QRectF(x - 1.4, y - 1.4, 2.8, 2.8))


def _i_equa(p):
    p.drawLine(3.5, 3.5, 3.5, 16.5)
    p.drawLine(3.5, 16.5, 16.5, 16.5)
    prev = None
    for i in range(24):
        t = i / 23.0
        x = 4.5 + 11 * t
        y = 14.5 - 9.5 * (0.15 + 0.85 * t) ** 1.5
        if prev:
            p.drawLine(*prev, x, y)
        prev = (x, y)


def _i_thres(p):
    for i, h in enumerate((4.5, 6.5, 8.5, 10.5)):
        x = 4.0 + i * 3.8
        p.drawLine(4.0, 16, 16, 16)
        p.drawRect(QRectF(x, 16 - h, 2.2, h))


def _i_verify(p):
    p.drawEllipse(QRectF(3, 3, 14, 14))
    pts = QPolygonF([QPointF(7, 10.2), QPointF(9.5, 12.5), QPointF(13.5, 7.5)])
    p.drawPolyline(pts)


def _i_live(p):
    p.drawEllipse(QRectF(3.5, 3.5, 13, 13))
    p.drawEllipse(QRectF(7, 7, 6, 6))
    p.drawEllipse(QRectF(14.2, 3.2, 3.4, 3.4))


def _i_dates(p):
    p.drawRect(QRectF(3.5, 5, 13, 11.5))
    p.drawLine(3.5, 9, 16.5, 9)
    p.drawLine(7.5, 9, 7.5, 16)
    p.drawLine(11.5, 9, 11.5, 16)
    p.drawLine(6.5, 3, 6.5, 6)
    p.drawLine(13.5, 3, 13.5, 6)


def _i_about(p):
    p.drawEllipse(QRectF(3, 3, 14, 14))
    p.drawEllipse(QRectF(8.7, 6.7, 2.6, 2.6))
    p.drawLine(10, 10.8, 10, 14)


def _i_book(p):
    p.drawRect(QRectF(5, 4, 11, 13))
    p.drawLine(5, 7, 16, 7)
    p.drawLine(5, 10, 16, 10)
    p.drawLine(5, 13, 16, 13)


_ICON_PAINTERS = {
    "prev": _i_prev, "next": _i_next, "today": _i_today, "setup": _i_gear,
    "sight": _i_sight, "cond": _i_cond, "equa": _i_equa, "thres": _i_thres,
    "verify": _i_verify, "live": _i_live, "dates": _i_dates,
    "about": _i_about, "guide": _i_book,
}
_ICONS = {}


def icon(name, on=False):
    key = (name, on)
    if key not in _ICONS:
        _ICONS[key] = _mk(_ICON_PAINTERS[name], ICON_ON if on else ICON)
    return _ICONS[key]


# --------------------------------------------------------------------------- window
class MainWindow(QMainWindow):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.ctrl = AppController(self)
        self.setWindowTitle("Moon Watch - Crescent Visibility Workstation")
        self.setWindowIcon(app_logo())
        self.resize(1280, 800)
        self.setMinimumSize(980, 640)

        self._build_actions()
        self._build_menus()
        self._build_toolbar()
        self._build_tabs()
        self._build_statusbar()

        self.ctrl.dataChanged.connect(self._sync_status)
        self._sync_status()

    # -------------------------------------------------------------- actions
    def _build_actions(self):
        self.act_prev = QAction(icon("prev"), "Previous day", self)
        self.act_prev.setShortcut(Qt.Key_Left)
        self.act_prev.triggered.connect(lambda: self.ctrl.step_day(-1))

        self.act_next = QAction(icon("next"), "Next day", self)
        self.act_next.setShortcut(Qt.Key_Right)
        self.act_next.triggered.connect(lambda: self.ctrl.step_day(1))

        self.act_today = QAction(icon("today"), "Back to today", self)
        self.act_today.setShortcut(Qt.Key_T)
        self.act_today.triggered.connect(self._go_today)

        self.act_setup = QAction(icon("setup", True), "Date & location...", self)
        self.act_setup.setShortcut("Ctrl+L")
        self.act_setup.triggered.connect(self.show_location)

        self.act_dates = QAction(icon("dates", True), "Ramadan & Eid dates...", self)
        self.act_dates.setShortcut(Qt.Key_D)
        self.act_dates.triggered.connect(self.show_dates)

        self.act_about = QAction(icon("about", True), "About Moon Watch", self)
        self.act_about.setShortcut(Qt.Key_F1)
        self.act_about.triggered.connect(self.show_about)

        self.act_guide = QAction(icon("guide", True), "Moon Watch User Guide", self)
        self.act_guide.setShortcut("Ctrl+F1")
        self.act_guide.triggered.connect(self.show_guide)

        self.act_check = QAction("Run NASA HORIZONS comparison", self)
        self.act_check.setShortcut(Qt.Key_R)
        self.act_check.triggered.connect(self.ctrl.run_hz_check)

        self.act_param = QAction("Cycle analysis parameter", self)
        self.act_param.setShortcut(Qt.Key_X)
        self.act_param.triggered.connect(self._cycle_param)

        self.act_anime = QAction("Export animation...", self)
        self.act_anime.setShortcut("Ctrl+E")
        self.act_anime.triggered.connect(self.show_animation)

        self.act_full = QAction("Toggle fullscreen", self)
        self.act_full.setShortcut(Qt.Key_F11)
        self.act_full.triggered.connect(self._toggle_fullscreen)

        self.act_quit = QAction("Quit", self)
        self.act_quit.setShortcut("Ctrl+Q")
        self.act_quit.triggered.connect(self.close)

        self.view_group = QActionGroup(self)
        self.view_group.setExclusive(True)
        self.view_actions = {}
        letters = {"sight": "S", "cond": "C", "equa": "E",
                   "thres": "H", "verify": "V", "live": "L"}
        for i, (key, label, tip) in enumerate(TABS, start=1):
            act = QAction(icon(key), "%s  (Alt+%d)" % (label, i), self)
            act.setCheckable(True)
            act.setShortcuts([str(i), letters[key]])
            act.setStatusTip(tip)
            act.toggled.connect(lambda on, k=key, a=act: (
                a.setIcon(icon(k, on)), self._switch_view(k) if on else None))
            self.view_group.addAction(act)
            self.view_actions[key] = act

    def _go_today(self):
        import datetime
        self.ctrl.set_date(datetime.datetime.now().replace(
            hour=0, minute=0, second=0, microsecond=0))

    def _cycle_param(self):
        if self.tabs.currentIndex() == 3:
            from .pages import ANALYSIS_X_CHOICES
            combo = self.pages["thres"].param_combo
            cur = combo.currentIndex()
            combo.setCurrentIndex((cur + 1) % len(ANALYSIS_X_CHOICES))

    def _toggle_fullscreen(self):
        if self.isFullScreen():
            self.showNormal()
        else:
            self.showFullScreen()

    # ----------------------------------------------------------------- menus
    def _build_menus(self):
        mb = self.menuBar()
        file_menu = mb.addMenu("&File")
        file_menu.addAction(self.act_setup)
        file_menu.addAction(self.act_dates)
        file_menu.addSeparator()
        file_menu.addAction(self.act_quit)

        view_menu = mb.addMenu("&View")
        for act in (self.act_prev, self.act_next, self.act_today):
            view_menu.addAction(act)
        view_menu.addSeparator()
        for key, _, _label in TABS:
            view_menu.addAction(self.view_actions[key])
        view_menu.addSeparator()
        view_menu.addAction(self.act_full)

        tools_menu = mb.addMenu("&Tools")
        tools_menu.addAction(self.act_anime)
        tools_menu.addAction(self.act_check)
        tools_menu.addAction(self.act_param)

        help_menu = mb.addMenu("&Help")
        help_menu.addAction(self.act_guide)
        help_menu.addAction(self.act_about)

    # --------------------------------------------------------------- toolbar
    def _build_toolbar(self):
        tb = QToolBar("Main", self)
        tb.setMovable(False)
        tb.setToolButtonStyle(Qt.ToolButtonTextBesideIcon)
        self.addToolBar(tb)

        for act in (self.act_prev, self.act_next, self.act_today):
            tb.addAction(act)
        tb.addSeparator()
        for key, _, _label in TABS:
            tb.addAction(self.view_actions[key])
        tb.addSeparator()
        tb.addAction(self.act_setup)
        tb.addAction(self.act_dates)
        tb.addAction(self.act_about)

    # ------------------------------------------------------------------- tabs
    def _build_tabs(self):
        c = self.ctrl
        self.pages = {
            "sight": SightingPage(c),
            "cond": AnalysisPage("cond", c),
            "equa": AnalysisPage("equa", c),
            "thres": AnalysisPage("thres", c),
            "verify": VerifyPage(c),
            "live": LivePage(c),
        }
        self.tabs = QTabWidget()
        for key, label, _tip in TABS:
            self.tabs.addTab(self.pages[key], label)
        self.tabs.currentChanged.connect(self._tab_changed)
        self.setCentralWidget(self.tabs)
        self.view_actions["sight"].setChecked(True)

    def _switch_view(self, key):
        index = [t[0] for t in TABS].index(key)
        self.tabs.setCurrentIndex(index)

    def _tab_changed(self, index):
        key = TABS[index][0]
        self.view_actions[key].setChecked(True)
        if key == "verify":
            self.ctrl.start_checks()
        elif key == "live":
            self.ctrl.tick_live()

    # ------------------------------------------------------------ statusbar
    def _build_statusbar(self):
        self.lbl_date = QLabel()
        self.lbl_loc = QLabel()
        self.lbl_verdict = QLabel()
        sb = self.statusBar()
        sb.addWidget(self.lbl_date)
        sb.addWidget(self.lbl_loc)
        sb.addPermanentWidget(self.lbl_verdict)
        self.lbl_date.setStyleSheet("color: %s; font-weight: 600;" % theme.TEXT)
        self.lbl_loc.setStyleSheet("color: %s;" % theme.TEXT_MUT)

    def _sync_status(self):
        c = self.ctrl
        self.lbl_date.setText(fmt_date(c.date))
        self.lbl_loc.setText("%s   |   %s" % (c.city, coord_str(c.lat, c.lon, c.tz)))
        word, kind = c.verdict()
        color = theme.chip_color(kind).name()
        self.lbl_verdict.setText("  %s  " % word)
        self.lbl_verdict.setStyleSheet("color: %s; font-weight: 700;" % color)

    def closeEvent(self, event):
        self.ctrl.shutdown()
        super().closeEvent(event)

    # -------------------------------------------------------------- dialogs
    def show_location(self):
        dlg = LocationDateDialog(self.ctrl, self)
        if dlg.exec():
            city, lat, lon, tz, when = dlg.result()
            self.ctrl.set_date(when)
            self.ctrl.set_location(city, lat, lon, tz)

    def show_dates(self):
        dlg = DatesDialog(self.ctrl, self)
        dlg.exec()

    def show_animation(self):
        dlg = GenerateAnimationDialog(self.ctrl, self)
        dlg.exec()

    def show_about(self):
        dlg = AboutDialog(self)
        dlg.exec()

    def show_guide(self):
        dlg = UserGuideDialog(self)
        dlg.exec()