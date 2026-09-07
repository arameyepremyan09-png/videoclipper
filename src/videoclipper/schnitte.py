"""Stage 04b — Bildschnitte in der Quelle.

WOZU: Eine Clipgrenze darf nicht ueber einem harten Bildwechsel liegen, und
erst recht darf keiner *mitten* im Clip stehen. Sonst springt das Bild, und im
QC der fertigen Datei ist das nicht mehr nachweisbar — Dauer, Aufloesung und
Tonspur stimmen ja. CLAUDE.md notiert denselben Fehler schon fuer den
BMW-Vlog: Zwei Clipgrenzen lagen in eingeblendeten Fremdclips, und es fiel
erst im Standbild des fertigen Clips auf.

Bei OME.TV-Material ist der Fall die Regel, nicht die Ausnahme: Zwischen zwei
Gespraechspartnern steht die Suchkarte des Kanals. Ein Clip, der darueber
laeuft, zeigt mitten im Satz ein fremdes Gesicht.

ABGRENZUNG ZU ``signals.ModusSignatur``: Die Signatur beantwortet "welches
Layout liegt hier vor" und braucht dafuer eine gemessene Kante oder Flaeche,
also Materialwissen. Hier geht es um "hat sich das Bild schlagartig geaendert"
— das ist materialunabhaengig und braucht kein Profil.

WARUM NICHT EINFACH EIN SCHWELLWERT auf den Bildabstand: Handkamera. Im
Hausrundgang von utB7GTrmLYY (648-834 s) liegt der Abstand von Bild zu Bild
dauerhaft ueber jedem Wert, den ein Schnitt anderswo erreicht — ein fester
Schwellwert meldet dort hunderte Schnitte und ist unbrauchbar. Gemessen wird
deshalb gegen den *lokalen* Median: Ein Schnitt ist ein Ausreisser in seiner
eigenen Umgebung, nicht im ganzen Video.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import numpy as np

# Abtastraster. 0.25 s ist fein genug fuer eine Clipgrenze (bei 30 fps sind das
# gut sieben Bilder) und grob genug, dass ein 840-s-Video in Sekunden durchlaeuft.
SCHRITT = 0.25
BREITE, HOEHE = 48, 40


def _fps(video: Path) -> float:
    roh = subprocess.run(
        ["ffprobe", "-v", "error", "-select_streams", "v:0",
         "-show_entries", "stream=r_frame_rate", "-of", "csv=p=0", str(video)],
        check=True, capture_output=True, text=True).stdout.strip()
    zaehler, _, nenner = roh.partition("/")
    return float(zaehler) / float(nenner or 1)


def abtasten(video: Path, schritt: float = SCHRITT,
             box: tuple[int, int, int, int] | None = None
             ) -> tuple[np.ndarray, np.ndarray]:
    """Kleine Graubilder im festen Zeitraster. Gibt (Zeiten, Bilder) zurueck.

    Abgetastet wird ueber echte Bildnummern statt ueber den ``fps``-Filter —
    der laeuft gegen die echte Zeitachse weg (siehe CLAUDE.md). ``format=gray``
    steht vor dem Crop, weil ``crop`` ungerade Kantenmasse sonst still abrundet.
    """
    k = max(1, round(_fps(video) * schritt))
    kette = ["format=gray"]
    if box:
        x, y, w, h = box
        kette.append(f"crop={w}:{h}:{x}:{y}")
    kette += [f"scale={BREITE}:{HOEHE}", f"select='not(mod(n\\,{k}))'"]

    roh = subprocess.run(
        ["ffmpeg", "-hide_banner", "-loglevel", "error", "-i", str(video),
         "-vf", ",".join(kette), "-vsync", "0", "-f", "rawvideo", "-"],
        check=True, capture_output=True).stdout
    bilder = np.frombuffer(roh, dtype=np.uint8) \
        .reshape(-1, HOEHE, BREITE).astype(np.float32)
    return np.arange(len(bilder)) * (k / _fps(video)), bilder


def finde(video: Path, schritt: float = SCHRITT,
          box: tuple[int, int, int, int] | None = None,
          mindest: float = 12.0, faktor: float = 4.0, umgebung: float = 6.0
          ) -> list[float]:
    """Zeitpunkte harter Bildwechsel.

    ``mindest``  absoluter Mindestabstand — darunter ist es Rauschen.
    ``faktor``   Vielfaches des lokalen Medians, ab dem es ein Schnitt ist.
    ``umgebung`` Sekunden, ueber die der lokale Median gebildet wird.

    Der Median haelt die Handkamera draussen: Dort ist die Umgebung selbst
    schon unruhig, ein echter Schnitt muesste sie um ``faktor`` uebertreffen.
    """
    zeiten, bilder = abtasten(video, schritt, box)
    if len(bilder) < 3:
        return []
    abstand = np.r_[0.0, np.abs(np.diff(bilder, axis=0)).mean(axis=(1, 2))]

    halb = max(1, int(umgebung / schritt) // 2)
    lokal = np.empty_like(abstand)
    for i in range(len(abstand)):
        fenster = abstand[max(0, i - halb):i + halb + 1]
        lokal[i] = np.median(fenster)

    treffer = (abstand >= mindest) & (abstand >= faktor * np.maximum(lokal, 0.5))
    return [round(float(t), 2) for t in zeiten[treffer]]


def pruefe(start: float, ende: float, schnitte: list[float],
           rand: float = 0.30) -> list[float]:
    """Schnitte, die INNERHALB des Clipfensters liegen.

    ``rand`` laesst die aeussersten Sekunden aus: Ein Schnitt genau auf der
    Grenze ist kein Sprung im Clip, sondern sein Anfang oder sein Ende — genau
    dort *soll* eine Grenze liegen.
    """
    return [s for s in schnitte if start + rand < s < ende - rand]


def melde(clip_id: str, start: float, ende: float,
          schnitte: list[float]) -> list[str]:
    """Meldetexte fuer ``clip rendere``. Leer heisst: nichts dazwischen."""
    drin = pruefe(start, ende, schnitte)
    if not drin:
        return []
    liste = ", ".join(f"{s:.2f}s" for s in drin[:6])
    mehr = f" (+{len(drin) - 6} weitere)" if len(drin) > 6 else ""
    return [f"{clip_id}: {len(drin)} Bildwechsel im Clip bei {liste}{mehr} — "
            f"der Clip springt dort. Grenzen pruefen."]
