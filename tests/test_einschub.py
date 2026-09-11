"""Tests fuer Einschuebe — ein Clip ueber eine kurze Strecke eines anderen Modus.

Geprueft wird, was im fertigen Clip niemand mehr nachmessen kann: ob das
Ersatzpanel auf das Bild genau kommt und geht, woher das gehaltene Bild stammt
und ob der Filtergraph seine Eingaenge richtig zaehlt. Ein Frame daneben ist im
QC unsichtbar — Dauer, Aufloesung und Tonspur stimmen —, im Feed aber ein
Blitz aus dem falschen Bildausschnitt.
"""

from __future__ import annotations

import numpy as np
import pytest

from videoclipper import layout
from videoclipper.editplan import Aufgeloest, EditPlan
from videoclipper.render import filtergraph

FPS = 60000 / 1001


@pytest.fixture
def prof():
    return layout.profil("COACHLIM_KAESE_SNAP")


@pytest.fixture
def tmpl():
    return layout.template("PHONE_STACK")


def _achse(sek: float) -> np.ndarray:
    """Bildzeitstempel wie von ``signals.modus_je_bild``: 59.94 fps ab 0."""
    return np.arange(int(sek * FPS)) / FPS


def _eigen(z: np.ndarray, *fremd: tuple[float, float]) -> np.ndarray:
    m = np.ones(len(z), dtype=bool)
    for a, b in fremd:
        m[(z >= a) & (z < b)] = False
    return m


def _schiebe(prof, tmpl, z, eigen, dauer):
    return layout.einschuebe(prof, tmpl, "PHONE", "FULLCAM", z, eigen, dauer)


def test_ohne_fremde_bilder_kein_einschub(prof, tmpl):
    z = _achse(20.0)
    assert _schiebe(prof, tmpl, z, np.ones(len(z), dtype=bool), 20.0) == []


def test_fenster_sitzt_auf_das_bild_genau(prof, tmpl):
    """Das Fenster muss das erste fremde Bild enthalten und das erste eigene
    danach ausschliessen — ``between`` schliesst beide Raender ein."""
    z = _achse(30.0)
    e = _schiebe(prof, tmpl, z, _eigen(z, (10.0, 15.0)), 30.0)
    assert len(e) == 1
    erstes, davor = z[z >= 10.0][0], z[z < 10.0][-1]
    letztes, zurueck = z[z < 15.0][-1], z[z >= 15.0][0]
    assert davor < e[0]["ab"] <= erstes
    assert letztes <= e[0]["bis"] < zurueck


def test_facecam_kommt_aus_der_vollbild_cam_der_chat_haelt(prof, tmpl):
    z = _achse(30.0)
    e = _schiebe(prof, tmpl, z, _eigen(z, (10.0, 15.0)), 30.0)[0]
    assert [p["name"] for p in e["ersatz"]] == ["facecam"]
    assert e["ersatz"][0]["src"] == [0, 0, 1920, 1080]
    assert e["ersatz"][0]["dst"] == [0, 0, 1080, 606]      # dieselbe Stelle wie live
    assert [p["name"] for p in e["halten"]] == ["handy"]


def test_haltebild_liegt_mit_abstand_vor_dem_wechsel(prof, tmpl):
    """Nicht das letzte Bild vor dem Wechsel: Eine Rundung beim Herausholen
    gaebe sonst ein Bild aus der Vollbild-Cam statt des Chats."""
    z = _achse(30.0)
    e = _schiebe(prof, tmpl, z, _eigen(z, (10.0, 15.0)), 30.0)[0]
    erstes = z[z >= 10.0][0]
    assert erstes - 4 / FPS < e["halten_bei"] < erstes - 2 / FPS


def test_einschub_am_clipanfang_haelt_das_bild_danach(prof, tmpl):
    z = _achse(30.0)
    e = _schiebe(prof, tmpl, z, _eigen(z, (0.0, 3.0)), 30.0)[0]
    assert e["halten_bei"] > 3.0
    assert e["ab"] < 0.0


