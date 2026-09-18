#!/usr/bin/env python3
"""Moon Watch Link - Termux edition (no APK, no build needed).

Streams the phone's rotation-vector orientation + GPS to the desktop Moon
Watch workstation over UDP, using only the Python standard library plus the
Termux:API commands ``termux-sensor`` and ``termux-location``.

Usage:
    python aim.py                # auto-find the desktop; sends the built-in
                                 #   Ludhiana location (no GPS needed)
    python aim.py 192.168.1.10   # stream straight to that host
    python aim.py 192.168.1.10 5555
    python aim.py --gps          # try live GPS instead of the fixed location
    python aim.py --lat 28.61 --lon 77.20   # override to anywhere else
"""

import argparse
import json
import math
import socket
import subprocess
import sys
import threading
import time

PORT = 5555
MOVE_DEG = 0.00005            # min GPS movement that triggers a new "loc" event
SENSOR_DELAY_MS = 60          # termux-sensor -d: ~17 Hz from the rotation sensor
GPS_TIMEOUT = 60              # how long to wait for one GPS fix
DEFAULT_LOCATION = (30.900965, 75.857275, 262.0)   # Ludhiana, Punjab, India


def q_to_aim(qx, qy, qz, qw=-1.0, axis="back"):
    """(az, alt) the phone points at, from the Android rotation-vector
    quaternion (device -> world in east-north-up).  axis "back" (0,0,-1,
    default) or "top" (0,1,0, laser-pointer pose)."""
    if qw in (None, -1.0):
        qw = math.sqrt(max(0.0, 1.0 - (qx * qx + qy * qy + qz * qz)))
    if str(axis or "").lower() == "top":
        vx, vy, vz = 0.0, 1.0, 0.0                # device +Y (top edge)
    else:
        vx, vy, vz = 0.0, 0.0, -1.0              # device -Z (back camera)
    tx = 2.0 * (qy * vz - qz * vy)
    ty = 2.0 * (qz * vx - qx * vz)
    tz = 2.0 * (qx * vy - qy * vx)
    ox = vx + qw * tx + (qy * tz - qz * ty)        # world: east
    oy = vy + qw * ty + (qz * tx - qx * tz)        # world: north
    oz = vz + qw * tz + (qx * ty - qy * tx)        # world: up
    az = (math.degrees(math.atan2(ox, oy)) + 360.0) % 360.0
    alt = math.degrees(math.asin(max(-1.0, min(1.0, oz))))
    return az, alt


class Streamer(object):
    """Sends JSON packets to the desktop host; supports LAN discovery."""

    def __init__(self):
        self._sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self._sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
        self._target = None

    def set_target(self, ip, port=PORT):
        self._target = (ip, port)

    def send(self, obj):
        if self._target is None:
            return
        data = json.dumps(obj).encode("utf-8")
        try:
            self._sock.sendto(data, self._target)
        except OSError:
            pass


def local_ip():
    """Best guess of the phone's own LAN IPv4 address (or None)."""
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        try:
            s.connect(("8.8.8.8", 80))
            return s.getsockname()[0]
        finally:
            s.close()
    except OSError:
        return None


def subnet_broadcast(ip):
    """/24 subnet broadcast for an address (typical home Wi-Fi)."""
    if not ip:
        return None
    parts = ip.split(".")
    if len(parts) != 4:
        return None
    return ".".join(parts[:3] + ["255"])


def find_desktop(port=PORT, timeout=5.0):
    """Probe both the limited (255.255.255.255) and the /24 subnet broadcast
    a few times, collecting disc_reply packets.  Returns the desktop IP or
    None."""
    targets = ["255.255.255.255"]
    bc = subnet_broadcast(local_ip())
    if bc and bc not in targets:
        targets.append(bc)

    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
    sock.settimeout(0.4)
    found = set()
    deadline = time.time() + timeout
    while time.time() < deadline:
        for t in targets:
            try:
                sock.sendto(json.dumps({"type": "disc"}).encode("utf-8"),
                            (t, port))
            except OSError:
                pass
        while time.time() < deadline:
            try:
                data, addr = sock.recvfrom(2048)
            except socket.timeout:
                break
            try:
                msg = json.loads(data.decode("utf-8"))
            except (ValueError, UnicodeDecodeError):
                continue
            if msg.get("type") == "disc_reply":
                found.add(msg.get("ip") or addr[0])
    sock.close()
    return sorted(found)[0] if found else None


def events(proc):
    """Yield JSON objects as they appear on proc.stdout, tolerating partial
    documents split across reads and pretty-printed multi-line output."""
    decoder = json.JSONDecoder()
    buf = b""
    while True:
        chunk = proc.stdout.read(4096)
        if not chunk:
            break
        buf += chunk
        while True:
            text = buf.lstrip()
            if not text:
                break
            try:
                obj, end = decoder.raw_decode(text.decode("utf-8", "replace"))
            except ValueError:
                break                      # incomplete JSON, read more
            buf = text[end:].lstrip().encode("utf-8")
            yield obj


