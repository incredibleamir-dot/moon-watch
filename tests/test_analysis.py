"""Tests for analysis.py - the three analysis chart data builders."""

import analysis


def _methods(res):
    return set(res["error_rates"])


def test_condition_analysis_shape():
    res = analysis.condition_analysis()
    assert res["kind"] == "cond"
    assert res["points"]
    assert res["limitx"] > 0 and res["limity"] > 0
    assert res["conditionx"] > 0 and res["conditiony"] > 0
    assert {"Naked Eye", "Optical Aided"} <= _methods(res)
    for label, (pos, neg) in res["error_rates"].items():
        assert 0.0 <= pos <= 100.0
        assert 0.0 <= neg <= 100.0


def test_equation_analysis_shape():
    res = analysis.equation_analysis()
    assert res["kind"] == "equa"
    assert res["points"]
    assert len(res["curve"]) > 10
    assert res["xlabel"] and res["ylabel"]
    assert {"Naked Eye", "Optical Aided"} <= _methods(res)


def test_threshold_analysis_every_parameter():
    for param in ("ArcL", "MAlt", "ArcV", "W", "LT", "MA"):
        res = analysis.threshold_analysis(param)
        assert res["kind"] == "thres"
        assert res["xlabel"] == param
        assert set(res["series"]) == {"Naked Eye", "Optical Aided"}
        for s in res["series"].values():
            assert s["count"] >= 0
            assert s["min"] <= s["median"] <= s["max"]
        assert res["minima"]  # non-empty


def test_condition_points_have_verdict_column():
    res = analysis.condition_analysis()
    vis = {p[2] for p in res["points"]}
    assert vis <= {"V", "I"}
    assert "V" in vis and "I" in vis
