"""Tests for islamic.py and the Ramadan/Eid calendar button in the app."""

import os
os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

import datetime

import pytest

import islamic


def _events(lat, lon, tz, now):
    evs = {e["name"]: e for e in islamic.events(lat, lon, tz, now)["events"]}
    return evs


class TestDates:
    def test_returns_three_events(self):
        d = islamic.events(51.5, -0.1, 0)
        names = [e["name"] for e in d["events"]]
        assert names == ["Ramadan", "Eid ul Fitr", "Eid ul Adha"]

    def test_prev_next_flank_today(self):
        now = datetime.datetime(2025, 7, 1)
        for e in islamic.events(51.5, -0.1, 0, now)["events"]:
            assert e["prev"] is not None and e["next"] is not None
            assert e["prev"][0] < e["next"][0]
            assert e["prev"][1] <= now.date() < e["next"][1]

    def test_eid_fitr_about_month_after_ramadan(self):
        now = datetime.datetime(2025, 1, 1)
        evs = _events(51.5, -0.1, 0, now)
        r, f = evs["Ramadan"]["next"], evs["Eid ul Fitr"]["next"]
        assert 28 <= (f[1] - r[1]).days <= 30

    def test_eid_adha_after_eid_fitr(self):
        now = datetime.datetime(2025, 1, 1)
        evs = _events(51.5, -0.1, 0, now)
        f, a = evs["Eid ul Fitr"]["next"], evs["Eid ul Adha"]["next"]
        assert (a[1] - f[1]).days >= 65

    def test_known_ramadan_1446(self):
        now = datetime.datetime(2025, 2, 1)
        evs = _events(51.5, -0.1, 0, now)
        assert evs["Ramadan"]["next"] == (1446, datetime.date(2025, 3, 1))

    def test_known_eid_fitr_1446(self):
        now = datetime.datetime(2025, 2, 1)
        evs = _events(51.5, -0.1, 0, now)
        assert evs["Eid ul Fitr"]["next"] == (1446, datetime.date(2025, 3, 30))

    def test_known_ramadan_1447(self):
        now = datetime.datetime(2026, 1, 1)
        evs = _events(51.5, -0.1, 0, now)
        assert evs["Ramadan"]["next"] == (1447, datetime.date(2026, 2, 18))

    def test_mecca_dates_valid(self):
        evs = _events(21.4, 39.8, 3, datetime.datetime(2026, 1, 1))
        assert evs["Ramadan"]["next"][1] == datetime.date(2026, 2, 18)

    def test_round_trip_years(self):
        now = datetime.datetime(2025, 1, 1)
        evs = _events(24.5, 54.4, 4, now)
        for e in ("Ramadan", "Eid ul Fitr", "Eid ul Adha"):
            assert evs[e]["prev"][0] == 1445
            assert evs[e]["next"][0] == 1446


class TestAppCalendar:
    @pytest.fixture(scope="module")
    def app(self):
        import hilal_sighting as H
        a = H.HilalApp()
        a.date = datetime.datetime(2025, 5, 1)
        a.lat, a.lon, a.tz = 21.4, 39.8, 3
        a.city = "Mecca, Saudi Arabia"
        a.refresh(force=True)
        yield a

    def test_calendar_button_present(self, app):
        ids = {b["id"] for b in app.buttons}
        assert "dates" in ids

    def test_activate_dates_opens_and_computes(self, app):
        assert app.show_dates is False
        app.activate("dates")
        assert app.show_dates is True
        assert app.dates_data is not None
        assert len(app.dates_data["events"]) == 3
        app.activate("dates")
        assert app.show_dates is False

    def test_click_calendar_button_toggles(self, app):
        b = next(x for x in app.buttons if x["id"] == "dates")
        assert app.show_dates is False
        app.activate(b["id"])
        assert app.show_dates is True
        app.activate(b["id"])
        assert app.show_dates is False

    def test_modal_renders(self, app):
        app.activate("dates")
        try:
            app.draw()  # must not raise
        finally:
            app.show_dates = False

    def test_fmt_line_has_ah(self, app):
        line = app._fmt_dates_line("1 Ramadan", 1447, datetime.date(2026, 2, 18))
        assert "18 Feb 2026" in line
        assert "1 Ramadan 1447 AH" in line
