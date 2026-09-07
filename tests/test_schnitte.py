"""Tests fuer die Schnitterkennung.

Getestet wird die Rechenlogik, nicht die Bilderkennung: ``finde`` braucht ein
Video und laeuft deshalb nicht im Test. Was hier falsch sein kann, ist die
Frage "liegt dieser Schnitt im Clip oder auf seiner Grenze" — und genau die
entscheidet, ob ein Clip mitten im Satz springt.
"""

from __future__ import annotations

from videoclipper import schnitte


# --- pruefe: drinnen, draussen, auf der Grenze -----------------------------

def test_schnitt_mitten_im_clip_wird_gemeldet():
    assert schnitte.pruefe(100.0, 130.0, [115.0]) == [115.0]


def test_schnitt_ausserhalb_wird_nicht_gemeldet():
    assert schnitte.pruefe(100.0, 130.0, [80.0, 200.0]) == []


def test_schnitt_auf_der_clipgrenze_ist_kein_sprung():
    """Genau dort SOLL eine Grenze liegen — ein Partnerwechsel ist der
    natuerliche Anfang und das natuerliche Ende eines Clips."""
    assert schnitte.pruefe(100.0, 130.0, [100.0, 130.0]) == []


def test_rand_haelt_knappe_grenzfaelle_draussen():
    """Der Nachlauf aus ``snappe`` schiebt das Ende um 0.35 s nach hinten.
    Ein Schnitt, der dadurch gerade eben hineinrutscht, ist keine Meldung wert."""
    assert schnitte.pruefe(100.0, 130.0, [100.2, 129.8]) == []
    assert schnitte.pruefe(100.0, 130.0, [100.2], rand=0.0) == [100.2]


def test_mehrere_schnitte_bleiben_sortiert():
    drin = schnitte.pruefe(0.0, 100.0, [10.0, 50.0, 90.0, 200.0])
    assert drin == [10.0, 50.0, 90.0]


# --- melde: Text nur, wenn wirklich etwas dazwischenliegt ------------------

def test_saubere_grenzen_melden_nichts():
    assert schnitte.melde("c_001", 100.0, 130.0, [99.0, 131.0]) == []


def test_meldung_nennt_clip_und_zeitpunkt():
    (text,) = schnitte.melde("c_001", 100.0, 130.0, [115.0])
    assert "c_001" in text
    assert "115.00s" in text


def test_lange_liste_wird_gekuerzt():
    """Bei Handkamera koennen es viele werden; die Meldung bleibt lesbar."""
    (text,) = schnitte.melde("c_001", 0.0, 100.0, [float(i) for i in range(10, 60, 5)])
    assert text.count("s,") <= 6
    assert "+4 weitere" in text
