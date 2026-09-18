"""Application controller: scientific state and background computations.

Re-homes the non-rendering logic of the original pygame app - evening
prediction, 14-evening forecast, live positions, NASA/records verification
threads and all of the shared formatting/reading helpers.
"""

import datetime
import multiprocessing
import os
import queue
import time
import threading

import numpy as np

from PySide6.QtCore import QObject, QTimer, Signal
from PySide6.QtGui import QImage, QIcon
from PySide6.QtCore import Qt

import astronomy
import analysis
from moonwatch import globalmap

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _run_check(q, kind, date, lat, lon, tz):
    """Worker sub-process: runs one verification check and ships the result.

    Lives at module level so ``multiprocessing`` can re-import it under
    Windows ``spawn``.  A separate process (rather than a thread) is used
    because the pure-Python astronomy loops hold the GIL and would starve
    the Qt event loop for seconds.
    """
    import verification as _v
    try:
        if kind == "ephemeris":
            res = _v.ephemeris_check(date, lat, lon, tz)
            state = "done" if res.get("ok") else "error"
            err = res.get("error")
        else:
            res = _v.observation_check(sample=600)
            state, err = "done", None
    except Exception as exc:
        res, state, err = None, "error", str(exc)
    q.put((state, res, err))


def _run_global_map(q, date):
    """Worker sub-process: compute the 1-degree visibility grid for ``date``."""
    try:
        def _progress(frac):
            q.put(("progress", frac))
        data = globalmap.compute(date, progress=_progress)
        q.put(("done", data))
    except Exception as exc:
        q.put(("error", str(exc)))


def _run_animation_gif(q, date, lat, lon, tz, city, crit, step_min,
                       grid_step, out_dir, want_sky, want_global, combined):
    """Worker sub-process: render the GIF animation for one evening.

    ``render_animations`` needs Qt for the painter work, so the worker
    creates its own offscreen-capable QApplication (``ensure_qapp`` handles
    that) and ships progress + results back through the queue.
    """
    from moonwatch import animation
    try:
        def _progress(frac):
            q.put(("progress", float(frac)))
        written = animation.render_animations(
            date, lat, lon, tz, city=city, crit=crit, step_min=step_min,
            grid_step=grid_step, split=combined, out_dir=out_dir,
            progress=_progress, want_sky=want_sky, want_global=want_global)
        q.put(("done", written))
    except Exception as exc:
        q.put(("error", str(exc)))


# --------------------------------------------------------------------------- formatting
def fmt_time(dt):
    return dt.strftime("%H:%M") if dt else "--:--"


def fmt_date(dt):
    return dt.strftime("%A, %d %B %Y")


def fmt_age_h(hours):
    """Moon age as days + hours, e.g. 43.2 h -> '1d 19h'."""
    if hours is None:
        return "-"
    days = int(hours) // 24
    hrs = int(hours) % 24
    if days and hrs:
        return "%dd %dh" % (days, hrs)
    if days:
        return "%dd" % days
    return "%.1fh" % hours


def coord_str(lat, lon, tz):
    return "%.2f\u00b0N, %.2f\u00b0E, UTC%+.1f" % (lat, lon, tz)


def app_logo():
    """The application logo (assets/app-logo.png) as a QIcon, if present."""
    img = os.path.join(ROOT, "assets", "app-logo.png")
    return QIcon(img) if os.path.exists(img) else QIcon()


# --------------------------------------------------------------------------- textures
GM_CACHE_MAX = 20   # dates in the in-memory grid cache

class TextureBank:
    """Best-effort loader of the bundled display textures as numpy arrays."""

    def __init__(self, assets_dir=None):
        base = assets_dir or os.path.join(ROOT, "assets")
        self._loaded = {}
        for name, fname, fmt in (
                ("sun", "sun.jpg", QImage.Format_RGB888),
                ("earth", "earth_line.png", QImage.Format_RGBA8888),
                ("earth_sat", "earth.jpg", QImage.Format_RGB888),
                ("moon", "moon.jpg", QImage.Format_RGB888)):
            try:
                img = QImage(os.path.join(base, fname))
                img = img.convertToFormat(fmt)
                w, h = img.width(), img.height()
                arr = self._as_array(img, w, h)
                if name in ("earth", "earth_sat"):
                    arr = self._scale(img, arr, 512)
                elif name == "moon":
                    arr = self._scale(img, arr, 192)
                elif name == "sun":
                    arr = self._scale(img, arr, 256)
                self._loaded[name] = arr
            except Exception:
                self._loaded[name] = None

    @staticmethod
    def _as_array(img, w, h):
        ch = img.depth() // 8
        buf = img.bits()
        if hasattr(buf, "setsize"):
            buf.setsize(img.sizeInBytes())
            return np.frombuffer(buf, np.uint8).reshape(h, w, ch).copy()
        return np.frombuffer(buf.tobytes(), np.uint8).reshape(h, w, ch).copy()

    @staticmethod
    def _scale(img, arr, max_side):
        h, w = arr.shape[:2]
        f = max_side / max(h, w)
        if f >= 1.0:
            return arr
        nh, nw = max(1, int(round(h * f))), max(1, int(round(w * f)))
        small = img.scaled(nw, nh, Qt.KeepAspectRatio, Qt.SmoothTransformation)
        # KeepAspectRatio may return a smaller box than requested; use the
        # actual pixmap size so the numpy reshape always matches.
        sw, sh = max(1, small.width()), max(1, small.height())
        return TextureBank._as_array(small, sw, sh)

    def get(self, name):
        return self._loaded.get(name)


