"""astronomy.py - lunar crescent visibility calculations for the Islamic calendar.

Computes sunset / moonset times and lunar phase, then applies the three standard
visibility criteria (MABIMS 2023, Danjon limit, Odeh 2006 zones) to judge
whether the new crescent (hilal) can be seen on a given evening from a given
location:

  * sunset / moonset times and the moon's lag time
  * moon age, altitude at sunset, arc of light (elongation), arc of vision,
    relative azimuth and crescent width
  * visibility verdicts for the MABIMS 2023, Danjon and Odeh (2006) criteria

The orbital model is Paul Schlyter's ("How to compute planetary positions")
as vendored in this repo's ``vendor/solarsystem`` package, so this module needs
no extra dependency.

Key functions:
  * evening_report()                      - full evening analysis
  * sunset_local() / moonset_local()      - solar / lunar set times
  * moon_age_hours() / illumination()     - lunar phase
  * odeh_verdict() / mabims_verdict() / danjon_verdict() - visibility criteria

References:
  [1] Meeus, J. (2009). Astronomical Algorithms, 2nd ed.
  [2] Odeh, M.S. (2006). New criterion for lunar crescent visibility.
  [3] Schlyter, P. (2009). How to compute planetary positions.
  [4] Yallop, B.D. (1997). A method for predicting the first visibility of the
      lunar crescent.
"""

import functools
import math
import os
import sys
import datetime as _dt
from datetime import datetime, timedelta

LIB_DIR = os.path.dirname(os.path.abspath(__file__))
if LIB_DIR not in sys.path:
    sys.path.insert(0, LIB_DIR)
VENDOR = os.path.join(LIB_DIR, "vendor")
if os.path.isdir(VENDOR) and VENDOR not in sys.path:
    sys.path.insert(0, VENDOR)

from solarsystem import Moon          # noqa: E402
from solarsystem.functions import normalize  # noqa: E402

# Altitude of the disk centre at rise/set: the upper limb touches the horizon
# at -0.833 deg = 34' refraction + 16' solar / lunar angular radius
# (Meeus, "Astronomical Algorithms", 2nd ed., Ch. 16).
SUN_ALT_SUNSET = -0.833
MOON_ALT_SET = -0.833

# 1 AU expressed in Earth radii (149.6e6 km / 6371 km ~ 23480).  Converts the
# moon's geocentric distance from Earth radii to AU for the illumination law.
AU_IN_EARTH_RADII = 23455.0

# Ratio of the Moon's mean radius to the Earth's equatorial radius
# (Meeus, Ch. 48), used for the topocentric semi-diameter.
PARALLAX_COEFF = 0.27245

# Odeh (2006) visibility-threshold polynomial:  arcv' = a0 + a1*w + a2*w^2 + a3*w^3.
ODEH_A0, ODEH_A1, ODEH_A2, ODEH_A3 = 7.1651, -6.3226, 0.7319, -0.1018
# Odeh (2006) zone thresholds on v = arcv - arcv' (degrees).
ODEH_ZONE_A_MIN, ODEH_ZONE_B_MIN, ODEH_ZONE_C_MIN = 5.65, 2.0, -0.96

# MABIMS (2023) and Danjon criteria thresholds.
MABIMS_ARC_L_MIN = 6.4
MABIMS_ALT_MIN = 3.0
DANJON_ARC_L_MIN = 7.0

# ---------------------------------------------------------------------------
# Julian date helpers
# ---------------------------------------------------------------------------

