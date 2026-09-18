"""Tab pages: the six scientific workspaces of the workstation.

Each page listens to the shared controller and repaints its chart, tables and
status chips when the underlying data changes.  The layout is a conventional
desktop splitter - chart on the left, parameter/result panels on the right.
"""

import time

from PySide6.QtCore import Qt, QTimer, QSettings
from PySide6.QtGui import QColor, QShortcut, QKeySequence
from PySide6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QSplitter,
                               QGroupBox, QLabel, QTableWidget, QSlider,
                               QTableWidgetItem, QHeaderView, QScrollArea,
                               QComboBox, QPushButton, QFrame, QSizePolicy,
                               QAbstractItemView, QStackedWidget,
                               QCheckBox, QDoubleSpinBox, QDialog,
                               QLineEdit, QApplication)

from . import theme
import astronomy
from .charts import (SkyWidget, AltitudeChartWidget, ScatterWidget,
                     BoxPlotWidget, GlobalVisibilityWidget,
                     crescent_pixmap, crescent_rot, F)
from .sighting_sky_3d import SightingSky3D
from .sky_map import HorizonSkyWidget
from .controller import fmt_date, fmt_time, fmt_age_h, coord_str
from .phone import PhoneLink
from .sensorcast import (apply_calibration, calibration_from_aim,
                         wrap_az_delta)


def panel_frame(widget):
    f = QFrame()
    f.setStyleSheet("QFrame { background: %s; border: 1px solid %s;"
                    " border-radius: 6px; }" % (theme.PANEL, theme.BORDER))
    lay = QVBoxLayout(f)
    lay.setContentsMargins(10, 10, 10, 10)
    lay.setSpacing(8)
    lay.addWidget(widget)
    return f


class StatusChip(QLabel):
    """A coloured status pill used for verdicts and PASS/FAIL results."""

    def __init__(self, text="", kind="info", parent=None):
        super().__init__(text, parent)
        self.setAlignment(Qt.AlignCenter)
        self.set_kind(text, kind)

    def set_kind(self, text, kind):
        col = theme.chip_color(kind).name()
        bg = {"ok": theme.OK_BG, "warn": theme.WARN_BG,
              "err": theme.ERR_BG, "info": theme.INFO_BG,
              "no": theme.WARN_BG}.get(kind, theme.INFO_BG)
        self.setText(text)
        self.setStyleSheet(
            "QLabel { background: %s; color: %s; border-radius: 8px;"
            " padding: 4px 10px; font-weight: 600; }" % (bg, col))


def _table(headers, rows, widths=None, stretch=None):
    t = QTableWidget(len(rows), len(headers))
    t.setHorizontalHeaderLabels(headers)
    t.verticalHeader().setVisible(False)
    t.setEditTriggers(QAbstractItemView.NoEditTriggers)
    t.setSelectionMode(QAbstractItemView.NoSelection)
    t.setFocusPolicy(Qt.NoFocus)
    t.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
    hh = t.horizontalHeader()
    hh.setMinimumSectionSize(0)
    last = len(headers) - 1 if stretch is None else stretch
    for i in range(len(headers)):
        if i == last:
            hh.setSectionResizeMode(i, QHeaderView.Stretch)
        elif widths and i < len(widths):
            hh.setSectionResizeMode(i, QHeaderView.Fixed)
            t.setColumnWidth(i, widths[i])
        else:
            hh.setSectionResizeMode(i, QHeaderView.ResizeToContents)
    for ri, row in enumerate(rows):
        for ci, (text, font) in enumerate(row):
            item = QTableWidgetItem(text)
            item.setFont(font)
            t.setItem(ri, ci, item)
    t.setShowGrid(True)
    return t


