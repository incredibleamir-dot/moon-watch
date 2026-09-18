"""QPainter renderers for every scientific view.

Straight ports of the pygame drawing routines in the original app, reworked
for a clean light desktop look: western-evening sky diagram, 14-evening
altitude bar chart, condition / equation scatter plots, threshold box plot
and the live Sun-Earth-Moon canvas.  All rendering is vectorised with numpy
so textured globes and crescent discs stay fast.
"""

import math

import numpy as np

from PySide6.QtCore import Qt, QRect, QRectF, QPointF
from PySide6.QtGui import (QPainter, QColor, QImage, QPixmap, QLinearGradient,
                           QRadialGradient, QPen, QBrush,
                           QFontMetrics, QPolygonF)
from PySide6.QtWidgets import QWidget

import astronomy

from . import theme
from . import globalmap as gm
from .controller import fmt_time, fmt_age_h

_FONTS = {}


def F(size, bold=False, mono=False):
    key = (size, bold, mono)
    if key not in _FONTS:
        _FONTS[key] = theme.font(size, bold, mono)
    return _FONTS[key]


def tw(font, text):
    return QFontMetrics(font).horizontalAdvance(text)


def text_height(font):
    return QFontMetrics(font).height()


def _draw_text(p, x, y, text, color, font, align=Qt.AlignLeft | Qt.AlignTop):
    p.setFont(font)
    p.setPen(QColor(color))
    rect = QRectF(x, y, 1e6, 1e6)
    p.drawText(rect, align, text)


def _draw_centered(p, cx, cy, text, color, font):
    p.setFont(font)
    p.setPen(QColor(color))
    p.drawText(QRectF(cx - 500, cy, 1000, 60), Qt.AlignHCenter | Qt.AlignTop, text)


# --------------------------------------------------------------------------- pixmaps
def pix_from_bgra(arr):
    """Convert an (n, n, 4) BGRA image array to a QPixmap (copy)."""
    n = arr.shape[0]
    data = np.ascontiguousarray(arr).tobytes()
    img = QImage(data, n, n, n * 4, QImage.Format_ARGB32).copy()
    return QPixmap.fromImage(img)


def crescent_pixmap(r, k, rot_deg, lit=None, dark=None, ss=2):
    """A young-crescent disc of radius r, lit fraction k, orientation rot_deg."""
    lit = tuple(lit) if lit else (253, 254, 255)
    dark = tuple(dark) if dark else (185, 195, 207)
    rq = int(r * ss)
    n = 2 * rq + 1
    dyv = np.arange(-rq, rq + 1)
    yy, xx = np.meshgrid(dyv, dyv)
    d2 = xx * xx + yy * yy
    inside = d2 <= rq * rq
    bgra = np.zeros((n, n, 4), np.uint8)
    bgra[..., 3] = np.where(inside, 255, 0)
    if k >= 0.999:
        bgra[inside, 0], bgra[inside, 1], bgra[inside, 2] = lit[2], lit[1], lit[0]
    elif k <= 0.001:
        bgra[inside, 0], bgra[inside, 1], bgra[inside, 2] = dark[2], dark[1], dark[0]
    else:
        i = math.acos(max(-1.0, min(1.0, 2.0 * k - 1.0)))
        sini, cosi = math.sin(i), math.cos(i)
        rot = math.radians(rot_deg)
        ux, uy = math.cos(rot), math.sin(rot)
        u = xx * ux + yy * uy
        v = -xx * math.sin(rot) + yy * math.cos(rot)
        w = np.sqrt(np.maximum(0.0, rq * rq - (u * u + v * v)))
        litm = inside & ((u * sini + w * cosi) >= 0.0)
        on = inside & ~litm
        bgra[litm, 0], bgra[litm, 1], bgra[litm, 2] = lit[2], lit[1], lit[0]
        bgra[on, 0], bgra[on, 1], bgra[on, 2] = dark[2], dark[1], dark[0]
    pm = pix_from_bgra(bgra)
    if ss != 1:
        pm = pm.scaled(2 * r + 1, 2 * r + 1, Qt.KeepAspectRatio,
                       Qt.SmoothTransformation)
    return pm


def crescent_rot(m_az, m_alt, s_az, s_alt):
    """Rotation for ``crescent_pixmap`` that points the lit limb toward the
    Sun, using the same sky projection the evening map draws (azimuth to the
    right, altitude upward).  Returns degrees in (-180, 180]."""
    daz = (s_az - m_az + 180.0) % 360.0 - 180.0
    return math.degrees(math.atan2(m_alt - s_alt, daz))


