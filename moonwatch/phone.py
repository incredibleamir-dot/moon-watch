"""Phone link: streams the Android phone's sensors into the app via SensorCast.

The phone runs the SensorCast Android app (https://sensorcast.app) and
broadcasts sensor frames (Rotation Vector + Magnetic Field + Accelerometer
fallback, optional GPS).  This desktop class connects to the SensorCast
WebSocket API as a subscriber and re-emits the frames as Qt signals that
LivePage consumes to drive the horizon sky map and, optionally, the observer
location.  The aim axis is selectable: "top" (+Y, laser-pointer pose,
default) or "back" (-Z, back-camera photograph pose).

    wss://api.sensorcast.app   /socket.io/   namespace /stream/<username>

After connecting, the subscriber must emit ``role`` == ``"subscriber"`` within
5 seconds and keep sending a ``heartbeat`` event every ~20 s.

Frame formats handled: JSON, CSV, COMPACT, TIMESTAMP (see sensorcast.app/docs).
The parsing / quaternion helpers themselves live in ``moonwatch.sensorcast`` so
the desktop link and the capture tool share one definition.
"""

import threading
import time

from PySide6.QtCore import QObject, Signal

from .sensorcast import (SERVER, parse_frame, q_to_aim, accel_mag_to_aim,
                           mag_strength, DEFAULT_AIM_AXIS)