# --------------------------------------------------------------------------- sighting
class SightingPage(QWidget):
    def __init__(self, ctrl, parent=None):
        super().__init__(parent)
        self.ctrl = ctrl

        self.sky = SkyWidget()
        self.alt_chart = AltitudeChartWidget()
        self.global_widget = GlobalVisibilityWidget()
        self.global_widget.set_tex(ctrl.tex)

        self.mode_combo = QComboBox()
        self.mode_combo.addItems(["Local - this evening",
                                  "Global visibility map"])
        self.mode_combo.setToolTip("G - toggle between the local sky diagram "
                                   "and the world visibility map")
        self.crit_combo = QComboBox()
        self.crit_combo.addItems(["Odeh (2006)", "MABIMS 2023", "Danjon limit"])
        self.crit_combo.setToolTip("Criteria used to colour the map")
        self._crit_keys = ["odeh", "mabims", "danjon"]
        self.mode_combo.currentIndexChanged.connect(self._set_mode)
        self.crit_combo.currentIndexChanged.connect(self._on_crit)

        local_page = QWidget()
        ll = QVBoxLayout(local_page)
        ll.setContentsMargins(0, 0, 0, 0)
        ll.setSpacing(6)
        ll.addWidget(self.sky, 5)
        ll.addWidget(self.alt_chart, 3)

        global_page = QWidget()
        gl = QVBoxLayout(global_page)
        gl.setContentsMargins(0, 0, 0, 0)
        gl.addWidget(self.global_widget)

        self.left_stack = QStackedWidget()
        self.left_stack.addWidget(local_page)
        self.left_stack.addWidget(global_page)

        ctrl_row = QHBoxLayout()
        ctrl_row.setSpacing(8)
        ctrl_row.addWidget(self.mode_combo)
        ctrl_row.addWidget(self.crit_combo)
        ctrl_row.addStretch(1)

        left = QVBoxLayout()
        left.setSpacing(6)
        left.addLayout(ctrl_row)
        left.addWidget(self.left_stack, 1)
        left_host = QWidget()
        left_host.setLayout(left)

        self.lbl_date = QLabel()
        self.lbl_date.setObjectName("section")
        self.lbl_date.setStyleSheet(
            "font-size: 15px; font-weight: 600; color: %s;" % theme.TEXT)
        self.lbl_date.setWordWrap(True)
        self.lbl_loc = QLabel()
        self.lbl_loc.setStyleSheet("color: %s;" % theme.TEXT_MUT)
        self.lbl_loc.setWordWrap(True)
        self.lbl_moon = QLabel()
        self.verdict_chip = StatusChip()
        self.lbl_zone = QLabel()
        self.lbl_zone.setStyleSheet("color: %s;" % theme.TEXT_MUT)
        self.lbl_zone.setWordWrap(True)

        summary = _table(["", "Value"], [], widths=[130, 200])
        summary.setMaximumHeight(400)
        self.tbl = summary

        crit = _table(["Criterion", "Result", "Condition"], [], widths=[110, 70, 150])
        self.crit_tbl = crit

        self.lbl_words = QLabel()
        self.lbl_words.setWordWrap(True)
        self.lbl_words.setStyleSheet("color: %s;" % theme.TEXT_DIM)

        header = QHBoxLayout()
        header.setSpacing(12)
        header.addWidget(self.lbl_moon)
        right_cols = QVBoxLayout()
        right_cols.addWidget(self.lbl_date)
        right_cols.addWidget(self.lbl_loc)
        header.addLayout(right_cols)
        header.addStretch(1)

        words_box = QGroupBox("In plain words")
        wl = QVBoxLayout(words_box)
        wl.addWidget(self.lbl_words)

        crit_box = QGroupBox("Visibility criteria")
        cl = QVBoxLayout(crit_box)
        cl.addWidget(self.crit_tbl)

        param_box = QGroupBox("Evening parameters")
        pl = QVBoxLayout(param_box)
        pl.addWidget(self.tbl)

        right = QScrollArea()
        right.setWidgetResizable(True)
        right.setMinimumWidth(320)
        right.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        right.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        right_container = QWidget()
        rlay = QVBoxLayout(right_container)
        rlay.setContentsMargins(0, 0, 0, 0)
        rlay.setSpacing(10)
        rlay.addLayout(header)
        rlay.addWidget(self.verdict_chip)
        rlay.addWidget(self.lbl_zone)
        rlay.addWidget(crit_box)
        rlay.addWidget(param_box)
        rlay.addWidget(words_box)
        rlay.addStretch(1)
        right.setWidget(right_container)

        split = QSplitter(Qt.Horizontal)
        split.addWidget(panel_frame(left_host))
        split.addWidget(right)
        split.setStretchFactor(0, 3)
        split.setStretchFactor(1, 1)
        split.setSizes([900, 350])
        _install_resize(self, split)
        outer = QVBoxLayout(self)
        outer.addWidget(split)

        ctrl.dataChanged.connect(self.update_view)
        ctrl.globalMapChanged.connect(self._sync_global)
        QShortcut(QKeySequence("G"), self).activated.connect(self._toggle_mode)
        self.update_view()

    def _toggle_mode(self):
        self.mode_combo.setCurrentIndex(1 - self.mode_combo.currentIndex())

    def _set_mode(self, index):
        self.left_stack.setCurrentIndex(index)
        self.crit_combo.setEnabled(index == 1)
        if index == 1:
            self.ctrl.ensure_global_map()
            self._sync_global()

    def _on_crit(self, index):
        self.global_widget.set_crit(self._crit_keys[index])

    def _sync_global(self):
        c = self.ctrl
        self.global_widget.set_observer(c.lat, c.lon, c.city)
        self.global_widget.set_data(c.global_map)
        self.global_widget.set_status(c.global_map_state, c.global_map_prog,
                                      c.global_map_error)
        if self.left_stack.currentIndex() == 1:
            c.ensure_global_map()

    def update_view(self):
        c = self.ctrl
        self._sync_global()
        self.sky.set_data(c.report, c.altseries)
        self.alt_chart.set_data(c.series14, c.date)
        self.lbl_date.setText(fmt_date(c.date))
        self.lbl_loc.setText("%s   |   %s" % (c.city, coord_str(c.lat, c.lon, c.tz)))
        r = c.report

        if r is not None:
            pm = crescent_pixmap(26, r["illum"],
                                 crescent_rot(r["m_az"], r["m_alt"],
                                              r["s_az"], r["s_alt"]))
            self.lbl_moon.setPixmap(pm)
        else:
            self.lbl_moon.clear()

        word, kind = c.verdict()
        self.verdict_chip.set_kind(word, kind)
        self.lbl_zone.setText("Odeh zone %s - %s" % (r["zone"], r["zone_label"])
                              if r else "")

        if r is None:
            rows = [("Sunset", "-"), ("Moonset", "-"), ("Lag", "-"),
                    ("Best time", "-"), ("Moon age", "-"), ("Illumination", "-"),
                    ("Arc of light", "-"), ("Moon altitude", "-"),
                    ("Arc of vision", "-"), ("Crescent width", "-")]
            self._fill(self.tbl, rows)
            self._fill_crit(None)
            self.lbl_words.setText("No sunset on this date here.")
            return

        if r["lag"] is not None:
            lag = "%.0f min" % r["lag"]
        elif r["m_alt_sunset"] > 0:
            lag = "above horizon all evening"
        else:
            lag = "moon already set"
        rows = [
            ("Sunset", fmt_time(r["sunset"])),
            ("Moonset", fmt_time(r["moonset"])),
            ("Lag", lag),
            ("Best time", fmt_time(r["best"])),
            ("Moon age", fmt_age_h(r["age_sunset"])),
            ("Illumination", "%.1f %%" % (r["illum"] * 100)),
            ("Arc of light", "%.2f°" % r["arc_l_sunset"]),
            ("Moon altitude", "%.2f°" % r["m_alt_sunset"]),
            ("Arc of vision", "%.2f°" % r["arc_v"]),
            ("Crescent width", "%.2f'" % r["w"]),
        ]
        self._fill(self.tbl, rows)
        self._fill_crit(r)
        self.lbl_words.setText("\n".join(c.plain_summary()))

    def _fill(self, t, rows):
        t.setRowCount(len(rows))
        mono = F(9, mono=True)
        for i, (label, value) in enumerate(rows):
            a = QTableWidgetItem(label)
            a.setFont(F(9))
            a.setForeground(QColor(theme.TEXT_MUT))
            b = QTableWidgetItem(value)
            b.setFont(mono)
            t.setItem(i, 0, a)
            t.setItem(i, 1, b)
        t.resizeRowsToContents()

    def _fill_crit(self, r):
        if r is None:
            self._fill_crit_rows([("MABIMS 2023", "FAIL", "-"),
                                  ("Danjon", "FAIL", "-"),
                                  ("Odeh 2006", "FAIL", "zone -")])
            return
        rows = [
            ("MABIMS 2023", r["mabims"],
             "ArcL>=%.1f & alt>=%.1f" % (astronomy.MABIMS_ARC_L_MIN,
                                          astronomy.MABIMS_ALT_MIN)),
            ("Danjon", r["danjon"],
             "ArcL>=%.1f" % astronomy.DANJON_ARC_L_MIN),
            ("Odeh 2006", r["zone"] in ("A", "B", "C"), "zone %s" % r["zone"]),
        ]
        self._fill_crit_rows([(n, ("PASS" if ok else "FAIL"), note)
                              for n, ok, note in rows])

    def _fill_crit_rows(self, rows):
        t = self.crit_tbl
        t.setRowCount(len(rows))
        for i, (name, res, note) in enumerate(rows):
            t.setItem(i, 0, QTableWidgetItem(name))
            n = QTableWidgetItem(note)
            n.setFont(F(8))
            n.setForeground(QColor(theme.TEXT_DIM))
            t.setItem(i, 2, n)
            r = QTableWidgetItem(res)
            r.setForeground(QColor(theme.OK if res == "PASS" else theme.ERR))
            r.setFont(F(9, mono=True))
            t.setItem(i, 1, r)
        t.resizeRowsToContents()


def left_widget(*widgets, stretches=(1,)):
    """Wrap widgets into a container owned by the chapter's panel frame."""
    w = QWidget()
    lay = QVBoxLayout(w)
    lay.setContentsMargins(0, 0, 0, 0)
    lay.setSpacing(8)
    for i, item in enumerate(widgets):
        stretch = stretches[i] if i < len(stretches) else 1
        lay.addWidget(item, stretch)
    return w


