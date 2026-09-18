"""Tests for the sky-map altitude clamp (pure function + widget smoke)."""

import pytest

from moonwatch.sky_map import BOTTOM_ALT, clamp_alt_center, HorizonSkyWidget


# VSPAN=32, ALT_MAX=90, BOTTOM_ALT=-5
_VSPAN, _ALT_MAX = 32.0, 90.0
_LO = _VSPAN / 2.0 + BOTTOM_ALT      # 11.0
_HI = _ALT_MAX - _VSPAN / 2.0         # 74.0


def test_expected_bounds():
    assert _LO == 11.0
    assert _HI == 74.0


@pytest.mark.parametrize("value,expected", [
    (-100.0, _LO),
    (0.0,     _LO),
    (11.0,    11.0),
    (40.0,    40.0),
    (74.0,    74.0),
    (100.0,   _HI),
])
def test_clamp(value, expected):
    assert clamp_alt_center(value, _VSPAN, _ALT_MAX) == expected


# --- widget smoke (requires QApplication fixture from conftest) ---


def test_widget_initial_alt_center(qapp):
    w = HorizonSkyWidget()
    assert w.alt_center == _LO


def test_widget_set_aim_updates_both_centers(qapp):
    w = HorizonSkyWidget()
    w.set_aim(90.0, 40.0)
    assert w.az_center == 90.0
    assert w.alt_center == 40.0


def test_widget_set_aim_clamps_low(qapp):
    w = HorizonSkyWidget()
    w.set_aim(0.0, -100.0)
    assert w.alt_center == _LO


def test_widget_set_aim_clamps_high(qapp):
    w = HorizonSkyWidget()
    w.set_aim(0.0, 200.0)
    assert w.alt_center == _HI
