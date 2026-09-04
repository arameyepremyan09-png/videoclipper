"""Stage 13 — QC.

Gemessen wird die fertige Datei, nicht der Plan. Unterschreitet die gerenderte
Dauer die Tier-A-Schwelle, verliert der Clip seine Markierung.
"""

from __future__ import annotations

import json
import subprocess
from dataclasses import dataclass
from pathlib import Path

from .settings import einstellungen


@dataclass
class QCBefund:
    datei: Path
    dauer: float
    breite: int
    hoehe: int
    tier: str
    tier_korrigiert: bool
    hinweise: list[str]


def pruefe(datei: Path, tier: str) -> QCBefund:
    aus = subprocess.run(
        ["ffprobe", "-v", "error", "-print_format", "json",
         "-show_format", "-show_streams", str(datei)],
        capture_output=True, text=True, check=True).stdout
    daten = json.loads(aus)
    v = next(s for s in daten["streams"] if s["codec_type"] == "video")
    dauer = float(daten["format"]["duration"])

    e = einstellungen()
    schwelle = e["monetarisierung"]["tier_a_min_sekunden"]
    soll_b, soll_h = e["output"]["width"], e["output"]["height"]

    hinweise = []
    neu_tier, korrigiert = tier, False
    if tier == "A" and dauer < schwelle:
        neu_tier, korrigiert = "B", True
        hinweise.append(f"Dauer {dauer:.2f}s < {schwelle}s — Tier A entzogen")
    if (v["width"], v["height"]) != (soll_b, soll_h):
        hinweise.append(f"Aufloesung {v['width']}x{v['height']} statt {soll_b}x{soll_h}")
    if not any(s["codec_type"] == "audio" for s in daten["streams"]):
        hinweise.append("Keine Audiospur")

    return QCBefund(datei, dauer, v["width"], v["height"],
                    neu_tier, korrigiert, hinweise)
