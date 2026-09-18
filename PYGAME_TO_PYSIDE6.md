# Port map: pygame → PySide6

How the original pygame app
([github.com/incredibleamir-dot/moon-watch](https://github.com/incredibleamir-dot/moon-watch),
`crescent_sighting.py`) maps onto this PySide6 refactor
([github.com/incredibleamir-dot/Crescent-Visibility-Workstation](https://github.com/incredibleamir-dot/Crescent-Visibility-Workstation)).
The goal was to keep every computation bit-identical while replacing a neon HUD
with a conventional desktop-scientific workspace.

## What stayed the same

| Original module | Here | Notes |
|-----------------|------|-------|
| `astronomy.py` | `astronomy.py` | copied unchanged |
| `analysis.py` | `analysis.py` | copied unchanged (cond / equa / thres engines) |
| `islamic.py` | `islamic.py` | copied unchanged (returns civil first day; the UI shows the sunset-start evening) |
| `verification.py` | `verification.py` | copied unchanged (HORIZONS + sightings checks) |
| `vendor/solarsystem/` | `vendor/solarsystem/` | vendored astronomy library, unchanged |
| `data/Final.csv` | `data/Final.csv` | recorded-sightings database, unchanged |
| `assets/*.jpg` | `assets/*.jpg` | texture maps, unchanged |

The data path between these four modules is preserved: the controller calls the
same functions with the same arguments and consumes the same `report` dict,
`series14` / `altseries` arrays, `islamic.events` tuples and analysis results
that the original UI consumed.

## What changed

| pygame concern | PySide6 replacement |
|----------------|---------------------|
| main loop + event pump | `QApplication` event loop (`main.py`) |
| HUD surface / taskbar | `QMainWindow` + `QToolBar` + menubar + statusbar (`app_window.py`) |
| view switching (1–6) | `QTabWidget` with six pages in the same order |
| per-pixel drawing loops | `QPainter` canvases rendered from numpy arrays (`charts.py`) |
| text gauge boxes | `QTableWidget` / `QLabel` tables with Consolas values |
| the "neon" retro font & glow | Segoe UI + flat light palette (`theme.py`) |
| modal popups | `QDialog` (setup / dates / about), `dialogs.py` |
| 14-evening bar chart | bar canvas in the Sighting view |
| live 5 s timer | `QTimer` driving the Live view refresh (`LivePage` → interactive 3D Alt–Az sky, `sighting_sky_3d.py`) |
| HORIZONS / sightings checks | separate **sub-processes** so the pure-Python astronomy loops never stall the GUI thread; results arrive through queues drained by a `QTimer` (`AppController.start_checks()`) |
| key handling | `QShortcut` (see table below) |

## Where each view lives

* Sighting → `pages.SightingPage` (sky canvas + altitude chart + verdict,
  criteria and plain-words panels)
* Condition → `pages.AnalysisPage("cond")`
* Equation → `pages.AnalysisPage("equa")`
* Threshold → `pages.AnalysisPage("thres")` with a parameter combo + X key
* Verify → `pages.VerifyPage` (HORIZONS rows + recorded-sightings rates)
* Live → `pages.LivePage`

## Shortcut mapping

| Key | pygame (HUD) | PySide6 (this port) |
|-----|--------------|---------------------|
| Left / Right | same | same |
| T | same | same |
| 1–6 | number keys switch views | number keys **or** S/C/E/H/V/L |
| V / L | aliases for views 5 / 6 | same aliases |
| R | NASA check | same |
| X | cycle threshold param | same |
| D | show/hide dates popup | open dates dialog |
| I | show About | **F1** (About also under Help menu) |
| F11 | fullscreen | same |
| Esc | close modal / exit fullscreen | native dialog Esc |
| Quit | taskbar power button | **Ctrl+Q** (and File → Quit) |

## Behaviour notes that changed intentionally

* **Islamic date display**: the calendar engine is unchanged, but the dates
  dialog now states explicitly that an Islamic date begins at sunset, showing
  the sighting evening and the following civil first day.
* **Branding**: the recorded-sightings database is described in the UI and
  docs as *the sighting database*; the only upstream project name used is the
  one required to credit the database (in CREDITS.md and the About dialog's
  "database project" link). `analysis.py`'s own module docstring is
  untouched.
* **Offline-friendly analysis**: all analysis views work offline; only the
  NASA HORIZONS comparison needs internet. Recorded-sightings checks run
  locally from `data/Final.csv`.

## Rendering notes

The physics code is vector-friendly, so the port renders charts with numpy
arrays (lens/pixmap operations, planet positions, illusion-of-3D overlap) and
draws them with `QPainter`, avoiding the original's row-by-row alpha-blending
tight loops. The sky diagram keeps the original semantics: Sun half-sunk at
its azimuth at sunset, altitude rings every 10°, the true crescent shape and
limb orientation, a dotted evening trail, and a drop-line to the horizon.