"""Plattformauflösung.

Genau drei Dinge unterscheiden sich zwischen dem Windows-Desktop und dem
MacBook: Arbeitsverzeichnis, Encoder und ASR-Backend. Sie werden hier einmal
aufgelöst; der Rest der Pipeline sieht nur noch fertige Werte.
"""

from __future__ import annotations

import sys
import tomllib
from functools import cache
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
CONFIG_DIR = ROOT / "config"


def _deep_merge(basis: dict[str, Any], drueber: dict[str, Any]) -> dict[str, Any]:
    """Verschmilzt zwei Konfigurationen; verschachtelte Tabellen bleiben erhalten."""
    ergebnis = dict(basis)
    for schluessel, wert in drueber.items():
        vorhanden = ergebnis.get(schluessel)
        if isinstance(vorhanden, dict) and isinstance(wert, dict):
            ergebnis[schluessel] = _deep_merge(vorhanden, wert)
        else:
            ergebnis[schluessel] = wert
    return ergebnis


@cache
def einstellungen() -> dict[str, Any]:
    """settings.toml, überschrieben von einem optionalen local.toml.

    Die Plattform-Tabelle wird flachgezogen: Nach dem Laden liegt der Block
    der aktuellen Plattform direkt unter ``platform``, damit kein Aufrufer
    ``sys.platform`` selbst abfragen muss.
    """
    with (CONFIG_DIR / "settings.toml").open("rb") as f:
        daten = tomllib.load(f)

    lokal = CONFIG_DIR / "local.toml"
    if lokal.exists():
        with lokal.open("rb") as f:
            daten = _deep_merge(daten, tomllib.load(f))

    plattformen = daten.pop("platform", {})
    if sys.platform not in plattformen:
        raise RuntimeError(
            f"Keine Plattformkonfiguration für {sys.platform!r}. "
            f"Bekannt: {sorted(plattformen)}. Ergänze sie in config/settings.toml."
        )
    daten["platform"] = plattformen[sys.platform]
    return daten


def arbeitsverzeichnis() -> Path:
    """Wo Quellvideos, Cache und Renderergebnisse liegen.

    Auf dem Windows-Desktop F: (620 GB frei), auf dem MacBook das Home —
    dort mit nur 256 GB gesamt und deshalb nur für Einzelvideos geeignet.
    """
    pfad = Path(einstellungen()["platform"]["work_dir"]).expanduser()
    pfad.mkdir(parents=True, exist_ok=True)
    return pfad


def encoder(preview: bool = False) -> str:
    plattform = einstellungen()["platform"]
    return plattform["preview_encoder" if preview else "encoder"]
