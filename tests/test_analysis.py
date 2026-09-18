"""Smoke checks for the analysis engines (uses the real data/Final.csv)."""

import analysis


def test_condition_analysis_structure():
    c = analysis.condition_analysis()
    assert c["kind"] == "cond"
    assert len(c["points"]) > 100
    pos, neg = c["error_rates"]["Whole"]
    assert 0.0 <= pos <= 100.0
    assert 0.0 <= neg <= 100.0


def test_equation_analysis_curve_length():
    e = analysis.equation_analysis()
    assert e["kind"] == "equa"
    assert len(e["curve"]) == 160
    pos, neg = e["error_rates"]["Whole"]
    assert 0.0 <= pos <= 100.0
    assert 0.0 <= neg <= 100.0


def test_threshold_analysis_golden_counts():
    t = analysis.threshold_analysis()
    assert t["kind"] == "thres"
    assert t["series"]["Naked Eye"]["count"] == 3236
    assert t["series"]["Optical Aided"]["count"] == 925
