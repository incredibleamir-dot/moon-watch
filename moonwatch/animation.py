"""GIF animation export: moon trajectory (west-looking sky) + global map.

Renders a timed animation of a chosen evening - from 1 hour before the
selected location's sunset to 1 hour after it - as a GIF.  Two views are
drawn side by side (or separately):

  * WEST-LOOKING SKY  - the same western-evening scene as the Sighting
    page, but with the Sun and Moon sweeping through their true positions
    at every simulated instant, plus the arc the Moon traces through the
    whole window.
  * GLOBAL VISIBILITY - an equirectangular world map, recoloured at every
    instant with the *same* visibility rules the app uses (Odeh / MABIMS /
    Danjon via ``globalmap.classify``), so the map and the sky never
    disagree about what an evening looks like.

The snapshot grids are computed with a coarse default resolution (2 deg) -
enough for a GIF, ~10 s of work - in a background sub-process (see
``compute_series`` and ``render_animations``) so the UI stays responsive.
Frame assembly uses Pillow (``PIL``); if Pillow is unavailable the user is
told instead of crashing.
"""

import datetime
import os

import numpy as np

from PySide6.QtCore import Qt, QRect, QRectF, QPointF
from PySide6.QtGui import (QImage, QPainter, QColor, QPen, QBrush,
                           QLinearGradient, QRadialGradient, QPolygonF)
from PySide6.QtWidgets import QApplication

import astronomy
from . import globalmap as gm
from . import theme
from .charts import F, tw, crescent_pixmap, crescent_rot, _draw_text
from .controller import fmt_age_h

SKY_W, SKY_H = 860, 440
GLOBAL_W, GLOBAL_H = 860, 480
DEFAULT_STEP_MIN = 5        # cadence of the animation
DEFAULT_GRID_STEP = 2       # degrees per cell of the snapshot grids
WINDOW_MIN = -60            # start: 1 h before sunset
WINDOW_MAX = 60             # end:   1 h after sunset
ZONE_COLORS = {
    gm.VISIBLE: (43, 158, 95, 175),
    gm.BORDERLINE: (192, 120, 23, 185),
    gm.NOT_VISIBLE: (214, 71, 71, 175),
    gm.NO_SUNSET: (0, 0, 0, 0),
}
ZONE_KEYS = [(gm.VISIBLE, "Visible"), (gm.BORDERLINE, "Borderline"),
             (gm.NOT_VISIBLE, "Not visible"), (gm.NO_SUNSET, "Daylight")]


# ---------------------------------------------------------------------------
# snapshot grids
# ---------------------------------------------------------------------------
def snapshot_grid(date, lat, lon, tz, offset_min, grid_step=DEFAULT_GRID_STEP):
    """World-grid visibility data evaluated at one simulated instant.

    The instant is ``sunset_local(date) + offset_min`` for the given observer
    (so the animation is anchored to *their* evening).  Returns a dict with
    arrays shaped exactly like ``globalmap.compute`` so the result feeds the
    same ``globalmap.classify`` rules; ``nolight`` marks cells where the Sun
    is still above civil twilight (drawn transparent, like the polar band).

    Returns None when there is no sunset that day at the observer.
    """
    day = datetime.datetime.combine(date, datetime.time(0, 0))
    sunset = astronomy.sunset_local(date, lat, lon, tz)
    if sunset is None:
        return None
    T = sunset + datetime.timedelta(minutes=offset_min)
    jd = astronomy.jd_utc(T - datetime.timedelta(hours=tz))

    lats = np.arange(89.0, -90.0, -float(grid_step))
    lons = np.arange(-179.0, 180.0, float(grid_step))
    nl, nlo = len(lats), len(lons)
    mh = np.full((nl, nlo), np.nan, np.float32)
    ark = np.full((nl, nlo), np.nan, np.float32)
    av = np.full((nl, nlo), np.nan, np.float32)
    w = np.full((nl, nlo), np.nan, np.float32)
    ark_b = np.full((nl, nlo), np.nan, np.float32)
    nolight = np.ones((nl, nlo), bool)

    lon_s, lat_s, sun_dist = astronomy.sun_ecliptic(jd)
    for i in range(nl):
        la = float(lats[i])
        for j in range(nlo):
            lo = float(lons[j])
            s_alt, _ = astronomy.sun_alt_az(jd, la, lo)
            if s_alt >= -6.0:
                continue        # not dark enough to matter; nolight stays True
            nolight[i, j] = False
            try:
                lon_m, lat_m, dist_m = astronomy.moon_topocentric(jd, la, lo)
                m_alt, _ = astronomy.moon_alt_az(jd, la, lo)
            except Exception:
                lon_m, lat_m, dist_m = astronomy.moon_geocentric(jd)
                m_alt, _ = astronomy.ecl2alt_az(lon_m, lat_m, jd, la, lo)
            a = astronomy.elongation(lon_m, lat_m, lon_s, lat_s)
            mh[i, j] = m_alt
            ark[i, j] = a
            ark_b[i, j] = a
            av[i, j] = m_alt - s_alt
            w[i, j] = astronomy.crescent_width(a, dist_m, m_alt)
    return {"date": date, "jd": jd, "offset_min": offset_min, "step": grid_step,
            "mh": mh, "ark": ark, "av": av, "w": w, "ark_b": ark_b,
            "nolight": nolight}


