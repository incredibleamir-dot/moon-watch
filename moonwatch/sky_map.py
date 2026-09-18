"""2D horizon sky map for the LIVE page.

A cylindrical (azimuth x altitude) panorama that can be panned across the full
360 degrees of azimuth and from the horizon up to the zenith (0-90 degrees of
altitude), like turning and tilting the observer's head.  The Sun, Moon and
bright planets are drawn at their live positions together with their altitude
paths, and the sky gradient follows the Sun so the background shifts
seamlessly from day to twilight to night.

The widget re-uses the astronomy layer (``sun_alt_az``, ``moon_alt_az``,
``planet_alt_az``, ``ecl2alt_az``) so it shows exactly the same positions the
rest of the app computes.
"""

import math

import numpy as np

from PySide6.QtCore import Qt, QPointF, QRectF
from PySide6.QtGui import (QPainter, QColor, QImage, QPixmap,
                           QRadialGradient, QPen, QPolygonF,
                           QLinearGradient)
from PySide6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout,
                               QPushButton, QLabel)

import astronomy

from .charts import F, tw, crescent_pixmap, crescent_rot

# --------------------------------------------------------------------------- sky
_DAY_TOP = (0.24, 0.47, 0.76)
_DAY_HORIZON = (0.80, 0.91, 0.98)
_TWILIGHT_TOP = (0.10, 0.13, 0.28)
_TWILIGHT_MID = (0.42, 0.26, 0.42)
_TWILIGHT_HORIZON = (0.94, 0.60, 0.38)
_NIGHT_TOP = (0.02, 0.03, 0.07)
_NIGHT_HORIZON = (0.07, 0.10, 0.18)

_CARDINALS = ("N", "NE", "E", "SE", "S", "SW", "W", "NW")

_PLANET_COLORS = {
    "Mercury": (0.78, 0.72, 0.64),
    "Venus": (0.98, 0.95, 0.83),
    "Mars": (0.92, 0.48, 0.38),
    "Jupiter": (0.86, 0.74, 0.52),
    "Saturn": (0.82, 0.76, 0.58),
    "Uranus": (0.55, 0.80, 0.80),
    "Neptune": (0.42, 0.56, 0.88),
}

_PATH_COLORS = {
    "Sun": (0.95, 0.70, 0.25),
    "Moon": (0.55, 0.80, 0.95),
    "Mercury": (0.62, 0.57, 0.50),
    "Venus": (0.75, 0.72, 0.62),
    "Mars": (0.70, 0.40, 0.34),
    "Jupiter": (0.66, 0.58, 0.42),
    "Saturn": (0.63, 0.58, 0.46),
    "Uranus": (0.45, 0.62, 0.62),
    "Neptune": (0.38, 0.48, 0.70),
}


def _smoothstep(a, b, x):
    if b <= a:
        return 0.0
    t = max(0.0, min(1.0, (x - a) / (b - a)))
    return t * t * (3.0 - 2.0 * t)


def _mix(c1, c2, t):
    return tuple(c1[i] + (c2[i] - c1[i]) * t for i in range(3))


def _sky_weights(sun_alt):
    """(day, twilight, night) weights for a sun altitude, smooth and normalised."""
    w_day = _smoothstep(1.0, 6.0, sun_alt)
    w_night = 1.0 - _smoothstep(-6.5, -1.5, sun_alt)
    w_twi = 1.0 - w_day - w_night
    total = max(1e-9, w_day + w_twi + w_night)
    return w_day / total, w_twi / total, w_night / total


def _blend3(c_night, c_twi, c_day, wn, wt, wd):
    return (c_night[0] * wn + c_twi[0] * wt + c_day[0] * wd,
            c_night[1] * wn + c_twi[1] * wt + c_day[1] * wd,
            c_night[2] * wn + c_twi[2] * wt + c_day[2] * wd)


BOTTOM_ALT = -5.0          # the view bottom never drops below -5°


def clamp_alt_center(value, vspan, alt_max, bottom_alt=BOTTOM_ALT):
    """Clamp the map's centre altitude so the visible band always lies within
    ``[bottom_alt, alt_max]``: the view bottom never drops below
    ``bottom_alt`` and the view top never rises above ``alt_max``."""
    lo = vspan / 2.0 + bottom_alt
    hi = alt_max - vspan / 2.0
    return max(lo, min(hi, float(value)))


