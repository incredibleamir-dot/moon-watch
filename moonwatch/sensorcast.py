"""SensorCast WebSocket phone-link protocol (framework-free helpers).

SensorCast (https://sensorcast.app) broadcasts phone sensor frames over a
Socket.IO WebSocket API:

    wss://api.sensorcast.app   /socket.io/   namespace /stream/<username>

After connecting, a subscriber must emit ``role`` == ``"subscriber"`` within
5 seconds and keep sending a ``heartbeat`` event every ~20 s.

This module holds the pure parsing / vector helpers shared by the desktop link
(``phone.py``) and the command-line capture tool (``tools/sensorcast_capture.py``)
so the wire format is defined exactly once.  It contains no Qt or network code.
"""

import json
import math
import time

SERVER = "https://api.sensorcast.app"

# Device-frame pointing vectors.  Android device frame: +X right, +Y top
# edge, +Z out of the screen toward the user.
AIM_AXES = {
    "back": (0.0, 0.0, -1.0),   # back camera (-Z): photograph-the-sky pose
    "top": (0.0, 1.0, 0.0),     # top edge (+Y): laser-pointer pose
}
DEFAULT_AIM_AXIS = "top"


def _aim_vector(axis):
    if isinstance(axis, (list, tuple)) and len(axis) == 3:
        try:
            vx, vy, vz = (float(axis[0]), float(axis[1]), float(axis[2]))
        except (TypeError, ValueError):
            return AIM_AXES["back"]
        n = math.sqrt(vx * vx + vy * vy + vz * vz)
        if n < 1e-9:
            return AIM_AXES["back"]
        return (vx / n, vy / n, vz / n)
    return AIM_AXES.get(str(axis or "").lower(), AIM_AXES[DEFAULT_AIM_AXIS])


def vec_to_aim(ex, ey, ez):
    """(az, alt) for a world-frame (east, north, up) direction."""
    try:
        ex, ey, ez = float(ex), float(ey), float(ez)
    except (TypeError, ValueError):
        return 0.0, -90.0
    az = (math.degrees(math.atan2(ex, ey)) + 360.0) % 360.0
    alt = math.degrees(math.asin(max(-1.0, min(1.0, ez))))
    return az, alt


def q_to_aim(qx, qy, qz, qw=-1.0, axis="back"):
    """(az, alt) the phone points at, from the Android rotation-vector
    quaternion (device -> world in east-north-up).

    ``axis`` selects the device-frame pointer: ``"back"`` (0,0,-1, the
    back camera) or ``"top"`` (0,1,0, the top edge, laser-pointer pose).
    Defaults to ``"back"`` for backward compatibility.
    """
    try:
        qx = float(qx)
        qy = float(qy)
        qz = float(qz)
        qw_f = None if qw is None else float(qw)
    except (TypeError, ValueError):
        return 0.0, -90.0
    if (qw_f is None or qw_f == -1.0 or math.isnan(qw_f)
            or abs(qw_f) > 1.0 + 1e-6):
        qw_f = math.sqrt(max(0.0, 1.0 - (qx * qx + qy * qy + qz * qz)))
    qw = qw_f
    vx, vy, vz = _aim_vector(axis)
    tx = 2.0 * (qy * vz - qz * vy)
    ty = 2.0 * (qz * vx - qx * vz)
    tz = 2.0 * (qx * vy - qy * vx)
    ox = vx + qw * tx + (qy * tz - qz * ty)        # world: east
    oy = vy + qw * ty + (qz * tx - qx * tz)        # world: north
    oz = vz + qw * tz + (qx * ty - qy * tx)        # world: up
    return vec_to_aim(ox, oy, oz)


def mag_strength(mx, my, mz):
    """Total magnetic-field strength in the sensor's native unit (uT)."""
    try:
        return math.sqrt(float(mx) * float(mx) + float(my) * float(my)
                         + float(mz) * float(mz))
    except (TypeError, ValueError):
        return 0.0


def accel_mag_to_aim(ax, ay, az, mx, my, mz, axis="top"):
    """(az, alt) from accelerometer + magnetic-field vectors.

    Tilt-compensated compass: world Up in device coords is the normalized
    accelerometer ``(ax,ay,az)``; East is ``M x Up``; North is ``Up x East``.
    The chosen device ``axis`` is then dotted with those world axes.
    Returns ``(None, None)`` when the geometry is degenerate (free-fall or
    field parallel to gravity).
    """
    try:
        ax, ay, az = float(ax), float(ay), float(az)
        mx, my, mz = float(mx), float(my), float(mz)
    except (TypeError, ValueError):
        return None, None
    na = math.sqrt(ax * ax + ay * ay + az * az)
    if na < 1e-6:
        return None, None
    ux, uy, uz = ax / na, ay / na, az / na       # world Up in device coords
    # East = M x Up
    ex, ey, ez = (my * uz - mz * uy, mz * ux - mx * uz, mx * uy - my * ux)
    ne = math.sqrt(ex * ex + ey * ey + ez * ez)
    if ne < 1e-6:
        return None, None
    ex, ey, ez = ex / ne, ey / ne, ez / ne
    # North = Up x East
    nx, ny, nz = (uy * ez - uz * ey, uz * ex - ux * ez, ux * ey - uy * ex)
    vx, vy, vz = _aim_vector(axis)
    # world components of the pointer = dot(pointer, world-axis-in-device)
    e = vx * ex + vy * ey + vz * ez
    n = vx * nx + vy * ny + vz * nz
    u = vx * ux + vy * uy + vz * uz
    return vec_to_aim(e, n, u)


