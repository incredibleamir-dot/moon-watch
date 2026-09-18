#!/usr/bin/env python3
"""SensorCast WebSocket capture — terminal only.

Connects to a SensorCast stream via Socket.IO, captures all sensor frames,
and saves them to a file for offline analysis.

Usage:
    python sensorcast_capture.py                 # your stream by default
    python sensorcast_capture.py --key MYKEY     # private stream
    python sensorcast_capture.py --out sensor_log
    python sensorcast_capture.py --timeout 60
"""

import argparse
import datetime
import json
import os
import sys
import threading
import time

try:
    import socketio
except ImportError:
    sys.exit("Missing dependency. Run:\n  pip install \"python-socketio[client]\"")

_PROJ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _PROJ not in sys.path:
    sys.path.insert(0, _PROJ)

from moonwatch.sensorcast import SERVER, parse_frame

sensor_data = {}
frame_count = 0
start_time = 0.0
out_file = None
txt_file = None
lock = threading.Lock()


def log(msg):
    """Write to terminal and text log."""
    ts = datetime.datetime.now().strftime("%H:%M:%S.%f")[:-3]
    line = "[%s] %s" % (ts, msg)
    sys.stdout.write(line + "\n")
    sys.stdout.flush()
    if txt_file:
        txt_file.write(line + "\n")
        txt_file.flush()


def main():
    global frame_count, start_time, out_file, txt_file

    USERNAME = "incredibleamir_5338"

    parser = argparse.ArgumentParser(
        description="Capture SensorCast WebSocket stream to file.")
    parser.add_argument("username", nargs="?", default=USERNAME,
                        help="SensorCast username (default: %s)" % USERNAME)
    parser.add_argument("--key", default=None, help="Stream key (for private streams)")
    parser.add_argument("--server", default=SERVER, help="Server URL")
    parser.add_argument("--out", default="sensorcast_capture",
                        help="Output file prefix (default: sensorcast_capture)")
    parser.add_argument("--timeout", type=float, default=None,
                        help="Stop after N seconds (default: run forever)")
    args = parser.parse_args()

    ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    raw_path = "%s_%s.jsonl" % (args.out, ts)
    txt_path = "%s_%s.txt" % (args.out, ts)

    out_file = open(raw_path, "w", encoding="utf-8")
    txt_file = open(txt_path, "w", encoding="utf-8")

    sio = socketio.Client()
    start_time = time.time()

    namespace = "/stream/%s" % args.username

    def heartbeat_loop():
        while True:
            time.sleep(20)
            if sio.connected:
                try:
                    sio.emit("heartbeat", namespace=namespace)
                except Exception:
                    pass

    @sio.event(namespace=namespace)
    def connect():
        log("Socket connected, announcing subscriber role...")
        sio.emit("role", "subscriber", namespace=namespace)

    @sio.on("connected", namespace=namespace)
    def on_connected(data):
        log("Server accepted role: %s" % data)

    @sio.on("frame", namespace=namespace)
    def on_frame(data):
        global frame_count
        frame_count += 1

        parsed = parse_frame(data)

        sensor_name = parsed.get("sensor", "?")
        values = parsed.get("values", {})
        ts_ms = parsed.get("timestamp", 0)

        with lock:
            sensor_data[sensor_name] = {"parsed": parsed, "count": frame_count}

        out_file.write(json.dumps(
            {"raw": data, "parsed": parsed}, ensure_ascii=False) + "\n")
        out_file.flush()

        val_str = "  ".join("%s=%.4f" % (k, v) for k, v in values.items())
        log("  #%05d  %-30s  %s" % (frame_count, sensor_name, val_str))

    @sio.on("publisher_disconnected", namespace=namespace)
    def on_pub_gone():
        log("Publisher disconnected. Stream ended.")

    @sio.event(namespace=namespace)
    def disconnect():
        log("Disconnected from server.")

    @sio.on("connect_error", namespace=namespace)
    def on_error(data):
        log("Connection error: %s" % data)

    @sio.on("auth_error", namespace=namespace)
    def on_auth_error(data):
        log("Auth error: %s" % data)

    auth = {"streamKey": args.key} if args.key else {}

    print("=" * 60)
    print("  SensorCast WebSocket Capture")
    print("=" * 60)
    print("  Server:   %s" % args.server)
    print("  Username: %s" % args.username)
    print("  Private:  %s" % ("yes (key provided)" if args.key else "no"))
    print("  Raw log:  %s" % raw_path)
    print("  Text log: %s" % txt_path)
    print("=" * 60)
    print()
    print("Connecting...")

    try:
        sio.connect(
            args.server,
            namespaces=[namespace],
            socketio_path="/socket.io/",
            auth=auth if auth else None,
        )
        log("Connected, listening on %s" % namespace)

        hb = threading.Thread(target=heartbeat_loop, daemon=True)
        hb.start()

        if args.timeout:
            sio.sleep(args.timeout)
            log("\nTimeout reached. Disconnecting...")
            sio.disconnect()
        else:
            sio.wait()

    except KeyboardInterrupt:
        log("\nStopped by user.")
        sio.disconnect()
    except Exception as e:
        log("Fatal: %s" % e)

    elapsed = time.time() - start_time
    print("\n" + "=" * 60)
    print("  CAPTURE SUMMARY")
    print("=" * 60)
    print("  Duration:     %.1f s" % elapsed)
    print("  Total frames: %d" % frame_count)
    if elapsed > 0:
        print("  Avg rate:     %.1f Hz" % (frame_count / elapsed))
    print("  Sensors seen: %d" % len(sensor_data))
    for name, info in sensor_data.items():
        vals = info["parsed"].get("values", {})
        print("    - %-28s  fields: %s" % (name, ", ".join(vals.keys())))
    print("  Raw log:      %s" % raw_path)
    print("  Text log:     %s" % txt_path)
    print("=" * 60)

    out_file.close()
    txt_file.close()


if __name__ == "__main__":
    main()
