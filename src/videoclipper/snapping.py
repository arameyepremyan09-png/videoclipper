"""Stage 08 — Snapping.

Hier entscheidet sich, ob ein Clip handgeschnitten wirkt oder automatisch:
nicht mitten im Wort beginnen, keine Totzeit am Anfang, auf der Pointe enden.
"""

from __future__ import annotations

from collections.abc import Sequence

import numpy as np

from .settings import einstellungen
from .transcript import Transkript

# Wie nah an Anfang oder Ende ein Bilduebergang liegen darf, bevor die Grenze
# aus ihm herausgezogen wird. Das deckt Vor- und Nachlauf (0.20 / 0.35 s) ab —
# genau dort lagen die Uebergaenge, die bisher erst im Standbild auffielen.
GRENZZONE = 0.4

# Wann das letzte Wort wirklich zu Ende ist. GEMESSEN an saiJDq9DM_Y in
# 50-ms-Fenstern: Sprache liegt bei -13..-35 dBFS, Pausen bei -60..-100, vom
# Cutter stummgeschaltete Stellen bei -180. Eine einzelne leise Stelle ist oft
# nur die Luecke zwischen zwei Silben ("an-grei-fen" fiel bei 540.85 s auf
# -53) — erst 0.2 s am Stueck gelten als Pause.
STILLE_DB = -50.0
STILLE_MIN = 0.20
NACHKLANG = 0.15

Pegel = tuple[np.ndarray, np.ndarray]


def _naechste_wortgrenze(tr: Transkript, t: float, richtung: str,
                         spanne: float = 2.5) -> float:
    """Naechste Sprechpause in der gewuenschten Richtung."""
    if richtung == "vor":
        kandidaten = [w.start for w in tr.woerter if t - spanne <= w.start <= t + spanne]
        return min(kandidaten, key=lambda x: abs(x - t)) if kandidaten else t
    kandidaten = [w.ende for w in tr.woerter if t - spanne <= w.ende <= t + spanne]
    return min(kandidaten, key=lambda x: abs(x - t)) if kandidaten else t


def _stille_ab(pegel: Pegel, von: float, bis: float) -> float | None:
    """Beginn der ersten Pause von mindestens ``STILLE_MIN``, die vor ``bis`` einsetzt.

    Die Pause darf ueber ``bis`` hinaus andauern, sie muss nur vorher beginnen.
    Setzt dort schon das naechste Wort ein, reisst sie ab und zaehlt nicht.
    """
    zeiten, db = pegel
    if len(zeiten) < 2:
        return None
    noetig = max(1, int(round(STILLE_MIN / float(zeiten[1] - zeiten[0]))))
    i0 = int(np.searchsorted(zeiten, von))
    i1 = min(len(db), int(np.searchsorted(zeiten, bis + STILLE_MIN)) + 1)
    lauf = 0
    for i in range(i0, i1):
        lauf = lauf + 1 if db[i] < STILLE_DB else 0
        if lauf >= noetig:
            beginn = float(zeiten[i - noetig + 1])
            return beginn if beginn < bis else None
    return None


# GEMESSEN am 2026-09-11 an jd9bSJ7mshM (1:1 Kaese, durchgehend laut): An den
# Raendern eines json3-Ereignisses stimmen die Wortzeiten nicht mit dem Ton.
#
# * Einsatz: "Wir rudern zurueck" setzt bei 287.35 s ein, das Transkript nennt
#   288.0; "Was fuer Herzrasen" bei 1033.9 gegen 1034.72. 0.20 s Vorlauf vor
#   dem Transkript beginnen dort mitten im Satz.
# * Ausklang: Auf "dann bin ich einverstanden" folgt "Was?", 0.7 s Stille und
#   dann 1.9 s Gelaechter — die Reaktion, fuer die der Clip da ist.
#   ``_stille_ab`` fand die 0.7 s und schnitt davor ab. SCHNITTREGELN.md 1b:
#   Ein Clip, der vor der Reaktion aufhoert, ist keiner. Welche Luecke das
#   Ende ist, weiss der Pegel allein nicht — ein Lacher und das naechste Wort
#   sehen dort gleich aus. Das weiss die Selektion: Liegt ihr ``ende`` in
#   einer Luecke, wird dort geschnitten. Die AI entscheidet WAS, der Code WIE.
# * Kein Ausklang: Bei durchgehender Rede liegt im Nachlauf von 0.35 s schon
#   das naechste Wort ("gute." -> "Wir bauen"), und nirgends sind 0.2 s Stille.
#   Als Luecke zaehlt deshalb auch ein Tal, mindestens TAL_DB unter der
#   Umgebung — geschnitten wird an seiner leisesten Stelle.
EINSATZ_SPANNE = 1.0
TAL_DB = 10.0


