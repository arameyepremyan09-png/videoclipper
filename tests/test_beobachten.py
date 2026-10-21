"""Feed, Entscheidung, Laufpruefung, Agentenaufruf. Netzwerk wird nicht beruehrt."""

from datetime import datetime, timedelta, timezone
from pathlib import Path

from videoclipper import ausgabe, beobachten as b

UTC = timezone.utc
CONF = {**b.STANDARD}

FEED = """<?xml version="1.0" encoding="UTF-8"?>
<feed xmlns:yt="http://www.youtube.com/xml/schemas/2015" xmlns="http://www.w3.org/2005/Atom">
 <title>Coachlim</title>
 <entry>
  <yt:videoId>neu1</yt:videoId>
  <title>KAESE AUF OMETV</title>
  <link rel="alternate" href="https://www.youtube.com/watch?v=neu1"/>
  <published>2026-10-21T11:00:00+00:00</published>
 </entry>
 <entry>
  <yt:videoId>kurz1</yt:videoId>
  <title>ein Short</title>
  <link rel="alternate" href="https://www.youtube.com/shorts/kurz1"/>
  <published>2026-10-21T10:00:00+00:00</published>
 </entry>
</feed>"""

KANAL = b.Kanal("CoachLimTTV", "UCB62iJ-rz1Z2v0PyGh_W-Zg")


def test_feed_lesen():
    e = b.lies_feed(FEED)
    assert [(x.video_id, x.short) for x in e] == [("neu1", False), ("kurz1", True)]
    assert e[0].titel == "KAESE AUF OMETV"
    assert e[0].veroeffentlicht == datetime(2026, 10, 21, 11, tzinfo=UTC)


def test_kanaele_aus_dem_repo():
    k = b.kanaele()
    assert len(k) == 8
    assert all(x.channel_id.startswith("UC") for x in k)
    assert "channel_id=UC" in k[0].feed_url


def test_erster_abruf_holt_nichts_nach():
    stand = {"kanaele": {}, "videos": {}}
    jetzt = datetime(2026, 10, 21, 12, tzinfo=UTC)
    assert b.nimm_auf(stand, KANAL, b.lies_feed(FEED), jetzt) == []
    assert stand["videos"] == {}
    assert set(stand["kanaele"][KANAL.channel_id]["gesehen"]) == {"neu1", "kurz1"}


def test_neues_video_wartet_short_wird_uebersprungen():
    stand = {"kanaele": {KANAL.channel_id: {"handle": "CoachLimTTV",
                                            "seit": "2026-10-21T08:00:00+00:00",
                                            "gesehen": []}}, "videos": {}}
    neu = b.nimm_auf(stand, KANAL, b.lies_feed(FEED), datetime(2026, 10, 21, 12, tzinfo=UTC))
    assert [e.video_id for e in neu] == ["neu1", "kurz1"]
    assert stand["videos"]["neu1"]["status"] == "wartet"
    assert stand["videos"]["kurz1"]["status"] == "uebersprungen"
    # Zweiter Abruf: nichts doppelt.
    assert b.nimm_auf(stand, KANAL, b.lies_feed(FEED), datetime(2026, 10, 21, 13, tzinfo=UTC)) == []


def test_alte_videos_aus_der_zeit_vor_dem_start_bleiben_draussen():
    stand = {"kanaele": {KANAL.channel_id: {"handle": "CoachLimTTV",
                                            "seit": "2026-10-25T08:00:00+00:00",
                                            "gesehen": []}}, "videos": {}}
    assert b.nimm_auf(stand, KANAL, b.lies_feed(FEED), datetime(2026, 10, 25, 9, tzinfo=UTC)) == []


def _meta(**kw):
    return {"duration": 1800, "live_status": "not_live",
            "automatic_captions": {"de-orig": []}, **kw}


