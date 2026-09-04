"""Stage 03 — Transkript.

YouTube liefert ``de-orig`` im ``json3``-Format mit Offsets pro Wort. Das ist die
Primaerquelle; eigene ASR waere nur Fallback.

Zur Rolling-Window-Struktur: Ereignisse mit ``aAppend`` tragen in diesem Material
ausschliesslich Zeilenumbrueche, keinen Text. Sie werden verworfen. Das erste
Ereignis definiert nur das Fenster und hat keine ``segs``.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path

# YouTube annotiert Audio-Ereignisse in eckigen Klammern.
MARKER = re.compile(r"\[([^\]]{1,30})\]")


@dataclass(frozen=True)
class Wort:
    text: str
    start: float          # Sekunden ab Videobeginn
    ende: float

    @property
    def ist_marker(self) -> bool:
        return bool(MARKER.fullmatch(self.text.strip()))


@dataclass(frozen=True)
class Transkript:
    video_id: str
    sprache: str
    woerter: tuple[Wort, ...]

    @property
    def dauer(self) -> float:
        return self.woerter[-1].ende if self.woerter else 0.0

    def text_zwischen(self, start: float, ende: float) -> str:
        """Wortlaut im Zeitfenster — die Umgebung, die die Selektion sieht."""
        teile = [w.text for w in self.woerter if start <= w.start < ende]
        return " ".join(t.strip() for t in teile if t.strip())

    def marker(self, art: str | None = None) -> list[Wort]:
        out = [w for w in self.woerter if w.ist_marker]
        if art is not None:
            out = [w for w in out if art in w.text.lower()]
        return out


def lade_json3(pfad: Path, video_id: str, sprache: str = "de") -> Transkript:
    daten = json.loads(pfad.read_text(encoding="utf-8"))
    woerter: list[Wort] = []

    for ereignis in daten.get("events", []):
        if ereignis.get("aAppend"):          # nur Zeilenumbrueche
            continue
        segs = ereignis.get("segs")
        if not segs:                          # Fensterdefinition
            continue
        basis = ereignis["tStartMs"]
        dauer = ereignis.get("dDurationMs", 0)
        for i, seg in enumerate(segs):
            text = seg.get("utf8", "")
            if not text.strip():
                continue
            start = (basis + seg.get("tOffsetMs", 0)) / 1000.0
            # Ende ist der Beginn des naechsten Wortes, sonst das Ereignisende.
            naechster = next(
                (s for s in segs[i + 1:] if s.get("utf8", "").strip()), None
            )
            if naechster is not None:
                ende = (basis + naechster.get("tOffsetMs", 0)) / 1000.0
            else:
                ende = (basis + dauer) / 1000.0
            woerter.append(Wort(text, start, max(ende, start + 0.05)))

    woerter.sort(key=lambda w: w.start)
    return Transkript(video_id, sprache, tuple(woerter))
