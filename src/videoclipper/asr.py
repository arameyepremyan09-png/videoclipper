"""Stage 03b — eigene ASR, wenn YouTube kein brauchbares Transkript hat.

WOZU: ``transcript.py`` nennt die eigene ASR seit jeher "nur Fallback", und in
acht vermessenen Videos wurde sie nie gebraucht — ``de-orig`` war immer da.
Bei JtWRKErMIGc ist sie es nicht, und der Grund ist lehrreich genug fuer eine
eigene Notiz:

**Auf einem Reaction-Video waehlt YouTubes ASR die Sprache des reagierten
Videos, nicht die des Kanals.** Bei einer Reaktion auf eine englische Show
gibt es deshalb gar kein ``de-orig``; angeboten werden ``en-orig`` (das
Original) und ``de`` (eine Maschinenuebersetzung davon). Beide enthalten den
Dialog der Show — der deutsche Kommentar des Creators, also das eigentliche
Produkt, steht in keinem von beiden. Gemessen an JtWRKErMIGc: 3528 Woerter
``en-orig``, davon Stichproben bei 120 s, 400 s, 800 s und 1200 s **komplett**
aus der Show, kein Wort Deutsch.

Ein Transkript, das den Kommentar nicht enthaelt, ist hier wertlos: Stage 06
sucht die lustigen Stellen durch Lesen, und die Untertitel sind Pflicht in
jedem Clip.

WIE: whisper.cpp als Subprozess, wie FFmpeg auch. Kein Python-Binding, keine
zusaetzliche Abhaengigkeit — das Homebrew-Paket ``whisper-cpp`` bringt Metal
mit und laeuft auf dem M4 deutlich schneller als CPU.

DAS ERGEBNIS WIRD ALS ``json3`` GESCHRIEBEN, nicht als eigenes Format. Damit
liest ``lade_json3`` es unveraendert, und der Rest der Pipeline merkt nicht,
woher das Transkript kommt — Stage 03 bleibt eine reine Funktion auf eine
Datei. Ein eigenes Format haette jede spaetere Stage angefasst.

WAS FEHLT: Marker. YouTube schreibt ``[gelächter]`` und ``[schreien]`` in den
Text, Whisper tut das nicht. Bei ASR-Material ist ``lachmarker`` im Profil
deshalb zwingend 0 — das ist derselbe Fall wie bei den drei markerlosen
YouTube-Transkripten, und die Auswahl passiert dann in Stage 06 durch Lesen.
"""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

#: Die Binaerdatei aus ``brew install whisper-cpp``.
WHISPER = "whisper-cli"

#: 16 kHz mono ist das Format, das whisper.cpp erwartet; alles andere lehnt es ab.
ABTASTRATE = 16000


def _werkzeug() -> str:
    pfad = shutil.which(WHISPER)
    if not pfad:
        raise RuntimeError(
            f"{WHISPER} nicht gefunden. Auf macOS: brew install whisper-cpp. "
            "Das Modell liegt nicht im Repo — siehe README."
        )
    return pfad


def hole_audio(video: Path, ziel: Path) -> Path:
    """Tonspur als 16-kHz-Mono-WAV. Idempotent: vorhandene Datei bleibt liegen."""
    if ziel.exists() and ziel.stat().st_size > 0:
        return ziel
    ziel.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(
        ["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-i", str(video),
         "-vn", "-ac", "1", "-ar", str(ABTASTRATE), "-c:a", "pcm_s16le", str(ziel)],
        check=True)
    return ziel


def _nach_json3(worte: list[dict]) -> dict:
    """whisper.cpp-Segmente in die json3-Struktur, die ``lade_json3`` liest.

    Ein Ereignis je Wort. Das ist mehr Ereignisse, als YouTube schreibt, aber
    ``lade_json3`` kuerzt ohnehin jedes Wortende auf den Beginn des naechsten —
    die Rolling-Window-Falle aus dem Original kann hier also gar nicht
    entstehen.
    """
    events = []
    for w in worte:
        ab, bis = w["ab"], w["bis"]
        events.append({
            "tStartMs": ab,
            "dDurationMs": max(bis - ab, 50),
            "segs": [{"utf8": w["text"], "tOffsetMs": 0}],
        })
    return {"wireMagic": "pb3", "events": events}


def transkribiere(video: Path, modell: Path, ziel: Path,
                  sprache: str = "de", threads: int = 8) -> Path:
    """Video -> ``<ziel>`` im json3-Format.

    ``-ml 1 -sow`` zerlegt in einzelne Woerter statt in Saetze: Die Pipeline
    braucht Wortgrenzen — ``snappe`` schneidet daran, und ``untertitel.schneide``
    bricht daran um. Ein Transkript aus Satzsegmenten waere fuer beide zu grob.
    """
    werkzeug = _werkzeug()
    if not modell.exists():
        raise FileNotFoundError(f"Whisper-Modell fehlt: {modell}")

    wav = hole_audio(video, video.with_suffix(".16k.wav"))
    rumpf = ziel.with_suffix("")            # whisper haengt .json selbst an

    subprocess.run(
        [werkzeug, "-m", str(modell), "-f", str(wav),
         "-l", sprache, "-t", str(threads),
         "-ml", "1", "-sow",                # ein Wort je Segment
         "-oj", "-of", str(rumpf), "-np", "-nt"],
        check=True)

    roh = json.loads(Path(f"{rumpf}.json").read_text(encoding="utf-8"))
    worte = []
    for eintrag in roh.get("transcription", []):
        text = eintrag.get("text", "")
        if not text.strip():
            continue
        o = eintrag.get("offsets", {})
        worte.append({"text": text, "ab": int(o.get("from", 0)),
                      "bis": int(o.get("to", 0))})

    if not worte:
        raise RuntimeError(f"ASR lieferte keine Woerter fuer {video.name}")

    ziel.write_text(json.dumps(_nach_json3(worte), ensure_ascii=False),
                    encoding="utf-8")
    Path(f"{rumpf}.json").unlink(missing_ok=True)
    return ziel
