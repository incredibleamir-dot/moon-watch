"""islamic.py - Ramadan, Eid ul Fitr and Eid ul Adha dates for any place.

The Islamic months are found from the new-moon (conjunction) dates computed by
``astronomy`` plus a local-sighting rule that matches the rest of the app: a
month begins the day *after* the first evening when the young crescent is above
the horizon at sunset at the chosen location.  The absolute month number is
anchored to a well-known reference (1 Ramadan 1446 AH = 1 March 2025) and the
lunations are then counted forward / backward from it.
"""

from datetime import date, datetime, timedelta

import astronomy

MONTH_NAMES = [
    "Muharram", "Safar", "Rabi al-Awwal", "Rabi al-Thani",
    "Jumada al-Ula", "Jumada al-Akhirah", "Rajab", "Sha'ban",
    "Ramadan", "Shawwal", "Dhul Qa'dah", "Dhul Hijjah",
]

# Reference: 1 Ramadan 1446 AH = 2025-03-01 (common civil anchor).
ANCHOR_DATE = date(2025, 3, 1)
ANCHOR_MONTH = 9        # Ramadan
ANCHOR_YEAR = 1446

SYNODIC = 29.530588853

RAMADAN = 9
SHAWWAL = 10            # Eid ul Fitr is 1 Shawwal
DHUL_HIJJAH = 12        # Eid ul Adha is 10 Dhul Hijjah


def _month_start(lat, lon, tz, conj_jd):
    """Local day-1 date of the month that follows the new moon at ``conj_jd``.

    The crescent is looked for on the evening of the conjunction and the next
    few evenings; the month starts the day after the first evening on which the
    young moon is actually above the horizon at sunset here.
    """
    local = astronomy.dt_utc_from_jd(conj_jd) + timedelta(hours=tz)
    base = local.date()
    for probe in range(4):
        evening = base + timedelta(days=probe)
        rep = astronomy.evening_report(
            datetime(evening.year, evening.month, evening.day), lat, lon, tz)
        if rep is not None and rep["lag"] is not None and rep["m_alt_sunset"] > 0.0:
            return evening + timedelta(days=1)
    return base + timedelta(days=1)


def _month_starts(lat, lon, tz, jd_from, jd_to):
    """(conj_jd, day1_date) for every lunation whose conjunction lies in range."""
    out = []
    jd = jd_from
    while jd < jd_to:
        conj = astronomy.conjunction_before(jd)
        out.append((conj, _month_start(lat, lon, tz, conj)))
        jd = conj + SYNODIC + 0.5
    return out


def _fmt_ah(month, year):
    return "%s %d AH" % (MONTH_NAMES[month - 1], year)


def _pick(rows, today, offset_days):
    """Single closest previous and next (year, civil_date) around ``today``."""
    items = [(y, day1 + timedelta(days=offset_days))
             for y, day1 in sorted(rows, key=lambda r: r[1])]
    prevs = [(y, d) for (y, d) in items if d <= today]
    nexts = [(y, d) for (y, d) in items if d > today]
    return (prevs[-1] if prevs else None, nexts[0] if nexts else None)


def _pick_many(rows, today, offset_days, n=6):
    """Sorted (year, civil_date) pairs around ``today`` - the closest n each way."""
    items = [(y, day1 + timedelta(days=offset_days))
             for y, day1 in sorted(rows, key=lambda r: r[1])]
    prevs = [(y, d) for (y, d) in items if d <= today]
    nexts = [(y, d) for (y, d) in items if d > today]
    return prevs[-n:], nexts[:n]


def _calendar(lat, lon, tz, now):
    """(today, months) - months = [(month, year, day1_date), ...] around today."""
    now = now or datetime.now()
    today = now.date()
    utc_noon = datetime(now.year, now.month, now.day, 12) - timedelta(hours=tz)
    jd_today = astronomy.jd_utc(utc_noon)

    starts = _month_starts(lat, lon, tz,
                           jd_today - 6 * 366.0, jd_today + 6 * 366.0)
    if not starts:
        return today, []

    best = min(range(len(starts)),
               key=lambda i: abs((starts[i][1] - ANCHOR_DATE).days))
    months = []
    for i, (_conj, day1) in enumerate(starts):
        dm = i - best
        month = (ANCHOR_MONTH - 1 + dm) % 12 + 1
        year = ANCHOR_YEAR + (ANCHOR_MONTH - 1 + dm) // 12
        months.append((month, year, day1))
    return today, months


def _by_month(months):
    grouped = {}
    for month, year, day1 in months:
        grouped.setdefault(month, []).append((year, day1))
    return grouped


def events(lat, lon, tz, now=None):
    """Previous and next Ramadan, Eid ul Fitr and Eid ul Adha at this place.

    Returns a dict::

        {
          "location": (lat, lon, tz),
          "today": date,
          "events": [
            {"name", "desc", "ah_name", "prev": (year, date)|None,
             "next": (year, date)|None},
            ...
          ],
        }
    """
    today, months = _calendar(lat, lon, tz, now)
    by_month = _by_month(months)
    ramadan = by_month.get(RAMADAN, [])
    shawwal = by_month.get(SHAWWAL, [])
    dhu_hij = by_month.get(DHUL_HIJJAH, [])

    return {
        "location": (lat, lon, tz),
        "today": today,
        "events": [
            {"name": "Ramadan",
             "desc": "start of the fasting month",
             "ah_name": "1 Ramadan",
             "prev": _pick(ramadan, today, 0)[0],
             "next": _pick(ramadan, today, 0)[1]},
            {"name": "Eid ul Fitr",
             "desc": "1 Shawwal, end of the fast",
             "ah_name": "1 Shawwal",
             "prev": _pick(shawwal, today, 0)[0],
             "next": _pick(shawwal, today, 0)[1]},
            {"name": "Eid ul Adha",
             "desc": "10 Dhul Hijjah, Feast of Sacrifice",
             "ah_name": "10 Dhul Hijjah",
             "prev": _pick(dhu_hij, today, 9)[0],
             "next": _pick(dhu_hij, today, 9)[1]},
        ],
    }


def event_series(lat, lon, tz, now=None, n=6):
    """The same three events, each with the n previous and n next civil dates.

    Each entry is (ah_year, civil_date) where ``civil_date`` is the civil
    calendar day the occasion falls on (the sighting night is the evening
    before it, because the Islamic day starts at sunset).
    """
    today, months = _calendar(lat, lon, tz, now)
    by_month = _by_month(months)
    ramadan = by_month.get(RAMADAN, [])
    shawwal = by_month.get(SHAWWAL, [])
    dhu_hij = by_month.get(DHUL_HIJJAH, [])

    return {
        "location": (lat, lon, tz),
        "today": today,
        "events": [
            {"name": "Ramadan", "ah_name": "1 Ramadan",
             "desc": "start of the fasting month",
             "prev6": _pick_many(ramadan, today, 0, n)[0],
             "next6": _pick_many(ramadan, today, 0, n)[1]},
            {"name": "Eid ul Fitr", "ah_name": "1 Shawwal",
             "desc": "1 Shawwal - end of the fasting month",
             "prev6": _pick_many(shawwal, today, 0, n)[0],
             "next6": _pick_many(shawwal, today, 0, n)[1]},
            {"name": "Eid ul Adha", "ah_name": "10 Dhul Hijjah",
             "desc": "10 Dhul Hijjah - Feast of Sacrifice",
             "prev6": _pick_many(dhu_hij, today, 9, n)[0],
             "next6": _pick_many(dhu_hij, today, 9, n)[1]},
        ],
    }
