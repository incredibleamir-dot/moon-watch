#!/usr/bin/env python3
"""Bluetooth serial capture tool.

Discovers Bluetooth devices, lets you select one, connects via serial
(SPP/RFCOMM or COM port), and dumps all incoming raw bytes to a file
so the data format can be analyzed.

Usage:
    python bt_capture.py                    # auto-discover + list COM ports
    python bt_capture.py --port COM5        # skip discovery, read COM5 directly
    python bt_capture.py --baud 115200      # set baud rate (default 19200)
    python bt_capture.py --timeout 30       # stop after 30 seconds
"""

import argparse
import datetime
import glob
import os
import platform
import re
import serial
import serial.tools.list_ports
import struct
import sys
import threading
import time

try:
    import bluetooth
    HAS_BT = True
except ImportError:
    HAS_BT = False


def discover_bluetooth_devices(timeout=8):
    """Discover nearby Bluetooth devices. Returns list of (addr, name)."""
    if not HAS_BT:
        return []
    print("Scanning for Bluetooth devices ( %ds )..." % timeout)
    try:
        devices = bluetooth.discover_devices(duration=timeout, lookup_names=True)
        return [(addr, name) for addr, name in devices]
    except bluetooth.BluetoothError as e:
        print("Bluetooth scan failed: %s" % e)
        return []


def list_com_ports():
    """List available serial/COM ports. Returns list of (port, desc)."""
    ports = []
    for info in serial.tools.list_ports.comports():
        ports.append((info.device, info.description or ""))
    return ports


def format_hex(data, bytes_per_line=16):
    """Format bytes as hex dump with ASCII sidebar."""
    lines = []
    for i in range(0, len(data), bytes_per_line):
        chunk = data[i:i + bytes_per_line]
        hex_part = " ".join("%02x" % b for b in chunk)
        ascii_part = "".join(chr(b) if 32 <= b < 127 else "." for b in chunk)
        lines.append("%06x  %-48s  %s" % (i, hex_part, ascii_part))
    return "\n".join(lines)


def run_capture(port, baud, timeout, outfile):
    """Open serial port, capture data until interrupted or timeout."""
    print("Opening %s @ %d baud..." % (port, baud))
    try:
        ser = serial.Serial(port, baud, timeout=1)
    except serial.SerialException as e:
        print("ERROR: %s" % e)
        return

    print("Connected. Logging to: %s" % outfile)
    print("Press Ctrl+C to stop.\n")

    raw_path = outfile
    txt_path = outfile + ".txt"
    raw_f = open(raw_path, "wb")
    txt_f = open(txt_path, "w", encoding="utf-8")

    start = time.time()
    total_bytes = 0
    pkt_count = 0
    buf = bytearray()

    try:
        while True:
            if timeout and (time.time() - start) > timeout:
                print("\nTimeout reached.")
                break

            line = ser.readline()
            if not line:
                continue

            raw_f.write(line)
            raw_f.flush()
            total_bytes += len(line)
            pkt_count += 1
            buf.extend(line)

            ts = datetime.datetime.now().strftime("%H:%M:%S.%f")[:-3]

            # Write hex + ASCII to text log
            txt_f.write("--- frame #%d  %s  len=%d  total=%d ---\n"
                        % (pkt_count, ts, len(line), total_bytes))
            txt_f.write(format_hex(line) + "\n")

            # Try to decode as text
            try:
                decoded = line.decode("utf-8", errors="replace").rstrip("\r\n")
                txt_f.write("TEXT: %s\n" % decoded)
            except Exception:
                pass

            txt_f.write("\n")
            txt_f.flush()

            # Live terminal output
            try:
                display = line.decode("utf-8", errors="replace").rstrip("\r\n")
            except Exception:
                display = format_hex(line)
            sys.stdout.write(
                "\r[%s] #%d  +%3d B  total=%d  | %s\n"
                % (ts, pkt_count, len(line), total_bytes, display))
            sys.stdout.flush()

    except KeyboardInterrupt:
        print("\nStopped by user.")
    finally:
        ser.close()
        raw_f.close()
        txt_f.close()

        print("\n===== CAPTURE SUMMARY =====")
        print("  Duration:    %.1f s" % (time.time() - start))
        print("  Packets:     %d" % pkt_count)
        print("  Total bytes: %d" % total_bytes)
        print("  Raw binary:  %s" % raw_path)
        print("  Text log:    %s" % txt_path)

        if total_bytes > 0:
            print("\n===== FIRST 256 BYTES (HEX DUMP) =====")
            print(format_hex(bytes(buf[:256])))

            # Try common encodings
            print("\n===== UTF-8 DECODE =====")
            print(buf[:512].decode("utf-8", errors="replace"))

            print("\n===== ASCII DECODE =====")
            print(buf[:512].decode("ascii", errors="replace"))

        print("\nRe-run with:  python bt_capture.py --port %s" % port)