def _balance(split, panel_min=320, panel_max=440):
    """Keep the right-hand panel at a comfortable share of the window."""
    avail = split.width()
    if avail <= panel_min + 1:
        return
    target = min(panel_max, max(panel_min, int(avail * 0.26)))
    sizes = split.sizes()
    if len(sizes) > 1 and abs(sizes[1] - target) > 10:
        split.setSizes([max(1, avail - target), target])


def _install_resize(page, split):
    """Rebalance the splitter as the page grows / shrinks (feeds resize)."""
    base = page.resizeEvent

    def resize(event):
        base(event)
        _balance(split)

    page.resizeEvent = resize
    _balance(split)


# --------------------------------------------------------------------------- analysis
ANALYSIS_X_CHOICES = ["ArcL", "MAlt", "ArcV", "W", "LT", "MA"]

VIEW_INFO = {
    "cond": ("Condition", "Criteria versus the sighting database.  Each dot is "
             "one recorded evening; the amber lines are the MABIMS limits."),
    "equa": ("Equation", "Boundary-curve test.  The purple curve is the "
             "visibility boundary from the fitted equation."),
    "thres": ("Threshold", "Minimum observed values of a chosen parameter for "
              "actually-seen crescents, split by observing method."),
}


class AnalysisPage(QWidget):
    def __init__(self, kind, ctrl, parent=None):
        super().__init__(parent)
        self.kind = kind
        self.ctrl = ctrl

        if kind == "thres":
            self.chart = BoxPlotWidget()
        else:
            self.chart = ScatterWidget()

        self.param_combo = QComboBox()
        self.param_combo.addItems(ANALYSIS_X_CHOICES)
        self.param_combo.setCurrentText(ctrl.analysis_x)
        self.param_combo.currentTextChanged.connect(self._param_changed)
        self.param_combo.setVisible(kind == "thres")

        self.lbl_title = QLabel()
        self.lbl_title.setObjectName("section")
        self.lbl_title.setStyleSheet("font-size: 16px; font-weight: 600; color: %s;" % theme.ACCENT)
        self.lbl_desc = QLabel()
        self.lbl_desc.setWordWrap(True)
        self.lbl_desc.setStyleSheet("color: %s;" % theme.TEXT_MUT)
        self.lbl_info = QLabel()
        self.lbl_info.setWordWrap(True)
        self.lbl_info.setStyleSheet("color: %s;" % theme.TEXT_DIM)

        self.stats = _table(["Breakdown", "Value"], [], widths=[150, 170])
        self.err = _table(["Method", "Positive %", "Negative %"], [], widths=[120, 90, 90])

        head_group = QGroupBox("Analysis")
        hl = QVBoxLayout(head_group)
        hl.addWidget(self.lbl_title)
        hl.addWidget(self.lbl_desc)
        hl.addWidget(self.param_combo)
        hl.addWidget(self.lbl_info)

        info_group = QGroupBox("Error rates")
        info_group.setStyleSheet("QGroupBox { margin-top: 12px; }")
        il = QVBoxLayout(info_group)
        il.addWidget(self.err)
        note = QLabel("Positive = seen but criterion missed; negative = unseen "
                      "but criterion said visible.")
        note.setWordWrap(True)
        note.setStyleSheet("color: %s;" % theme.TEXT_DIM)
        il.addWidget(note)

        stats_group = QGroupBox("Observed minimums")
        sl = QVBoxLayout(stats_group)
        sl.addWidget(self.stats)

        right = QScrollArea()
        right.setWidgetResizable(True)
        right.setMinimumWidth(320)
        right.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        right.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        holder = QWidget()
        rl = QVBoxLayout(holder)
        rl.addWidget(head_group)
        rl.addWidget(stats_group if kind == "thres" else info_group)
        rl.addStretch(1)
        right.setWidget(holder)

        split = QSplitter(Qt.Horizontal)
        split.addWidget(self.chart)
        split.addWidget(right)
        split.setStretchFactor(0, 3)
        split.setStretchFactor(1, 1)
        split.setSizes([900, 350])
        _install_resize(self, split)
        outer = QVBoxLayout(self)
        outer.addWidget(split)

        ctrl.dataChanged.connect(self.update_view)
        ctrl.analysisChanged.connect(self.update_view)
        self.update_view()

    def _param_changed(self, text):
        if self.kind != "thres":
            return
        self.ctrl.analysis_x = text
        self.ctrl.invalidate_analysis()

    def update_view(self):
        c = self.ctrl
        res = c.analysis_result(self.kind)
        name, desc = VIEW_INFO[self.kind]
        self.lbl_title.setText(name)
        self.lbl_desc.setText(desc)

        if self.kind == "thres":
            self.chart.set_res(res, highlight=c.current_highlight("thres"))
            infos = ["X = %s (%s)" % ("parameter", res["xlabel"])]
            self.lbl_info.setText("\n".join(infos))
            rows = [("%s  (n=%d)" % (k, v["count"]),
                     "min %.2f | med %.2f | max %.2f" % (v["min"], v["median"], v["max"]))
                    for k, v in res["series"].items()]
            self.stats.setRowCount(max(1, len(rows)))
            for i, (k, v) in enumerate(rows):
                a = QTableWidgetItem(k); a.setFont(F(9))
                b = QTableWidgetItem(v); b.setFont(F(9, mono=True))
                self.stats.setItem(i, 0, a); self.stats.setItem(i, 1, b)
            self.stats.resizeRowsToContents()
        else:
            hl = c.current_highlight("cond" if self.kind == "cond" else "equa")
            self.chart.set_res(res, self.kind, highlight=hl)
            if self.kind == "cond":
                self.lbl_info.setText(
                    "X = ArcL (arc of light, °)\n"
                    "Y = MAlt (moon altitude, °)\n"
                    "Criteria line: ArcL %.1f° and MAlt %.1f°"
                    % (res["conditionx"], res["conditiony"]))
            else:
                self.lbl_info.setText(
                    "X = LT (lag time, min)\nY = ArcL (arc of light, °)\n"
                    "Boundary f(x): %s" % res["equation"])
            rows = []
            for label, (pos, neg) in res["error_rates"].items():
                rows.append((label, "%.1f%%" % pos, "%.1f%%" % neg))
            self.err.setRowCount(len(rows))
            for i, (label, pos, neg) in enumerate(rows):
                a = QTableWidgetItem(label); a.setFont(F(9))
                b = QTableWidgetItem(pos); b.setFont(F(9, mono=True))
                cw = QTableWidgetItem(neg); cw.setFont(F(9, mono=True))
                for item, v in ((b, pos), (cw, neg)):
                    num = float(v.rstrip("%"))
                    col = theme.OK if num < 5 else (theme.WARN if num < 15 else theme.ERR)
                    item.setForeground(QColor(col))
                self.err.setItem(i, 0, a)
                self.err.setItem(i, 1, b)
                self.err.setItem(i, 2, cw)
            self.err.resizeRowsToContents()


