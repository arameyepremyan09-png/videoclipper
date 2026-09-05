"""Stage 17b — Performance-Score.

Was ein Clip nach der Veroeffentlichung wirklich getan hat, auf einer Zahl von
0 bis 100. Drei Regeln tragen das ganze Modul:

**Nur Raten, nie Rohzahlen.** Ein Clip mit 1000 Views und 50 Likes ist besser
als einer mit 5000 Views und 100 Likes. Wer Rohzahlen vergleicht, behauptet das
Gegenteil und optimiert am Ende auf Glueck statt auf Qualitaet.

**Nur innerhalb desselben Messfensters.** Views nach 1 h und nach 7 d sind
verschiedene Groessen. Ohne diese Trennung gewinnt immer der aeltere Post.

**Fehlende Metriken werden nicht als Null gewertet.** Completion-Rate und
Follows kommen aus dem Creator-Center und fehlen anfangs bei jedem Post. Wer
sie als 0 einsetzt, bestraft den Clip fuer eine fehlende Messung. Stattdessen
wird das Gewicht der fehlenden Achse auf die vorhandenen verteilt und die
erreichte ``abdeckung`` mit ausgegeben.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from functools import cache
from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parents[2]


def _verschmelze(basis: dict, drueber: dict) -> dict:
    erg = dict(basis)
    for k, v in drueber.items():
        erg[k] = _verschmelze(erg[k], v) if isinstance(erg.get(k), dict) \
            and isinstance(v, dict) else v
    return erg


@cache
def konfiguration() -> dict[str, Any]:
    """scoring.yaml, ueberschrieben von einer optionalen Kalibrierdatei.

    Dasselbe Muster wie settings.toml/local.toml: Die handgepflegte Datei mit
    ihren Begruendungen bleibt unangetastet, `clip kalibriere` schreibt nur die
    gemessenen Zahlen in ein Overlay. Loeschen des Overlays stellt die
    Startannahmen wieder her — eine Kalibrierung auf duenner Datenbasis ist
    damit jederzeit rueckgaengig zu machen.
    """
    with (ROOT / "config" / "scoring.yaml").open("rb") as f:
        daten = yaml.safe_load(f)
    overlay = ROOT / "config" / "scoring.kalibriert.yaml"
    if overlay.exists():
        with overlay.open("rb") as f:
            gemessen = yaml.safe_load(f) or {}
        daten = _verschmelze(daten, gemessen)
    return daten


# ---------------------------------------------------------------------------
# Raten
# ---------------------------------------------------------------------------

RATEN_FELDER = ("like_rate", "kommentar_rate", "share_rate", "save_rate",
                "follow_rate")


def _glaette(ereignisse: float, views: float, p0: float) -> float:
    """Eine Rate zum Erwartungswert hinziehen, gewichtet mit der Beobachtungszahl.

    Ohne das ist jede Rate aus wenigen Views Rauschen: 1 Like auf 4 Views sind
    25 %, das Fuenffache eines sehr guten Werts — gemessen am 2026-09-05, wo
    genau dieser Post dadurch auf Platz 1 von 10 landete.

    Bei ``views == prior_views`` zaehlen Messung und Annahme gleich viel; bei
    tausend Views ist der Prior praktisch verschwunden.
    """
    m = konfiguration()["glaettung"]["prior_views"]
    return (ereignisse + m * p0) / (views + m)


def raten(messung: dict[str, Any], dauer: float | None,
          plattform: str | None = None, geglaettet: bool = True
          ) -> dict[str, float | None]:
    """Rohe Zaehlwerte in Raten umrechnen. ``None`` heisst nicht gemessen.

    Ohne Views ist keine Rate definiert — nicht null, sondern unbekannt.
    Ein Post mit 0 Views hat keine schlechte Like-Rate, er hat gar keine.

    ``geglaettet=False`` liefert die rohen Quotienten. Die sind fuer die
    Anzeige richtig ("6,7 % Like-Rate") und fuer die Bewertung falsch.
    """
    views = messung.get("views")
    erg: dict[str, float | None] = {f: None for f in RATEN_FELDER}
    erg["completion_rate"] = None
    erg["watchtime_abs"] = None

    if views:
        for feld, quelle in (("like_rate", "likes"),
                             ("kommentar_rate", "kommentare"),
                             ("share_rate", "shares"),
                             ("save_rate", "saves"),
                             ("follow_rate", "follows")):
            wert = messung.get(quelle)
            if wert is None:
                continue
            b = _bench(plattform, feld) if plattform else None
            erg[feld] = (_glaette(wert, views, b["mittel"])
                         if geglaettet and b else wert / views)

    wt = messung.get("avg_watchtime")
    cr = messung.get("completion_rate")
    if wt is not None:
        erg["watchtime_abs"] = float(wt)
        # Completion aus Watchtime ableiten, wenn die Plattform sie nicht
        # direkt liefert. Ueber 1.0 ist legitim: Loops zaehlen mit.
        if cr is None and dauer:
            cr = wt / dauer
    if cr is not None:
        erg["completion_rate"] = float(cr)
    elif erg["watchtime_abs"] is None and dauer and messung.get("view_time_total") \
            and views:
        erg["watchtime_abs"] = messung["view_time_total"] / views
        erg["completion_rate"] = erg["watchtime_abs"] / dauer

    return erg


# ---------------------------------------------------------------------------
# Normalisierung
# ---------------------------------------------------------------------------

def _normiere(wert: float, schwach: float, mittel: float, stark: float) -> float:
    """Stueckweise linear auf 0..1, oberhalb von ``stark`` asymptotisch.

    Die Stuetzpunkte sind bewusst nicht gleichmaessig: 0.25 / 0.50 / 0.85 laesst
    Luft nach oben, damit ein wirklich viraler Ausreisser sich noch vom bloss
    guten Clip abhebt, statt beide bei 100 zu deckeln.
    """
    if wert <= 0:
        return 0.0
    if wert <= schwach:
        return 0.25 * (wert / schwach) if schwach > 0 else 0.0
    if wert <= mittel:
        return 0.25 + 0.25 * (wert - schwach) / max(mittel - schwach, 1e-9)
    if wert <= stark:
        return 0.50 + 0.35 * (wert - mittel) / max(stark - mittel, 1e-9)
    return 0.85 + 0.15 * (1.0 - math.exp(-(wert - stark) / max(stark, 1e-9)))


def _bench(plattform: str, feld: str) -> dict[str, float] | None:
    b = konfiguration()["benchmarks"].get(plattform)
    return b.get(feld) if b else None


# ---------------------------------------------------------------------------
# Der Score
# ---------------------------------------------------------------------------

@dataclass
class Bewertung:
    score: float                     # 0..100
    achsen: dict[str, float | None]  # je 0..1, None = nicht messbar
    abdeckung: float                 # Anteil des Gewichts, der wirklich belegt ist
    fehlend: list[str] = field(default_factory=list)
    hinweise: list[str] = field(default_factory=list)
    genug_views: bool = True

    @property
    def belastbar(self) -> bool:
        """Zwei getrennte Gruende, einem Score nicht zu trauen: zu wenige
        Achsen gemessen, oder zu wenige Views hinter den Raten. Beide muessen
        erfuellt sein, sonst ist die Zahl eine Andeutung und kein Urteil."""
        return self.abdeckung >= 0.66 and self.genug_views


def _achse_engagement(r: dict, plattform: str) -> float | None:
    cfg = konfiguration()
    gew = cfg["performance"]["engagement_gewichte"]
    paare = (("share", "share_rate"), ("save", "save_rate"),
             ("kommentar", "kommentar_rate"), ("like", "like_rate"))
    summe = gewicht_summe = 0.0
    for name, feld in paare:
        if r.get(feld) is None:
            continue
        b = _bench(plattform, feld)
        if not b:
            continue
        summe += gew[name] * _normiere(r[feld], b["schwach"], b["mittel"], b["stark"])
        gewicht_summe += gew[name]
    return summe / gewicht_summe if gewicht_summe else None


def _achse_retention(r: dict, plattform: str) -> float | None:
    cfg = konfiguration()
    gew = cfg["performance"]["retention_gewichte"]
    summe = gewicht_summe = 0.0
    for name, feld in (("completion_rate", "completion_rate"),
                       ("watchtime_abs", "watchtime_abs")):
        if r.get(feld) is None:
            continue
        b = _bench(plattform, feld)
        if not b:
            continue
        summe += gew[name] * _normiere(r[feld], b["schwach"], b["mittel"], b["stark"])
        gewicht_summe += gew[name]
    return summe / gewicht_summe if gewicht_summe else None


def _achse_reichweite(views: int | None, median: float | None) -> float | None:
    """Views gegen den eigenen Median, logarithmisch.

    Logarithmisch, weil viral eine Groessenordnung ist und kein Zuschlag: Der
    Sprung von 1000 auf 10 000 ist derselbe Vorgang wie der von 10 000 auf
    100 000, und beide sind etwas voellig anderes als 900 gegen 1000.
    """
    if views is None or not median or median <= 0:
        return None
    verhaeltnis = max(views, 1) / median
    # 0.1x -> 0.0, 1x -> 0.5, 10x -> 1.0
    return min(1.0, max(0.0, 0.5 + 0.5 * math.log10(verhaeltnis)))


def bewerte(messung: dict[str, Any], plattform: str, dauer: float | None,
            median_views: float | None = None) -> Bewertung:
    """Ein Messschnappschuss wird zu einer Zahl.

    ``median_views`` ist der Median derselben Plattform im selben Messfenster.
    Fehlt er, entfaellt die Reichweiten-Achse und ihr Gewicht verteilt sich.
    """
    cfg = konfiguration()
    gew = cfg["performance"]["achsen"]
    r = raten(messung, dauer, plattform)

    achsen: dict[str, float | None] = {
        "retention": _achse_retention(r, plattform),
        "engagement": _achse_engagement(r, plattform),
        "konversion": (_normiere(r["follow_rate"], **_bench(plattform, "follow_rate"))
                       if r.get("follow_rate") is not None
                       and _bench(plattform, "follow_rate") else None),
        "reichweite": _achse_reichweite(messung.get("views"), median_views),
    }

    # Fehlende Achsen tragen ihr Gewicht nicht mit. Der Rest wird auf die
    # vorhandenen umgelegt, statt Nullen einzusetzen.
    vorhanden = {k: v for k, v in achsen.items() if v is not None}
    gewicht_da = sum(gew[k] for k in vorhanden)
    fehlend = [k for k, v in achsen.items() if v is None]

    views = messung.get("views")
    genug = (views or 0) >= cfg["glaettung"]["min_views_fuer_urteil"]

    if not vorhanden:
        return Bewertung(0.0, achsen, 0.0, fehlend,
                         ["Keine einzige Achse messbar — fehlen die Views?"],
                         genug_views=genug)

    score = 100.0 * sum(gew[k] * v for k, v in vorhanden.items()) / gewicht_da

    hinweise = []
    if "retention" in fehlend:
        hinweise.append("Retention fehlt (Creator-Center) — schwerste Achse ungedeckt")
    if "konversion" in fehlend:
        hinweise.append("Follows fehlen (Creator-Center)")
    if not genug:
        hinweise.append(
            f"Nur {views or 0} Views — unter {cfg['glaettung']['min_views_fuer_urteil']} "
            "sind die Raten geglaettet und der Score kein Urteil ueber den Clip, "
            "sondern ueber die Ausspielung")

    return Bewertung(round(score, 1), achsen, round(gewicht_da, 3), fehlend,
                     hinweise, genug_views=genug)
