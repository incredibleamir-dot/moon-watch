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

BLITS = []  # (dest_id, dest_size, local_rect, src_size)


def is_text_like(src):
    if not (src.get_flags() & pygame.SRCALPHA):
        return False
    w, h = src.get_size()
    if h > 70 or h < 6:
        return False
    try:
        corners = (src.get_at((0, 0)).a, src.get_at((w - 1, 0)).a,
                   src.get_at((0, h - 1)).a, src.get_at((w - 1, h - 1)).a)
    except Exception:
        return False
    return all(c == 0 for c in corners)


class Tracked(pygame.Surface):
    def blit(self, source, dest=None, area=None, special_flags=0):
        if isinstance(source, pygame.Surface) and dest is not None and \
                is_text_like(source):
            d = dest
            if not isinstance(d, pygame.Rect):
                d = pygame.Rect(int(d[0]), int(d[1]),
                                source.get_width(), source.get_height())
            BLITS.append((id(self), self.get_size(), d.copy(),
                          source.get_size()))
        return super().blit(source, dest, area, special_flags)


H.pygame.Surface = Tracked

app = H.HilalApp()
app.screen = Tracked((H.W, H.H))
app.date = datetime.datetime(2024, 4, 9)
app.lat, app.lon, app.tz = 30.90, 75.85, 5.5
app.city = "Ludhiana, India"
app.refresh(force=True)

app.view = "sight"
app.show_setup = True
app.draw()

box = app.setup_box()
close_local = pygame.Rect(box.right - 130 - box.x, box.bottom - 52 - box.y,
                          100, 36)
modal_blits = [(r, s) for sid, ssize, r, s in BLITS if ssize == box.size]
print("modal text blits:", len(modal_blits))
for r, s in modal_blits:
    inter = close_local.clip(r)
    if inter.w > 0 and inter.h > 0:
        print("  CLOSE overlaps text at %s (src %dx%d) inter=%dx%d"
              % (r, s[0], s[1], inter.w, inter.h))

# also report text that extends past modal bounds (clipped)
for r, s in modal_blits:
    if r.right > box.w or r.bottom > box.h or r.left < 0 or r.top < 0:
        print("  text clipped by modal edge: %s (src %dx%d)"
              % (r, s[0], s[1]))
print("DONE")