def compute_series(date, lat, lon, tz, step_min=DEFAULT_STEP_MIN,
                   grid_step=DEFAULT_GRID_STEP, progress=None):
    """Snapshot grids + sky instants for the whole -1h..+1h window.

    Runs the (slow) pure-Python grid loops; designed for a background
    sub-process.  Returns ``None`` if there is no sunset, else a dict with
    ``sunset`` and ``frames`` = list of ``(offset_min, local_datetime,
    sunset_dict)`` per step.
    """
    sunset = astronomy.sunset_local(date, lat, lon, tz)
    if sunset is None:
        return None
    offsets = list(range(WINDOW_MIN, WINDOW_MAX + 1, step_min))
    frames = []
    for k, off in enumerate(offsets):
        t = sunset + datetime.timedelta(minutes=off)
        jd = astronomy.jd_utc(t - datetime.timedelta(hours=tz))
        m_alt, m_az = astronomy.moon_alt_az(jd, lat, lon)
        s_alt, s_az = astronomy.sun_alt_az(jd, lat, lon)
        lon_m, lat_m, dist_m = astronomy.moon_topocentric(jd, lat, lon)
        lon_s, lat_s, sd = astronomy.sun_ecliptic(jd)
        arc = astronomy.elongation(lon_m, lat_m, lon_s, lat_s)
        illum = astronomy.illumination(arc, dist_m, sd)
        age = astronomy.moon_age_hours(jd)
        frames.append({
            "offset": off, "t": t, "sunset": sunset,
            "m_alt": m_alt, "m_az": m_az, "s_alt": s_alt, "s_az": s_az,
            "arc": arc, "illum": illum, "age": age,
            "grid": snapshot_grid(date, lat, lon, tz, off, grid_step),
        })
        if progress is not None:
            progress((k + 1) / len(offsets))
    return {"sunset": sunset, "frames": frames, "offsets": offsets}


