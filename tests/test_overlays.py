"""Tests fuer die beiden Pflicht-Overlays.

Bewusst die Stellen, die still falsch sein koennen. Ein Clip ohne Untertitel
sieht im QC genauso aus wie einer mit: richtige Dauer, richtige Aufloesung,
Tonspur vorhanden. Und ein Cue, der 0.2 s aufblitzt oder unter TikToks UI
haengt, faellt erst im Feed auf — dort aber jedem.
"""

from __future__ import annotations

import pytest
from videoclipper import follow, layout, qc, untertitel
from videoclipper.transcript import Transkript, Wort


@pytest.fixture
def tmpl():
    return layout.template("SOLO_FULL")


def _tr(*paare: tuple[str, float, float]) -> Transkript:
    return Transkript("t", "de", tuple(Wort(t, a, b) for t, a, b in paare))


def _conf(tmpl, **kw):
    c = dict(tmpl["untertitel"])
    c.update(kw)
    return c


# --- Templates tragen die Pflicht-Overlays ---------------------------------

def test_jedes_template_traegt_beide_overlays():
    """Das ist die eigentliche Zusage: kein Clip ohne Untertitel und Follow."""
    from videoclipper.layout import ROOT
    import yaml
    namen = [yaml.safe_load(p.read_text(encoding="utf-8"))["name"]
             for p in (ROOT / "config" / "templates").glob("*.yaml")]
    assert namen
    for name in namen:
        assert qc.pflichtelemente(layout.template(name)) == [], name


def _schneiden(a: tuple, b: tuple) -> bool:
    """Ueberlappen sich zwei Rechtecke (x, y, breite, hoehe)?"""
    ax, ay, aw, ah = a
    bx, by, bw, bh = b
    return ax < bx + bw and bx < ax + aw and ay < by + bh and by < ay + ah


