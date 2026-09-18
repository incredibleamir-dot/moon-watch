#!/usr/bin/env python3
"""Moon Watch - a scientific crescent-visibility workstation (PySide6).

Run from this directory:  python main.py
"""

import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
if getattr(sys, "frozen", False):
    BASE = getattr(sys, "_MEIPASS", os.path.dirname(sys.executable))
else:
    BASE = HERE
sys.path.insert(0, BASE)
sys.path.insert(0, os.path.join(BASE, "vendor"))

if __name__ == "__main__":
    import multiprocessing
    multiprocessing.freeze_support()

    if getattr(sys, "frozen", False):
        if sys.stdout is None:
            sys.stdout = open(os.devnull, "w")
        if sys.stderr is None:
            sys.stderr = open(os.devnull, "w")

    from PySide6.QtWidgets import QApplication

    from moonwatch.theme import STYLE, FAMILY
    from moonwatch.controller import app_logo
    from moonwatch.app_window import MainWindow

    app = QApplication(sys.argv)
    app.setApplicationName("Moon Watch")
    app.setOrganizationName("MoonWatch")
    app.setStyle("Fusion")
    app.setStyleSheet(STYLE)
    app.setWindowIcon(app_logo())
    font = app.font()
    font.setFamily(FAMILY)
    font.setPointSize(10)
    app.setFont(font)

    win = MainWindow()
    win.show()
    sys.exit(app.exec())