# --------------------------------------------------------------------------- verify
class VerifyPage(QWidget):
    def __init__(self, ctrl, parent=None):
        super().__init__(parent)
        self.ctrl = ctrl
        self.chart = ScatterWidget()
        self.chart.set_title("ALL RECORDED SIGHTINGS")

        self.lbl_status = QLabel()
        self.lbl_status.setWordWrap(True)
        self.btn_run = QPushButton("Run comparison")
        self.btn_run.clicked.connect(ctrl.run_hz_check)

        self.hz = _table(["Parameter", "Ours", "NASA", "Result"],
                         [], widths=[130, 60, 60, 55])
        self.lbl_obs = QLabel()
        self.lbl_obs.setWordWrap(True)
        self.lbl_obs.setStyleSheet("color: %s;" % theme.TEXT_DIM)

        hz_group = QGroupBox("")
        hl = QVBoxLayout(hz_group)
        title = QLabel("NASA / JPL HORIZONS")
        title.setStyleSheet("font-weight: 600; font-size: 11px; "
                            "color: %s;" % theme.ACCENT)
        hl.addWidget(title)
        sub = QLabel("Our sunset / moonset / moon values vs the official "
                     "ephemeris (live)")
        sub.setWordWrap(True)
        sub.setStyleSheet("color: %s;" % theme.TEXT_DIM)
        hl.addWidget(sub)
        hl.addWidget(self.hz)
        hl.addWidget(self.lbl_status)
        hl.addWidget(self.btn_run)

        obs_group = QGroupBox("Recorded sightings")
        ol = QVBoxLayout(obs_group)
        ol.addWidget(self.lbl_obs)

        right = QScrollArea()
        right.setWidgetResizable(True)
        right.setMinimumWidth(320)
        right.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        right.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        holder = QWidget()
        rl = QVBoxLayout(holder)
        rl.addWidget(hz_group)
        rl.addWidget(obs_group)
        rl.addStretch(1)
        right.setWidget(holder)

        split = QSplitter(Qt.Horizontal)
        split.addWidget(self.chart)
        split.addWidget(right)
        split.setStretchFactor(0, 3)
        split.setStretchFactor(1, 1)
        split.setSizes([900, 350])
        _install_resize(self, split)
        outer = QVBoxLayout(self)
        outer.addWidget(split)

        ctrl.dataChanged.connect(self.update_view)
        ctrl.verifyChanged.connect(self.update_view)
        self.update_view()

    def update_view(self):
        c = self.ctrl
        res = c.analysis_result("cond")
        self.chart.set_res(res, "cond",
                           highlight=c.current_highlight("cond"))
        self._update_hz()
        self._update_obs()

    def _update_hz(self):
        c = self.ctrl
        names = [
            ("sunset", "Sunset"),
            ("moonset", "Moonset"),
            ("m_alt_sunset", "Moon alt. at sunset"),
            ("m_az_sunset", "Moon az. at sunset"),
            ("arc_l_sunset", "Arc of light"),
            ("illum", "Illumination"),
        ]
        state = c.verify["hz_state"]
        comp = c.verify.get("hz") or {}
        rows = []
        for key, label in names:
            if state in ("running", "idle"):
                pair, verdict, vk = ("-", "-"), "-", "info"
            elif key in comp:
                mine, theirs = comp[key]
                if mine is None or theirs is None:
                    pair, verdict, vk = ("-", "-"), "-", "info"
                else:
                    pair = ((mine.strftime("%H:%M"), theirs.strftime("%H:%M"))
                            if key in ("sunset", "moonset")
                            else ("%.2f" % mine, "%.2f" % theirs))
                    v = comp["verdicts"].get(key)
                    if v is None:
                        verdict, vk = "-", "info"
                    else:
                        verdict, vk = ("PASS" if v else "FAIL",
                                       "ok" if v else "err")
            else:
                pair, verdict, vk = ("-", "-"), "-", "info"
            rows.append((label, pair[0], pair[1], (verdict, vk)))
        self.hz.setRowCount(len(rows))
        for i, (label, ours, nasa, (res, vk)) in enumerate(rows):
            for j, (txt, mono) in enumerate(((label, False), (ours, True),
                                             (nasa, True))):
                item = QTableWidgetItem(txt)
                item.setFont(F(9, mono=mono))
                self.hz.setItem(i, j, item)
            ritem = QTableWidgetItem(res)
            ritem.setFont(F(9, mono=True))
            ritem.setForeground(QColor(theme.chip_color(vk)))
            self.hz.setItem(i, 3, ritem)
        self.hz.resizeRowsToContents()

        if state == "idle":
            status, kind = "Press 'Run' to compare with NASA", "info"
        elif state == "running":
            status, kind = "Contacting NASA HORIZONS...", "info"
        elif state == "done":
            passed = sum(1 for v in comp.get("verdicts", {}).values() if v)
            status, kind = "OK - %d/%d within tolerance" % (
                passed, len(comp.get("verdicts", {}))), "ok"
        elif state == "stale":
            status, kind = "Date changed - press 'Run' to re-check", "warn"
        else:
            status, kind = "Error: %s" % (c.verify.get("hz_error") or "unknown"), "err"
        self.lbl_status.setText(status)
        self.lbl_status.setStyleSheet(
            "color: %s; font-weight: 600;" % theme.chip_color(kind).name())

    def _update_obs(self):
        c = self.ctrl
        state = c.verify["obs_state"]
        if state == "done" and c.verify.get("obs"):
            obs = c.verify["obs"]
            lines = ["Compared our verdict against %d recorded sightings."
                     % obs["n"],
                     "Match rate: %.1f%%" % (obs["agreement_pct"] or 0.0)]
            for label, pct in obs.get("by_method", {}).items():
                lines.append("%s: %.1f%%" % (label, pct))
            err = obs.get("err_arc_l", {})
            if err.get("mean") is not None:
                lines.append("Average arc-of-light error: %.2f° (n=%d)"
                             % (err["mean"], err["n"]))
            self.lbl_obs.setText("\n".join(lines))
        elif state == "running":
            self.lbl_obs.setText("Scanning the sighting database...")
        else:
            self.lbl_obs.setText("Not started yet.")


