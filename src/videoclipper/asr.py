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
import tempfile
import wave
from pathlib import Path

import numpy as np

#: Die Binaerdatei aus ``brew install whisper-cpp``.
WHISPER = "whisper-cli"

#: 16 kHz mono ist das Format, das whisper.cpp erwartet; alles andere lehnt es ab.
ABTASTRATE = 16000

#: Laenger wird kein Stueck: Whisper dekodiert 30-s-Fenster, und ein Stueck
#: darunter liegt in genau einem davon — ohne die Fensterfortschreibung, an der
#: die Zeitachse ueber eine Stunde wegdriftet (siehe ``transkribiere``).
STUECK_MAX = 28.0
#: Fruehestens hier wird nach der Pause gesucht; kuerzer kostet nur Aufrufe.
STUECK_MIN = 15.0
#: Ein Stueck, das nirgends lauter wird, geht nicht an Whisper. In digitaler
#: Stille (Twitchs DMCA-Stummschaltung) erfindet es sonst "Vielen Dank."
STILLE_DB = -60.0


def stuecke(x: np.ndarray, sr: int = ABTASTRATE) -> list[tuple[int, int]]:
    """Schnittgrenzen in Sprechpausen, als Sample-Indizes (von, bis).

    Je Stueck die leiseste 200-ms-Stelle zwischen ``STUECK_MIN`` und
    ``STUECK_MAX`` hinter der vorigen Grenze. 200 ms statt eines einzelnen
    10-ms-Fensters: Eine Silbenluecke ist kurz, eine Atempause nicht. Endet ein
    Stueck mitten im Wort, legt Whisper die letzten Woerter alle auf das
    Stueckende — gemessen an 24-s-Stuecken, die blind geschnitten waren:
    vierzehn Woerter auf 23.99 s.

    ``x`` als Float in [-1, 1]. Stille Stuecke fehlen in der Rueckgabe.
    """
    hop = sr // 100
    n = len(x) // hop
    if n == 0:
        return []
    rms = np.sqrt((x[:n * hop].astype(np.float64).reshape(n, hop) ** 2).mean(axis=1))
    glatt = np.convolve(rms, np.ones(20) / 20, mode="same")
    grenzen = [0]
    while n - grenzen[-1] > STUECK_MAX * 100:
        a = grenzen[-1] + int(STUECK_MIN * 100)
        b = grenzen[-1] + int(STUECK_MAX * 100)
        grenzen.append(a + int(np.argmin(glatt[a:b])))
    grenzen.append(n)
    schwelle = 10 ** (STILLE_DB / 20)
    return [(g0 * hop, g1 * hop) for g0, g1 in zip(grenzen, grenzen[1:])
            if rms[g0:g1].max() > schwelle]


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


#: So lange nach dem DTW-Zeitpunkt seines letzten Tokens endet ein Wort.
#: DTW markiert den Token, nicht sein Ende; ``lade_json3`` kuerzt ohnehin auf
#: den Beginn des naechsten Wortes, und ``snappe`` zieht ein Ende in der Pause
#: ueber den Pegel nach vorn. Zu spaet ist deshalb harmlos, zu frueh nicht.
NACHLAUF_MS = 250


def woerter_aus_tokens(roh: dict, anfang: int) -> tuple[list[dict], int]:
    """Woerter aus den DTW-Zeiten der Tokens (``-ojf``), in ms ab ``anfang``.

    Ein Wort beginnt am Segmentanfang oder mit einem Token mit fuehrendem
    Leerzeichen; Silben und Satzzeichen haengen sich an. Satzzeichen
    verschieben das Ende nicht — ihr DTW-Zeitpunkt liegt oft mitten in der
    Pause dahinter (gemessen: "bin" 189.17 s, der Punkt dazu 190.29 s).
    Rueckgabe: die Woerter und die Zahl der Tokens ohne DTW-Zeit.
    """
    worte, ohne = [], 0
    for seg in roh.get("transcription", []):
        wort, seg_worte = None, []
        for tok in seg.get("tokens", []):
            text = tok.get("text", "")
            if not text or text.startswith("[_"):       # [_BEG_], [_TT_...]
                continue
            t = tok.get("t_dtw", -1)
            if t is None or t < 0:
                ohne += 1
                t = tok.get("offsets", {}).get("from", 0) // 10
            ms = anfang + int(t) * 10                   # t_dtw in 10 ms
            if wort is None or text.startswith(" "):
                if wort is not None:
                    seg_worte.append(wort)
                wort = {"text": text, "ab": ms, "bis": ms + NACHLAUF_MS}
            else:
                wort["text"] += text
                if any(c.isalnum() for c in text):
                    wort["bis"] = ms + NACHLAUF_MS
        if wort is not None:
            seg_worte.append(wort)
        worte += _anmerkungen(seg_worte)
    return [w for w in worte if any(c.isalnum() for c in w["text"])], ohne


