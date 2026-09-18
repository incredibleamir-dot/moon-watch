"""Global lunar-crescent visibility map.

Computes, on a 1-degree latitude/longitude grid, the evening crescent
visibility class for a given date: how many places on Earth would see the new
crescent if the sky were clear.  The computation mirrors ``astronomy``'s local
``evening_report`` rule for rule (Odeh 2006 zones at each place's *best time*
= sunset + 4/9 of the moonset lag, MABIMS 2023 and the Danjon limit) so the
map and the local Sighting verdict never disagree about what "visible" means.

A naive per-point sunset solve would be far too slow for 65k grid points, so
the Sun's setting instant is profiled once per *latitude* (the daily elevation
curve is the same for every longitude, just shifted in UT).  Each grid point
then solves ``moonset`` with a short warm-started bisection and evaluates the
Moon at its own sunset and best instants.

Run at module level so ``multiprocessing`` (Windows ``spawn``) can re-import
it in the worker process.
"""

import datetime
import math
import time

import numpy as np

import astronomy

SUNSET_ALT = astronomy.SUN_ALT_SUNSET          # -0.833 degrees
MOON_ALT_SET = astronomy.MOON_ALT_SET          # -0.833 degrees
STEP_MIN = 10                                  # minutes, sun-profile sampling
LAG_SAMPLES_H = (0.75, 1.5, 2.5, 4.0, 6.0, 9.0)   # moonset scan offsets after sunset

# 1-degree grid
LATS = np.arange(89.0, -90.0, -1.0)            # row-major, north pole -> south
LONS = np.arange(-179.0, 180.0, 1.0)
NLAT, NLON = len(LATS), len(LONS)

# Zone codes shared with the widget
VISIBLE, BORDERLINE, NOT_VISIBLE, NO_SUNSET = 0, 1, 2, 3


def _sunset_ut0(date, lat):
    """UTC instant of the evening sunset at (``lat``, 0 lon) for ``date``.

    Returns ``None`` when the Sun does not set that evening at these
    latitudes of the date window (polar day/night) - matching the app's
    ``sunset_local`` return value.
    """
    day = datetime.datetime.combine(date, datetime.time(0, 0))
    t0 = day + datetime.timedelta(hours=6)     # earliest possible sunset UT
    span_h = 30.0                              # one full world-longitudes sweep
    n = int(round(span_h * 3600.0 / (STEP_MIN * 60))) + 1
    times = [t0 + datetime.timedelta(minutes=STEP_MIN * i) for i in range(n)]
    alts = np.array([astronomy.sun_alt_az(astronomy.jd_utc(t), lat, 0.0)[0]
                     for t in times], dtype=float)
    below = alts <= SUNSET_ALT
    if below.all() or not below.any():
        return None                           # polar night or midnight sun
    # the trailing edge of the "sun above" run is the evening crossing
    run = np.where(alts > SUNSET_ALT)[0]
    idx = None
    for i in run:
        if i + 1 < n and alts[i + 1] <= SUNSET_ALT:
            idx = i
            break
    if idx is None:
        return None
    lo, hi = times[idx], times[idx + 1]
    for _ in range(22):
        mid = lo + (hi - lo) / 2.0
        if astronomy.sun_alt_az(astronomy.jd_utc(mid), lat, 0.0)[0] > SUNSET_ALT:
            lo = mid
        else:
            hi = mid
    return lo + (hi - lo) / 2.0


def _point_values(jd, lat, lon):
    """(moon ecl lon/lat/dist, moon alt) for one grid point.

    The solarsystem topocentric parallax has a sin(g)~0 singularity at exact
    conjunction; fall back to the geocentric position there (the cells are a
    hair's-breadth band around new moon where it does not matter).
    """
    try:
        lon_m, lat_m, dist_m = astronomy.moon_topocentric(jd, lat, lon)
    except Exception:
        lon_m, lat_m, dist_m = astronomy.moon_geocentric(jd)
    m_alt, _ = astronomy.ecl2alt_az(lon_m, lat_m, jd, lat, lon)
    return lon_m, lat_m, dist_m, m_alt


def _moonset_ut(sunset, lat, lon, mh_at_sunset):
    """UTC instant of moonset after ``sunset`` (or ``None``).

    ``mh_at_sunset`` is the Moon topocentric altitude at sunset; if it is
    below the setting horizon there is no evening moonset to chase.  A few
    coarse samples locate the descending crossing, then a short bisection
    refines it (millisecond-exact instants are pointless at 1-degree scale).
    """
    if mh_at_sunset <= MOON_ALT_SET:
        return None
    alts = []
    for off in LAG_SAMPLES_H:
        alts.append(_point_values(
            astronomy.jd_utc(sunset + datetime.timedelta(hours=off)),
            lat, lon)[3])
    i = None
    for k, a in enumerate(alts):
        if a <= MOON_ALT_SET:
            i = k
            break
    if i is None:
        return None                       # moon stays up all evening
    lo = sunset + datetime.timedelta(hours=0.0 if i == 0 else LAG_SAMPLES_H[i - 1])
    hi = sunset + datetime.timedelta(hours=LAG_SAMPLES_H[i])
    for _ in range(12):
        mid = lo + (hi - lo) / 2.0
        if _point_values(astronomy.jd_utc(mid), lat, lon)[3] > MOON_ALT_SET:
            lo = mid
        else:
            hi = mid
    return lo + (hi - lo) / 2.0