def _einsatz(pegel: Pegel, t: float, spanne: float = EINSATZ_SPANNE) -> float | None:
    """Wo der Ton einsetzt, zu dem das erste Wort gehoert (laut Transkript bei ``t``).

    Gesucht wird die letzte Stille von mindestens zwei Fenstern, die zwischen
    ``t - spanne`` und kurz nach ``t`` liegt; zurueck kommt ihr letztes
    Fenster, der Clip beginnt also mit hoechstens 50 ms Stille. Hinter ``t``
    wird nur 0.1 s weit gesucht — weiter hinten laege schon die Pause nach dem
    ersten Wort, und der Clip begaenne hinter ihm. Ohne Stille in Reichweite
    (durchgehende Rede) gibt es keinen Einsatz, und der Vorlauf bleibt.
    """
    zeiten, db = pegel
    if len(zeiten) < 2:
        return None
    i0 = max(1, int(np.searchsorted(zeiten, t - spanne)))
    i1 = min(len(db), int(np.searchsorted(zeiten, t + 0.1)))
    for i in range(i1 - 1, i0 - 1, -1):
        if db[i] < STILLE_DB and db[i - 1] < STILLE_DB:
            return float(zeiten[i])
    return None


def _luecke(pegel: Pegel, t: float, von: float) -> float | None:
    """Schnittpunkt, wenn ``t`` in einer Luecke liegt — einer Pause oder einem Tal.

    Pause: ``t`` liegt in Stille, die insgesamt mindestens ``STILLE_MIN``
    dauert; geschnitten wird ``NACHKLANG`` nach ihrem Beginn. Tal: ``t`` liegt
    mindestens ``TAL_DB`` unter dem lauten Viertel der Umgebung (0.5 s zu
    beiden Seiten); geschnitten wird in der Mitte des leisesten Fensters.

    Gemessen wird gegen das laute Viertel, nicht gegen den Median. GEMESSEN an
    jd9bSJ7mshM bei 84.4 s: Hinter einem Lacher liegt dort nur noch der
    Grundpegel der Musik, 5 dB unter dem Median — den der Lacher und die
    Luecke selbst mitbestimmen —, aber 11 dB unter dem lauten Viertel. Bei
    gleichmaessigem Pegel gibt es kein Tal, und es bleibt beim Wortende.

    Beginnt die Luecke vor ``von``, liegt sie nicht hinter dem letzten Wort,
    und es gibt keinen Schnittpunkt.
    """
    zeiten, db = pegel
    if len(zeiten) < 2:
        return None
    dt = float(zeiten[1] - zeiten[0])
    i = int(np.searchsorted(zeiten, t, side="right")) - 1
    if i < 1 or i >= len(db):
        return None

    stille = bool(db[i] < STILLE_DB)
    r = int(round(0.5 / dt))
    if stille:
        grenze, links, rechts = STILLE_DB, 0, len(db) - 1
    else:
        grenze = float(np.percentile(db[max(0, i - r): i + r + 1], 75)) - TAL_DB
        if db[i] >= grenze:
            return None
        # Ein Tal ist eine Stelle, keine Strecke: Gesucht wird nur in der
        # Umgebung, an der die Grenze gemessen ist. Sonst liefe es bei hoher
        # Grenze ueber ganze Saetze, und das tiefste Fenster laege irgendwo.
        links, rechts = max(0, i - r), min(len(db) - 1, i + r)
    j, k = i, i
    while j > links and db[j - 1] < grenze:
        j -= 1
    while k < rechts and db[k + 1] < grenze:
        k += 1
    if zeiten[j] <= von:
        return None
    if stille:
        if (k - j + 1) * dt < STILLE_MIN - 1e-9:
            return None
        return float(zeiten[j]) + NACHKLANG
    tiefste = j + int(np.argmin(db[j:k + 1]))
    return float(zeiten[tiefste]) + dt / 2


def _aus_uebergaengen(s: float, en: float,
                      sperren: Sequence[tuple[float, float]]) -> tuple[float, float]:
    """Anfang und Ende aus Bilduebergaengen herausziehen.

    Jede Sperre ist ``(erstes veraendertes Bild, erstes fertiges neues Bild)``
    aus ``schnitte.uebergaenge``. Ein Uebergang am Anfang schiebt den Clip
    hinter sich, einer am Ende zieht das Ende davor. Uebergaenge mitten im
    Clip bleiben unberuehrt: Die meldet ``schnitte.melde``, und ob der Clip
    dort springen darf, entscheidet die Selektion, nicht das Snapping.
    """
    for a, b in sorted(sperren):
        if a < s + GRENZZONE and b > s:
            s = b
    for a, b in sorted(sperren, reverse=True):
        if b > en - GRENZZONE and a < en:
            en = a
    return s, en