def textured_globe_pixmap(tex, R, mode, frac=0.6, rot_deg=0.0):
    """Texture-mapped globe.

    mode "earth": show sub-polar point ``lam_sub`` at front (frac unused).
    mode "moon": shade with lit fraction around ``rot_deg``.
    Returns a QPixmap of diameter 2*R+1.
    """
    n = 2 * R + 1
    dyv = np.arange(-R, R + 1)
    yy, xx = np.meshgrid(dyv, dyv)
    d2 = xx * xx + yy * yy
    inside = d2 <= R * R
    r = np.sqrt(np.where(inside, d2, 0.0))
    bgra = np.zeros((n, n, 4), np.uint8)
    bgra[..., 3] = np.where(inside, 255, 0)
    H, W = tex.shape[0], tex.shape[1]
    is4 = tex.ndim == 3 and tex.shape[2] == 4
    rgb = tex[..., :3] if is4 else tex
    a = tex[..., 3] if is4 else np.full((H, W), 255, np.uint8)
    if mode == "earth":
        lam_sub = frac
        lat = 90.0 - np.degrees(np.arcsin(np.minimum(1.0, r / R)))
        th = np.degrees(np.arctan2(-yy, xx)) % 360.0
        lon = (lam_sub + 180.0 - th) % 360.0
        tx = (lon + 180.0) / 360.0
        ty = 0.5 - lat / 180.0
        xi = np.clip((tx * (W - 1)).astype(int), 0, W - 1)
        yi = np.clip((ty * (H - 1)).astype(int), 0, H - 1)
        col = rgb[yi, xi]
        av = a[yi, xi]
    else:
        w3 = np.sqrt(np.maximum(0.0, R * R - d2))
        lon = np.arctan2(np.where(inside, xx / R, 0.0),
                         np.where(inside, w3 / R, 1.0))
        lat = np.arcsin(np.clip(-yy / R, -1.0, 1.0))
        fx = (lon / math.tau + 0.5) % 1.0
        fy = 0.5 - lat / math.pi
        xi = np.clip((fx * (W - 1)).astype(int), 0, W - 1)
        yi = np.clip((fy * (H - 1)).astype(int), 0, H - 1)
        col = rgb[yi, xi]
        av = a[yi, xi]
        if mode != "sun":
            i = math.acos(max(-1.0, min(1.0, 2.0 * frac - 1.0)))
            si, ci = math.sin(i), math.cos(i)
            rot = math.radians(rot_deg)
            ux, uy = math.cos(rot), math.sin(rot)
            litm = (xx * ux + yy * uy) * si + w3 * ci >= 0.0
            col = col.copy()
            col[inside & ~litm] = (col[inside & ~litm] * 0.22).astype(np.uint8)
    bgra[inside, 0] = col[inside, 2]
    bgra[inside, 1] = col[inside, 1]
    bgra[inside, 2] = col[inside, 0]
    bgra[inside, 3] = av[inside]
    return pix_from_bgra(bgra)


# --------------------------------------------------------------------------- axes
def draw_axes(p, area, xr, yr, title, xlabel, ylabel, caption="",
              xticks=(), yticks=(), fmt_x=str, fmt_y=str):
    plot = QRect(area.left() + 62, area.top() + 42,
                 area.width() - 78, area.height() - 102)
    p.fillRect(plot, QColor(theme.CHART_PLOT))
    p.setPen(QColor(theme.BORDER))
    p.drawRect(plot)

    x0, x1 = xr
    y0, y1 = yr

    def mapx(v):
        return plot.left() + (v - x0) / (x1 - x0) * plot.width()

    def mapy(v):
        return plot.bottom() - (v - y0) / (y1 - y0) * plot.height()

    grid_pen = QPen(QColor(theme.CHART_GRID), 1)
    p.setPen(grid_pen)
    for t in xticks:
        px = int(mapx(t))
        p.drawLine(px, plot.top(), px, plot.bottom())
    for t in yticks:
        py = int(mapy(t))
        p.drawLine(plot.left(), py, plot.right(), py)

    tick_font = F(8, mono=True)
    p.setFont(tick_font)
    p.setPen(QColor(theme.TEXT_DIM))
    for t in xticks:
        px = int(mapx(t))
        w = tw(tick_font, fmt_x(t))
        p.drawText(QRectF(px - w / 2, plot.bottom() + 5, w, 16),
                   Qt.AlignCenter, fmt_x(t))
    for t in yticks:
        py = int(mapy(t))
        w = tw(tick_font, fmt_y(t))
        p.drawText(QRectF(plot.left() - w - 6, py - 8, w, 16),
                   Qt.AlignRight | Qt.AlignVCenter, fmt_y(t))

    p.setFont(F(9))
    p.setPen(QColor(theme.CHART_LABEL))
    _draw_centered(p, plot.center().x(), area.bottom() - 8, xlabel, theme.CHART_LABEL, F(9))
    _draw_text(p, area.left() + 6, area.top() + 10, ylabel, theme.CHART_LABEL, F(9))

    p.setFont(F(11, bold=True))
    p.setPen(QColor(theme.CHART_TITLE))
    _draw_centered(p, area.center().x(), area.top() + 2, title, theme.CHART_TITLE, F(11, bold=True))

    if caption:
        p.setFont(F(8))
        p.setPen(QColor(theme.CHART_CAPTION))
        _draw_text(p, plot.left(), plot.bottom() + 18, caption, theme.CHART_CAPTION, F(8))

    return plot, mapx, mapy


