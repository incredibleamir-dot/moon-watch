# Credits

## Recorded-sightings database (data/Final.csv)

The `cond`, `equa` and `thres` analyses and the recorded-sightings verification
all use the observation database bundled at `data/Final.csv` (8,004
night-sighting records). The database originates from the open-source
**HilalPy** project, whose upstream hosted `Final.csv` at a GitHub URL that no
longer exists; the copy here was pulled from a historical commit of that
repository so that the analyses stay fully reproducible.

* Project: [github.com/msyazwanfaid/hilalpy](https://github.com/msyazwanfaid/hilalpy)
* The chart rendering and analysis-adaptation approach in this port follows
  the same conventions as that project's `cond`, `equa` and `thres`
  analyses.

## Astronomical engine

* `astronomy.py`, `analysis.py`, `islamic.py` and `verification.py` are
  reused from the original **Moon Watch** pygame application that this port
  refactors.
* The orbital calculations are based on Paul Schlyter's
  *[How to compute planetary positions](https://stjarnhimlen.se/comp/ppcomp.html)*,
  vendored as the `solarsystem` package in `vendor/`, written by
  **Ioannis Nasios** and used under the **MIT license**
  (Copyright (c) 2020, Ioannis Nasios):

  > If you use the solarsystem library in published work, please cite:
  >
  > ```bibtex
  > @misc{nasios2026solarsystemvalidatedlightweightpython,
  >       title={Solarsystem: A Validated Lightweight Python Package for Planetary
  >              Positions and Solar-Lunar Event Calculations},
  >       author={Ioannis Nasios},
  >       year={2026},
  >       eprint={2606.27055},
  >       archivePrefix={arXiv},
  >       primaryClass={astro-ph.EP},
  >       url={https://arxiv.org/abs/2606.27055},
  > }
  > ```

## Textures

The Sun, Earth and Moon maps in the Live view are the free equirectangular
maps from [Solar System Scope](https://www.solarsystemscope.com/textures/),
licensed under [CC BY 4.0](https://creativecommons.org/licenses/by/4.0/) and
bundled in `assets/`:

* `assets/earth.jpg` — 2k earth day map
* `assets/moon.jpg` — 2k moon map
* `assets/sun.jpg` — 2k sun map

When a texture is missing or fails to load, the Live view falls back to the
plain vector drawing automatically.

## Visibility criteria

* **MABIMS 2023** — minimum arc of light 6.4°, minimum moon altitude 3.0°.
* **Danjon limit** — minimum arc of light 7.0° (thin-crescent visibility limit).
* **Odeh (2006)** — visibility zones A–D from arc of vision, crescent width and
  elongation.

## External services

* **NASA / JPL HORIZONS** ([ssd.jpl.nasa.gov/horizons](https://ssd.jpl.nasa.gov/hORIZONS/))
  — queried by the Verify view for independent cross-checks of sunset,
  moonset, moon altitude and illumination. Requires internet access; the rest
  of the app works fully offline.

## Design & lineage

The original pygame app and the underlying desktop concept grew from
[tiny-solarsystem](https://github.com/incredibleamir-dot/tiny-solarsystem).
This PySide6 port keeps the physics and analysis identical, and replaces the
HUD styling with a conventional light enterprise workspace.