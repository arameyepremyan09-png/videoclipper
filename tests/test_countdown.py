"""Tests fuer das Compilation-Format.

Bewusst die Stellen, die still falsch sein koennen. Eine Countdown-Liste sieht
auch dann richtig aus, wenn die Reihenfolge kippt oder ein Zustand einen Platz
zu frueh zeigt — im fertigen Video faellt das erst auf, wenn die Pointe schon
oben steht, bevor sie kommt.
"""

from __future__ import annotations

import pytest
from videoclipper import countdown, layout


@pytest.fixture
def tmpl():
    return layout.template("TOP5_COUNTDOWN")


def _plan(**kw):
    eintraege = [
        {"platz": p, "text": f"Platz {p}", "video_id": f"v{p}",
         "start": 10.0 * p, "dauer": 5.0}
        for p in range(1, 6)
    ]
    daten = {"clip_id": "t", "titel": "Titel", "eintraege": eintraege,
         "upload": {"tiktok": "TikTok", "youtube": "Shorts"}}
    daten.update(kw)
    return countdown.CountdownPlan.model_validate(daten)


# --- Reihenfolge -----------------------------------------------------------

def test_abgespielt_wird_von_platz_fuenf_nach_platz_eins(tmpl):
    r = countdown.loese_auf(_plan(), tmpl).aufgeloest
    assert [s["platz"] for s in r.segmente] == [5, 4, 3, 2, 1]


def test_platz_eins_steht_erst_im_letzten_zustand(tmpl):
    """Der Payoff darf nicht vorher schon in der Liste stehen."""
    r = countdown.loese_auf(_plan(), tmpl).aufgeloest
    for seg in r.segmente[:-1]:
        assert 1 not in seg["sichtbar"]
    assert r.segmente[-1]["sichtbar"] == [5, 4, 3, 2, 1]


def test_jeder_zustand_zeigt_genau_die_bisherigen_plaetze(tmpl):
    r = countdown.loese_auf(_plan(), tmpl).aufgeloest
    for i, seg in enumerate(r.segmente):
        assert seg["sichtbar"] == sorted(range(5 - i, 6), reverse=True)


# --- Zeitachse -------------------------------------------------------------

def test_segmente_stossen_lueckenlos_aneinander(tmpl):
    r = countdown.loese_auf(_plan(), tmpl).aufgeloest
    for a, b in zip(r.segmente, r.segmente[1:]):
        assert a["bis"] == pytest.approx(b["ab"])
    assert r.dauer == pytest.approx(25.0)


# --- Vertrag ---------------------------------------------------------------

def test_luecke_in_den_plaetzen_wird_abgewiesen():
    with pytest.raises(ValueError, match="lueckenlos"):
        countdown.CountdownPlan.model_validate({
            "clip_id": "t", "titel": "Titel",
            "upload": {"tiktok": "Testtitel fuer TikTok", "youtube": "Testtitel fuer Shorts"},
            "eintraege": [
                {"platz": 1, "text": "a", "video_id": "v", "start": 0, "dauer": 1},
                {"platz": 3, "text": "b", "video_id": "v", "start": 0, "dauer": 1},
            ]})


def test_falsche_anzahl_plaetze_wird_abgewiesen(tmpl):
    plan = countdown.CountdownPlan.model_validate({
        "clip_id": "t", "titel": "Titel",
        "upload": {"tiktok": "Testtitel fuer TikTok", "youtube": "Testtitel fuer Shorts"},
        "eintraege": [
            {"platz": 1, "text": "a", "video_id": "v", "start": 0, "dauer": 1},
            {"platz": 2, "text": "b", "video_id": "v", "start": 0, "dauer": 1},
        ]})
    with pytest.raises(ValueError, match="erwartet 5 Plaetze"):
        countdown.loese_auf(plan, tmpl)


def test_ungerade_panelmasse_brechen_ab(tmpl):
    """In yuv420p rundet der Scaler still ab — lieber hier scheitern."""
    kaputt = dict(tmpl)
    kaputt["panels"] = [{"quelle": "segment", "ziel": [60, 812, 960, 917],
                         "passung": "einpassen"}]
    with pytest.raises(ValueError, match="gerade"):
        countdown.loese_auf(_plan(), kaputt)


