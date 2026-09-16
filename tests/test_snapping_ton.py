"""Tests fuer Stage 08 — Anfang und Ende am Ton statt am Transkript.

GEMESSEN an jd9bSJ7mshM (1:1 Kaese): An den Raendern eines json3-Ereignisses
liegen die Wortzeiten bis zu 1 s neben dem Ton. Drei Folgen, alle im QC
unsichtbar, weil Dauer, Aufloesung und Tonspur stimmen:

* der Clip begann mitten im ersten Satz,
* er endete vor dem Lacher, der die Pointe traegt,
* oder er nahm die erste Silbe des naechsten Satzes mit.

Welche Luecke hinter dem letzten Wort das Ende ist, weiss der Pegel allein
nicht. Das weiss die Selektion: Liegt ihr ``ende`` in einer Luecke, wird dort
geschnitten; liegt es im Ton, gilt die Regel aus ``test_snapping.py``. Die
Faelle von dort (stummgeschaltete Stille hinter dem letzten Wort) muessen
unveraendert gruen bleiben.
"""

from __future__ import annotations

import numpy as np
import pytest

from videoclipper.snapping import snappe
from videoclipper.transcript import Transkript, Wort


def _pegel(*abschnitte: tuple[float, float, float],
           grund: float = -25.0) -> tuple[np.ndarray, np.ndarray]:
    """50-ms-Pegel ueber 0..1200 s: ``grund`` ueberall, dazu (von, bis, dB)."""
    zeiten = np.arange(0.0, 1200.0, 0.05)
    db = np.full(len(zeiten), grund)
    for von, bis, wert in abschnitte:
        db[(zeiten >= von - 1e-9) & (zeiten < bis - 1e-9)] = wert
    return zeiten, db


def _rede(ab: float, bis: float, schritt: float = 0.25,
          name: str = "w") -> list[tuple[str, float, float]]:
    n = int(round((bis - ab) / schritt))
    return [(f"{name}{i}", round(ab + i * schritt, 3), round(ab + (i + 1) * schritt, 3))
            for i in range(n)]


def _tr(*folge: tuple[str, float, float]) -> Transkript:
    return Transkript("t", "de", tuple(Wort(t, a, b) for t, a, b in folge))


# --- Ende in einer Pause: der Lacher gehoert dazu ----------------------------

def _was_und_lacher() -> tuple[Transkript, tuple[np.ndarray, np.ndarray]]:
    """GEMESSEN bei 731-736 s: "Was?", 0.7 s Stille, 1.9 s Gelaechter,
    0.4 s Stille, dann der naechste Satz."""
    tr = _tr(*_rede(700.0, 732.0), ("Was?", 732.04, 735.04),
             *_rede(735.56, 745.0, name="n"))
    pegel = _pegel((732.35, 733.1, -80.0), (733.1, 735.1, -18.0),
                   (735.1, 735.5, -80.0))
    return tr, pegel


def test_lacher_nach_kurzer_pause_gehoert_zum_clip():
    """Die Selektion legt das Ende hinter den Lacher. Die erste Stille nach
    dem letzten Wort ist dann nicht das Ende — das Gelaechter ist die
    Reaktion auf die Pointe."""
    tr, pegel = _was_und_lacher()
    _, e, _ = snappe(tr, 700.0, 735.3, pegel=pegel)
    assert e == pytest.approx(735.25)


def test_ende_hinter_einem_lacher_marker_liegt_in_der_senke():
    """GEMESSEN an 8haLC71kEDg: [gelaechter] 3303.86-3304.56, direkt dahinter
    "Richtig", dazwischen eine Senke bei 3304.30. Das naechste Wortende zum
    gewuenschten Ende 3304.3 war das des Markers; ohne Messung endete der
    Teaser bei 3304.91, mitten in "Richtig"."""
    tr = _tr(*_rede(700.0, 720.0), ("Bruder.", 720.0, 720.4),
             ("[gelächter]", 720.4, 721.1), ("Richtig", 721.1, 721.6))
    pegel = _pegel((720.4, 720.85, -12.0), (720.85, 721.0, -40.0),
                   (721.0, 721.6, -12.0))
    _, ohne, _ = snappe(tr, 700.0, 720.9)
    assert ohne == pytest.approx(721.45)            # "Richtig" im Clip
    _, e, _ = snappe(tr, 700.0, 720.9, pegel=pegel)
    assert 720.85 <= e < 721.05


def test_stille_hinter_einem_schrei_marker_ist_das_ende():
    """GEMESSEN an I-mbVr4qgFs: [schreien] steht bis 139.56 im Transkript,
    geschrien ist bis 139.05, danach 0.5 s Stille bis "Warum". Die Stille
    beginnt 0.51 s vor dem Markerende; mit der alten Schranke von 0.5 s galt
    sie nicht, und der Clip endete bei 139.91 in "Warum macht"."""
    tr = _tr(*_rede(100.0, 137.5), ("[schreien]", 137.55, 139.56),
             ("Warum", 139.56, 139.84), ("macht", 139.84, 140.04))
    pegel = _pegel((137.1, 139.05, -17.0), (139.05, 139.55, -62.0),
                   (139.55, 140.1, -18.0))
    _, e, _ = snappe(tr, 100.0, 139.3, pegel=pegel)
    assert e == pytest.approx(139.2)


