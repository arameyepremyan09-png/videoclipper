"""Tests fuer Stage 08 — Grenzen an Wort, Bild und Ton.

``snappe`` haengt an die Wortgrenzen Vor- und Nachlauf an. Geprueft wird hier,
dass diese Zugabe nie in einen Bilduebergang laeuft und keine Stille hinter
dem letzten Wort mitnimmt. Beides hat im QC die richtige Dauer, die richtige
Aufloesung und eine Tonspur — auffallen wuerde es erst im Feed, und dort im
ersten Bild oder in der letzten Sekunde.
"""

from __future__ import annotations

import numpy as np
import pytest

from videoclipper import schnitte
from videoclipper.snapping import snappe
from videoclipper.transcript import Transkript, Wort


def _rede(ab: float, n: int = 150, schritt: float = 0.3) -> Transkript:
    """Durchgehende Rede ab ``ab``: n Woerter zu je ``schritt`` Sekunden."""
    return Transkript("t", "de", tuple(
        Wort(f"w{i}", round(ab + i * schritt, 3), round(ab + (i + 1) * schritt, 3))
        for i in range(n)))


def _satz_und_pause(ab: float, bis: float, weiter: float) -> Transkript:
    """Rede von ``ab`` bis ``bis``, dann Pause, ab ``weiter`` geht es weiter.

    Nur so bekommt das letzte Wort den vollen Nachlauf — bei durchgehender
    Rede endet er vor dem naechsten Wort.
    """
    n = int(round((bis - ab) / 0.3))
    vorn = [Wort(f"w{i}", round(ab + i * 0.3, 3), round(ab + (i + 1) * 0.3, 3))
            for i in range(n)]
    hinten = [Wort(f"n{i}", round(weiter + i * 0.3, 3), round(weiter + (i + 1) * 0.3, 3))
              for i in range(20)]
    return Transkript("t", "de", tuple(vorn + hinten))


# --- snappe: ohne Zusaetze wie bisher ----------------------------------------

def test_ohne_zusaetze_aendert_sich_nichts():
    tr = _rede(15.72)
    assert snappe(tr, 15.72, 40.0) == snappe(tr, 15.72, 40.0, sperren=[], pegel=None)
    s, _, _ = snappe(tr, 15.72, 40.0)
    assert s == pytest.approx(15.52)


# --- snappe: Bilduebergaenge am Anfang ---------------------------------------

def test_vorlauf_zeigt_kein_bild_vor_dem_harten_schnitt():
    """GEMESSEN an saiJDq9DM_Y: Das Intro endet mit hartem Schnitt bei
    15.683 s, das erste Wort beginnt 0.04 s danach. 0.20 s Vorlauf zeigten
    zehn Bilder Intro, bevor der Clip anfing."""
    s, _, _ = snappe(_rede(15.72), 15.72, 40.0, sperren=[(15.683, 15.683)])
    assert s == pytest.approx(15.683)


def test_anfang_springt_aus_der_ueberblendung():
    """Zweiter Fall aus demselben Video: Browser -> Cam in 0.3 s, das erste
    Wort 0.11 s nach dem Ende der Blende."""
    s, _, _ = snappe(_rede(249.16), 249.16, 280.0, sperren=[(248.45, 249.05)])
    assert s == pytest.approx(249.05)


# --- snappe: Bilduebergaenge am Ende -----------------------------------------

def test_nachlauf_endet_vor_der_ueberblendung():
    tr = _satz_und_pause(100.0, 130.0, weiter=131.0)
    _, e, _ = snappe(tr, 100.0, 130.0)
    assert e == pytest.approx(130.35)
    _, e, _ = snappe(tr, 100.0, 130.0, sperren=[(130.2, 130.5)])
    assert e == pytest.approx(130.2)


def test_uebergang_mitten_im_clip_bleibt_unberuehrt():
    """Den meldet ``schnitte.melde``; ob der Clip dort springen darf,
    entscheidet die Selektion."""
    tr = _rede(100.0)
    assert snappe(tr, 100.0, 130.0, sperren=[(115.0, 115.3)]) == \
        snappe(tr, 100.0, 130.0)


def test_sperre_zerdrueckt_den_clip_nicht():
    s, e, _ = snappe(_rede(100.0), 100.0, 108.0, sperren=[(99.0, 106.0)])
    assert e - s >= 5.0


