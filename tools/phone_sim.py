#!/usr/bin/env python3
"""Moon Watch - desktop phone simulator (legacy UDP).

A standalone tool that pretends to be the phone: an on-screen cube you drag
with the mouse rotates like a phone, and the resulting orientation + a fixed
Ludhiana location are streamed over UDP with the same protocol the original
Termux link (``phone-app/termux/aim.py``) used.

**Legacy note** - the desktop app now links to SensorCast over WebSocket;
this simulator is retained for offline testing of the quaternion / aim math
but is **not** connected to the current desktop listener.

    python tools/phone_sim.py                  # -> 192.168.200.198:5555
    python tools/phone_sim.py --host 10.0.0.8 --port 5555

Drag the cube:  left/right = azimuth, up/down = altitude (drag right to aim
east).  The orange face is the phone's back camera.  Watch the depression of
the horizon sky map follow the cube.  The cube starts level, aiming at the
horizon; tilting up/down covers the sky above and below it.
"""

import argparse
import json
import math
import socket
import time

from PySide6.QtCore import QPointF, Qt, QTimer
from PySide6.QtGui import QColor, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import (QApplication, QHBoxLayout, QLabel, QPushButton,
                               QVBoxLayout, QWidget)

DEFAULT_HOST = "192.168.200.198"
DEFAULT_PORT = 5555
LUDHIANA = (30.900965, 75.857275, 262.0)
PX_DEG = 0.25                 # degrees of rotation per pixel of drag
PITCH_LIMIT = 80.0            # keep far from the dead straight-up singularity

# --------------------------------------------------------------------------- #
# quaternion helpers (scalar-last, world = east-north-up, like the Android     #
# rotation vector used by aim.py)                                              #

def quat_mult(a, b):
    aw, ax, ay, az = a
    bw, bx, by, bz = b
    return (aw * bw - ax * bx - ay * by - az * bz,
            aw * bx + ax * bw + ay * bz - az * by,
            aw * by - ax * bz + ay * bw + az * bx,
            aw * bz + ax * by - ay * bx + az * bw)


def quat_conj(q):
    return (q[0], -q[1], -q[2], -q[3])


def quat_norm(q):
    n = math.sqrt(sum(v * v for v in q))
    return tuple(v / n for v in q)


def rotate(q, v):
    """Rotate 3-vector v by unit quaternion q (scalar-last)."""
    r = quat_mult(quat_mult(q, (0.0,) + tuple(v)), quat_conj(q))
    return r[1], r[2], r[3]


def q_to_aim(q, axis="back"):
    """(az, alt) degrees that the phone points at ("back" -Z or "top" +Y)."""
    _, qx, qy, qz = q
    qw = q[0]
    if qw in (None, -1.0):
        qw = math.sqrt(max(0.0, 1.0 - (qx * qx + qy * qy + qz * qz)))
    if str(axis or "").lower() == "top":
        vx, vy, vz = 0.0, 1.0, 0.0
    else:
        vx, vy, vz = 0.0, 0.0, -1.0
    tx = 2.0 * (qy * vz - qz * vy)
    ty = 2.0 * (qz * vx - qx * vz)
    tz = 2.0 * (qx * vy - qy * vx)
    ox = vx + qw * tx + (qy * tz - qz * ty)
    oy = vy + qw * ty + (qz * tx - qx * tz)
    oz = vz + qw * tz + (qx * ty - qy * tx)
    az = (math.degrees(math.atan2(ox, oy)) + 360.0) % 360.0
    alt = math.degrees(math.asin(max(-1.0, min(1.0, oz))))
    return az, alt


# --------------------------------------------------------------------------- #
# cube mesh (device frame: +x right, +y top of screen, +z out of the screen)  #
CORNERS = [
    (-1, -1, -1), (1, -1, -1), (1, 1, -1), (-1, 1, -1),
    (-1, -1, 1), (1, -1, 1), (1, 1, 1), (-1, 1, 1),
]
FACES = [
    (0, 1, 2, 3),        # -z : back of the phone (camera)
    (4, 5, 6, 7),        # +z : screen
    (0, 1, 5, 4),        # -y : bottom edge
    (2, 3, 7, 6),        # +y : top edge
    (1, 2, 6, 5),        # +x : right edge
    (0, 3, 7, 4),        # -x : left edge
]
FACE_COLORS = [
    QColor(255, 150, 20),   # back / camera
    QColor(40, 60, 90),     # screen
    QColor(70, 110, 160),   # bottom
    QColor(180, 90, 50),    # top
    QColor(90, 150, 90),    # right
    QColor(140, 120, 190),  # left
]
NORMALS = [(0, 0, -1), (0, 0, 1), (0, -1, 0), (0, 1, 0),
           (1, 0, 0), (-1, 0, 0)]
LIGHT = (0.45, -0.72, 0.53)      # shading light direction


