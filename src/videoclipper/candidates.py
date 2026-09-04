"""Stage 05 — Kandidaten.

Deterministisches Zusammenfuehren der Signale zu Zeitfenstern. Bewusst ohne LLM:
Das ist der Filter, der die AI-Kosten um zwei Groessenordnungen drueckt — die
Selektion sieht nie das ganze Video, nur die Umgebung dieser Fenster.

Ein globaler Lautheitsschwellwert taugt bei diesem Material nicht: Ein
Reaction-Streamer ist fast durchgehend laut, damit verschmelzen die Fenster zu
wenigen Bloecken ueber Minuten. Stattdessen werden lokale Maxima mit erzwungenem
Mindestabstand gepflueckt — das verteilt die Kandidaten ueber das ganze Video.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from .signals import Signale
from .transcript import Transkript


@dataclass
class Kandidat:
    peak: float          # der Moment selbst
    start: float         # Kontextfenster, in dem die Selektion schneiden darf
    ende: float
    score: float
    quelle: str
    modus_anteil: float
    text: str


def _glaetten(x: np.ndarray, breite: int) -> np.ndarray:
    if breite < 2:
        return x
    kern = np.ones(breite) / breite
    return np.convolve(x, kern, mode="same")


def bilde(tr: Transkript, sig: Signale, gewichte: dict[str, float],
          vorlauf: float = 35.0, nachlauf: float = 20.0,
          mindestabstand: float = 22.0, maximal: int = 40) -> list[Kandidat]:
    """Lokale Maxima einer kombinierten Signalkurve.

    Der Vorlauf ist bewusst gross: Der Aufbau vor der Pointe traegt einen Clip
    ueber 60 Sekunden, ohne ihn zu strecken. Die Selektion schneidet darin.
    """
    zt, db = sig.zeiten_db, sig.db
    raster = float(zt[1] - zt[0])

    endlich = db[np.isfinite(db)]
    p50, p99 = np.percentile(endlich, 50), np.percentile(endlich, 99)
    laut = np.clip((db - p50) / max(p99 - p50, 1e-6), 0.0, 1.0)
    laut = _glaetten(laut, max(2, int(round(2.0 / raster))))

    kurve = gewichte.get("loudness_peak", 0.8) * laut

    g_lach = gewichte.get("lachmarker", 1.0)
    if g_lach > 0 and sig.lacher:
        lach = np.zeros_like(kurve)
        halb = int(round(3.0 / raster))
        for t in sig.lacher:
            i = int(round(t / raster))
            lach[max(0, i - halb):min(len(lach), i + halb)] = 1.0
        kurve = kurve + g_lach * lach

    herkunft = np.where(
        (np.array([any(abs(t - l) <= 3.0 for l in sig.lacher) for t in zt])
         if sig.lacher else np.zeros(len(zt), bool)), "lacher", "lautheit")

    # Gierige Auswahl: staerkster Punkt, dann Umgebung sperren.
    rest = kurve.copy()
    sperre = int(round(mindestabstand / raster))
    gewaehlt: list[int] = []
    while len(gewaehlt) < maximal:
        i = int(np.argmax(rest))
        if rest[i] <= 0:
            break
        gewaehlt.append(i)
        rest[max(0, i - sperre):min(len(rest), i + sperre)] = 0.0

    kandidaten = []
    for i in sorted(gewaehlt):
        t = float(zt[i])
        s = max(0.0, t - vorlauf)
        e = min(tr.dauer, t + nachlauf)
        if e - s < 20.0:
            continue
        kandidaten.append(Kandidat(
            round(t, 2), round(s, 2), round(e, 2), round(float(kurve[i]), 3),
            str(herkunft[i]), round(sig.modus_anteil(s, e), 3),
            tr.text_zwischen(s, e)))

    kandidaten.sort(key=lambda k: k.score, reverse=True)
    return kandidaten
