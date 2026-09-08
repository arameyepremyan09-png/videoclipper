"""Ablage der Renderergebnisse — ein Lauf, ein Ordner.

Bis hierher schrieb jeder Renderlauf in denselben flachen ``clips/``-Ordner.
Nach acht vermessenen Videos lagen dort ueber 200 Eintraege aus einem Dutzend
Laeufen nebeneinander, und weil MP4, EditPlan-JSON und Headline-PNG desselben
Clips sich den Namensstamm teilen, standen sie auch noch verschraenkt:

    4ubrGJLb4FQ_001.editplan.json
    4ubrGJLb4FQ_001.headline.png
    4ubrGJLb4FQ_001.mp4
    4ubrGJLb4FQ_002.editplan.json
    ...

Welcher Lauf welchen Clip erzeugt hat, stand danach nur noch im Zeitstempel der
Datei — und wer die fertigen Clips aufs Handy ziehen wollte, musste sie aus den
Zwischenschritten heraussuchen.

Deshalb bekommt jeder Lauf einen eigenen Ordner, benannt nach seinem
Startzeitpunkt, und darunter liegen die Dateitypen getrennt:

    clips/2026-09-08_14-30-15/
      mp4/    die fertigen Clips  — das, was hochgeladen wird
      json/   EditPlans + lauf.json — was die Pipeline entschieden hat
      png/    Headline, Untertitel, Follow — Zwischenschritte des Renderers

Die Trennung ist nicht Kosmetik. ``mp4/`` ist der einzige Ordner, dessen Inhalt
den Rechner verlaesst; er laesst sich am Stueck kopieren, ohne dass
Zwischenschritte mitwandern. ``png/`` ist reiner Zwischenstand und jederzeit
loeschbar — der Renderer baut ihn aus dem EditPlan neu. Und ``json/`` ist das
Einzige, was auch noch etwas wert ist, wenn die Videodateien laengst geloescht
sind: Es sagt, welcher Ausschnitt mit welcher Headline gerendert wurde.

Ein Lauf ist bewusst der *Aufruf*, nicht das Video. Werden zwei Videos in einem
Rutsch geschnitten, gehoeren ihre Clips zusammen — sie entstehen aus derselben
Absicht und werden am selben Tag gepostet. Die Zuordnung zum Video steckt
ohnehin in jedem Clipnamen und zusaetzlich in ``lauf.json``.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

#: Ordnername eines Laufes. Sortiert als Text chronologisch, enthaelt keine
#: Zeichen, die Windows oder eine Shell gesondert behandeln — ``:`` aus der
#: ISO-Schreibweise ist auf Windows in Dateinamen verboten.
LAUF_FORMAT = "%Y-%m-%d_%H-%M-%S"

#: Die Unterordner. Der Schluessel ist die Dateiendung, die dort landet.
UNTERORDNER = ("mp4", "json", "png")


@dataclass(frozen=True)
class Lauf:
    """Ein Renderlauf und seine drei Unterordner.

    Die Ordner werden beim Anlegen erzeugt, nicht erst beim ersten Schreiben:
    Ein leerer ``mp4``-Ordner nach einem Abbruch ist eine ehrlichere Auskunft
    als ein fehlender.
    """

    wurzel: Path

    @property
    def mp4(self) -> Path:
        return self.wurzel / "mp4"

    @property
    def json(self) -> Path:
        return self.wurzel / "json"

    @property
    def png(self) -> Path:
        return self.wurzel / "png"

    @property
    def name(self) -> str:
        return self.wurzel.name

    def clip(self, clip_id: str) -> Path:
        """Zielpfad der fertigen MP4."""
        return self.mp4 / f"{clip_id}.mp4"

    def editplan(self, clip_id: str) -> Path:
        return self.json / f"{clip_id}.editplan.json"

    def notiere(self, **felder: Any) -> Path:
        """Schreibt ``json/lauf.json`` — was diesen Lauf ausgeloest hat.

        Ohne das ist ein Ordner nur ein Zeitstempel. Mit ihm laesst sich noch
        in einem Monat sagen, aus welcher Quelle und welchem Plan die Clips
        stammen, ohne einen EditPlan oeffnen zu muessen.
        """
        pfad = self.json / "lauf.json"
        vorhanden = {}
        if pfad.exists():
            vorhanden = json.loads(pfad.read_text(encoding="utf-8"))
        vorhanden.update(felder)
        vorhanden.setdefault("lauf", self.name)
        pfad.write_text(json.dumps(vorhanden, ensure_ascii=False, indent=2),
                        encoding="utf-8")
        return pfad


def neuer_lauf(basis: Path, zeitpunkt: datetime | None = None) -> Lauf:
    """Legt ``basis/<datum>_<uhrzeit>/{mp4,json,png}`` an.

    Faellt ein zweiter Lauf in dieselbe Sekunde — zwei Aufrufe aus einem
    Skript —, bekommt er ein ``_2`` angehaengt, statt in den fremden Ordner zu
    schreiben. Ein Lauf ueberschreibt nie einen anderen.
    """
    stempel = (zeitpunkt or datetime.now()).strftime(LAUF_FORMAT)
    ziel = basis / stempel
    zaehler = 2
    while ziel.exists():
        ziel = basis / f"{stempel}_{zaehler}"
        zaehler += 1

    lauf = Lauf(ziel)
    for unter in UNTERORDNER:
        (ziel / unter).mkdir(parents=True, exist_ok=True)
    return lauf


def zuletzt(basis: Path) -> Lauf | None:
    """Der juengste Lauf unter ``basis``, oder ``None``.

    Sortiert wird nach dem Ordnernamen, nicht nach der Aenderungszeit: Der Name
    ist der Startzeitpunkt und aendert sich nicht mehr, waehrend die
    Aenderungszeit beim Aufraeumen springt.
    """
    kandidaten = sorted(
        (p for p in basis.glob("*") if p.is_dir() and (p / "mp4").is_dir()),
        key=lambda p: p.name,
    )
    return Lauf(kandidaten[-1]) if kandidaten else None
