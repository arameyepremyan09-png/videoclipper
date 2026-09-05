"""Stage 17a — Messwerte einsammeln.

Die einzige Stage neben dem Ingest, die ins Netz greift, und damit die zweite
fragile Stelle der Pipeline. Deshalb strikt getrennt vom Rechnen: Dieses Modul
holt Zahlen und legt sie ab, es bewertet nichts.

yt-dlp laeuft als Subprozess, nicht als Import — wie FFmpeg. Das Binary wird
ohnehin fuer den Ingest gebraucht, und ein Extractor-Bruch reisst so nur diese
Stage, nicht den Interpreter.

Gemessen am 2026-09-05, und der Befund entscheidet ueber den Zuschnitt:

    TikTok     views, likes, kommentare, shares, saves — ohne Login, vollstaendig
    YouTube    views immer, likes meist; shares und saves nie
    Instagram  gar nichts, Login-Wand, Extractor als broken markiert

Watchtime, Completion-Rate und Follows gibt keine der drei oeffentlich heraus.
Sie sind der Teil, den der Mensch nachtragen muss — und ausgerechnet die
schwerste Achse des Scores haengt daran.
"""

from __future__ import annotations

import json
import subprocess
from dataclasses import dataclass
from datetime import datetime, timezone
from functools import cache
from pathlib import Path
from typing import Any

import yaml

from . import store

ROOT = Path(__file__).resolve().parents[2]

# Kein Abruf laeuft laenger. Ein haengender Extractor darf den taeglichen
# Batch nicht blockieren.
ZEITLIMIT = 180


@cache
def konten() -> dict[str, Any]:
    with (ROOT / "config" / "konten.yaml").open("rb") as f:
        return yaml.safe_load(f)


class AbrufFehler(RuntimeError):
    pass


def _ytdlp(*args: str) -> dict[str, Any]:
    befehl = ["yt-dlp", "--ignore-config", "--no-warnings", *args]
    try:
        p = subprocess.run(befehl, capture_output=True, text=True,
                           timeout=ZEITLIMIT)
    except FileNotFoundError as e:
        raise AbrufFehler("yt-dlp nicht gefunden — siehe README") from e
    except subprocess.TimeoutExpired as e:
        raise AbrufFehler(f"yt-dlp nach {ZEITLIMIT}s abgebrochen") from e
    if p.returncode != 0 or not p.stdout.strip():
        fehler = (p.stderr or "").strip().splitlines()
        raise AbrufFehler(fehler[-1] if fehler else f"Rueckgabewert {p.returncode}")
    return json.loads(p.stdout)


def _alter_stunden(veroeffentlicht: str, gemessen: str) -> float:
    a = datetime.fromisoformat(veroeffentlicht)
    b = datetime.fromisoformat(gemessen)
    return round((b - a).total_seconds() / 3600.0, 2)


# ---------------------------------------------------------------------------
# Plattformen
# ---------------------------------------------------------------------------

@dataclass
class Rohpost:
    """Was eine Plattform ueber einen Post hergibt, vor jeder Bewertung."""
    plattform: str
    extern_id: str
    url: str
    titel: str
    dauer: float | None
    veroeffentlicht: str | None
    zahlen: dict[str, int | None]


def _tiktok(grenze: int) -> list[Rohpost]:
    daten = _ytdlp("--flat-playlist", "-J", "--playlist-end", str(grenze),
                   konten()["tiktok"]["url"])
    posts = []
    for e in daten.get("entries", []):
        ts = e.get("timestamp")
        posts.append(Rohpost(
            "tiktok", str(e["id"]), e.get("url", ""), e.get("title") or "",
            e.get("duration"),
            datetime.fromtimestamp(ts).astimezone().isoformat(timespec="seconds")
            if ts else None,
            {"views": e.get("view_count"), "likes": e.get("like_count"),
             "kommentare": e.get("comment_count"),
             # repost_count ist TikToks Name fuer Shares.
             "shares": e.get("repost_count"), "saves": e.get("save_count")},
        ))
    return posts