def best_rotation_sensor(names):
    """Pick which rotation-vector sensor to stream from.

    Prefer the compass-using "Rotation Vector" (absolute heading) over the
    "Game Rotation Vector" (gyro-only, drifts). Names vary per vendor, e.g.
    Samsung exposes 'Samsung Rotation Vector Sensor'."""
    if isinstance(names, dict):
        names = list(names.keys())
    plain = [n for n in names
             if "rotation vector" in n.lower() and "game" not in n.lower()]
    game = [n for n in names if "game rotation vector" in n.lower()]
    chosen = plain or game
    return [chosen[0]] if chosen else []


def sensor_probe():
    """Query termux-sensor -a for rotation-vector sensors.

    Returns (found_names_or_None, reason). found_names is a list of the
    rotation-vector sensors the device actually has; None means we could not
    get a clean sensor list and reason explains why."""
    try:
        out = subprocess.check_output(["termux-sensor", "-a"], timeout=30)
    except FileNotFoundError:
        return None, "termux-sensor is missing - run: bash setup.sh"
    except subprocess.TimeoutExpired:
        return None, ("termux-sensor -a timed out (30s). Open the Termux:API "
                      "app once and grant it the sensor + location "
                      "permissions in Android settings, then retry.")
    except subprocess.CalledProcessError as exc:
        return None, "termux-sensor -a exited %d" % exc.returncode
    text = out.decode("utf-8", "replace").strip()
    if not text:
        return None, "(termux-sensor -a printed nothing)"
    try:
        registry = json.loads(text)
    except ValueError:
        return None, text          # e.g. "Termux:API is not yet available..."
    return best_rotation_sensor(registry), None


