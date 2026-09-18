"""Tests for phone-pointing calibration helpers (no GUI needed)."""

from moonwatch.sensorcast import (accel_mag_to_aim, apply_calibration,
                                  calibration_from_aim, mag_strength,
                                  q_to_aim, wrap_az_delta)


def test_wrap_az_delta():
    assert wrap_az_delta(350.0) == -10.0
    assert wrap_az_delta(-190.0) == 170.0
    assert wrap_az_delta(180.0) == 180.0
    assert wrap_az_delta(0.0) == 0.0


def test_calibration_roundtrip():
    # phone raw 10 deg + north 2 deg should need +3 deg to reach target 15.
    az_off, alt_off = calibration_from_aim(10.0, 20.0, 15.0, 22.0,
                                           north_offset=2.0)
    assert round(az_off, 6) == 3.0
    assert round(alt_off, 6) == 2.0
    out_az, out_alt = apply_calibration(10.0, 20.0, 2.0, az_off, alt_off)
    assert round(out_az, 6) == 15.0
    assert round(out_alt, 6) == 22.0


def test_calibration_wraps():
    az_off, _ = calibration_from_aim(350.0, 10.0, 10.0, 10.0)
    assert round(az_off, 6) == 20.0
    out_az, _ = apply_calibration(350.0, 10.0, 0.0, az_off, 0.0)
    assert round(out_az, 6) == 10.0


def test_calibration_alt_clamped():
    _, alt_off = calibration_from_aim(0.0, 0.0, 0.0, 80.0)
    assert alt_off == 30.0
    _, alt_off2 = calibration_from_aim(0.0, 50.0, 0.0, 0.0)
    assert alt_off2 == -30.0


def test_top_axis_identity_points_north_horizon():
    az, alt = q_to_aim(0.0, 0.0, 0.0, 1.0, axis="top")
    assert round(az, 6) == 0.0
    assert round(alt, 6) == 0.0


def test_back_axis_default_unchanged():
    # default axis stays "back" so old callers/tests keep working
    az, alt = q_to_aim(0.0, 0.0, 0.0, 1.0)
    assert round(az, 6) == 0.0
    assert round(alt, 6) == -90.0


def test_accel_mag_flat_top_north():
    az, alt = accel_mag_to_aim(0, 0, 9.8, 0, 20, -40, axis="top")
    assert az is not None
    assert round(az, 6) == 0.0
    assert round(alt, 6) == 0.0


def test_accel_mag_flat_top_east():
    az, alt = accel_mag_to_aim(0, 0, 9.8, -20, 0, -40, axis="top")
    assert round(az, 6) == 90.0
    assert round(alt, 6) == 0.0


def test_accel_mag_degenerate_returns_none():
    az, alt = accel_mag_to_aim(0, 0, 0, 0, 0, 0)
    assert az is None and alt is None


def test_mag_strength_range():
    assert 25.0 <= mag_strength(0, 20, -40) <= 65.0
