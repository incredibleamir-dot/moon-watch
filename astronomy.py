"""astronomy.py - hilal (new crescent) visibility calculations.

Computes everything needed to judge whether the Ramadan / Eid crescent can be
seen on a given evening from a given place:

  * sunset / moonset times and the moon's lag time
  * moon age, altitude at sunset, arc of light (elongation), arc of vision,
    relative azimuth and crescent width
  * visibility verdicts for the MABIMS 2023, Danjon and Odeh (2006) criteria

The orbital model is Paul Schlyter's ("How to compute planetary positions")
as vendored in this repo's ``vendor/solarsystem`` package, so this module needs
no extra dependency.
"""

import math
import os
import sys
from datetime import datetime, timedelta

LIB_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if LIB_DIR not in sys.path:
    sys.path.insert(0, LIB_DIR)

from solarsystem import Moon          # noqa: E402
from solarsystem.functions import normalize  # noqa: E402

RAD = math.pi / 180.0
SUN_ALT_SUNSET = -0.833       # centre of solar disk at sunset (refraction+size)
MOON_ALT_SET = -0.833         # centre of moon at moonset (topocentric, airless)

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
    """Angular separation in degrees between two ecliptic positions."""
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


def sunset_local(date, lat, lon, tz):
    """Local datetime of sunset for the civil date ``date`` (midnight based)."""
    day = date.replace(hour=0, minute=0, second=0, microsecond=0)
    start = day.replace(hour=11, minute=0)
    end = day.replace(hour=23, minute=59, second=59)
    if _sun_alt_local(start, lat, lon, tz) <= SUN_ALT_SUNSET:
        return None
    return _solve(start, end, lat, lon, tz, _sun_alt_local, SUN_ALT_SUNSET)


def moonset_local(date, lat, lon, tz):
    """Local datetime of moonset for the civil date ``date`` (searches the
    window from 10:00 to 24:00 + next day 06:00 so the evening setting moon
    is captured even when it sets shortly after midnight)."""
    day = date.replace(hour=0, minute=0, second=0, microsecond=0)
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


def conjunction_before(jd):
    """Julian date of the most recent geocentric new moon before ``jd``.

    Scans the previous 32 days for the last sign change of the signed
    elongation that happens near zero (full-moon wraps at +-180 are skipped).
    """
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
    return last if last is not None else jd


def moon_age_hours(jd):
    return (jd - conjunction_before(jd)) * 24.0


def illumination(elong_deg, moon_dist_er, sun_dist_au):
    """Fraction of the moon's disk illuminated (0 = new, 1 = full).

    Uses the phase angle at the Moon, not the elongation as seen from Earth.
    """
    r = moon_dist_er / 23455.0          # earth radii -> AU
    R = sun_dist_au
    e = math.radians(elong_deg)
    ms = math.sqrt(R * R + r * r - 2 * R * r * math.cos(e))
    cos_i = (r * r + ms * ms - R * R) / (2.0 * r * ms)
    return (1.0 + cos_i) / 2.0


def crescent_width(arc_l, moon_dist_er, alt_geo):
    """Topocentric crescent width W in arcminutes (Odeh / Yallop)."""
    parallax_deg = math.degrees(math.asin(1.0 / max(moon_dist_er, 1e-9)))
    sd_min = 0.27245 * parallax_deg * 60.0
    sd_topo = sd_min * (1.0 + math.sin(math.radians(alt_geo))
                        * math.sin(math.radians(parallax_deg)))
    return sd_topo * (1.0 - math.cos(math.radians(arc_l)))


# ---------------------------------------------------------------------------
# Criteria
# ---------------------------------------------------------------------------

def mabims_verdict(arc_l_sunset, m_alt_sunset):
    """MABIMS 2023: crescent visible if ArcL >= 6.4 deg and altitude >= 3 deg."""
    return arc_l_sunset >= 6.4 and m_alt_sunset >= 3.0


def danjon_verdict(arc_l):
    """Danjon limit: the crescent cannot be seen when elongation < 7 deg."""
    return arc_l >= 7.0


def odeh_verdict(arcv, w, arc_l):
    """Odeh (2006) criterion -> (zone, label)."""
    arcv_prime = 7.1651 - 6.3226 * w + 0.7319 * w * w - 0.1018 * w * w * w
    v = arcv - arcv_prime
    if arc_l < 6.4:
        return "D", "Not visible (below Danjon limit)"
    if v >= 5.65:
        return "A", "Easily visible to the naked eye"
    if v >= 2.0:
        return "B", "Visible with optical aid / maybe naked eye"
    if v >= -0.96:
        return "C", "Visible with optical aid only"
    return "D", "Not visible even with optical aid"


# ---------------------------------------------------------------------------
# Full evening report
# ---------------------------------------------------------------------------

def evening_report(date, lat, lon, tz):
    """Compute every parameter needed by the app for the evening of ``date``.

    Returns a dict (or None if no sunset / impossible geometry).
    """
    sunset = sunset_local(date, lat, lon, tz)
    if sunset is None:
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
    lon_mg, lat_mg, dist_mg = moon_geocentric(jd_set)
    alt_geo = ecl2alt_az(lon_mg, lat_mg, jd_set, lat, lon)[0]
    w = crescent_width(arc_l_best, dist_mb, alt_geo)

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
