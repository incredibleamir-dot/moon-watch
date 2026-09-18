# Changelog

## [Unreleased]

### Added
- **Top-edge phone pointing** (default): `Point with` switches between top
  edge (+Y, laser-pointer pose) and back camera (−Z, photograph pose);
  `q_to_aim(..., axis=)` in `moonwatch/sensorcast.py` (plus `vec_to_aim`,
  `accel_mag_to_aim`, `mag_strength` helpers).  Standing on your origin and
  turning now pans the horizon map; calibration offsets are per-axis and
  persisted.
- **Magnetic-field + accelerometer support**: the desktop consumes mag/accel
  frames (live `mag uT` health readout, ~25–65 µT clean), with a smoothed
  tilt-compensated accel+mag compass fallback when no rotation vector is
  seen.  Stream Rotation Vector + Magnetic Field (+ Accelerometer) in
  SensorCast.
- **Pointing calibration dialog**: point the top at the Moon/Sun, drag it to
  the middle (or *Center map on target*), then *Calibrate to Moon/Sun* or
  *Calibrate to view centre*; offsets persist via `QSettings`.

### Documentation
- In-app User Guide Live section rewritten (3D sky + horizon map + phone aim
  + calibration); README phone section, `phone-app/README.md`, and
  `phone.py`/`sky_map.py` docstrings updated to top-edge + mag workflow.

## [1.5.0] - 2026-09-16

### Changed
- **Phone link now uses SensorCast WebSocket** instead of Termux/UDP: the
  desktop subscribes to the SensorCast stream (`wss://api.sensorcast.app`,
  namespace `/stream/<username>`, `role=subscriber` + heartbeat) for the phone's
  rotation-vector orientation and optional GPS location.
- **Sky-map altitude clamp**: the Live horizon map now pans from the horizon up
  to the zenith (0-90°), pinned so the view bottom never drops below -5°; both
  the phone-driven aim and drag panning route through the same clamp.

### Added
- `moonwatch/sensorcast.py`: the SensorCast wire parsing + quaternion-to-aim
  maths, shared by the desktop phone link and `tools/sensorcast_capture.py` so
  the frame format is defined exactly once.
- Pytest test suite (`tests/`): frame parsing, quaternion aiming, the sky-map
  altitude clamp, and golden spot-checks of the astronomy / analysis / islamic /
  verification engines.  Install with `pip install -r requirements-dev.txt`
  (adds `pytest`) and run `python -m pytest tests`.

### Removed
- `phone-app/` (Termux UDP aim streamer) - superseded by the SensorCast link.
- Stale `sensorcast_capture_*.txt` debug dumps.  `tools/phone_sim.py` is kept
  but re-labelled as a legacy UDP simulator (not wired to the current desktop
  receiver).
- Dead code: unused `sys` import and `VENDOR` constant in `astronomy.py`;
  unused `math` / `os` imports in `islamic.py`; unused `QFont` import in
  `moonwatch/charts.py`; the capture tool's duplicated `parse_frame` and
  `animation.py`'s duplicated age formatter (both now use the shared one).


## [1.4.0] - 2026-09-14

### Added
- **Phone link (Termux)**: `phone-app/termux/aim.py` streams the phone's
  rotation-vector orientation + location to the desktop app over UDP.
  - Default **Ludhiana** location (30.900965, 75.857275, 262 m) sent automatically
    so GPS is not required; override with `--lat/--lon/--alt`, or pass `--gps` for
    live GPS (60 s timeout, then network-provider fallback, then an interactive
    manual-coordinate prompt).
  - Automatic LAN discovery over both broadcast addresses (limited and /24
    subnet), retrying for up to 5 s; falls back to an interactive manual-IP
    prompt if nothing is found.
  - Vendor-agnostic sensor picker: queries `termux-sensor -a` and matches any
    sensor whose name contains *rotation vector*, so Samsung-prefixed names
    (e.g. "Samsung Rotation Vector Sensor") work without hard-coding.
- **Desktop phone simulator** (`tools/phone_sim.py`): a standalone PySide6 tool
  that streams the exact same `orient` / `ping` / `loc` traffic, driven by a
  mouse-draggable cube (orange face = back camera).  Run it on the same machine
  as the desktop app to exercise the phone-link pipeline without a phone.
- Desktop **"Drive sky map from phone"** checkbox now defaults to checked.
- Desktop *Phone link* box now shows a large **"Desktop IP for the phone"**
  label so the IP can be read on a phone screen, and flips to
  "streaming from \<ip\>" the moment a discovery round-trip completes.


## [1.3.1] - 2026-09-09

### Fixed
- **Live page layout on first paint**: content panels now balance immediately on
  construction, not only after a resize, so the initial split ratio matches what
  the user sees after the first drag.
- **Live time slider no longer triggers a day simulation while the page is being
  built**: the slider / debounce / NOW connections are wired only after the view is
  first populated, so the 24 h scrubber cannot fire `set_live_sim` during startup.

### Performance
- **New-moon conjunction search** (`astronomy.conjunction_before`): the bisection
  no longer re-evaluates the elongation of the lower bound 60 times per candidate;
  the cached value is reused, cutting per-lunation root-finding work roughly in
  half.  Results remain memoised per ~6-hour bucket.
- **World-grid snapshots** (`animation.snapshot_grid`): the Sun's altitude is now
  checked *before* computing the (far more expensive) topocentric Moon position,
  so cells still in daylight skip the Moon work entirely - identical output, about
  half the CPU for a full world frame.
