"""Tests for astronomy.py against known, independently-verifiable values.

The reference numbers for 2024-04-09 Ludhiana were cross-checked live against
the NASA/JPL HORIZONS ephemeris (see verification.py); tolerances are kept
looser than the online check so these stay fast and deterministic.
"""

import datetime
import math

import pytest

import astronomy

LUDHIANA = dict(lat=30.90, lon=75.85, tz=5.5)
D = datetime.datetime(2024, 4, 9)


def report(**kw):
    lat = kw.get("lat", LUDHIANA["lat"])
    lon = kw.get("lon", LUDHIANA["lon"])
    tz = kw.get("tz", LUDHIANA["tz"])
    return astronomy.evening_report(kw.get("date", D), lat, lon, tz)


class TestEveningReport:
    def test_known_values_match_horizons(self):
        r = report()
        assert r is not None
        # HORIZONS: sunset 18:50, moonset 19:41 local
        assert abs((r["sunset"] - datetime.datetime(2024, 4, 9, 18, 50))
                   .total_seconds()) < 300
        assert abs((r["moonset"] - datetime.datetime(2024, 4, 9, 19, 41))
                   .total_seconds()) < 600
        assert abs(r["m_alt_sunset"] - 9.29) < 1.5
        assert abs(r["m_az_sunset"] - 283.0) < 6.0
        assert abs(r["arc_l_sunset"] - 10.13) < 2.0
        assert abs(r["illum"] * 100 - 0.78) < 1.5

    def test_illumination_in_valid_range(self):
        for day in (1, 9, 17, 25):
            r = report(date=datetime.datetime(2024, 4, day))
            assert 0.0 <= r["illum"] <= 1.0
            assert 0.0 <= r["arc_l_sunset"] <= 180.0

    def test_moonset_none_when_moon_already_set(self):
        # 2025-01-04 Ludhiana: the Sun sets at ~17:38 but the Moon is below the
        # horizon through the moonset search window -> no moonset, no lag.
        r = report(date=datetime.datetime(2025, 1, 4))
        assert r is not None
        assert r["moonset"] is None
        assert r["lag"] is None

    def test_age_positive(self):
        r = report()
        assert r["age_sunset"] > 0
        assert r["age_sunset"] < 360

    def test_mabims_is_boolean(self):
        r = report()
        assert isinstance(r["mabims"], bool)

    def test_sunset_altitudes_14days_length(self):
        s = astronomy.sunset_altitudes_14days(D, LUDHIANA["lat"],
                                              LUDHIANA["lon"],
                                              LUDHIANA["tz"], 14)
        assert len(s) == 14
        for day, alt in s:
            assert isinstance(day, datetime.datetime)
            assert alt is None or isinstance(alt, float)


class TestAltitudeSeries:
    def test_returns_time_and_altitude_lists(self):
        r = report()
        ts, alts, s_alts = astronomy.altitude_series(
            r, LUDHIANA["lat"], LUDHIANA["lon"], LUDHIANA["tz"], 12)
        assert isinstance(ts, list) and len(ts) == len(alts)
        assert len(alts) >= 5
        assert all(isinstance(v, float) for v in alts)
        assert all(math.isfinite(v) for v in s_alts)
