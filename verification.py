"""verification.py - independent checks of astronomy.py against public data.

Two independent ways to check the calculations:

1. **Ephemeris check (online)** - compare our sunset / moonset / moon-at-sunset
   values against the NASA/JPL HORIZONS ephemeris, the authoritative source,
   which covers both the past and the future.

2. **Observation check (offline)** - compare our visibility verdicts against
   the recorded real-world crescent sightings in ``data/Final.csv``.

Both functions return plain data dicts so the pygame UI and the test-suite can
share them.
"""

import math
import re
import urllib.parse
import urllib.request
from datetime import datetime, timedelta

import astronomy

HORIZONS_URL = "https://ssd.jpl.nasa.gov/api/horizons.api"
SUNSET_ALT = -0.833          # geometric altitude of the Sun centre at sunset
SOLAR_DISK = 0.267           # apparent semi-diameter (deg) used for the Moon

# HORIZONS OBSERVER quantity codes we rely on
Q_AZEL = "4"                 # azimuth & elevation (topocentric, airless)
Q_ILLUM = "10"               # illumination (%)
Q_ELONG = "23"               # Sun-observer-target angle (elongation, deg)
Q_PHASE = "24"               # Sun-target-observer angle (phase, deg)
Q_FULL = ",".join([Q_AZEL, Q_ILLUM, Q_ELONG, Q_PHASE])

TOL = {
    "sunset": 8.0,        # minutes
    "moonset": 12.0,      # minutes
    "m_alt_sunset": 1.5,  # degrees
    "m_az_sunset": 4.0,   # degrees
    "arc_l_sunset": 2.0,  # degrees
    "illum": 1.5,         # percent points
}


def _fetch(command, ut_start, ut_stop, step, lat, lon, quantities):
    site = "%.3f,%.3f,0.0" % (lon, lat)
    params = {
        "format": "text", "COMMAND": command, "OBJ_DATA": "NO",
        "MAKE_EPHEM": "YES", "EPHEM_TYPE": "OBSERVER", "CENTER": "coord@399",
        "COORD_TYPE": "GEODETIC", "SITE_COORD": "'%s'" % site,
        "START_TIME": "'%s'" % ut_start, "STOP_TIME": "'%s'" % ut_stop,
        "STEP_SIZE": "'%s'" % step, "QUANTITIES": "'%s'" % quantities,
    }
    url = HORIZONS_URL + "?" + urllib.parse.urlencode(params)
    last = None
    for attempt in range(3):
        try:
            with urllib.request.urlopen(url, timeout=60) as resp:
                return resp.read().decode("ascii", "replace")
        except Exception as exc:
            last = exc
    raise last


def _parse_rows(txt):
    """Return [(ut_datetime, [float values...]), ...] from a HORIZONS table."""
    soe = txt.find("$$SOE")
    eoe = txt.find("$$EOE")
    if soe < 0 or eoe < 0 or "INPUT ERROR" in txt:
        raise ValueError("HORIZONS did not return a table")
    rows = []
    for line in txt[soe + 5:eoe].splitlines():
        m = re.match(r"\s*(\d{4})-(...)-(\d{2})\s+(\d{2}):(\d{2})(?::(\d{2}))?\s+(\S+)(.*)$", line)
        if not m:
            continue
        yy, mon, dd, hh, mm, ss, markers, rest = m.groups()
        vals = []
        for tok in rest.split():
            try:
                vals.append(float(tok))
            except ValueError:
                continue
        if not vals:
            continue
        month = {"Jan": 1, "Feb": 2, "Mar": 3, "Apr": 4, "May": 5, "Jun": 6,
                 "Jul": 7, "Aug": 8, "Sep": 9, "Oct": 10, "Nov": 11,
                 "Dec": 12}[mon]
        t = datetime(int(yy), month, int(dd), int(hh), int(mm),
                     int(ss or 0))
        rows.append((t, vals))
    if not rows:
        raise ValueError("HORIZONS table was empty")
    return rows


def _interp_set(times, values, target):
    """Time (utc datetime) when values crosses ``target`` while decreasing."""
    prev_t, prev_v = None, None
    for t, v in zip(times, values):
        if prev_t is not None:
            if prev_v > target >= v or prev_v < target <= v:
                f = (prev_v - target) / (prev_v - v)
                return prev_t + (t - prev_t) * f
        prev_t, prev_v = t, v
    return None


def _interp_value(times, values, t_target):
    for i in range(len(times) - 1):
        t0, t1 = times[i], times[i + 1]
        if t0 <= t_target <= t1:
            if t1 == t0:
                return values[i]
            f = (t_target - t0) / (t1 - t0)
            return values[i] + (values[i + 1] - values[i]) * f
    return None


def _sun_moon(lat, lon, ut0, ut1, step="5m"):
    sun = _parse_rows(_fetch("10", ut0, ut1, step, lat, lon, Q_AZEL))
    moon = _parse_rows(_fetch("301", ut0, ut1, step, lat, lon, Q_FULL))
    s_t = [t for t, _ in sun]
    s_el = [v[1] for _, v in sun if len(v) > 1]
    m_t = [t for t, _ in moon]
    m_az = [v[0] for _, v in moon if len(v) > 0]
    m_el = [v[1] for _, v in moon if len(v) > 1]
    m_illum = [v[2] for _, v in moon if len(v) > 2]
    m_elong = [v[3] for _, v in moon if len(v) > 3]
    m_phase = [v[4] if len(v) > 4 else None for _, v in moon]
    return (s_t, s_el), (m_t, m_az, m_el, m_illum, m_elong, m_phase)


