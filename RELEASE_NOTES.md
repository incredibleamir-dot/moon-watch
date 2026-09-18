# Moon Watch - Crescent Visibility Workstation — Release Notes

**Version 1.5.0** · PySide6 desktop app for predicting and analysing new-crescent
visibility (Ramadan / Eid) from any location.

> Repository: [Crescent-Visibility-Workstation](https://github.com/incredibleamir-dot/Crescent-Visibility-Workstation)

---

## What's new in v1.5.0

- **Phone link over SensorCast WebSocket** (replaces the Termux/UDP link): the
  desktop subscribes to a SensorCast stream
  (`wss://api.sensorcast.app`, namespace `/stream/<username>`) for the phone's
  rotation-vector orientation and optional GPS.  Enter the username in the LIVE
  page's *Phone link* box and the horizon sky map follows the phone's aim.
- **Altitude clamping on the horizon sky map**: the view pans from the horizon
  up to the zenith (0–90°), pinned so the view bottom never drops below -5°.
- **Shared SensorCast protocol module** (`moonwatch/sensorcast.py`): frame
  parsing and the quaternion→aim maths now live in one place, reused by both the
  desktop link and the `tools/sensorcast_capture.py` terminal tool.
- **Pytest test suite** covering the protocol parser, quaternion aiming, the
  altitude clamp and golden spot-checks of the astronomy / analysis / islamic /
  verification engines (`pip install -r requirements-dev.txt && python -m pytest tests`).
- **Cleanup**: removed the Termux `phone-app/` and stale debug dumps; removed
  dead imports/constants across the astronomy / islamic / charts modules.

## What's new in v1.3.0

- **2D Horizon Sky Map** (new, Live view): a pannable 360° azimuth–altitude panorama of
  the sky, toggled from the 3D sighting sky with the **View** selector. The Sun, Moon and
  the bright planets (Mercury, Venus, Mars, Jupiter, Saturn) appear at their live positions
  with labels, along with each body's day-long altitude path and the ecliptic line.
- **Pan the horizon** like turning around: click-drag, mouse wheel, or the arrow / cardinal
  buttons; compass directions are marked below the horizon line.
- **Seamless day→twilight→night background**: the sky gradient follows the Sun, including a
  warm glow on the horizon toward the Sun at twilight.
- Built on the same astronomy engine as the rest of the app, so the map always agrees with
  the other views.

## What's new in v1.2.0

- **Interactive 3D Altitude–Azimuth Sighting Sky** in the Live view (replaces the flat
  2D Sun–Earth–Moon diagram), rendered with PyVista. The hemisphere around you is drawn
  in the local Alt–Az frame: compass cardinals (N highlighted), altitude rings, azimuth
  grid, horizon rim and a translucent earth-textured ground.
- **Moon at its true phase**: the lit crescent is shaded per-vertex from the Sun's
  direction, so it faces and thins exactly like the real Moon — no separate phase code.
- **Screen-facing readout boxes** always face the viewer: Sun / Moon name + Alt + Az,
  and the observer's location name + Lat/Lon, each in a translucent backing box.
- **Observer lines & trails**: observer → Sun / Moon lines, a dashed Sun–Moon separation
  link, and ±3 h trails for both bodies (toggle Moon/Sun path).
- **Controls**: Reset / Top / North / South / East / West camera buttons plus
  click-drag rotate and scroll-zoom; Grid / Moon path / Sun path / Labels toggles.
- **Dependency**: added PyVista and PyVistaQt (used only by the 3D Live sky).
- **3D sky animation export (MP4)**: the *Export animation* dialog now also offers the 3D
  dome as an MP4 (`sky-3d-<date>.mp4`). Selecting it opens a small preview window that plays
  the whole 24-hour Sun/Moon cycle while the camera slowly orbits 360°, then closes itself
  when the file is written. Requires OpenCV (`opencv-python`).

## What's new in v1.1.0

- **GIF animation export** (new): **Tools ▸ Export animation (GIF)...** (Ctrl+E) turns any
  chosen evening into an animation running from 1 hour before sunset to 1 hour after it.
  Three outputs: the **west-looking sky** (Sun, Moon and the trail the Moon traces through
  the whole window), the **global visibility map** recoloured at every instant with the same
  Odeh / MABIMS / Danjon rules as the app, and an optional **combined** GIF (sky above the
  map). A date picker, output-folder choice and progress bar are in the dialog; the heavy
  grid computation runs in a background sub-process so the interface never freezes.
- **Physically setting sun**: the sun in the sky frames now climbs before sunset, touches
  the horizon at sunset, and sinks out of view — it is no longer glued to the horizon line.
- **Dependency**: added Pillow (used for GIF frame assembly).

## What's new in v1.0.1

- **Global lunar crescent visibility map** (new): in the Sighting view, press
  **G** (or use the top-left selector) to switch from the local sky diagram to
  a whole-world map of the same evening. Every 1° cell is classified at that
  location's sunset by the chosen criterion and coloured **green** (visible) /
  **amber** (borderline) / **red** (not visible); the no-sunset polar band is
  left clear. A criterion dropdown (Odeh 2006 default, MABIMS 2023, Danjon
  limit) re-colours the map instantly — the ≈64k-point grid is computed once
  per date in a background sub-process (~2–4 s). Your city is pinned on the
  map, and the four classes are the same ones used by the local verdict pill.
- **Live view — fully textured Sun, Earth and Moon**: all three bodies now use
  the bundled texture maps, not just the Earth.
- **Live time scrubber**: slide through the 24 h of the selected date to watch
  the Sun-Earth-Moon system at any time of day; press **NOW** to return to the
  live clock (fixed 5 s updates). The scrub control bar is slim.
- **Instant location response**: changing the date/location updates the Live
  view (observer dot + clock) immediately instead of waiting for the next
  tick.

## Bug fixes in v1.0.1

- **UTC offset no longer rounds** in the status bar: `UTC+5.5` really shows
  `UTC+5.5` (was `UTC+6`).
- **Textures actually load**: the Live view always drew plain circles because
  the texture loader was broken on the current PySide6 (`QImage.bits()` now
  returns a `memoryview`); Earth/Moon/Sun maps now render.
- **Earth night side** in the Live view is no longer near-pure-black — dim but
  visible.
- Crescent limb orientation was fixed earlier (lit side aims at the Sun) and
  remains correct across sky map, sidebar thumbnail and Live view.

## Requirements & build

- Python 3.11+, `pip install -r requirements.txt` (PySide6, PyVista, PyVistaQt, numpy, pandas, Pillow, OpenCV).
- Run: `python main.py`
- Build: `python -m PyInstaller --clean --noconfirm MoonWatch.spec`
  → `dist/MoonWatch.exe`

## Notes / limitations

- The **NASA HORIZONS** comparison needs internet; everything else is offline.
- The global map classifies using values at each cell's *sunset*; the polar
  no-sunset band is uncoloured.
- Islamic dates use the app's local-visibility rule, so they can differ from a
  fixed civil calendar.

## Thanks

- Original pygame app + engine: [moon-watch](https://github.com/incredibleamir-dot/moon-watch)
- Recorded-sightings database: [HilalPy](https://github.com/msyazwanfaid/hilalpy)
- `solarsystem` (Paul Schlyter's algorithms): MIT licence
- Textures: [Solar System Scope](https://www.solarsystemscope.com/textures/), CC BY 4.0

See `CHANGELOG.md`, `CREDITS.md` and `PYGAME_TO_PYSIDE6.md`.