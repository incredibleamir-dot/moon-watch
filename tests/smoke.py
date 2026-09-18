"""Headless smoke test: paints every workspace and dialog offscreen.

Run:  python tests/smoke.py
Writes screenshots to the system temp folder. Network permitting, the
Verify page also waits for the NASA HORIZONS + sightings comparisons to
finish (they auto-skip when offline / missing).
"""

import os
import sys
import time

PROJ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJ)
sys.path.insert(0, os.path.join(PROJ, "vendor"))

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import numpy as np
from PySide6.QtGui import QImage
from PySide6.QtWidgets import QApplication

from moonwatch.theme import STYLE
from moonwatch.app_window import MainWindow, TABS


def img_stats(widget, name, outdir):
    pm = widget.grab()
    img = pm.toImage().convertToFormat(QImage.Format_RGB32)
    w, h = img.width(), img.height()
    arr = np.frombuffer(img.bits(), np.uint8).reshape(h, w, 4)[:, :, :3]
    unique = len(np.unique(arr.reshape(-1, 3), axis=0))
    dark = (arr.sum(axis=2) < 60).mean()
    print(f"{name:22s} {w}x{h} unique_colors={unique:6d} pct_dark={dark:.4f}")
    assert w > 200 and (unique > 50 or (arr.sum(axis=2) < 300).mean() > 0.02), name
    img.save(os.path.join(outdir, f"tab_{name}.png"))


def main():
    app = QApplication(sys.argv)
    app.setStyle("Fusion")
    app.setStyleSheet(STYLE)
    win = MainWindow()
    win.resize(1280, 800)
    win.show()
    app.processEvents()

    outdir = os.path.join(os.environ.get("TEMP", "."), "moonwatch_smoke")
    os.makedirs(outdir, exist_ok=True)
    keys = [t[0] for t in TABS]
    for key in keys:
        win.tabs.setCurrentIndex(keys.index(key))
        app.processEvents()
        win.pages[key].repaint()
        app.processEvents()
        img_stats(win.pages[key], key, outdir)

    # cycle a threshold parameter, re-render live, re-render a JSON report
    win.pages["thres"].param_combo.setCurrentIndex(2)
    app.processEvents()
    win.tabs.setCurrentIndex(0)
    app.processEvents()
    win.pages["live"]._on_tick()
    app.processEvents()
    img_stats(win.pages["live"], "live2", outdir)

    # global visibility map: switch the Sighting page to Global mode and wait
    # for the background worker (spawned sub-process) to deliver the grid
    sight = win.pages["sight"]
    sight.mode_combo.setCurrentIndex(1)
    app.processEvents()
    deadline = time.time() + 60
    while time.time() < deadline and win.ctrl.global_map_state == "running":
        app.processEvents()
        time.sleep(0.05)
    app.processEvents()
    sight._sync_global()
    app.processEvents()
    img_stats(sight, "sight_global", outdir)
    assert win.ctrl.global_map_state in ("done", "error"), win.ctrl.global_map_state
    if win.ctrl.global_map_state == "done" and win.ctrl.report is not None:
        from moonwatch import globalmap as gm
        d = sight.global_widget.data
        codes = gm.classify("odeh", d["mh"], d["ark"], d["av"], d["w"],
                            d["ark_b"], d["nolight"])
        li = int(round(89.0 - win.ctrl.lat))
        lj = int(round(win.ctrl.lon + 179.0))
        r = win.ctrl.report
        if r["zone"] in ("A", "B"):
            want = gm.VISIBLE
        elif r["zone"] == "C" or r["mabims"] or r["danjon"]:
            want = gm.BORDERLINE
        else:
            want = gm.NOT_VISIBLE
        got = int(codes[li, lj])
        names = {gm.VISIBLE: "VISIBLE", gm.BORDERLINE: "BORDERLINE",
                 gm.NOT_VISIBLE: "NOT_VISIBLE", gm.NO_SUNSET: "NO_SUNSET"}
        print("sight_global  verdict@%s: map=%s app=%s"
              % (win.ctrl.city, names.get(got, "?"), names.get(want, "?")))
        assert got == want, (got, want, win.ctrl.city)
    sight._sync_global()          # regression: layer must survive re-sync
    app.processEvents()
    sight.global_widget.update()
    app.processEvents()
    img_stats(sight, "sight_global2", outdir)
    sight.mode_combo.setCurrentIndex(0)
    app.processEvents()
    img_stats(sight, "sight", outdir)

    # let the Verify-page threads finish (HORIZONS + sightings)
    win.tabs.setCurrentIndex(keys.index("verify"))
    app.processEvents()
    deadline = time.time() + 60
    verdict = win.ctrl.verify
    while time.time() < deadline and (
            verdict["hz_state"] in ("idle", "running") or
            verdict["obs_state"] in ("idle", "running")):
        app.processEvents()
        time.sleep(0.05)
    app.processEvents()
    win.pages["verify"].update_view()
    app.processEvents()
    img_stats(win.pages["verify"], "verify2", outdir)
    print("verify states:", verdict["hz_state"], verdict["obs_state"])

    from moonwatch.dialogs import (LocationDateDialog, DatesDialog, AboutDialog,
                                   UserGuideDialog)
    for dlg in (LocationDateDialog(win.ctrl, win), DatesDialog(win.ctrl, win),
                AboutDialog(win), UserGuideDialog(win)):
        dlg.show()
        app.processEvents()
        img_stats(dlg, type(dlg).__name__, outdir)
        dlg.close()

    print(f"SMOKE OK -> {outdir}")


if __name__ == "__main__":
    main()