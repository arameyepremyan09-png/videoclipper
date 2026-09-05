"""Ablage fuer Veroeffentlichungen, Messwerte und Experimente.

JSONL, nicht SQLite. Der Blueprint sieht SQLite fuer den Jobstate vor — das
bleibt so. Diese Daten sind aber etwas anderes: Sie wandern mit dem Repo auf
beide Rechner, sind Kilobytes gross und sollen im Diff lesbar sein. Eine
Binaerdatei in Git waere auf zwei Maschinen ein Merge-Konflikt pro Tag.

Drei Dateien, alle append-only ausser `posts` (dort ersetzt eine spaetere
Zeile eine fruehere mit derselben ``post_id``):

    data/performance/posts.jsonl        was wann wo veroeffentlicht wurde
    data/performance/metrics.jsonl      Messschnappschuesse, mehrere pro Post
    data/performance/experiments.jsonl  A/B-Register
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator

ROOT = Path(__file__).resolve().parents[2]
ABLAGE = ROOT / "data" / "performance"

POSTS = "posts.jsonl"
METRIKEN = "metrics.jsonl"
EXPERIMENTE = "experiments.jsonl"

# Metriken, die keine Plattform oeffentlich herausgibt. Sie kommen aus dem
# Creator-Center und werden von Hand oder per CSV-Import nachgetragen.
NUR_INTERN = ("avg_watchtime", "completion_rate", "follows", "profilaufrufe")


def _pfad(datei: str) -> Path:
    ABLAGE.mkdir(parents=True, exist_ok=True)
    return ABLAGE / datei


def jetzt() -> str:
    """Zeitstempel in lokaler Zone mit Offset — ohne Offset ist er wertlos,
    weil die Postzeit selbst eine der bewerteten Groessen ist."""
    return datetime.now().astimezone().isoformat(timespec="seconds")


def lies(datei: str) -> list[dict[str, Any]]:
    p = _pfad(datei)
    if not p.exists():
        return []
    zeilen = []
    for nr, zeile in enumerate(p.read_text(encoding="utf-8").splitlines(), 1):
        zeile = zeile.strip()
        if not zeile:
            continue
        try:
            zeilen.append(json.loads(zeile))
        except json.JSONDecodeError as e:
            raise ValueError(f"{p.name} Zeile {nr}: {e}") from e
    return zeilen


def haenge_an(datei: str, satz: dict[str, Any]) -> None:
    with _pfad(datei).open("a", encoding="utf-8") as f:
        f.write(json.dumps(satz, ensure_ascii=False, sort_keys=True) + "\n")


def schreibe_neu(datei: str, saetze: list[dict[str, Any]]) -> None:
    with _pfad(datei).open("w", encoding="utf-8") as f:
        for s in saetze:
            f.write(json.dumps(s, ensure_ascii=False, sort_keys=True) + "\n")


# ---------------------------------------------------------------------------
# Posts
# ---------------------------------------------------------------------------

def posts() -> list[dict[str, Any]]:
    """Alle Veroeffentlichungen, spaetere Zeile gewinnt bei gleicher post_id."""
    nach_id: dict[str, dict] = {}
    for p in lies(POSTS):
        nach_id[p["post_id"]] = p
    return sorted(nach_id.values(), key=lambda p: p.get("veroeffentlicht") or "")


def post(post_id: str) -> dict[str, Any] | None:
    for p in posts():
        if p["post_id"] == post_id:
            return p
    return None


def speichere_post(satz: dict[str, Any]) -> None:
    haenge_an(POSTS, satz)


# ---------------------------------------------------------------------------
# Messwerte
# ---------------------------------------------------------------------------

def messungen(post_id: str | None = None) -> list[dict[str, Any]]:
    alle = lies(METRIKEN)
    if post_id is not None:
        alle = [m for m in alle if m["post_id"] == post_id]
    return sorted(alle, key=lambda m: m.get("alter_stunden", 0.0))


@dataclass
class Treffer:
    """Ein Messschnappschuss samt seiner Abweichung vom Wunschfenster."""
    messung: dict[str, Any]
    fenster: float
    abweichung_stunden: float

    @property
    def brauchbar(self) -> bool:
        """Eine Messung bei 6 h taugt nicht als 24-h-Wert. Toleranz ist
        proportional zum Fenster, weil 2 h Abweichung bei einem 1-h-Fenster
        alles bedeutet und bei einem 168-h-Fenster nichts."""
        return self.abweichung_stunden <= max(1.0, 0.5 * self.fenster)


def messung_im_fenster(post_id: str, fenster: float) -> Treffer | None:
    """Der Schnappschuss, der dem Fenster am naechsten liegt.

    Verglichen wird immer nur innerhalb desselben Fensters. Sonst gewinnt der
    aeltere Post automatisch, weil er laenger Zeit hatte Views zu sammeln —
    der haeufigste Fehler beim Vergleich von Social-Metriken.
    """
    kandidaten = messungen(post_id)
    if not kandidaten:
        return None
    beste = min(kandidaten, key=lambda m: abs(m.get("alter_stunden", 0.0) - fenster))
    return Treffer(beste, fenster, abs(beste.get("alter_stunden", 0.0) - fenster))


def speichere_messung(satz: dict[str, Any]) -> None:
    haenge_an(METRIKEN, satz)


# ---------------------------------------------------------------------------
# Experimente
# ---------------------------------------------------------------------------

def experimente() -> list[dict[str, Any]]:
    nach_id: dict[str, dict] = {}
    for e in lies(EXPERIMENTE):
        nach_id[e["experiment_id"]] = e
    return list(nach_id.values())


def experiment(experiment_id: str) -> dict[str, Any] | None:
    for e in experimente():
        if e["experiment_id"] == experiment_id:
            return e
    return None


def speichere_experiment(satz: dict[str, Any]) -> None:
    haenge_an(EXPERIMENTE, satz)