def test_kein_template_laesst_die_drei_textebenen_kollidieren():
    """Headline, Follow-Knopf und Untertitelband duerfen sich nie beruehren.

    Sie stehen an drei verschiedenen Orten: Headline im Template, die beiden
    anderen in config/overlays.yaml. Wer eine Headline tiefer setzt, sieht den
    Knopf nicht — und im fertigen Clip liegt dann Text auf Text.

    Geprueft werden Rechtecke, nicht die Reihenfolge von oben nach unten. Die
    stand hier bis zum 2026-09-11 als Zusage (Headline -> Knopf -> Band); bei
    PHONE_STACK sitzt der Knopf seitdem im Facecam-Panel und damit UEBER der
    Headline, weil im Handypanel nichts frei ist (siehe Template).
    """
    import yaml
    from videoclipper.layout import ROOT
    for pfad in (ROOT / "config" / "templates").glob("*.yaml"):
        t = layout.template(yaml.safe_load(pfad.read_text(encoding="utf-8"))["name"])
        cw, _ = t["canvas"]
        hc = t["headline"]
        zh = int(hc["schriftgroesse"] * 1.12)
        halb = zh * hc.get("max_zeilen", 2) // 2
        mb = int(hc.get("max_breite", cw))
        headline = ((cw - mb) // 2, hc["y"] - halb, mb, 2 * halb)
        knopf = follow.masse(t)
        assert not _schneiden(headline, knopf), t["name"]
        if t["untertitel"].get("aktiv", True):
            oben, hoehe = untertitel.band(t)
            band = (0, oben, cw, hoehe)
            assert not _schneiden(knopf, band), t["name"]
            assert not _schneiden(headline, band), t["name"]


def test_knopf_darf_seitlich_stehen():
    """PHONE_STACK setzt ``x`` — Knopf und Zielpunkt des Zeigers wandern mit."""
    t = layout.template("PHONE_STACK")
    x, _, k, _ = follow.masse(t)
    assert x + k // 2 == t["follow_hinweis"]["x"]
    h = follow.Hinweis("X", 10.0, 13.0)
    anflug = [s for s in follow.szene(h, t) if s.name == "zeiger"][0]
    _, _, polster = follow._zeiger_masse(t["follow_hinweis"])
    assert abs(_eval(anflug.x, t=anflug.bis) + polster - t["follow_hinweis"]["x"]) < 40
    assert _eval(anflug.x, t=anflug.ab) > t["canvas"][0], "Zeiger startet im Bild"


def test_abschalten_ohne_grund_ist_ein_fehler(tmpl):
    tmpl["untertitel"] = {"aktiv": False}
    assert qc.pflichtelemente(tmpl)


def test_abschalten_mit_grund_ist_erlaubt(tmpl):
    tmpl["untertitel"] = {"aktiv": False, "grund": "Format hat keine Quelle"}
    assert qc.pflichtelemente(tmpl) == []


def test_template_darf_einzelne_werte_ueberschreiben():
    """TOP5_COUNTDOWN setzt nur y — der Rest kommt aus config/overlays.yaml."""
    t = layout.template("TOP5_COUNTDOWN")
    assert t["follow_hinweis"]["y"] == 1650
    assert t["follow_hinweis"]["text"] == layout.template("SOLO_FULL")[
        "follow_hinweis"]["text"]


# --- Untertitel: Schnitt ---------------------------------------------------

def test_marker_werden_nicht_gesetzt(tmpl):
    """[gelaechter] ist eine Annotation von YouTube, kein gesprochenes Wort."""
    tr = _tr(("Hallo", 0.0, 0.5), ("[gelächter]", 0.5, 1.5), ("Welt", 1.5, 2.0))
    cues = untertitel.schneide(tr, 0.0, 3.0, tmpl["untertitel"])
    assert "gelächter" not in " ".join(c.text for c in cues)


def test_satzende_bricht_die_zeile(tmpl):
    tr = _tr(("Stell", 0.0, 0.2), ("dich", 0.2, 0.4), ("vor.", 0.4, 0.6),
             ("Also,", 0.6, 0.8), ("ich", 0.8, 1.0))
    cues = untertitel.schneide(tr, 0.0, 2.0, _conf(tmpl, max_halten=0.0))
    assert cues[0].text == "Stell dich vor."


def test_initialen_brechen_nicht(tmpl):
    """'Maus L.' ist kein Satzende — sonst steht der Nachname allein im Bild."""
    tr = _tr(("Gute", 0.0, 0.2), ("Maus", 0.2, 0.4), ("L.", 0.4, 0.6),
             ("Gute", 0.6, 0.8))
    cues = untertitel.schneide(tr, 0.0, 2.0, _conf(tmpl, max_halten=0.0))
    assert cues[0].text == "Gute Maus L. Gute"


def test_sprechpause_bricht_die_zeile(tmpl):
    tr = _tr(("eins", 0.0, 0.3), ("zwei", 2.0, 2.3))
    cues = untertitel.schneide(tr, 0.0, 3.0, tmpl["untertitel"])
    assert [c.text for c in cues] == ["eins", "zwei"]


def test_lange_rede_bricht_an_der_zeichenzahl(tmpl):
    tr = _tr(*[(f"wort{i}", i * 0.1, i * 0.1 + 0.1) for i in range(30)])
    conf = _conf(tmpl, satzende=False, max_dauer=99.0)
    for c in untertitel.schneide(tr, 0.0, 5.0, conf):
        assert len(c.text) <= conf["max_zeichen"]


# --- Untertitel: Zeitachse -------------------------------------------------

def test_kein_cue_blitzt_nur_auf(tmpl):
    """Unter min_dauer wuerde der Text erscheinen und wieder weg sein."""
    tr = _tr(("ja.", 0.0, 0.12), ("nein.", 2.0, 2.2))
    cues = untertitel.schneide(tr, 0.0, 4.0, tmpl["untertitel"])
    for c in cues:
        assert c.bis - c.ab >= tmpl["untertitel"]["min_dauer"] - 1e-6


def test_abgeschnittener_letzter_cue_faellt_weg(tmpl):
    """Der Nachlauf aus ``snappe`` zieht oft das naechste Wort halb mit herein.

    GEMESSEN am 2026-09-07 an utB7GTrmLYY: Drei von acht Clips endeten auf
    einem 0.35-s-Fetzen ("E ich", "Ja, ich habe"). Mitten im Clip kann
    ``min_dauer`` so einen Cue noch dehnen, am Fensterrand nicht — dort blitzt
    er genau so lange auf, wie er lang ist, und der Clip sieht aus, als sei er
    mitten im Satz abgeschnitten.
    """
    tr = _tr(("Das", 0.0, 0.5), ("reicht.", 0.5, 1.0), ("Und", 1.9, 2.1))
    cues = untertitel.schneide(tr, 0.0, 2.05, tmpl["untertitel"])
    assert [c.text for c in cues] == ["Das reicht."]


def test_kurzes_letztes_wort_haengt_am_satz_statt_zu_verschwinden(tmpl):
    """GEMESSEN an saiJDq9DM_Y: Seit ``snappe`` am echten Wortende schneidet,
    ist der kurze letzte Cue oft das Wort der Pointe selbst — "angreifen."
    steht im Transkript bis 543.12 s, gesprochen ist es um 541.0 zu Ende."""
    tr = _tr(("Der", 0.0, 0.2), ("soll", 0.2, 0.4), ("da", 0.4, 0.6),
             ("noch", 0.6, 0.8), ("mal", 0.8, 1.0), ("angreifen.", 1.0, 3.6))
    cues = untertitel.schneide(tr, 0.0, 1.5, tmpl["untertitel"])
    assert [c.text for c in cues] == ["Der soll da noch mal angreifen."]
    assert cues[-1].bis == pytest.approx(1.5)


def test_wort_vor_dem_clip_steht_nicht_im_ersten_cue(tmpl):
    """GEMESSEN an saiJDq9DM_Y: "Sternen," war vor dem Clipanfang zu Ende
    gesprochen, sein Transkriptende reicht aber bis zum naechsten Wort — der
    erste Cue lautete "Sternen, ob Sydney Friede"."""
    tr = _tr(("Sternen,", 0.0, 0.92), ("ob", 0.92, 1.2), ("Sydney", 1.2, 1.64),
             ("Friede", 1.64, 2.0), ("spielen", 2.0, 2.32), ("kann.", 2.32, 2.8))
    cues = untertitel.schneide(tr, 0.76, 3.3, tmpl["untertitel"])
    assert cues[0].text.startswith("ob ")
    assert "Sternen" not in " ".join(c.text for c in cues)


def test_vollstaendiger_letzter_cue_bleibt(tmpl):
    """Nur der abgeschnittene faellt weg — ein Cue, der von selbst endet, nicht."""
    tr = _tr(("Das", 0.0, 0.5), ("reicht.", 0.5, 1.0))
    cues = untertitel.schneide(tr, 0.0, 6.0, tmpl["untertitel"])
    assert [c.text for c in cues] == ["Das reicht."]
    assert cues[-1].bis - cues[-1].ab >= tmpl["untertitel"]["min_dauer"] - 1e-6


def test_kurzer_cue_mitten_im_clip_bleibt_stehen(tmpl):
    """Die Regel gilt nur am Fensterrand. Sonst verschwaende Gesprochenes."""
    tr = _tr(("Was", 0.0, 0.2), ("hab?", 0.2, 0.5), ("Spaeter.", 5.0, 5.4))
    cues = untertitel.schneide(tr, 0.0, 8.0, tmpl["untertitel"])
    assert "Was hab?" in [c.text for c in cues]


def test_cues_ueberlappen_sich_nie(tmpl):
    """Zwei Standbilder gleichzeitig waeren zwei Zeilen uebereinander."""
    tr = _tr(*[(f"w{i}.", i * 0.5, i * 0.5 + 0.3) for i in range(12)])
    cues = untertitel.schneide(tr, 0.0, 6.0, tmpl["untertitel"])
    for a, b in zip(cues, cues[1:]):
        assert a.bis <= b.ab + 1e-6


def test_cues_bleiben_im_clipfenster(tmpl):
    tr = _tr(("vorher", 0.0, 4.0), ("drin", 12.0, 12.4), ("nachher", 19.0, 25.0))
    cues = untertitel.schneide(tr, 10.0, 20.0, tmpl["untertitel"])
    assert cues
    for c in cues:
        assert 0.0 <= c.ab < c.bis <= 10.0


def test_ein_cue_haelt_nicht_ewig_stehen(tmpl):
    """Nach dem letzten Wort verschwindet er, sonst steht er ueber der naechsten
    Szene."""
    tr = _tr(("kurz.", 0.0, 0.4), ("spaeter.", 8.0, 8.4))
    cues = untertitel.schneide(tr, 0.0, 10.0, tmpl["untertitel"])
    assert cues[0].bis <= 0.4 + tmpl["untertitel"]["max_halten"] + 1e-6


# --- Untertitel: Lage und Animation ----------------------------------------

def test_band_bleibt_ueber_der_ui_zone(tmpl):
    oben, hoehe = untertitel.band(tmpl)
    frei = tmpl["canvas"][1] - tmpl["sicherheitszone"]["unten"]
    assert oben + hoehe <= frei


def test_band_im_ui_bereich_bricht_ab(tmpl):
    tmpl["untertitel"]["y"] = 1800
    with pytest.raises(ValueError, match="UI-Zone"):
        untertitel.band(tmpl)


def test_animation_endet_in_der_ruhelage(tmpl):
    """Nach der Einschwingzeit muss der Cue exakt auf der Bandkante sitzen."""
    cue = untertitel.Cue("x", 5.0, 7.0)
    ausdruck = untertitel.y_ausdruck(cue, 1424, tmpl["untertitel"])
    assert _eval(ausdruck, t=5.0) == pytest.approx(1424 + 26)
    assert _eval(ausdruck, t=5.14) == pytest.approx(1424)
    assert _eval(ausdruck, t=6.5) == pytest.approx(1424)


def _eval(ausdruck: str, t: float) -> float:
    """Die FFmpeg-Ausdruecke nachrechnen — sie nutzen nur pow/min/max."""
    return eval(ausdruck.replace("pow", "__pow"),
                {"__pow": pow, "min": min, "max": max, "t": t})


# --- Follow-Aufforderung ---------------------------------------------------

def test_steht_nicht_im_hook(tmpl):
    h, _ = follow.platziere(60.0, tmpl["follow_hinweis"])
    assert h.ab >= tmpl["follow_hinweis"]["nicht_vor"]


def test_steht_nicht_auf_der_pointe(tmpl):
    conf = tmpl["follow_hinweis"]
    for dauer in (8.0, 15.0, 27.0, 68.0, 90.0):
        h, _ = follow.platziere(dauer, conf)
        assert h.bis <= dauer - conf["nicht_nach_ende"] + 1e-6, dauer


def test_zu_kurzer_clip_bekommt_keine_aufforderung_sondern_eine_meldung(tmpl):
    h, meldungen = follow.platziere(4.0, tmpl["follow_hinweis"])
    assert h is None and meldungen


def test_pille_bleibt_ueber_der_ui_zone(tmpl):
    _, y, _, ph = follow.masse(tmpl)
    assert y + ph <= tmpl["canvas"][1] - tmpl["sicherheitszone"]["unten"]


def test_pille_kollidiert_nicht_mit_dem_untertitelband(tmpl):
    _, y, _, ph = follow.masse(tmpl)
    oben, _ = untertitel.band(tmpl)
    assert y + ph <= oben


def test_pille_hat_gerade_masse(tmpl):
    """In yuv420p rundet der Scaler ungerade Kanten still ab."""
    _, _, pw, ph = follow.masse(tmpl)
    assert pw % 2 == 0 and ph % 2 == 0


# --- Die Klickszene --------------------------------------------------------
#
# Seit dem 2026-09-08 ist die Aufforderung kein einzelnes Bild mehr, sondern
# eine Folge: Knopfzustaende plus ein Mauszeiger, der hereinfaehrt und drueckt.
# Geprueft wird, was im fertigen Clip sonst niemand mehr sieht.

def test_zeiger_kommt_von_ausserhalb_und_landet_auf_dem_knopf(tmpl):
    h = follow.Hinweis("X", 10.0, 13.0)
    cw, _ = tmpl["canvas"]
    cx, cy = cw // 2, tmpl["follow_hinweis"]["y"]
    anflug = [s for s in follow.szene(h, tmpl) if s.name == "zeiger"][0]

    assert _eval(anflug.x, t=anflug.ab) > cw, "Zeiger startet im Bild"
    # Am Ende der Fahrt steht die Spitze auf dem Knopf. Die Ausdruecke geben
    # die Bildecke zurueck, die Spitze liegt um das Polster versetzt darin.
    _, _, polster = follow._zeiger_masse(tmpl["follow_hinweis"])
    spitze_x = _eval(anflug.x, t=anflug.bis) + polster
    spitze_y = _eval(anflug.y, t=anflug.bis) + polster
    assert abs(spitze_x - cx) < 40 and abs(spitze_y - cy) < 40


def test_zeiger_verlaesst_das_bild_wieder(tmpl):
    h = follow.Hinweis("X", 10.0, 13.0)
    cw, _ = tmpl["canvas"]
    abflug = [s for s in follow.szene(h, tmpl) if s.name == "zeiger"][-1]
    assert _eval(abflug.x, t=abflug.bis) > cw


def test_knopfzustaende_ueberlappen_sich_nie(tmpl):
    """Zwei Zustaende gleichzeitig waeren ein doppelt gezeichneter Knopf."""
    h = follow.Hinweis("X", 10.0, 13.0)
    knoepfe = [s for s in follow.szene(h, tmpl) if s.name.startswith("knopf_")]
    for a, b in zip(knoepfe, knoepfe[1:]):
        assert a.bis < b.ab, (a.name, b.name)


def test_knopf_ist_ueber_das_ganze_fenster_zu_sehen(tmpl):
    """Zwischen den Zustaenden darf keine Luecke stehen, sonst blinkt er."""
    h = follow.Hinweis("X", 10.0, 13.0)
    knoepfe = [s for s in follow.szene(h, tmpl) if s.name.startswith("knopf_")]
    assert knoepfe[0].ab == pytest.approx(h.ab)
    assert knoepfe[-1].bis == pytest.approx(h.bis, abs=0.01)
    for a, b in zip(knoepfe, knoepfe[1:]):
        assert b.ab - a.bis < 0.01, (a.name, b.name)


def test_knopf_wird_rot_und_endet_weiss(tmpl):
    h = follow.Hinweis("X", 10.0, 13.0)
    knoepfe = [s for s in follow.szene(h, tmpl) if s.name.startswith("knopf_")]
    assert not knoepfe[0].zeichnung["weiss"]
    assert knoepfe[-1].zeichnung["weiss"]
    # Genau ein Wechsel: was einmal weiss ist, bleibt weiss.
    weiss = [bool(s.zeichnung["weiss"]) for s in knoepfe]
    assert weiss == sorted(weiss)


def test_szene_bleibt_im_fenster(tmpl):
    h = follow.Hinweis("X", 10.0, 13.0)
    for s in follow.szene(h, tmpl):
        assert h.ab - 1e-6 <= s.ab < s.bis <= h.bis + 1e-6, s.name


# --- Countdown -------------------------------------------------------------

def test_countdown_bekommt_die_aufforderung_aber_keine_untertitel():
    from videoclipper import countdown
    t = layout.template("TOP5_COUNTDOWN")
    plan = countdown.CountdownPlan.model_validate({
        "clip_id": "t", "titel": "Titel",
        "eintraege": [{"platz": p, "text": f"P{p}", "video_id": f"v{p}",
                       "start": 0.0, "dauer": 9.0} for p in range(1, 6)]})
    r = countdown.loese_auf(plan, t).aufgeloest
    assert r.follow and 0 < r.follow["ab"] < r.follow["bis"] < r.dauer
    assert not t["untertitel"]["aktiv"] and t["untertitel"]["grund"]
    # countdown.Aufgeloest kennt kein Feld ``untertitel``. Die Pruefung darf
    # daran nicht scheitern, auch wenn ein Template sie einmal einschaltet.
    assert qc.overlays_vorhanden(r, t) == []
    t["untertitel"] = {"aktiv": True}
    assert qc.overlays_vorhanden(r, t) == [
        "Keine Untertitel — im Clipfenster steht kein Wort im Transkript. "
        "Bitte den Clip ansehen."]


# --- Handkorrekturen an den Untertiteln ------------------------------------

def test_korrekturregeln_werden_ueber_den_ganzen_lauf_gezaehlt(tmpl, monkeypatch):
    """Eine Regel fuer Clip 3 greift in Clip 1 nicht — das ist keine Fehlmeldung.

    Je Clip gemeldet ergab das bei 22 Regeln und 4 Clips rund 60 Zeilen
    Rauschen, in dem die eine echte Fehlmeldung unterging.
    """
    regeln = [{"suche": "hier steht Unsinn", "ersetze": "hier steht Sinn"},
              {"suche": "und hier auch", "ersetze": "und hier nicht"},
              {"suche": "kommt nirgends vor", "ersetze": "egal"}]
    monkeypatch.setattr(untertitel, "regeln", lambda _vid: regeln)

    clip1, t1 = untertitel.korrigiere([untertitel.Cue("hier steht Unsinn", 0, 1)], "v")
    clip2, t2 = untertitel.korrigiere([untertitel.Cue("und hier auch", 0, 1)], "v")

    assert clip1[0].text == "hier steht Sinn"
    assert clip2[0].text == "und hier nicht"
    # Je Clip einzeln betrachtet haette jeder die Regel des anderen vermisst.
    assert untertitel.ungenutzte("v", t1) and untertitel.ungenutzte("v", t2)
    # Ueber den Lauf bleibt genau die eine uebrig, die wirklich nie greift.
    offen = untertitel.ungenutzte("v", t1 | t2)
    assert len(offen) == 1 and "kommt nirgends vor" in offen[0]


def test_hookpruefung_liest_die_korrigierte_schreibweise(monkeypatch):
    """GEMESSEN an saiJDq9DM_Y: Die ASR schreibt "Sydney", Headline und
    Kanaltitel "Sidney". Ohne die Korrektur galt jede Headline mit dem Namen
    als lose, obwohl er im Clip dutzendfach faellt."""
    from videoclipper import hook
    tr = _tr(("Was", 0.0, 0.3), ("ist", 0.3, 0.5), ("mit", 0.5, 0.7),
             ("Sydney?", 0.7, 1.2), ("Keine", 5.0, 5.3), ("Ahnung.", 5.3, 5.8))
    assert not hook.pruefe("WAS IST MIT SIDNEY", tr, 0.0, 6.0).verankert
    monkeypatch.setattr(untertitel, "regeln",
                        lambda _vid: [{"suche": "Sydney", "ersetze": "Sidney"}])
    assert hook.pruefe("WAS IST MIT SIDNEY", tr, 0.0, 6.0).verankert
