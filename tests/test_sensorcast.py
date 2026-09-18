"""Unit tests for the SensorCast protocol helpers."""

import json
import time

from moonwatch.sensorcast import SERVER, parse_frame, q_to_aim


def test_server_constant():
    assert SERVER == "https://api.sensorcast.app"


# ------------------------------------------------------------------- parse_frame


def test_dict_passthrough():
    d = {"sensor": "rv", "type": 0, "timestamp": 1, "values": {"x": 0.0}}
    assert parse_frame(d) is d


def test_json_string():
    s = json.dumps({"sensor": "gps", "type": 1, "timestamp": 2,
                    "values": {"lat": 1.0}})
    p = parse_frame(s)
    assert p["sensor"] == "gps" and p["values"]["lat"] == 1.0


def test_compact_with_timestamp():
    s = "98765;rotation vector;x,y,z,w:0.1,0.2,0.3,0.4"
    p = parse_frame(s)
    assert p["timestamp"] == 98765
    assert p["sensor"] == "rotation vector"
    assert len(p["values"]) == 4


def test_csv_format():
    s = "98765,rotation vector,x,y,z,w,0.1,0.2,0.3,0.4"
    p = parse_frame(s)
    assert p["timestamp"] == 98765
    assert p["sensor"] == "rotation vector"
    assert len(p["values"]) == 4


def test_compact_without_timestamp():
    s = "rotation vector;x,y:0.5,0.6"
    p = parse_frame(s)
    assert p["sensor"] == "rotation vector"
    assert p["values"]["x"] == 0.5
    # timestamp defaults to current ms; just check it's recent
    assert abs(p["timestamp"] - int(time.time() * 1000)) < 2000


def test_unknown_returns_empty_values_dict():
    p = parse_frame("garbage")
    assert p["type"] == -1
    assert p["values"] == {}
    assert "garbage" in p["raw"]


# ------------------------------------------------------------------- q_to_aim


def test_q_to_aim_identity_quat():
    az, alt = q_to_aim(0.0, 0.0, 0.0, 1.0)
    assert (round(az, 6), round(alt, 6)) == (0.0, -90.0)


def test_q_to_aim_level_phone():
    # +90° pitch from flat → back camera points along north horizon (alt 0°)
    az, alt = q_to_aim(0.70710678, 0.0, 0.0, 0.70710678)
    assert (round(az, 6), round(alt, 6)) == (0.0, 0.0)


def test_q_to_aim_default_qw_fallback():
    az, alt = q_to_aim(0.70710678, 0.0, 0.0)
    assert (round(az, 6), round(alt, 6)) == (0.0, 0.0)


def test_q_to_aim_yaw90():
    az, alt = q_to_aim(0.5, 0.5, 0.5, -0.5)
    assert (round(az, 1), round(alt, 1)) == (180.0, 0.0)