def _anmerkungen(worte: list[dict]) -> list[dict]:
    """Whispers Geraeuschangaben als Marker: "*Klatschen*" wird "[klatschen]",
    "* Musik *" wird "[musik]" — dieselbe Form wie YouTubes "[gelächter]".

    Gemessen am 2026-09-15: Bei TikTok-Ton ohne Sprache schreibt Whisper
    "*Klatschen*" mitten in den Text. Als Wort stuende es im Untertitel, und
    aus "* Musik *" bliebe "Musik" als gesprochenes Wort stehen; als Marker
    ueberspringt beides ``untertitel``.
    """
    out, offen = [], None
    for w in worte:
        t = w["text"].strip()
        if offen is None:
            if not t.startswith(("*", "(")):
                out.append(w)
                continue
            offen = dict(w, text=t)
        else:
            offen["text"] += " " + t
            offen["bis"] = w["bis"]
        if len(offen["text"]) > 1 and offen["text"].endswith(("*", ")")):
            innen = offen["text"].strip("*() ").lower()
            if innen:
                out.append(dict(offen, text=f" [{innen}]"))
            offen = None
    if offen is not None:
        innen = offen["text"].strip("*() ").lower()
        if innen:
            out.append(dict(offen, text=f" [{innen}]"))
    return out


def transkribiere(video: Path, modell: Path, ziel: Path,
                  sprache: str = "de", threads: int = 8,
                  dtw: str = "large.v3.turbo") -> Path:
    """Video -> ``<ziel>`` im json3-Format.

    Die Pipeline braucht Wortgrenzen — ``snappe`` schneidet daran, und
    ``untertitel.schneide`` bricht daran um. Sie kommen aus den DTW-Zeiten der
    Tokens (``-dtw``, ``woerter_aus_tokens``), nicht aus Whispers Segmentzeiten:
    Die lagen am 2026-09-15 auch in Stuecken unter 30 s bis zu 12 s daneben
    ("Ah, ich bin tot" bei 1110.9 s statt 1123.0 s, wo die Lautheit einsetzt),
    und am Stueckende stapelten sich die Woerter auf einer einzigen Zeit —
    1428 von 4647. Die DTW-Zeiten derselben Stellen folgen der Lautheit auf
    rund 0.2 s (Einsatz 1123.0, DTW 1123.4; Einsatz 190.4, DTW 190.6).
    Voraussetzung ist ``-nfa``: Mit Flash-Attention liefert whisper.cpp fuer
    jeden Token -1, ohne Fehlermeldung.

    ``-mc 0`` (kein Text der vorigen Fenster als Prompt) ist bei langem Material
    Pflicht. Gemessen am 2026-09-15 an einem 60-min-Twitch-VOD (dwitch_j9snk5q6):
    Mit Kontext blieb der Decoder nach Musik oder Stille in Schleifen haengen
    ("Warte." 60-mal, "Wallah." 29-mal) und schleppte sie ueber gesprochene
    Strecken weiter — Minute 15-21 und 50-59 hatten 4-11 Woerter je Minute,
    fast alle Wiederholungen, obwohl durchgehend geredet wird. Ohne Kontext ist
    jedes 30-s-Fenster unabhaengig; dieselben Stellen kamen vollstaendig und
    zusammenhaengend heraus.

    DIE DATEI WIRD IN STUECKEN TRANSKRIBIERT, nicht am Stueck. Am selben Video
    gemessen: Ueber die ganze Stunde in einem Lauf driftet die Zeitachse —
    "Ah, ich bin tot" stand bei 1110.0 s, gesprochen ist es bei 1123.0 s, und
    Woerter lagen mitten in gemessener Stille (1096-1099 s, 281-287 s). Die
    Abweichung schwankte zwischen 5 und 13 s. Fuer ein Transkript, an dem
    ``snappe`` Clipgrenzen und ``untertitel`` Cues ausrichten, ist das
    unbrauchbar. Ein Stueck unter 30 s liegt in genau einem Fenster, und seine
    Zeiten werden nur um den bekannten Stueckanfang verschoben. Geschnitten wird
    in Pausen (``stuecke``); alle Stuecke laufen in einem Aufruf, das Modell
    wird also einmal geladen.
    """
    wav = hole_audio(video, video.with_suffix(".16k.wav"))
    x = _samples(wav)
    grenzen = stuecke(x.astype(np.float32) / 32768)
    if not grenzen:
        raise RuntimeError(f"Nur Stille in {video.name}")

    worte, ohne = _whisper(x, grenzen, modell, sprache, threads, dtw)
    if not worte:
        raise RuntimeError(f"ASR lieferte keine Woerter fuer {video.name}")

    still = round(len(x) / ABTASTRATE - sum(b - a for a, b in grenzen) / ABTASTRATE)
    print(f"  {len(grenzen)} Stuecke, {still}s Stille uebersprungen, "
          f"{ohne} Tokens ohne DTW-Zeit")
    ziel.write_text(json.dumps(_nach_json3(worte), ensure_ascii=False),
                    encoding="utf-8")
    return ziel