def compute(date, progress=None):
    """Grid arrays for the evening of ``date``.

    For every cell: ``mh``/``ark`` are the Moon's altitude and arc of light
    *at sunset* (the MABIMS quantities); ``av``/``w``/``ark_b`` are the arc of
    vision, crescent width and arc of light at that place's *best time*
    (sunset + 4/9 * moonset lag, or +15 min when the Moon sets first / stays
    up - exactly as ``astronomy.evening_report``).  ``nolight`` marks cells
    without an evening sunset.
    """
    t_start = time.time()
    sunset0 = []                              # None = no sunset for the latitude
    for i, lat in enumerate(LATS):
        sunset0.append(_sunset_ut0(date, float(lat)))
    nonzero = [i for i, s in enumerate(sunset0) if s is not None]
    mh = np.full((NLAT, NLON), np.nan, np.float32)
    ark = np.full((NLAT, NLON), np.nan, np.float32)
    av = np.full((NLAT, NLON), np.nan, np.float32)
    w = np.full((NLAT, NLON), np.nan, np.float32)
    ark_b = np.full((NLAT, NLON), np.nan, np.float32)
    nolight = np.ones((NLAT, NLON), bool)
    done = 0
    for li in nonzero:
        s0 = sunset0[li]
        lat = float(LATS[li])
        for j, lon in enumerate(LONS):
            sunset = s0 - datetime.timedelta(hours=float(lon) / 15.0)
            jd = astronomy.jd_utc(sunset)
            lon_m, lat_m, dist_m, m_alt = _point_values(jd, lat, float(lon))
            lon_s, lat_s, _sd = astronomy.sun_ecliptic(jd)
            ark1 = astronomy.elongation(lon_m, lat_m, lon_s, lat_s)
            mh[li, j] = m_alt
            ark[li, j] = ark1
            nolight[li, j] = False
            # best time = sunset + 4/9 * lag, or +15 min when the moon sets
            # before the sun / stays up all evening (exactly as the app).
            if m_alt > MOON_ALT_SET:
                ms = _moonset_ut(sunset, lat, float(lon), m_alt)
                if ms is not None and ms > sunset:
                    lag_min = (ms - sunset).total_seconds() / 60.0
                    best = sunset + datetime.timedelta(
                        seconds=4.0 * lag_min * 60.0 / 9.0)
                else:
                    best = sunset + datetime.timedelta(minutes=15)
            else:
                best = sunset + datetime.timedelta(minutes=15)
            jdb = astronomy.jd_utc(best)
            lon_mb, lat_mb, dist_mb, m_altt = _point_values(
                jdb, lat, float(lon))
            lon_sb, lat_sb, _ = astronomy.sun_ecliptic(jdb)
            s_altt, _ = astronomy.ecl2alt_az(lon_sb, lat_sb, jdb,
                                             lat, float(lon))
            ark_b[li, j] = astronomy.elongation(lon_mb, lat_mb, lon_sb, lat_sb)
            av[li, j] = m_altt - s_altt
            w[li, j] = astronomy.crescent_width(ark_b[li, j], dist_mb, m_altt)
            done += 1
        if progress is not None and (li + 1) % max(1, NLAT // 20) == 0:
            progress(float(li + 1) / NLAT)
    if progress is not None:
        progress(1.0)
    return {
        "date": date,
        "mh": mh, "ark": ark,
        "av": av, "w": w, "ark_b": ark_b, "nolight": nolight,
        "seconds": time.time() - t_start,
    }


def classify(crit, mh, ark, av, w, ark_b, nolight):
    """Array of zone codes (0=visible .. 3=no sunset) for a criterion.

    Mirrors the app's verdict exactly so the map never disagrees with the
    Sighting page: *odeh* = the app's combined verdict (Odeh zones with the
    best-time arc-of-vision/width, plus MABIMS on the sunset values and the
    Danjon limit on the best-time arc of light, with no altitude gate, just
    like ``Controller.verdict``).  *mabims* / the Danjon limit are the bare
    criteria (moon up above the horizon to count as visible).
    """
    out = np.where(nolight, NO_SUNSET, NOT_VISIBLE).astype(np.int8)
    live = ~np.isnan(mh) & ~np.isnan(ark) & ~np.isnan(ark_b) & ~nolight
    if crit == "mabims":
        vis = live & (ark >= astronomy.MABIMS_ARC_L_MIN) & (
            mh >= astronomy.MABIMS_ALT_MIN)
        bor = live & (mh > 0.0) & ~vis & (
            (ark >= astronomy.MABIMS_ARC_L_MIN) |
            (mh >= astronomy.MABIMS_ALT_MIN))
    elif crit == "danjon":
        vis = live & (mh > 0.0) & (ark_b >= astronomy.DANJON_ARC_L_MIN)
        bor = live & (mh > 0.0) & ~vis & (ark_b >= 4.5)
    else:  # odeh - exactly Controller.verdict()
        prime = (astronomy.ODEH_A0 + astronomy.ODEH_A1 * w +
                 astronomy.ODEH_A2 * w * w + astronomy.ODEH_A3 * w * w * w)
        v = av - prime
        zone_ab = live & (ark_b >= astronomy.MABIMS_ARC_L_MIN) & (
            v >= astronomy.ODEH_ZONE_B_MIN)
        zone_c = live & (ark_b >= astronomy.MABIMS_ARC_L_MIN) & ~zone_ab & (
            v >= astronomy.ODEH_ZONE_C_MIN)
        mabims_vis = (ark >= astronomy.MABIMS_ARC_L_MIN) & (
            mh >= astronomy.MABIMS_ALT_MIN)
        danjon_vis = ark_b >= astronomy.DANJON_ARC_L_MIN
        vis = zone_ab
        bor = (zone_c | mabims_vis | danjon_vis) & ~vis
    out[vis] = VISIBLE
    out[bor] = BORDERLINE
    return out