class PhoneSim(QWidget):
    """Drag-to-rotate cube that streams its pose to the Moon Watch desktop."""

    def __init__(self, host=DEFAULT_HOST, port=DEFAULT_PORT, parent=None):
        super().__init__(parent)
        self.host = host
        self.port = int(port)
        self.yaw = 0.0
        self.pitch = 0.0
        self._drag = None

        self._sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self._sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
        self._target = (host, int(port))

        self.setWindowTitle("Phone simulator -> %s:%d" % self._target)
        self.resize(420, 380)

        self.lbl_aim = QLabel("aim  az 000.0\u00b0  alt +000.0\u00b0")
        self.lbl_aim.setStyleSheet(
            "font-family: Consolas; font-size: 14pt; color: #20242a;")
        self.lbl_status = QLabel("-> %s:%d  (drag the cube)" % self._target)
        self.lbl_status.setStyleSheet("color: #5a6068;")
        btn_reset = QPushButton("Reset")
        btn_reset.setMaximumWidth(90)
        btn_reset.clicked.connect(self.reset)

        lay = QVBoxLayout(self)
        lay.addWidget(self.lbl_aim, 0, Qt.AlignCenter)
        top = QHBoxLayout()
        top.addWidget(self.lbl_status, 1)
        top.addWidget(btn_reset, 0)
        lay.addLayout(top)

        self._timer = QTimer(self)
        self._timer.setInterval(40)          # ~25 Hz stream
        self._timer.timeout.connect(self._send_once)

        self._send_location()

    # ----------------------------------------------------------- drag input
    def mousePressEvent(self, e):
        self._drag = self._pos(e)

    def mouseMoveEvent(self, e):
        pos = self._pos(e)
        if self._drag is not None:
            self.step(pos.x() - self._drag.x(), pos.y() - self._drag.y())
            self._drag = pos

    def mouseReleaseEvent(self, e):
        self._drag = None

    @staticmethod
    def _pos(e):
        pos = getattr(e, "position", None)
        return pos() if pos is not None else QPointF(e.x(), e.y())

    def step(self, dx, dy):
        """Apply a mouse drag: right = +az, up = +alt."""
        self.yaw -= dx * PX_DEG
        self.pitch -= dy * PX_DEG
        self.pitch = max(-PITCH_LIMIT, min(PITCH_LIMIT, self.pitch))
        self.update_readout()

    def reset(self):
        self.yaw = 0.0
        self.pitch = 0.0
        self.update_readout()

    # -------------------------------------------------------------- state
    def quaternion(self):
        """Unit device->world quaternion, scalar-last like (w, x, y, z).

        A +90 degree offset puts the level pose at the horizon (alt 0,
        pointing north) instead of flat-on-the-table (alt -90), so tilting
        up/down sweeps across the sky the desktop map can show."""
        hy, sy = math.cos(math.radians(self.yaw) / 2.0), \
            math.sin(math.radians(self.yaw) / 2.0)
        hp, sp = math.cos(math.radians(self.pitch + 90.0) / 2.0), \
            math.sin(math.radians(self.pitch + 90.0) / 2.0)
        rz = (hy, 0.0, 0.0, sy)              # yaw about world z
        rx = (hp, sp, 0.0, 0.0)              # pitch about world x
        return quat_norm(quat_mult(rz, rx))

    def update_readout(self):
        az, alt = q_to_aim(self.quaternion())
        self.lbl_aim.setText("aim  az %06.1f\u00b0  alt %+06.1f\u00b0"
                             % (az, alt))
        self.update()

    # ------------------------------------------------------------- outflow
    def start(self):
        self._timer.start()
        self.update_readout()

    def stop(self):
        self._timer.stop()

    def _send_location(self):
        lat, lon, alt = LUDHIANA
        self._send({"type": "loc", "t": time.time(), "lat": lat,
                    "lon": lon, "alt": alt, "acc": 0.0})

    def _send_once(self):
        q = self.quaternion()
        qx, qy, qz, qw = q[1], q[2], q[3], q[0]
        az, alt = q_to_aim(q)
        now = time.time()
        self._send({"type": "orient", "t": now, "qx": qx, "qy": qy,
                    "qz": qz, "qw": qw, "az": round(az, 1),
                    "alt": round(alt, 1)})
        self._send({"type": "ping", "t": now})
        self.lbl_status.setText("-> %s:%d  az %06.1f\u00b0 alt %+06.1f\u00b0"
                                % (self._target + (az, alt)))

    def _send(self, obj):
        try:
            self._sock.sendto(json.dumps(obj).encode("utf-8"), self._target)
        except OSError:
            pass

    # -------------------------------------------------------------- drawing
    def paintEvent(self, ev):
        p = QPainter(self)
        p.fillRect(self.rect(), QColor(242, 245, 249))
        p.setRenderHint(QPainter.Antialiasing, True)

        cx = self.width() / 2.0
        cy = self.height() / 2.0
        side = min(self.width(), self.height()) * 0.36
        s = side / 3.0                          # world units -> px
        q = self.quaternion()

        def proj(v):
            x, y, z = v
            return cx + x * s, cy - z * s        # camera looks along +y

        seen = []
        for fi, face in enumerate(FACES):
            world = [rotate(q, CORNERS[i]) for i in face]
            n = rotate(q, NORMALS[fi])
            bright = max(0.12, n[0] * LIGHT[0] + n[1] * LIGHT[1]
                         + n[2] * LIGHT[2])
            base = FACE_COLORS[fi]
            col = QColor(int(base.red() * bright), int(base.green() * bright),
                         int(base.blue() * bright))
            depth = sum(c[1] for c in world)     # +y is the camera axis
            seen.append((depth, col, world))

        for depth, col, pts in sorted(seen, key=lambda f: f[0]):
            path = QPainterPath()
            x0, y0 = proj(pts[0])
            path.moveTo(x0, y0)
            for v in pts[1:]:
                x, y = proj(v)
                path.lineTo(x, y)
            path.closeSubpath()
            p.setBrush(col)
            p.setPen(QPen(QColor(0, 0, 0, 90), 1))
            p.drawPath(path)
        p.end()


def main():
    ap = argparse.ArgumentParser(description="Phone simulator for Moon Watch")
    ap.add_argument("--host", default=DEFAULT_HOST,
                    help="desktop IP (default %s)" % DEFAULT_HOST)
    ap.add_argument("--port", type=int, default=DEFAULT_PORT,
                    help="UDP port (default %d)" % DEFAULT_PORT)
    args = ap.parse_args()

    app = QApplication([])
    sim = PhoneSim(args.host, args.port)
    sim.show()
    sim.start()
    app.exec()


if __name__ == "__main__":
    main()