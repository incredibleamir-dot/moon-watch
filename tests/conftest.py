import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
SOLAR = os.path.join(os.path.dirname(ROOT), "solarsystem")
VENDOR = os.path.join(os.path.dirname(ROOT), "vendor")

for path in (ROOT, SOLAR):
    if path not in sys.path:
        sys.path.insert(0, path)
if os.path.isdir(VENDOR) and VENDOR not in sys.path:
    sys.path.insert(0, VENDOR)
