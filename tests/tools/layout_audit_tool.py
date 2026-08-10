import os
import sys
os.environ["SDL_VIDEODRIVER"] = "dummy"
os.environ["SDL_AUDIODRIVER"] = "dummy"
_HERE = os.path.dirname(os.path.abspath(__file__))
_HILAL = os.path.dirname(os.path.dirname(_HERE))
sys.path.insert(0, _HILAL)
_VENDOR = os.path.join(os.path.dirname(_HILAL), "vendor")
if os.path.isdir(_VENDOR) and _VENDOR not in sys.path:
    sys.path.insert(0, _VENDOR)

import datetime
import pygame
import hilal_sighting as H

TRACK = []


class Tracked(pygame.Surface):
    def blit(self, source, dest=None, area=None, special_flags=0):
        if isinstance(source, pygame.Surface) and dest is not None:
            d = dest
            if not isinstance(d, pygame.Rect):
                d = pygame.Rect(int(d[0]), int(d[1]),
                                source.get_width(), source.get_height())
            r = d.copy()
            if r.right > self.get_width() + 2 or r.bottom > self.get_height() + 2 \
                    or r.left < -2 or r.top < -2:
                try:
                    if source.get_at((2, 2)).a > 0:
                        TRACK.append(("OOB", r, self.get_size(),
                                      source.get_width(), source.get_height()))
                except Exception:
                    pass
            if r.bottom > self.get_height() - 4:
                TRACK.append(("EDGE", r, self.get_size(),
                              source.get_width(), source.get_height()))
        return super().blit(source, dest, area, special_flags)


H.pygame.Surface = Tracked

app = H.HilalApp()
app.date = datetime.datetime(2024, 4, 9)
app.lat, app.lon, app.tz = 30.90, 75.85, 5.5
app.city = "Ludhiana, India"
app.refresh(force=True)


def audit(view, setup=False, about=False, dates=False):
    global TRACK
    TRACK = []
    app.view = view
    app.show_setup = setup
    app.show_about = about
    app.show_dates = dates
    if dates:
        app.dates_data = H.islamic.events(app.lat, app.lon, app.tz, app.date)
    app.invalidate_analysis()
    app.draw()
    print("view=%-6s setup=%-5s about=%-5s dates=%-5s -> %d warnings"
          % (view, setup, about, dates, len(TRACK)))
    seen = set()
    for tag, r, size, sw, sh in TRACK:
        key = (tag, r.topleft, size)
        if key in seen:
            continue
        seen.add(key)
        print("   %s rect=%-25s surface=%s src=%dx%d"
              % (tag, "%s..%s" % (r.topleft, r.bottomright), size, sw, sh))


for v in ["sight", "cond", "equa", "thres", "verify"]:
    audit(v)
audit("sight", setup=True)
audit("sight", about=True)
audit("sight", dates=True)
print("AUDIT DONE")