class HorizonSkyWidget(QWidget):
    """Renders the sky map plus its pan / view controls."""

    SPAN = 130.0            # degrees of azimuth visible at once
    VSPAN = 32.0            # degrees of altitude visible at once
    ALT_MAX = 90.0          # zenith; highest altitude the top of the view can reach

    def __init__(self, parent=None):
        super().__init__(parent)
        self.live = None
        self.az_center = 90.0
        self.alt_center = clamp_alt_center(0.0, self.VSPAN, self.ALT_MAX)
        self._tex = None

        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(4)

        bar = QHBoxLayout()
        bar.setSpacing(6)
        self.lbl_view = QLabel()
        bar.addWidget(self.lbl_view)
        bar.addStretch(1)
        btn_style = ("QPushButton { background: #2c7fb8; color: #ffffff;"
                     " border: none; border-radius: 4px;"
                     " font-weight: 600; padding: 0px; }"
                     "QPushButton:hover { background: #1f5f8b; }"
                     "QPushButton:pressed { background: #15496c; }")
        for text, fn in (("\u2190", lambda: self.pan(-45)),
                         ("\u2192", lambda: self.pan(45))):
            b = QPushButton(text)
            b.setFixedSize(28, 24)
            b.setToolTip("Pan around the horizon (or drag the map)")
            b.setStyleSheet(btn_style)
            b.clicked.connect(fn)
            bar.addWidget(b)
        for text, fn in (("\u2191", lambda: self.vpan(15)),
                         ("\u2193", lambda: self.vpan(-15))):
            b = QPushButton(text)
            b.setFixedSize(28, 24)
            b.setToolTip("Pan the sky up/down (or drag the map)")
            b.setStyleSheet(btn_style)
            b.clicked.connect(fn)
            bar.addWidget(b)
        for name, az in (("N", 0), ("E", 90), ("S", 180), ("W", 270)):
            b = QPushButton(name)
            b.setFixedSize(30, 24)
            b.setToolTip("Look %s" % name)
            b.setStyleSheet(btn_style)
            b.clicked.connect(lambda _x, a=az: self.set_center(a))
            bar.addWidget(b)
        lay.addLayout(bar)

        self.canvas = _HorizonCanvas(self)
        lay.addWidget(self.canvas, 1)

        self._update_label()

    # ------------------------------------------------------------- data
    def set_tex(self, tex):
        self._tex = tex
        self.canvas.update()

    def set_data(self, live, tex=None):
        if tex is not None and tex is not self._tex:
            self.set_tex(tex)
        self.live = live
        self.canvas.live = live
        self.canvas.compute_paths(live)
        self.canvas.update()

    # ------------------------------------------------------------ control
    def set_center(self, az):
        self.az_center = az % 360.0
        self.canvas.az_center = self.az_center
        self._update_label()
        self.canvas.update()

    def pan(self, deg):
        self.set_center(self.az_center + deg)

    def set_alt_center(self, alt):
        self.alt_center = clamp_alt_center(alt, self.VSPAN, self.ALT_MAX)
        self.canvas.alt_center = self.alt_center
        self._update_label()
        self.canvas.update()

    def vpan(self, deg):
        self.set_alt_center(self.alt_center + deg)

    def set_aim(self, az, alt):
        """Point the view centre at an (azimuth, altitude) aim, e.g. the
        direction the phone's selected edge points in real space."""
        self.set_center(az)
        self.set_alt_center(alt)

    def _update_label(self):
        a = self.az_center % 360.0
        name = _CARDINALS[int(round(a / 45.0)) % 8]
        lo = self.alt_center - self.VSPAN / 2.0
        hi = self.alt_center + self.VSPAN / 2.0
        self.lbl_view.setText(
            "Looking %s  -  %03.0f\u00b0 az   \u00b7   alt %02.0f\u00b0-%02.0f\u00b0"
            % (name, a, lo, hi))


