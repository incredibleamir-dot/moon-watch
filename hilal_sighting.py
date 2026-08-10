"""Moon Watch - a moon sighting system for Ramadan, Eid and every hilal.

A colourful, futuristic pygame app (same neon look as the Solar System Kids
explorer) that answers one question: *can we see the new crescent moon this
evening?*

  * Sighting view  - sky diagram of the setting Sun and young crescent,
    rendered crescent (true illuminated fraction & bright-limb orientation),
    "moon altitude at sunset over the next 14 evenings" chart and a verdict
    for the MABIMS 2023, Danjon and Odeh (2006) criteria.
  * Analysis views - HilalPy-style condition / equation / threshold charts
    against the bundled 8000+ sighting database.

Calculations come from ``astronomy.py`` (built on the vendored ``solarsystem``
library); database analysis comes from ``analysis.py`` (adapted from HilalPy).
"""

import math
import os
import random
import sys
import datetime
import threading

ROOT = os.path.dirname(os.path.abspath(__file__))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)
VENDOR = os.path.join(ROOT, "vendor")
if os.path.isdir(VENDOR) and VENDOR not in sys.path:
    sys.path.insert(0, VENDOR)

import pygame

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

import astronomy
import analysis
import verification
import islamic

# ---------------------------------------------------------------------------
# Layout
W0, H0 = 1280, 800
W, H = W0, H0
BAR_H = 68
PANEL_W = 320
CANVAS_H = H - BAR_H
VIEW_W = W - PANEL_W
FPS = 60

SKY_TOP = 18
SKY_H = 348
CHART_TOP = SKY_TOP + SKY_H + 12
CHART_H = CANVAS_H - CHART_TOP - 16

# ---------------------------------------------------------------------------
# Palette
C_BG = (4, 7, 18)
C_CYAN = (0, 232, 255)
C_CYAN_DIM = (38, 140, 180)
C_MAGENTA = (255, 70, 170)
C_AMBER = (255, 208, 96)
C_GREEN = (110, 255, 150)
C_RED = (255, 96, 96)
C_TEXT = (226, 236, 252)
C_DIM = (138, 152, 188)
ORBIT_COLOR = (52, 70, 130)
C_TASKBAR_EDGE = (64, 96, 180)
PANEL_FILL = (12, 18, 44, 178)
PANEL_LINE = (0, 232, 255, 130)
TASKBAR_BG = (9, 13, 32)
ICON_COLOR = (205, 244, 255)

SUN_COLOR = (255, 214, 92)
MOON_LIT = (240, 240, 236)
MOON_DARK = (24, 32, 58)

BTN_W = 46
BTN_GAP = 8
BTN_RADIUS = 12

# ---------------------------------------------------------------------------
# City presets
CITIES = [
    ("Ludhiana, India", 30.90, 75.85, 5.5),
    ("Roorkee, India", 29.87, 77.89, 5.5),
    ("Delhi, India", 28.61, 77.21, 5.5),
    ("Makkah, Saudi Arabia", 21.42, 39.83, 3.0),
    ("Karachi, Pakistan", 24.86, 67.01, 5.0),
    ("Kuala Lumpur, Malaysia", 3.14, 101.69, 8.0),
    ("Jakarta, Indonesia", -6.21, 106.85, 7.0),
    ("London, UK", 51.51, -0.13, 0.0),
    ("New York, USA", 40.71, -74.01, -5.0),
]

MABIMS_ARCL = 6.4
MABIMS_ALT = 3.0
DANJON_ARCL = 7.0

VIEWS = {
    "sight": ("SIGHTING", "Crescent prediction"),
    "cond": ("CONDITION", "Criteria vs database"),
    "equa": ("EQUATION", "Boundary curve test"),
    "thres": ("THRESHOLD", "Minimum observed values"),
    "verify": ("VERIFY", "Check our math"),
}

ANALYSIS_X_CHOICES = ["ArcL", "MAlt", "ArcV", "W", "LT", "MA"]

COND_EQUATION = ("-0.5058 * x + 0.0059 * x**2 + -0.000021 * x**3 + 10.8467")


def lerp_color(a, b, t):
    return tuple(int(a[i] + (b[i] - a[i]) * t) for i in range(3))


def sign_num(v):
    return "+%.2f" % v if v >= 0 else "%.2f" % v


def fmt_time(dt):
    return dt.strftime("%H:%M") if dt else "--:--"


def fmt_date(dt):
    return dt.strftime("%A, %d %B %Y")


# ---------------------------------------------------------------------------
# Icon painters
def _poly(surf, pts, color):
    pygame.draw.polygon(surf, color, [(int(x), int(y)) for x, y in pts])


def _icon_prev(surf, s):
    _poly(surf, [(0.70 * s, 0.20 * s), (0.70 * s, 0.80 * s),
                 (0.30 * s, 0.50 * s)], ICON_COLOR)
    pygame.draw.rect(surf, ICON_COLOR,
                     (int(0.20 * s), int(0.20 * s), int(0.10 * s), int(0.60 * s)))


def _icon_next(surf, s):
    _poly(surf, [(0.30 * s, 0.20 * s), (0.30 * s, 0.80 * s),
                 (0.70 * s, 0.50 * s)], ICON_COLOR)
    pygame.draw.rect(surf, ICON_COLOR,
                     (int(0.70 * s), int(0.20 * s), int(0.10 * s), int(0.60 * s)))


def _icon_today(surf, s):
    pygame.draw.circle(surf, ICON_COLOR,
                       (int(0.5 * s), int(0.5 * s)), int(0.33 * s), int(0.09 * s))
    pygame.draw.line(surf, ICON_COLOR, (int(0.5 * s), int(0.5 * s)),
                     (int(0.5 * s), int(0.28 * s)), int(0.08 * s))
    pygame.draw.line(surf, ICON_COLOR, (int(0.5 * s), int(0.5 * s)),
                     (int(0.66 * s), int(0.58 * s)), int(0.08 * s))


def _icon_gear(surf, s):
    pygame.draw.circle(surf, ICON_COLOR,
                       (int(0.5 * s), int(0.5 * s)), int(0.18 * s), 0)
    for i in range(8):
        a = math.pi * 2 * i / 8
        x1 = int(0.5 * s + math.cos(a) * 0.24 * s)
        y1 = int(0.5 * s + math.sin(a) * 0.24 * s)
        x2 = int(0.5 * s + math.cos(a) * 0.40 * s)
        y2 = int(0.5 * s + math.sin(a) * 0.40 * s)
        pygame.draw.line(surf, ICON_COLOR, (x1, y1), (x2, y2), int(0.10 * s))


def _icon_crescent(surf, s):
    pygame.draw.circle(surf, ICON_COLOR, (int(0.46 * s), int(0.5 * s)),
                       int(0.30 * s), 0)
    pygame.draw.circle(surf, (10, 14, 34), (int(0.64 * s), int(0.44 * s)),
                       int(0.26 * s), 0)


def _icon_scatter(surf, s):
    pts = [(0.30, 0.32), (0.58, 0.62), (0.72, 0.34),
           (0.44, 0.72), (0.78, 0.76)]
    for x, y in pts:
        pygame.draw.circle(surf, ICON_COLOR,
                           (int(x * s), int(y * s)), int(0.055 * s), 0)
    pygame.draw.line(surf, ICON_COLOR, (int(0.22 * s), int(0.18 * s)),
                     (int(0.22 * s), int(0.82 * s)), int(0.06 * s))
    pygame.draw.line(surf, ICON_COLOR, (int(0.18 * s), int(0.82 * s)),
                     (int(0.82 * s), int(0.82 * s)), int(0.06 * s))


def _icon_curve(surf, s):
    pygame.draw.line(surf, ICON_COLOR, (int(0.22 * s), int(0.18 * s)),
                     (int(0.22 * s), int(0.82 * s)), int(0.06 * s))
    pygame.draw.line(surf, ICON_COLOR, (int(0.18 * s), int(0.82 * s)),
                     (int(0.82 * s), int(0.82 * s)), int(0.06 * s))
    prev = None
    for i in range(40):
        t = i / 39.0
        x = 0.24 + 0.72 * t
        y = 0.80 - 0.62 * (0.2 + 0.8 * t) ** 1.6
        p = (int(x * s), int(y * s))
        if prev:
            pygame.draw.line(surf, ICON_COLOR, prev, p, int(0.055 * s))
        prev = p


