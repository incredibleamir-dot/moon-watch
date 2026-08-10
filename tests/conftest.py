import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
VENDOR = os.path.join(ROOT, "vendor")

for path in (ROOT, VENDOR):
    if os.path.isdir(path) and path not in sys.path:
        sys.path.insert(0, path)