class _HorizonCanvas(QWidget):
    """The actual painted panorama; lives inside HorizonSkyWidget."""

    def __init__(self, owner):
        super().__init__(owner)
        self.owner = owner
        self.live = None
        self.az_center = 90.0
        self.alt_center = owner.alt_center
        self._paths = {}
        self._path_key = None
        self._sky_pm = None
        self._sky_key = None
        self._ecl_pts = None
        self._ecl_key = None
        self._drag_last = None
        self.setMinimumHeight(220)
        self.setMouseTracking(True)

    # ------------------------------------------------------------- geometry
    def _az_to_x(self, az):
        start = self.az_center - self.owner.SPAN / 2.0
        rel = (az - start) % 360.0
        if rel > self.owner.SPAN:
            return None
        return rel / self.owner.SPAN * self.width()

    def _alt_to_y(self, alt):
        h = self.height()
        vb = self.alt_center - self.owner.VSPAN / 2.0
        return h - (alt - vb) / self.owner.VSPAN * h

    # ------------------------------------------------------------- paths
    def compute_paths(self, live):
        if live is None:
            self._paths = {}
            self._path_key = None
            return
        jd = live["jd"]; lat = live["_lat"]; lon = live["_lon"]
        date = live["local"].date().toordinal()
        key = (date, round(lat, 4), round(lon, 4))
        if key == self._path_key:
            return
        self._path_key = key
        try:
            self._paths = self._build_paths(live["local"], live["now_utc"],
                                            lat, lon)
        except Exception:
            self._paths = {}

    def _build_paths(self, local, now_utc, lat, lon):
        tz_hours = (local - now_utc).total_seconds() / 3600.0
        import datetime as _dt
        local_midnight = _dt.datetime(local.year, local.month, local.day)
        utc_midnight = local_midnight - _dt.timedelta(hours=tz_hours)
        day_start = astronomy.jd_utc(utc_midnight)
        times = [day_start + k / 48.0 for k in range(49)]   # one local day, 30 min steps
        out = {}
        try:
            out["Sun"] = [astronomy.sun_alt_az(t, lat, lon) for t in times]
        except Exception:
            pass
        try:
            out["Moon"] = [astronomy.moon_alt_az(t, lat, lon) for t in times]
        except Exception:
            pass
        for name in ("Mercury", "Venus", "Mars", "Jupiter", "Saturn"):
            try:
                out[name] = [astronomy.planet_alt_az(t, name, lat, lon)
                             for t in times]
            except Exception:
                pass
        return out

    # ------------------------------------------------------------- events
    def mousePressEvent(self, e):
        if e.button() == Qt.LeftButton:
            self._drag_last = e.position()
            self.setCursor(Qt.ClosedHandCursor)

    def mouseMoveEvent(self, e):
        if self._drag_last is None:
            self.setCursor(Qt.OpenHandCursor)
            return
        pos = e.position()
        dx = pos.x() - self._drag_last.x()
        dy = pos.y() - self._drag_last.y()
        self._drag_last = pos
        if self.width() and self.height():
            # Single update: panning twice would repaint twice per move.
            daz = -dx / self.width() * self.owner.SPAN
            dalt = dy / self.height() * self.owner.VSPAN
            self.owner.set_aim(self.owner.az_center + daz,
                               self.owner.alt_center + dalt)

    def mouseReleaseEvent(self, e):
        self._drag_last = None
        self.unsetCursor()

    def wheelEvent(self, e):
        self.owner.vpan(e.angleDelta().y() / 120.0 * 15.0)

    # ------------------------------------------------------------- paint
    def paintEvent(self, _ev):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        w, h = self.width(), self.height()
        if self.live is None or w < 20 or h < 20:
            p.fillRect(self.rect(), QColor("#070b14"))
            p.setPen(QColor("#8fa3bd"))
            p.setFont(F(11))
            p.drawText(self.rect(), Qt.AlignCenter,
                       "Waiting for live data...")
            return

        sun_alt = self.live["s_alt"]
        self._draw_sky(p, w, h, sun_alt)
        self._draw_sun_glow(p, w, h, sun_alt, self.live["s_az"])
        self._draw_ecliptic(p)
        self._draw_paths(p)
        self._draw_ground(p, w, h)
        self._draw_grid(p)
        self._draw_bodies(p)
        self._draw_az_labels(p, w, h)
        p.end()

    def _draw_sky(self, p, w, h, sun_alt):
        # alt_center rounded coarsely: phone aiming at 25 Hz would otherwise
        # rebuild a full w*h numpy gradient on every sensor frame.
        key = (w, h, int(round(sun_alt * 2.0)), round(self.alt_center * 2.0))
        if self._sky_key != key or self._sky_pm is None:
            self._sky_pm = self._build_sky_pixmap(w, h, sun_alt)
            self._sky_key = key
        p.drawPixmap(0, 0, self._sky_pm)

    def _build_sky_pixmap(self, w, h, sun_alt):
        wd, wt, wn = _sky_weights(sun_alt)
        top = _blend3(_NIGHT_TOP, _TWILIGHT_TOP, _DAY_TOP, wn, wt, wd)
        mid = _blend3(_NIGHT_TOP, _TWILIGHT_MID, _DAY_TOP, wn, wt, wd)
        hor = _blend3(_NIGHT_HORIZON, _TWILIGHT_HORIZON, _DAY_HORIZON, wn, wt, wd)
        stops = [0.0, 0.42, 1.0]
        cols_arr = np.array([top, mid, hor], np.float32)
        vb = self.alt_center - self.owner.VSPAN / 2.0
        vt = self.alt_center + self.owner.VSPAN / 2.0
        alts = np.linspace(vt, vb, h)               # top row .. bottom row
        f = np.clip(1.0 - np.clip(alts, 0.0, 90.0) / 90.0, 0.0, 1.0)
        rows = np.column_stack(
            [np.interp(f, stops, cols_arr[:, k]) for k in range(3)]
        )[:, np.newaxis, :]
        arr = np.repeat(rows, w, axis=1)
        col = np.clip(arr * 255.0, 0, 255).astype(np.uint8)
        img = QImage(col.data, w, h, w * 3, QImage.Format_RGB888)
        return QPixmap.fromImage(img.copy())

    def _draw_sun_glow(self, p, w, h, sun_alt, sun_az):
        """Warm glow resting on the horizon toward the sun's azimuth."""
        wd, wt, wn = _sky_weights(sun_alt)
        if wt < 0.05 or sun_alt > 0.0:
            return
        gy = int(self._alt_to_y(0.0))
        x = self._az_to_x(sun_az)
        if x is None or gy < 0 or gy > h:
            return
        if sun_alt < -8.0:
            return
        warm = _mix((0.35, 0.18, 0.12), (0.95, 0.55, 0.30), wt)
        g = QRadialGradient(x, gy, w * 0.28)
        g.setColorAt(0.0, QColor(int(warm[0] * 255), int(warm[1] * 255),
                                 int(warm[2] * 255), int(120 * wt)))
        g.setColorAt(0.5, QColor(int(warm[0] * 255), int(warm[1] * 255),
                                 int(warm[2] * 255), int(55 * wt)))
        g.setColorAt(1.0, QColor(0, 0, 0, 0))
        p.setPen(Qt.NoPen)
        p.setBrush(g)
        p.drawRect(QRectF(0, gy - h * 0.4, w, h * 0.4))

    def _ecliptic_alt_az(self):
        # 240 ecl->horizon transforms per paint is the hottest loop when the
        # phone drives the map at sensor rate; cache per ~10 s JD bucket.
        live = self.live
        key = (round(float(live["jd"]), 4), round(float(live["_lat"]), 4),
               round(float(live["_lon"]), 4))
        if key == self._ecl_key and self._ecl_pts is not None:
            return self._ecl_pts
        lon_vals = np.linspace(0.0, 360.0, 240)
        out = []
        for el in lon_vals:
            try:
                alt, az = astronomy.ecl2alt_az(float(el), 0.0, live["jd"],
                                               live["_lat"], live["_lon"])
            except Exception:
                continue
            out.append((float(alt), float(az)))
        # keep the cache tiny (a handful of recent instants while scrubbing)
        self._ecl_pts = out
        self._ecl_key = key
        return out

    def _draw_ecliptic(self, p):
        pts = []
        for alt, az in self._ecliptic_alt_az():
            if alt > 0.0:
                x = self._az_to_x(az)
                if x is None:
                    continue
                pts.append(QPointF(x, self._alt_to_y(alt)))
            else:
                if len(pts) > 1:
                    self._stroke_poly(p, pts, _mix(_PATH_COLORS["Sun"],
                                                   (0.3, 0.6, 0.35), 0.5),
                                      1.2, 150)
                pts = []
        if len(pts) > 1:
            self._stroke_poly(p, pts, _mix(_PATH_COLORS["Sun"],
                                           (0.3, 0.6, 0.35), 0.5), 1.2, 150)

    def _draw_paths(self, p):
        for name, series in self._paths.items():
            col = _PATH_COLORS.get(name, (0.6, 0.7, 0.8))
            self._draw_one_path(p, series, col)

    def _draw_one_path(self, p, series, col):
        raw = []
        for alt, az in series:
            x = self._az_to_x(az)
            if x is None:
                continue
            raw.append((x, self._alt_to_y(alt)))
        # split at wrap gaps
        chunks = []
        cur = []
        for px, py in raw:
            if not cur:
                cur.append(QPointF(px, py))
                continue
            if abs(px - cur[-1].x()) > self.width() * 0.5:
                chunks.append(cur)
                cur = [QPointF(px, py)]
            else:
                cur.append(QPointF(px, py))
        chunks.append(cur)
        for ch in chunks:
            if len(ch) > 1:
                self._stroke_poly(p, ch, col, 1.0, 110)

    def _stroke_poly(self, p, pts, col, width, alpha):
        if len(pts) < 2:
            return
        pen = QPen(QColor(int(col[0] * 255), int(col[1] * 255),
                          int(col[2] * 255), alpha), width)
        pen.setStyle(Qt.SolidLine)
        p.setPen(pen)
        p.setBrush(Qt.NoBrush)
        poly = QPolygonF(pts)
        p.drawPolyline(poly)

    def _draw_ground(self, p, w, h):
        gy = int(self._alt_to_y(-1.0))
        if gy < 0 or gy >= h:
            return
        # One gradient fill replaces ~h per-row drawLine calls.
        grad = QLinearGradient(0, gy, 0, h)
        grad.setColorAt(0.0, QColor(16, 20, 30))
        grad.setColorAt(1.0, QColor(22, 27, 39))
        p.setPen(Qt.NoPen)
        p.setBrush(grad)
        p.drawRect(0, gy, w, h - gy)
        trees = self._tree_points(w, gy, seed=7)
        p.setPen(Qt.NoPen)
        p.setBrush(QColor(6, 8, 14))
        p.drawPolygon(QPolygonF(trees))
        p.setPen(QPen(QColor(40, 70, 110), 2))
        p.drawLine(0, gy, w, gy)

    def _tree_points(self, w, gy, seed):
        pts = [QPointF(0, gy)]
        x = 0.0
        i = 0
        while x < w:
            hgt = 8 + 10 * abs(math.sin(seed * 0.017 + i * 1.7)) \
                + 14 * abs(math.sin(seed * 0.031 + i * 0.61 + 2.0))
            pts.append(QPointF(x, gy - hgt))
            pts.append(QPointF(x + 5, gy - hgt * 0.4))
            x += 10 + 6 * abs(math.sin(seed * 0.043 + i * 0.91))
            i += 1
        pts.append(QPointF(w, gy))
        pts.append(QPointF(w, gy + 40))
        pts.append(QPointF(0, gy + 40))
        return pts

    def _draw_grid(self, p):
        w, h = self.width(), self.height()
        vb = max(0.0, self.alt_center - self.owner.VSPAN / 2.0)
        vt = self.alt_center + self.owner.VSPAN / 2.0
        first = int(math.ceil(vb / 5.0)) * 5
        last = int(math.floor(vt / 5.0)) * 5
        p.setFont(F(7))
        for alt in range(max(5, first), min(90, last) + 1, 5):
            y = self._alt_to_y(alt)
            pen = QPen(QColor(255, 255, 255, 26), 1)
            pen.setStyle(Qt.DashLine)
            p.setPen(pen)
            p.drawLine(0, int(y), w, int(y))
            p.setPen(QColor(255, 255, 255, 110))
            p.drawText(QRectF(3, int(y) - 9, 26, 14), Qt.AlignRight | Qt.AlignVCenter,
                       "%d\u00b0" % alt)

    def _draw_az_labels(self, p, w, h):
        gy = self._alt_to_y(-1.0)
        ly = gy + 4
        if ly < 4 or ly > h - 16:
            ly = max(4, h - 16)
        p.setFont(F(9, mono=True))
        for i, name in enumerate(_CARDINALS):
            az = i * 45.0
            x = self._az_to_x(az)
            if x is None:
                continue
            if name in ("N", "E", "S", "W"):
                col = QColor(120, 220, 220)
            else:
                col = QColor(160, 184, 206)
            p.setPen(col)
            wl = tw(F(9, mono=True), name)
            p.drawText(QRectF(x - wl / 2, ly, wl, 14), Qt.AlignCenter, name)

    def _draw_bodies(self, p):
        live = self.live
        w, h = self.width(), self.height()
        gy = int(self._alt_to_y(-1.0))
        items = [("Sun", live["s_alt"], live["s_az"]),
                 ("Moon", live["m_alt"], live["m_az"])]
        for name in ("Mercury", "Venus", "Mars", "Jupiter", "Saturn"):
            try:
                alt, az = astronomy.planet_alt_az(live["jd"], name,
                                                  live["_lat"], live["_lon"])
                items.append((name, alt, az))
            except Exception:
                continue
        for name, alt, az in items:
            x = self._az_to_x(az)
            if x is None:
                continue
            y = self._alt_to_y(alt)
            above = alt > 0.0
            self._draw_body(p, name, x, y, alt, above, gy)

    def _draw_body(self, p, name, x, y, alt, above, gy):
        if name == "Sun":
            g = QRadialGradient(x, y, 26)
            g.setColorAt(0.0, QColor(255, 220, 130, 255))
            g.setColorAt(0.6, QColor(255, 176, 64, 160))
            g.setColorAt(1.0, QColor(255, 176, 64, 0))
            p.setPen(Qt.NoPen)
            p.setBrush(g)
            p.drawEllipse(QPointF(x, y), 22, 22)
            p.setBrush(QColor("#f5b432"))
            p.drawEllipse(QPointF(x, y), 9, 9)
            self._label(p, "SUN", x, y, QColor(255, 216, 130), above, gy)
        elif name == "Moon":
            live = self.live
            rot = crescent_rot(live["m_az"], live["m_alt"],
                               live["s_az"], live["s_alt"])
            pm = crescent_pixmap(13, live["illum"], rot)
            p.drawPixmap(int(x) - 13, int(y) - 13, pm)
            p.setPen(QPen(QColor(150, 180, 205), 1))
            p.setBrush(Qt.NoBrush)
            p.drawEllipse(QPointF(x, y), 18, 18)
            self._label(p, "MOON", x, y, QColor(190, 220, 240), above, gy)
        else:
            col = _PLANET_COLORS.get(name, (0.7, 0.75, 0.8))
            r = 5 if name == "Venus" else 3.5
            if name == "Venus":
                g = QRadialGradient(x, y, 14)
                g.setColorAt(0.0, QColor(255, 250, 225, 230))
                g.setColorAt(1.0, QColor(255, 250, 225, 0))
                p.setPen(Qt.NoPen)
                p.setBrush(g)
                p.drawEllipse(QPointF(x, y), 14, 14)
            p.setPen(QPen(QColor(255, 255, 255, 210), 1.0))
            p.setBrush(QColor(int(col[0] * 255), int(col[1] * 255),
                              int(col[2] * 255)))
            if name == "Saturn":
                p.drawEllipse(QPointF(x, y), r + 2, r + 2)
                p.setBrush(Qt.NoBrush)
                p.setPen(QPen(QColor(230, 220, 180), 1.2))
                p.drawEllipse(QPointF(x, y), 8, 3.2)
            else:
                p.drawEllipse(QPointF(x, y), r, r)
            self._label(p, name.upper(), x, y,
                        QColor(230, 235, 240), above, gy)

    def _label(self, p, text, x, y, col, above, gy):
        p.setFont(F(8, bold=True))
        wl = tw(F(8, bold=True), text)
        lx = min(max(x - wl / 2, 4), self.width() - wl - 4)
        if above:
            ly = max(4, y - 24)
            p.setPen(col)
        else:
            ly = gy + 24
            p.setPen(QColor(255, 255, 255, 120))
        p.drawText(QRectF(lx, ly, wl, 14), Qt.AlignLeft | Qt.AlignTop, text)