def _icon_box(surf, s):
    x0, x1 = int(0.30 * s), int(0.70 * s)
    for i, w in enumerate((0.30, 0.46, 0.62, 0.78)):
        x = int(0.22 * s + (i + 0.5) * 0.14 * s)
        h = int(w * s * 0.22)
        pygame.draw.rect(surf, ICON_COLOR, (x, int(0.5 * s) - h // 2, int(0.10 * s), h), 0)
    pygame.draw.line(surf, ICON_COLOR, (x0, int(0.18 * s)), (x0, int(0.82 * s)), int(0.05 * s))
    pygame.draw.line(surf, ICON_COLOR, (x1, int(0.18 * s)), (x1, int(0.82 * s)), int(0.05 * s))
    pygame.draw.line(surf, ICON_COLOR, (x0, int(0.5 * s)), (x1, int(0.5 * s)), int(0.05 * s))


def _icon_about(surf, s):
    pygame.draw.circle(surf, ICON_COLOR,
                       (int(0.5 * s), int(0.5 * s)), int(0.34 * s), int(0.08 * s))
    pygame.draw.circle(surf, ICON_COLOR, (int(0.5 * s), int(0.34 * s)), int(0.06 * s))
    pygame.draw.line(surf, ICON_COLOR, (int(0.5 * s), int(0.44 * s)),
                     (int(0.5 * s), int(0.68 * s)), int(0.09 * s))


def _icon_fullscreen(surf, s):
    m, r = int(0.12 * s), int(0.08 * s)
    for (x0, y0, x1, y1) in [(m, m, int(0.38 * s), m), (m, m, m, int(0.38 * s)),
                             (int(0.62 * s), m, int(0.88 * s), m),
                             (int(0.88 * s), m, int(0.88 * s), int(0.38 * s)),
                             (m, int(0.62 * s), m, int(0.88 * s)),
                             (m, int(0.88 * s), int(0.38 * s), int(0.88 * s)),
                             (int(0.62 * s), int(0.88 * s), int(0.88 * s), int(0.88 * s)),
                             (int(0.88 * s), int(0.62 * s), int(0.88 * s), int(0.88 * s))]:
        pygame.draw.line(surf, ICON_COLOR, (x0, y0), (x1, y1), r)


def _icon_fit(surf, s):
    for x in (int(0.24 * s), int(0.76 * s)):
        pygame.draw.line(surf, ICON_COLOR, (x, int(0.20 * s)), (x, int(0.80 * s)), int(0.06 * s))
    for y in (int(0.20 * s), int(0.80 * s)):
        pygame.draw.line(surf, ICON_COLOR, (int(0.24 * s), y), (int(0.76 * s), y), int(0.06 * s))
    pygame.draw.circle(surf, ICON_COLOR, (int(0.5 * s), int(0.5 * s)), int(0.13 * s), int(0.07 * s))


def _icon_check(surf, s):
    pts = [(0.22 * s, 0.52 * s), (0.42 * s, 0.70 * s), (0.80 * s, 0.28 * s)]
    pygame.draw.lines(surf, ICON_COLOR, False,
                      [(int(x), int(y)) for x, y in pts], int(0.09 * s))
    pygame.draw.circle(surf, ICON_COLOR, (int(0.5 * s), int(0.5 * s)),
                       int(0.40 * s), int(0.07 * s))


def _icon_power(surf, s):
    c = (int(0.5 * s), int(0.5 * s))
    pygame.draw.circle(surf, ICON_COLOR, c, int(0.32 * s), int(0.08 * s))
    pygame.draw.line(surf, ICON_COLOR, (c[0], int(0.16 * s)), (c[0], int(0.5 * s)),
                     int(0.08 * s))


def _icon_calendar(surf, s):
    x0, y0 = int(0.20 * s), int(0.26 * s)
    w, h = int(0.60 * s), int(0.50 * s)
    pygame.draw.rect(surf, ICON_COLOR, (x0, y0, w, h), int(0.07 * s))
    for yy in (int(0.40 * s), int(0.52 * s), int(0.64 * s)):
        pygame.draw.line(surf, ICON_COLOR, (x0, yy), (x0 + w, yy), int(0.05 * s))
    for xx in (int(0.33 * s), int(0.48 * s), int(0.63 * s)):
        pygame.draw.line(surf, ICON_COLOR, (xx, y0), (xx, y0 + h), int(0.05 * s))
    for xx in (int(0.30 * s), int(0.70 * s)):
        pygame.draw.line(surf, ICON_COLOR, (xx, int(0.18 * s)), (xx, int(0.30 * s)),
                         int(0.08 * s))



# ---------------------------------------------------------------------------
class InputBox:
    def __init__(self, rect, text="", numeric=True):
        self.rect = pygame.Rect(rect)
        self.text = text
        self.active = False
        self.numeric = numeric

    def handle_event(self, event):
        if event.type == pygame.MOUSEBUTTONDOWN:
            self.active = self.rect.collidepoint(event.pos)
            return
        if event.type == pygame.KEYDOWN and self.active:
            if event.key == pygame.K_BACKSPACE:
                self.text = self.text[:-1]
            elif event.key == pygame.K_RETURN:
                self.active = False
            elif event.key == pygame.K_MINUS:
                if self.text == "" or self.text[0] != "-":
                    self.text = "-" + self.text
            elif event.unicode and event.unicode in "0123456789.-":
                self.text += event.unicode


# ---------------------------------------------------------------------------
class HilalApp:
    def __init__(self):
        pygame.init()
        self.screen = pygame.display.set_mode((W, H))
        pygame.display.set_caption("Moon Watch - Moon Sighting System")
        self.clock = pygame.time.Clock()

        self.font_title = self.get_font(28)
        self.font_section = self.get_font(20)
        self.font_body = self.get_font(17)
        self.font_small = self.get_font(14)
        self.font_tiny = self.get_font(12)
        self.font_big = self.get_font(24)
        self.font_label = self.get_font(15)
        self.font_tooltip = self.get_font(13)

        now = datetime.datetime.now()
        self.date = now.replace(hour=0, minute=0, second=0, microsecond=0)
        self.city, self.lat, self.lon, self.tz = CITIES[0]
        self.view = "sight"
        self.analysis_x = "ArcL"
        self.fullscreen = False
        self.show_setup = False
        self.show_about = False
        self.show_dates = False
        self.dates_data = None

        self.inputs = {}
        self.hover_btn = None
        self.pressed_btn = None

        self.stars = self.make_stars()
        self.scanlines = self.make_scanlines()
        self.divider = self.make_divider(PANEL_W - 48)
        self.taskbar_grad = self.make_taskbar_grad()
        self.title_surf = self.neon("MOON WATCH", self.font_title, C_CYAN)
        self.icons = self.make_icons()
        self.button_glow = self.make_button_glow()
        self.buttons = self.build_buttons()

        self.caches = {}
        self.report = None
        self.report_key = None
        self.series14 = []
        self.altseries = None
        self.analysis_results = {}
        self.chart_surfs = {}
        self.setup_surfs = {}
        self.thumb = None
        self.crescent_cache = {}
        self.cursor = pygame.SYSTEM_CURSOR_ARROW
        self.verify = {
            "hz_state": "idle", "hz": None, "hz_error": None,
            "obs_state": "idle", "obs": None, "obs_error": None,
        }
        self.build_inputs()
        self.refresh()

    def start_checks(self):
        if self.verify["obs_state"] in ("idle", "done"):
            self.verify["obs_state"] = "idle"
            self.verify["obs"] = None
            self.run_obs_check()
        if self.verify["hz_state"] == "idle":
            self.run_hz_check()

    def run_hz_check(self):
        self.verify["hz_state"] = "running"
        self.verify["hz_error"] = None

        def work():
            try:
                res = verification.ephemeris_check(
                    self.date, self.lat, self.lon, self.tz)
                self.verify["hz"] = res
                self.verify["hz_state"] = "done" if res.get("ok") else "error"
                if not res.get("ok"):
                    self.verify["hz_error"] = res.get("error")
            except Exception as exc:
                self.verify["hz_state"] = "error"
                self.verify["hz_error"] = str(exc)
        threading.Thread(target=work, daemon=True).start()

    def run_obs_check(self):
        if self.verify["obs_state"] != "idle":
            return
        self.verify["obs_state"] = "running"
        self.verify["obs_error"] = None

        def work():
            try:
                res = verification.observation_check(sample=500)
                self.verify["obs"] = res
                self.verify["obs_state"] = "done"
            except Exception as exc:
                self.verify["obs_state"] = "error"
                self.verify["obs_error"] = str(exc)
        threading.Thread(target=work, daemon=True).start()

    # ------------------------------------------------------------ helpers
    def get_font(self, size):
        for name in ("bahnschrift", "segoeui", "segoe ui", "consolas"):
            try:
                return pygame.font.SysFont(name, size)
            except Exception:
                continue
        return pygame.font.Font(None, size)

    def neon(self, text, font, color):
        base = font.render(text, True, color)
        w, h = base.get_size()
        out = pygame.Surface((w + 12, h + 12), pygame.SRCALPHA)
        small = pygame.transform.smoothscale(base, (max(1, w // 2), max(1, h // 2)))
        blur = pygame.transform.smoothscale(small, (w, h))
        blur.set_alpha(110)
        out.blit(blur, (6, 6))
        out.blit(base, (6, 6))
        return out

    def cached(self, key, font, text, color):
        item = self.caches.get((key, text, color))
        if item is None:
            item = font.render(text, True, color)
            self.caches[(key, text, color)] = item
            if len(self.caches) > 4000:
                self.caches.clear()
        return item

    def make_stars(self):
        rng = random.Random(11)
        return [(rng.randrange(0, W), rng.randrange(0, CANVAS_H),
                 rng.choice((1, 1, 1, 2)), rng.random() * math.tau)
                for _ in range(160)]

    def make_scanlines(self):
        s = pygame.Surface((PANEL_W, CANVAS_H), pygame.SRCALPHA)
        for y in range(0, CANVAS_H, 4):
            pygame.draw.line(s, (0, 0, 0, 24), (0, y), (PANEL_W, y))
        return s

    def make_divider(self, w):
        s = pygame.Surface((w, 2), pygame.SRCALPHA)
        for x in range(w):
            t = x / max(1, w - 1)
            pygame.draw.line(s, (0, 232, 255, int(140 * (1 - t))), (x, 0), (x, 1))
        return s

    def make_taskbar_grad(self):
        s = pygame.Surface((W, BAR_H))
        top, bottom = (11, 16, 40), (5, 8, 22)
        for y in range(BAR_H):
            t = y / max(1, BAR_H - 1)
            pygame.draw.line(s, lerp_color(top, bottom, t), (0, y), (W, y))
        return s

    def make_button_glow(self):
        s = pygame.Surface((BTN_W + 14, BTN_W + 14), pygame.SRCALPHA)
        pygame.draw.rect(s, (0, 232, 255, 36),
                         (3, 3, BTN_W + 8, BTN_W + 8), border_radius=BTN_RADIUS + 4)
        pygame.draw.rect(s, (0, 232, 255, 70),
                         (7, 7, BTN_W, BTN_W), border_radius=BTN_RADIUS)
        return s

    def make_icons(self):
        def mk(painter):
            big = pygame.Surface((104, 104), pygame.SRCALPHA)
            painter(big, 104)
            return pygame.transform.smoothscale(big, (26, 26))
        return {
            "prev": mk(_icon_prev), "next": mk(_icon_next), "today": mk(_icon_today),
            "setup": mk(_icon_gear), "sight": mk(_icon_crescent),
            "cond": mk(_icon_scatter), "equa": mk(_icon_curve),
            "thres": mk(_icon_box),             "verify": mk(_icon_check),
            "about": mk(_icon_about),
            "calendar": mk(_icon_calendar),
            "fullscreen": mk(_icon_fullscreen), "fit": mk(_icon_fit),
            "quit": mk(_icon_power),
        }

    def wrap_text(self, text, font, max_w):
        words = text.split(" ")
        lines, cur = [], ""
        for w in words:
            trial = (cur + " " + w).strip()
            if font.size(trial)[0] <= max_w or not cur:
                cur = trial
            else:
                lines.append(cur)
                cur = w
        if cur:
            lines.append(cur)
        return lines

    # ------------------------------------------------------------- buttons
    def build_buttons(self):
        defs = [
            ("prev", "prev", "Previous day"),
            ("next", "next", "Next day"),
            ("today", "today", "Back to today"),
            ("setup", "setup", "Date & location"),
            ("sight", "sight", "Moon sighting"),
            ("cond", "cond", "Condition analysis"),
            ("equa", "equa", "Equation analysis"),
            ("thres", "thres", "Threshold analysis"),
            ("verify", "verify", "Verify our math (NASA + records)"),
            ("dates", "calendar", "Ramadan & Eid dates"),
            ("about", "about", "About"),
            ("fullscreen", "fullscreen", "Fullscreen (F11)"),
            ("fit", "fit", "Reset view"),
            ("quit", "quit", "Quit the app"),
        ]
        btns = []
        x, y = 80, CANVAS_H + (BAR_H - BTN_W) // 2
        for bid, icon, tip in defs:
            btns.append({"id": bid, "icon": icon, "tip": tip,
                         "rect": pygame.Rect(x, y, BTN_W, BTN_W)})
            x += BTN_W + BTN_GAP
        return btns

    def button_at(self, mx, my):
        for b in self.buttons:
            if b["rect"].collidepoint(mx, my):
                return b
        return None

    def toggle_fullscreen(self):
        global W, H, CANVAS_H, VIEW_W
        self.fullscreen = not self.fullscreen
        if self.fullscreen:
            info = pygame.display.Info()
            W, H = info.current_w, info.current_h
        else:
            W, H = W0, H0
        CANVAS_H = H - BAR_H
        VIEW_W = W - PANEL_W
        flags = pygame.FULLSCREEN if self.fullscreen else 0
        self.screen = pygame.display.set_mode((W, H), flags)
        self.stars = self.make_stars()
        self.taskbar_grad = self.make_taskbar_grad()
        self.buttons = self.build_buttons()
        self.caches.clear()
        self.invalidate_analysis()

    # ------------------------------------------------------------ actions
    def activate(self, bid):
        if bid == "prev":
            self.date -= datetime.timedelta(days=1)
            self.refresh()
        elif bid == "next":
            self.date += datetime.timedelta(days=1)
            self.refresh()
        elif bid == "today":
            self.date = datetime.datetime.now().replace(hour=0, minute=0,
                                                        second=0, microsecond=0)
            self.refresh()
        elif bid == "setup":
            self.show_setup = not self.show_setup
            self.show_about = False
            self.show_dates = False
            self.build_inputs()
        elif bid in ("sight", "cond", "equa", "thres", "verify"):
            self.view = bid
            self.show_setup = False
            self.show_about = False
            self.show_dates = False
            if bid == "verify":
                self.start_checks()
        elif bid == "about":
            self.show_about = not self.show_about
            self.show_dates = False
        elif bid == "dates":
            self.show_dates = not self.show_dates
            self.show_about = False
            self.show_setup = False
            if self.show_dates:
                self.dates_data = islamic.events(
                    self.lat, self.lon, self.tz, self.date)
        elif bid == "fullscreen":
            self.toggle_fullscreen()
        elif bid == "fit":
            self.refresh(force=True)
        elif bid == "quit":
            pygame.event.post(pygame.event.Event(pygame.QUIT))

    # ----------------------------------------------------------- computation
    def refresh(self, force=False):
        key = (self.date.toordinal(), self.lat, self.lon, self.tz, self.view)
        if not force and key == self.report_key:
            return
        self.report_key = key
        self.report = astronomy.evening_report(self.date, self.lat, self.lon,
                                               self.tz)
        self.series14 = astronomy.sunset_altitudes_14days(
            self.date, self.lat, self.lon, self.tz, 14)
        if self.report:
            self.altseries = astronomy.altitude_series(
                self.report, self.lat, self.lon, self.tz, 12)
        else:
            self.altseries = None
        if self.verify["hz_state"] == "done":
            self.verify["hz_state"] = "stale"
        self.invalidate_analysis()

    def invalidate_analysis(self):
        self.analysis_results = {}
        self.chart_surfs = {}

    def analysis_result(self, kind):
        if kind in self.analysis_results:
            return self.analysis_results[kind]
        if kind == "cond":
            res = analysis.condition_analysis()
        elif kind == "equa":
            res = analysis.equation_analysis()
        else:
            res = analysis.threshold_analysis(self.analysis_x)
        self.analysis_results[kind] = res
        return res

    # ------------------------------------------------------------------ run
    def run(self):
        running = True
        dt = 0.0
        while running:
            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    running = False
                elif self.show_setup:
                    self.handle_setup_event(event)
                elif event.type == pygame.KEYDOWN:
                    if event.key == pygame.K_ESCAPE:
                        if self.show_about:
                            self.show_about = False
                        elif self.show_dates:
                            self.show_dates = False
                        elif self.fullscreen:
                            self.toggle_fullscreen()
                    elif event.key in (pygame.K_i,):
                        self.show_about = not self.show_about
                        self.show_dates = False
                    elif event.key in (pygame.K_d,):
                        self.activate("dates")
                    elif not self.show_about:
                        if event.key == pygame.K_LEFT:
                            self.activate("prev")
                        elif event.key == pygame.K_RIGHT:
                            self.activate("next")
                        elif event.key == pygame.K_t:
                            self.activate("today")
                        elif event.key in (pygame.K_1, pygame.K_s):
                            self.activate("sight")
                        elif event.key in (pygame.K_2, pygame.K_c):
                            self.activate("cond")
                        elif event.key in (pygame.K_3, pygame.K_e):
                            self.activate("equa")
                        elif event.key in (pygame.K_4, pygame.K_h):
                            self.activate("thres")
                        elif event.key in (pygame.K_5, pygame.K_v):
                            self.activate("verify")
                        elif event.key == pygame.K_x and self.view == "thres":
                            self.analysis_x = ANALYSIS_X_CHOICES[
                                (ANALYSIS_X_CHOICES.index(self.analysis_x) + 1)
                                % len(ANALYSIS_X_CHOICES)]
                            self.invalidate_analysis()
                        elif event.key == pygame.K_r and self.view == "verify":
                            self.run_hz_check()
                        elif event.key == pygame.K_F11:
                            self.toggle_fullscreen()
                elif event.type == pygame.MOUSEBUTTONDOWN:
                    b = self.button_at(*event.pos)
                    if b is not None:
                        self.pressed_btn = b["id"]
                elif event.type == pygame.MOUSEBUTTONUP:
                    if self.pressed_btn:
                        b = self.button_at(*event.pos)
                        if b is not None and b["id"] == self.pressed_btn:
                            self.activate(self.pressed_btn)
                        self.pressed_btn = None

            self.hover_btn = self.button_at(*pygame.mouse.get_pos())

            want = pygame.SYSTEM_CURSOR_ARROW
            if self.hover_btn or self.pressed_btn:
                want = pygame.SYSTEM_CURSOR_HAND
            if want != self.cursor:
                self.cursor = want
                pygame.mouse.set_cursor(want)

            self.draw()
            pygame.display.flip()
            dt = self.clock.tick(FPS) / 1000.0
        pygame.quit()

    # ------------------------------------------------------------ background
    def draw_background(self):
        self.screen.fill(C_BG)
        tick = pygame.time.get_ticks() * 0.002
        for x, y, size, phase in self.stars:
            a = int(60 + 120 * (0.5 + 0.5 * math.sin(tick + phase)))
            pygame.draw.circle(self.screen, (a, a, min(255, a + 24)), (x, y), size)

    def draw_hud_corners(self):
        col = (0, 190, 255)
        L = 20
        corners = [
            [(10, 10), (10 + L, 10), (10, 10 + L)],
            [(VIEW_W - 10, 10), (VIEW_W - 10 - L, 10), (VIEW_W - 10, 10 + L)],
        ]
        for (ax, ay), (bx, by), (cx, cy) in corners:
            pygame.draw.line(self.screen, col, (ax, ay), (bx, by), 2)
            pygame.draw.line(self.screen, col, (bx, by), (cx, cy), 2)

    # ------------------------------------------------------------- drawing
    def draw(self):
        self.draw_background()
        self.draw_hud_corners()
        if self.view == "sight":
            self.draw_sight_canvas()
        elif self.view == "verify":
            self.draw_verify_canvas()
        else:
            self.draw_analysis_canvas()
        self.draw_panel()
        self.draw_taskbar()
        self.draw_tooltip()
        if self.show_setup:
            self.draw_setup_modal()
        if self.show_about:
            self.draw_about()
        if self.show_dates:
            self.draw_dates()
        pygame.draw.line(self.screen, C_TASKBAR_EDGE, (0, CANVAS_H), (W, CANVAS_H))

    # ===================================================================
    # Sighting view
    # ===================================================================
    def draw_sight_canvas(self):
        if self.report is None:
            msg = "No sunset on this date at this location."
            img = self.font_section.render(msg, True, C_AMBER)
            self.screen.blit(img, img.get_rect(center=(VIEW_W // 2, CANVAS_H // 2)))
            return
        self.draw_sky_diagram(self.report)
        self.draw_altitude_chart()

    def _sky_geo(self, rect, az, alt):
        x = rect[0] + (az - 180.0) / 180.0 * rect[2]
        y = rect[1] + (1.0 - max(0.0, min(1.0, alt / 40.0))) * rect[3]
        return x, y

    def draw_sky_diagram(self, report):
        rect = pygame.Rect(20, SKY_TOP, VIEW_W - 40, SKY_H)
        top_col = (8, 16, 44)
        bot_col = (62, 42, 86)
        horizon_y = rect.bottom - 6
        alt_top = rect.top + 4

        for yy in range(rect.top, rect.bottom):
            t = (yy - rect.top) / max(1, rect.height - 1)
            near = max(0.0, min(1.0, (horizon_y - yy) / (horizon_y - alt_top)))
            col = lerp_color(top_col, bot_col, t * 0.55 + near * 0.45)
            pygame.draw.line(self.screen, col, (rect.left, yy), (rect.right, yy))

        ground = pygame.Surface((rect.width, rect.bottom - horizon_y),
                                pygame.SRCALPHA)
        ground.fill((22, 16, 30, 255))
        for gx in range(rect.width):
            f = gx / max(1, rect.width - 1)
            ground.fill((30, 18, 26, 255),
                        (gx, 0, 1, int(5 * (1 - f * f))))
        self.screen.blit(ground, (rect.left, horizon_y))

        sun_az_x = int(self._sky_geo(rect, report["s_az"], 0)[0])
        for rad, alpha in ((95, 26), (62, 40), (38, 60)):
            g = pygame.Surface((rad * 2, rad * 2), pygame.SRCALPHA)
            pygame.draw.circle(g, (255, 150, 60, alpha), (rad, rad), rad)
            self.screen.blit(g, (sun_az_x - rad, horizon_y - rad * 3 // 5))

        pygame.draw.line(self.screen, (0, 232, 255, 110),
                         (rect.left, horizon_y), (rect.right, horizon_y), 1)

        for alt in (10, 20, 30):
            y = alt_top + (1.0 - alt / 40.0) * (horizon_y - alt_top)
            pygame.draw.line(self.screen, (40, 66, 110),
                             (rect.left, int(y)), (rect.right, int(y)), 1)
            img = self.cached("sky", self.font_tiny, "%d°" % alt, C_DIM)
            self.screen.blit(img, (rect.left + 4, int(y) - img.get_height() // 2))

        az_labels = [("S", 180), ("SW", 225), ("W", 270), ("NW", 315), ("N", 360)]
        for label, az in az_labels:
            x = int(self._sky_geo(rect, az, 0)[0])
            img = self.cached("sky", self.font_tiny, label, C_DIM)
            self.screen.blit(img, (x - img.get_width() // 2, horizon_y + 6))

        moon_trail = self.altseries or ([], [], [])
        ts, alts, s_alts = moon_trail
        trail_pts = []
        for t, alt in zip(ts, alts):
            trail_pts.append(self._sky_geo(rect, report["s_az"] + 0.0, alt))
        if len(trail_pts) > 1:
            pygame.draw.lines(self.screen, (120, 160, 220), False,
                              [tuple(int(v) for v in p) for p in trail_pts], 1)
            step = max(1, len(trail_pts) // 6)
            for i in range(0, len(trail_pts), step):
                px, py = trail_pts[i]
                if horizon_y - py > 12:
                    pygame.draw.circle(self.screen, (150, 185, 235),
                                       (int(px), int(py)), 2)

        sun_y = self._sky_geo(rect, report["s_az"],
                              max(-8.0, report["s_alt"]))[1]
        sun_y = min(sun_y, horizon_y)
        sun_r = 13
        glow = pygame.Surface((60, 60), pygame.SRCALPHA)
        pygame.draw.circle(glow, (255, 170, 60, 70), (30, 30), 26)
        pygame.draw.circle(glow, (255, 214, 92, 255), (30, 30), sun_r)
        self.screen.blit(glow, (int(sun_az_x) - 30, int(sun_y) - 30))
        lab = self.cached("sky", self.font_tiny, "SUNSET", C_AMBER)
        self.screen.blit(lab, (int(sun_az_x) - lab.get_width() // 2,
                               int(sun_y) - 44))

        moon_x, moon_y = self._sky_geo(rect, report["m_az"], max(-8.0, report["m_alt"]))
        moon_y = max(moon_y, alt_top)
        pygame.draw.line(self.screen, (70, 110, 170),
                         (int(moon_x), int(moon_y)),
                         (int(moon_x), horizon_y + 2), 1)
        pygame.draw.line(self.screen, (70, 110, 170),
                         (int(moon_x) - 4, horizon_y), (int(moon_x) + 4, horizon_y), 1)
        lit = report["illum"]
        if lit <= 0.03:
            r_small = 6
            pygame.draw.circle(self.screen, MOON_LIT, (int(moon_x), int(moon_y)), r_small)
        else:
            dx = sun_az_x - moon_x
            dy = (sun_y if sun_y < horizon_y else horizon_y - 8) - moon_y
            rot = math.degrees(math.atan2(dy, dx))
            self.draw_crescent(self.screen, int(moon_x), int(moon_y), 15,
                               lit, rot, MOON_LIT, MOON_DARK)
        pygame.draw.circle(self.screen, C_CYAN, (int(moon_x), int(moon_y)), 18, 1)
        lab = self.cached("sky", self.font_tiny, "MOON", C_CYAN)
        self.screen.blit(lab, (int(moon_x) - lab.get_width() // 2,
                               int(moon_y) - 28))

        info1 = "SUNSET %s   |   MOONSET %s" % (fmt_time(report["sunset"]),
                                                fmt_time(report["moonset"]))
        info2 = "MOON ALT %s°  ARC LIGHT %s°  AGE %s" % (
            round(report["m_alt_sunset"], 1), round(report["arc_l_sunset"], 1),
            self._fmt_age(report["age_sunset"]))
        for i, txt in enumerate((info1, info2)):
            img = self.cached("sky", self.font_small, txt, C_TEXT)
            self.screen.blit(img, (rect.left + 10, rect.top + 6 + i * 20))

        title = self.cached("sky", self.font_section, "EVENING SKY - looking West",
                            C_CYAN)
        self.screen.blit(title, title.get_rect(centerx=rect.centerx, top=rect.top + 4))

    def draw_altitude_chart(self):
        rect = pygame.Rect(20, CHART_TOP, VIEW_W - 40, CHART_H)
        title = self.cached("chart", self.font_section,
                            "MOON ALTITUDE AT SUNSET - next 14 evenings", C_CYAN)
        self.screen.blit(title, (rect.x, rect.y))

        plot = pygame.Rect(rect.x + 46, rect.y + 30, rect.width - 52, rect.height - 56)
        pygame.draw.rect(self.screen, (8, 13, 32), plot)
        pygame.draw.rect(self.screen, (40, 66, 110), plot, 1)

        def mapy(alt):
            return plot.bottom - (max(-90, min(90, alt)) + 90) / 180.0 * plot.height

        zero_y = int(mapy(0))
        thresh_y = int(mapy(MABIMS_ALT))
        pygame.draw.line(self.screen, (60, 90, 140), (plot.left, zero_y),
                         (plot.right, zero_y), 1)
        pygame.draw.line(self.screen, (0, 232, 255, 90), (plot.left, thresh_y),
                         (plot.right, thresh_y), 1)
        for alt in (-90, -45, 0, 45, 90):
            y = int(mapy(alt))
            img = self.cached("chart", self.font_tiny, "%d°" % alt, C_DIM)
            self.screen.blit(img, (plot.x - img.get_width() - 4, y - img.get_height() // 2))
        lab = self.cached("chart", self.font_tiny, "MABIMS 3°", C_CYAN)
        self.screen.blit(lab, (plot.right - lab.get_width() - 4, thresh_y + 4))

        n = len(self.series14)
        if n:
            bw = plot.width / n
            today_idx = None
            for i, (d, alt) in enumerate(self.series14):
                if alt is None:
                    continue
                if d.date() == self.date.date():
                    today_idx = i
                h = plot.bottom - int(mapy(alt))
                x = plot.x + int(i * bw) + int(bw * 0.18)
                w = max(3, int(bw * 0.64))
                visible = alt >= MABIMS_ALT
                col = C_GREEN if visible else C_AMBER
                if i == today_idx:
                    col = C_CYAN
                pygame.draw.rect(self.screen, col, (x, plot.bottom - h, w, h))
                pygame.draw.rect(self.screen, (255, 255, 255, 60),
                                 (x, plot.bottom - h, w, h), 1)
                if i == today_idx:
                    img = self.cached("chart", self.font_tiny, "TODAY", C_CYAN)
                    self.screen.blit(img, (x + w // 2 - img.get_width() // 2,
                                           plot.bottom - h - 16))
                lab = self.cached("chart", self.font_tiny,
                                  "%02d" % d.day, (200, 220, 245))
                self.screen.blit(lab, (x + w // 2 - lab.get_width() // 2,
                                       plot.bottom + 4))

        note = "Bars are the crescent altitude at sunset. Green = above the MABIMS 3° line."
        img = self.cached("chart", self.font_tiny, note, C_DIM)
        self.screen.blit(img, (plot.x, plot.bottom + 20))

    # ------------------------------------------------------------- analysis
    def draw_analysis_canvas(self):
        res = self.analysis_result(self.view)
        key = self.view
        if key not in self.chart_surfs or self.show_setup:
            self.chart_surfs[key] = self.render_analysis_chart(res)
        surf = self.chart_surfs[key]
        self.screen.blit(surf, (20, SKY_TOP))

    def render_analysis_chart(self, res):
        rect = pygame.Rect(0, 0, VIEW_W - 40, CANVAS_H - SKY_TOP - 16)
        surf = pygame.Surface(rect.size, pygame.SRCALPHA)
        hl = self.current_highlight(res["kind"])
        if res["kind"] == "thres":
            self._draw_boxplot(surf, res, rect, highlight=hl)
        else:
            self._draw_scatter(surf, res, rect, highlight=hl)
        return surf

    def _chart_axes(self, surf, rect, xlabel, ylabel, xrange, yrange, xticks,
                    yticks, title, caption=None):
        plot = pygame.Rect(rect.x + 52, rect.y + 34, rect.width - 64, rect.height - 88)
        pygame.draw.rect(surf, (8, 13, 32), plot)
        pygame.draw.rect(surf, (52, 70, 130), plot, 1)

        def mapx(v):
            x0, x1 = xrange
            return plot.x + (v - x0) / (x1 - x0) * plot.width

        def mapy(v):
            y0, y1 = yrange
            return plot.bottom - (v - y0) / (y1 - y0) * plot.height

        for gx in range(0, 101, 20):
            px = int(mapx(xrange[0] + (xrange[1] - xrange[0]) * gx / 100))
            pygame.draw.line(surf, (30, 46, 82), (px, plot.top), (px, plot.bottom))
        for gy in range(0, 101, 20):
            py = int(mapy(yrange[0] + (yrange[1] - yrange[0]) * gy / 100))
            pygame.draw.line(surf, (30, 46, 82), (plot.x, py), (plot.right, py))

        for t in xticks:
            img = self.cached("ax", self.font_tiny, str(t), C_DIM)
            surf.blit(img, (int(mapx(t)) - img.get_width() // 2, plot.bottom + 5))
        for t in yticks:
            img = self.cached("ax", self.font_tiny, str(t), C_DIM)
            surf.blit(img, (plot.x - img.get_width() - 5, int(mapy(t)) - 6))

        xl = self.cached("ax", self.font_small, xlabel, C_CYAN)
        surf.blit(xl, (plot.centerx - xl.get_width() // 2, rect.bottom - 16))
        yl = self.cached("ax", self.font_small, ylabel, C_CYAN)
        surf.blit(yl, (rect.x + 4, rect.y + 8))
        ti = self.cached("ax", self.font_section, title, C_CYAN)
        surf.blit(ti, ti.get_rect(centerx=rect.centerx, top=rect.y + 2))
        if caption:
            c = self.cached("ax", self.font_tiny, caption, C_DIM)
            surf.blit(c, (plot.x, plot.bottom + 18))
        return plot, mapx, mapy

    def _legend(self, surf, plot, items):
        text = [it[2] for it in items]
        widths = [self.cached("ax", self.font_tiny, t, C_DIM).get_width()
                  for t in text]
        row_h = 16
        box_w = max(widths) + 26
        box_h = row_h * len(items) + 12
        box = pygame.Rect(plot.right - box_w - 8, plot.bottom - box_h - 8,
                          box_w, box_h)
        bg = pygame.Surface(box.size, pygame.SRCALPHA)
        bg.fill((4, 8, 22, 215))
        surf.blit(bg, box.topleft)
        pygame.draw.rect(surf, (70, 100, 160), box, 1)
        y = box.y + 6
        for (color, kind, text) in items:
            tx = box.x + 10
            cy = y + row_h // 2
            if kind == "square":
                pygame.draw.rect(surf, color, (tx, cy - 5, 9, 9))
            elif kind == "dot":
                pygame.draw.circle(surf, color, (tx + 4, cy), 4)
            else:
                pygame.draw.line(surf, color, (tx, cy), (tx + 8, cy), 2)
            img = self.cached("ax", self.font_tiny, text, C_TEXT)
            surf.blit(img, (tx + 14, y + 1))
            y += row_h

    def _draw_scatter(self, surf, res, rect, highlight=None, title=None):
        xr = (0.0, res["limitx"]) if res["kind"] == "cond" else (0.0, res["limita"])
        yr = (0.0, res["limity"]) if res["kind"] == "cond" else (0.0, res["limitb"])
        if res["kind"] == "cond":
            xticks = [0, 5, 10, 15, 20, 25, 30]
            t = "CONDITION: %s >= %.1f  AND  %s >= %.1f" % (
                res["xlabel"], res["conditionx"], res["ylabel"], res["conditiony"])
            caption = ("Each dot = one recorded evening. GREEN = seen, "
                       "RED = not seen. Amber lines = MABIMS limits.")
        else:
            xticks = [0, 5, 10, 15, 20, 25, 30]
            t = "EQUATION: visible when %s >= f(%s)" % (res["ylabel"], res["xlabel"])
            caption = ("Each dot = one recorded evening. GREEN = seen, "
                       "RED = not seen. Magenta curve = visibility boundary.")
        title = title or t
        plot, mapx, mapy = self._chart_axes(
            surf, rect, res["xlabel"] + "  (abs)", res["ylabel"] + "  (abs)",
            xr, yr, xticks, [0, 10, 20, 30], title, caption=caption)

        for px, py, vis, method in res["points"]:
            x = int(mapx(px))
            y = int(mapy(py))
            if not (plot.left <= x <= plot.right and plot.top <= y <= plot.bottom):
                continue
            col = C_GREEN if vis == "V" else C_RED
            if method == "NE":
                pygame.draw.circle(surf, col, (x, y), 2)
            else:
                pygame.draw.rect(surf, col, (x - 2, y - 2, 4, 4))

        if res["kind"] == "cond":
            lx = int(mapx(res["conditionx"]))
            ly = int(mapy(res["conditiony"]))
            pygame.draw.line(surf, C_AMBER, (lx, plot.top), (lx, plot.bottom), 1)
            pygame.draw.line(surf, C_AMBER, (plot.x, ly), (plot.right, ly), 1)
            img = self.cached("ax", self.font_tiny,
                              "%.1f°" % res["conditionx"], C_AMBER)
            surf.blit(img, (lx + 4, plot.top + 4))
            img = self.cached("ax", self.font_tiny,
                              "%.1f°" % res["conditiony"], C_AMBER)
            surf.blit(img, (plot.right - img.get_width() - 4, ly + 4))
            self._legend(surf, plot, [
                (C_GREEN, "dot", "Seen"),
                (C_RED, "dot", "Not seen"),
                (C_AMBER, "line", "MABIMS limits"),
            ])
        else:
            prev = None
            for cx, cy in res["curve"]:
                p = (int(mapx(cx)), int(mapy(cy)))
                if prev:
                    pygame.draw.line(surf, C_MAGENTA, prev, p, 2)
                prev = p
            self._legend(surf, plot, [
                (C_GREEN, "dot", "Seen"),
                (C_RED, "dot", "Not seen"),
                (C_MAGENTA, "line", "Boundary curve"),
            ])

        if highlight:
            hx, hy = highlight["x"], highlight["y"]
            x, y = int(mapx(hx)), int(mapy(hy))
            if (plot.left - 6 <= x <= plot.right + 6 and
                    plot.top - 6 <= y <= plot.bottom + 6):
                pygame.draw.circle(surf, (255, 255, 255), (x, y), 9, 2)
                pygame.draw.circle(surf, C_CYAN, (x, y), 5, 0)
                lbl = self.cached("ax", self.font_tiny,
                                  highlight["label"], C_CYAN)
                bx, by = x - lbl.get_width() // 2, y - 22
                bx = max(plot.x + 2, min(plot.right - lbl.get_width() - 2, bx))
                by = max(plot.top + 2, by)
                surf.blit(lbl, (bx, by))

    def _draw_boxplot(self, surf, res, rect, highlight=None):
        ymax = max([s["max"] for s in res["series"].values()] + [1.0]) * 1.15
        caption = ("Box = middle half of records, white line = median, "
                   "whiskers = smallest and largest.")
        plot, mapx, mapy = self._chart_axes(
            surf, rect, "Observing method", res["xlabel"] + "  (abs)",
            (0, 2), (0.0, ymax), [0, 1, 2], [0, int(ymax)],
            "BOXPLOT - visible evening crescents", caption=caption)
        groups = list(res["series"].items())
        n = len(groups)
        bw = plot.width / max(1, n)
        for i, (label, s) in enumerate(groups):
            cx = plot.x + (i + 0.5) * bw
            w = min(60, int(bw * 0.4))
            col = C_CYAN if i == 0 else C_MAGENTA
            x0 = int(cx - w // 2)
            q1y = int(mapy(s["q1"]))
            q3y = int(mapy(s["q3"]))
            med_y = int(mapy(s["median"]))
            min_y = int(mapy(s["min"]))
            max_y = int(mapy(s["max"]))
            pygame.draw.line(surf, col, (int(cx), min_y), (int(cx), max_y), 2)
            pygame.draw.line(surf, col, (int(cx) - 10, min_y), (int(cx) + 10, min_y), 2)
            pygame.draw.line(surf, col, (int(cx) - 10, max_y), (int(cx) + 10, max_y), 2)
            box = pygame.Rect(x0, min(q1y, q3y), w, abs(q3y - q1y))
            box_s = pygame.Surface(box.size, pygame.SRCALPHA)
            box_s.fill(col + (60,))
            surf.blit(box_s, box.topleft)
            pygame.draw.rect(surf, col, box, 2)
            pygame.draw.line(surf, (255, 255, 255), (x0, med_y), (x0 + w, med_y), 2)
            lab = self.cached("ax", self.font_small, "%s  n=%d" % (label, s["count"]),
                              col)
            surf.blit(lab, lab.get_rect(center=(int(cx), plot.bottom + 38)))

        self._legend(surf, plot, [
            (C_CYAN, "square", "Naked eye"),
            (C_MAGENTA, "square", "Optical aid"),
            ((255, 255, 255), "line", "Median"),
        ])
        if highlight:
            v = highlight["value"]
            y = int(mapy(max(0.0, min(ymax, v))))
            pygame.draw.line(surf, (255, 255, 255), (plot.x + 6, y),
                             (plot.right - 6, y), 1)
            lbl = self.cached("ax", self.font_tiny,
                              highlight["label"], C_CYAN)
            surf.blit(lbl, (plot.x + 10, y + 4))

    # ---------------------------------------------------------------- verify
    def draw_verify_canvas(self):
        title = self.cached("ax", self.font_section,
                            "VERIFY - CHECKING OUR MATH", C_CYAN)
        self.screen.blit(title, title.get_rect(
            centerx=VIEW_W // 2, y=SKY_TOP + 2))
        y0 = SKY_TOP + 40
        chart_rect = pygame.Rect(20, y0, 480, CANVAS_H - y0 - 14)
        res = self.analysis_result("cond")
        hl = {"x": self.report["arc_l_sunset"],
              "y": self.report["m_alt_sunset"],
              "label": "THIS EVENING"} if self.report else None
        self._draw_scatter(self.screen, res, chart_rect, highlight=hl,
                           title="ALL RECORDED SIGHTINGS")
        self._draw_hz_table(y0)

    def _draw_hz_table(self, y0):
        x = 520
        w = VIEW_W - 20 - x
        box = pygame.Rect(x, y0, w, 168)
        pygame.draw.rect(self.screen, (8, 13, 32), box)
        pygame.draw.rect(self.screen, (52, 70, 130), box, 1)
        head = self.cached("ax", self.font_small,
                           "vs NASA/JPL HORIZONS  (live)", C_CYAN)
        self.screen.blit(head, (box.x + 10, box.y + 6))
        sub = self.cached("ax", self.font_tiny,
                          "our values for the date shown above vs the "
                          "official ephemeris", C_DIM)
        self.screen.blit(sub, (box.x + 10, box.y + 28))

        cols = [("", 150), ("OURS", 90), ("NASA", 90), ("", 44)]
        cx = box.x + 10
        cy = box.y + 50
        for label, cw in cols:
            img = self.cached("ax", self.font_tiny, label, C_CYAN)
            self.screen.blit(img, (cx, cy))
            cx += cw
        cy += 16
        names = [
            ("sunset", "Sunset"),
            ("moonset", "Moonset"),
            ("m_alt_sunset", "Moon alt. at sunset"),
            ("m_az_sunset", "Moon az. at sunset"),
            ("arc_l_sunset", "Arc of light"),
            ("illum", "Illumination"),
        ]
        state = self.verify["hz_state"]
        comp = self.verify.get("hz") or {}
        for i, (key, label) in enumerate(names):
            cy = box.y + 66 + i * 16
            img = self.cached("ax", self.font_tiny, label, C_TEXT)
            self.screen.blit(img, (box.x + 10, cy))
            cx = box.x + 10 + 150
            if state in ("running", "idle"):
                pair = ("-", "-")
            elif key in comp:
                ours, hz = comp[key]
                pair = self._hz_fmt(key, ours, hz)
            else:
                pair = ("-", "-")
            self.screen.blit(self.cached("ax", self.font_tiny, pair[0], C_TEXT),
                             (cx, cy))
            cx += 90
            self.screen.blit(self.cached("ax", self.font_tiny, pair[1], C_TEXT),
                             (cx, cy))
            cx += 90
            if key in comp:
                v = comp["verdicts"].get(key)
                if v is None:
                    img = self.cached("ax", self.font_tiny, "-", C_DIM)
                elif v:
                    img = self.cached("ax", self.font_tiny, "PASS", C_GREEN)
                else:
                    img = self.cached("ax", self.font_tiny, "FAIL", C_RED)
                self.screen.blit(img, (cx, cy))
        status = {
            "idle": "press R to compare with NASA",
            "running": "contacting NASA HORIZONS...",
            "done": "all within tolerance",
            "stale": "date changed - press R to re-check",
        }.get(state, "offline")
        col = C_GREEN if state == "done" else (
            C_AMBER if state in ("idle", "stale") else C_DIM)
        img = self.cached("ax", self.font_tiny, status, col)
        self.screen.blit(img, (box.x + 10, box.bottom - 18))

        obs = self.verify.get("obs")
        if obs:
            oy = box.bottom + 16
            obox = pygame.Rect(x, oy, w, 150)
            pygame.draw.rect(self.screen, (8, 13, 32), obox)
            pygame.draw.rect(self.screen, (52, 70, 130), obox, 1)
            head = self.cached("ax", self.font_small,
                               "vs %d REAL SIGHTINGS" % obs["n"], C_CYAN)
            self.screen.blit(head, (obox.x + 10, obox.y + 6))
            lines = [
                "Our verdict matched the recorded sighting %.1f%% of the time."
                % (obs["agreement_pct"] or 0.0),
            ]
            for label, pct in obs.get("by_method", {}).items():
                lines.append("%s sightings: %.1f%% match" % (label, pct))
            yy = obox.y + 30
            for line in lines:
                img = self.cached("ax", self.font_tiny, line, C_TEXT)
                self.screen.blit(img, (obox.x + 10, yy))
                yy += 18
            err = obs.get("err_arc_l", {})
            if err.get("mean") is not None:
                img = self.cached(
                    "ax", self.font_tiny,
                    "Average arc-of-light error: %.2f deg (n=%d)"
                    % (err["mean"], err["n"]), C_DIM)
                self.screen.blit(img, (obox.x + 10, yy))

    def _hz_fmt(self, key, ours, hz):
        if ours is None or hz is None:
            return ("-", "-")
        if key in ("sunset", "moonset"):
            return (ours.strftime("%H:%M"), hz.strftime("%H:%M"))
        return ("%.2f" % ours, "%.2f" % hz)

    # ---------------------------------------------------------------- panel
    def draw_panel(self):
        surf = pygame.Surface((PANEL_W, CANVAS_H), pygame.SRCALPHA)
        surf.fill(PANEL_FILL)
        pygame.draw.line(surf, C_CYAN, (1, 0), (1, CANVAS_H), 2)
        surf.blit(self.title_surf, (20, 16))
        sub = self.cached("panel", self.font_small, "Moon sighting system", C_DIM)
        surf.blit(sub, (24, 58))
        surf.blit(self.divider, (24, 82))

        if self.view == "sight":
            self._panel_sight(surf)
        elif self.view == "verify":
            self._panel_verify(surf)
        else:
            self._panel_analysis(surf, self.view)

        surf.blit(self.scanlines, (0, 0))
        self.screen.blit(surf, (W - PANEL_W, 0))

    def _panel_sight(self, surf):
        pad = 24
        y = 92
        if self.report:
            cx, cy, r = PANEL_W - 62, 46, 26
            pygame.draw.circle(surf, (8, 12, 30), (cx, cy), r + 4)
            pygame.draw.circle(surf, (40, 60, 100), (cx, cy), r + 4, 1)
            self.draw_crescent(surf, cx, cy, r, self.report["illum"],
                               self.report["pa"] - 90, MOON_LIT, MOON_DARK)
        date_img = self.cached("panel", self.font_section, fmt_date(self.date), C_TEXT)
        surf.blit(date_img, (pad, y))
        y += 30
        loc_img = self.cached("panel", self.font_body,
                              "%s  %s" % (self.city, self._coord_str()), C_DIM)
        surf.blit(loc_img, (pad, y))
        y += 34

        verdict, vcol = self._verdict()
        banner = self.neon(verdict, self.font_big, vcol)
        surf.blit(banner, (pad - 4, y))
        y += banner.get_height() + 6
        if self.report:
            zl = self.cached("panel", self.font_small,
                             "Odeh zone %s - %s" % (self.report["zone"],
                                                    self.report["zone_label"]),
                             vcol)
            surf.blit(zl, (pad, y))
            y += zl.get_height() + 14

        surf.blit(self.divider, (pad, y))
        y += 14
        if self.report is None:
            msg = self.cached("panel", self.font_body,
                              "No sunset on this date here.", C_AMBER)
            surf.blit(msg, (pad, y))
            return

        rows = [
            ("Sunset", fmt_time(self.report["sunset"])),
            ("Moonset", fmt_time(self.report["moonset"])),
            ("Lag", "%.0f min" % self.report["lag"] if self.report["lag"] is not None
             else "above horizon all evening" if self.report["m_alt_sunset"] > 0
             else "moon already set"),
            ("Best time", fmt_time(self.report["best"])),
            ("Moon age", self._fmt_age(self.report["age_sunset"])),
            ("Illumination", "%.1f %%" % (self.report["illum"] * 100)),
            ("Arc of light", "%.2f°" % self.report["arc_l_sunset"]),
            ("Moon altitude", "%.2f°" % self.report["m_alt_sunset"]),
            ("Arc of vision", "%.2f°" % self.report["arc_v"]),
            ("Crescent width", "%.2f'" % self.report["w"]),
        ]
        for label, value in rows:
            lbl = self.cached("panel", self.font_tiny, label, C_CYAN_DIM)
            val = self.cached("panel", self.font_small, value, C_TEXT)
            surf.blit(lbl, (pad, y))
            surf.blit(val, (pad + 118, y))
            y += 22
        y += 8
        surf.blit(self.divider, (pad, y))
        y += 16

        crit = [
            ("MABIMS 2023", self.report["mabims"],
             "ArcL>=%.1f & alt>=%.1f" % (MABIMS_ARCL, MABIMS_ALT)),
            ("Danjon", self.report["danjon"],
             "ArcL>=%.1f" % DANJON_ARCL),
            ("Odeh 2006", self.report["zone"] in ("A", "B", "C"),
             "zone %s" % self.report["zone"]),
        ]
        for name, ok, note in crit:
            col = C_GREEN if ok else C_RED
            pygame.draw.circle(surf, col, (pad + 5, y + 7), 5)
            nm = self.cached("panel", self.font_small, name, C_TEXT)
            surf.blit(nm, (pad + 18, y))
            st = self.cached("panel", self.font_tiny, "PASS" if ok else "FAIL", col)
            surf.blit(st, (pad + 18, y + 18))
            nt = self.cached("panel", self.font_tiny, note, C_DIM)
            surf.blit(nt, (pad + 96, y + 18))
            y += 46

        surf.blit(self.divider, (pad, y))
        y += 16
        head = self.cached("panel", self.font_small, "IN PLAIN WORDS", C_CYAN)
        surf.blit(head, (pad, y))
        y += 22
        text = " ".join(self.plain_summary())
        for line in self.wrap_text(text, self.font_tiny, PANEL_W - pad * 2 - 8):
            it = self.cached("panel", self.font_tiny, line, C_DIM)
            surf.blit(it, (pad, y))
            y += 15

    def _verdict(self):
        if self.report is None:
            return "NO SUNSET", C_AMBER
        r = self.report
        strong = r["mabims"] and r["danjon"] and r["zone"] in ("A", "B")
        if r["zone"] in ("A", "B"):
            return "HILAL VISIBLE", C_GREEN
        if r["zone"] == "C" or r["mabims"] or r["danjon"]:
            return "BORDERLINE", C_AMBER
        return "NOT VISIBLE", C_RED

    def plain_summary(self):
        """Short plain-language reading of the current evening, no jargon."""
        r = self.report
        if r is None:
            return ["The Sun does not set here this evening, so there is",
                    "nothing to check."]
        v, _ = self._verdict()
        word = {"HILAL VISIBLE": "it should be possible to see",
                "BORDERLINE": "it is borderline - binoculars may help",
                "NOT VISIBLE": "it is probably too faint to see"}[v]
        if r["lag"] is not None:
            lag = "%d minutes after sunset" % r["lag"]
        elif r["m_alt_sunset"] > 0:
            lag = "all evening (moon stays up)"
        else:
            lag = "already down at sunset"
        lines = [
            "The moon is %s old and %.1f%% lit - a thin crescent."
            % (self._fmt_age(r["age_sunset"]), r["illum"] * 100),
            "At sunset it stands %.1f degrees up, low in the west, and sets %s."
            % (r["m_alt_sunset"], lag),
            "Bottom line: %s." % word,
        ]
        return lines

    def current_highlight(self, kind):
        """Where the selected evening sits on an analysis chart (or None)."""
        r = self.report
        if r is None:
            return None
        if kind == "cond":
            return {"x": r["arc_l_sunset"], "y": r["m_alt_sunset"],
                    "label": "THIS EVENING"}
        if kind == "equa":
            if r["lag"] is None:
                return None
            return {"x": r["lag"], "y": r["arc_l_sunset"],
                    "label": "THIS EVENING"}
        if kind == "thres":
            value = {"ArcL": r["arc_l_sunset"], "MAlt": r["m_alt_sunset"],
                     "ArcV": r["arc_v"], "W": r["w"], "LT": r["lag"],
                     "MA": r["age_sunset"]}.get(self.analysis_x)
            if value is None:
                return None
            return {"value": value, "label": "THIS EVENING"}
        return None

    def _coord_str(self):
        return "%.2f°N, %.2f°E, UTC%+.0f" % (self.lat, self.lon, self.tz)

    def _fmt_age(self, hours):
        """Moon age as days + hours, e.g. 43.2 h -> '1d 19h'."""
        if hours is None:
            return "-"
        days = int(hours) // 24
        hrs = int(hours) % 24
        if days and hrs:
            return "%dd %dh" % (days, hrs)
        if days:
            return "%dd" % days
        return "%.1fh" % hours

    def _panel_analysis(self, surf, kind):
        res = self.analysis_result(kind)
        pad = 24
        y = 92
        name, desc = VIEWS[kind]
        img = self.neon(name, self.font_section, C_CYAN)
        surf.blit(img, (pad - 4, y))
        y += img.get_height() + 6
        for line in self.wrap_text(desc, self.font_small, PANEL_W - pad * 2):
            it = self.cached("panel", self.font_small, line, C_DIM)
            surf.blit(it, (pad, y))
            y += 20
        y += 6
        surf.blit(self.divider, (pad, y))
        y += 16

        if kind == "cond":
            info = ["X = ArcL (arc of light, °)",
                    "Y = MAlt (moon altitude, °)",
                    "Criteria line: ArcL %.1f° and MAlt %.1f°"
                    % (res["conditionx"], res["conditiony"])]
            for line in info:
                it = self.cached("panel", self.font_tiny, line, C_DIM)
                surf.blit(it, (pad, y))
                y += 18
            y += 6
        elif kind == "equa":
            info = ["X = LT (lag time, min)", "Y = ArcL (arc of light, °)",
                    "Boundary f(x): %s" % res["equation"]]
            for line in self.wrap_text(info[2], self.font_tiny, PANEL_W - pad * 2):
                it = self.cached("panel", self.font_tiny, line, C_DIM)
                surf.blit(it, (pad, y))
                y += 16
            for line in info[:2]:
                it = self.cached("panel", self.font_tiny, line, C_DIM)
                surf.blit(it, (pad, y))
                y += 18
            y += 6
        else:
            for label, v in res["minima"].items():
                it = self.cached("panel", self.font_tiny,
                                 "Min %s: %.2f" % (label, v), C_DIM)
                surf.blit(it, (pad, y))
                y += 18
            y += 8
            img = self.cached("panel", self.font_tiny,
                              "Param: %s   (press X to change)" % res["xlabel"],
                              C_CYAN_DIM)
            surf.blit(img, (pad, y))
            y += 20

        surf.blit(self.divider, (pad, y))
        y += 14
        head = self.cached("panel", self.font_small, "ERROR RATE  (pos / neg)", C_CYAN)
        surf.blit(head, (pad, y))
        y += 24
        if kind == "thres":
            for label, s in res["series"].items():
                nm = self.cached("panel", self.font_small, label, C_TEXT)
                surf.blit(nm, (pad, y))
                y += 18
                row = self.cached(
                    "panel", self.font_tiny,
                    "n=%d   min %.2f   median %.2f   max %.2f"
                    % (s["count"], s["min"], s["median"], s["max"]), C_DIM)
                surf.blit(row, (pad + 6, y))
                y += 20
            return
        for label, (pos, neg) in res["error_rates"].items():
            def col(v):
                return C_GREEN if v < 5 else (C_AMBER if v < 15 else C_RED)
            nm = self.cached("panel", self.font_small, label, C_TEXT)
            surf.blit(nm, (pad, y))
            p = self.cached("panel", self.font_small,
                            "%.1f%%" % pos, col(pos))
            n = self.cached("panel", self.font_small,
                            "%.1f%%" % neg, col(neg))
            surf.blit(p, (pad + 150, y))
            surf.blit(n, (pad + 210, y))
            y += 24
        y += 6
        note = self.wrap_text(
            "Positive = seen but criterion missed; negative = unseen but "
            "criterion said visible.", self.font_tiny, PANEL_W - pad * 2)
        for line in note:
            it = self.cached("panel", self.font_tiny, line, C_DIM)
            surf.blit(it, (pad, y))
            y += 16

    def _panel_verify(self, surf):
        pad = 24
        y = 92
        name, desc = VIEWS["verify"]
        img = self.neon(name, self.font_section, C_CYAN)
        surf.blit(img, (pad - 4, y))
        y += img.get_height() + 6
        for line in self.wrap_text(desc, self.font_small, PANEL_W - pad * 2):
            it = self.cached("panel", self.font_small, line, C_DIM)
            surf.blit(it, (pad, y))
            y += 20
        y += 6
        surf.blit(self.divider, (pad, y))
        y += 16

        head = self.cached("panel", self.font_small, "NASA HORIZONS", C_CYAN)
        surf.blit(head, (pad, y))
        y += 20
        state = self.verify["hz_state"]
        if state == "idle":
            status, col = "Press R to compare with NASA", C_DIM
        elif state == "running":
            status, col = "Contacting NASA...", C_AMBER
        elif state == "done":
            comp = self.verify.get("hz") or {}
            passed = sum(1 for v in comp.get("verdicts", {}).values() if v)
            status, col = "OK - %d/%d within tolerance" % (
                passed, len(comp.get("verdicts", {}))), C_GREEN
        elif state == "stale":
            status, col = "Date changed - press R to re-check", C_AMBER
        else:
            status = "Error: %s" % (self.verify.get("hz_error") or "unknown")
            col = C_RED
        for line in self.wrap_text(status, self.font_tiny,
                                   PANEL_W - pad * 2):
            it = self.cached("panel", self.font_tiny, line, col)
            surf.blit(it, (pad, y))
            y += 16
        y += 6

        surf.blit(self.divider, (pad, y))
        y += 16
        head = self.cached("panel", self.font_small, "REAL SIGHTINGS", C_CYAN)
        surf.blit(head, (pad, y))
        y += 20
        obs_state = self.verify["obs_state"]
        if obs_state == "done" and self.verify.get("obs"):
            obs = self.verify["obs"]
            lines = [
                "Compared our verdict against %d recorded sightings."
                % obs["n"],
                "Match rate: %.1f%%" % (obs["agreement_pct"] or 0.0),
            ]
            for label, pct in obs.get("by_method", {}).items():
                lines.append("%s: %.1f%%" % (label, pct))
            for line in lines:
                it = self.cached("panel", self.font_tiny, line,
                                 C_GREEN if "Match" in line else C_TEXT)
                surf.blit(it, (pad, y))
                y += 16
        elif obs_state == "running":
            it = self.cached("panel", self.font_tiny,
                             "Scanning the sighting database...", C_AMBER)
            surf.blit(it, (pad, y))
        else:
            it = self.cached("panel", self.font_tiny,
                             "not started", C_DIM)
            surf.blit(it, (pad, y))

    # --------------------------------------------------------------- modal
    def build_inputs(self):
        self.inputs = {
            "lat": InputBox(pygame.Rect(0, 0, 1, 1), "%.2f" % self.lat),
            "lon": InputBox(pygame.Rect(0, 0, 1, 1), "%.2f" % self.lon),
            "tz": InputBox(pygame.Rect(0, 0, 1, 1), "%.1f" % self.tz),
        }

    def handle_setup_event(self, event):
        box = self.setup_box()
        if event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE:
            self.show_setup = False
            return
        handled = False
        for inp in self.inputs.values():
            inp.handle_event(event)
            handled = handled or inp.active
        if event.type == pygame.MOUSEBUTTONDOWN:
            if not box.collidepoint(event.pos):
                self.show_setup = False
                self.commit_inputs()
                return
            sub = self.setup_sub_rects()
            for key, r in sub["days"].items():
                if r.collidepoint(event.pos):
                    self._step(key, -1)
                    return
            for key, r in sub["daysp"].items():
                if r.collidepoint(event.pos):
                    self._step(key, 1)
                    return
            for i, r in enumerate(sub["cities"]):
                if r.collidepoint(event.pos):
                    name, la, lo, tz = CITIES[i]
                    self.city, self.lat, self.lon, self.tz = name, la, lo, tz
                    self.inputs["lat"].text = "%.2f" % la
                    self.inputs["lon"].text = "%.2f" % lo
                    self.inputs["tz"].text = "%.1f" % tz
                    self.refresh(force=True)
                    return
            if sub["close"].collidepoint(event.pos):
                self.show_setup = False
                self.commit_inputs()
                return
        elif event.type == pygame.KEYDOWN and event.key in (
                pygame.K_RETURN, pygame.K_TAB):
            self.commit_inputs()

    def _step(self, key, delta):
        y, m, d = self.date.year, self.date.month, self.date.day
        if key == "day":
            d += delta
        elif key == "month":
            m += delta
        else:
            y += delta
        try:
            self.date = datetime.datetime(y, m, d)
            self.refresh()
        except ValueError:
            pass

    def commit_inputs(self):
        try:
            la = float(self.inputs["lat"].text or self.lat)
            lo = float(self.inputs["lon"].text or self.lon)
            tz = float(self.inputs["tz"].text or self.tz)
            if -90 <= la <= 90 and -180 <= lo <= 180 and -14 <= tz <= 14:
                self.lat, self.lon, self.tz = la, lo, tz
                self.city = "Custom"
                self.refresh(force=True)
        except ValueError:
            pass
        for inp in self.inputs.values():
            inp.active = False

    def setup_box(self):
        w, h = 640, 560
        return pygame.Rect((W - w) // 2, (H - h) // 2, w, h)

    def setup_sub_rects(self):
        box = self.setup_box()
        sub = {"days": {}, "daysp": {}, "cities": [], "close": pygame.Rect(0, 0, 0, 0)}
        pad = 30
        x = box.x + pad
        y = box.y + 110
        for label, key in (("DAY", "day"), ("MONTH", "month"), ("YEAR", "year")):
            sub["days"][key] = pygame.Rect(x, y, 30, 32)
            sub["daysp"][key] = pygame.Rect(x + 96, y, 30, 32)
            x += 150
        y = box.y + 214
        cw = (box.width - pad * 2 - 24) // 3
        for i in range(len(CITIES)):
            r = pygame.Rect(box.x + pad + (i % 3) * (cw + 12),
                            y + (i // 3) * 42, cw, 36)
            sub["cities"].append(r)
        sub["close"] = pygame.Rect(box.right - 130, box.bottom - 52, 100, 36)
        return sub

    def draw_setup_modal(self):
        shade = pygame.Surface((W, H), pygame.SRCALPHA)
        shade.fill((0, 0, 0, 170))
        self.screen.blit(shade, (0, 0))

        box = self.setup_box()
        surf = pygame.Surface(box.size, pygame.SRCALPHA)
        surf.fill((10, 16, 40, 245))
        pygame.draw.rect(surf, C_CYAN, (0, 0, box.width, box.height), 2,
                         border_radius=14)
        pad = 30

        title = self.neon("DATE & LOCATION", self.font_title, C_CYAN)
        surf.blit(title, (pad, 20))
        sub = self.font_small.render("Pick the sighting evening and place", True, C_DIM)
        surf.blit(sub, (pad, 66))

        x = pad
        y = 92
        for label, key, val in (("DAY", "day", self.date.day),
                                ("MONTH", "month", self.date.month),
                                ("YEAR", "year", self.date.year)):
            lab = self.font_tiny.render(label, True, C_CYAN_DIM)
            surf.blit(lab, (x + 8, y))
            rminus = pygame.Rect(x, y + 18, 30, 32)
            rplus = pygame.Rect(x + 96, y + 18, 30, 32)
            pygame.draw.rect(surf, (24, 34, 70), rminus, border_radius=7)
            pygame.draw.rect(surf, (24, 34, 70), rplus, border_radius=7)
            pygame.draw.rect(surf, C_CYAN_DIM, rminus, 1, border_radius=7)
            pygame.draw.rect(surf, C_CYAN_DIM, rplus, 1, border_radius=7)
            self._center_text(surf, rminus, "-", self.font_body, C_CYAN)
            self._center_text(surf, rplus, "+", self.font_body, C_CYAN)
            valimg = self.font_section.render(str(val), True, C_TEXT)
            surf.blit(valimg, (x + 44, y + 24))
            x += 150

        pygame.draw.line(surf, C_CYAN_DIM, (pad, 172), (box.width - pad, 172), 1)
        y = 190
        lab = self.font_tiny.render("CITY", True, C_CYAN_DIM)
        surf.blit(lab, (pad, y))
        cw = (box.width - pad * 2 - 24) // 3
        for i, (name, la, lo, tz) in enumerate(CITIES):
            r = pygame.Rect(pad + (i % 3) * (cw + 12),
                            y + 24 + (i // 3) * 42, cw, 36)
            sel = (name == self.city)
            col = C_CYAN if sel else C_CYAN_DIM
            pygame.draw.rect(surf, (22, 32, 68) if sel else (14, 22, 52), r,
                             border_radius=8)
            pygame.draw.rect(surf, col, r, 1, border_radius=8)
            t = self.font_small.render(name, True, C_TEXT if sel else C_DIM)
            surf.blit(t, t.get_rect(midleft=(r.x + 10, r.centery)))

        pygame.draw.line(surf, C_CYAN_DIM, (pad, 356), (box.width - pad, 356), 1)
        y = 368
        lab = self.font_tiny.render("OR TYPE COORDINATES", True, C_CYAN_DIM)
        surf.blit(lab, (pad, y))
        fields = [("LAT", "lat", self.inputs["lat"]),
                  ("LON", "lon", self.inputs["lon"]),
                  ("UTC+", "tz", self.inputs["tz"])]
        fx = pad
        fy = y + 20
        for label, key, inp in fields:
            lab = self.font_tiny.render(label, True, C_DIM)
            surf.blit(lab, (fx, fy))
            r = pygame.Rect(fx, fy + 22, 180, 32)
            inp.rect = pygame.Rect(box.x + fx, box.y + fy + 22, 180, 32)
            col = C_CYAN if inp.active else C_CYAN_DIM
            pygame.draw.rect(surf, (16, 26, 60), r, border_radius=7)
            pygame.draw.rect(surf, col, r, 1, border_radius=7)
            t = self.font_body.render(inp.text, True, C_TEXT)
            surf.blit(t, t.get_rect(midleft=(r.x + 10, r.centery)))
            fx += 190

        close = pygame.Rect(box.width - 130, box.height - 52, 100, 36)
        pygame.draw.rect(surf, (26, 36, 76), close, border_radius=9)
        pygame.draw.rect(surf, C_CYAN, close, 1, border_radius=9)
        self._center_text(surf, close, "CLOSE", self.font_small, C_CYAN)

        self.screen.blit(surf, box.topleft)

    def _center_text(self, surf, rect, text, font, color):
        img = font.render(text, True, color)
        surf.blit(img, img.get_rect(center=rect.center))

    # ---------------------------------------------------------- crescent
    def draw_crescent(self, surf, cx, cy, r, k, rot_deg, lit, dark):
        key = (int(r), int(k * 200), int(rot_deg / 5), tuple(lit), tuple(dark))
        spr = self.crescent_cache.get(key)
        if spr is None:
            spr = self.render_crescent(int(r), k, rot_deg, lit, dark)
            self.crescent_cache[key] = spr
            if len(self.crescent_cache) > 256:
                self.crescent_cache.clear()
        surf.blit(spr, (int(cx) - r, int(cy) - r))
        pygame.draw.circle(surf, (255, 255, 255, 70), (int(cx), int(cy)), int(r), 1)

    def render_crescent(self, r, k, rot_deg, lit, dark):
        spr = pygame.Surface((2 * r + 1, 2 * r + 1), pygame.SRCALPHA)
        if k >= 0.999:
            pygame.draw.circle(spr, lit, (r, r), r)
            return spr
        if k <= 0.001:
            pygame.draw.circle(spr, dark, (r, r), r)
            return spr
        i = math.acos(max(-1.0, min(1.0, 2.0 * k - 1.0)))
        sini, cosi = math.sin(i), math.cos(i)
        rot = math.radians(rot_deg)
        ux, uy = math.cos(rot), math.sin(rot)
        vx, vy = -math.sin(rot), math.cos(rot)
        r2 = r * r
        for dy in range(-r, r + 1):
            for dx in range(-r, r + 1):
                u = dx * ux + dy * uy
                v = dx * vx + dy * vy
                d2 = u * u + v * v
                if d2 > r2:
                    continue
                w = math.sqrt(r2 - d2)
                if u * sini + w * cosi >= 0.0:
                    spr.set_at((r + dx, r + dy), lit)
                else:
                    spr.set_at((r + dx, r + dy), dark)
        return spr

    # ------------------------------------------------------------ taskbar
    def draw_taskbar(self):
        self.screen.blit(self.taskbar_grad, (0, CANVAS_H))

        led_col = C_GREEN if self.view == "sight" else C_CYAN
        lx, ly = 18, CANVAS_H + BAR_H // 2
        pygame.draw.circle(self.screen, lerp_color((10, 14, 30), led_col, 0.35),
                           (lx, ly), 7)
        pygame.draw.circle(self.screen, led_col, (lx, ly), 5)
        led = self.font_tiny.render("MOON", True, led_col)
        self.screen.blit(led, (lx + 14, ly - led.get_height() // 2))

        mouse = pygame.mouse.get_pos()
        for b in self.buttons:
            self.draw_button(b, mouse)

        tx = W - 14
        date = fmt_date(self.date)
        d = self.font_section.render(date, True, C_TEXT)
        self.screen.blit(d, (tx - d.get_width(), CANVAS_H + 8))
        loc = self.font_small.render("%s   %s" % (self.city, self._coord_str()), True, C_DIM)
        self.screen.blit(loc, (tx - loc.get_width(), CANVAS_H + 34))
        view = self.font_small.render("VIEW: %s" % VIEWS[self.view][0], True, C_CYAN)
        self.screen.blit(view, (tx - view.get_width(), CANVAS_H + 52))

    def draw_button(self, b, mouse):
        rect = b["rect"]
        over = rect.collidepoint(mouse)
        active = (b["id"] == self.view and b["id"] in VIEWS)
        pressed = (self.pressed_btn == b["id"] and over)
        if over or active:
            self.screen.blit(self.button_glow, (rect.x - 7, rect.y - 7))
        if pressed:
            bg, border = (8, 12, 26), C_CYAN
        elif over:
            bg, border = (26, 36, 76), C_CYAN
        elif active:
            bg, border = (22, 30, 68), C_CYAN
        else:
            bg, border = (15, 20, 44), (62, 74, 122)
        offset = 2 if pressed else 0
        r = rect.move(0, offset)
        pygame.draw.rect(self.screen, bg, r, border_radius=BTN_RADIUS)
        pygame.draw.rect(self.screen, border, r, 2, border_radius=BTN_RADIUS)
        pygame.draw.line(self.screen, (120, 160, 220), (r.x + 5, r.y + 3),
                         (r.right - 5, r.y + 3))
        icon = self.icons[b["icon"]]
        self.screen.blit(icon, icon.get_rect(center=r.center))

    def draw_tooltip(self):
        b = self.hover_btn
        if not b:
            return
        tip = self.cached("tip", self.font_tooltip, b["tip"], C_TEXT)
        pad = 10
        pill = pygame.Rect(0, 0, tip.get_width() + pad * 2, tip.get_height() + 8)
        pill.centerx = b["rect"].centerx
        pill.bottom = b["rect"].top - 6
        if pill.left < 6:
            pill.left = 6
        if pill.right > W - 6:
            pill.right = W - 6
        pygame.draw.rect(self.screen, (10, 14, 36), pill, border_radius=8)
        pygame.draw.rect(self.screen, C_CYAN_DIM, pill, 1, border_radius=8)
        self.screen.blit(tip, tip.get_rect(center=pill.center))

    def draw_about(self):
        w, h = 460, 360
        x = (W - w) // 2
        y = (H - h) // 2
        box = pygame.Surface((w, h), pygame.SRCALPHA)
        box.fill((10, 16, 40, 235))
        pygame.draw.rect(box, C_CYAN, (0, 0, w, h), 2, border_radius=12)
        pad = 26
        ty = pad
        title = self.font_title.render("Moon Watch", True, C_CYAN)
        box.blit(title, (pad, ty))
        ty += 38
        sub = self.font_small.render("A Moon Sighting System for Ramadan & Eid", True, C_AMBER)
        box.blit(sub, (pad, ty))
        ty += 28
        pygame.draw.line(box, C_CYAN_DIM, (pad, ty), (w - pad, ty), 1)
        ty += 16
        story = ("See if the new crescent moon (hilal) will be visible on any "
                 "evening, from any place. Watch the sky diagram, check the "
                 "MABIMS 2023, Danjon and Odeh (2006) criteria, and explore "
                 "the 8000+ sighting database with HilalPy-style analysis.")
        for line in self.wrap_text(story, self.font_body, w - pad * 2):
            box.blit(self.font_body.render(line, True, C_TEXT), (pad, ty))
            ty += 24
        ty += 8
        pygame.draw.line(box, C_CYAN_DIM, (pad, ty), (w - pad, ty), 1)
        ty += 12
        for line in self.wrap_text(
                "Calculations: solarsystem library  |  Analysis: HilalPy (adapted)",
                self.font_body, w - pad * 2):
            box.blit(self.font_body.render(line, True, C_GREEN), (pad, ty))
            ty += 24
        ty += 2
        close = self.font_small.render(
            "Press Esc, I, or click About again to close", True, C_DIM)
        box.blit(close, (pad, ty))
        self.screen.blit(box, (x, y))

    def _fmt_dates_line(self, ah_name, ah_year, d):
        return "%s  (%s %d AH)" % (d.strftime("%d %b %Y"), ah_name, ah_year)

    def draw_dates(self):
        w, h = 560, 430
        x = (W - w) // 2
        y = (H - h) // 2
        box = pygame.Surface((w, h), pygame.SRCALPHA)
        box.fill((10, 16, 40, 235))
        pygame.draw.rect(box, C_CYAN, (0, 0, w, h), 2, border_radius=12)
        pad = 26
        ty = pad
        title = self.font_title.render("Ramadan & Eid Dates", True, C_CYAN)
        box.blit(title, (pad, ty))
        ty += 36
        sub = self.font_small.render(
            "Found from local crescent visibility at this place", True, C_AMBER)
        box.blit(sub, (pad, ty))
        ty += 26
        pygame.draw.line(box, C_CYAN_DIM, (pad, ty), (w - pad, ty), 1)
        ty += 14

        data = self.dates_data or islamic.events(
            self.lat, self.lon, self.tz, self.date)
        city = next((c for c in CITIES if c[1] == self.lat
                     and c[2] == self.lon and c[3] == self.tz), None)
        where = city[0] if city else ("lat %.2f, lon %.2f, UTC%+.1f"
                                      % (self.lat, self.lon, self.tz))

        for ev in data["events"]:
            name = self.font_section.render(ev["name"], True, C_AMBER)
            box.blit(name, (pad, ty))
            ty += 22
            desc = self.font_small.render(ev["desc"], True, C_DIM)
            box.blit(desc, (pad + 2, ty))
            ty += 20
            if ev["prev"]:
                box.blit(self.font_body.render(
                    "Previous  " + self._fmt_dates_line(
                        ev["ah_name"], ev["prev"][0], ev["prev"][1]),
                    True, C_GREEN), (pad, ty))
            else:
                box.blit(self.font_body.render("Previous  ---", True, C_DIM),
                         (pad, ty))
            ty += 20
            if ev["next"]:
                box.blit(self.font_body.render(
                    "Next      " + self._fmt_dates_line(
                        ev["ah_name"], ev["next"][0], ev["next"][1]),
                    True, C_CYAN), (pad, ty))
            else:
                box.blit(self.font_body.render("Next      ---", True, C_DIM),
                         (pad, ty))
            ty += 26

        pygame.draw.line(box, C_CYAN_DIM, (pad, ty), (w - pad, ty), 1)
        ty += 10
        box.blit(self.font_small.render(
            "Place: %s" % where, True, C_TEXT), (pad, ty))
        ty += 18
        box.blit(self.font_small.render(
            "Selected date: %s  |  Today: %s"
            % (self.date.strftime("%d %b %Y"),
               data["today"].strftime("%d %b %Y")),
            True, C_TEXT), (pad, ty))
        ty += 18
        close = self.font_small.render(
            "Press Esc, D, or click the calendar button again to close",
            True, C_DIM)
        box.blit(close, (pad, ty))
        self.screen.blit(box, (x, y))


if __name__ == "__main__":
    HilalApp().run()
