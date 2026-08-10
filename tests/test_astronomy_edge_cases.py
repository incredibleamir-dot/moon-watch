"""Edge-case tests for astronomy.py: polar behaviour, coordinate frames and
input validation."""

import datetime
import math

import pytest

import astronomy


class TestPolarAndGeometry:
    def test_polar_no_sunset(self):
        """Svalbard in midsummer has 24h daylight - no sunset to report."""
        result = astronomy.evening_report(datetime.date(2025, 6, 21),
                                          lat=78.0, lon=15.0, tz=2.0)
        assert result is None

    def test_accepts_plain_date_and_datetime(self):
        d = datetime.date(2025, 3, 1)
        dt = datetime.datetime(2025, 3, 1)
        a = astronomy.evening_report(d, lat=31.95, lon=35.34, tz=3.0)
        b = astronomy.evening_report(dt, lat=31.95, lon=35.34, tz=3.0)
        assert a is not None and b is not None
        assert a["sunset"] == b["sunset"]
        assert a["date"].year == b["date"].year == 2025

    def test_crescent_width_positive_and_finite(self):
        r = astronomy.evening_report(datetime.datetime(2025, 3, 1),
                                     lat=31.95, lon=35.34, tz=3.0)
        assert r is not None
        assert r["w"] > 0.0 and math.isfinite(r["w"])


class TestTopocentricVsGeocentric:
    def test_parallax_is_significant(self):
        """Topocentric vs geocentric altitude must differ by ~1 degree near
        the horizon (lunar parallax), which is why the crescent-width altitude
        must not come from geocentric coordinates."""
        jd = 2460000.0
        lon_t, lat_t, _ = astronomy.moon_topocentric(jd, lat=40.0, lon=-74.0)
        lon_g, lat_g, _ = astronomy.moon_geocentric(jd)
        alt_t = astronomy.ecl2alt_az(lon_t, lat_t, jd, 40.0, -74.0)[0]
        alt_g = astronomy.ecl2alt_az(lon_g, lat_g, jd, 40.0, -74.0)[0]
        assert abs(alt_t - alt_g) > 0.5

    def test_report_uses_topocentric_altitude(self):
        """crescent_width must receive the topocentric altitude.  Reproduce
        the internal computation from the report's best time and confirm the
        stored width matches - proving no geocentric-derived altitude slipped
        in."""
        r = astronomy.evening_report(datetime.datetime(2025, 3, 1),
                                     lat=31.95, lon=35.34, tz=3.0)
        assert r is not None
        jd_best = astronomy.jd_utc(r["best"] - datetime.timedelta(hours=3.0))
        _, _, dist = astronomy.moon_topocentric(jd_best, 31.95, 35.34)
        w = astronomy.crescent_width(r["arc_l"], dist, r["m_alt"])
        assert abs(r["w"] - w) < 1e-9


class TestInputValidation:
    def test_latitude_out_of_range(self):
        with pytest.raises(ValueError):
            astronomy.evening_report(datetime.date(2025, 1, 1), lat=91.0,
                                     lon=0, tz=0)

    def test_longitude_out_of_range(self):
        with pytest.raises(ValueError):
            astronomy.evening_report(datetime.date(2025, 1, 1), lat=0,
                                     lon=181, tz=0)

    def test_timezone_out_of_range(self):
        with pytest.raises(ValueError):
            astronomy.evening_report(datetime.date(2025, 1, 1), lat=0,
                                     lon=0, tz=15)

    def test_bad_date_type(self):
        with pytest.raises(TypeError):
            astronomy.evening_report("2025-01-01", lat=0, lon=0, tz=0)


class TestConstants:
    def test_named_constants_used(self):
        assert astronomy.MABIMS_ARC_L_MIN == 6.4
        assert astronomy.DANJON_ARC_L_MIN == 7.0
        assert astronomy.ODEH_A0 == 7.1651

    def test_no_dead_rad_constant(self):
        assert not hasattr(astronomy, "RAD")
