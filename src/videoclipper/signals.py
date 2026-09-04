"""Stage 04 — Signale.

Alles deterministisch und gratis: Lautheits-Huellkurve, Sprechtempo, Lachmarker
aus dem Transkript und — fuer dieses Material zusaetzlich noetig — die Erkennung
des Layout-Modus pro Zeitpunkt.

Der Modus ist hier ein *Signal*, kein fester Profilwert: Das Material wechselt
innerhalb eines Videos zwischen Vollbild-Cam und Browser-/Gameplay-Capture. Das
Blueprint nimmt statische Boxen an; fuer diese Quellen stimmt das nicht.
"""

from __future__ import annotations

import io
import subprocess
from dataclasses import dataclass
from pathlib import Path

import numpy as np
from PIL import Image

from .transcript import Transkript


# ---------------------------------------------------------------- Audio

def lautheit(video: Path, fenster: float = 0.25) -> tuple[np.ndarray, np.ndarray]:
    """RMS-Huellkurve in dBFS. Gibt (Zeiten, dB) zurueck."""
    rate = 8000
    roh = subprocess.run(
        ["ffmpeg", "-hide_banner", "-loglevel", "error", "-i", str(video),
         "-ac", "1", "-ar", str(rate), "-f", "s16le", "-"],
        capture_output=True, check=True).stdout
    x = np.frombuffer(roh, dtype=np.int16).astype(np.float32) / 32768.0
    n = int(rate * fenster)
    nutz = (len(x) // n) * n
    bloecke = x[:nutz].reshape(-1, n)
    rms = np.sqrt((bloecke ** 2).mean(axis=1)) + 1e-9
    return np.arange(len(rms)) * fenster, 20 * np.log10(rms)


# ---------------------------------------------------------------- Layout

@dataclass(frozen=True)
class ModusSignatur:
    """Wie ein Layout erkannt wird: eine statische Kante, die es sonst nicht gibt."""
    name: str
    kante_x: int | None = None      # Spalte mit persistenter vertikaler Kante
    kante_y: int | None = None      # Zeile mit persistenter horizontaler Kante
    bereich: tuple[int, int] = (0, 0)   # Ausschnitt laengs der Kante
    schwelle: float = 12.0


def _kantenstaerke(bild: np.ndarray, sig: ModusSignatur) -> float:
    if sig.kante_x is not None:
        a, b = sig.bereich
        streifen = bild[a:b, sig.kante_x - 2:sig.kante_x + 3]
        return float(np.abs(np.diff(streifen, axis=1)).max(axis=1).mean())
    a, b = sig.bereich
    streifen = bild[sig.kante_y - 2:sig.kante_y + 3, a:b]
    return float(np.abs(np.diff(streifen, axis=0)).max(axis=0).mean())


def _frame(video: Path, t: float) -> np.ndarray:
    roh = subprocess.run(
        ["ffmpeg", "-hide_banner", "-loglevel", "error", "-ss", f"{t:.2f}",
         "-i", str(video), "-frames:v", "1", "-f", "image2pipe", "-vcodec", "png", "-"],
        capture_output=True).stdout
    if not roh:
        raise RuntimeError(f"Kein Frame bei t={t}")
    return np.asarray(Image.open(io.BytesIO(roh)).convert("L"), dtype=np.float32)


def bildrate(video: Path) -> float:
    aus = subprocess.run(
        ["ffprobe", "-v", "error", "-select_streams", "v:0",
         "-show_entries", "stream=avg_frame_rate", "-of", "default=nw=1:nk=1", str(video)],
        capture_output=True, text=True, check=True).stdout.strip()
    z, n = aus.split("/")
    return float(z) / float(n)


def modus_verlauf(video: Path, sig: ModusSignatur, dauer: float,
                  schritt: float = 2.0) -> tuple[np.ndarray, np.ndarray]:
    """Kantenstaerke ueber die Zeit. Hoch = Layout vorhanden.

    Abgetastet wird ueber echte Bildnummern (``select`` auf ``mod(n,K)``), nicht
    ueber den ``fps``-Filter: Der resampelt und laeuft auf diesem Material gegen
    die echte Zeitachse weg — die Modi wechseln hier im Sekundenbereich, damit
    waeren die Fenstergrenzen falsch. Bildnummer durch Bildrate ist driftfrei.

    Der Streifen laengs der Kante wird schon im Filtergraph ausgeschnitten, damit
    nur wenige Kilobyte pro Frame anfallen. ``format=gray`` muss vor dem Crop
    stehen — auf yuv420p rundet crop ungerade Kantenmasse still ab.
    """
    fps = bildrate(video)
    K = max(1, round(fps * schritt))

    a, b = sig.bereich
    laenge = (b - a) // 2 * 2
    if sig.kante_x is not None:
        crop = f"crop=6:{laenge}:{sig.kante_x-3}:{a}"
        breite, hoehe, achse = 6, laenge, 1
    else:
        crop = f"crop={laenge}:6:{a}:{sig.kante_y-3}"
        breite, hoehe, achse = laenge, 6, 0

    roh = subprocess.run(
        ["ffmpeg", "-hide_banner", "-loglevel", "error", "-i", str(video),
         "-vf", rf"select='not(mod(n\,{K}))',format=gray,{crop}",
         "-fps_mode", "passthrough", "-f", "rawvideo", "-"],
        capture_output=True, check=True).stdout

    n = breite * hoehe
    anzahl = len(roh) // n
    stapel = np.frombuffer(roh[:anzahl * n], dtype=np.uint8).reshape(anzahl, hoehe, breite)
    d = np.abs(np.diff(stapel.astype(np.float32), axis=achse + 1))
    w = d.max(axis=achse + 1).mean(axis=1).astype(np.float32)
    return np.arange(anzahl) * (K / fps), w


# ---------------------------------------------------------------- Zusammenfuehrung

@dataclass
class Signale:
    zeiten_db: np.ndarray
    db: np.ndarray
    lacher: list[float]          # Zeitpunkte aus [gelächter] & Verwandten
    modus_zeiten: np.ndarray
    modus_wert: np.ndarray
    modus_schwelle: float

    def db_bei(self, t: float) -> float:
        i = int(np.clip(t / (self.zeiten_db[1] - self.zeiten_db[0]), 0, len(self.db) - 1))
        return float(self.db[i])

    def modus_anteil(self, start: float, ende: float) -> float:
        """Anteil des Fensters, in dem das Speziallayout aktiv ist (0..1)."""
        m = (self.modus_zeiten >= start) & (self.modus_zeiten < ende)
        if not m.any():
            return 0.0
        w = self.modus_wert[m]
        w = w[~np.isnan(w)]
        return float((w > self.modus_schwelle).mean()) if len(w) else 0.0


def sammle(video: Path, tr: Transkript, sig: ModusSignatur,
           schritt: float = 2.0) -> Signale:
    zt, db = lautheit(video)
    lach_arten = ("gelächter", "lachen", "schreien", "applaus")
    lacher = [w.start for w in tr.marker()
              if any(a in w.text.lower() for a in lach_arten)]
    mz, mw = modus_verlauf(video, sig, tr.dauer, schritt)
    return Signale(zt, db, lacher, mz, mw, sig.schwelle)
