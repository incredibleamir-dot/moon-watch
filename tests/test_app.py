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

import crescent_sighting as H


@pytest.fixture(scope="module")
def app_fixture():
    a = H.CrescentApp()
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
        for view in ("sight", "cond", "equa", "thres", "verify", "live"):
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


class TestLiveView:
    def test_live_button_present(self, app_fixture):
        ids = {b["id"] for b in app_fixture.buttons}
        assert "live" in ids

    def test_live_view_in_views(self, app_fixture):
        assert "live" in H.VIEWS
        assert H.VIEWS["live"][0] == "LIVE"

    def test_compute_live_keys(self, app_fixture):
        d = app_fixture.compute_live()
        for key in ("jd", "lon_s", "lon_m", "m_alt", "s_alt", "illum",
                    "age_h", "phase", "moonrise", "moonset", "local"):
            assert key in d
        assert 0.0 <= d["illum"] <= 1.0
        assert d["age_h"] >= 0.0

    def test_phase_names(self, app_fixture):
        assert app_fixture._phase_name(-175.0) == "Full Moon"
        assert app_fixture._phase_name(5.0) == "New Moon"
        assert app_fixture._phase_name(95.0) == "First Quarter"
        assert app_fixture._phase_name(-95.0) == "Last Quarter"
        assert app_fixture._phase_name(40.0) == "Waxing Crescent"
        assert app_fixture._phase_name(120.0) == "Waxing Gibbous"
        assert app_fixture._phase_name(-40.0) == "Waning Crescent"
        assert app_fixture._phase_name(-120.0) == "Waning Gibbous"

    def test_live_canvas_renders(self, app_fixture):
        app_fixture.view = "live"
        app_fixture.live = None
        app_fixture.draw_live_canvas()  # must not raise

    def test_textures_loaded_or_missing(self, app_fixture):
        for key in ("sun", "earth", "moon"):
            assert key in app_fixture.tex
        if app_fixture.tex["sun"] is not None:
            assert app_fixture.tex["sun"].get_size() == (256, 256)
        if app_fixture.tex["earth"] is not None:
            assert app_fixture.tex["earth"].get_size() == (2048, 1024)
        if app_fixture.tex["moon"] is not None:
            assert app_fixture.tex["moon"].get_size() == (512, 256)

    def test_render_earth_globe(self, app_fixture):
        if app_fixture.tex["earth"] is None:
            pytest.skip("earth texture missing")
        spr = app_fixture._render_earth_globe(20, 200.0)
        assert spr.get_size() == (41, 41)
        assert spr.get_at((20, 20))[3] == 255  # inside the disk, opaque

    def test_render_moon_globe_full_and_new(self, app_fixture):
        if app_fixture.tex["moon"] is None:
            pytest.skip("moon texture missing")
        def brightness(spr):
            return sum(max(spr.get_at((x, y))[:3]) for y in range(41)
                       for x in range(41))
        full = brightness(app_fixture._render_moon_globe(20, 1.0, 0.0))
        new = brightness(app_fixture._render_moon_globe(20, 0.01, 0.0))
        assert full > new * 1.5  # full moon is far brighter than a new sliver

    def test_render_sun_alpha(self, app_fixture):
        if app_fixture.tex["sun"] is None:
            pytest.skip("sun texture missing")
        spr = app_fixture._render_sun(10)
        opaque = sum(1 for y in range(21) for x in range(21)
                     if spr.get_at((x, y))[3] > 0)
        assert 0 < opaque < 21 * 21  # alpha disc, not a filled square

    def test_live_panel_renders(self, app_fixture):
        app_fixture.live = None
        app_fixture.view = "live"
        surf = pygame.Surface((H.PANEL_W, H.CANVAS_H), pygame.SRCALPHA)
        app_fixture._panel_live(surf)  # must not raise


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
