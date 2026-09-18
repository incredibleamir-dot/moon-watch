# Moon Watch Link (phone as sky pointer)

Turns your phone into a "sky pointer" for the desktop **Moon Watch**
workstation.  The phone's rotation-vector IMU (+ magnetic field, with
accelerometer as backup) tells the desktop where the phone is pointed, and the
desktop's horizon sky map follows in real time.  The phone can also send its
location, or just use a built-in one (default: Ludhiana, Punjab).

> Current path is **SensorCast** (LIVE page → *Phone link* → username →
> **Connect**): stream **Rotation Vector** + **Magnetic Field** (+
> Accelerometer) at the fastest delay.  Point the **top edge of the phone**
> at the sky like a laser pointer (*Point with* can switch to *Back
> camera*).  The Termux/UDP streamer below is kept as a legacy offline
> reference.

## Requirements (legacy Termux path)

## Requirements

**Termux** and **Termux:API** must *both* be installed from **F-Droid**
(https://f-droid.org).  The Google Play builds cannot talk to the API app
(different app signatures), so `termux-sensor` there fails with
`Termux:API is not yet available on Google Play`.  Uninstall the Play Store
apps and install both from F-Droid, then open the **Termux:API** app once to
grant its sensor + location permissions.

## Setup (inside Termux)

```bash
pkg update -y
pkg install -y python termux-api
```

or just run once:

```bash
bash termux/setup.sh
```

## Use

Desktop and phone must be on the **same Wi-Fi**.  The desktop app always
listens on **UDP 5555** and shows its LAN IP in the *Phone link* box on the
**LIVE** page.  On the phone:

```bash
python termux/aim.py                  # auto-finds the desktop
python termux/aim.py 192.168.1.10     # ...or stream straight to an IP
python termux/aim.py 192.168.1.10 5555
```

* If discovery finds nothing it asks you to type the desktop IP manually.
* By default it streams aim + the fixed **Ludhiana (30.900965, 75.857275,
  262 m)** location, so GPS is not needed.
* `--gps` tries **live GPS** instead (waits ~60 s for a fix, then falls back
  to the coarse `network` provider, then offers a manual `lat, lon` entry).
* Override the location any time: `--lat 28.61 --lon 77.20 [--alt 216]`.

On the desktop: tick **Drive sky map from phone** (on by default), stand on
your spot and point the **top edge** toward the sky — turning your body pans
left/right, tilting the top up/down pans vertically.  The horizon map centres
on your aim (use *Point with* → *Back camera* only if you prefer the old
photograph pose).  Tick **Use phone GPS location** to also sync live lat/lon.
Watch the **mag uT** readout (~25–65 µT is clean; far outside means indoor
interference).  If the map's north doesn't align with real north, adjust
**North offset** (local magnetic declination, positive east), or point the top
at the Moon/Sun, drag it to the middle and press **Calibrate...**.

## Wire protocol

UDP JSON packets, UTF-8:

| `type`       | fields                             | meaning                          |
|--------------|------------------------------------|----------------------------------|
| `orient`     | `t, qx, qy, qz, qw, az, alt`       | camera aim (az/alt in deg)       |
| `loc`        | `t, lat, lon, acc[, alt]`          | location fix (acc in metres)     |
| `ping`       | `t`                                | keep-alive heartbeat             |
| `disc`       | -                                  | broadcast: "find the desktop"    |
| `disc_reply` | `ip`                               | desktop → phone discovery answer |

`q*` is the Android rotation-vector quaternion (device → world, east-north-up);
`az` is clockwise from north.  The desktop adds the configurable North offset
plus the stored pointing calibration, and aims the selected axis (`top` +Y by
default, `back` −Z optional).

## Desktop phone simulator (no phone needed)

`tools/phone_sim.py` in the main repo is a standalone desktop tool that sends
the exact same `orient` / `ping` / `loc` traffic, driven by a mouse-draggable
cube (left/right = azimuth, up/down = altitude):

```bash
python tools/phone_sim.py                    # -> 192.168.200.198:5555
python tools/phone_sim.py --host <ip> --port <port>
```

Run it on the same machine as the desktop app to exercise the whole phone-link
pipeline, sky-map aiming and UI without a phone.

## Troubleshooting

* **Windows Firewall** silently drops inbound UDP; allow UDP 5555 inbound for
  Python (needs an admin).
* **"not yet available"** — Play Store Termux/API; install both from F-Droid.
* **`termux-sensor -a` times out** — open the Termux:API app once and grant it
  sensor + location permissions in Android settings.
* **No rotation-vector sensor found** — the probe matches any sensor whose
  name contains *rotation vector* (Samsung phones expose e.g.
  *Samsung Rotation Vector Sensor*), so this is only hit on unusual devices.
* **Can't find the desktop** — same Wi-Fi, no AP/client isolation, or use
  `python termux/aim.py <desktop-ip>` directly.
* **GPS never fixes** — indoor fixes can take over a minute; go near a
  window/outside, or just use the default location.

## Calibration notes

- The rotation-vector sensor fuses magnetometer + accelerometer + gyro; a quick
  "figure-8" wave before streaming improves compass calibration.  Streaming
  **Magnetic Field** too lets the desktop show live field health and fall back
  to a tilt-compensated accel+mag compass when no rotation vector is seen.
- Indoor magnetic fields (rebar, desks, chargers) shift azimuth — the desktop
  **mag uT** readout flags this (~25–65 µT clean), and **North offset** +
  **Calibrate...** (point top at Moon/Sun → drag to middle → Calibrate)
  correct the residual twist.  Calibration is per-axis and persisted.
- Keep the streaming app in the foreground; Android suspends the sensors in the
  background.