def pick_device(devices, ports):
    """Interactive menu. Returns (port_or_addr, is_com_port)."""
    print("\n" + "=" * 60)
    print("  BLUETOOTH SERIAL CAPTURE")
    print("=" * 60)

    idx = 1
    bt_items = []
    com_items = []

    if ports:
        print("\n  COM / Serial Ports:")
        for port, desc in ports:
            print("    [%d]  %-12s  %s" % (idx, port, desc))
            com_items.append((idx, port))
            idx += 1

    if devices:
        print("\n  Bluetooth Devices (paired/visible):")
        for addr, name in devices:
            print("    [%d]  %-17s  %s" % (idx, addr, name or "(unknown)"))
            bt_items.append((idx, addr, name))
            idx += 1

    if not com_items and not bt_items:
        print("\n  No devices found.")
        if not HAS_BT:
            print("  (pybluez not installed - install with: pip install pybluez)")
        print("  Pair your SensorCast device in Windows Bluetooth settings,")
        print("  then re-run. Or use --port COMx directly.")

    print("\n  [0]  Rescan")
    print("  [q]  Quit")
    print()

    while True:
        try:
            choice = input("Select device number: ").strip()
        except (EOFError, KeyboardInterrupt):
            return None, False

        if choice.lower() in ("q", "quit", "exit"):
            return None, False
        if choice == "0":
            return "rescan", False

        try:
            n = int(choice)
        except ValueError:
            print("  Enter a number.")
            continue

        for idx, port in com_items:
            if n == idx:
                return port, True
        for idx, addr, name in bt_items:
            if n == idx:
                return addr, False

        print("  Invalid selection.")


def try_connect_bluetooth(addr):
    """Try RFCOMM connection to a Bluetooth device. Returns port path or None.

    On Windows this attempts the SDP query then falls back to suggesting
    the user pair and use the assigned COM port."""
    if not HAS_BT:
        return None

    print("\nQuerying %s for serial port service..." % addr)
    try:
        services = bluetooth.find_service(address=addr, uuid="00001101"
                                          "-0000-1000-8000-00805F9B34FB")
    except bluetooth.BluetoothError as e:
        print("SDP query failed: %s" % e)
        return None

    if not services:
        print("No serial service found on device.")
        return None

    svc = services[0]
    channel = svc["port"]
    host = svc["host"]
    print("  Service: %s  channel: %d" % (svc.get("name", "?"), channel))

    print("  Connecting RFCOMM to %s channel %d..." % (host, channel))
    try:
        sock = bluetooth.BluetoothSocket(bluetooth.RFCOMM)
        sock.connect((host, channel))
        print("  Connected! Wrapping as serial...")
        # Wrap in a file-like object for uniform handling
        return sock
    except bluetooth.BluetoothError as e:
        print("  Connection failed: %s" % e)
        print("\n  On Windows, pair the device first in:")
        print("    Settings > Bluetooth & devices > Add device")
        print("  Then find the assigned COM port and re-run with:")
        print("    python bt_capture.py --port COMx")
        return None


def main():
    parser = argparse.ArgumentParser(
        description="Capture Bluetooth serial data to file for format analysis.")
    parser.add_argument("--port", help="COM port to read (skip discovery)")
    parser.add_argument("--baud", type=int, default=19200,
                        help="baud rate (default 19200)")
    parser.add_argument("--timeout", type=float, default=None,
                        help="stop after N seconds (default: run forever)")
    parser.add_argument("--out", default="bt_capture",
                        help="output filename prefix (default: bt_capture)")
    parser.add_argument("--scan", type=int, default=8,
                        help="BT scan duration in seconds (default 8)")
    args = parser.parse_args()

    if args.port:
        # Direct COM port mode
        ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        outfile = "%s_%s.bin" % (args.out, ts)
        run_capture(args.port, args.baud, args.timeout, outfile)
        return

    # Discovery mode
    devices = discover_bluetooth_devices(timeout=args.scan)
    ports = list_com_ports()

    while True:
        choice, is_com = pick_device(devices, ports)

        if choice is None:
            print("Bye.")
            return
        if choice == "rescan":
            devices = discover_bluetooth_devices(timeout=args.scan)
            ports = list_com_ports()
            continue

        ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        outfile = "%s_%s.bin" % (args.out, ts)

        if is_com:
            run_capture(choice, args.baud, args.timeout, outfile)
            return
        else:
            # Bluetooth address - try RFCOMM
            sock = try_connect_bluetooth(choice)
            if sock:
                # Wrap Bluetooth socket with serial-like interface
                try:
                    import io
                    sock.settimeout(1.0)
                    # Manual capture from Bluetooth socket
                    print("\nConnected! Logging to: %s" % outfile)
                    print("Press Ctrl+C to stop.\n")

                    raw_f = open(outfile, "wb")
                    txt_f = open(outfile + ".txt", "w", encoding="utf-8")
                    start = time.time()
                    total = 0
                    pkt = 0

                    while True:
                        if args.timeout and (time.time() - start) > args.timeout:
                            break
                        try:
                            data = sock.recv(1024)
                        except bluetooth.BluetoothError:
                            continue
                        if not data:
                            continue

                        raw_f.write(data)
                        raw_f.flush()
                        total += len(data)
                        pkt += 1
                        ts_now = datetime.datetime.now().strftime("%H:%M:%S.%f")[:-3]

                        txt_f.write("--- #%d  %s  len=%d ---\n" % (pkt, ts_now, len(data)))
                        txt_f.write(format_hex(data) + "\n")
                        try:
                            txt_f.write("TEXT: %s\n" % data.decode("utf-8", errors="replace"))
                        except Exception:
                            pass
                        txt_f.write("\n")
                        txt_f.flush()

                        sys.stdout.write("\r[%s] #%d  +%d  total=%d" % (ts_now, pkt, len(data), total))
                        sys.stdout.flush()

                except KeyboardInterrupt:
                    print("\nStopped.")
                finally:
                    sock.close()
                    raw_f.close()
                    txt_f.close()
                    print("\nBytes captured: %d  -> %s" % (total, outfile))
            else:
                print("\nCould not connect via Bluetooth.")
                print("Try pairing the device in Windows settings first,")
                print("then re-run and select the assigned COM port.")
            return


if __name__ == "__main__":
    main()