def test_einschub_am_clipende_bleibt_offen(prof, tmpl):
    """Sonst legte die Rundung am letzten Frame das falsche Panel frei."""
    z = _achse(30.0)
    e = _schiebe(prof, tmpl, z, _eigen(z, (26.0, 31.0)), 30.0)[0]
    assert e["bis"] > 30.0


def test_zu_langer_einschub_bricht_ab(prof, tmpl):
    z = _achse(40.0)
    with pytest.raises(ValueError, match="hoechstens"):
        _schiebe(prof, tmpl, z, _eigen(z, (5.0, 20.0)), 40.0)


def test_einzelnes_fremdes_bild_ist_rauschen(prof, tmpl):
    z = _achse(20.0)
    m = np.ones(len(z), dtype=bool)
    m[600] = False
    assert _schiebe(prof, tmpl, z, m, 20.0) == []


def test_profil_ohne_einschub_bricht_ab(tmpl):
    """COACHLIM_HANDYS nennt keine Ersatzzone — dort bleibt es beim alten
    Verbot: keine Clipgrenze ueber einen Moduswechsel hinweg."""
    prof = layout.profil("COACHLIM_HANDYS")
    z = _achse(20.0)
    with pytest.raises(ValueError, match="keinen Einschub"):
        layout.einschuebe(prof, tmpl, "PHONE", "SOLO", z, _eigen(z, (5.0, 8.0)), 20.0)


def _plan(prof, tmpl, einschuebe) -> EditPlan:
    plan = EditPlan.model_validate({
        "clip_id": "t_001",
        "quelle": {"video_id": "t", "kanal": "k", "orig_start": 100.0},
        "tier": "B", "profil": prof["name"], "template": tmpl["name"],
        "template_grund": "Test", "timing": {"start": 100.0, "ende": 130.0},
        "headline": "TEST HEADLINE",
        "score": {"overall": 0.5, "reaktion": 0.5, "klarheit": 0.5, "payoff": 0.5},
        "grund": "Test"})
    plan.resolved = Aufgeloest(
        start=100.0, ende=130.0, dauer=30.0, modus="PHONE", modus_anteil=0.8,
        panels=layout.panels(prof, tmpl, "PHONE"), canvas=(1080, 1920), fps=30,
        headline_y=606, untertitel=[{"text": "HALLO", "ab": 1.0, "bis": 2.0}],
        follow=None, einschuebe=einschuebe)
    return plan


def test_filtergraph_zaehlt_die_eingaenge_richtig(prof, tmpl):
    """Zwei Haltebilder schieben alle PNGs um zwei Eingaenge nach hinten."""
    z = _achse(30.0)
    e = _schiebe(prof, tmpl, z, _eigen(z, (5.0, 8.0), (20.0, 24.0)), 30.0)
    g = filtergraph(_plan(prof, tmpl, e), tmpl)
    assert "[1:v]crop=486:694:800:386" in g and "[2:v]crop=486:694:800:386" in g
    assert "[3:v]overlay" in g                     # Headline
    assert "[4:v]overlay" in g                     # der eine Untertitel
    assert "[5:v]" not in g


def test_vollbild_cam_laeuft_einmal_fuer_alle_einschuebe(prof, tmpl):
    """Eine Kette je Einschub hiesse eine Skalierung mit Blur je Einschub ueber
    alle Bilder des Clips."""
    z = _achse(30.0)
    e = _schiebe(prof, tmpl, z, _eigen(z, (5.0, 8.0), (20.0, 24.0)), 30.0)
    g = filtergraph(_plan(prof, tmpl, e), tmpl)
    # Einpassen braucht die Zone zweimal (Blur hinten, Bild vorn) — in EINER Kette.
    assert g.count("[0:v]crop=1920:1080:0:0") == 2


def test_ohne_einschub_bleibt_der_graph_wie_bisher(prof, tmpl):
    g = filtergraph(_plan(prof, tmpl, []), tmpl)
    assert "[1:v]overlay" in g and "crop=1920:1080" not in g