def jd_utc(dt):
    """Julian date from a naive UTC datetime."""
    y, m, d = dt.year, dt.month, dt.day
    hh = dt.hour + dt.minute / 60.0 + dt.second / 3600.0
    a = (14 - m) // 12
    yy = y + 4800 - a
    mm = m + 12 * a - 3
    jdn = (d + (153 * mm + 2) // 5 + 365 * yy + yy // 4
           - yy // 100 + yy // 400 - 32045)
    return jdn + hh / 24.0 - 0.5


def dt_utc_from_jd(jd):
    """Naive UTC datetime from a Julian date."""
    z = jd + 0.5
    f = math.modf(z)[0]
    z = int(z - f)
    if z < 2299161:
        a = z
    else:
        alpha = int((z - 1867216.25) / 36524.25)
        a = z + 1 + alpha - alpha // 4
    b = a + 1524
    c = int((b - 122.1) / 365.25)
    d = int(365.25 * c)
    e = int((b - d) / 30.6001)
    day = b - d - int(30.6001 * e) + f
    month = e - 1 if e < 14 else e - 13
    year = c - 4716 if month > 2 else c - 4715
    day_int = int(day)
    frac = day - day_int
    secs = int(round(frac * 86400.0))
    hh, rem = divmod(secs, 3600)
    mm, ss = divmod(rem, 60)
    if ss >= 60:
        ss = 0
        mm += 1
    if mm >= 60:
        mm = 0
        hh += 1
    if hh >= 24:
        hh = 0
        day_int += 1
    return datetime(year, month, day_int, hh, mm, ss)


def obliquity(jd):
    d = jd - 2451543.5
    return 23.4393 - 3.563e-7 * d


# ---------------------------------------------------------------------------
# Sun
# ---------------------------------------------------------------------------

def sun_ecliptic(jd):
    """Geocentric ecliptic (longitude, latitude, distance AU) of the Sun."""
    d = jd - 2451543.5
    w = 282.9404 + 4.70935e-5 * d
    e = 0.016709 - 1.151e-9 * d
    M = math.radians(normalize(356.047 + 0.9856002585 * d))
    E = M + e * math.sin(M) * (1 + e * math.cos(M))
    xv = math.cos(E) - e
    yv = math.sqrt(1 - e * e) * math.sin(E)
    v = math.atan2(yv, xv)
    r = math.hypot(xv, yv)
    lon = normalize(math.degrees(v) + w)
    return lon, 0.0, r


sun_ecliptic = functools.lru_cache(maxsize=8192)(sun_ecliptic)


# ---------------------------------------------------------------------------
# Moon (via the vendored solarsystem library)
# ---------------------------------------------------------------------------

def _moon_instant(jd, lat, lon, topographic):
    dt = dt_utc_from_jd(jd)
    minute = dt.minute + dt.second / 60.0
    m = Moon(year=dt.year, month=dt.month, day=dt.day,
             hour=dt.hour, minute=minute, UT=0, dst=0,
             longtitude=lon, latitude=lat, topographic=topographic)
    return m.position()          # (ecliptic lon, lat, distance in Earth radii)


# Exact-JD memoisation: an evening report asks for the same instant several
# times (alt/az plus the direct position), so cache rather than recompute.
_moon_instant = functools.lru_cache(maxsize=8192)(_moon_instant)


def moon_geocentric(jd):
    return _moon_instant(jd, 0.0, 0.0, False)


def moon_topocentric(jd, lat, lon):
    return _moon_instant(jd, lat, lon, True)


# ---------------------------------------------------------------------------
# Coordinate transforms
# ---------------------------------------------------------------------------

def ecl2alt_az(ecl_lon, ecl_lat, jd, lat, lon):
    """Ecliptic (lon, lat) -> (alt, az) for observer at lat/lon.

    Airless altitude.  Azimuth 0 = North, 90 = East, 180 = South, 270 = West.
    """
    ob = math.radians(obliquity(jd))
    lon_r, lat_r = math.radians(ecl_lon), math.radians(ecl_lat)
    xe = math.cos(lon_r) * math.cos(lat_r)
    ye = math.sin(lon_r) * math.cos(lat_r)
    ze = math.sin(lat_r)
    xq = xe
    yq = ye * math.cos(ob) - ze * math.sin(ob)
    zq = ye * math.sin(ob) + ze * math.cos(ob)
    ra = math.degrees(math.atan2(yq, xq)) % 360.0
    dec = math.degrees(math.atan2(zq, math.hypot(xq, yq)))

    d = jd - 2451545.0
    gmst = normalize(280.46061837 + 360.98564736629 * d)
    lst = (gmst + lon) % 360.0
    ha = (lst - ra) % 360.0
    if ha > 180.0:
        ha -= 360.0
    ha_r, dec_r, lat_r = math.radians(ha), math.radians(dec), math.radians(lat)
    sin_alt = (math.sin(lat_r) * math.sin(dec_r)
               + math.cos(lat_r) * math.cos(dec_r) * math.cos(ha_r))
    alt = math.degrees(math.asin(max(-1.0, min(1.0, sin_alt))))
    az = (math.degrees(math.atan2(
        math.sin(ha_r),
        math.cos(ha_r) * math.sin(lat_r)
        - math.tan(dec_r) * math.cos(lat_r))) + 180.0) % 360.0
    return alt, az


def sun_alt_az(jd, lat, lon):
    lon_s, lat_s, _ = sun_ecliptic(jd)
    return ecl2alt_az(lon_s, lat_s, jd, lat, lon)


def moon_alt_az(jd, lat, lon):
    lon_m, lat_m, _ = moon_topocentric(jd, lat, lon)
    return ecl2alt_az(lon_m, lat_m, jd, lat, lon)


def ecl2radec(ecl_lon, ecl_lat, jd):
    """Ecliptic (lon, lat) -> equatorial (RA, Dec)."""
    ob = math.radians(obliquity(jd))
    lon_r, lat_r = math.radians(ecl_lon), math.radians(ecl_lat)
    xe = math.cos(lon_r) * math.cos(lat_r)
    ye = math.sin(lon_r) * math.cos(lat_r)
    ze = math.sin(lat_r)
    xq = xe
    yq = ye * math.cos(ob) - ze * math.sin(ob)
    zq = ye * math.sin(ob) + ze * math.cos(ob)
    ra = math.degrees(math.atan2(yq, xq)) % 360.0
    dec = math.degrees(math.atan2(zq, math.hypot(xq, yq)))
    return ra, dec


def sun_radec(jd):
    lon_s, lat_s, _ = sun_ecliptic(jd)
    return ecl2radec(lon_s, lat_s, jd)


def moon_radec(jd, lat, lon):
    lon_m, lat_m, _ = moon_topocentric(jd, lat, lon)
    return ecl2radec(lon_m, lat_m, jd)


def bright_limb_position_angle(jd, lat, lon):
    """Position angle (deg, measured from celestial north through east) of the
    Moon's bright limb toward the Sun - used to orient the drawn crescent."""
    ra_s, dec_s = sun_radec(jd)
    ra_m, dec_m = moon_radec(jd, lat, lon)
    ra_s, dec_s = math.radians(ra_s), math.radians(dec_s)
    ra_m, dec_m = math.radians(ra_m), math.radians(dec_m)
    x = math.cos(dec_s) * math.sin(ra_s - ra_m)
    y = (math.cos(dec_m) * math.sin(dec_s)
         - math.sin(dec_m) * math.cos(dec_s) * math.cos(ra_s - ra_m))
    return math.degrees(math.atan2(x, y)) % 360.0


def elongation(lon1, lat1, lon2, lat2):
    """Angular separation in degrees between two ecliptic positions.

    Args:
        lon1, lat1: ecliptic longitude / latitude of the first body (degrees)
        lon2, lat2: ecliptic longitude / latitude of the second body (degrees)

    Returns:
        float: angular separation in degrees, in 0..180

    References:
        Meeus, "Astronomical Algorithms", 2nd ed., Ch. 17 (angular separation)
    """
    dlon = math.radians(normalize(lon1 - lon2))
    b1, b2 = math.radians(lat1), math.radians(lat2)
    cos_ang = (math.cos(b1) * math.cos(b2) * math.cos(dlon)
               + math.sin(b1) * math.sin(b2))
    return math.degrees(math.acos(max(-1.0, min(1.0, cos_ang))))


# ---------------------------------------------------------------------------
# Sunset / moonset solvers
# ---------------------------------------------------------------------------

def _sun_alt_local(dt_local, lat, lon, tz):
    jd = jd_utc(dt_local - timedelta(hours=tz))
    return sun_alt_az(jd, lat, lon)[0]


def _moon_alt_local(dt_local, lat, lon, tz):
    jd = jd_utc(dt_local - timedelta(hours=tz))
    return moon_alt_az(jd, lat, lon)[0]


def _solve(dt_a, dt_b, lat, lon, tz, fn, target):
    """Bisection for fn(time) == target between dt_a (above) and dt_b (below)."""
    lo, hi = dt_a, dt_b
    for _ in range(60):
        mid = lo + (hi - lo) / 2
        if (fn(lo, lat, lon, tz) - target) * (fn(mid, lat, lon, tz) - target) <= 0:
            hi = mid
        else:
            lo = mid
    return lo + (hi - lo) / 2


def _as_datetime(d):
    """Midnight local datetime for a date, or the datetime itself."""
    if isinstance(d, datetime):
        return d
    return datetime(d.year, d.month, d.day)


def sunset_local(date, lat, lon, tz):
    """Local datetime of sunset for the civil date ``date`` (midnight based).

    Returns None when the Sun never sets in the search window (polar day) or
    is already below the horizon at 11:00 local (polar night / deep twilight).
    """
    day = _as_datetime(date)
    start = day.replace(hour=11, minute=0)
    end = day.replace(hour=23, minute=59, second=59)
    a_start = _sun_alt_local(start, lat, lon, tz)
    a_end = _sun_alt_local(end, lat, lon, tz)
    if a_start <= SUN_ALT_SUNSET or a_end >= SUN_ALT_SUNSET:
        # No sign change across the window: already below at 11:00, or still
        # above at 23:59 (midnight sun) - there is no sunset to report.
        return None
    return _solve(start, end, lat, lon, tz, _sun_alt_local, SUN_ALT_SUNSET)


def moonset_local(date, lat, lon, tz):
    """Local datetime of moonset for the civil date ``date`` (searches the
    window from 10:00 to 24:00 + next day 06:00 so the evening setting moon
    is captured even when it sets shortly after midnight)."""
    day = _as_datetime(date)
    start = day.replace(hour=10, minute=0)
    end = day + timedelta(days=1, hours=6)
    if _moon_alt_local(start, lat, lon, tz) <= MOON_ALT_SET:
        return None
    return _solve(start, end, lat, lon, tz, _moon_alt_local, MOON_ALT_SET)


# ---------------------------------------------------------------------------
# Conjunction / moon age
# ---------------------------------------------------------------------------

def _signed_elongation(jd):
    """Signed geocentric sun-moon ecliptic longitude difference (deg, -180..180)."""
    lon_s, _, _ = sun_ecliptic(jd)
    lon_m, _, _ = moon_geocentric(jd)
    d = (lon_m - lon_s) % 360.0
    if d > 180.0:
        d -= 360.0
    return d


_conjunction_cache = {}


def conjunction_before(jd):
    """Julian date of the most recent geocentric new moon before ``jd``.

    Scans the previous 32 days for the last sign change of the signed
    elongation that happens near zero (full-moon wraps at +-180 are skipped).
    Results are memoised per ~6-hour bucket so consecutive evenings within the
    same lunation (e.g. the Ramadan / Eid date walker) reuse one search.
    """
    key = round(jd, 2)
    if key in _conjunction_cache:
        return _conjunction_cache[key]
    last = None
    prev_t = jd - 32.0
    prev_d = _signed_elongation(prev_t)
    t = prev_t + 0.125
    while t <= jd:
        d = _signed_elongation(t)
        if prev_d * d < 0.0 and abs(prev_d) < 90.0 and abs(d) < 90.0:
            lo, hi = prev_t, t
            for _ in range(60):
                mid = (lo + hi) / 2.0
                if _signed_elongation(lo) * _signed_elongation(mid) <= 0:
                    hi = mid
                else:
                    lo = mid
            last = (lo + hi) / 2.0
        prev_t, prev_d = t, d
        t += 0.125
    if last is None:
        last = jd
    if len(_conjunction_cache) > 2048:
        _conjunction_cache.clear()
    _conjunction_cache[key] = last
    return last


def moon_age_hours(jd):
    """Hours since the most recent geocentric new moon (conjunction).

    Age 0 = new moon; a thin crescent just after new moon is a few hours old.

    Args:
        jd: float, Julian date (UTC)

    Returns:
        float: hours since the last conjunction

    References:
        Meeus, "Astronomical Algorithms", 2nd ed., Ch. 49
    """
    return (jd - conjunction_before(jd)) * 24.0


def illumination(elong_deg, moon_dist_er, sun_dist_au):
    """Fraction of the moon's disk illuminated (0 = new, 1 = full).

    Uses the phase angle at the Moon, not the elongation as seen from Earth
    (Meeus, "Astronomical Algorithms", 2nd ed., Ch. 48).
    """
    r = moon_dist_er / AU_IN_EARTH_RADII   # Earth radii -> AU
    R = sun_dist_au
    e = math.radians(elong_deg)
    ms = math.sqrt(R * R + r * r - 2 * R * r * math.cos(e))
    cos_i = (r * r + ms * ms - R * R) / (2.0 * r * ms)
    return (1.0 + cos_i) / 2.0


def crescent_width(arc_l, moon_dist_er, alt_geo):
    """Topocentric crescent width W in arcminutes (Odeh / Yallop).

    ``alt_geo`` must be the observer's *topocentric* altitude of the Moon at
    the same time ``arc_l`` is measured - it drives the parallactic augmentation
    of the apparent semi-diameter, so a geocentric altitude would mix frames.
    """
    parallax_deg = math.degrees(math.asin(1.0 / max(moon_dist_er, 1e-9)))
    sd_min = PARALLAX_COEFF * parallax_deg * 60.0
    sd_topo = sd_min * (1.0 + math.sin(math.radians(alt_geo))
                        * math.sin(math.radians(parallax_deg)))
    return sd_topo * (1.0 - math.cos(math.radians(arc_l)))


# ---------------------------------------------------------------------------
# Criteria
# ---------------------------------------------------------------------------

def mabims_verdict(arc_l_sunset, m_alt_sunset):
    """MABIMS 2023: crescent visible if ArcL >= 6.4 deg and altitude >= 3 deg."""
    return arc_l_sunset >= MABIMS_ARC_L_MIN and m_alt_sunset >= MABIMS_ALT_MIN


def danjon_verdict(arc_l):
    """Danjon limit: the crescent cannot be seen when elongation < 7 deg."""
    return arc_l >= DANJON_ARC_L_MIN


def odeh_verdict(arcv, w, arc_l):
    """Odeh (2006) criterion -> (zone, label).

    The visibility threshold curve is the cubic arcv' = a0 + a1*w + a2*w^2 +
    a3*w^3 (Odeh, "New criterion for lunar crescent visibility", 2006); the
    observed arc-of-vision minus that threshold, v, picks the zone.
    """
    arcv_prime = (ODEH_A0 + ODEH_A1 * w + ODEH_A2 * w * w + ODEH_A3 * w * w * w)
    v = arcv - arcv_prime
    if arc_l < MABIMS_ARC_L_MIN:
        return "D", "Not visible (below Danjon limit)"
    if v >= ODEH_ZONE_A_MIN:
        return "A", "Easily visible to the naked eye"
    if v >= ODEH_ZONE_B_MIN:
        return "B", "Visible with optical aid / maybe naked eye"
    if v >= ODEH_ZONE_C_MIN:
        return "C", "Visible with optical aid only"
    return "D", "Not visible even with optical aid"


# ---------------------------------------------------------------------------
# Full evening report
# ---------------------------------------------------------------------------

def _validate_observer(lat, lon, tz):
    """Validate an observer location / timezone, raising ValueError if out of
    range.  Ranges match the app's Setup dialog (``commit_inputs``)."""
    if not (-90 <= lat <= 90):
        raise ValueError("latitude out of range: %s (must be -90..90)" % lat)
    if not (-180 <= lon <= 180):
        raise ValueError("longitude out of range: %s (must be -180..180)" % lon)
    if not (-14 <= tz <= 14):
        raise ValueError("UTC offset out of range: %s (must be -14..14)" % tz)


def evening_report(date, lat, lon, tz):
    """Compute every parameter needed by the app for the evening of ``date``.

    Returns a dict, or None when the Sun does not set that day (polar summer)
    or the geometry is impossible.

    Args:
        date: a ``datetime.date`` (or ``datetime``) for the evening to analyse.
        lat:  observer latitude in degrees (-90..90).
        lon:  observer longitude in degrees (-180..180).
        tz:   UTC offset in hours (-14..14).

    Returns:
        dict of sighting parameters, or None if there is no sunset.

    Raises:
        TypeError:  if ``date`` is not a date / datetime.
        ValueError: if lat / lon / tz are out of range.

    Example:
        >>> from datetime import date
        >>> report = evening_report(date(2025, 3, 1), lat=31.95, lon=35.34, tz=3.0)
        >>> report["zone"]            # Odeh zone A/B/C/D
        'B'
    """
    if not isinstance(date, (datetime, _dt.date)):
        raise TypeError("date must be a datetime.date or datetime, got %r" % date)
    _validate_observer(lat, lon, tz)

    sunset = sunset_local(date, lat, lon, tz)
    if sunset is None:
        # No sunset this evening (e.g. polar midnight sun) - nothing to report.
        return None
    moonset = moonset_local(date, lat, lon, tz)

    # moon at sunset
    jd_set = jd_utc(sunset - timedelta(hours=tz))
    m_alt_set, m_az_set = moon_alt_az(jd_set, lat, lon)
    lon_m, lat_m, dist_m = moon_topocentric(jd_set, lat, lon)
    lon_s, lat_s, _ = sun_ecliptic(jd_set)
    arc_l_set = elongation(lon_m, lat_m, lon_s, lat_s)

    # best time = sunset + (4/9) * lag   (Yallop 1997 / Odeh 2006)
    if moonset is not None and moonset > sunset:
        lag = (moonset - sunset).total_seconds() / 60.0
        best = sunset + timedelta(seconds=4.0 * lag * 60.0 / 9.0)
    else:
        lag = None
        best = sunset + timedelta(minutes=15)

    jd_best = jd_utc(best - timedelta(hours=tz))
    m_alt, m_az = moon_alt_az(jd_best, lat, lon)
    s_alt, s_az = sun_alt_az(jd_best, lat, lon)
    lon_mb, lat_mb, dist_mb = moon_topocentric(jd_best, lat, lon)
    lon_sb, lat_sb, sun_dist = sun_ecliptic(jd_best)
    arc_l_best = elongation(lon_mb, lat_mb, lon_sb, lat_sb)
    arc_v = m_alt - s_alt
    daz = (s_az - m_az) % 360.0
    if daz > 180.0:
        daz = 360.0 - daz
    # Crescent width: the parallactic augmentation of the apparent semi-diameter
    # needs the observer's TOPOCENTRIC altitude.  Use m_alt (topocentric, at the
    # best time, consistent with arc_l_best / dist_mb) rather than an altitude
    # derived from geocentric coordinates, which would ignore lunar parallax.
    w = crescent_width(arc_l_best, dist_mb, m_alt)
    age = moon_age_hours(jd_best)
    illum = illumination(arc_l_best, dist_mb, sun_dist)
    age_set = moon_age_hours(jd_set)
    pa = bright_limb_position_angle(jd_best, lat, lon)

    zone, zone_label = odeh_verdict(arc_v, w, arc_l_best)

    return {
        "date": date,
        "sunset": sunset,
        "moonset": moonset,
        "lag": lag,                       # minutes (None if moon already set)
        "best": best,
        "age": age,                       # hours at best time
        "age_sunset": age_set,
        "illum": illum,
        "arc_l_sunset": arc_l_set,
        "arc_l": arc_l_best,
        "arc_v": arc_v,
        "daz": daz,
        "w": w,
        "m_alt": m_alt,                   # topocentric moon altitude at best time
        "m_alt_sunset": m_alt_set,
        "m_az_sunset": m_az_set,
        "m_az": m_az,
        "s_alt": s_alt,
        "s_az": s_az,
        "zone": zone,
        "zone_label": zone_label,
        "pa": pa,
        "mabims": mabims_verdict(arc_l_set, m_alt_set),
        "danjon": danjon_verdict(arc_l_best),
    }


def altitude_series(report, lat, lon, tz, step_min=10):
    """(time, moon_alt, sun_alt) samples from sunset to moonset / +3h."""
    t0 = report["sunset"]
    end = report["moonset"] or (t0 + timedelta(hours=3))
    if end <= t0:
        end = t0 + timedelta(hours=3)
    ts, alts, s_alts = [], [], []
    t = t0
    while t <= end:
        jd = jd_utc(t - timedelta(hours=tz))
        alts.append(moon_alt_az(jd, lat, lon)[0])
        s_alts.append(sun_alt_az(jd, lat, lon)[0])
        ts.append(t)
        t += timedelta(minutes=step_min)
    return ts, alts, s_alts


def sunset_altitudes_14days(date, lat, lon, tz, days=14):
    """Moon altitude at sunset for the next ``days`` evenings."""
    rows = []
    for i in range(days):
        d = date + timedelta(days=i)
        ss = sunset_local(d, lat, lon, tz)
        if ss is None:
            rows.append((d, None))
            continue
        jd = jd_utc(ss - timedelta(hours=tz))
        alt = moon_alt_az(jd, lat, lon)[0]
        rows.append((d, alt))
    return rows
