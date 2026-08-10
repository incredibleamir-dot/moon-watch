"""Tests for the pygame app: layout invariants, plain-language summary,
highlight logic, input handling, and the QUIT/verification wiring.

Runs headless (SDL dummy video driver) so no window is needed.
"""

import os
os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

import datetime

import pygame
import pytest

import hilal_sighting as H


@pytest.fixture(scope="module")
def app_fixture():
    a = H.HilalApp()
    a.date = datetime.datetime(2024, 4, 9)
    a.lat, a.lon, a.tz = 30.90, 75.85, 5.5
    a.city = "Ludhiana, India"
    a.refresh(force=True)
    yield a


class TestViews:
    def test_verify_view_registered(self):
        assert "verify" in H.VIEWS
        assert H.VIEWS["verify"][0] == "VERIFY"

    def test_button_ids(self, app_fixture):
        ids = {b["id"] for b in app_fixture.buttons}
        assert "verify" in ids
        assert "quit" in ids
        assert "setup" in ids

    def test_all_views_render(self, app_fixture):
        for view in ("sight", "cond", "equa", "thres", "verify"):
            app_fixture.view = view
            app_fixture.invalidate_analysis()
            app_fixture.draw()  # must not raise

    def test_setup_modal_render(self, app_fixture):
        app_fixture.show_setup = True
        app_fixture.draw()
        app_fixture.show_setup = False

    def test_about_render(self, app_fixture):
        app_fixture.show_about = True
        app_fixture.draw()
        app_fixture.show_about = False


class TestPlainSummary:
    def test_three_plain_lines(self, app_fixture):
        lines = app_fixture.plain_summary()
        assert len(lines) == 3
        text = " ".join(lines).lower()
        assert "moon" in text
        assert "old" in text
        assert "bottom line" in text

    def test_returns_message_when_no_report(self, app_fixture):
        app_fixture.report = None
        try:
            lines = app_fixture.plain_summary()
            assert "does not set" in lines[0].lower()
        finally:
            app_fixture.refresh(force=True)


class TestHighlight:
    def test_cond_highlight(self, app_fixture):
        hl = app_fixture.current_highlight("cond")
        assert hl["label"]
        assert hl["x"] > 0 and hl["y"] > 0

    def test_equa_highlight(self, app_fixture):
        hl = app_fixture.current_highlight("equa")
        assert hl is None or hl["x"] > 0

    def test_thres_highlight_each_param(self, app_fixture):
        for param in ("ArcL", "MAlt", "ArcV", "W", "LT", "MA"):
            app_fixture.analysis_x = param
            hl = app_fixture.current_highlight("thres")
            assert hl is not None
            assert hl["value"] is not None

    def test_no_report_returns_none(self, app_fixture):
        app_fixture.report = None
        try:
            assert app_fixture.current_highlight("cond") is None
        finally:
            app_fixture.refresh(force=True)


class TestInputs:
    def test_input_rects_inside_modal(self, app_fixture):
        app_fixture.show_setup = True
        app_fixture.draw()
        box = app_fixture.setup_box()
        try:
            for key in ("lat", "lon", "tz"):
                r = app_fixture.inputs[key].rect
                assert box.contains(r), "%s rect outside modal: %s" % (key, r)
        finally:
            app_fixture.show_setup = False

    def test_typing_commits(self, app_fixture):
        inp = app_fixture.inputs["lat"]
        inp.active = True
        inp.text = ""
        for ch in "31.5":
            app_fixture.handle_setup_event(
                pygame.event.Event(pygame.KEYDOWN, key=None, unicode=ch,
                                   mod=0))
        app_fixture.commit_inputs()
        assert app_fixture.lat == pytest.approx(31.5)
        app_fixture.lat, app_fixture.lon, app_fixture.tz = 30.90, 75.85, 5.5
        app_fixture.city = "Ludhiana, India"
        app_fixture.refresh(force=True)

    def test_escape_closes_setup_not_app(self, app_fixture):
        app_fixture.show_setup = True
        app_fixture.handle_setup_event(
            pygame.event.Event(pygame.KEYDOWN, key=pygame.K_ESCAPE))
        assert app_fixture.show_setup is False


class TestQuit:
    def test_activate_quit_posts_quit(self, app_fixture):
        pygame.event.clear()
        app_fixture.activate("quit")
        events = pygame.event.get()
        assert any(e.type == pygame.QUIT for e in events)


class TestVerifyCanvas:
    def test_render_with_done_hz(self, app_fixture):
        now = datetime.datetime.now()
        app_fixture.verify.update({
            "hz_state": "done",
            "hz": {
                "sunset": (now, now),
                "moonset": (None, None),
                "m_alt_sunset": (9.3, 9.2),
                "m_az_sunset": (283.0, 282.0),
                "arc_l_sunset": (10.2, 10.1),
                "illum": (0.83, 0.80),
                "verdicts": {k: True for k in
                             ("sunset", "moonset", "m_alt_sunset",
                              "m_az_sunset", "arc_l_sunset", "illum")},
            },
            "obs": {
                "n": 300,
                "agreement_pct": 67.5,
                "by_method": {"Naked Eye": 65.0, "Optical Aided": 80.0},
                "err_arc_l": {"n": 300, "mean": 1.2, "max": 5.0, "p90": 3.0},
            },
        })
        app_fixture.view = "verify"
        app_fixture.invalidate_analysis()
        app_fixture.draw()  # must not raise

    def test_render_with_error_hz(self, app_fixture):
        app_fixture.verify.update({"hz_state": "error",
                                   "hz_error": "HORIZONS request failed"})
        app_fixture.view = "verify"
        app_fixture.invalidate_analysis()
        app_fixture.draw()  # must not raise
