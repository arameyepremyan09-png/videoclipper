"""Tests fuer die Rechenteile des Bewertungssystems.

Bewusst nur die Stellen, die still falsch sein koennen: Eine Rangliste sieht
auch dann plausibel aus, wenn die Glaettung nicht greift oder Gewichte bei
fehlenden Metriken falsch umverteilt werden. Genau dieser Fehler ist am
2026-09-05 im ersten Lauf aufgetreten — ein Post mit vier Views stand auf
Platz 1 von 10.
"""

from __future__ import annotations

import pytest

from videoclipper import experiments, publish, scoring, store


@pytest.fixture(autouse=True)
def eigene_ablage(tmp_path, monkeypatch):
    """Jeder Test bekommt eine leere Ablage — nie die echten Daten anfassen."""
    monkeypatch.setattr(store, "ABLAGE", tmp_path / "performance")


# --- Glaettung -------------------------------------------------------------

def test_kleine_fallzahl_wird_zum_erwartungswert_gezogen():
    """1 Like auf 4 Views sind roh 25 % — das Fuenffache eines sehr guten Werts."""
    roh = scoring.raten({"views": 4, "likes": 1}, 73.0, "youtube",
                        geglaettet=False)["like_rate"]
    glatt = scoring.raten({"views": 4, "likes": 1}, 73.0, "youtube")["like_rate"]
    mittel = scoring.konfiguration()["benchmarks"]["youtube"]["like_rate"]["mittel"]
    assert roh == pytest.approx(0.25)
    assert abs(glatt - mittel) < abs(roh - mittel)
    assert glatt < 0.06


def test_grosse_fallzahl_bleibt_bei_der_messung():
    roh = scoring.raten({"views": 1021, "likes": 68}, 27.0, "tiktok",
                        geglaettet=False)["like_rate"]
    glatt = scoring.raten({"views": 1021, "likes": 68}, 27.0, "tiktok")["like_rate"]
    assert abs(glatt - roh) < 0.005


def test_glaettung_dreht_die_reihenfolge_nicht_um():
    """Ein Post mit vier Views darf einen mit tausend nicht ueberholen."""
    wenig = scoring.bewerte({"views": 4, "likes": 1}, "youtube", 73.0, 38)
    viel = scoring.bewerte({"views": 1021, "likes": 68}, "tiktok", 27.0, 907)
    assert not wenig.belastbar
    assert not wenig.genug_views and viel.genug_views


# --- Score ------------------------------------------------------------------

def test_fehlende_metrik_ist_nicht_null():
    """Ohne Creator-Center-Daten darf der Clip nicht bestraft werden."""
    ohne = scoring.bewerte({"views": 1000, "likes": 50}, "tiktok", 30.0, 1000)
    mit = scoring.bewerte({"views": 1000, "likes": 50, "completion_rate": 0.45,
                           "avg_watchtime": 13.5}, "tiktok", 30.0, 1000)
    assert "retention" in ohne.fehlend
    assert ohne.abdeckung < mit.abdeckung
    # Gleiche Likes, gleiche Views: Der Score darf nicht allein daran haengen,
    # dass eine Achse gemessen wurde.
    assert ohne.score > 0


def test_null_views_ergibt_keine_rate():
    r = scoring.raten({"views": 0, "likes": 0}, 30.0, "tiktok")
    assert r["like_rate"] is None, "0 Views heisst unbekannt, nicht 0 %"


def test_abdeckung_summiert_nur_vorhandene_achsen():
    b = scoring.bewerte({"views": 1000, "likes": 50}, "tiktok", 30.0, None)
    gew = scoring.konfiguration()["performance"]["achsen"]
    assert b.abdeckung == pytest.approx(gew["engagement"])


# --- Messfenster ------------------------------------------------------------

def test_fenster_nimmt_den_naechsten_schnappschuss():
    store.speichere_post({"post_id": "t_1", "plattform": "tiktok",
                          "veroeffentlicht": "2026-09-04T18:00:00+02:00"})
    for alter, views in ((1.0, 100), (24.0, 900), (168.0, 1200)):
        store.speichere_messung({"post_id": "t_1", "alter_stunden": alter,
                                 "views": views})
    t = store.messung_im_fenster("t_1", 24)
    assert t.messung["views"] == 900
    assert t.brauchbar


def test_zu_weit_entfernte_messung_gilt_nicht():
    store.speichere_post({"post_id": "t_2", "plattform": "tiktok"})
    store.speichere_messung({"post_id": "t_2", "alter_stunden": 2.0, "views": 50})
    t = store.messung_im_fenster("t_2", 24)
    assert not t.brauchbar, "2 h duerfen nicht als 24-h-Wert durchgehen"


# --- A/B --------------------------------------------------------------------

def test_zuweisung_bleibt_balanciert():
    experiments.anlegen("e1", "dauer", "h", {"kurz": "a", "lang": "b"})
    for i in range(10):
        publish.registriere("tiktok", f"https://www.tiktok.com/@x/video/{i}",
                            experiment="e1")
    zaehler = {"kurz": 0, "lang": 0}
    for p in store.posts():
        zaehler[p["variante"]] += 1
    assert zaehler["kurz"] == zaehler["lang"] == 5


def test_p_bester_ist_deterministisch_und_summiert_zu_eins():
    a = experiments.Arm("A", views=3000, ereignisse=200)
    b = experiments.Arm("B", views=2700, ereignisse=33)
    w1 = experiments._p_bester([a, b], 20000, 42)
    w2 = experiments._p_bester([a, b], 20000, 42)
    assert w1 == w2
    assert sum(w1.values()) == pytest.approx(1.0)
    assert w1["A"] > 0.99


def test_zu_wenige_posts_pro_arm_entscheiden_nicht():
    experiments.anlegen("e2", "hook", "h", {"A": "x", "B": "y"},
                        metrik="like_rate")
    for name, likes in (("A", 90), ("B", 5)):
        publish.registriere("tiktok", f"https://www.tiktok.com/@x/video/9{name}",
                            experiment="e2", variante=name,
                            veroeffentlicht="2026-09-01T18:00:00+02:00")
        store.speichere_messung({"post_id": f"tiktok_9{name}", "alter_stunden": 24,
                                 "views": 1000, "likes": likes})
    erg = experiments.werte_aus("e2")
    assert erg.wahrscheinlichkeit["A"] > 0.99
    assert not erg.entscheidbar, "1 Post pro Arm darf nie entscheiden"
    assert erg.benoetigte_views_pro_arm is not None


def test_eine_variable_pro_experiment():
    with pytest.raises(ValueError, match="Unbekannte Variable"):
        experiments.anlegen("e3", "hook_und_laenge", "h", {"A": "x", "B": "y"})