# ---------------------------------------------------------------------------
# west-looking sky frames
# ---------------------------------------------------------------------------
def render_west_frame(frames, idx, lat, lon, tz, w=SKY_W, h=SKY_H):
    """One sky frame at frame ``idx``, with the Moon's full-window trail."""
    ensure_qapp()
    f = frames[idx]

    img = QImage(w, h, QImage.Format_RGB32)
    img.fill(QColor("#ffffff"))
    p = QPainter(img)
    p.setRenderHint(QPainter.Antialiasing)
    area = QRect(4, 4, w - 8, h - 8)
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

    def sky_geo(az, alt):
        px = area.left() + (az - 180.0) / 180.0 * area.width()
        py = area.top() + (1.0 - max(-1.0, min(1.0, alt / 40.0))) * (
            horizon_y - alt_top)
        return px, py

    p.setPen(QPen(QColor("#8a7d67"), 2))
    p.drawLine(area.left(), horizon_y, area.right(), horizon_y)
    for alt in (0, 10, 20, 30, 40):
        _, py = sky_geo(180.0, alt)
        p.setPen(QPen(QColor("#c5d4e3"), 1, Qt.DashLine))
        p.drawLine(area.left(), int(py), area.right(), int(py))
        if alt:
            _draw_text(p, area.left() + 4, int(py) - 8, "%d°" % alt,
                       theme.CHART_AXIS, F(8, mono=True))
    for label, az in (("S", 180), ("SW", 225), ("W", 270), ("NW", 315),
                      ("N", 360)):
        px, _ = sky_geo(az, 0.0)
        _draw_text(p, px - tw(F(8, mono=True), label) / 2, horizon_y + 6,
                   label, theme.TEXT_DIM, F(8, mono=True))

    trail = [QPointF(*sky_geo(fr["m_az"], max(-5.0, fr["m_alt"])))
             for fr in frames]
    if len(trail) > 1:
        pen = QPen(QColor(127, 168, 207, 150), 1.5)
        pen.setCapStyle(Qt.RoundCap)
        p.setPen(pen)
        p.drawPolyline(QPolygonF(trail))
        step = max(1, len(trail) // 8)
        for i in range(0, len(trail), step):
            yp = trail[i].y()
            if horizon_y - yp > 12:
                p.setBrush(QColor(127, 168, 207, 150))
                p.setPen(Qt.NoPen)
                p.drawEllipse(trail[i], 2.0, 2.0)

    sun_x, sun_y = sky_geo(f["s_az"], f["s_alt"])
    p.save()
    p.setClipRect(QRect(area.left(), area.top(), area.width(),
                        horizon_y - area.top() + 1))
    g = QRadialGradient(sun_x, sun_y, 30)
    g.setColorAt(0.0, QColor(255, 198, 90, 255))
    g.setColorAt(0.6, QColor(255, 176, 64, 190))
    g.setColorAt(1.0, QColor(255, 176, 64, 0))
    p.setPen(Qt.NoPen)
    p.setBrush(g)
    p.drawEllipse(QPointF(sun_x, sun_y), 26, 26)
    p.setBrush(QColor("#f5b432"))
    p.drawEllipse(QPointF(sun_x, sun_y), 13, 13)
    p.restore()
    if sun_y <= horizon_y + 2:
        _draw_text(p, sun_x - tw(F(8, mono=True), "SUN") / 2,
                   min(sun_y + 6, horizon_y - 2), "SUN", theme.C_SUN,
                   F(8, mono=True))

    mx, my = sky_geo(f["m_az"], max(-5.0, f["m_alt"]))
    my = max(my, alt_top)
    p.setPen(QPen(QColor("#a3b6c9"), 1, Qt.DashLine))
    p.drawLine(int(mx), int(my), int(mx), horizon_y + 2)
    p.setPen(QPen(QColor("#a3b6c9"), 1.5))
    p.drawLine(int(mx) - 4, horizon_y, int(mx) + 4, horizon_y)
    if f["illum"] <= 0.03:
        p.setBrush(QColor(theme.C_MOON_LIT))
        p.setPen(Qt.NoPen)
        p.drawEllipse(QPointF(mx, my), 6, 6)
    else:
        rot = crescent_rot(f["m_az"], f["m_alt"], f["s_az"], f["s_alt"])
        pm = crescent_pixmap(15, f["illum"], rot)
        p.drawPixmap(int(mx) - 15, int(my) - 15, pm)
    p.setBrush(Qt.NoBrush)
    p.setPen(QPen(QColor("#9fb6cc"), 1))
    p.drawEllipse(QPointF(mx, my), 18, 18)
    _draw_text(p, mx + 20, my - 8, f["t"].strftime("%H:%M"),
               theme.TEXT_MUT, F(8, mono=True))

    title = "MOON TRAJECTORY - LOOKING WEST   %s" % f["t"].strftime(
        "%a %d %b %Y   %H:%M")
    _draw_text(p, area.center().x() - tw(F(10, bold=True), title) / 2,
               area.top(), title, theme.C_TODAY, F(10, bold=True))
    _draw_text(p, area.left() + 10, area.top() + 22,
               "Sunset %s  |  Moon %.1f\u00b0  |  Arc of light %.1f\u00b0  |  Age %s"
               % (f["sunset"].strftime("%H:%M"),
                  f["m_alt"], f["arc"], fmt_age_h(f["age"])),
               theme.TEXT_MUT, F(9, mono=True))
    p.end()
    return _to_pil(img)


# ---------------------------------------------------------------------------
# global map frames
# ---------------------------------------------------------------------------
def render_global_frame(grid, lat, lon, city, crit, w=GLOBAL_W, h=GLOBAL_H,
                        tex=None):
    """One global visibility map frame from a snapshot grid."""
    ensure_qapp()
    img = QImage(w, h, QImage.Format_RGB32)
    img.fill(QColor(theme.CHART_PLOT))
    p = QPainter(img)
    p.setRenderHint(QPainter.SmoothPixmapTransform, True)
    p.setRenderHint(QPainter.Antialiasing, True)

    pad_top, pad_side, pad_bot = 46, 8, 8
    avh = h - pad_top - pad_bot
    rw = w - 2 * pad_side
    rh = int(rw / 2.0)
    rect = QRect((w - rw) // 2, pad_top + (avh - rh) // 2, rw, rh)

    if tex is not None:
        ih, iw = tex.shape[:2]
        stride = iw * (4 if tex.shape[2] == 4 else 3)
        fmt = (QImage.Format_RGBA8888 if tex.shape[2] == 4
               else QImage.Format_RGB888)
        p.drawImage(rect, QImage(tex.data, iw, ih, stride, fmt))
    else:
        p.fillRect(rect, QColor("#b9cddd"))

    if grid is not None:
        overlay = _overlay_image(grid, crit, rh, rw)
        p.drawImage(rect, overlay)

    _graticule(p, rect)
    _observer(p, rect, lat, lon, city)

    p.setBrush(Qt.NoBrush)
    p.setPen(QPen(QColor(theme.BORDER), 1.0))
    p.drawRect(QRect(rect.x(), rect.y(), rect.width() - 1, rect.height() - 1))
    head = "GLOBAL VISIBILITY   -   %s" % _crit_name(crit)
    _draw_text(p, rect.x(), rect.y() - pad_top + 8, head,
               theme.TEXT_DIM, F(8, bold=True))
    lf = F(9)
    lx = rect.x()
    ly = rect.y() - pad_top + 23
    for code, label in ZONE_KEYS:
        rgba = ZONE_COLORS[code]
        p.setBrush(QColor(*rgba[:3]))
        p.setPen(QPen(QColor(theme.BORDER), 0.6))
        p.drawRect(QRectF(lx, ly, 11, 11))
        p.setFont(lf)
        p.drawText(QRectF(lx + 15, ly - 1, 220, 14), Qt.AlignLeft, label)
        lx += 15 + tw(lf, label) + 18
    p.end()
    return _to_pil(img)


def _overlay_image(grid, crit, rh, rw):
    mh = grid["mh"]; ark = grid["ark"]; av = grid["av"]
    w = grid["w"]; ark_b = grid["ark_b"]; nl = grid["nolight"]
    nlat, nlon = mh.shape
    gstep = float(grid.get("step", DEFAULT_GRID_STEP))
    lat = 90.0 - (np.arange(rh) + 0.5) / rh * 180.0
    li = np.clip(np.round((89.0 - lat) / gstep).astype(int), 0, nlat - 1)
    lon = -180.0 + (np.arange(rw) + 0.5) / rw * 360.0
    lci = np.clip(np.round((lon + 179.0) / gstep).astype(int), 0, nlon - 1)
    codes = gm.classify(crit, mh[li][:, lci], ark[li][:, lci],
                        av[li][:, lci], w[li][:, lci], ark_b[li][:, lci],
                        nl[li][:, lci])
    arr = np.zeros((rh, rw, 4), np.uint8)
    for code, rgba in ZONE_COLORS.items():
        if rgba[3]:
            arr[codes == code] = rgba
    data = arr.tobytes()
    img = QImage(data, rw, rh, rw * 4, QImage.Format_RGBA8888).copy()
    return img


def _graticule(p, rect):
    pen = QPen(QColor(255, 255, 255, 90))
    pen.setWidthF(0.7)
    p.setPen(pen)
    for lon in range(-180, 180, 30):
        x = rect.x() + (lon + 180.0) / 360.0 * rect.width()
        p.drawLine(QPointF(x, rect.y()), QPointF(x, rect.bottom()))
    for la in range(-60, 61, 30):
        y = rect.y() + (90.0 - la) / 180.0 * rect.height()
        p.drawLine(QPointF(rect.x(), y), QPointF(rect.right(), y))
    pen = QPen(QColor(255, 255, 255, 150))
    pen.setWidthF(1.2)
    p.setPen(pen)
    ye = rect.y() + 0.5 * rect.height()
    p.drawLine(QPointF(rect.x(), ye), QPointF(rect.right(), ye))


def _observer(p, rect, lat, lon, city):
    px = rect.x() + (lon + 180.0) / 360.0 * rect.width()
    py = rect.y() + (90.0 - lat) / 180.0 * rect.height()
    p.setBrush(QColor(255, 255, 255, 200))
    p.setPen(QPen(QColor(theme.ACCENT_DARK), 1.4))
    p.drawEllipse(QPointF(px, py), 4.0, 4.0)
    if city:
        name = city.split(",")[0]
        _draw_text(p, px + 7, py + 3, name, theme.ACCENT_DARK,
                   F(8, bold=True))


def _crit_name(crit):
    return {"odeh": "Odeh (2006)", "mabims": "MABIMS 2023",
            "danjon": "Danjon limit"}.get(crit, crit)


def _to_pil(qimg):
    qimg = qimg.convertToFormat(QImage.Format_RGBA8888)
    arr = np.frombuffer(qimg.constBits().tobytes(), np.uint8).reshape(
        qimg.height(), qimg.width(), 4).copy()
    from PIL import Image
    return Image.fromarray(arr[:, :, :3], "RGB")


# ---------------------------------------------------------------------------
# assembly
# ---------------------------------------------------------------------------
def assemble_gif(frames, path, duration=120, loop=0):
    """Write ``frames`` (PIL images) as an animated GIF via Pillow."""
    from PIL import Image
    first, rest = frames[0], frames[1:]
    first.save(path, save_all=True, append_images=rest, duration=duration,
               loop=loop)


def render_animations(date, lat, lon, tz, city=None, crit="odeh",
                      step_min=DEFAULT_STEP_MIN, grid_step=DEFAULT_GRID_STEP,
                      split=False, out_dir=None, progress=None,
                      want_sky=True, want_global=True, tex=None, gifs=None):
    """Full pipeline: compute the series, draw every frame, write GIF(s).

    If ``gifs`` is supplied it receives the produced (title, path) tuples.
    ``progress`` gets floats 0..1 (computation is the slow part).
    Raises ValueError when the sun does not set on the chosen day, or
    FileNotFoundError / ImportError variants when Pillow / the output folder
    is missing.
    """
    series = compute_series(date, lat, lon, tz, step_min, grid_step,
                            progress=progress)
    if series is None:
        raise ValueError("No sunset on this date at this location - "
                         "animation not possible.")
    if progress:
        progress(0.5)
    frames = series["frames"]
    sky = [render_west_frame(frames, i, lat, lon, tz) for i in range(len(frames))]
    glob_ = [render_global_frame(fr["grid"], lat, lon, city, crit, tex=tex)
             for fr in frames]
    if progress:
        progress(0.85)
    base = datetime.date.strftime(date, "%Y-%m-%d")
    if not out_dir:
        out_dir = os.path.join(os.getcwd(), "animations")
    os.makedirs(out_dir, exist_ok=True)

    written = []
    if want_sky:
        path = os.path.join(out_dir, "moon-trajectory-%s.gif" % base)
        assemble_gif(sky, path)
        written.append(("West-looking sky", path))
    if want_global:
        path = os.path.join(out_dir, "global-visibility-%s.gif" % base)
        assemble_gif(glob_, path)
        written.append(("Global map", path))
    if want_sky and want_global and split:
        # combined = sky over global for one shared animation
        comb = [_stack(s, g) for s, g in zip(sky, glob_)]
        path = os.path.join(out_dir, "moon-animation-%s.gif" % base)
        assemble_gif(comb, path)
        written.append(("Combined", path))
    if gifs is not None:
        gifs.extend(written)
    if progress:
        progress(1.0)
    return written


def _stack(sky, glob_):
    from PIL import Image
    comp = Image.new("RGB", (max(sky.width, glob_.width),
                             sky.height + glob_.height), "white")
    comp.paste(sky, (0, 0))
    comp.paste(glob_, (0, sky.height))
    return comp


def ensure_qapp():
    """Make sure a QGuiApplication exists so offscreen painting works."""
    if QApplication.instance() is None:
        QApplication([])
    return QApplication.instance()


# ---------------------------------------------------------------------------
# 3D sighting sky MP4
# ---------------------------------------------------------------------------
def _live_at(date, lat, lon, tz, city, seconds):
    """Minimal live-dict for one instant, matching the Live widget's source
    fields, so the 3D sky can be driven without a full controller."""
    target_local = (datetime.datetime.combine(date, datetime.time(0, 0)) +
                    datetime.timedelta(seconds=seconds))
    jd = astronomy.jd_utc(target_local - datetime.timedelta(hours=tz))
    s_alt, s_az = astronomy.sun_alt_az(jd, lat, lon)
    m_alt, m_az = astronomy.moon_alt_az(jd, lat, lon)
    return {"jd": jd, "s_alt": s_alt, "s_az": s_az,
            "m_alt": m_alt, "m_az": m_az,
            "_lat": lat, "_lon": lon, "_city": city, "local": target_local}