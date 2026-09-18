"""Shared test fixtures: headless Qt + path setup."""

import os
import sys

PROJ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJ not in sys.path:
    sys.path.insert(0, PROJ)
_vendor = os.path.join(PROJ, "vendor")
if _vendor not in sys.path:
    sys.path.insert(0, _vendor)

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtWidgets import QApplication


@pytest.fixture(scope="session")
def qapp():
    """Return a session-scoped QApplication with the app stylesheet."""
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    app.setStyle("Fusion")
    from moonwatch.theme import STYLE
    app.setStyleSheet(STYLE)
    return app