- **Analysis point extraction** (`analysis._points`): replaced a `iterrows()` loop
  with vectorised numpy extraction (same result tuple-per-row).
- **Planet position cache** (`astronomy._planet_positions`): the overflow policy
  stopped clearing the whole ~1 MB cache and now evicts one least-recently-used
  entry at a time (bounded at 1,024 entries), keeping inter-date lookups warm.

### Cleanup
- Removed dead `LiveWidget` (flat 2D Sun-Earth-Moon painter) and its
  `astronomy_ecl2alt_az` helper from `moonwatch/charts.py` - replaced by the 3D sky
  and 2D horizon map in 1.2/1.3.
- Removed the duplicated worker `globalmap._run_global_map` (the controller-owned
  sub-process entry was the one actually used).
- `moonwatch/controller.py` no longer redefines the MABIMS/Danjon thresholds that
  already live in `astronomy.py`; pages read them from the single source.
- Dropped the redundant `sys.path` bootstrap and the unused `PLANET_NAMES` constant
  from `astronomy.py`, and an unused `numpy` import from `moonwatch/dialogs.py`.


## [1.3.0] - 2026-09-04

### Added
- **2D Horizon Sky Map** in the Live view: a pannable 360° azimuth–altitude panorama
  of the sky around the observer, toggled from the existing 3D sighting sky with the
  **View** selector:
  - Sun, Moon and the bright planets (Mercury, Venus, Mars, Jupiter, Saturn) drawn at
    their live positions with labels, plus their day-long altitude paths and the ecliptic.
  - Pan across the full 360° by click-drag, mouse wheel, or the arrow / cardinal buttons;
    compass directions are marked below the horizon line.
  - The background shifts **seamlessly from day to twilight to night** as the Sun moves,
    with a warm glow on the horizon toward the Sun at twilight.
- All values come from the same astronomy engine as the 3D sky and every other view.


## [1.2.0] - 2026-09-02
### Added
- **Interactive 3D Altitude–Azimuth Sighting Sky** in the Live view (replaces the old
  flat 2D Sun–Earth–Moon diagram), rendered with PyVista / PyVistaQt:
  - Hemispherical celestial dome in the local Alt–Az frame — compass cardinals (N
    highlighted), altitude rings, azimuth grid, horizon rim and a translucent
    earth-textured ground.
  - Sun as a glowing sphere; the **Moon drawn at its true phase** — the lit crescent is
    shaded from the Sun's direction, so it faces and thins exactly as the real Moon does.
  - Observer → Sun / Moon lines, a dashed Sun–Moon angular-separation link, and ±3 h
    trails for both bodies (toggle Moon/Sun path).
  - Screen-facing Sun / Moon readouts (name, altitude, azimuth) and the observer's
    location name + Lat/Lon; Grid / Moon path / Sun path / Labels toggles; Reset, Top,
    North, South, East, West camera buttons plus click-drag / scroll-zoom.
  - All values come from the same astronomy engine as every other view.
- Added `pyvista>=0.44` and `pyvistaqt>=0.11` to `requirements.txt` (power the 3D sky).
- **3D sky animation export (MP4)** added to the existing *Export animation* dialog: a new
  *"3D sighting sky (MP4) - full 24 h + orbiting camera"* option renders the whole 3D dome
  through a complete 24-hour Sun/Moon cycle while the camera slowly orbits 360°, written to
  `animations/sky-3d-<date>.mp4` (H.264 via OpenCV).  It opens a small preview window that
  closes itself when the file is written.  Requires OpenCV (`opencv-python`).


## [1.1.0] - 2026-09-01

### Added
- **GIF animation export** (Tools ▸ *Export animation (GIF)...*, Ctrl+E): capture any
  chosen evening as an animated GIF spanning 1 hour before sunset to 1 hour after it.
  Choose the west-looking sky map (Sun, Moon and the Moon's trail), the global visibility
  map evaluated at every frame instant (Odeh 2006 / MABIMS 2023 / Danjon), or both stacked
  into a single combined GIF.  The work runs in a background sub-process with a progress
  bar and writes to the `animations/` folder.  Requires Pillow (added to
  `requirements.txt`).
- The sky animation now shows the **Sun physically setting**: it rides above the horizon
  before sunset, dips as the animation passes sunset, and fades out below the horizon
  (previously it was pinned to the horizon line); the Moon's trail also extends slightly
  below the horizon.


## [1.0.1] - 2026-08-28

### Added
- **Global lunar crescent visibility map** (Sighting view, **G**): 1° grid over
  the world, every cell evaluated at its best time with the same rules as the
  on-page verdict, re-coloured instantly by criterion (Odeh 2006 / MABIMS 2023 /
  Danjon), computed in the background and cached per date in memory so stepping
  between dates is instant; observer pin and no-sunset polar band.
- **Live view**: textured Sun, Earth and Moon (a Natural Earth black-and-white
  line map on the globe); a 24 h time scrubber with a **NOW** button; immediate
  response to location/date changes.
- User guide + README coverage and smoke tests for the above.


## [1.0.0] - 2026-08-27

### Added
- Initial release: complete PySide6/Qt port of the pygame app with six
  workspaces (Sighting, Condition, Equation, Threshold, Verify, Live),
  Ramadan/Eid dates dialog, in-app guide, verification against NASA HORIZONS
  and ~8,000 recorded sightings, and a standalone Windows executable.
- Crescent limb orientation fix (lit side aims at the Sun).