class PhoneLink(QObject):
    """Subscribe to a SensorCast stream and re-emit Qt signals.

    The socket client runs in a daemon thread; signals are queued to the GUI
    thread automatically by Qt.
    """

    orient = Signal(float, float, float, float, float, float)
    #                                  qx    qy    qz    qw    az   alt
    loc = Signal(float, float, float)                     # lat lon acc-m
    mag = Signal(float, float, float, float)              # mx my mz |B| uT
    status = Signal(bool, str)                            # connected, username
    error = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._thread = None
        self._sio = None
        self._stop = threading.Event()
        self._connected = False
        self._seen_plain_rv = False
        self._seen_game_rv = False
        self._aim_axis = DEFAULT_AIM_AXIS
        self._accel = None          # (ax, ay, az) smoothed
        self._mag = None            # (mx, my, mz) smoothed
        self._gen = 0
        self.username = ""

    def set_aim_axis(self, axis):
        """Select the device pointer: "top" (+Y) or "back" (-Z)."""
        a = str(axis or "").lower()
        self._aim_axis = a if a in ("top", "back") else DEFAULT_AIM_AXIS

    def aim_axis(self):
        return self._aim_axis

    # ------------------------------------------------------------- lifecycle
    def is_connected(self):
        return self._connected

    def connect_stream(self, username):
        self.disconnect()
        username = (username or "").strip()
        if not username:
            self.error.emit("Enter a SensorCast username first")
            return
        self.username = username
        self._seen_plain_rv = False
        self._seen_game_rv = False
        self._accel = None
        self._mag = None
        self._gen += 1
        gen = self._gen
        self._stop.clear()
        self._thread = threading.Thread(target=self._run,
                                        args=(username, gen),
                                        daemon=True)
        self._thread.start()

    def disconnect(self):
        self._gen += 1
        self._stop.set()
        sio = self._sio
        self._sio = None
        if sio is not None:
            try:
                sio.disconnect()
            except Exception:
                pass
        thread, self._thread = self._thread, None
        if thread is not None and thread is not threading.current_thread():
            # Never block the GUI event loop on a wedged socket connect.
            thread.join(timeout=0.1)
        was = self._connected
        self._connected = False
        if was:
            self.status.emit(False, self.username)

    # --------------------------------------------------------------- socket
    def _run(self, username, gen):
        try:
            import socketio
        except ImportError:
            if gen == self._gen:
                self.error.emit('Missing dependency: run  '
                                'pip install "python-socketio[client]"')
                self.status.emit(False, username)
            return
        try:
            self._run_client(socketio, username, gen)
        except Exception as exc:
            if gen == self._gen and not self._stop.is_set():
                self.error.emit("SensorCast connection failed: %s" % exc)
                self.status.emit(False, username)
        finally:
            if gen == self._gen:
                self._sio = None

    def _run_client(self, socketio, username, gen):
        ns = "/stream/%s" % username
        sio = socketio.Client()
        self._sio = sio

        @sio.event(namespace=ns)
        def connect():
            sio.emit("role", "subscriber", namespace=ns)

        @sio.on("connected", namespace=ns)
        def on_connected(data):
            self._connected = True
            self.status.emit(True, username)

        @sio.on("frame", namespace=ns)
        def on_frame(data):
            self._handle_frame(data)

        @sio.on("publisher_disconnected", namespace=ns)
        def on_pub_gone():
            if not self._stop.is_set():
                self.error.emit("Publisher disconnected - stream ended")
                self.status.emit(False, username)

        @sio.on("connect_error", namespace=ns)
        def on_conn_error(e):
            if not self._stop.is_set():
                self.error.emit("Connection error: %s" % e)
                self.status.emit(False, username)

        @sio.on("auth_error", namespace=ns)
        def on_auth_error(e):
            if not self._stop.is_set():
                self.error.emit("Auth error: %s" % e)
                self.status.emit(False, username)

        @sio.event(namespace=ns)
        def disconnect():
            if self._connected:
                self._connected = False
                self.status.emit(False, username)

        def heartbeat():
            while gen == self._gen and not self._stop.is_set():
                time.sleep(20)
                if gen != self._gen or self._sio is not sio:
                    break
                if sio.connected:
                    try:
                        sio.emit("heartbeat", namespace=ns)
                    except Exception:
                        pass

        threading.Thread(target=heartbeat, daemon=True).start()

        sio.connect(SERVER, namespaces=[ns], socketio_path="/socket.io/")
        try:
            while gen == self._gen and not self._stop.is_set() \
                    and sio.connected:
                sio.sleep(0.3)
        finally:
            try:
                sio.disconnect()
            except Exception:
                pass
            if gen == self._gen:
                self._connected = False

    # --------------------------------------------------------------- frames
    def _handle_frame(self, data):
        parsed = parse_frame(data)
        sensor = parsed.get("sensor") or ""
        values = parsed.get("values") or {}
        if not values:
            return
        s_low = str(sensor).lower()

        # --- GPS fix -----------------------------------------------------
        if "gps" in s_low:
            try:
                lat = float(values.get("latitude", values.get("lat")))
                lon = float(values.get("longitude", values.get("lon")))
                acc = float(values.get("accuracy", values.get("acc", -1.0)))
            except (TypeError, ValueError):
                return
            self.loc.emit(lat, lon, acc)
            return

        # --- rotation vector quaternion (absolute heading) ---------------
        if "rotation vector" in s_low:
            try:
                qx = float(values.get("x", 0.0))
                qy = float(values.get("y", 0.0))
                qz = float(values.get("z", 0.0))
                qw = float(values.get("w", -1.0))
            except (TypeError, ValueError):
                return
            if "game" not in s_low:
                self._seen_plain_rv = True
            else:
                self._seen_game_rv = True
                if self._seen_plain_rv:
                    return                  # prefer the compass RV sensor
            az, alt = q_to_aim(qx, qy, qz, qw, axis=self._aim_axis)
            self.orient.emit(qx, qy, qz, qw, az, alt)
            return

        # --- accelerometer (kept for the mag+accel compass fallback) -----
        if "accel" in s_low:
            xyz = _xyz(values)
            if xyz is None:
                return
            self._accel = _smooth(self._accel, xyz)
            self._maybe_emit_accel_mag()
            return

        # --- magnetic field (health display + compass fallback) ----------
        if "magnet" in s_low:
            xyz = _xyz(values)
            if xyz is None:
                return
            self._mag = _smooth(self._mag, xyz)
            mx, my, mz = self._mag
            self.mag.emit(mx, my, mz, mag_strength(mx, my, mz))
            self._maybe_emit_accel_mag()
            return

        # --- euler / legacy orientation (fallback only) ------------------
        if "orientation" in s_low and not self._seen_plain_rv \
                and not self._seen_game_rv and self._accel is None:
            try:
                yaw = float(values.get("yaw", values.get("z",
                          values.get("azimuth", values.get("x")))))
                pitch = float(values.get("pitch", values.get("y")))
            except (TypeError, ValueError):
                return
            self.orient.emit(0.0, 0.0, 0.0, 1.0,
                             (float(yaw) + 180.0) % 360.0, -float(pitch))

    def _maybe_emit_accel_mag(self):
        # Tilt-compensated compass fallback: only while no rotation-vector
        # (plain or game) has ever been seen, so a high-rate RV stream is
        # never fought by the slower/noisier accel+mag pair.  Stand on your
        # origin, top edge toward the sky: turning your body yaws the view,
        # tilting the top up/down pitches it.
        if self._seen_plain_rv or self._seen_game_rv:
            return
        if self._accel is None or self._mag is None:
            return
        az, alt = accel_mag_to_aim(self._accel[0], self._accel[1],
                                   self._accel[2], self._mag[0],
                                   self._mag[1], self._mag[2],
                                   axis=self._aim_axis)
        if az is None:
            return
        self.orient.emit(0.0, 0.0, 0.0, 1.0, az, alt)


def _xyz(values):
    """(x, y, z) floats from a sensor values dict with varying key names."""
    try:
        if "x" in values and "y" in values and "z" in values:
            return (float(values["x"]), float(values["y"]),
                    float(values["z"]))
        for keys in (("ax", "ay", "az"), ("X", "Y", "Z"),
                     ("0", "1", "2")):
            if all(k in values for k in keys):
                return (float(values[keys[0]]), float(values[keys[1]]),
                        float(values[keys[2]]))
        nums = [float(v) for v in values.values()]
        if len(nums) >= 3:
            return (nums[0], nums[1], nums[2])
    except (TypeError, ValueError):
        return None
    return None


def _smooth(prev, new, alpha=0.35):
    if prev is None:
        return new
    try:
        return tuple(p + alpha * (n - p) for p, n in zip(prev, new))
    except (TypeError, ValueError):
        return new