# --- snappe: das echte Ende des letzten Wortes -------------------------------

def _pegel(stille: tuple[float, float] | None = None,
           luecke: float | None = None) -> tuple[np.ndarray, np.ndarray]:
    """Durchgehend Sprache bei -25 dBFS in 50-ms-Fenstern, wahlweise mit Pause."""
    zeiten = np.arange(0.0, 600.0, 0.05)
    db = np.full(len(zeiten), -25.0)
    if stille:
        db[(zeiten >= stille[0] - 1e-9) & (zeiten < stille[1] - 1e-9)] = -80.0
    if luecke is not None:
        db[np.argmin(np.abs(zeiten - luecke))] = -53.0
    return zeiten, db


def _angreifen(letztes: str = "angreifen.") -> Transkript:
    """Nachgebaut aus saiJDq9DM_Y: Das letzte Wort steht bis 543.12 im
    Transkript, gesprochen ist es um 541.0 zu Ende."""
    woerter = [Wort(f"w{i}", round(520.0 + i * 0.3, 3), round(520.3 + i * 0.3, 3))
               for i in range(69)]                                   # bis 540.7
    woerter.append(Wort(letztes, 540.7, 543.12))
    woerter += [Wort(f"n{i}", round(543.12 + i * 0.3, 3), round(543.42 + i * 0.3, 3))
                for i in range(20)]
    return Transkript("t", "de", tuple(woerter))


def test_ende_nimmt_keine_stille_mit():
    tr = _angreifen()
    _, ohne_ton, _ = snappe(tr, 520.0, 542.5)
    assert ohne_ton > 543.0                    # ueber 2 s Stille im Clip
    _, e, _ = snappe(tr, 520.0, 542.5, pegel=_pegel(stille=(541.0, 543.12)))
    assert e == pytest.approx(541.15)


def test_durchgehende_rede_wird_nicht_gekuerzt():
    tr = _angreifen()
    assert snappe(tr, 520.0, 542.5, pegel=_pegel()) == snappe(tr, 520.0, 542.5)


def test_silbenluecke_ist_keine_pause():
    """Ein einzelnes leises Fenster mitten im Wort beendet es nicht."""
    tr = _angreifen()
    assert snappe(tr, 520.0, 542.5, pegel=_pegel(luecke=540.85)) == \
        snappe(tr, 520.0, 542.5)


def test_lachen_am_ende_wird_nicht_gekuerzt():
    """Endet der Clip auf einem Marker, ist die 'Stille' dort das Lachen."""
    tr = _angreifen(letztes="[gelächter]")
    assert snappe(tr, 520.0, 542.5, pegel=_pegel(stille=(541.0, 543.12))) == \
        snappe(tr, 520.0, 542.5)


# --- schnitte._spanne: bildgenau aus Bildabstaenden --------------------------

def _abstaende(n: int = 120, ruhe: float = 0.2) -> tuple[np.ndarray, np.ndarray]:
    """n Bilder bei 60 fps, ruhiges Bild."""
    return np.arange(n) / 60.0, np.full(n, ruhe)


def test_harter_schnitt_ist_ein_einziges_bild():
    zeiten, abstand = _abstaende()
    abstand[41] = 40.0
    a, b = schnitte._spanne(zeiten, abstand, 0.5, 1.0)
    assert a == b == round(41 / 60, 3)


def test_ueberblendung_reicht_vom_ersten_bis_zum_letzten_bild():
    zeiten, abstand = _abstaende()
    abstand[33:51] = 5.0          # 0.3 s Blende wie bei saiJDq9DM_Y
    assert schnitte._spanne(zeiten, abstand, 0.4, 1.0) == (
        round(33 / 60, 3), round(50 / 60, 3))


def test_bewegung_ausserhalb_des_fensters_zaehlt_nicht():
    zeiten, abstand = _abstaende()
    abstand[5] = 40.0
    abstand[60] = 30.0
    assert schnitte._spanne(zeiten, abstand, 0.8, 1.2) == (1.0, 1.0)


def test_ruhiges_fenster_hat_keinen_uebergang():
    zeiten, abstand = _abstaende()
    assert schnitte._spanne(zeiten, abstand, 0.2, 1.8) is None
