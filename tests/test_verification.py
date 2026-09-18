"""Tests for verification.py - interpolation helpers, the offline
observation check, and (when a network is present) the live NASA/JPL
HORIZONS comparison against both a past and a future date.
"""

import datetime

import pytest

import verification

D_PAST = datetime.datetime(2024, 4, 9)
D_FUTURE = datetime.datetime(2026, 8, 20)
LUDHIANA = dict(lat=30.90, lon=75.85, tz=5.5)
MECCA = dict(lat=21.4225, lon=39.8262, tz=3.0)


class TestInterpHelpers:
    def test_interp_set_descending(self):
        times = [datetime.datetime(2024, 1, 1, t, 0) for t in (18, 19, 20)]
        values = [5.0, 2.0, -1.0]
        hit = verification._interp_set(times, values, 0.0)
        # crosses 0 between 19:00 (2.0) and 20:00 (-1.0)
        assert hit.hour == 19
        assert 0.0 < hit.minute < 60.0

    def test_interp_set_returns_none_when_no_crossing(self):
        times = [datetime.datetime(2024, 1, 1, t, 0) for t in (18, 19, 20)]
        assert verification._interp_set(times, [5.0, 4.0, 3.0], 0.0) is None

    def test_interp_value_linear(self):
        times = [datetime.datetime(2024, 1, 1, t, 0) for t in (18, 19, 20)]
        values = [0.0, 10.0, 20.0]
        assert verification._interp_value(times, values,
                                          datetime.datetime(2024, 1, 1, 18, 30)) \
            == pytest.approx(5.0)

    def test_interp_value_outside(self):
        times = [datetime.datetime(2024, 1, 1, t, 0) for t in (18, 19)]
        assert verification._interp_value(times, [1.0, 2.0],
                                          datetime.datetime(2024, 1, 1, 21)) \
            is None


class TestObservationCheck:
    def test_shape_and_ranges(self):
        res = verification.observation_check(sample=100)
        assert res["n"] > 0
        assert 0.0 <= res["agreement_pct"] <= 100.0
        assert isinstance(res["by_method"], dict)
        for s in (res["err_arc_l"], res["err_m_alt"], res["err_lag_min"]):
            assert s["n"] >= 0
            if s["n"]:
                assert s["mean"] >= 0
                assert s["max"] >= s["p90"] >= 0

    def test_deterministic_sample(self):
        a = verification.observation_check(sample=200)["n"]
        b = verification.observation_check(sample=200)["n"]
        assert a == b


class TestEphemerisCheckOnline:
    @pytest.mark.parametrize("date,loc", [
        (D_PAST, LUDHIANA),     # past
        (D_FUTURE, MECCA),      # future
    ])
    def test_past_and_future_match_horizons(self, date, loc):
        res = verification.ephemeris_check(date, loc["lat"], loc["lon"],
                                           loc["tz"])
        if not res.get("ok") and "HORIZONS request failed" in str(
                res.get("error")):
            pytest.skip("offline - NASA HORIZONS unreachable")
        assert res.get("ok"), res.get("error")
        for key, verdict in res["verdicts"].items():
            ours, hz = res[key]
            if ours is None and hz is None:
                continue  # both agree there is no moonset, e.g.
            assert verdict is not None, "HORIZONS missing value for %s" % key
            assert verdict, "out of tolerance for %s (ours=%s vs nasa=%s)" % (
                key, ours, hz)