def read_sensors(stream):
    found, why = sensor_probe()
    if found is None:
        if "not yet available" in (why or ""):
            sys.exit("\nTermux:API is 'not yet available' here.\n"
                     "This happens when Termux (or Termux:API) was installed "
                     "from Google Play -\nthe Play Store builds cannot talk to "
                     "the F-Droid API app (different signatures).\n\n"
                     "Fix: install BOTH apps from F-Droid (f-droid.org):\n"
                     "  1. uninstall the Play Store Termux + Termux:API\n"
                     "  2. F-Droid -> install Termux, then Termux:API\n"
                     "  3. pkg update -y && pkg install -y python termux-api\n"
                     "  4. python aim.py\n"
                     "\nRaw termux-sensor output was: %s" % why)
        sys.exit(why)
    if not found:
        sys.exit("no rotation-vector sensor found on this phone. "
                 "Run 'termux-sensor -a' to see what sensors Termux lists.")
    try:
        proc = subprocess.Popen(
            ["termux-sensor", "-s", ",".join(found),
             "-d", str(SENSOR_DELAY_MS)],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    except FileNotFoundError:
        sys.exit("termux-sensor not found - run: bash setup.sh")

    last = 0.0
    sent = 0
    for ev in events(proc):
        if ev is None:
            continue
        for samples in ev.values():
            if not isinstance(samples, list) or not samples:
                continue
            vals = samples[-1].get("values") or []
            if len(vals) < 3:
                continue
            qx, qy, qz = float(vals[0]), float(vals[1]), float(vals[2])
            qw = float(vals[3]) if len(vals) > 3 else -1.0
            az, alt = q_to_aim(qx, qy, qz, qw)
            now = time.time()
            if now - last < 0.05:            # cap at ~20 Hz
                continue
            last = now
            sent += 1
            stream.send({"type": "orient", "t": now, "qx": qx, "qy": qy,
                         "qz": qz, "qw": qw, "az": round(az, 1),
                         "alt": round(alt, 1)})
            stream.send({"type": "ping", "t": now})
            sys.stdout.write("\raim: az %03.0f deg  alt %02.0f deg  "
                             "[%d sent] " % (az, alt, sent))
            sys.stdout.flush()

    err = proc.stderr.read().decode("utf-8", "replace").strip()
    if sent == 0:
        print()
        print("no sensor data received - termux-sensor reported:")
        print(err or "(nothing)")
        print("check: Termux:API app installed? rotation-vector sensor present? "
              "run: bash setup.sh")
    else:
        print("\nsensor stream ended.%s" % ("\n" + err if err else ""))


def gps_fix(provider, timeout=GPS_TIMEOUT):
    """One termux-location request. Returns a (lat, lon, acc) tuple, or a
    reason string 'timeout'/'missing' if nothing usable came back."""
    try:
        out = subprocess.check_output(
            ["termux-location", "-p", provider, "-r", "once"], timeout=timeout)
    except subprocess.TimeoutExpired:
        return "timeout"
    except FileNotFoundError:
        return "missing"
    except subprocess.SubprocessError:
        return "error"
    try:
        gloc = json.loads(out.decode("utf-8"))
        lat = float(gloc["latitude"])
        lon = float(gloc["longitude"])
        acc = float(gloc.get("accuracy") or 0.0)
        return lat, lon, acc
    except (ValueError, KeyError, TypeError):
        return "unparseable"


def manual_location_prompt():
    """Ask the user for a manual 'lat, lon' fallback location.

    Returns (lat, lon, alt), the string 'skip' to stop location monitoring,
    or None to keep trying auto GPS."""
    print("\nGPS gave no fix. You can type a manual location instead.")
    try:
        ans = input("lat, lon (e.g. 30.900965, 75.857275)   [Enter=keep GPS, "
                    "'skip'=off]: ").strip()
    except (EOFError, KeyboardInterrupt):
        return None
    if not ans:
        return None
    if ans.lower() in ("skip", "none", "off"):
        return "skip"
    try:
        parts = [p.strip() for p in ans.replace(";", ",").split(",")]
        lat, lon = float(parts[0]), float(parts[1])
    except (ValueError, IndexError):
        print("  could not parse '%s' - expected 'lat, lon'" % ans)
        return None
    return lat, lon, 0.0


def gps_loop(stream):
    last = None
    order = ["gps", "network"]
    prefer = 0
    while True:
        provider = order[prefer]
        res = gps_fix(provider)
        if isinstance(res, tuple):
            lat, lon, acc = res
            moved = (last is None
                     or abs(lat - last[0]) > MOVE_DEG
                     or abs(lon - last[1]) > MOVE_DEG)
            if moved:
                stream.send({"type": "loc", "t": time.time(), "lat": lat,
                             "lon": lon, "acc": acc})
                print("\nGPS(%s): %.5f, %.5f (%.1f m)" % (provider, lat,
                                                           lon, acc))
                last = (lat, lon)
            prefer = order.index(provider)  # keep whichever provider worked
        elif provider == "gps":
            print("\ngps: no GPS fix in %ds - near a window or outside helps "
                  "a satellite lock." % GPS_TIMEOUT)
            manual = manual_location_prompt()
            if manual == "skip":
                print("gps: location monitoring stopped.")
                return
            if manual:
                lat, lon, alt = manual
                stream.send({"type": "loc", "t": time.time(), "lat": lat,
                             "lon": lon, "alt": alt, "acc": 0.0})
                print("\nGPS(manual): %.5f, %.5f" % (lat, lon))
                last = (lat, lon)
                return
            prefer = 1                      # try the coarse 'network' fix
        else:
            print("\ngps: 'network' fix unavailable too - retrying GPS.")
            prefer = 0
        time.sleep(10)


def ask_for_ip(port):
    """Interactive fallback: ask the user to type the desktop IP manually."""
    print("\nSearching again did not find the desktop.")
    print("Quick checks:")
    print("  1) same Wi-Fi (disable AP/client isolation on the router)")
    print("  2) Windows Firewall on the desktop must allow in UDP %d" % port)
    mine = local_ip()
    if mine:
        print("  3) this phone's IP is %s - the desktop must be on that "
              "subnet" % mine)
    while True:
        try:
            ans = input(
                "\nType the desktop IP shown in its 'Phone link' box\n"
                "(or press Enter to search the LAN again): ").strip()
        except (EOFError, KeyboardInterrupt):
            raise KeyboardInterrupt
        if not ans:
            ip = find_desktop(port)
            if ip:
                return ip
            print("  still nothing found.")
            continue
        if len(ans.split(".")) == 4:
            return ans
        print("  '%s' does not look like an IPv4 address." % ans)


def main():
    parser = argparse.ArgumentParser(
        prog="aim.py",
        description="Stream the phone's aim + location to the desktop Moon "
                    "Watch.")
    parser.add_argument("ip", nargs="?", default=None,
                        help="desktop IP (auto-discovery by default)")
    parser.add_argument("port", nargs="?", type=int, default=None,
                        help="UDP port (default %d)" % PORT)
    parser.add_argument("--lat", type=float, default=DEFAULT_LOCATION[0],
                        help="latitude to send (default Ludhiana)")
    parser.add_argument("--lon", type=float, default=DEFAULT_LOCATION[1],
                        help="longitude to send (default Ludhiana)")
    parser.add_argument("--alt", type=float, default=DEFAULT_LOCATION[2],
                        help="altitude metres (default %d)" % DEFAULT_LOCATION[2])
    parser.add_argument("--gps", action="store_true",
                        help="try live GPS instead of the fixed location")
    opts = parser.parse_args()

    ip = opts.ip
    port = opts.port or PORT
    stream = Streamer()
    if not ip:
        print("Finding desktop on the LAN...")
        ip = find_desktop(port)
        while not ip:
            ip = ask_for_ip(port)
        print("Found desktop at", ip)
    stream.set_target(ip, port)

    if opts.gps:
        threading.Thread(target=gps_loop, args=(stream,), daemon=True).start()
        print("Streaming aim + live GPS to %s:%s  (Ctrl+C to stop)"
              % (ip, port))
    else:
        lat, lon, alt = opts.lat, opts.lon, opts.alt
        stream.send({"type": "loc", "t": time.time(), "lat": lat,
                     "lon": lon, "alt": alt, "acc": 0.0})
        print("Streaming aim + location (%.5f, %.5f, %dm) to %s:%s  "
              "(Ctrl+C to stop)" % (lat, lon, alt, ip, port))
    try:
        read_sensors(stream)
    except KeyboardInterrupt:
        pass
    print("\nstopped")


if __name__ == "__main__":
    main()