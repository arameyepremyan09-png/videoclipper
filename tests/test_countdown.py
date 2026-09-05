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
    daten = {"clip_id": "t", "titel": "Titel", "eintraege": eintraege}
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
            "eintraege": [
                {"platz": 1, "text": "a", "video_id": "v", "start": 0, "dauer": 1},
                {"platz": 3, "text": "b", "video_id": "v", "start": 0, "dauer": 1},
            ]})


def test_falsche_anzahl_plaetze_wird_abgewiesen(tmpl):
    plan = countdown.CountdownPlan.model_validate({
        "clip_id": "t", "titel": "Titel",
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
