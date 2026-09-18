"""Interactive 3D Altitude-Azimuth Sighting Sky embedded in the Live page.

This is a *visualization-only* widget.  It consumes the same live data the
old 2D Sun-Earth-Moon chart consumed (``controller.live``) and renders a local
sky as seen by the observer: a transparent hemispherical celestial dome in the
local Alt-Az coordinate system, with the observer at the centre, the Sun and
Moon positioned from the existing astronomy calculations, and the observer /
horizon / zenith / compass grid as fixed references.

Coordinate convention (used throughout):
    +X  = East         +Y  = North          +Z  = Zenith
    Azimuth 0 deg = North, 90 deg = East, 180 deg = South, 270 deg = West
    Altitude controls the vertical (+Z) component; 0 deg = horizon, 90 = zenith.

Only the conversion ``altitude + azimuth -> cartesian`` lives here.  All
astronomical values (sun/moon alt-az, elongation, illumination, age) come from
the existing astronomy / controller layer and are taken as-is.
"""

import math

import numpy as np
import pyvista as pv
from PySide6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QPushButton,
                               QCheckBox)

from pyvistaqt import QtInteractor
from vtkmodules.vtkRenderingCore import vtkBillboardTextActor3D

import astronomy

# ---------------------------------------------------------------------------
# Dark sky palette (this visualization only - the rest of the app keeps its
# light scientific look).
# ---------------------------------------------------------------------------
SKY_BG = "#050a14"
GRID_C = (96, 190, 226)          # luminous cyan for grid lines
GRID_DIM = (72, 150, 185)
HORIZON_C = (60, 160, 200)
ACCENT_C = (79, 195, 247)
SUN_C = (245, 180, 50)
MOON_C = (223, 233, 245)
TEXT_C = (200, 220, 235)
ZENITH_C = (120, 200, 240)
OBSERVER_C = (120, 220, 160)
SUN_LABEL_C = (245, 200, 120)
MOON_NIGHT = (24, 30, 42)        # earthshine-tinted dark side of the Moon

ALTITUDE_RINGS = (10.0, 20.0, 30.0, 40.0, 50.0, 60.0, 70.0, 80.0, 90.0)
CARDINALS = ("N", "NE", "E", "SE", "S", "SW", "W", "NW")
CARDINAL_C = (150, 200, 230)


def alt_az_to_xyz(alt, az, r=1.0):
    """Convert local altitude/azimuth (deg) to cartesian on a sphere of
    radius r using the +X=East / +Y=North / +Z=Zenith convention."""
    a = math.radians(alt)
    zr = math.radians(az)
    return (r * math.cos(a) * math.sin(zr),
            r * math.cos(a) * math.cos(zr),
            r * math.sin(a))


def _unit(v):
    v = np.asarray(v, dtype=float)
    n = np.linalg.norm(v)
    return v / n if n else v


def _ring(alt, r, n=128):
    """Points of an altitude circle (horizontal ring) at given altitude."""
    rr = r * math.cos(math.radians(alt))
    zz = r * math.sin(math.radians(alt))
    th = np.linspace(0.0, 2.0 * math.pi, n, endpoint=False)
    return np.column_stack([rr * np.sin(th), rr * np.cos(th),
                            np.full(n, zz)])


def _polyline(pts, close=False):
    return pv.lines_from_points(np.asarray(pts, dtype=float), close=close)


def _dashed_line(a, b, dash=0.05, gap=0.035):
    """Build a lightweight dashed polyline between two 3D points in the
    horizontal plane projection so the break pattern reads as a dashed link."""
    a = np.asarray(a, dtype=float)
    b = np.asarray(b, dtype=float)
    d = b - a
    length = np.linalg.norm(d)
    segs = []
    t = 0.0
    while t < length:
        t2 = min(t + dash, length)
        if t2 - t >= 1e-6:
            segs.append(a + d * (t / length))
            segs.append(a + d * (t2 / length))
        t += dash + gap
    if len(segs) < 2:
        segs = [a, b]
    pts = np.array(segs)
    poly = pv.PolyData(pts)
    lines = []
    for i in range(0, len(pts) - 1, 2):
        lines += [2, i, i + 1]
    poly.lines = np.array(lines, dtype=np.int64)
    return poly