# --------------------------------------------------------------------------- live
class PhoneCalDialog(QDialog):
    """Calibrate phone pointing against the Moon or Sun.

    Workflow (matches Settings -> Phone link -> Calibrate):
    1. Physically point the phone's selected edge at the Moon (or Sun).
    2. Drag the horizon sky map so that body sits in the middle of the
       screen (or press "Center map on target").
    3. Press "Calibrate".  The azimuth/altitude offset between the raw
       phone aim and the reference is stored and applied to every future
       phone frame until Reset.
    """

    def __init__(self, page, parent=None):
        super().__init__(parent)
        self.page = page
        self.setWindowTitle("Calibrate phone pointing")
        self.setModal(True)
        self.setMinimumWidth(460)

        try:
            axis_txt = ("top edge" if self.page.cmb_axis.currentData()
                        == "top" else "back camera")
        except Exception:
            axis_txt = "top edge"
        info = QLabel(
            "Point the phone's <b>%s</b> directly at the "
            "<b>Moon</b> (or Sun), then drag the sky map so that body is "
            "in the <b>middle of the screen</b> and press "
            "<b>Calibrate</b>. The offset is saved and applied to all "
            "future phone aims.<br><br>"
            "Stand on your spot and turn your body to pan: "
            "rotation-vector (+ magnetic field) aims from your origin, "
            "no walking needed.<br><br>"
            "<b>Sun safety:</b> never look directly at the Sun; aim "
            "roughly using the phone's shadow instead." % axis_txt)
        info.setTextFormat(Qt.RichText)
        info.setWordWrap(True)
        info.setStyleSheet("color: %s;" % theme.TEXT_MUT)

        target_row = QHBoxLayout()
        target_row.addWidget(QLabel("Reference body"))
        self.cmb_target = QComboBox()
        self.cmb_target.addItems(["Moon", "Sun"])
        self.cmb_target.currentIndexChanged.connect(self._refresh)
        target_row.addWidget(self.cmb_target, 1)

        self.lbl_true = QLabel("--")
        self.lbl_raw = QLabel("--")
        self.lbl_view = QLabel("--")
        self.lbl_off = QLabel("--")
        for lab in (self.lbl_true, self.lbl_raw, self.lbl_view,
                    self.lbl_off):
            lab.setStyleSheet("font-family: Consolas; color: %s;"
                              % theme.TEXT)
            lab.setWordWrap(True)

        form = QVBoxLayout()
        form.addWidget(QLabel("True position (app ephemeris)"))
        form.addWidget(self.lbl_true)
        form.addWidget(QLabel("Phone aim (raw, before calibration)"))
        form.addWidget(self.lbl_raw)
        form.addWidget(QLabel("Sky-map centre (drag the body here)"))
        form.addWidget(self.lbl_view)
        form.addWidget(QLabel("Offset that Calibrate would store"))
        form.addWidget(self.lbl_off)

        btn_center = QPushButton("Center map on target")
        btn_center.setToolTip("Pan the horizon sky map to the true "
                              "Moon/Sun position")
        btn_center.clicked.connect(self._center_on_target)
        self.btn_center = btn_center

        btn_cal_target = QPushButton("Calibrate to Moon/Sun")
        btn_cal_target.setProperty("primary", True)
        btn_cal_target.setToolTip("Store the offset phone-raw -> true body")
        btn_cal_target.clicked.connect(self._cal_to_target)
        self.btn_cal_target = btn_cal_target

        btn_cal_view = QPushButton("Calibrate to view centre")
        btn_cal_view.setToolTip("Store the offset phone-raw -> current "
                                "map centre (use after dragging the body "
                                "to the middle)")
        btn_cal_view.clicked.connect(self._cal_to_view)
        self.btn_cal_view = btn_cal_view

        btn_reset = QPushButton("Reset")
        btn_reset.setToolTip("Clear the stored azimuth/altitude offset")
        btn_reset.clicked.connect(self._reset)

        btn_close = QPushButton("Close")
        btn_close.clicked.connect(self.accept)

        row1 = QHBoxLayout()
        row1.addWidget(btn_center, 1)
        row1.addWidget(btn_reset)
        row1.addWidget(btn_close)
        row2 = QHBoxLayout()
        row2.addWidget(btn_cal_target, 1)
        row2.addWidget(btn_cal_view, 1)

        lay = QVBoxLayout(self)
        lay.addWidget(info)
        lay.addLayout(target_row)
        lay.addLayout(form)
        lay.addLayout(row1)
        lay.addLayout(row2)

        self._timer = QTimer(self)
        self._timer.setInterval(500)
        self._timer.timeout.connect(self._refresh)
        self._timer.start()
        self._refresh()

    def _target_name(self):
        return self.cmb_target.currentText()

    def _true_pos(self):
        live = self.page.ctrl.live
        if not live:
            return None
        try:
            if self._target_name() == "Sun":
                return float(live["s_az"]), float(live["s_alt"])
            return float(live["m_az"]), float(live["m_alt"])
        except (KeyError, TypeError, ValueError):
            return None

    def _refresh(self):
        true = self._true_pos()
        raw = self.page.last_raw_aim()
        view = (self.page.horizon_widget.az_center,
                self.page.horizon_widget.alt_center)
        north = self.page.spin_north.value()

        if true is None:
            self.lbl_true.setText("waiting for live data...")
        else:
            self.lbl_true.setText("az %06.1f°   alt %+06.1f°"
                                  % (true[0], true[1]))
        if raw[0] is None:
            self.lbl_raw.setText("waiting for phone aim... "
                                 "(connect + stream Rotation Vector)")
        else:
            self.lbl_raw.setText("az %06.1f°   alt %+06.1f°   "
                                 "(north %+05.1f°)" % (raw[0], raw[1], north))
        self.lbl_view.setText("az %06.1f°   alt %+06.1f°" % (view[0], view[1]))

        can = raw[0] is not None and true is not None
        if can:
            off = calibration_from_aim(raw[0], raw[1], true[0], true[1],
                                       north)
            self.lbl_off.setText("az %+07.1f°   alt %+06.1f°" % off)
        else:
            self.lbl_off.setText("--")
        self.btn_cal_target.setEnabled(bool(can))
        self.btn_cal_view.setEnabled(raw[0] is not None)
        self.btn_center.setEnabled(true is not None)
        self.btn_cal_target.setText("Calibrate to %s" % self._target_name())

    def _center_on_target(self):
        true = self._true_pos()
        if true is None:
            return
        self.page.horizon_widget.set_aim(true[0], true[1])
        # show the horizon map so the user sees the body centred
        try:
            self.page.cmb_view.setCurrentIndex(1)
        except Exception:
            pass
        self._refresh()

    def _cal_to_target(self):
        true = self._true_pos()
        raw = self.page.last_raw_aim()
        if true is None or raw[0] is None:
            return
        off = calibration_from_aim(raw[0], raw[1], true[0], true[1],
                                   self.page.spin_north.value())
        self.page.set_calibration(off[0], off[1])
        self.page.horizon_widget.set_aim(true[0], true[1])
        self._refresh()

    def _cal_to_view(self):
        raw = self.page.last_raw_aim()
        if raw[0] is None:
            return
        view = (self.page.horizon_widget.az_center,
                self.page.horizon_widget.alt_center)
        off = calibration_from_aim(raw[0], raw[1], view[0], view[1],
                                   self.page.spin_north.value())
        self.page.set_calibration(off[0], off[1])
        self._refresh()

    def _reset(self):
        self.page.set_calibration(0.0, 0.0)
        self._refresh()