def _youtube(grenze: int) -> list[Rohpost]:
    # Die flache Liste liefert Views, aber keine Likes. Bei einem kleinen Kanal
    # ist ein Einzelabruf pro Video vertretbar; bei einem grossen waere er es
    # nicht, deshalb haengt er an `grenze`.
    liste = _ytdlp("--flat-playlist", "-J", "--playlist-end", str(grenze),
                   konten()["youtube"]["url"])
    posts = []
    for e in liste.get("entries", []):
        url = e.get("url") or f"https://www.youtube.com/watch?v={e['id']}"
        try:
            v = _ytdlp("-J", "--skip-download", url)
        except AbrufFehler:
            v = {}                      # Einzelabruf darf die Liste nicht reissen
        ts = v.get("timestamp")
        posts.append(Rohpost(
            "youtube", str(e["id"]), url, v.get("title") or e.get("title") or "",
            v.get("duration"),
            datetime.fromtimestamp(ts).astimezone().isoformat(timespec="seconds")
            if ts else None,
            {"views": v.get("view_count", e.get("view_count")),
             "likes": v.get("like_count"), "kommentare": v.get("comment_count"),
             "shares": None, "saves": None},
        ))
    return posts


HOLER = {"tiktok": _tiktok, "youtube": _youtube}


# ---------------------------------------------------------------------------
# Einsammeln
# ---------------------------------------------------------------------------

@dataclass
class Bericht:
    neu: int = 0
    gemessen: int = 0
    uebersprungen: list[str] = None
    fehler: list[str] = None

    def __post_init__(self):
        self.uebersprungen = self.uebersprungen or []
        self.fehler = self.fehler or []


def sammle(plattformen: list[str] | None = None, grenze: int = 60) -> Bericht:
    """Abrufen, unbekannte Posts anlegen, Messschnappschuss anhaengen.

    Posts, die nie durch die Pipeline liefen, werden hier mit ``clip_id: null``
    angelegt. Das ist Absicht: Die Historie eines Accounts ist auch dann die
    beste verfuegbare Grundlage, wenn sie von Hand entstanden ist.
    """
    bericht = Bericht()
    bekannt = {p["post_id"] for p in store.posts()}
    gemessen_am = store.jetzt()

    # Standard ist jede konfigurierte Plattform, nicht jede abrufbare —
    # sonst faellt Instagram still heraus statt gemeldet zu werden.
    for plattform in (plattformen or list(konten())):
        holer = HOLER.get(plattform)
        if holer is None:
            bericht.uebersprungen.append(
                f"{plattform}: kein automatischer Abruf "
                f"({'Login-Wand' if plattform == 'instagram' else 'nicht unterstuetzt'})"
                " — `clip trage-nach` benutzen")
            continue
        try:
            roh = holer(grenze)
        except AbrufFehler as e:
            bericht.fehler.append(f"{plattform}: {e}")
            continue

        for r in roh:
            post_id = f"{r.plattform}_{r.extern_id}"
            if post_id not in bekannt:
                store.speichere_post({
                    "post_id": post_id,
                    "clip_id": None,
                    "plattform": r.plattform,
                    "extern_id": r.extern_id,
                    "url": r.url,
                    "titel": r.titel,
                    "dauer": r.dauer,
                    "veroeffentlicht": r.veroeffentlicht,
                    "experiment": None,
                    "variante": None,
                    "prognose": None,
                    "erfasst": gemessen_am,
                    "herkunft": "sammler",
                })
                bekannt.add(post_id)
                bericht.neu += 1

            satz = {"post_id": post_id, "gemessen": gemessen_am,
                    "quelle": "yt-dlp", **r.zahlen}
            if r.veroeffentlicht:
                satz["alter_stunden"] = _alter_stunden(r.veroeffentlicht, gemessen_am)
            store.speichere_messung(satz)
            bericht.gemessen += 1

    return bericht


def trage_nach(post_id: str, werte: dict[str, float], alter_stunden: float | None = None
               ) -> dict[str, Any]:
    """Creator-Center-Werte von Hand ergaenzen.

    Sie kommen als eigener Schnappschuss, nicht als Korrektur des automatischen.
    So bleibt sichtbar, welche Zahl gemessen und welche abgetippt wurde.
    """
    p = store.post(post_id)
    if p is None:
        raise ValueError(f"Unbekannter Post: {post_id}")

    gemessen = store.jetzt()
    satz: dict[str, Any] = {"post_id": post_id, "gemessen": gemessen,
                            "quelle": "manuell"}
    satz.update({k: v for k, v in werte.items() if v is not None})

    if alter_stunden is not None:
        satz["alter_stunden"] = alter_stunden
    elif p.get("veroeffentlicht"):
        satz["alter_stunden"] = _alter_stunden(p["veroeffentlicht"], gemessen)

    # Completion aus Watchtime und Dauer, wenn nur eines der beiden kam.
    if satz.get("avg_watchtime") and p.get("dauer") and "completion_rate" not in satz:
        satz["completion_rate"] = round(satz["avg_watchtime"] / p["dauer"], 4)

    store.speichere_messung(satz)
    return satz
