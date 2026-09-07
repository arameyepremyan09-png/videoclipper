"""Stage 13 — QC.

Gemessen wird die fertige Datei, nicht der Plan. Unterschreitet die gerenderte
Dauer die Tier-A-Schwelle, verliert der Clip seine Markierung.

Dazu kommt eine Pruefung *vor* dem Rendern: ``pflichtelemente``. Untertitel und
Follow-Aufforderung gehoeren in jeden Clip, und ein fehlendes Overlay ist im
fertigen Video nicht messbar — die Datei hat dann trotzdem die richtige Dauer,
die richtige Aufloesung und eine Tonspur. Genau solche Fehler faellt sonst erst
im Feed auf, so wie die Fremdclips im BMW-Vlog: erst im Standbild zu sehen,
nicht im QC.
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


# ---------------------------------------------------------------------------
# Vor dem Rendern
# ---------------------------------------------------------------------------

# Beide Overlays sind Hausregel, nicht Geschmack: Shorts laufen stumm an, und
# ``konversion`` (Follows pro View) ist laut scoring.yaml das Ziel des Accounts.
PFLICHT = {
    "untertitel": "Untertitel",
    "follow_hinweis": "Follow-Aufforderung",
}


def pflichtelemente(tmpl: dict) -> list[str]:
    """Traegt das Template beide Pflicht-Overlays? Gibt Fehlertexte zurueck.

    Abschalten ist erlaubt, aber nur mit ``grund`` im Template. ``aktiv: false``
    ohne Begruendung ist ein Fehler und keine Einstellung — sonst verschwindet
    ein Overlay durch eine unbemerkte Aenderung und niemand weiss mehr, ob das
    Absicht war.
    """
    fehler = []
    for schluessel, name in PFLICHT.items():
        conf = tmpl.get(schluessel)
        if conf is None:
            fehler.append(f"{tmpl['name']}: {name} fehlt "
                          f"(config/overlays.yaml wird nicht geerbt?)")
        elif not conf.get("aktiv", True) and not str(conf.get("grund", "")).strip():
            fehler.append(f"{tmpl['name']}: {name} steht auf 'aktiv: false' "
                          f"ohne 'grund' — Abschalten braucht eine Begruendung")
    return fehler


def overlays_vorhanden(r, tmpl: dict) -> list[str]:
    """Ist im aufgeloesten Plan tatsaechlich beides gelandet?

    Untertitel koennen legitim leer sein — wenn im Clipfenster nichts gesprochen
    wird, gibt es nichts zu setzen. Das ist ein Hinweis, kein Fehler: bei
    markerlosem Material ist genau das die Stelle, an der eine Sichtkontrolle
    faellig ist.

    ``r`` ist entweder ein ``editplan.Aufgeloest`` oder ein
    ``countdown.Aufgeloest``. Das zweite kennt ``untertitel`` gar nicht, weil
    das Format keine hat — deshalb ``getattr`` statt Attributzugriff. Ohne das
    haengt die Pruefung daran, dass die Bedingung davor kurzschliesst.
    """
    hinweise = []
    if (tmpl.get("untertitel") or {}).get("aktiv", True) \
            and not getattr(r, "untertitel", None):
        hinweise.append("Keine Untertitel — im Clipfenster steht kein Wort "
                        "im Transkript. Bitte den Clip ansehen.")
    if (tmpl.get("follow_hinweis") or {}).get("aktiv", True) \
            and not getattr(r, "follow", None):
        hinweise.append("Keine Follow-Aufforderung im Clip")
    return hinweise
