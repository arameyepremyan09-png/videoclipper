"""Stage 15 — Prognose.

Was sich ueber einen Clip sagen laesst, BEVOR er draussen ist. Fuenf Merkmale,
alle vor dem Posten bekannt: Hook, Dauer, Payoff-Position, Postzeit, Thema.

Dies ist der schwaechste Teil des Systems, und das Modul sagt das selbst. Die
Startgewichte in ``config/scoring.yaml`` sind Annahmen — plausible, aber
unbelegte. Deshalb gibt jede Prognose eine ``konfidenz`` mit aus, die bei nicht
kalibrierten Gewichten niedrig bleibt. Eine Prognose mit Konfidenz 0.2 ist eine
Sortierhilfe fuer die Reviewschlange, keine Vorhersage.

``clip kalibriere`` ersetzt die Annahmen durch gemessene Werte, sobald genug
eigene Posts vorliegen. Erst danach verdient die Zahl ihren Namen.
"""

from __future__ import annotations

import math
import re
import unicodedata
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from .scoring import konfiguration

# Fuellwoerter tragen kein Thema. Klein gehalten und bewusst deutsch —
# das Material ist deutschsprachig.
STOPP = {
    "der", "die", "das", "und", "ist", "ich", "du", "er", "sie", "es", "wir",
    "ihr", "den", "dem", "ein", "eine", "einen", "einem", "einer", "nicht",
    "mit", "auf", "von", "zu", "in", "im", "am", "an", "fuer", "für", "aber",
    "auch", "so", "wie", "was", "hat", "habe", "hab", "bin", "war", "mal",
    "noch", "schon", "dann", "da", "man", "mir", "mich", "dich", "sich", "denn",
}


def _woerter(text: str) -> list[str]:
    return [w for w in re.findall(r"[\wäöüßÄÖÜ]+", text.lower()) if w]


def _schluessel(text: str) -> set[str]:
    """Themenwoerter: Hashtags und laengere Nicht-Fuellwoerter."""
    tags = {t.lower() for t in re.findall(r"#(\w+)", text)}
    rest = {w for w in _woerter(re.sub(r"#\w+", " ", text))
            if len(w) >= 4 and w not in STOPP}
    return tags | rest


def _interpoliere(x: float, punkte: list[list[float]]) -> float:
    """Lineare Interpolation zwischen Stuetzpunkten, ausserhalb geklemmt."""
    ps = sorted(punkte)
    if x <= ps[0][0]:
        return float(ps[0][1])
    if x >= ps[-1][0]:
        return float(ps[-1][1])
    for (x0, y0), (x1, y1) in zip(ps, ps[1:]):
        if x0 <= x <= x1:
            return float(y0 + (y1 - y0) * (x - x0) / max(x1 - x0, 1e-9))
    return float(ps[-1][1])


# ---------------------------------------------------------------------------

@dataclass
class Merkmale:
    """Alles, was vor dem Posten feststeht."""
    headline: str
    dauer: float
    plattform: str = "tiktok"
    hook_text: str = ""              # Transkript der ersten Sekunden
    payoff_position: float | None = None   # 0..1, wo die Pointe im Clip liegt
    postzeit: datetime | None = None
    hashtags: list[str] = field(default_factory=list)


@dataclass
class Teilwert:
    wert: float                      # 0..1
    grund: str


@dataclass
class Prognose:
    score: float                     # 0..100
    teile: dict[str, Teilwert]
    konfidenz: float                 # 0..1 — wie sehr die Gewichte belegt sind
    hinweise: list[str] = field(default_factory=list)
    beste_stunden: list[int] = field(default_factory=list)

    @property
    def kalibriert(self) -> bool:
        return konfiguration()["prognose"]["kalibriert_am"] is not None


# ---------------------------------------------------------------------------
# Die fuenf Merkmale
# ---------------------------------------------------------------------------

def _hook(m: Merkmale) -> Teilwert:
    """Die ersten Sekunden entscheiden, ob ueberhaupt jemand bleibt.

    Drei Teile: Wie viel gesprochen wird (wenig ist besser als viel), ob ein
    Signalwort vorkommt, und ob die Headline in einem Blick lesbar ist.
    """
    cfg = konfiguration()["prognose"]["hook"]
    gruende = []

    woerter = _woerter(m.hook_text)
    if m.hook_text:
        anteil = len(woerter) / max(cfg["max_woerter"], 1)
        # Ideal ist knapp unter der Grenze: gar nichts gesagt ist auch kein Hook.
        dichte = 1.0 - abs(anteil - 0.6) / 0.6 if anteil <= 1.2 else 0.2
        dichte = max(0.0, min(1.0, dichte))
        gruende.append(f"{len(woerter)} Woerter in {cfg['fenster_sekunden']:.0f}s")
    else:
        dichte = 0.5
        gruende.append("kein Hook-Transkript uebergeben")

    signale = {w for w in cfg["signalwoerter"]}
    treffer = sorted(set(woerter) & signale)
    signal = min(1.0, 0.35 + 0.35 * len(treffer)) if treffer else 0.25
    if treffer:
        gruende.append("Signalwort " + "/".join(treffer[:3]))

    lo, hi = cfg["headline_zeichen_ideal"]
    n = len(m.headline)
    if lo <= n <= hi:
        kopf = 1.0
        gruende.append(f"Headline {n} Zeichen")
    else:
        kopf = max(0.2, 1.0 - abs(n - (lo + hi) / 2) / max(hi, 1))
        gruende.append(f"Headline {n} Zeichen (ideal {lo}-{hi})")

    wert = 0.40 * dichte + 0.35 * signal + 0.25 * kopf
    return Teilwert(round(wert, 3), "; ".join(gruende))


