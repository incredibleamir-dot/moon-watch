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

app = H.HilalApp()
app.date = datetime.datetime(2024, 4, 9)
app.lat, app.lon, app.tz = 30.90, 75.85, 5.5
app.city = "Ludhiana, India"
app.refresh(force=True)

out = os.path.join(_HILAL, "screenshots")
os.makedirs(out, exist_ok=True)

views = ["sight", "cond", "equa", "thres", "verify"]
for v in views:
    app.view = v
    app.invalidate_analysis()
    app.draw()
    pygame.image.save(app.screen, os.path.join(out, "view_%s.png" % v))
    print("saved", v)

app.view = "sight"
app.show_setup = True
app.draw()
pygame.image.save(app.screen, os.path.join(out, "view_setup.png"))
print("saved setup")
app.show_setup = False

app.show_about = True
app.draw()
pygame.image.save(app.screen, os.path.join(out, "view_about.png"))
print("saved about")
app.show_about = False

app.show_dates = True
app.dates_data = H.islamic.events(app.lat, app.lon, app.tz, app.date)
app.draw()
pygame.image.save(app.screen, os.path.join(out, "view_dates.png"))
print("saved dates")
app.show_dates = False

print("OK")