class LivePage(QWidget):
    def __init__(self, ctrl, parent=None):
        super().__init__(parent)
        self.ctrl = ctrl
        self.live_widget = SightingSky3D()
        self.live_widget.set_tex(ctrl.tex)

        self.horizon_widget = HorizonSkyWidget()
        self.horizon_widget.set_tex(ctrl.tex)

        view_stack = QStackedWidget()
        view_stack.addWidget(self.live_widget)
        view_stack.addWidget(self.horizon_widget)
        self.view_stack = view_stack

        self.cmb_view = QComboBox()
        self.cmb_view.addItems(["3D Sighting Sky", "Horizon sky map"])
        self.cmb_view.currentIndexChanged.connect(self._on_view_changed)

        self.lbl_clock = QLabel()
        self.lbl_clock.setStyleSheet("font-family: Consolas; font-size: 22px; color: %s;" % theme.OK)
        self.lbl_clock_sub = QLabel("local time - updates every 5 s")
        self.lbl_clock_sub.setWordWrap(True)
        self.lbl_clock_sub.setStyleSheet("color: %s;" % theme.TEXT_DIM)
        self.lbl_verdict = StatusChip()
        self.lbl_zone = QLabel()
        self.lbl_zone.setStyleSheet("color: %s;" % theme.TEXT_MUT)
        self.lbl_zone.setWordWrap(True)

        self.tbl = _table(["Live parameter", "Value"], [], widths=[130, 200])
        rows = [("Sun alt", ".."), ("Moon alt", ".."), ("Moon now", ".."),
                ("Phase", ".."), ("Moon age", ".."), ("Illumination", ".."),
                ("Moonrise", ".."), ("Moonset", "..")]
        self._tbl_rows = rows
        self.tbl.setRowCount(len(rows))
        for i, (k, v) in enumerate(rows):
            a = QTableWidgetItem(k); a.setFont(F(9))
            a.setForeground(QColor(theme.TEXT_MUT))
            b = QTableWidgetItem(v); b.setFont(F(9, mono=True))
            self.tbl.setItem(i, 0, a); self.tbl.setItem(i, 1, b)

        l_group = QGroupBox("Live status")
        ll = QVBoxLayout(l_group)
        ll.addWidget(self.lbl_clock)
        ll.addWidget(self.lbl_clock_sub)
        ll.addWidget(self.lbl_verdict)
        ll.addWidget(self.lbl_zone)
        ll.addWidget(self.tbl, 1)
        l_group.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.tbl.verticalHeader().setSectionResizeMode(QHeaderView.ResizeToContents)
        self.tbl.setMinimumHeight(240)
        self.tbl.verticalHeader().setDefaultSectionSize(26)

        right = QWidget()
        right.setMinimumWidth(320)
        rl = QVBoxLayout(right)
        rl.setContentsMargins(0, 0, 0, 0)
        rl.setSpacing(8)
        rl.addWidget(self._build_phone_box())
        rl.addWidget(l_group, 1)

        view_panel = QWidget()
        vpl = QVBoxLayout(view_panel)
        vpl.setContentsMargins(0, 0, 0, 0)
        vpl.setSpacing(4)
        header = QHBoxLayout()
        header.addWidget(QLabel("View"))
        header.addWidget(self.cmb_view)
        header.addStretch(1)
        vpl.addLayout(header)
        vpl.addWidget(self.view_stack, 1)

        split = QSplitter(Qt.Horizontal)
        split.addWidget(view_panel)
        split.addWidget(right)
        split.setStretchFactor(0, 3)
        split.setStretchFactor(1, 1)
        split.setSizes([900, 350])
        _install_resize(self, split)

        scrub = QFrame()
        scrub.setStyleSheet("QFrame { background: %s; border: 1px solid %s;"
                            " border-radius: 6px; }" % (theme.PANEL, theme.BORDER))
        scrub.setFixedHeight(38)
        scrub.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        hl = QHBoxLayout(scrub)
        hl.setContentsMargins(10, 6, 10, 6)
        hl.setSpacing(10)
        hl.addWidget(QLabel("LIVE time"))
        self.live_slider = QSlider(Qt.Horizontal)
        self.live_slider.setRange(0, 24 * 60 - 1)
        self.live_slider.setSingleStep(5)
        self.live_slider.setPageStep(30)
        self.live_slider.setToolTip("Move through the 24 hours of the selected day")
        hl.addWidget(self.live_slider, 1)
        self.lbl_sim = QLabel()
        self.lbl_sim.setStyleSheet("color: %s; font-family: Consolas; font-size: 13px;"
                                   % theme.C_TODAY)
        hl.addWidget(self.lbl_sim)
        self.btn_now = QPushButton("NOW")
        self.btn_now.setToolTip("Return to the current time and live updates")
        hl.addWidget(self.btn_now)

        outer = QVBoxLayout(self)
        outer.addWidget(split)
        outer.addWidget(scrub)

        self._debounce = QTimer(self)
        self._debounce.setSingleShot(True)
        self._debounce.setInterval(30)

        self.timer = QTimer(self)
        self.timer.timeout.connect(self._on_tick)
        self.timer.start(5000)

        ctrl.dataChanged.connect(self.update_view)
        self.update_view()

        self._debounce.timeout.connect(self._apply_slider)
        self.live_slider.valueChanged.connect(self._on_slider)
        self.btn_now.clicked.connect(self._go_now)

    # ------------------------------------------------------------ phone link
    def _build_phone_box(self):
        self._phone_base_loc = None
        self._phone_loc = None
        self._settings = QSettings("MoonWatch", "PhonePointing")
        try:
            self._cal_az = float(self._settings.value("cal_az", 0.0))
            self._cal_alt = float(self._settings.value("cal_alt", 0.0))
        except (TypeError, ValueError):
            self._cal_az, self._cal_alt = 0.0, 0.0
        self._cal_az = wrap_az_delta(self._cal_az)
        self._cal_alt = max(-30.0, min(30.0, self._cal_alt))
        self._raw_aim = (None, None)
        self._last_phone_ts = 0.0
        self._last_phone_corr = (None, None)

        box = QGroupBox(
            "Phone link - aim the sky map with your phone (SensorCast)")
        lay = QVBoxLayout(box)
        lay.setSpacing(6)

        self.lbl_phone_status = QLabel(
            "not connected\u2014enter your SensorCast username and press "
            "<b>Connect</b>")
        self.lbl_phone_status.setTextFormat(Qt.RichText)
        self.lbl_phone_status.setStyleSheet("color: %s;" % theme.TEXT_DIM)
        self.lbl_phone_status.setWordWrap(True)
        lay.addWidget(self.lbl_phone_status)

        row = QHBoxLayout()
        self.edit_username = QLineEdit()
        self.edit_username.setPlaceholderText(
            "SensorCast username, e.g. incredibleamir_5338")
        self.edit_username.setToolTip(
            "Username shown in the SensorCast Android app; keep the app "
            "streaming and the phone on the internet")
        self.edit_username.returnPressed.connect(self._phone_toggle)
        btn_connect = QPushButton("Connect")
        btn_connect.setFixedWidth(90)
        btn_connect.setToolTip("Connect to / disconnect from the SensorCast stream")
        btn_connect.clicked.connect(self._phone_toggle)
        self.btn_connect = btn_connect
        row.addWidget(QLabel("Username"))
        row.addWidget(self.edit_username, 1)
        row.addWidget(self.btn_connect)
        lay.addLayout(row)

        self.lbl_phone_hint = QLabel(
            "Phone app: stream <b>Rotation Vector</b> + <b>Magnetic Field</b> "
            "(+ Accelerometer as backup) at the fastest delay; tick "
            "<b>GPS / Location</b> too if you want the live observer "
            "location. Stand on your spot, <b>top edge of the phone</b> "
            "toward the sky: turning your body pans left/right, tilting "
            "the top up/down pans vertically. If the view lags your hand, "
            "point the top at the Moon/Sun, drag it to the middle and press "
            "<b>Calibrate...</b>.")
        self.lbl_phone_hint.setTextFormat(Qt.RichText)
        self.lbl_phone_hint.setStyleSheet("color: %s;" % theme.TEXT_MUT)
        self.lbl_phone_hint.setWordWrap(True)
        lay.addWidget(self.lbl_phone_hint)

        axis_row = QHBoxLayout()
        axis_row.addWidget(QLabel("Point with"))
        self.cmb_axis = QComboBox()
        self.cmb_axis.addItem("Top edge of phone", "top")
        self.cmb_axis.addItem("Back camera", "back")
        self.cmb_axis.setToolTip(
            "Which phone direction aims the sky map: top edge (+Y, hold "
            "like a laser pointer) or back camera (-Z, photograph pose)")
        self.cmb_axis.currentIndexChanged.connect(self._on_axis_changed)
        axis_row.addWidget(self.cmb_axis, 1)
        lay.addLayout(axis_row)

        self.chk_drive = QCheckBox("Drive sky map from phone")
        self.chk_drive.setChecked(True)
        self.chk_drive.setToolTip(
            "Point the horizon sky map along the phone's selected "
            "direction in real space")
        lay.addWidget(self.chk_drive)

        self.chk_gps = QCheckBox("Use phone GPS location")
        self.chk_gps.setToolTip(
            "Move the observer location to the phone's GPS fix; the saved "
            "location is restored when this is switched off")
        self.chk_gps.toggled.connect(self._on_phone_gps_toggled)
        lay.addWidget(self.chk_gps)

        nor = QHBoxLayout()
        self.spin_north = QDoubleSpinBox()
        self.spin_north.setRange(-180.0, 180.0)
        self.spin_north.setDecimals(1)
        self.spin_north.setSingleStep(0.5)
        self.spin_north.setSuffix(" \u00b0")
        self.spin_north.setToolTip(
            "Added to the phone azimuth so magnetically-north readings line "
            "up with true north on the map (local magnetic declination, "
            "positive east)")
        try:
            saved_north = float(self._settings.value("north_offset", 0.0))
        except (TypeError, ValueError):
            saved_north = 0.0
        self.spin_north.setValue(max(-180.0, min(180.0, saved_north)))
        self.spin_north.valueChanged.connect(self._on_north_changed)
        nor.addWidget(QLabel("North offset"))
        nor.addWidget(self.spin_north)
        nor.addStretch(1)
        lay.addLayout(nor)

        cal_row = QHBoxLayout()
        self.lbl_cal = QLabel()
        self.lbl_cal.setStyleSheet("color: %s; font-family: Consolas;"
                                   % theme.TEXT_MUT)
        cal_row.addWidget(QLabel("Pointing cal"))
        cal_row.addWidget(self.lbl_cal, 1)
        self.btn_cal = QPushButton("Calibrate...")
        self.btn_cal.setToolTip(
            "Point the top edge of the phone at the Moon/Sun, drag that "
            "body to the middle of the sky map, then press Calibrate")
        self.btn_cal.clicked.connect(self._open_calibrate)
        cal_row.addWidget(self.btn_cal)
        self.btn_cal_reset = QPushButton("Reset")
        self.btn_cal_reset.setFixedWidth(60)
        self.btn_cal_reset.setToolTip("Clear the stored pointing offset")
        self.btn_cal_reset.clicked.connect(lambda: self.set_calibration(
            0.0, 0.0))
        cal_row.addWidget(self.btn_cal_reset)
        lay.addLayout(cal_row)
        self._update_cal_label()

        self.lbl_aim = QLabel("aim   az \u2014\u00b0   alt \u2014\u00b0")
        self.lbl_aim.setStyleSheet("color: %s; font-family: Consolas;"
                                   % theme.TEXT_MUT)
        lay.addWidget(self.lbl_aim)

        self.lbl_mag = QLabel("mag  -- uT")
        self.lbl_mag.setStyleSheet("color: %s; font-family: Consolas;"
                                   % theme.TEXT_MUT)
        self.lbl_mag.setToolTip("Live magnetic-field strength from the "
                                "phone. Earth field is ~25-65 uT; far "
                                "outside means indoor interference and the "
                                "compass (rotation vector) cannot be trusted")
        lay.addWidget(self.lbl_mag)
        self._last_mag_ts = 0.0

        self.phone = PhoneLink(box)
        self.phone.orient.connect(self._on_phone_orient)
        self.phone.loc.connect(self._on_phone_loc)
        self.phone.mag.connect(self._on_phone_mag)
        self.phone.status.connect(self._on_phone_status)
        self.phone.error.connect(self._on_phone_error)
        # restore the saved pointer axis (default: top edge)
        try:
            saved_axis = str(self._settings.value("aim_axis",
                                                  "top") or "top").lower()
        except Exception:
            saved_axis = "top"
        if saved_axis not in ("top", "back"):
            saved_axis = "top"
        self.cmb_axis.setCurrentIndex(0 if saved_axis == "top" else 1)
        self.phone.set_aim_axis(saved_axis)
        QApplication.instance().aboutToQuit.connect(self._phone_shutdown)
        return box

    def _phone_shutdown(self):
        self.phone.disconnect()

    def _phone_toggle(self):
        if self.phone.is_connected():
            self.phone.disconnect()
            self._set_phone_ui(connected=False)
        else:
            username = self.edit_username.text().strip()
            if not username:
                self.lbl_phone_status.setText(
                    "Enter your SensorCast username first")
                self.lbl_phone_status.setStyleSheet("color: %s;" % theme.ERR)
                return
            self.lbl_phone_status.setText(
                "connecting to <b>%s</b>\u2026" % username)
            self.lbl_phone_status.setStyleSheet("color: %s;" % theme.TEXT_DIM)
            self.phone.connect_stream(username)

    def _set_phone_ui(self, connected):
        self.btn_connect.setText("Disconnect" if connected else "Connect")
        self.edit_username.setEnabled(not connected)

    def _on_phone_status(self, connected, peer):
        if connected:
            self.lbl_phone_status.setText("streaming from <b>%s</b>" % peer)
            self.lbl_phone_status.setStyleSheet("color: %s;" % theme.OK)
        else:
            self.lbl_phone_status.setText(
                "not connected\u2014enter your SensorCast username and press "
                "<b>Connect</b>")
            self.lbl_phone_status.setStyleSheet("color: %s;" % theme.TEXT_DIM)
        self._set_phone_ui(connected)

    def _on_phone_error(self, text):
        self.lbl_phone_status.setText(text)
        self.lbl_phone_status.setStyleSheet("color: %s;" % theme.ERR)
        self._set_phone_ui(False)

    def _on_north_changed(self, value):
        try:
            self._settings.setValue("north_offset", float(value))
        except Exception:
            pass

    def _on_axis_changed(self, index):
        axis = self.cmb_axis.itemData(index) or "top"
        axis = str(axis).lower()
        if axis not in ("top", "back"):
            axis = "top"
        try:
            self._settings.setValue("aim_axis", axis)
        except Exception:
            pass
        try:
            self.phone.set_aim_axis(axis)
        except Exception:
            pass
        # Offsets are axis-specific; do not silently reuse a back-camera
        # calibration for the top edge (or vice versa).
        self.set_calibration(0.0, 0.0)
        self._raw_aim = (None, None)
        self._last_phone_corr = (None, None)
        self.chk_drive.setToolTip(
            "Point the horizon sky map along the phone's %s in real space"
            % ("top edge" if axis == "top" else "back camera"))

    def _on_phone_mag(self, _mx, _my, _mz, strength):
        now = time.monotonic()
        if now - self._last_mag_ts < 1.0:
            return
        self._last_mag_ts = now
        try:
            s = float(strength)
        except (TypeError, ValueError):
            return
        if 25.0 <= s <= 65.0:
            tag, col = "OK", theme.OK
        elif s <= 0.0:
            tag, col = "no mag yet", theme.TEXT_DIM
        else:
            tag, col = "interference?", theme.WARN
        self.lbl_mag.setText("mag  %05.1f uT  %s" % (s, tag))
        self.lbl_mag.setStyleSheet("color: %s; font-family: Consolas;" % col)

    def last_raw_aim(self):
        """Last raw (uncalibrated) phone aim, or (None, None)."""
        return self._raw_aim

    def set_calibration(self, az_off, alt_off):
        try:
            az_off = wrap_az_delta(float(az_off))
            alt_off = max(-30.0, min(30.0, float(alt_off)))
        except (TypeError, ValueError):
            return
        self._cal_az, self._cal_alt = az_off, alt_off
        try:
            self._settings.setValue("cal_az", az_off)
            self._settings.setValue("cal_alt", alt_off)
        except Exception:
            pass
        self._update_cal_label()
        # Re-apply to the last aim immediately so the map jumps to the
        # calibrated direction without waiting for the next sensor frame.
        if self._raw_aim[0] is not None and self.chk_drive.isChecked():
            corr_az, corr_alt = apply_calibration(
                self._raw_aim[0], self._raw_aim[1],
                self.spin_north.value(), self._cal_az, self._cal_alt)
            corr_alt = max(0.0, min(90.0, corr_alt))
            self.horizon_widget.set_aim(corr_az, corr_alt)

    def _update_cal_label(self):
        self.lbl_cal.setText("az %+05.1f°  alt %+05.1f°"
                             % (self._cal_az, self._cal_alt))

    def _open_calibrate(self):
        dlg = PhoneCalDialog(self, self)
        dlg.exec()

    def _on_phone_orient(self, _qx, _qy, _qz, _qw, az, alt):
        try:
            az = float(az) % 360.0
            alt = float(alt)
        except (TypeError, ValueError):
            return
        self._raw_aim = (az, alt)
        corr_az, corr_alt = apply_calibration(
            az, alt, self.spin_north.value(), self._cal_az, self._cal_alt)
        corr_alt = max(0.0, min(90.0, corr_alt))
        # Throttle high-rate sensor streams: repaint at most ~25 Hz and
        # skip imperceptible (<0.2 deg, <40 ms) jitter.
        now = time.monotonic()
        last = self._last_phone_corr
        if last[0] is not None and now - self._last_phone_ts < 0.04:
            d_az = abs(wrap_az_delta(corr_az - last[0]))
            if d_az < 0.2 and abs(corr_alt - last[1]) < 0.2:
                return
        self._last_phone_ts = now
        self._last_phone_corr = (corr_az, corr_alt)
        if self.chk_drive.isChecked():
            self.horizon_widget.set_aim(corr_az, corr_alt)
        self.lbl_aim.setText("aim   az %03.0f°   alt %02.0f°"
                             % (corr_az, corr_alt))

    def _on_phone_loc(self, lat, lon, _acc):
        if not self.chk_gps.isChecked():
            return
        try:
            lat = float(lat)
            lon = float(lon)
        except (TypeError, ValueError):
            return
        if not (-90.0 <= lat <= 90.0 and -180.0 <= lon <= 180.0):
            return
        now = time.time()
        prev = self._phone_loc
        if prev is not None:
            # set_location() recomputes sunset/moonset + live, so require a
            # real move (~50 m) or 15 s before re-anchoring the observer.
            moved = (abs(lat - prev[0]) >= 0.0005
                     or abs(lon - prev[1]) >= 0.0005)
            if not moved and now - prev[2] < 15.0:
                return
        if self._phone_base_loc is None:
            self._phone_base_loc = (self.ctrl.city, self.ctrl.lat,
                                    self.ctrl.lon, self.ctrl.tz)
        self._phone_loc = (lat, lon, now)
        self.ctrl.set_location("Phone GPS", lat, lon, self.ctrl.tz)

    def _on_phone_gps_toggled(self, checked):
        if checked:
            return
        base = self._phone_base_loc
        if base is None:
            return
        self._phone_base_loc = None
        self._phone_loc = None
        city, lat, lon, tz = base
        self.ctrl.set_location(city, lat, lon, tz)

    def _on_view_changed(self, index):
        self.view_stack.setCurrentIndex(index)

    def _on_slider(self, minutes):
        self.lbl_sim.setText("%02d:%02d" % (minutes // 60, minutes % 60))
        self.lbl_clock_sub.setText("scrubbing %s - press NOW to return to live"
                                   % self.ctrl.date.strftime("%d %b %Y"))
        self._debounce.start()

    def _apply_slider(self):
        self.ctrl.set_live_sim(self.live_slider.value() * 60)

    def _go_now(self):
        self.ctrl.set_live_now()

    def _on_tick(self):
        self.ctrl.tick_live()

    def update_view(self):
        c = self.ctrl
        if c.live is None:
            c.tick_live()
        d = c.live
        if d is None:
            return
        self.live_widget.set_data(d, c.tex)
        self.horizon_widget.set_data(d, c.tex)
        self.lbl_clock.setText(d["local"].strftime("%H:%M:%S"))
        minutes = d["local"].hour * 60 + d["local"].minute
        self.live_slider.blockSignals(True)
        self.live_slider.setValue(minutes)
        self.live_slider.blockSignals(False)
        if c.live_sim is None:
            self.lbl_clock_sub.setText("local time - live updates every 5 s")
            self.lbl_sim.setText("NOW")
        else:
            self.lbl_clock_sub.setText("scrubbing %s - press NOW to return to live"
                                       % c.date.strftime("%d %b %Y"))
            self.lbl_sim.setText(d["local"].strftime("%H:%M"))
        up = d["m_alt"] > 0.0
        values = [("%.1f°  az %.1f°" % (d["s_alt"], d["s_az"])),
                  ("%.1f°  az %.1f°" % (d["m_alt"], d["m_az"])),
                  ("UP" if up else "BELOW horizon"),
                  d["phase"],
                  fmt_age_h(d["age_h"]),
                  "%.1f %%" % (d["illum"] * 100),
                  fmt_time(d["moonrise"]),
                  fmt_time(d["moonset"])]
        for i, v in enumerate(values):
            self.tbl.item(i, 1).setText(v)
        word, kind = c.verdict()
        self.lbl_verdict.set_kind(word, kind)
        self.lbl_zone.setText("Odeh zone %s - %s" % (c.report["zone"], c.report["zone_label"])
                              if c.report else "")