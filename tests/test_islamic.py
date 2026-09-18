"""Golden checks for Islamic calendar date computation."""

from datetime import date, datetime

import islamic

_LAT, _LON, _TZ = 30.900965, 75.857275, 5.5


def test_events_keys():
    ev = islamic.events(_LAT, _LON, _TZ, now=datetime(2025, 3, 5))
    assert ev.keys() == {"location", "today", "events"}
    names = [e["name"] for e in ev["events"]]
    assert "Ramadan" in names
    assert "Eid ul Fitr" in names
    assert "Eid ul Adha" in names


def test_events_next_dates():
    ev = islamic.events(_LAT, _LON, _TZ, now=datetime(2025, 3, 5))
    by = {e["name"]: e for e in ev["events"]}
    # 2025-03-05 is after 1 Ramadan 1446 (2025-03-01) — next Ramadan is 1447
    assert by["Ramadan"]["prev"][1] == date(2025, 3, 1)
    assert by["Ramadan"]["next"][1] == date(2026, 2, 19)
    assert by["Eid ul Fitr"]["next"][1] == date(2025, 3, 31)
    assert by["Eid ul Adha"]["next"][1] == date(2025, 6, 6)


def test_events_location_and_today():
    ev = islamic.events(_LAT, _LON, _TZ, now=datetime(2025, 3, 5))
    assert ev["location"] == (_LAT, _LON, _TZ)
    assert ev["today"] == date(2025, 3, 5)
