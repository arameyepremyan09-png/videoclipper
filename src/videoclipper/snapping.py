"""Stage 08 — Snapping.

Hier entscheidet sich, ob ein Clip handgeschnitten wirkt oder automatisch:
nicht mitten im Wort beginnen, keine Totzeit am Anfang, auf der Pointe enden.
"""

from __future__ import annotations

from .settings import einstellungen
from .transcript import Transkript


def _naechste_wortgrenze(tr: Transkript, t: float, richtung: str,
                         spanne: float = 2.5) -> float:
    """Naechste Sprechpause in der gewuenschten Richtung."""
    if richtung == "vor":
        kandidaten = [w.start for w in tr.woerter if t - spanne <= w.start <= t + spanne]
        return min(kandidaten, key=lambda x: abs(x - t)) if kandidaten else t
    kandidaten = [w.ende for w in tr.woerter if t - spanne <= w.ende <= t + spanne]
    return min(kandidaten, key=lambda x: abs(x - t)) if kandidaten else t


def snappe(tr: Transkript, start: float, ende: float) -> tuple[float, float, str]:
    """Auf Wortgrenzen ausrichten und Tier bestimmen.

    Tier A wird nur vergeben, wenn die Laenge natuerlich erreicht wird. Gestreckt
    wird nie — ein isolierter Payoff bleibt kurz und damit Tier B.
    """
    e = einstellungen()["monetarisierung"]
    s = max(0.0, _naechste_wortgrenze(tr, start, "vor"))
    en = min(tr.dauer, _naechste_wortgrenze(tr, ende, "zurueck"))
    if en - s < 5.0:                       # Snapping hat das Fenster zerdrueckt
        s, en = start, ende

    # Kleiner Vor-/Nachlauf, damit der erste Konsonant nicht abgeschnitten wird.
    s = max(0.0, s - 0.20)
    en = min(tr.dauer, en + 0.35)

    # GEMESSEN am 2026-09-07: Liegt das gewuenschte Fenster hinter dem letzten
    # transkribierten Wort, zieht ``min(tr.dauer, ...)`` das Ende VOR den
    # Anfang — ``snappe`` gab dann eine negative Dauer zurueck, und FFmpeg
    # bekam ein negatives ``-t``. Das Transkript endet regelmaessig vor dem
    # Video (nach dem letzten Wort laufen oft noch Bilder), der Fall ist also
    # nicht konstruiert. Dann gilt das ungesnappte Fenster.
    if en <= s:
        s, en = max(0.0, start), max(start + 0.05, ende)

    tier = "A" if (en - s) >= e["tier_a_min_sekunden"] else "B"
    return round(s, 3), round(en, 3), tier