def parse_frame(raw):
    """Best-effort parse of any SensorCast frame.

    Returns {"sensor":.., "type":.., "timestamp":.., "values":{..}}.
    """
    if isinstance(raw, dict):
        return raw

    s = str(raw).strip()

    if s.startswith("{"):
        try:
            return json.loads(s)
        except json.JSONDecodeError:
            pass

    # CSV format: "ts,sensor,f1,f2,...,v1,v2,..." (also tolerates a
    # legacy leading comma).  Guarded to not swallow JSON ("{...}") or
    # COMPACT (";") frames handled below.
    if "," in s and ";" not in s and not s.startswith("{"):
        parts = [p.strip() for p in s.split(",")]
        # drop a single leading empty field from a leading comma
        if parts and parts[0] == "":
            parts = parts[1:]
        if len(parts) >= 4:
            try:
                ts = int(float(parts[0]))
                sensor = parts[1].strip()
                n = len(parts) - 2
                if n >= 2 and n % 2 == 0 and sensor:
                    half = n // 2
                    fields = [f.strip() for f in parts[2: 2 + half]]
                    values = [float(v) for v in parts[2 + half:]]
                    if fields and len(fields) == len(values):
                        return {"sensor": sensor, "type": 0,
                                "timestamp": ts,
                                "values": dict(zip(fields, values))}
            except (ValueError, IndexError):
                pass

    if ";" in s:                                        # COMPACT/TIMESTAMP
        segs = s.split(";")
        try:
            if len(segs) == 3 and segs[0].strip().isdigit() \
                    and ":" in segs[2]:
                # "ts;sensor;f1,f2:v1,v2"
                ts = int(segs[0].strip())
                sensor = segs[1].strip()
                fields_str, vals_str = segs[2].split(":", 1)
                fields = [f.strip() for f in fields_str.split(",")
                          if f.strip()]
                values = [float(v) for v in vals_str.split(",")]
                if sensor and fields and len(fields) == len(values):
                    return {"sensor": sensor, "type": 0,
                            "timestamp": ts,
                            "values": dict(zip(fields, values))}
            elif len(segs) == 2 and ":" in segs[1]:
                # "sensor;f1,f2:v1,v2" (no timestamp)
                left = segs[0].strip()
                fields_str, vals_str = segs[1].split(":", 1)
                fields = [f.strip() for f in fields_str.split(",")
                          if f.strip()]
                values = [float(v) for v in vals_str.split(",")]
                if fields and len(fields) == len(values):
                    ts = (int(left) if left.isdigit()
                          else int(time.time() * 1000))
                    sensor = left if len(fields) > 1 else fields[0]
                    return {"sensor": sensor, "type": 0,
                            "timestamp": ts,
                            "values": dict(zip(fields, values))}
        except (ValueError, IndexError):
            pass

    return {"sensor": "unknown", "type": -1,
            "timestamp": int(time.time() * 1000), "values": {}, "raw": s}


def wrap_az_delta(delta):
    """Wrap an azimuth difference to (-180, 180]."""
    try:
        d = float(delta) % 360.0
    except (TypeError, ValueError):
        return 0.0
    if d > 180.0:
        d -= 360.0
    return d


def calibration_from_aim(phone_az, phone_alt, target_az, target_alt,
                         north_offset=0.0):
    """Offset that aligns a raw phone aim with a known target.

    ``phone_az/phone_alt`` is the raw :func:`q_to_aim` output,
    ``target_az/target_alt`` the true body (or dragged view-centre)
    position.  Returns ``(az_offset, alt_offset)`` to be added *after*
    ``north_offset`` (az wrapped to -180..180, alt clamped to -30..30).
    """
    try:
        base_az = (float(phone_az) + float(north_offset)) % 360.0
        az_off = wrap_az_delta(float(target_az) - base_az)
        alt_off = float(target_alt) - float(phone_alt)
    except (TypeError, ValueError):
        return 0.0, 0.0
    alt_off = max(-30.0, min(30.0, alt_off))
    return az_off, alt_off


def apply_calibration(az, alt, north_offset=0.0, cal_az=0.0, cal_alt=0.0):
    """Apply north + calibration offsets to a raw phone aim."""
    try:
        out_az = (float(az) + float(north_offset) + float(cal_az)) % 360.0
        out_alt = float(alt) + float(cal_alt)
    except (TypeError, ValueError):
        return az, alt
    return out_az, out_alt