def snappe(tr: Transkript, start: float, ende: float,
           sperren: Sequence[tuple[float, float]] = (),
           pegel: Pegel | None = None) -> tuple[float, float, str]:
    """Auf Wortgrenzen ausrichten und Tier bestimmen.

    Tier A wird nur vergeben, wenn die Laenge natuerlich erreicht wird. Gestreckt
    wird nie — ein isolierter Payoff bleibt kurz und damit Tier B.

    Beide Zusaetze kommen aus der Quelle und fehlen deshalb in ``clip
    rangliste``, das ohne Video rechnet. Ohne sie verhaelt sich die Funktion
    wie bisher.

    ``sperren``  Bilduebergaenge (``schnitte.uebergaenge``). Vor- und Nachlauf
                 laufen nicht in sie hinein.
    ``pegel``    Lautheit in 50-ms-Fenstern (``signals.lautheit``). Damit endet
                 der Clip, wo das letzte Wort wirklich endet — nie spaeter als
                 bisher, hoechstens frueher.
    """
    e = einstellungen()["monetarisierung"]
    s_wort = s = max(0.0, _naechste_wortgrenze(tr, start, "vor"))
    en_wort = en = min(tr.dauer, _naechste_wortgrenze(tr, ende, "zurueck"))
    gesnappt = en - s >= 5.0
    if not gesnappt:                       # Snapping hat das Fenster zerdrueckt
        s, en = start, ende

    # Kleiner Vor-/Nachlauf, damit der erste Konsonant nicht abgeschnitten wird.
    s = max(0.0, s - 0.20)
    en = min(tr.dauer, en + 0.35)

    # Der Anfang beim Ton statt beim Transkript — Begruendung bei
    # EINSATZ_SPANNE. Nur, wo wirklich auf einen Wortanfang gesnappt wurde.
    if pegel is not None and gesnappt and any(
            abs(w.start - s_wort) < 1e-6 for w in tr.woerter):
        einsatz = _einsatz(pegel, s_wort)
        if einsatz is not None:
            s = einsatz

    # GEMESSEN am 2026-09-11 an saiJDq9DM_Y: "angreifen." steht im Transkript
    # von 540.56 bis 543.12 s, gesprochen ist es um 541.0 zu Ende — danach hat
    # der Cutter 1.8 s stummgeschaltet. Das letzte Wort eines json3-Ereignisses
    # erbt das Fensterende, und vor einer Pause kuerzt ``lade_json3`` es nicht
    # (dort gibt es kein naechstes Wort, an dem es enden koennte). Der Nachlauf
    # haengte also 2.5 s Stille an; genau die will SCHNITTREGELN Regel 5
    # weggeschnitten haben. Gemessen wird nur hinter dem Anfang des letzten
    # Wortes, und das Ende wandert nur nach vorn.
    if pegel is not None and gesnappt:
        letztes = next((w for w in tr.woerter
                        if abs(w.ende - en_wort) < 1e-6 and not w.ist_marker), None)
        if letztes is not None:
            # Liegt das gewuenschte Ende in einer Luecke hinter dem letzten
            # Wort, ist genau diese gemeint — auch wenn davor noch ein Lacher
            # liegt (Begruendung bei EINSATZ_SPANNE). Sonst die erste Pause.
            luecke = _luecke(pegel, ende, letztes.start + 0.1)
            pause = (None if luecke is not None
                     else _stille_ab(pegel, letztes.start + 0.1, letztes.ende))
            if luecke is not None:
                en = min(en, luecke)
            elif pause is not None:
                en = min(en, pause + NACHKLANG)

    # GEMESSEN am 2026-09-07: Liegt das gewuenschte Fenster hinter dem letzten
    # transkribierten Wort, zieht ``min(tr.dauer, ...)`` das Ende VOR den
    # Anfang — ``snappe`` gab dann eine negative Dauer zurueck, und FFmpeg
    # bekam ein negatives ``-t``. Das Transkript endet regelmaessig vor dem
    # Video (nach dem letzten Wort laufen oft noch Bilder), der Fall ist also
    # nicht konstruiert. Dann gilt das ungesnappte Fenster.
    if en <= s:
        s, en = max(0.0, start), max(start + 0.05, ende)

    # GEMESSEN am 2026-09-11 an saiJDq9DM_Y: Der Vorlauf kennt nur Woerter,
    # keine Bilder. Das erste Wort nach dem Intro faellt dort 0.04 s hinter
    # einen harten Schnitt — 0.20 s Vorlauf zeigten zehn Bilder Intro, bevor
    # der Clip ueberhaupt anfing. Ein zweiter Anfang lag im Rest einer 0.3-s-
    # Ueberblendung zwischen Browser und Cam. Beides steht im ersten Bild des
    # fertigen Clips, und das erste Bild ist im Feed das Vorschaubild.
    if sperren:
        s2, en2 = _aus_uebergaengen(s, en, sperren)
        # Nie so weit, dass vom Clip nichts uebrig bleibt — dann lieber den
        # Uebergang zeigen und ``schnitte.melde`` ihn nennen lassen.
        if en2 - s2 >= 5.0:
            s, en = s2, en2

    tier = "A" if (en - s) >= e["tier_a_min_sekunden"] else "B"
    return round(s, 3), round(en, 3), tier
