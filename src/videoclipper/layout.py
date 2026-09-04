"""Stage 09 — Layout.

Materialprofil (Geometrie der Quelle) + Template (Zielkomposition) + erkannter
Modus ergeben konkrete Rechtecke. Rein deklarativ: Der Renderer bekommt Zahlen,
keine Entscheidungen.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parents[2]


def _lade(ordner: str, name: str) -> dict[str, Any]:
    for pfad in (ROOT / "config" / ordner).glob("*.yaml"):
        daten = yaml.safe_load(pfad.read_text(encoding="utf-8"))
        if daten.get("name") == name:
            return daten
    raise FileNotFoundError(f"{ordner}/{name} nicht gefunden")


def profil(name: str) -> dict[str, Any]:
    return _lade("profiles", name)


def template(name: str) -> dict[str, Any]:
    return _lade("templates", name)


def template_fuer(profil_name: str, modus: str) -> dict[str, Any]:
    """Das Template, das zu diesem Profil und diesem Modus gehoert."""
    for pfad in (ROOT / "config" / "templates").glob("*.yaml"):
        daten = yaml.safe_load(pfad.read_text(encoding="utf-8"))
        if profil_name in (daten.get("default_fuer") or []) \
                and daten.get("gilt_fuer_modus") == modus:
            return daten
    raise FileNotFoundError(f"Kein Template fuer {profil_name}/{modus}")


def panels(prof: dict, tmpl: dict, modus: str) -> list[dict]:
    """Loest Template-Panels gegen die Zonen des Modus auf.

    Ergebnis pro Panel: Quellrechteck (src), Zielrechteck (dst), Passung und
    optional der horizontale Fokus, um den beschnitten wird.
    """
    zonen = prof["modi"][modus]["zonen"]
    cb, ch = tmpl["canvas"]

    # In yuv420p muss jede Panelhoehe gerade sein — sonst rundet der Scaler
    # still ab und die Buehne wird ein paar Pixel zu kurz. Das faellt sonst
    # erst im QC der fertigen Datei auf.
    summe = 0
    for p in tmpl["panels"]:
        _, _, pw, ph = p["ziel"]
        if pw % 2 or ph % 2:
            raise ValueError(
                f"{tmpl['name']}: Panel {p['quelle']} hat ungerade Masse {pw}x{ph}")
        summe += ph
    if summe != ch:
        raise ValueError(
            f"{tmpl['name']}: Panelhoehen summieren zu {summe}, Canvas ist {ch}")

    out = []
    for p in tmpl["panels"]:
        zone = zonen[p["quelle"]]
        out.append({
            "name": p["quelle"],
            "src": list(zone["box"]),
            "dst": list(p["ziel"]),
            "passung": p.get("passung", "fuellen"),
            "fokus_x": zone.get("fokus_x"),
        })
    return out