def test_entscheidung():
    e = b.entscheide(_meta(), CONF, 1.0, "de-orig")
    assert (e.art, e.transkript) == ("los", "youtube")
    assert b.entscheide(_meta(live_status="is_live"), CONF, 1.0, "de-orig").art == "warten"
    assert b.entscheide(_meta(live_status="post_live"), CONF, 1.0, "de-orig").art == "warten"
    assert b.entscheide(_meta(duration=58), CONF, 1.0, "de-orig").art == "ueberspringen"
    assert b.entscheide(_meta(duration=6 * 3600), CONF, 1.0, "de-orig").art == "ueberspringen"


def test_mit_wartezeit_erst_warten_dann_asr():
    ohne = _meta(automatic_captions={"en": []})
    conf = {**CONF, "warte_auf_untertitel_h": 4.0}
    assert b.entscheide(ohne, conf, 1.0, "de-orig").art == "warten"
    e = b.entscheide(ohne, conf, 5.0, "de-orig")
    assert (e.art, e.transkript) == ("los", "asr")


def _lauf(basis: Path, video_id="abc", titel=True) -> Path:
    lauf = ausgabe.neuer_lauf(basis)
    lauf.notiere(video_id=video_id)
    (lauf.mp4 / f"{video_id}_001.mp4").write_bytes(b"x")
    if titel:
        lauf.titel([(f"{video_id}_001", "tiktok 💀 #x", "YouTube eins")])
    return lauf.wurzel


def test_lauf_pruefung(tmp_path):
    assert b.pruefe_lauf(_lauf(tmp_path), "abc", tmp_path) == []
    assert "gehoert nicht zu xyz" in b.pruefe_lauf(_lauf(tmp_path), "xyz", tmp_path)[0]
    assert "titel.md fehlt" in b.pruefe_lauf(_lauf(tmp_path, titel=False), "abc", tmp_path)


def test_lauf_ausserhalb_der_ausgabe_wird_nicht_hochgeladen(tmp_path):
    lauf = _lauf(tmp_path / "anderswo")
    assert "liegt nicht unter" in b.pruefe_lauf(lauf, "abc", tmp_path / "automat")[0]


def test_auftrag_fuellt_alle_felder(tmp_path):
    v = {"kanal": "CoachLimTTV", "titel": "KAESE {klammer}"}
    text = b.auftrag("abc", v, 1800, tmp_path / "abc.mp4", tmp_path / "abc.json3",
                     "asr", CONF, tmp_path / "erg.json")
    assert "KAESE {klammer}" in text and "30 min" in text
    assert "asr_fenster.py" in text
    assert '{"status": "fertig"' in text
    assert "{" + "clips}" not in text


def test_agent_ohne_upload_und_auftrag_nicht_in_argv():
    befehl = b.agent_befehl(CONF, "sid", "automat abc")
    assert befehl[:2] == ["claude", "-p"]
    assert "--strict-mcp-config" in befehl
    # Die Verbote stehen hinten: --disallowedTools nimmt alles bis zum Ende.
    i = befehl.index("--disallowedTools")
    assert tuple(befehl[i + 1:]) == b.VERBOTEN
    assert any("poste" in x for x in b.VERBOTEN)
    werkzeuge = befehl[befehl.index("--tools") + 1]
    assert "WebFetch" not in werkzeuge and "Bash" in werkzeuge


def test_standard_fuenf_clips_und_top5():
    assert CONF["clips_pro_video"] == 5 and CONF["top5"] is True
    # Auf Abruf: fehlt de-orig, wird sofort transkribiert statt gewartet.
    e = b.entscheide(_meta(automatic_captions={}), CONF, 0.5, "de-orig")
    assert (e.art, e.transkript) == ("los", "asr")


def test_countdown_lauf_gehoert_ueber_quellen_zum_video(tmp_path):
    lauf = ausgabe.neuer_lauf(tmp_path)
    lauf.notiere(format="countdown", quellen=["abc"], clips=1)
    (lauf.mp4 / "abc_top5.mp4").write_bytes(b"x")
    lauf.titel([("abc_top5", "Top 5 💀 #top5", "Top 5 Momente")])
    assert b.pruefe_lauf(lauf.wurzel, "abc", tmp_path) == []
    assert b.pruefe_lauf(lauf.wurzel, "xyz", tmp_path)


