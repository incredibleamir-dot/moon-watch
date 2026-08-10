import os
import sys
os.environ["SDL_VIDEODRIVER"] = "dummy"
os.environ["SDL_AUDIODRIVER"] = "dummy"
_HERE = os.path.dirname(os.path.abspath(__file__))
_HILAL = os.path.dirname(os.path.dirname(_HERE))
sys.path.insert(0, _HILAL)
_VENDOR = os.path.join(_HILAL, "vendor")
if os.path.isdir(_VENDOR) and _VENDOR not in sys.path:
    sys.path.insert(0, _VENDOR)

import datetime
import pygame
import hilal_sighting as H

REAL_SURFACE = pygame.Surface
BLITS = {}  # id(surf) -> (surf_size, local_rect, src_size, src_id)


def is_text_like(src):
    if not isinstance(src, REAL_SURFACE):
        return False
    if not (src.get_flags() & pygame.SRCALPHA):
        return False
    w, h = src.get_size()
    if h > 70 or h < 6:
        return False
    if max(w, h) / min(w, h) < 1.5:
        return False
    try:
        corners = (src.get_at((0, 0)).a, src.get_at((w - 1, 0)).a,
                   src.get_at((0, h - 1)).a, src.get_at((w - 1, h - 1)).a)
    except Exception:
        return False
    return all(c == 0 for c in corners)


class Tracked(REAL_SURFACE):
    def blit(self, source, dest=None, area=None, special_flags=0):
        if isinstance(source, REAL_SURFACE) and dest is not None and \
                is_text_like(source):
            d = dest
            if not isinstance(d, pygame.Rect):
                d = pygame.Rect(int(d[0]), int(d[1]),
                                source.get_width(), source.get_height())
            BLITS.setdefault(id(self), []).append(
                (self.get_size(), d.copy(), source.get_size(), id(source)))
        return super().blit(source, dest, area, special_flags)


H.pygame.Surface = Tracked

app = H.HilalApp()
app.screen = Tracked((H.W, H.H))
app.date = datetime.datetime(2024, 4, 9)
app.lat, app.lon, app.tz = 30.90, 75.85, 5.5
app.city = "Ludhiana, India"
app.refresh(force=True)


def overlap_area(a, b):
    x = max(0, min(a.right, b.right) - max(a.left, b.left))
    y = max(0, min(a.bottom, b.bottom) - max(a.top, b.top))
    return x * y


def audit(label):
    global BLITS
    BLITS = {}
    app.draw()
    issues = []
    for sid, blits in BLITS.items():
        n = len(blits)
        for i in range(n):
            ssize, ra, sa, sa_id = blits[i]
            for j in range(i + 1, n):
                ssize2, rb, sb, sb_id = blits[j]
                if ssize != ssize2:
                    continue
                if sa_id == sb_id and ra.topleft == rb.topleft:
                    continue
                if ra.topleft == rb.topleft:
                    continue
                inter = overlap_area(ra, rb)
                if inter >= 16:
                    issues.append((ssize, ra, rb, sa, sb, inter))
    print("== %-6s: %d overlaps (same surface)" % (label, len(issues)))
    seen = set()
    for ssize, ra, rb, sa, sb, inter in issues:
        key = (ra.topleft, rb.topleft)
        if key in seen:
            continue
        seen.add(key)
        print("   [%s] %s (src %dx%d) x %s (src %dx%d) inter=%dpx"
              % (ssize, ra, sa[0], sa[1], rb, sb[0], sb[1], inter))


app.view = "sight"
audit("sight")
for v in ("cond", "equa", "thres"):
    app.view = v
    app.invalidate_analysis()
    audit(v)
app.view = "verify"
app.invalidate_analysis()
audit("verify")
app.view = "sight"
app.show_setup = True
audit("setup")
app.show_setup = False
app.show_about = True
audit("about")
app.show_about = False
app.show_dates = True
app.dates_data = H.islamic.events(app.lat, app.lon, app.tz, app.date)
audit("dates")
app.show_dates = False
print("OVERLAP AUDIT DONE")