def draw_legend(p, plot, items):
    text = [it[2] for it in items]
    widths = [tw(F(8), t) for t in text]
    row_h = 15
    box_w = max(widths) + 30
    box_h = row_h * len(items) + 11
    box = QRect(plot.right() - box_w - 8, plot.bottom() - box_h - 8, box_w, box_h)
    p.setPen(QPen(QColor(theme.BORDER)))
    p.setBrush(QColor(255, 255, 255, 225))
    p.drawRoundedRect(box, 5, 5)
    y = box.top() + 5
    for (color, kind, label) in items:
        tx = box.left() + 9
        cy = y + row_h // 2
        p.setPen(Qt.NoPen)
        if kind == "square":
            p.setBrush(QColor(color))
            p.drawRect(tx, cy - 4, 8, 8)
        elif kind == "dot":
            p.setBrush(QColor(color))
            p.drawEllipse(QPointF(tx + 3, cy), 3.0, 3.0)
        else:
            p.setBrush(Qt.NoBrush)
            p.setPen(QPen(QColor(color), 2))
            p.drawLine(tx, cy, tx + 8, cy)
        _draw_text(p, tx + 13, y, label, theme.TEXT, F(8))
        y += row_h


def draw_highlight(p, plot, mapx, mapy, point, label="THIS EVENING"):
    hx, hy = point
    x, y = int(mapx(hx)), int(mapy(hy))
    if not (plot.left() - 6 <= x <= plot.right() + 6 and
            plot.top() - 6 <= y <= plot.bottom() + 6):
        return
    p.setPen(QPen(QColor(255, 255, 255), 2))
    p.setBrush(Qt.NoBrush)
    p.drawEllipse(QPointF(x, y), 9.0, 9.0)
    p.setPen(Qt.NoPen)
    p.setBrush(QColor(theme.C_TODAY))
    p.drawEllipse(QPointF(x, y), 4.5, 4.5)
    w = tw(F(9), label)
    bx = max(plot.left() + 2, min(plot.right() - w - 2, x - w // 2))
    by = max(plot.top() + 2, y - 22)
    _draw_text(p, bx, by, label, theme.C_TODAY, F(9))


# --------------------------------------------------------------------------- sky diagram
class SkyWidget(QWidget):
    """Western-evening sky: the setting Sun, the young crescent and its trail."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.report = None
        self.altseries = None
        self.setMinimumHeight(240)

    def set_data(self, report, altseries):
        self.report = report
        self.altseries = altseries
        self.update()

    def paintEvent(self, _ev):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        area = self.rect().adjusted(4, 4, -4, -4)
        if self.report is None:
            p.setFont(F(11, bold=True))
            p.setPen(QColor(theme.WARN))
            p.drawText(self.rect(), Qt.AlignCenter,
                       "No sunset on this date at this location.")
            return
        self._paint_sky(p, area)

    def _sky_geo(self, x, y, w, h, az, alt):
        px = x + (az - 180.0) / 180.0 * w
        py = y + (1.0 - max(0.0, min(1.0, alt / 40.0))) * h
        return px, py

    def _paint_sky(self, p, area):
        r = self.report
        horizon_y = area.bottom() - 6
        alt_top = area.top() + 4

        grad = QLinearGradient(0, area.top(), 0, area.bottom())
        grad.setColorAt(0.0, QColor("#cfe2f3"))
        grad.setColorAt(0.55, QColor("#dee8f4"))
        grad.setColorAt(1.0, QColor("#ffe3bd"))
        p.fillRect(area, QBrush(grad))

        ground = QRect(area.left(), horizon_y + 1, area.width(),
                       area.bottom() - horizon_y)
        p.fillRect(ground, QColor("#e6ddd0"))

        sun_az_x = self._sky_geo(area.left(), area.top(), area.width(),
                                 area.height(), r["s_az"], 0.0)[0]
        for rad, alpha in ((95, 26), (62, 42), (38, 62)):
            g = QRadialGradient(sun_az_x, horizon_y - rad * 0.3, rad)
            g.setColorAt(0.0, QColor(255, 176, 80, alpha))
            g.setColorAt(1.0, QColor(255, 176, 80, 0))
            p.setPen(Qt.NoPen)
            p.setBrush(g)
            p.drawEllipse(QPointF(sun_az_x, horizon_y - rad * 0.3), rad, rad)

        p.setPen(QPen(QColor("#8a7d67"), 2))
        p.drawLine(area.left(), horizon_y, area.right(), horizon_y)

        p.setFont(F(8, mono=True))
        p.setPen(QColor(theme.CHART_AXIS))
        for alt in (10, 20, 30):
            y = alt_top + (1.0 - alt / 40.0) * (horizon_y - alt_top)
            pen = QPen(QColor("#c5d4e3"), 1, Qt.DashLine)
            p.setPen(pen)
            p.drawLine(area.left(), int(y), area.right(), int(y))
            _draw_text(p, area.left() + 4, int(y) - 8, "%d°" % alt,
                       theme.CHART_AXIS, F(8, mono=True))

        for label, az in (("S", 180), ("SW", 225), ("W", 270),
                          ("NW", 315), ("N", 360)):
            x = self._sky_geo(area.left(), area.top(), area.width(),
                              area.height(), az, 0.0)[0]
            wdt = tw(F(8, mono=True), label)
            _draw_text(p, x - wdt / 2, horizon_y + 6, label,
                       theme.TEXT_DIM, F(8, mono=True))

        # moon altitude trail through the evening
        if self.altseries:
            ts, alts, _s_alts = self.altseries
            pts = [self._sky_geo(area.left(), area.top(), area.width(),
                                 area.height(), r["s_az"], alt)
                   for _t, alt in zip(ts, alts)]
            qpts = [QPointF(float(x), float(y)) for x, y in pts]
            if len(qpts) > 1:
                p.setPen(QPen(QColor("#7fa8cf"), 1.2))
                p.drawPolyline(QPolygonF(qpts))
                step = max(1, len(qpts) // 6)
                for i in range(0, len(qpts), step):
                    if horizon_y - qpts[i].y() > 12:
                        p.setBrush(QColor("#7fa8cf"))
                        p.setPen(Qt.NoPen)
                        p.drawEllipse(qpts[i], 2.0, 2.0)

        # the Sun, half sunk at the horizon
        sun_y = min(self._sky_geo(area.left(), area.top(), area.width(),
                                  area.height(), r["s_az"],
                                  max(-8.0, r["s_alt"]))[1], horizon_y)
        sun_r = 13
        g = QRadialGradient(sun_az_x, sun_y, 30)
        g.setColorAt(0.0, QColor(255, 209, 92, 255))
        g.setColorAt(0.6, QColor(255, 176, 64, 190))
        g.setColorAt(1.0, QColor(255, 176, 64, 0))
        p.setPen(Qt.NoPen)
        p.setBrush(g)
        p.drawEllipse(QPointF(sun_az_x, sun_y), 26, 26)
        p.setBrush(QColor("#f5b432"))
        p.drawEllipse(QPointF(sun_az_x, sun_y), sun_r, sun_r)
        wlab = tw(F(8, mono=True), "SUNSET")
        _draw_text(p, sun_az_x - wlab / 2, sun_y - 40, "SUNSET",
                   theme.C_SUN, F(8, mono=True))

        # the crescent
        moon_x, moon_y = self._sky_geo(area.left(), area.top(), area.width(),
                                       area.height(), r["m_az"],
                                       max(-8.0, r["m_alt"]))
        moon_y = max(moon_y, alt_top)
        p.setPen(QPen(QColor("#a3b6c9"), 1, Qt.DashLine))
        p.drawLine(int(moon_x), int(moon_y), int(moon_x), horizon_y + 2)
        p.setPen(QPen(QColor("#a3b6c9"), 1.5))
        p.drawLine(int(moon_x) - 4, horizon_y, int(moon_x) + 4, horizon_y)
        lit = r["illum"]
        if lit <= 0.03:
            p.setBrush(QColor(theme.C_MOON_LIT))
            p.setPen(Qt.NoPen)
            p.drawEllipse(QPointF(moon_x, moon_y), 6, 6)
        else:
            rot = crescent_rot(r["m_az"], r["m_alt"], r["s_az"], r["s_alt"])
            pm = crescent_pixmap(int(15), lit, rot)
            p.drawPixmap(int(moon_x) - 15, int(moon_y) - 15, pm)
        p.setBrush(Qt.NoBrush)
        p.setPen(QPen(QColor("#9fb6cc"), 1))
        p.drawEllipse(QPointF(moon_x, moon_y), 18, 18)
        wlab = tw(F(8, mono=True), "MOON")
        _draw_text(p, moon_x - wlab / 2, moon_y - 28, "MOON",
                   theme.C_TODAY, F(8, mono=True))

        info1 = "Sunset %s   |   Moonset %s" % (fmt_time(r["sunset"]),
                                                fmt_time(r["moonset"]))
        info2 = "Moon alt %s  |  Arc of light %s  |  Age %s" % (
            "%.1f°" % r["m_alt_sunset"], "%.1f°" % r["arc_l_sunset"],
            fmt_age_h(r["age_sunset"]))
        p.setFont(F(9, mono=True))
        p.setPen(QColor(theme.TEXT_MUT))
        for i, txt in enumerate((info1, info2)):
            _draw_text(p, area.left() + 10, area.top() + 6 + i * 18,
                       txt, theme.TEXT_MUT, F(9, mono=True))

        wlab = tw(F(10, bold=True), "EVENING SKY - LOOKING WEST")
        _draw_text(p, area.center().x() - wlab / 2, area.top() + 4,
                   "EVENING SKY - LOOKING WEST", theme.C_TODAY, F(10, bold=True))


# --------------------------------------------------------------------------- altitude chart
class AltitudeChartWidget(QWidget):
    """Moon altitude at sunset over the next 14 evenings (bar chart)."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.series14 = []
        self.today = None
        self.setMinimumHeight(190)

    def set_data(self, series14, today):
        self.series14 = series14 or []
        self.today = today
        self.update()

    def paintEvent(self, _ev):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        area = self.rect().adjusted(6, 4, -6, -4)
        title = "MOON ALTITUDE AT SUNSET - NEXT 14 EVENINGS"
        wlab = tw(F(10, bold=True), title)
        _draw_text(p, area.left(), area.top(), title, theme.C_TODAY, F(10, bold=True))

        plot = QRect(area.left() + 46, area.top() + 24,
                     area.width() - 56, area.height() - 56)
        p.fillRect(plot, QColor(theme.CHART_PLOT))
        p.setPen(QColor(theme.BORDER))
        p.drawRect(plot)

        def mapy(alt):
            return plot.bottom() - (max(-90, min(90, alt)) + 90) / 180.0 * plot.height()

        zero_y = int(mapy(0))
        thresh_y = int(mapy(astronomy.MABIMS_ALT_MIN))
        p.setPen(QPen(QColor("#b9c4d1"), 1))
        p.drawLine(plot.left(), zero_y, plot.right(), zero_y)
        p.setPen(QPen(QColor(theme.C_CRIT), 1.2, Qt.DashLine))
        p.drawLine(plot.left(), thresh_y, plot.right(), thresh_y)

        p.setFont(F(8, mono=True))
        p.setPen(QColor(theme.TEXT_DIM))
        for alt in (-90, -45, 0, 45, 90):
            y = int(mapy(alt))
            wl = tw(F(8, mono=True), "%d°" % alt)
            _draw_text(p, plot.left() - wl - 4, y - 7, "%d°" % alt,
                       theme.TEXT_DIM, F(8, mono=True))
        wlab = tw(F(8, mono=True), "MABIMS 3°")
        _draw_text(p, plot.right() - wlab - 4, thresh_y + 3, "MABIMS 3°",
                   theme.C_CRIT, F(8, mono=True))

        n = len(self.series14)
        if n:
            bw = plot.width() / n
            today_idx = None
            for i, (d, alt) in enumerate(self.series14):
                if alt is None:
                    continue
                if self.today is not None and d.date() == self.today.date():
                    today_idx = i
                h = plot.bottom() - int(mapy(alt))
                x = plot.left() + int(i * bw) + int(bw * 0.18)
                w = max(3, int(bw * 0.64))
                visible = alt >= astronomy.MABIMS_ALT_MIN
                col = QColor(theme.C_SEE if visible else theme.C_CRIT)
                if i == today_idx:
                    col = QColor(theme.C_TODAY)
                p.setPen(Qt.NoPen)
                p.setBrush(col)
                p.drawRect(x, plot.bottom() - h, w, h)
                p.setBrush(Qt.NoBrush)
                p.setPen(QPen(QColor(120, 130, 145, 90), 1))
                p.drawRect(x, plot.bottom() - h, w, h)
                p.setFont(F(8, mono=True))
                p.setPen(QColor(150, 160, 175))
                dlab = "%02d" % d.day
                dw = tw(F(8, mono=True), dlab)
                _draw_text(p, x + w // 2 - dw / 2, plot.bottom() + 4, dlab,
                           "#8ca0b5", F(8, mono=True))
                if i == today_idx:
                    wlab = tw(F(8, mono=True), "TODAY")
                    _draw_text(p, x + w // 2 - wlab / 2,
                               plot.bottom() - h - 15, "TODAY",
                               theme.C_TODAY, F(8, mono=True))

        note = ("Bars are the crescent altitude at sunset. "
                "Green = above the MABIMS 3° line, amber = below.")
        _draw_text(p, plot.left(), plot.bottom() + 20, note,
                   theme.CHART_CAPTION, F(8))


# Kept for backward compatibility; prefer astronomy.MABIMS_ALT_MIN.
theme_mabims_alt = astronomy.MABIMS_ALT_MIN


# --------------------------------------------------------------------------- scatter
class ScatterWidget(QWidget):
    """Condition (criteria vs database) and Equation (boundary curve) plots."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.res = None
        self.kind = "cond"
        self.highlight = None
        self.title_override = None

    def set_res(self, res, kind, highlight=None):
        self.res = res
        self.kind = kind
        self.highlight = highlight
        self.update()

    def set_title(self, title):
        self.title_override = title
        self.update()

    def paintEvent(self, _ev):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        area = self.rect().adjusted(4, 4, -4, -4)
        if self.res is None:
            p.setFont(F(11))
            p.setPen(QColor(theme.TEXT_DIM))
            p.drawText(self.rect(), Qt.AlignCenter, "Computation unavailable.")
            return
        res = self.res
        if self.kind == "cond":
            xr = (0.0, res["limitx"])
            yr = (0.0, res["limity"])
            title = self.title_override or (
                "CONDITION: %s >= %s  AND  %s >= %s" % (
                    res["xlabel"], "%.1f" % res["conditionx"],
                    res["ylabel"], "%.1f" % res["conditiony"]))
            caption = ("Each dot is one recorded evening. Green = seen, "
                       "red = not seen. Amber lines = MABIMS limits.")
        else:
            xr = (0.0, res["limita"])
            yr = (0.0, res["limitb"])
            title = self.title_override or (
                "EQUATION: visible when %s >= f(%s)" % (res["ylabel"], res["xlabel"]))
            caption = ("Each dot is one recorded evening. Green = seen, "
                       "red = not seen. Purple curve = visibility boundary.")
        plot, mapx, mapy = draw_axes(
            p, area, xr, yr, title,
            res["xlabel"] + "  (absolute)", res["ylabel"] + "  (absolute)",
            caption, [0, 5, 10, 15, 20, 25, 30], [0, 10, 20, 30])

        for px, py, vis, method in res["points"]:
            x = int(mapx(px))
            y = int(mapy(py))
            if not (plot.left() <= x <= plot.right() and
                    plot.top() <= y <= plot.bottom()):
                continue
            col = QColor(theme.C_SEE if vis == "V" else theme.C_UNSEE)
            if method == "NE":
                p.setPen(Qt.NoPen)
                p.setBrush(col)
                p.drawEllipse(QPointF(x, y), 1.8, 1.8)
            else:
                p.fillRect(x - 2, y - 2, 4, 4, col)

        if self.kind == "cond":
            lx = int(mapx(res["conditionx"]))
            ly = int(mapy(res["conditiony"]))
            p.setPen(QPen(QColor(theme.C_CRIT), 1.2))
            p.drawLine(lx, plot.top(), lx, plot.bottom())
            p.drawLine(plot.left(), ly, plot.right(), ly)
            _draw_text(p, lx + 4, plot.top() + 3, "%.1f°" % res["conditionx"],
                       theme.C_CRIT, F(9))
            wl = tw(F(9), "%.1f°" % res["conditiony"])
            _draw_text(p, plot.right() - wl - 4, ly + 3, "%.1f°" % res["conditiony"],
                       theme.C_CRIT, F(9))
            draw_legend(p, plot, [
                (theme.C_SEE, "dot", "Seen"),
                (theme.C_UNSEE, "dot", "Not seen"),
                (theme.C_CRIT, "line", "MABIMS limits"),
            ])
        else:
            prev = None
            pen = QPen(QColor(theme.C_BOUND), 2)
            p.setPen(pen)
            for cx, cy in res["curve"]:
                cp = QPointF(mapx(cx), mapy(cy))
                if prev is not None:
                    p.drawLine(prev, cp)
                prev = cp
            draw_legend(p, plot, [
                (theme.C_SEE, "dot", "Seen"),
                (theme.C_UNSEE, "dot", "Not seen"),
                (theme.C_BOUND, "line", "Boundary curve"),
            ])

        if self.highlight:
            draw_highlight(p, plot, mapx, mapy,
                           (self.highlight["x"], self.highlight["y"]),
                           self.highlight.get("label", "THIS EVENING"))


# --------------------------------------------------------------------------- box plot
class BoxPlotWidget(QWidget):
    """Threshold analysis: distribution of each minimum observed value."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.res = None
        self.highlight = None

    def set_res(self, res, highlight=None):
        self.res = res
        self.highlight = highlight
        self.update()

    def paintEvent(self, _ev):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        area = self.rect().adjusted(4, 4, -4, -4)
        if self.res is None:
            p.setFont(F(11))
            p.setPen(QColor(theme.TEXT_DIM))
            p.drawText(self.rect(), Qt.AlignCenter, "Computation unavailable.")
            return
        res = self.res
        series = res["series"]
        ymax = max([s["max"] for s in series.values()] + [1.0]) * 1.15
        caption = ("Box = middle half of records, dark line = median, "
                   "whiskers = smallest and largest. ")
        plot, mapx, mapy = draw_axes(
            p, area, (0, 2), (0.0, ymax),
            res.get("title", "DISTRIBUTION - VISIBLE EVENING CRESCENTS"),
            "Observing method", res["xlabel"] + "  (absolute)",
            caption, [0, 1, 2], [0, int(ymax)], fmt_y=lambda v: "%.0f" % v)

        groups = list(series.items())
        n = len(groups)
        bw = plot.width() / max(1, n)
        cols = [theme.C_SERIES1, theme.C_SERIES2]
        for i, (label, s) in enumerate(groups):
            cx = plot.left() + (i + 0.5) * bw
            w = min(60, int(bw * 0.4))
            col = QColor(cols[i % len(cols)])
            x0 = int(cx - w // 2)
            q1y = int(mapy(s["q1"]))
            q3y = int(mapy(s["q3"]))
            med_y = int(mapy(s["median"]))
            min_y = int(mapy(s["min"]))
            max_y = int(mapy(s["max"]))
            p.setPen(QPen(col, 2))
            p.drawLine(int(cx), min_y, int(cx), max_y)
            p.drawLine(int(cx) - 10, min_y, int(cx) + 10, min_y)
            p.drawLine(int(cx) - 10, max_y, int(cx) + 10, max_y)
            box = QRect(x0, min(q1y, q3y), w, abs(q3y - q1y))
            fill = QColor(col)
            fill.setAlpha(55)
            p.fillRect(box, fill)
            p.setPen(QPen(col, 2))
            p.drawRect(box)
            p.setPen(QPen(QColor(theme.CHART_TITLE), 2))
            p.drawLine(x0, med_y, x0 + w, med_y)
            p.setFont(F(9))
            lab = "%s   n = %d" % (label, s["count"])
            wl = tw(F(9), lab)
            _draw_text(p, cx - wl / 2, plot.bottom() + 6, lab, col, F(9))

        draw_legend(p, plot, [
            (cols[0], "square", "Naked eye"),
            (cols[1], "square", "Optical aid"),
            (theme.CHART_TITLE, "line", "Median"),
        ])
        if self.highlight:
            v = self.highlight["value"]
            y = int(mapy(max(0.0, min(ymax, v))))
            p.setPen(QPen(QColor(255, 255, 255), 1.6))
            p.drawLine(plot.left() + 6, y, plot.right() - 6, y)
            _draw_text(p, plot.left() + 10, y + 4, self.highlight["label"],
                       theme.C_TODAY, F(9))


# --------------------------------------------------------------------------- global map
class GlobalVisibilityWidget(QWidget):
    """Equirectangular world map of the evening crescent-visibility zones.

    One-degree grid computed in a background sub-process; the widget re-colours
    instantly when the criterion changes (the zone code is a pure function of
    the stored moon-altitude / arc-of-light / arc-of-vision / width arrays).
    """

    CRIT_NAMES = {"odeh": "Odeh (2006)", "mabims": "MABIMS 2023",
                  "danjon": "Danjon limit"}
    ZONE_COLORS = {
        gm.VISIBLE: (43, 158, 95, 175),
        gm.BORDERLINE: (192, 120, 23, 185),
        gm.NOT_VISIBLE: (214, 71, 71, 175),
        gm.NO_SUNSET: (0, 0, 0, 0),
    }
    ZONE_KEYS = [(gm.VISIBLE, "Visible"), (gm.BORDERLINE, "Borderline"),
                 (gm.NOT_VISIBLE, "Not visible"), (gm.NO_SUNSET, "No-sunset cycle")]

    PAD_TOP = 46          # header + legend strip above the map border
    PAD_SIDE = 8
    PAD_BOT = 8

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumSize(420, 240)
        self.data = None
        self.tex = None
        self.crit = "odeh"
        self.lat, self.lon = 30.90, 75.85
        self.city = ""
        self.extra = None            # (state, pct, error) from the controller
        self._img = None
        self._img_key = None

    def set_data(self, data):
        self.data = data
        self._img = None
        self._img_key = None
        self.update()

    def set_tex(self, tex):
        self.tex = tex
        self.update()

    def set_crit(self, crit):
        if crit != self.crit:
            self.crit = crit
            self._img = None
            self._img_key = None
            self.update()

    def set_observer(self, lat, lon, city):
        self.lat, self.lon, self.city = lat, lon, city
        self.update()

    def set_status(self, state, pct, error):
        self.extra = (state, pct, error)
        self.update()

    # -------------------------------------------------------------- paint
    def _map_rect(self, w, h):
        aspect = 2.0
        avh = h - self.PAD_TOP - self.PAD_BOT
        if w / avh > aspect:
            rw = int(avh * aspect)
            rh = int(avh)
        else:
            rw = w - 2 * self.PAD_SIDE
            rh = int(rw / aspect)
        return QRect((w - rw) // 2, self.PAD_TOP + (avh - rh) // 2, rw, rh)

    def _build_image(self, rw, rh):
        d = self.data
        if d is None:
            return None
        mh = d["mh"]; ark = d["ark"]
        av = d["av"]; w = d["w"]; ark_b = d["ark_b"]
        nolight = d["nolight"]
        lat = 90.0 - (np.arange(rh) + 0.5) / rh * 180.0
        li = np.clip(np.round(89.0 - lat).astype(int), 0, gm.NLAT - 1)
        lon = -180.0 + (np.arange(rw) + 0.5) / rw * 360.0
        lci = np.clip(np.round(lon + 179.0).astype(int), 0, gm.NLON - 1)
        mh2 = mh[li][:, lci]
        ark2 = ark[li][:, lci]
        av2 = av[li][:, lci]
        w2 = w[li][:, lci]
        arkb2 = ark_b[li][:, lci]
        nl2 = nolight[li][:, lci]
        codes = gm.classify(self.crit, mh2, ark2, av2, w2, arkb2, nl2)
        arr = np.zeros((rh, rw, 4), np.uint8)
        for code, rgba in self.ZONE_COLORS.items():
            if rgba[3]:
                arr[codes == code] = rgba
        img = QImage(arr.data, rw, rh, rw * 4, QImage.Format_RGBA8888)
        return img.copy()

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.SmoothPixmapTransform, True)
        p.setRenderHint(QPainter.Antialiasing, True)
        w, h = self.width(), self.height()
        p.fillRect(self.rect(), QColor(theme.CHART_PLOT))
        rect = self._map_rect(w, h)

        tex = self.tex.get("earth") if self.tex is not None else None
        if tex is not None:
            ih, iw = tex.shape[:2]
            stride = iw * (4 if tex.shape[2] == 4 else 3)
            fmt = (QImage.Format_RGBA8888 if tex.shape[2] == 4
                   else QImage.Format_RGB888)
            p.drawImage(rect, QImage(tex.data, iw, ih, stride, fmt))
        else:
            p.fillRect(rect, QColor("#b9cddd"))

        key = (self.crit, rect.width(), rect.height(),
               None if self.data is None else id(self.data))
        if self.data is not None and self._img_key != key:
            self._img = self._build_image(rect.width(), rect.height())
            self._img_key = key
        if self._img is not None:
            p.drawImage(rect, self._img)

        self._draw_graticule(p, rect)
        self._draw_observer(p, rect)
        p.setBrush(Qt.NoBrush)
        p.setPen(QPen(QColor(theme.BORDER), 1.0))
        p.drawRect(QRect(rect.x(), rect.y(), rect.width() - 1, rect.height() - 1))
        self._draw_labels(p, rect)
        p.end()

    def _draw_graticule(self, p, rect):
        pen = QPen(QColor(255, 255, 255, 90))
        pen.setWidthF(0.7)
        p.setPen(pen)
        for lon in range(-180, 180, 30):
            x = rect.x() + (lon + 180.0) / 360.0 * rect.width()
            p.drawLine(QPointF(x, rect.y()), QPointF(x, rect.bottom()))
        for lat in range(-60, 61, 30):
            y = rect.y() + (90.0 - lat) / 180.0 * rect.height()
            p.drawLine(QPointF(rect.x(), y), QPointF(rect.right(), y))
        pen = QPen(QColor(255, 255, 255, 150))
        pen.setWidthF(1.2)
        p.setPen(pen)
        ye = rect.y() + 0.5 * rect.height()
        p.drawLine(QPointF(rect.x(), ye), QPointF(rect.right(), ye))

    def _draw_observer(self, p, rect):
        px = rect.x() + (self.lon + 180.0) / 360.0 * rect.width()
        py = rect.y() + (90.0 - self.lat) / 180.0 * rect.height()
        p.setBrush(QColor(255, 255, 255, 200))
        p.setPen(QPen(QColor(theme.ACCENT_DARK), 1.4))
        p.drawEllipse(QPointF(px, py), 4.0, 4.0)
        if self.city:
            f = F(8, bold=True)
            name = self.city.split(",")[0]
            _draw_text(p, px + 7, py + 3, name, theme.ACCENT_DARK, f)

    def _draw_labels(self, p, rect):
        f = F(8, bold=True)
        state, pct, err = self.extra or ("idle", 0.0, None)
        date_txt = (self.data or {}).get("date")
        crit = self.CRIT_NAMES.get(self.crit, self.crit)
        head = ("Evening of %s   -   %s   (best time)" % (date_txt, crit)
                if date_txt else crit)
        top = rect.y() - self.PAD_TOP
        _draw_text(p, rect.x(), top + 8, head, theme.TEXT_DIM, f)
        st = ""
        if state == "running":
            st = "computing 1 degree grid ... %d%%" % int(pct * 100)
        elif state == "error":
            st = "error: %s" % (err or "unknown")
        if st:
            _draw_text(p, max(rect.x() + tw(f, head) + 24,
                              rect.right() - tw(f, st) - self.PAD_SIDE),
                       top + 12, st, theme.ERR if state == "error"
                       else theme.C_TODAY, f)
        # legend (above the map border, on white space)
        lf = F(9)
        lx = rect.x()
        ly = top + 23
        for code, label in self.ZONE_KEYS:
            rgba = self.ZONE_COLORS[code]
            p.setBrush(QColor(*rgba[:3]))
            p.setPen(QPen(QColor(theme.BORDER), 0.6))
            p.drawRect(QRectF(lx, ly, 11, 11))
            p.setPen(QColor(theme.TEXT_DIM))
            p.setFont(lf)
            p.drawText(QRectF(lx + 15, ly - 1, 200, 14), Qt.AlignLeft, label)
            lx += 15 + tw(lf, label) + 18