def transkribiere_fenster(video: Path, modell: Path, von: float, bis: float,
                          sprache: str = "de", threads: int = 8,
                          dtw: str = "large.v3.turbo") -> list[dict]:
    """Nur [von, bis) neu transkribieren; Woerter in ms der ganzen Datei.

    WOZU: Whisper dekodiert nicht deterministisch und laesst stellenweise Rede
    aus. Gemessen am 2026-09-15: Im Stundenlauf fehlte bei 1277-1288 s das
    ganze Setup eines Clips ("Kein Zitat trifft mich ..."), in einem frueheren
    Lauf ueber dieselbe Stelle war es da. Ein zweiter Lauf ueber genau das
    Clipfenster, in eigenen Stuecken ab dessen Anfang, kostet Sekunden statt
    elf Minuten. Eingesetzt wird er von ``werkzeuge/asr_fenster.py`` und nicht
    automatisch: Welche Fassung stimmt, entscheidet der Vergleich.
    """
    x = _samples(hole_audio(video, video.with_suffix(".16k.wav")))
    a0, b0 = int(von * ABTASTRATE), int(bis * ABTASTRATE)
    grenzen = [(a0 + a, a0 + b)
               for a, b in stuecke(x[a0:b0].astype(np.float32) / 32768)]
    worte, _ = _whisper(x, grenzen, modell, sprache, threads, dtw)
    return worte


def _samples(wav: Path) -> np.ndarray:
    with wave.open(str(wav)) as w:
        return np.frombuffer(w.readframes(w.getnframes()), np.int16)


def _whisper(x: np.ndarray, grenzen: list[tuple[int, int]], modell: Path,
             sprache: str, threads: int, dtw: str) -> tuple[list[dict], int]:
    """Alle Stuecke in einem whisper.cpp-Aufruf; Woerter in ms der ganzen Datei."""
    werkzeug = _werkzeug()
    if not modell.exists():
        raise FileNotFoundError(f"Whisper-Modell fehlt: {modell}")

    worte, ohne = [], 0
    with tempfile.TemporaryDirectory() as tmp:
        dateien = []
        for i, (a, b) in enumerate(grenzen):
            pfad = Path(tmp) / f"s{i:04d}.wav"
            with wave.open(str(pfad), "wb") as w:
                w.setnchannels(1)
                w.setsampwidth(2)
                w.setframerate(ABTASTRATE)
                w.writeframes(x[a:b].tobytes())
            dateien.append(pfad)

        befehl = [werkzeug, "-m", str(modell), "-l", sprache, "-t", str(threads),
                  "-mc", "0",               # kein Kontext: sonst Schleifen, siehe oben
                  "-nfa", "-dtw", dtw,      # DTW je Token; mit Flash-Attention kommt -1
                  "-ojf", "-np", "-nt"]     # je Eingang <eingang>.json, mit Tokens
        for pfad in dateien:
            befehl += ["-f", str(pfad)]
        subprocess.run(befehl, check=True, capture_output=True)

        for pfad, (a, _) in zip(dateien, grenzen):
            roh = json.loads(Path(f"{pfad}.json").read_text(encoding="utf-8"))
            neu, n = woerter_aus_tokens(roh, a * 1000 // ABTASTRATE)
            worte += neu
            ohne += n
    return worte, ohne