# --- Sicherheitszone -------------------------------------------------------

def test_top5_bleibt_ueber_der_ui_zone(tmpl):
    assert countdown.sicherheitszone_pruefen(tmpl) == []


def test_panel_bis_zum_bildrand_wird_gemeldet(tmpl):
    """GAME_STACK laesst sein unteres Panel bis y=1920 laufen — das ist gemeint."""
    kaputt = dict(tmpl)
    kaputt["panels"] = [{"quelle": "segment", "ziel": [0, 606, 1080, 1314],
                         "passung": "einpassen"}]
    hinweise = countdown.sicherheitszone_pruefen(kaputt)
    assert len(hinweise) == 1 and "y=1920" in hinweise[0]


# --- Renderpfad ------------------------------------------------------------

def test_filtergraph_hat_je_stueck_der_klickszene_einen_eingang(tmpl):
    """Die Follow-Szene ist seit dem 2026-09-08 eine Bildfolge, kein Bild.

    Der Compilation-Pfad baut seinen Graphen von Hand und zaehlt die Eingaenge
    selbst hoch. Zaehlt er falsch, greift ein ``overlay`` auf den falschen
    Eingang — im fertigen Video steht dann die Countdown-Liste dort, wo der
    Knopf sein sollte, und niemand sieht dem Graphen das an.
    """
    from videoclipper import follow, render

    plan = countdown.loese_auf(_plan(), tmpl)
    r = plan.aufgeloest
    assert r.follow, "Der Countdown traegt die Aufforderung"

    h = follow.Hinweis(r.follow["text"], r.follow["ab"], r.follow["bis"])
    stuecke = follow.szene(h, tmpl)
    graph = render.filtergraph_countdown(plan, tmpl, -14.0)

    # Eingaenge: N Segmente, 1 Headline, N Listenzustaende, dann die Szene.
    n = len(r.segmente)
    erster = n + 1 + n
    for j in range(len(stuecke)):
        assert f"[{erster + j}:v]" in graph, j
    assert f"[{erster + len(stuecke)}:v]" not in graph


# --- Liste mit Emojis (TOP5_HALLOFCLIPS, 2026-09-16) -----------------------

def _alpha_spalten(pfad, y, halbe_hoehe=40):
    import numpy as np
    from PIL import Image
    a = np.asarray(Image.open(pfad))[..., 3]
    return np.flatnonzero(a[int(y) - halbe_hoehe:int(y) + halbe_hoehe].max(axis=0) > 0)


def test_beschriftung_mit_emoji_steht_als_gruppe_mittig(tmp_path):
    """Die Referenzen setzen Text und Emoji zusammen mittig, nicht den Text allein."""
    from videoclipper import liste
    t = layout.template("TOP5_HALLOFCLIPS")
    conf = t["liste"]
    pfad = liste.baue_zustand({5: "Chaya reiten 💀"}, t, tmp_path / "l.png")
    y5 = conf["erste_zeile_y"] + 4 * conf["zeilenabstand"]
    xs = _alpha_spalten(pfad, y5)
    gruppe = xs[xs > conf["ziffer_x"] + 60]      # ohne die Ziffer
    mitte = (gruppe.min() + gruppe.max()) / 2
    assert abs(mitte - conf["text_x"]) < 12, mitte


def test_emoji_ohne_png_bricht_ab_statt_kaestchen_zu_rendern(tmp_path):
    """😭 steht in den Referenzen, ein PNG dafuer gibt es nicht."""
    from videoclipper import liste
    t = layout.template("TOP5_HALLOFCLIPS")
    with pytest.raises(ValueError, match="Kein Emoji-PNG"):
        liste.baue_zustand({5: "Holy stutter 😭"}, t, tmp_path / "l.png")