class SightingSky3D(QWidget):
    """A PyVista ``QtInteractor`` that renders the local altitude-azimuth sky.

    The widget is created once and its camera / grid / horizon / label actors
    are built a single time.  On every ``set_data`` call the Sun and Moon
    actors (also created once) are merely moved / re-shaded in place, and the
    billboard text labels (created once) are updated in place - so nothing is
    torn down and re-created per frame, which keeps the Live slider responsive
    and free of label flicker.
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self.R = 1.0

        self.plotter = QtInteractor(self, title="3D Sighting Sky")
        self.plotter.set_background(SKY_BG)

        self._sun_actor = None
        self._sun_glow = None
        self._moon_actor = None
        self._moon_mesh = None
        self._moon_base = None          # per-vertex base RGB from moon texture
        self._moon_pts = None
        self._moon_normals = None
        self._label_actors = []         # every billboard actor (for toggling)
        self._lab_sun = None
        self._lab_moon = None
        self._lab_observer = None
        self._sun_line = None
        self._moon_line = None
        self._rel_line = None
        self._moon_path = None
        self._sun_path = None
        self._vis_patch = None
        self._grid_actors = []         # collect every grid/horizon actor
        self._tex = None
        self._earth_arr = None
        self._show_grid = True
        self._show_moon_path = True
        self._show_sun_path = True
        self._show_labels = True

        self._build_static_scene()

        ctrl = QHBoxLayout()
        ctrl.setSpacing(6)
        ctrl.addStretch(1)
        for text, fn in (("Reset", self._view_reset), ("Top", self._view_top),
                         ("North", self._view_north), ("South", self._view_south),
                         ("East", self._view_east), ("West", self._view_west)):
            b = QPushButton(text)
            b.setFixedHeight(26)
            b.clicked.connect(fn)
            ctrl.addWidget(b)
        ctrl.addStretch(1)

        self.cb_grid = QCheckBox("Grid")
        self.cb_moon_path = QCheckBox("Moon path")
        self.cb_sun_path = QCheckBox("Sun path")
        self.cb_labels = QCheckBox("Labels")
        for cb, on in ((self.cb_grid, self._show_grid),
                       (self.cb_moon_path, self._show_moon_path),
                       (self.cb_sun_path, self._show_sun_path),
                       (self.cb_labels, self._show_labels)):
            cb.setChecked(on)
            cb.setStyleSheet(
                "QCheckBox { color: #23313f; background: #ffffff;"
                " border: 1px solid #d5dce3; border-radius: 4px;"
                " padding: 2px 8px; font-weight: 600; }"
                "QCheckBox::indicator { width: 14px; height: 14px; }")
        self.cb_grid.toggled.connect(lambda v: self._toggle(v, "grid"))
        self.cb_moon_path.toggled.connect(lambda v: self._toggle(v, "moon_path"))
        self.cb_sun_path.toggled.connect(lambda v: self._toggle(v, "sun_path"))
        self.cb_labels.toggled.connect(lambda v: self._toggle(v, "labels"))

        bar = QHBoxLayout()
        bar.setSpacing(8)
        bar.addWidget(self.cb_grid)
        bar.addWidget(self.cb_moon_path)
        bar.addWidget(self.cb_sun_path)
        bar.addWidget(self.cb_labels)
        bar.addStretch(1)

        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(4)
        lay.addLayout(ctrl)
        lay.addLayout(bar)
        lay.addWidget(self.plotter, 1)

        self._apply_visibility(self._grid_actors, self._show_grid)
        self._view_reset()
        self._applied_initial_view = False

    def showEvent(self, event):
        """Re-apply the reset camera the first time the widget is shown.

        The default view is set in ``__init__`` but the plotter has not been
        laid out / rendered at its real size yet, so auto-framing on first
        display can drift from it.  Re-running ``_view_reset()`` once on first
        show makes the default zoom exactly match what the Reset button shows.
        """
        super().showEvent(event)
        if not self._applied_initial_view:
            self._applied_initial_view = True
            self._view_reset()

    # ---------------------------------------------------------------- labels
    def _add_billboard(self, text, pos, color=TEXT_C, bg=(8, 12, 22),
                       size=18, opacity=0.72):
        """A screen-facing text label wrapped in a small translucent box.

        ``vtkBillboardTextActor3D`` always faces the viewer, supports
        multi-line input (``\\n``) and a background fill - exactly what the
        Sun / Moon / Observer readouts need.  It is created once and updated
        in place via ``SetInput`` / ``SetPosition``.
        """
        a = vtkBillboardTextActor3D()
        tp = a.GetTextProperty()
        tp.SetFontSize(size)
        tp.SetFontFamilyToTimes()
        tp.SetColor(*[c / 255.0 for c in color])
        tp.SetBackgroundColor(*[c / 255.0 for c in bg])
        tp.SetBackgroundOpacity(opacity)
        tp.SetVerticalJustificationToCentered()
        tp.SetJustificationToCentered()
        a.SetInput(text)
        a.SetPosition(pos)
        self.plotter.add_actor(a, reset_camera=False)
        self._label_actors.append(a)
        return a

    def _build_static_scene(self):
        R = self.R
        g = self._grid_actors
        # -- sky dome (upper hemisphere, thin translucent wireframe-ish shell)
        dome = pv.Sphere(radius=R, theta_resolution=72, phi_resolution=36)
        dome = dome.clip_closed_surface(normal=(0, 0, 1), origin=(0, 0, 0))
        g.append(self.plotter.add_mesh(
            dome, color=(35, 70, 110), opacity=0.06, name="dome",
            show_edges=False, lighting=False))

        # -- subtle star field
        rng = np.random.default_rng(7)
        n = 900
        azs = rng.uniform(0, 360, n)
        els = rng.uniform(2, 89, n)
        pts = np.array([alt_az_to_xyz(e, a, R * 0.97)
                        for a, e in zip(azs, els)])
        star = pv.PolyData(pts)
        g.append(self.plotter.add_points(
            star, color=(215, 225, 240), point_size=1.2,
            render_points_as_spheres=True, name="stars"))

        # -- altitude rings
        ring_group = pv.MultiBlock()
        for alt in ALTITUDE_RINGS:
            if alt >= 89.999:
                continue
            ring_group.append(_polyline(_ring(alt, R), close=True))
        g.append(self.plotter.add_mesh(
            ring_group, color=GRID_C, opacity=0.35, line_width=1.0,
            name="alt_rings"))

        # -- azimuth radial grid (great circles from zenith to horizon)
        az_group = pv.MultiBlock()
        for az in range(0, 360, 15):
            pts = [alt_az_to_xyz(alt, az, R)
                   for alt in np.linspace(0, 88, 30)]
            az_group.append(_polyline(pts))
        g.append(self.plotter.add_mesh(
            az_group, color=GRID_DIM, opacity=0.22, line_width=1.0,
            name="az_grid"))

        # -- horizon rim (clearly visible circle) + radial ticks
        g.append(self.plotter.add_mesh(
            _polyline(_ring(0.0, R), close=True), color=HORIZON_C, opacity=0.9,
            line_width=2.0, name="horizon_rim"))

        tick_group = pv.MultiBlock()
        for az in range(0, 360, 15):
            p0 = alt_az_to_xyz(0, az, R * 0.98)
            p1 = alt_az_to_xyz(0, az, R * 1.02)
            tick_group.append(_polyline([p0, p1]))
        g.append(self.plotter.add_mesh(
            tick_group, color=GRID_C, opacity=0.5, line_width=1.0,
            name="horizon_ticks"))

        # -- translucent horizon disk, textured with the earth map when present
        disc = pv.Disc(inner=0.0, outer=R, r_res=1, c_res=96)
        disc.texture_map_to_plane(
            origin=(0, 0, 0), point_u=(R, 0, 0), point_v=(0, R, 0), inplace=True)
        self._disc_mesh = disc
        g.append(self.plotter.add_mesh(
            disc, color=(20, 60, 95), opacity=0.90, name="horizon_disk",
            lighting=False))

        # -- zenith axis + marker + label
        zen_line = _polyline(np.array([[0, 0, 0], [0, 0, R * 1.06]]))
        g.append(self.plotter.add_mesh(
            zen_line, color=ZENITH_C, opacity=0.75, line_width=1.6,
            name="zenith_axis"))
        g.append(self.plotter.add_mesh(
            pv.Sphere(radius=0.02).translate((0, 0, R)), color=ZENITH_C,
            name="zenith_dot", lighting=False))
        self._add_billboard("ZENITH  90\u00b0", (0, 0, R + 0.06),
                            color=ZENITH_C, size=16)

        # -- observer marker + location label (updated on data change)
        g.append(self.plotter.add_mesh(
            pv.Sphere(radius=0.02), color=OBSERVER_C,
            name="observer_dot", lighting=False))
        self._lab_observer = self._add_billboard(
            "Observer", (0.0, 0.06, -0.03), color=OBSERVER_C, size=14)

        # -- cardinal direction labels + emphasis on North
        for i, name in enumerate(CARDINALS):
            az = i * 45.0
            pos = alt_az_to_xyz(0, az, R * 1.08)
            pos = (pos[0], pos[1], 0.0)
            color = ACCENT_C if name == "N" else CARDINAL_C
            self._add_billboard(name, pos, color=color, size=16)

        # -- crescent-visibility observation patch (low western sky)
        self._vis_patch = self._build_west_patch()
        g.append(self.plotter.add_mesh(
            self._vis_patch, color=(120, 200, 160), opacity=0.10,
            name="vis_patch", lighting=False))

        # -- Sun (glowing sphere) - created once, moved per update
        self._sun_actor = self.plotter.add_mesh(
            pv.Sphere(radius=0.055, theta_resolution=32, phi_resolution=32),
            color=SUN_C, smooth_shading=True, name="sun")
        self._sun_glow = self.plotter.add_mesh(
            pv.Sphere(radius=0.13, theta_resolution=32, phi_resolution=32),
            color=SUN_C, opacity=0.18, name="sun_glow", lighting=False)

        # -- Moon mesh (vertex-coloured per phase).  Created once; its point
        #    colours are re-derived each frame to reveal the lit crescent.
        self._moon_mesh = pv.Sphere(radius=0.045, theta_resolution=48,
                                    phi_resolution=48)
        self._moon_mesh.point_data["_rgba"] = np.full(
            (self._moon_mesh.n_points, 3), 180, dtype=np.uint8)
        self._moon_pts = np.asarray(self._moon_mesh.points)
        self._moon_normals = np.asarray(self._moon_mesh.point_normals)
        self._moon_actor = self.plotter.add_mesh(
            self._moon_mesh, scalars="_rgba", rgb=True,
            name="moon", lighting=False)
        self._moon_ring = self.plotter.add_mesh(
            pv.Sphere(radius=0.058, theta_resolution=24, phi_resolution=24),
            color=MOON_C, opacity=0.15, name="moon_ring", lighting=False)

        # Sun / Moon screen-facing readouts (created once)
        self._lab_sun = self._add_billboard("Sun", (1.1, 1.1, 1.1),
                                            color=SUN_LABEL_C, size=16)
        self._lab_moon = self._add_billboard("Moon", (1.1, 1.1, 1.1),
                                             color=MOON_C, size=16)

        # direction lines + relationship (created once, moved later)
        self._sun_line = self.plotter.add_mesh(
            _polyline([[0, 0, 0], [1, 1, 1]]), color=(140, 100, 40),
            opacity=0.55, line_width=1.2, name="sun_line")
        self._moon_line = self.plotter.add_mesh(
            _polyline([[0, 0, 0], [1, 1, 1]]), color=(100, 130, 170),
            opacity=0.55, line_width=1.2, name="moon_line")
        self._rel_line = self.plotter.add_mesh(
            _dashed_line([0, 0, 0.2], [0.5, 0.5, 0.2]), color=(180, 220, 250),
            opacity=0.85, line_width=1.4, name="rel_line")

        # optional paths (rebuilt on data change)
        self._moon_path = self.plotter.add_mesh(
            _polyline([[0, 0, 0], [1, 1, 1]]), color=MOON_C,
            opacity=0.5, line_width=1.4, name="moon_path")
        self._sun_path = self.plotter.add_mesh(
            _polyline([[0, 0, 0], [1, 1, 1]]), color=(150, 110, 50),
            opacity=0.4, line_width=1.4, name="sun_path")

    def _build_west_patch(self):
        """Small translucent wedge near the western horizon (the region where a
        young crescent is typically looked for after sunset)."""
        azs = np.linspace(235.0, 305.0, 16)
        alts = np.linspace(0.0, 12.0, 6)
        AZ, ALT = np.meshgrid(azs, alts)
        pts = np.array([alt_az_to_xyz(alt, az, self.R)
                        for az, alt in zip(AZ.ravel(), ALT.ravel())])
        grid = pv.StructuredGrid()
        grid.points = pts
        grid.dimensions = (16, 6, 1)
        return grid

    # ---------------------------------------------------------- data / update
    def set_tex(self, tex):
        """Refresh texture resources (moon map per-vertex colours, the earth
        ground map) from the app's TextureBank (numpy)."""
        if tex is self._tex and tex is not None:
            return
        if tex is None:
            self._tex = None
            return
        self._tex = tex
        moon = tex.get("moon")
        if moon is not None and self._moon_pts is not None:
            try:
                self._moon_base = self._sample_sphere_texture(self._moon_pts,
                                                              moon)
            except Exception:
                self._moon_base = None
        earth = tex.get("earth_sat")
        if earth is None:
            earth = tex.get("earth")
        if earth is not None and self._disc_mesh is not None:
            try:
                self._earth_arr = np.asarray(earth)
                self._apply_earth_texture()
            except Exception:
                pass

    @staticmethod
    def _sample_sphere_texture(pts, img):
        """Equirectangular sample of an HxW,x3 texture at unit-sphere points."""
        img = np.asarray(img)
        h, w = img.shape[:2]
        x, y, z = pts[:, 0], pts[:, 1], pts[:, 2]
        u = (np.arctan2(x, z) + np.pi) / (2.0 * np.pi)
        v = 0.5 - np.arcsin(np.clip(y, -1.0, 1.0)) / np.pi
        ui = np.clip((u * (w - 1)).astype(np.int64), 0, w - 1)
        vi = np.clip((v * (h - 1)).astype(np.int64), 0, h - 1)
        return img[vi, ui].astype(np.float32)          # N x 3

    def _apply_earth_texture(self):
        if self._earth_arr is None or self._disc_mesh is None:
            return
        try:
            as_flat = self._tex.get("earth_sat")
            tex = pv.Texture(as_flat if as_flat is not None else self._earth_arr)
            self.plotter.remove_actor(self._disc_mesh, render=False)
            self._disc_mesh.texture_map_to_plane(
                origin=(0, 0, 0), point_u=(self.R, 0, 0),
                point_v=(0, self.R, 0), inplace=True)
            self.plotter.add_mesh(self._disc_mesh, texture=tex, opacity=0.95,
                                  name="horizon_disk", lighting=False)
        except Exception:
            pass

    def set_data(self, live, tex=None):
        """Move / re-shade the Sun, Moon and readouts to the freshly computed
        altitude-azimuth positions.  ``live`` is the controller's live dict."""
        if tex is not None and tex is not self._tex:
            self.set_tex(tex)
        if live is None:
            return
        R = self.R
        s_alt, s_az = live["s_alt"], live["s_az"]
        m_alt, m_az = live["m_alt"], live["m_az"]

        # ---- objects
        sp = _unit(alt_az_to_xyz(s_alt, s_az, 1.0)) * R
        mp = _unit(alt_az_to_xyz(m_alt, m_az, 1.0)) * R
        self._move_actor(self._sun_actor, sp)
        self._move_actor(self._sun_glow, sp)
        self._move_actor(self._moon_actor, mp)
        self._move_actor(self._moon_ring, mp)

        # fade objects below the horizon for scientific context
        self._set_actor_opacity(self._sun_glow, 0.18 if s_alt > 0 else 0.06)
        self._set_actor_opacity(self._moon_ring, 0.15 if m_alt > 0 else 0.06)

        # ---- direction lines
        self._update_line(self._sun_line, [0, 0, 0], sp, R)
        self._update_line(self._moon_line, [0, 0, 0], mp, R)

        # ---- sun-moon angular-separation (dashed) line
        self._update_dashed(self._rel_line, sp, mp)

        # ---- crescent illumination of the Moon (geometry-based)
        self._shade_moon(sp, mp)

        # ---- screen-facing readouts (updated in place)
        self._update_labels(live, sp, mp)

        # ---- paths (rebuilt from the existing astronomy layer on data change)
        self._update_paths(live, sp, mp)

        self.plotter.render()

    def _shade_moon(self, sp, mp):
        """Colour the Moon mesh so the lit crescent faces the Sun.

        The sun direction at the Moon is ``unit(sun_pos - moon_pos)``; a
        surface point is lit where its outward normal points toward that
        direction.  The resulting lit region is exactly the crescent seen from
        the observer, orientation included, with a soft terminator and a faint
        earthshine-tinted night side so the dark limb stays visible.
        """
        if self._moon_mesh is None:
            return
        try:
            d = _unit(sp - mp)
            s = np.einsum("ij,j->i", self._moon_normals, d)
            lit = np.clip((s - 0.40) / 0.20, 0.0, 1.0)      # soft terminator
            if self._moon_base is not None:
                base = self._moon_base
            else:
                base = np.array(MOON_C, dtype=float)[None, :]
            night = np.array(MOON_NIGHT, dtype=float)[None, :]
            colors = base * lit[:, None] + night * (1.0 - lit[:, None])
            self._moon_mesh.point_data["_rgba"] = np.clip(colors, 0, 255).astype(
                np.uint8)
            self._moon_mesh.GetPointData().Modified()
            self._moon_mesh.Modified()
        except Exception:
            pass

    def _update_labels(self, live, sp, mp):
        R = self.R
        s_alt, s_az = live["s_alt"], live["s_az"]
        m_alt, m_az = live["m_alt"], live["m_az"]
        if self._lab_sun is not None:
            pos = _unit(sp) * R * 1.28
            self._lab_sun.SetInput(
                "Sun\nAlt %.1f\u00b0\nAz %.1f\u00b0" % (s_alt, s_az))
            self._lab_sun.SetPosition(pos)
        if self._lab_moon is not None:
            pos = _unit(mp) * R * 1.28
            self._lab_moon.SetInput(
                "Moon\nAlt %.1f\u00b0\nAz %.1f\u00b0" % (m_alt, m_az))
            self._lab_moon.SetPosition(pos)
        if self._lab_observer is not None:
            city = str(live.get("_city") or "")
            line2 = ""
            lat, lon = live.get("_lat"), live.get("_lon")
            if lat is not None and lon is not None:
                line2 = "Lat %.2f\u00b0  Lon %.2f\u00b0" % (lat, lon)
            self._lab_observer.SetInput(
                "Observer\n%s\n%s" % (city, line2))
            self._lab_observer.SetPosition((0.0, 0.10, 0.0))

    def _update_paths(self, live, sp, mp):
        def sample(alt_az_fn, jd0, hours, steps=48):
            out = []
            for k in range(steps):
                frac = k / max(1, steps - 1)
                jd = jd0 + (hours * (frac - 0.5)) / 24.0
                alt, az = alt_az_fn(jd, live["_lat"], live["_lon"])
                out.append(alt_az_to_xyz(alt, az, self.R))
            return out

        try:
            moon_pts = sample(astronomy.moon_alt_az, live["jd"], 6.0)
            sun_pts = sample(astronomy.sun_alt_az, live["jd"], 6.0)
            self._assign_line(self._moon_path, moon_pts)
            self._assign_line(self._sun_path, sun_pts)
        except Exception:
            pass

    def _assign_line(self, actor, pts):
        if actor is None or len(pts) < 2:
            return
        poly = _polyline(pts)
        try:
            actor.GetMapper().SetInputData(poly)
            actor.GetMapper().Modified()
        except Exception:
            pass

    # ------------------------------------------------------------- act/geom
    def _move_actor(self, actor, pos):
        if actor is None:
            return
        actor.SetPosition(pos)

    def _set_actor_opacity(self, actor, op):
        try:
            actor.GetProperty().SetOpacity(op)
        except Exception:
            pass

    def _update_line(self, actor, a, b, R):
        pts = [a, b]
        poly = _polyline(pts)
        try:
            actor.GetMapper().SetInputData(poly)
        except Exception:
            pass

    def _update_dashed(self, actor, a, b):
        poly = _dashed_line(a, b)
        try:
            actor.GetMapper().SetInputData(poly)
        except Exception:
            pass

    # ------------------------------------------------------------- controls
    def _view_reset(self):
        self.plotter.camera_position = [(2.4, -2.6, 1.6), (0, 0, 0.35), (0, 0, 1)]
        self.plotter.reset_camera()
        self._zoom_in(0.74)
        self.plotter.render()

    def _zoom_in(self, factor=0.74):
        """Pull the camera closer to its focal point by ``factor``.

        ``reset_camera()`` auto-fits the scene's world-space bounding box, and
        the screen-facing billboard text inflates that box, which would push
        the view out.  Re-aiming at the focal point at a shorter distance keeps
        the default view snug around the dome.
        """
        try:
            cam = self.plotter.camera
            fp = np.array(cam.focal_point)
            pos = np.array(cam.position)
            d = pos - fp
            cam.position = tuple(fp + d * factor)
            cam.SetParallelScale(cam.GetParallelScale() * factor)
            self.plotter.render()
        except Exception:
            pass

    def _view_top(self):
        self.plotter.view_xy(negative=True)
        self.plotter.set_viewup((0, 1, 0))
        self.plotter.render()

    def _view_north(self):
        self._look_toward(0.0)

    def _view_south(self):
        self._look_toward(180.0)

    def _view_east(self):
        self._look_toward(90.0)

    def _view_west(self):
        self._look_toward(270.0)

    def _look_toward(self, az):
        from_xyz = alt_az_to_xyz(8.0, az, 3.2)
        self.plotter.camera_position = [tuple(from_xyz), (0, 0, 0.3), (0, 0, 1)]
        self.plotter.render()

    def _toggle(self, enabled, key):
        if key == "grid":
            self._show_grid = enabled
            self._apply_visibility(self._grid_actors, enabled)
        elif key == "moon_path":
            self._show_moon_path = enabled
            self._apply_visibility([self._moon_path], enabled)
        elif key == "sun_path":
            self._show_sun_path = enabled
            self._apply_visibility([self._sun_path], enabled)
        elif key == "labels":
            self._show_labels = enabled
            self._apply_visibility(self._label_actors, enabled)
        self.plotter.render()

    def _apply_visibility(self, actors, enabled):
        for actor in actors:
            if actor is not None:
                try:
                    actor.SetVisibility(bool(enabled))
                except Exception:
                    pass

    def teardown(self):
        try:
            self.plotter.close()
        except Exception:
            pass
