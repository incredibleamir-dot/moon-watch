"""Offline unit tests for the internal helpers in verification.py."""

from datetime import datetime

import verification as v

# --- _parse_rows (HORIZONS text table) ------------------------------------

CANNED_TABLE = """\
$$SOE
2025-Mar-01 12:30  *     12.0
 2025-Mar-01 12:35  *      8.0
 2025-Mar-01 12:40  *      6.0
$$EOE
"""


def test_parse_rows_canned_table():
    rows = v._parse_rows(CANNED_TABLE)
    assert len(rows) == 3
    t, vals = rows[1]
    assert t == datetime(2025, 3, 1, 12, 35)
    assert vals == [8.0]


def test_parse_rows_rejects_missing_bounds():
    bad = "no $$SOE or $$EOE markers"
    try:
        v._parse_rows(bad)
        assert False, "expected ValueError"
    except ValueError:
        pass


# --- _interp_set / _interp_value -------------------------------------------


def test_interp_set_downward_crossing():
    times = [datetime(2025, 1, 1, i) for i in range(4)]
    vals = [12.0, 10.0, 7.0, 5.0]
    t = v._interp_set(times, vals, 8.0)
    assert t is not None
    # crosses between t=1 (10.0) and t=2 (7.0), f = (10-8)/(10-7) = 2/3
    assert t.hour == 1 and t.minute == 40


def test_interp_value_linear():
    times = [datetime(2025, 1, 1, 0), datetime(2025, 1, 1, 2)]
    vals = [0.0, 10.0]
    res = v._interp_value(times, vals, datetime(2025, 1, 1, 1))
    assert abs(res - 5.0) < 1e-9


def test_interp_value_out_of_range_returns_none():
    times = [datetime(2025, 1, 1, 0), datetime(2025, 1, 1, 2)]
    vals = [0.0, 10.0]
    res = v._interp_value(times, vals, datetime(2025, 1, 1, 5))
    assert res is None


# --- constants -------------------------------------------------------------

def test_tolerance_dict_exists():
    assert "sunset" in v.TOL and v.TOL["sunset"] == 8.0
