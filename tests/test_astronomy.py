"""Spot-checks and golden values for astronomy.py."""

import astronomy

_LAT, _LON, _TZ = 30.900965, 75.857275, 5.5


def test_evening_report_keys():
    rep = astronomy.evening_report(
        __import__("datetime").datetime(2025, 3, 1), _LAT, _LON, _TZ)
    assert rep is not None
    assert "sunset" in rep and "m_alt_sunset" in rep and "lag" in rep


def test_evening_report_golden_values():
    from datetime import datetime
    rep = astronomy.evening_report(datetime(2025, 3, 1), _LAT, _LON, _TZ)
    assert rep is not None
    assert rep["sunset"].isoformat().startswith("2025-03-01")
    assert round(rep["m_alt_sunset"], 4) == 18.794
    assert round(rep["arc_l_sunset"], 4) == 19.8315
    assert round(rep["illum"], 6) == 0.031041
    assert rep["mabims"] is True


def test_conjunction_before_returns_earlier_jd():
    from datetime import datetime
    jd = astronomy.jd_utc(datetime(2025, 3, 10))
    conj = astronomy.conjunction_before(jd)
    assert conj < jd
    dt = astronomy.dt_utc_from_jd(conj)
    assert dt.year == 2025 and dt.month == 2


def test_sun_alt_near_zenith_at_subsolar_point():
    from datetime import datetime
    jd = astronomy.jd_utc(datetime(2025, 3, 20, 12, 0, 0))
    ecl_lon, ecl_lat, _ = astronomy.sun_ecliptic(jd)
    # observer under the subsolar point should see the Sun near zenith
    lat = max(-90.0, min(90.0, ecl_lat))
    alt, az = astronomy.sun_alt_az(jd, lat, ecl_lon)
    assert alt > 85.0


def test_mabims_verdict_boundary():
    assert astronomy.mabims_verdict(6.4, 3.0) is True
    assert astronomy.mabims_verdict(0.0, 0.0) is False


def test_danjon_verdict_boundary():
    assert astronomy.danjon_verdict(7.0) is True
    assert astronomy.danjon_verdict(0.0) is False


def test_odeh_verdict_returns_valid_zone():
    # arc_v=15°, w=6° arc_l=15°: clearly visible zone
    zone, _desc = astronomy.odeh_verdict(15.0, 6.0, 15.0)
    assert zone in ("A", "B", "C", "D")