def test_auftrag_mit_und_ohne_top5(tmp_path):
    v = {"kanal": "K", "titel": "T"}
    args = ("abc", v, 600, tmp_path / "v.mp4", tmp_path / "t.json3", "youtube")
    mit = b.auftrag(*args, CONF, tmp_path / "e.json")
    assert "5 Clips und ein Top 5" in mit and "data/plans/abc_top5.json" in mit
    assert "kein Top 5" not in mit
    ohne = b.auftrag(*args, {**CONF, "top5": False}, tmp_path / "e.json")
    assert "Diesmal kein Top 5" in ohne


def _bereit(monkeypatch, tmp_path, erg):
    """bearbeite() bis zum Agenten ohne Netz, Platte und Agent."""
    monkeypatch.setattr(b, "metadaten", lambda vid: _meta())
    monkeypatch.setattr(b, "frei_gb", lambda: 500.0)
    monkeypatch.setattr(b, "naechster_termin", lambda jetzt: jetzt + timedelta(hours=1))
    monkeypatch.setattr(b, "lade", lambda vid, art, conf: (tmp_path / "v.mp4", tmp_path / "t"))
    monkeypatch.setattr(b, "clippe", lambda *a: erg)
    monkeypatch.setattr(b, "ausgabe_ordner", lambda: tmp_path)
    monkeypatch.setattr(b, "mitteilung", lambda text: None)
    hoch = []
    monkeypatch.setattr(b.veroeffentlichen, "veroeffentliche",
                        lambda lauf, **kw: hoch.append(lauf) or {"youtube_offen": 0})
    return hoch


def _video():
    return {"kanal": "K", "titel": "T", "status": "wartet", "versuche": 0,
            "veroeffentlicht": "2026-10-21T10:00:00+00:00",
            "entdeckt": "2026-10-21T11:00:00+00:00"}


def test_clips_und_top5_gehen_beide_hoch(monkeypatch, tmp_path):
    clips = _lauf(tmp_path)
    top5 = ausgabe.neuer_lauf(tmp_path)
    top5.notiere(format="countdown", quellen=["abc"])
    (top5.mp4 / "abc_top5.mp4").write_bytes(b"x")
    top5.titel([("abc_top5", "Top 5", "Top 5 Momente")])
    hoch = _bereit(monkeypatch, tmp_path, {"status": "fertig", "lauf": str(clips),
                                           "top5": str(top5.wurzel), "clips": 5})
    v = _video()
    b.bearbeite("abc", v, CONF, datetime(2026, 10, 21, 12, tzinfo=UTC), lambda: None,
                lambda t: None)
    assert hoch == [clips, top5.wurzel]
    assert v["status"] == "geplant"


def test_fehlender_top5_haelt_die_clips_nicht_auf(monkeypatch, tmp_path):
    clips = _lauf(tmp_path)
    hoch = _bereit(monkeypatch, tmp_path, {"status": "fertig", "lauf": str(clips),
                                           "top5": None, "clips": 5})
    v = _video()
    b.bearbeite("abc", v, CONF, datetime(2026, 10, 21, 12, tzinfo=UTC), lambda: None,
                lambda t: None)
    assert hoch == [clips]
    assert v["status"] == "geplant" and v["top5_fehlt"] == "kein Top 5 geliefert"


def test_alter_stand_mit_einzelnem_lauf():
    assert b.laeufe({"lauf": "/x"}) == [Path("/x")]
    assert b.laeufe({"laeufe": ["/x", "/y"]}) == [Path("/x"), Path("/y")]
    assert b.laeufe({}) == []


def test_stand_rundreise(tmp_path):
    pfad = tmp_path / "stand.json"
    stand = {"kanaele": {}, "videos": {"a": {"status": "wartet"}}}
    b.speichere_stand(stand, pfad)
    assert b.lade_stand(pfad) == stand
    assert b.lade_stand(tmp_path / "fehlt.json") == {"kanaele": {}, "videos": {}}