def _dauer(m: Merkmale) -> Teilwert:
    punkte = konfiguration()["prognose"]["dauer"]["stuetzpunkte"]
    wert = _interpoliere(m.dauer, punkte)
    return Teilwert(round(wert, 3), f"{m.dauer:.0f}s")


def _payoff(m: Merkmale) -> Teilwert:
    if m.payoff_position is None:
        return Teilwert(0.5, "Payoff-Position unbekannt")
    lo, hi = konfiguration()["prognose"]["payoff"]["ideal"]
    p = m.payoff_position
    if lo <= p <= hi:
        return Teilwert(1.0, f"Pointe bei {p:.0%} der Laufzeit")
    abstand = (lo - p) if p < lo else (p - hi)
    wert = max(0.2, 1.0 - 2.5 * abstand)
    lage = "frueh — kein Grund weiterzuschauen" if p < lo \
        else "spaet — die meisten sind vorher weg"
    return Teilwert(round(wert, 3), f"Pointe bei {p:.0%}, {lage}")


def _postzeit(m: Merkmale) -> Teilwert:
    if m.postzeit is None:
        return Teilwert(0.5, "keine Postzeit angegeben")
    faktoren = konfiguration()["prognose"]["postzeit"]["stundenfaktor"]
    h = m.postzeit.hour
    wert = float(faktoren.get(h, faktoren.get(str(h), 0.6)))
    return Teilwert(round(wert, 3), f"{h:02d} Uhr")


def _thema(m: Merkmale, historie: list[tuple[str, float]]) -> Teilwert:
    """Das Thema gegen die eigene Historie.

    ``historie`` ist [(Titel des Posts, Performance-Score 0..100)]. Ohne
    Historie gibt es kein Themenurteil — dann neutral, nicht geraten.
    """
    if not historie:
        return Teilwert(0.5, "keine Historie — Thema nicht bewertbar")

    eigene = _schluessel(m.headline + " " + " ".join(m.hashtags))
    if not eigene:
        return Teilwert(0.5, "keine Themenwoerter erkannt")

    passend = [(s, len(eigene & _schluessel(t)))
               for t, s in historie if eigene & _schluessel(t)]
    if not passend:
        return Teilwert(0.5, "Thema kommt in der Historie nicht vor")

    gewicht = sum(n for _, n in passend)
    schnitt = sum(s * n for s, n in passend) / gewicht
    return Teilwert(round(min(1.0, schnitt / 100.0), 3),
                    f"{len(passend)} vergleichbare Posts, Schnitt {schnitt:.0f}")


# ---------------------------------------------------------------------------

def prognostiziere(m: Merkmale, historie: list[tuple[str, float]] | None = None
                   ) -> Prognose:
    cfg = konfiguration()["prognose"]
    gew = cfg["gewichte"]

    teile = {
        "hook": _hook(m),
        "dauer": _dauer(m),
        "payoff": _payoff(m),
        "postzeit": _postzeit(m),
        "thema": _thema(m, historie or []),
    }
    score = 100.0 * sum(gew[k] * t.wert for k, t in teile.items()) / sum(gew.values())

    # Konfidenz: ohne Kalibrierung bleibt sie niedrig, egal wie sicher die
    # Zahl aussieht. Das ist der Punkt — eine unbelegte Gewichtung darf sich
    # nicht als Vorhersage ausgeben.
    grundlage = cfg.get("grundlage_posts", 0)
    if cfg.get("kalibriert_am") is None:
        konfidenz = 0.2
    else:
        konfidenz = min(0.9, 0.3 + 0.6 * (1 - math.exp(-grundlage / 40)))

    hinweise = []
    if cfg.get("kalibriert_am") is None:
        hinweise.append("Gewichte sind Startannahmen, nicht kalibriert "
                        "— `clip kalibriere`, sobald ~30 Posts gemessen sind")
    if not m.hook_text:
        hinweise.append("Ohne Hook-Transkript faellt das schwerste Merkmal "
                        "auf einen Mittelwert zurueck")

    faktoren = cfg["postzeit"]["stundenfaktor"]
    beste = sorted(range(24),
                   key=lambda h: -float(faktoren.get(h, faktoren.get(str(h), 0))))[:3]

    return Prognose(round(score, 1), teile, round(konfidenz, 2), hinweise,
                    sorted(beste))