# --------------------------------------------------------------------------- controller
class AppController(QObject):
    """Owns the prediction data; pages subscribe to its signals to repaint."""

    dataChanged = Signal()
    verifyChanged = Signal()
    analysisChanged = Signal()
    globalMapChanged = Signal()
    animationChanged = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        now = datetime.datetime.now()
        self.date = now.replace(hour=0, minute=0, second=0, microsecond=0)
        self.city = "Ludhiana, India"
        self.lat, self.lon, self.tz = 30.90, 75.85, 5.5
        self.analysis_x = "ArcL"

        self.report = None
        self.report_key = None
        self.series14 = []
        self.altseries = None
        self.live = None
        self.live_ts = 0.0
        self.live_sim = None
        self.analysis_results = {}
        self.global_map = None
        self.global_map_state = "idle"
        self.global_map_prog = 0.0
        self.global_map_error = None
        self._gm_q = None
        self._gm_proc = None
        self._gm_date = None
        self._gm_cache = {}         # date-ordinal -> grid dict (in-memory)

        self.animation = {
            "state": "idle", "prog": 0.0, "paths": [], "error": None,
        }
        self._anim_q = None
        self._anim_proc = None

        self.verify = {
            "hz_state": "idle", "hz": None, "hz_error": None,
            "obs_state": "idle", "obs": None, "obs_error": None,
        }
        self._analysis_lock = threading.Lock()
        self._hz_q = None
        self._obs_q = None
        self._hz_proc = None
        self._obs_proc = None
        self._hz_key = None
        self._obs_key = None
        self._poll = QTimer(self)
        self._poll.setInterval(100)
        self._poll.timeout.connect(self._drain)
        self._poll.start()

        self.tex = TextureBank()
        self.refresh()
        threading.Thread(target=self._warm_analysis, daemon=True).start()

    # ------------------------------------------------------------- prediction
    def refresh(self, force=False):
        key = (self.date.toordinal(), self.lat, self.lon, self.tz)
        if not force and key == self.report_key:
            return
        self.report_key = key
        self.report = astronomy.evening_report(self.date, self.lat, self.lon,
                                               self.tz)
        self.series14 = astronomy.sunset_altitudes_14days(
            self.date, self.lat, self.lon, self.tz, 14)
        self.altseries = (astronomy.altitude_series(
            self.report, self.lat, self.lon, self.tz, 12)
            if self.report else None)
        self.live = self.compute_live()
        self.live_ts = time.time()
        if self.verify["hz_state"] == "done":
            self.verify["hz_state"] = "stale"
        self.invalidate_analysis()
        if self._gm_date != self.date.toordinal():
            cached = self._gm_cache.get(self.date.toordinal())
            if cached is not None:
                self.global_map = cached
                self.global_map_state = "done"
                self.global_map_prog = 1.0
                self.global_map_error = None
                self._gm_date = self.date.toordinal()
            else:
                self.global_map = None
                self.global_map_state = "idle"
                self.global_map_prog = 0.0
                self.global_map_error = None
        self.dataChanged.emit()

    def set_location(self, city, lat, lon, tz):
        self.city = city
        self.lat, self.lon, self.tz = lat, lon, tz
        self.refresh(force=True)

    def set_date(self, when):
        self.date = when
        self.refresh(force=True)

    def step_day(self, delta):
        self.set_date(self.date + datetime.timedelta(days=delta))

    # --------------------------------------------------------------- analysis
    def invalidate_analysis(self):
        self.analysis_results = {}
        self.analysisChanged.emit()

    def analysis_result(self, kind):
        cached = self.analysis_results.get(kind)
        if cached is not None:
            return cached
        with self._analysis_lock:
            cached = self.analysis_results.get(kind)
            if cached is not None:
                return cached
            if kind == "cond":
                res = analysis.condition_analysis()
            elif kind == "equa":
                res = analysis.equation_analysis()
            else:
                res = analysis.threshold_analysis(self.analysis_x)
            self.analysis_results[kind] = res
            return res

    def _warm_analysis(self):
        """Precompute the analysis caches in the background so the first
        visit to each analysis / verify page never stalls the UI."""
        for kind in ("cond", "equa", "thres"):
            try:
                self.analysis_result(kind)
            except Exception:
                pass

    # -------------------------------------------------------------------- live
    def compute_live(self):
        """Positions of the Sun, Earth and Moon.

        Normally the wall-clock instant ("live"); when ``live_sim`` is set it
        is a fixed time-of-day (seconds after local midnight of ``self.date``)
        selected with the LIVE page slider.
        """
        if self.live_sim is None:
            now_utc = datetime.datetime.now(datetime.timezone.utc).replace(tzinfo=None)
        else:
            target_local = (datetime.datetime.combine(self.date, datetime.time())
                            + datetime.timedelta(seconds=self.live_sim))
            now_utc = target_local - datetime.timedelta(hours=self.tz)
        jd = astronomy.jd_utc(now_utc)
        lon_s, lat_s, sun_dist_au = astronomy.sun_ecliptic(jd)
        lon_m, lat_m, dist_m_er = astronomy.moon_geocentric(jd)
        elong = astronomy.elongation(lon_m, lat_m, lon_s, lat_s)
        s_alt, s_az = astronomy.sun_alt_az(jd, self.lat, self.lon)
        m_alt, m_az = astronomy.moon_alt_az(jd, self.lat, self.lon)
        age_h = astronomy.moon_age_hours(jd)
        illum = astronomy.illumination(elong, dist_m_er, sun_dist_au)
        d = (lon_m - lon_s) % 360.0
        if d > 180.0:
            d -= 360.0
        local = now_utc + datetime.timedelta(hours=self.tz)
        rise = set_ = None
        try:
            moon = astronomy.Moon(year=local.year, month=local.month,
                                  day=local.day, hour=0, minute=0, UT=self.tz,
                                  dst=0, longtitude=self.lon, latitude=self.lat)
            rise, set_ = moon.moonriseset()
        except Exception:
            pass
        return {
            "jd": jd, "now_utc": now_utc, "local": local,
            "lon_s": lon_s, "lat_s": lat_s, "lon_m": lon_m, "lat_m": lat_m,
            "elong": elong, "signed_e": d,
            "s_alt": s_alt, "s_az": s_az, "m_alt": m_alt, "m_az": m_az,
            "age_h": age_h, "illum": illum, "phase": self._phase_name(d),
            "moonrise": rise, "moonset": set_,
            "sun_dist_au": sun_dist_au, "dist_m_er": dist_m_er,
            "_lat": self.lat, "_lon": self.lon, "_city": self.city,
        }

    def tick_live(self):
        self.live = self.compute_live()
        self.live_ts = time.time()
        self.dataChanged.emit()

    def set_live_sim(self, seconds):
        """Freeze the LIVE view at a chosen time-of-day (0..24 h)."""
        self.live_sim = max(0.0, min(24 * 3600.0, float(seconds)))
        self.tick_live()

    def set_live_now(self):
        """Return the LIVE view to the wall-clock instant and auto-updates."""
        self.live_sim = None
        self.tick_live()

    @staticmethod
    def _phase_name(e):
        """Eight-phase name from the signed sun-moon elongation (-180..180)."""
        a = abs(e)
        if a < 10.0:
            return "New Moon"
        if a > 170.0:
            return "Full Moon"
        if abs(a - 90.0) < 8.0:
            return "First Quarter" if e > 0.0 else "Last Quarter"
        if e > 0.0:
            return "Waxing Crescent" if a < 90.0 else "Waxing Gibbous"
        return "Waning Crescent" if a < 90.0 else "Waning Gibbous"

    # ------------------------------------------------------------- verification
    def start_checks(self):
        if self.verify["obs_state"] in ("idle", "done"):
            self.verify["obs_state"] = "idle"
            self.verify["obs"] = None
            self.run_obs_check()
        if self.verify["hz_state"] == "idle":
            self.run_hz_check()

    def _current_key(self):
        return (self.date.toordinal(), self.lat, self.lon, self.tz)

    def _spawn(self, kind, attr_q, attr_proc, attr_key):
        """Start one verification worker in its own process."""
        setattr(self, attr_q, multiprocessing.Queue())
        setattr(self, attr_key, self._current_key())
        args = (getattr(self, attr_q), kind, self.date, self.lat,
                self.lon, self.tz)
        proc = multiprocessing.Process(target=_run_check, args=args,
                                       daemon=True)
        proc.start()
        setattr(self, attr_proc, proc)
        self.verifyChanged.emit()

    def run_hz_check(self):
        if self.verify["hz_state"] == "running":
            return
        self.verify["hz_state"] = "running"
        self.verify["hz_error"] = None
        self._spawn("ephemeris", "_hz_q", "_hz_proc", "_hz_key")

    def run_obs_check(self):
        if self.verify["obs_state"] != "idle":
            return
        self.verify["obs_state"] = "running"
        self.verify["obs_error"] = None
        self._spawn("obs", "_obs_q", "_obs_proc", "_obs_key")

    def _drain(self):
        """Poll the worker queues on the GUI thread; apply finished results."""
        changed = False
        if self._hz_q is not None:
            item = self._take(self._hz_q)
            if item is not None:
                state, res, err = item
                self._hz_q = None
                if self._hz_key == self._current_key():
                    self.verify.update(hz_state=state, hz=res, hz_error=err)
                else:
                    self.verify.update(hz_state="stale", hz=res,
                                       hz_error="date or location changed "
                                                "while the check ran")
                changed = True
        if self._obs_q is not None:
            item = self._take(self._obs_q)
            if item is not None:
                state, res, err = item
                self._obs_q = None
                if self._obs_key == self._current_key():
                    self.verify.update(obs_state=state, obs=res,
                                       obs_error=err)
                else:
                    self.verify.update(obs_state="idle", obs=None,
                                       obs_error=None)
                changed = True
        if changed:
            self.verifyChanged.emit()
        self._drain_global_map()
        self._drain_animation()

    @staticmethod
    def _take(q):
        try:
            return q.get_nowait()
        except queue.Empty:
            return None
        except (OSError, ValueError, EOFError):
            return ("error", None, "verification process unavailable")

    # ------------------------------------------------------------ global map
    def ensure_global_map(self, force=False):
        """Return the cached 1-degree visibility grid for ``self.date``, or
        (re)start the background worker that computes it."""
        if (not force and self.global_map is not None
                and self._gm_date == self.date.toordinal()):
            return self.global_map
        if (self.global_map_state == "running"
                and self._gm_date == self.date.toordinal()):
            return None
        if self._gm_proc is not None and self._gm_proc.is_alive():
            self._gm_proc.terminate()
        self.global_map = None
        self.global_map_error = None
        self.global_map_prog = 0.0
        self.global_map_state = "running"
        self._gm_q = q = multiprocessing.Queue()
        self._gm_date = self.date.toordinal()
        self._gm_proc = multiprocessing.Process(
            target=_run_global_map, args=(q, self.date), daemon=True)
        self._gm_proc.start()
        self.globalMapChanged.emit()
        return None

    def _drain_global_map(self):
        if self._gm_q is None:
            return
        # Drain every queued message so a burst of progress updates can not
        # delay the terminal done/error behind them.
        last_prog = None
        while self._gm_q is not None:
            try:
                item = self._gm_q.get_nowait()
            except queue.Empty:
                break
            except (OSError, ValueError, EOFError):
                self.global_map_state = "idle"
                self.globalMapChanged.emit()
                return
            kind, payload = item
            if kind == "progress":
                if self._gm_date == self.date.toordinal():
                    last_prog = float(payload)
            elif kind == "done":
                self._gm_q = None
                if self._gm_date == self.date.toordinal():
                    self.global_map = payload
                    self.global_map_state = "done"
                else:
                    self.global_map_state = "idle"
                try:
                    date_key = payload.get("date").toordinal()
                except AttributeError:
                    date_key = self._gm_date
                self._gm_cache[date_key] = payload
                while len(self._gm_cache) > GM_CACHE_MAX:
                    self._gm_cache.pop(next(iter(self._gm_cache)))
                self.globalMapChanged.emit()
            elif kind == "error":
                self._gm_q = None
                self.global_map_error = str(payload)
                self.global_map_state = "error"
                self.globalMapChanged.emit()
        if last_prog is not None and self._gm_q is not None:
            self.global_map_prog = last_prog
            self.globalMapChanged.emit()

    # -------------------------------------------------------------- animation
    def run_animation(self, date=None, city=None, crit="odeh",
                      step_min=5, grid_step=2, out_dir=None,
                      want_sky=True, want_global=True, combined=False):
        """Start rendering the GIF animation for one evening in a worker."""
        if self.animation["state"] == "running":
            return False
        if date is None:
            date = self.date
        if city is None:
            city = self.city
        if self._anim_proc is not None and self._anim_proc.is_alive():
            self._anim_proc.terminate()
        if not out_dir:
            out_dir = os.path.join(ROOT, "animations")
        self.animation.update(state="running", prog=0.0, paths=[],
                              error=None)
        self._anim_q = q = multiprocessing.Queue()
        self._anim_proc = multiprocessing.Process(
            target=_run_animation_gif,
            args=(q, date, self.lat, self.lon, self.tz, city, crit, step_min,
                  grid_step, out_dir, want_sky, want_global, combined),
            daemon=True)
        self._anim_proc.start()
        self.animationChanged.emit()
        return True

    def _drain_animation(self):
        if self._anim_q is None:
            return
        last_prog = None
        changed = False
        while self._anim_q is not None:
            try:
                item = self._anim_q.get_nowait()
            except queue.Empty:
                break
            except (OSError, ValueError, EOFError):
                self.animation.update(state="error",
                                      error="animation worker unavailable")
                self.animationChanged.emit()
                return
            kind, payload = item
            if kind == "progress":
                last_prog = float(payload)
                changed = True
            elif kind == "done":
                self._anim_q = None
                self.animation.update(state="done", prog=1.0,
                                      paths=list(payload))
                self.animationChanged.emit()
                return
            elif kind == "error":
                self._anim_q = None
                self.animation.update(state="error", error=str(payload))
                self.animationChanged.emit()
                return
        if changed:
            if last_prog is not None:
                self.animation["prog"] = last_prog
            self.animationChanged.emit()

    def shutdown(self):
        """Stop background work (call on application close)."""
        self._poll.stop()
        for proc in (self._hz_proc, self._obs_proc, self._gm_proc,
                     self._anim_proc):
            if proc is not None and proc.is_alive():
                proc.terminate()
                proc.join(timeout=2)

    # --------------------------------------------------------------- readings
    def verdict(self):
        """(word, kind) - kind is one of visible/borderline/not/no."""
        if self.report is None:
            return "NO SUNSET", "no"
        r = self.report
        if r["zone"] in ("A", "B"):
            return "CRESCENT VISIBLE", "visible"
        if r["zone"] == "C" or r["mabims"] or r["danjon"]:
            return "BORDERLINE", "borderline"
        return "NOT VISIBLE", "not"

    def plain_summary(self):
        """Short plain-language reading of the current evening, no jargon."""
        r = self.report
        if r is None:
            return ["The Sun does not set here this evening, so there is",
                    "nothing to check."]
        v, _ = self.verdict()
        word = {"CRESCENT VISIBLE": "it should be possible to see",
                "BORDERLINE": "it is borderline - binoculars may help",
                "NOT VISIBLE": "it is probably too faint to see"}[v]
        if r["lag"] is not None:
            lag = "%d minutes after sunset" % r["lag"]
        elif r["m_alt_sunset"] > 0:
            lag = "all evening (moon stays up)"
        else:
            lag = "already down at sunset"
        return [
            "The moon is %s old and %.1f%% lit - a thin crescent."
            % (fmt_age_h(r["age_sunset"]), r["illum"] * 100),
            "At sunset it stands %.1f degrees up, low in the west, and sets %s."
            % (r["m_alt_sunset"], lag),
            "Bottom line: %s." % word,
        ]

    def current_highlight(self, kind):
        """Where the selected evening sits on an analysis chart (or None)."""
        r = self.report
        if r is None:
            return None
        if kind == "cond":
            return {"x": r["arc_l_sunset"], "y": r["m_alt_sunset"],
                    "label": "THIS EVENING"}
        if kind == "equa":
            if r["lag"] is None:
                return None
            return {"x": r["lag"], "y": r["arc_l_sunset"],
                    "label": "THIS EVENING"}
        if kind == "thres":
            value = {"ArcL": r["arc_l_sunset"], "MAlt": r["m_alt_sunset"],
                     "ArcV": r["arc_v"], "W": r["w"], "LT": r["lag"],
                     "MA": r["age_sunset"]}.get(self.analysis_x)
            if value is None:
                return None
            return {"value": value, "label": "THIS EVENING"}
        return None