def test_liste_ohne_emoji_bleibt_wo_sie_war(tmp_path):
    """TOP5_COUNTDOWN hat keine Emojis — die Gruppenmitte darf dort nichts verschieben."""
    from videoclipper import liste
    t = layout.template("TOP5_COUNTDOWN")
    conf = t["liste"]
    pfad = liste.baue_zustand({5: "Platz fuenf"}, t, tmp_path / "l.png")
    y5 = conf["erste_zeile_y"] + 4 * conf["zeilenabstand"]
    xs = _alpha_spalten(pfad, y5)
    text = xs[xs > conf["ziffer_x"] + 60]
    assert abs((text.min() + text.max()) / 2 - conf["text_x"]) < 3


def test_hallofclips_bleibt_ueber_der_ui_zone():
    """Seit dem Umbau am 2026-10-20 endet das Videofeld bei 1438, nicht 1808.

    Die Referenzen liefen bewusst bis in TikToks UI-Zone hinein, und der
    Hinweis dazu war gewollt. Mit dem groesseren, aber flacheren Feld (volle
    Breite statt quadratisch) ist der Konflikt von selbst weg — das ist eine
    Folge des Umbaus, kein eigenes Ziel.
    """
    tmpl = layout.template("TOP5_HALLOFCLIPS")
    x, y, b, h = tmpl["panels"][0]["ziel"]
    assert y + h <= tmpl["canvas"][1] - tmpl["sicherheitszone"]["unten"]
    assert countdown.sicherheitszone_pruefen(tmpl) == []


def test_hallofclips_zeigt_mehr_bild_als_die_referenzvermessung():
    """"Das eigentliche Video muss viel groesser sein" (Nutzer, 2026-10-20).

    Gemessen in Bildflaeche, nicht in Feldflaeche: Eine 16:9-Quelle steht im
    alten quadratischen Feld 908x908 nur als 908x511. Das neue Feld ist exakt
    so hoch wie das Bild, es geht also nichts an Blur verloren.
    """
    b, h = layout.template("TOP5_HALLOFCLIPS")["panels"][0]["ziel"][2:]
    alt = 908 * round(908 * 9 / 16)          # Bild im alten quadratischen Feld
    assert b / h == pytest.approx(16 / 9, abs=0.01)
    assert b * h > alt * 1.4


# --- Bildgenaue Segmentgrenzen (2026-09-17) --------------------------------

def test_segmentgrenzen_liegen_auf_ganzen_ausgabebildern(tmpl):
    """Mit Dauern auf halben Bildern schaltete die Liste vor dem Schnitt um.

    Gemessen an knossi_top5: Platz 1 stand 50 ms vor dem Bildwechsel in der
    Liste, weil sich der Rest jeder Segmentdauer ueber vier Grenzen aufsummierte.
    """
    eintraege = [{"platz": p, "text": f"P{p}", "video_id": f"v{p}", "start": 0.117,
                  "dauer": d} for p, d in zip(range(5, 0, -1),
                                              (12.083, 14.433, 6.817, 10.117, 13.383))]
    plan = countdown.CountdownPlan.model_validate(
        {"clip_id": "t", "titel": "Titel", "eintraege": eintraege,
         "upload": {"tiktok": "TikTok", "youtube": "Shorts"}})
    r = countdown.loese_auf(plan, tmpl).aufgeloest
    bild = 0
    for s in r.segmente:
        assert s["ab"] == pytest.approx(bild / r.fps, abs=1e-3)
        assert s["bilder"] <= s["dauer"] * r.fps + 1e-6
        bild += s["bilder"]
    assert r.dauer == pytest.approx(bild / r.fps, abs=1e-3)


def test_renderer_schneidet_jedes_segment_auf_seine_bildzahl(tmpl):
    from videoclipper import render
    plan = countdown.loese_auf(_plan(), tmpl)
    graph = render.filtergraph_countdown(plan, tmpl, -14.0)
    for s in plan.aufgeloest.segmente:
        assert f"trim=end_frame={s['bilder']}" in graph
        assert f"atrim=end={s['bilder'] / plan.aufgeloest.fps:.6f}" in graph
