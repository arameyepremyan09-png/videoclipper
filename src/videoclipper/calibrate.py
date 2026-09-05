"""Annahmen durch Messungen ersetzen.

Die Startwerte in ``config/scoring.yaml`` sind als Annahmen markiert. Dieses
Modul ersetzt sie durch die eigenen Zahlen, sobald genug Posts vorliegen — und
verweigert die Arbeit, solange das nicht der Fall ist. Das ist der Punkt: Eine
Kalibrierung auf sieben Posts waere schaedlicher als gar keine, weil sie
Annahmen durch Zufall ersetzt und dabei wie Wissen aussieht.

Geschrieben wird nach ``config/scoring.kalibriert.yaml``. Die handgepflegte
Datei mit ihren Begruendungen bleibt unberuehrt; das Overlay laesst sich
loeschen, um zu den Startannahmen zurueckzukehren.
"""

from __future__ import annotations

import statistics
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

from . import store
from .report import sammle_auswertung
from .scoring import ROOT, konfiguration

OVERLAY = ROOT / "config" / "scoring.kalibriert.yaml"

# Was wieviel Datenbasis braucht. Die Benchmarks sind Perzentile und brauchen
# am wenigsten; die Postzeit braucht Posts ueber viele Stunden verteilt, sonst
# misst sie den Tagesrhythmus eines einzigen Tages.
BEDARF = {"benchmarks": 8, "dauer": 25, "postzeit": 30}


@dataclass
class Ergebnis:
    geschrieben: dict[str, Any] = field(default_factory=dict)
    uebersprungen: list[str] = field(default_factory=list)
    grundlage: int = 0


def _perzentil(werte: list[float], p: float) -> float:
    if not werte:
        return 0.0
    s = sorted(werte)
    if len(s) == 1:
        return s[0]
    i = p * (len(s) - 1)
    lo, hi = int(i), min(int(i) + 1, len(s) - 1)
    return s[lo] + (s[hi] - s[lo]) * (i - lo)


def kalibriere(schreiben: bool = True) -> Ergebnis:
    cfg = konfiguration()
    a = sammle_auswertung()
    erg = Ergebnis()

    # Nur gerankte Posts: Ein Post mit vier Views wuerde die Perzentile
    # verzerren, und genau davor schuetzt die Reichweitenschwelle.
    zeilen = a.gerankt
    erg.grundlage = len(zeilen)

    neu: dict[str, Any] = {}

    # --- Benchmarks: die eigenen Raten als Perzentile -----------------------
    nach_plattform: dict[str, list] = {}
    for z in zeilen:
        nach_plattform.setdefault(z.post["plattform"], []).append(z)

    benchmarks: dict[str, dict] = {}
    if not nach_plattform:
        erg.uebersprungen.append(
            "benchmarks: kein einziger Post ueber der Reichweitenschwelle — "
            "die Annahmen bleiben stehen")
    for plattform, gruppe in nach_plattform.items():
        if len(gruppe) < BEDARF["benchmarks"]:
            erg.uebersprungen.append(
                f"benchmarks/{plattform}: {len(gruppe)} von "
                f"{BEDARF['benchmarks']} noetigen Posts")
            continue
        felder: dict[str, dict[str, float]] = {}
        for feld in ("completion_rate", "watchtime_abs", "like_rate",
                     "kommentar_rate", "share_rate", "save_rate", "follow_rate"):
            werte = [z.rohraten.get(feld) for z in gruppe]
            werte = [w for w in werte if w is not None]
            if len(werte) < BEDARF["benchmarks"]:
                continue
            felder[feld] = {
                "schwach": round(_perzentil(werte, 0.25), 6),
                "mittel": round(_perzentil(werte, 0.50), 6),
                "stark": round(_perzentil(werte, 0.75), 6),
            }
        if felder:
            benchmarks[plattform] = felder
        else:
            erg.uebersprungen.append(
                f"benchmarks/{plattform}: keine Metrik oft genug gemessen")
    if benchmarks:
        neu["benchmarks"] = benchmarks

    # --- Dauerkurve ---------------------------------------------------------
    paare = [(z.post["dauer"], z.bewertung.score) for z in zeilen
             if z.post.get("dauer")]
    if len(paare) >= BEDARF["dauer"]:
        koerbe: dict[int, list[float]] = {}
        for d, s in paare:
            koerbe.setdefault(int(d // 15) * 15 + 7, []).append(s)
        punkte = [[k, round(min(1.0, statistics.mean(v) / 100.0), 3)]
                  for k, v in sorted(koerbe.items()) if len(v) >= 3]
        if len(punkte) >= 3:
            neu.setdefault("prognose", {})["dauer"] = {"stuetzpunkte": punkte}
        else:
            erg.uebersprungen.append("prognose/dauer: zu wenige besetzte Laengenkoerbe")
    else:
        erg.uebersprungen.append(
            f"prognose/dauer: {len(paare)} von {BEDARF['dauer']} noetigen Posts")

    # --- Postzeit -----------------------------------------------------------
    zeit = [(int(z.post["veroeffentlicht"][11:13]), z.views) for z in zeilen
            if z.post.get("veroeffentlicht")]
    stunden = {h for h, _ in zeit}
    if len(zeit) >= BEDARF["postzeit"] and len(stunden) >= 6:
        median_gesamt = statistics.median([v for _, v in zeit]) or 1
        faktoren = {}
        for h in range(24):
            eigene = [v for hh, v in zeit if hh == h]
            if eigene:
                faktoren[h] = round(min(1.0, statistics.median(eigene)
                                        / median_gesamt), 3)
        if faktoren:
            neu.setdefault("prognose", {})["postzeit"] = {"stundenfaktor": faktoren}
    else:
        erg.uebersprungen.append(
            f"prognose/postzeit: {len(zeit)} Posts ueber {len(stunden)} Stunden "
            f"— noetig sind {BEDARF['postzeit']} ueber mindestens 6 Stunden")

    if neu:
        neu.setdefault("prognose", {})["kalibriert_am"] = store.jetzt()[:10]
        neu["prognose"]["grundlage_posts"] = erg.grundlage
        erg.geschrieben = neu
        if schreiben:
            kopf = ("# Automatisch erzeugt von `clip kalibriere` — nicht von Hand\n"
                    "# bearbeiten. Ueberschreibt die Startannahmen in scoring.yaml.\n"
                    "# Loeschen stellt die Annahmen wieder her.\n"
                    f"# Grundlage: {erg.grundlage} bewertbare Posts.\n\n")
            OVERLAY.write_text(
                kopf + yaml.safe_dump(neu, allow_unicode=True, sort_keys=True),
                encoding="utf-8")
            konfiguration.cache_clear()

    return erg
