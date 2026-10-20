"""Titel lesen und Termine verteilen. Netzwerk wird nicht beruehrt."""

from datetime import datetime, time, timedelta
from zoneinfo import ZoneInfo

from videoclipper import ausgabe, veroeffentlichen as v

B = ZoneInfo("Europe/Berlin")
RASTER = dict(ab=time(10), bis=time(22), abstand=timedelta(hours=1), zone=B)


def test_titel_rundreise(tmp_path):
    lauf = ausgabe.Lauf(tmp_path)
    lauf.titel([("abc_001", "tiktok eins 💀 #paris", "YouTube eins"),
                ("abc_002", "tiktok zwei", "YouTube zwei")])
    t = v.lies_titel((tmp_path / "titel.md").read_text(encoding="utf-8"))
    assert t == {"abc_001": {"tiktok": "tiktok eins 💀 #paris", "youtube": "YouTube eins"},
                 "abc_002": {"tiktok": "tiktok zwei", "youtube": "YouTube zwei"}}


def test_nachts_beginnt_es_um_zehn():
    t = v.zeitplan(3, datetime(2026, 10, 21, 0, 30, tzinfo=B), **RASTER)
    assert [x.hour for x in t] == [10, 11, 12]
    assert all(x.date().day == 21 for x in t)


def test_nachmittags_naechste_volle_stunde():
    t = v.zeitplan(2, datetime(2026, 10, 21, 13, 20, tzinfo=B), **RASTER)
    assert [x.hour for x in t] == [14, 15]


def test_nach_dem_raster_naechster_tag():
    t = v.zeitplan(3, datetime(2026, 10, 21, 21, 30, tzinfo=B), **RASTER)
    assert [(x.day, x.hour) for x in t] == [(21, 22), (22, 10), (22, 11)]


def test_belegte_termine_werden_uebersprungen():
    belegt = [datetime(2026, 10, 21, h, tzinfo=B) for h in (10, 11, 13)]
    t = v.zeitplan(3, datetime(2026, 10, 21, 8, tzinfo=B), belegt=belegt, **RASTER)
    assert [x.hour for x in t] == [12, 14, 15]