def ephemeris_check(date, lat, lon, tz):
    """Compare astronomy.evening_report against NASA HORIZONS for ``date``.

    ``date`` can be in the past or the future.  Returns a dict of comparisons.
    """
    report = astronomy.evening_report(date, lat, lon, tz)
    if report is None:
        return {"ok": False, "error": "no sunset at this place on this date"}

    sunset_ut = report["sunset"] - timedelta(hours=tz)
    ut0 = sunset_ut - timedelta(minutes=90)
    ut1 = sunset_ut + timedelta(minutes=150)

    try:
        (s_t, s_el), (m_t, m_az, m_el, m_illum, m_elong, m_phase) = \
            _sun_moon(lat, lon, ut0.strftime("%Y-%m-%d %H:%M"),
                      ut1.strftime("%Y-%m-%d %H:%M"))
    except Exception as exc:  # network / parse failure
        return {"ok": False, "error": "HORIZONS request failed: %s" % exc}

    hz_sunset = _interp_set(s_t, s_el, SUNSET_ALT)
    hz_moonset = _interp_set(m_t, m_el, SUNSET_ALT)
    if hz_sunset is None:
        return {"ok": False, "error": "HORIZONS: no sunset found in window"}

    m_alt = _interp_value(m_t, m_el, hz_sunset)
    m_az = _interp_value(m_t, m_az, hz_sunset)
    m_illum = _interp_value(m_t, m_illum, hz_sunset)
    m_elong = _interp_value(m_t, m_elong, hz_sunset)

    local_sunset = hz_sunset + timedelta(hours=tz)

    def delta_minutes(a, b):
        return (a - b).total_seconds() / 60.0

    comp = {
        "sunset": (report["sunset"], local_sunset),
        "moonset": (report["moonset"], hz_moonset + timedelta(hours=tz)
                    if hz_moonset else None),
        "m_alt_sunset": (report["m_alt_sunset"], m_alt),
        "m_az_sunset": (report["m_az_sunset"], m_az),
        "arc_l_sunset": (report["arc_l_sunset"], m_elong),
        "illum": (report["illum"] * 100.0, m_illum),
    }
    verdicts = {}
    for key, (ours, hz) in comp.items():
        if ours is None or hz is None:
            verdicts[key] = None
        elif key in ("sunset", "moonset"):
            verdicts[key] = abs(delta_minutes(ours, hz)) <= TOL[key]
        else:
            verdicts[key] = abs(ours - hz) <= TOL[key]
    comp["verdicts"] = verdicts
    comp["ok"] = True
    return comp


def observation_check(sample=600):
    """Compare our MABIMS verdict against recorded real-world sightings.

    Uses a strided sample of ``data/Final.csv`` so it stays fast.  Returns a
    dict with agreement stats and per-parameter error summaries.
    """
    import analysis
    df = analysis.load_data().copy()
    n = len(df)
    idx = list(range(0, n, max(1, n // sample)))[:sample]
    rows = df.iloc[idx]

    tot = ag = 0
    err_arcl, err_malt, err_lag = [], [], []
    by_method = {}
    for _, r in rows.iterrows():
        try:
            rep = astronomy.evening_report(
                datetime(int(r["Year"]), int(r["Month"]), int(r["Day"])),
                float(r["Lat"]), float(r["Long"]), float(r["TZ"]))
        except (ValueError, TypeError):
            continue
        if rep is None:
            continue
        observed = r["V"] == "V"
        ours = rep["mabims"]
        tot += 1
        if ours == observed:
            ag += 1
        key = "Naked Eye" if r["M"] == "NE" else "Optical Aided"
        by_method.setdefault(key, [0, 0])
        by_method[key][0] += ours == observed
        by_method[key][1] += 1
        a = abs(float(r["ArcL"]))
        b = abs(float(r["MAlt"]))
        if a == a:
            err_arcl.append(abs(rep["arc_l_sunset"] - a))
        if b == b:
            err_malt.append(abs(rep["m_alt_sunset"] - b))
        if r["LT"] == r["LT"] and rep["lag"] is not None:
            err_lag.append(abs(rep["lag"] - float(r["LT"])))

    def stats(xs):
        xs = sorted(xs)
        m = len(xs)
        if not m:
            return {"n": 0, "mean": None, "max": None, "p90": None}
        p90 = xs[int(m * 0.9) - 1]
        return {"n": m, "mean": sum(xs) / m, "max": xs[-1], "p90": p90}

    return {
        "n": tot,
        "agreement_pct": 100.0 * ag / tot if tot else None,
        "by_method": {k: 100.0 * v[0] / v[1] for k, v in by_method.items()},
        "err_arc_l": stats(err_arcl),
        "err_m_alt": stats(err_malt),
        "err_lag_min": stats(err_lag),
    }