def test_ende_im_ton_schneidet_an_der_ersten_pause():
    """Liegt das gewuenschte Ende mitten im Lacher, ist keine Luecke gemeint —
    dann gilt die Regel aus saiJDq9DM_Y: erste Pause nach dem letzten Wort."""
    tr, pegel = _was_und_lacher()
    _, e, _ = snappe(tr, 700.0, 734.5, pegel=pegel)
    assert e == pytest.approx(732.5)


def test_stille_bis_ans_ende_schneidet_wie_bisher():
    """Der Fall aus saiJDq9DM_Y mit dem Ende in der Stille selbst."""
    tr = _tr(*_rede(500.0, 540.0), ("angreifen.", 540.7, 543.12),
             *_rede(545.0, 550.0, name="n"))
    _, e, _ = snappe(tr, 500.0, 542.5, pegel=_pegel((541.0, 545.0, -80.0)))
    assert e == pytest.approx(541.15)


# --- Ende in einem Tal: ohne Pause nicht ins naechste Wort -------------------

def test_ohne_pause_endet_der_clip_im_tal_vor_dem_naechsten_wort():
    """GEMESSEN bei 361-363.5 s: "gute." geht ohne Pause in "Wir bauen" ueber,
    der Nachlauf von 0.35 s nahm "Wir" mit. Dazwischen faellt der Pegel fuer
    0.1 s auf -45 — keine Stille, aber ein Tal."""
    tr = _tr(*_rede(330.0, 361.25), ("gute.", 361.32, 363.04),
             ("Wir", 363.04, 363.16), ("bauen", 363.16, 363.36),
             *_rede(363.36, 370.0, name="n"))
    pegel = _pegel((362.85, 362.95, -45.0), grund=-20.0)
    _, ohne, _ = snappe(tr, 330.0, 362.9)
    assert ohne == pytest.approx(363.39)            # "Wir" im Clip
    _, e, _ = snappe(tr, 330.0, 362.9, pegel=pegel)
    assert 362.85 <= e <= 362.95


def test_grundpegel_hinter_dem_lacher_ist_ein_tal():
    """GEMESSEN bei 83.6-84.9 s: Lacher bei -9..-22 dB, danach nur noch der
    Grundpegel der Musik (-33), dann der naechste Satz (-25). Gegen den
    Median waere das kein Tal, gegen das laute Viertel schon."""
    tr = _tr(*_rede(52.5, 81.75), ("Teilzeit.", 81.76, 84.88),
             *_rede(84.88, 95.0, name="n"))
    pegel = _pegel((82.15, 83.65, -85.0), (83.65, 84.3, -11.0),
                   (84.3, 84.8, -33.0), grund=-25.0)
    _, e, _ = snappe(tr, 52.5, 84.5, pegel=pegel)
    assert 84.3 <= e <= 84.8


def test_gleichmaessige_rede_hat_kein_tal():
    tr = _tr(*_rede(330.0, 361.25), ("gute.", 361.32, 363.04),
             *_rede(363.04, 370.0, name="n"))
    assert snappe(tr, 330.0, 362.9, pegel=_pegel(grund=-20.0)) == \
        snappe(tr, 330.0, 362.9)


# --- Einsatz: der Anfang beim Ton ---------------------------------------------

def test_anfang_setzt_beim_ton_ein_nicht_beim_transkript():
    """GEMESSEN bei 287-288 s: "Wir rudern zurueck" setzt bei 287.35 ein, das
    Transkript beginnt das Ereignis erst bei 288.0. 0.20 s Vorlauf begannen
    mitten im Satz."""
    tr = _tr(("Heiss", 285.08, 288.0), *_rede(288.0, 320.0))
    s, _, _ = snappe(tr, 288.0, 318.0, pegel=_pegel((287.15, 287.3, -80.0)))
    assert s == pytest.approx(287.25)


def test_anfang_ohne_stille_behaelt_den_vorlauf():
    tr = _tr(*_rede(250.0, 320.0))
    assert snappe(tr, 288.1, 318.0, pegel=_pegel())[0] == \
        snappe(tr, 288.1, 318.0)[0]


def test_pause_nach_dem_ersten_wort_verschiebt_den_anfang_nicht():
    """Liegt die erste Stille HINTER dem Wortanfang, ist sie die Pause nach dem
    ersten Wort — der Clip begaenne sonst hinter ihm."""
    tr = _tr(*_rede(250.0, 288.0, schritt=0.3), ("Hallo.", 288.0, 288.4),
             *_rede(288.8, 320.0, name="n"))
    s, _, _ = snappe(tr, 288.0, 318.0, pegel=_pegel((288.45, 288.8, -80.0)))
    assert s == pytest.approx(287.8)
