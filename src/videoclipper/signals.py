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
import re
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
    """Wie ein Layout erkannt wird.

    Der Regelfall ist eine statische Kante, die es nur im Speziallayout gibt.
    Manche Layouts haben aber gar keine: Wenn ein hochkantes Handybild mittig
    auf schwarzem Grund steht, ist die Kante zum Rahmen nur dann da, wenn der
    Handyinhalt gerade hell ist — bei einer dunklen App faellt sie auf null,
    obwohl das Layout unveraendert steht (gemessen an A14FQZsFooQ: Kantenwert
    0.3 bis 119 *innerhalb desselben Modus*). Erkannt wird dort deshalb der
    schwarze Rahmen selbst, ueber ``flaeche`` und ``invertiert``.
    """
    name: str
    kante_x: int | None = None      # Spalte mit persistenter vertikaler Kante
    kante_y: int | None = None      # Zeile mit persistenter horizontaler Kante
    flaeche: tuple[int, int, int, int] | None = None   # x,y,w,h: Flaeche statt Kante
    kantenenergie: bool = False     # bei flaeche: Struktur messen statt Helligkeit
    bereich: tuple[int, int] = (0, 0)   # Ausschnitt laengs der Kante
    schwelle: float = 12.0
    invertiert: bool = False        # True: Modus ist *unterhalb* der Schwelle aktiv
    immer: bool = False             # Material mit genau EINEM Modus
    sonst: str = "SOLO"             # Modusname, wo die Signatur nicht greift

    def aktiv(self, werte: np.ndarray) -> np.ndarray:
        """Elementweise: liegt an dieser Stelle das Speziallayout vor?"""
        if self.immer:
            return np.ones(len(werte), dtype=bool)
        return werte < self.schwelle if self.invertiert else werte > self.schwelle


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


def _flaechen_verlauf(video: Path, sig: ModusSignatur, K: int,
                      fps: float) -> tuple[np.ndarray, np.ndarray]:
    """Ein Ausschnitt ueber die Zeit — als Helligkeit oder als Kantenenergie.

    Helligkeit (16x16) beantwortet "ist diese Flaeche schwarz". Das reicht
    nicht immer: Ein Gitter aus vielen kleinen, dunklen Handybildern ist im
    Mittel genauso schwarz wie ein leerer Rahmen (gemessen an A14FQZsFooQ:
    0.7 gegen 0.0, ununterscheidbar). Was es unterscheidet, ist STRUKTUR —
    Kacheln haben Kanten, ein leerer Rahmen hat keine. ``kantenenergie``
    misst deshalb den mittleren Betrag des Gradienten statt des Pegels; auf
    denselben Daten trennt das PHONE (p95 1.59) von Gitter (p5 2.19) mit
    einer Luecke dazwischen.

    Der Massstab ist Teil der Messgroesse: Ein Gradient auf halber Aufloesung
    ist ein anderer Zahlenwert. Deshalb steht die Verkleinerung fest bei 4x,
    und die Schwellen im Profil gelten fuer genau diesen Massstab.
    """
    x, y, w, h = sig.flaeche
    if not sig.kantenenergie:
        roh = subprocess.run(
            ["ffmpeg", "-hide_banner", "-loglevel", "error", "-i", str(video),
             "-vf", rf"select='not(mod(n\,{K}))',format=gray,"
                    rf"crop={w}:{h}:{x}:{y},scale=16:16",
             "-fps_mode", "passthrough", "-f", "rawvideo", "-"],
            capture_output=True, check=True).stdout
        anzahl = len(roh) // 256
        stapel = np.frombuffer(roh[:anzahl * 256], dtype=np.uint8).reshape(anzahl, 256)
        return np.arange(anzahl) * (K / fps), stapel.mean(axis=1).astype(np.float32)

    bw, bh = (w // 4) // 2 * 2, (h // 4) // 2 * 2
    roh = subprocess.run(
        ["ffmpeg", "-hide_banner", "-loglevel", "error", "-i", str(video),
         "-vf", rf"select='not(mod(n\,{K}))',format=gray,"
                rf"crop={w}:{h}:{x}:{y},scale={bw}:{bh}",
         "-fps_mode", "passthrough", "-f", "rawvideo", "-"],
        capture_output=True, check=True).stdout
    n = bw * bh
    anzahl = len(roh) // n
    st = np.frombuffer(roh[:anzahl * n], dtype=np.uint8).reshape(anzahl, bh, bw).astype(np.float32)
    energie = (np.abs(np.diff(st, axis=2)).mean(axis=(1, 2))
               + np.abs(np.diff(st, axis=1)).mean(axis=(1, 2)))
    return np.arange(anzahl) * (K / fps), energie.astype(np.float32)


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
    # Genau ein Modus: Es gibt nichts zu unterscheiden, also wird auch nichts
    # abgetastet. Bei 42 Minuten spart das den kompletten Bilddurchlauf — und
    # eine Messung, die per Definition immer dasselbe Ergebnis haette, waere
    # ohnehin keine Messung. Ob ein Material einmodig ist, entscheidet die
    # Kantenmessung beim Anlegen des Profils, nicht dieser Aufruf.
    if sig.immer:
        z = np.arange(0.0, max(dauer, schritt), schritt, dtype=np.float32)
        return z, np.ones(len(z), dtype=np.float32)

    fps = bildrate(video)
    K = max(1, round(fps * schritt))

    if sig.flaeche is not None:
        return _flaechen_verlauf(video, sig, K, fps)

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


def modus_je_bild(video: Path, sig: ModusSignatur, start: float,
                  dauer: float) -> tuple[np.ndarray, np.ndarray]:
    """Signaturwert fuer JEDES Bild eines Clipfensters, auf der Zeitachse des Renderers.

    WOZU: ``modus_verlauf`` tastet im Raster ab — genug, um Laeufe zu finden,
    zu grob fuer einen Einschub (``layout.einschuebe``). Dort muss der Wechsel
    auf das Bild genau sitzen: Kommt das Ersatzpanel ein Bild zu frueh, steht
    fuer diesen Frame das ganze Chatlayout verkleinert im oberen Panel; kommt
    es zu spaet, ein Ausschnitt mitten aus der Vollbild-Cam.

    Deshalb dieselbe Suche wie ``render.rendere`` (``-ss`` vor ``-i``): Die
    Zeitstempel, die ``showinfo`` hier meldet, sind genau die ``t``, die im
    Filtergraph des Renderers in ``enable`` stehen. Kein Umrechnen ueber die
    Bildrate, keine Annahme darueber, wo das erste Bild nach der Suche liegt.

    Nur fuer Flaechensignaturen. Eine Kante hat bisher kein Profil mit
    Einschub gebraucht, und ungetesteter Code dafuer waere schlechter als ein
    klarer Fehler.
    """
    if sig.flaeche is None:
        raise ValueError(
            f"{sig.name}: bildgenaue Moduserkennung braucht eine Flaechensignatur")
    x, y, w, h = sig.flaeche
    # Massstab wie in ``_flaechen_verlauf`` — die Schwellen im Profil gelten
    # fuer genau diesen.
    bw, bh = ((w // 4) // 2 * 2, (h // 4) // 2 * 2) if sig.kantenenergie else (16, 16)

    p = subprocess.run(
        ["ffmpeg", "-hide_banner", "-nostats", "-loglevel", "info",
         "-ss", f"{start:.3f}", "-t", f"{dauer:.3f}", "-i", str(video),
         "-vf", f"format=gray,crop={w}:{h}:{x}:{y},scale={bw}:{bh},showinfo",
         "-fps_mode", "passthrough", "-an", "-f", "rawvideo", "-"],
        capture_output=True, check=True)
    zeiten = np.array([float(z) for z in re.findall(rb"pts_time:\s*(-?[\d.]+)", p.stderr)],
                      dtype=np.float64)
    n = bw * bh
    anzahl = min(len(zeiten), len(p.stdout) // n)
    st = np.frombuffer(p.stdout[:anzahl * n], dtype=np.uint8) \
        .reshape(anzahl, bh, bw).astype(np.float32)
    if sig.kantenenergie:
        werte = (np.abs(np.diff(st, axis=2)).mean(axis=(1, 2))
                 + np.abs(np.diff(st, axis=1)).mean(axis=(1, 2)))
    else:
        werte = st.mean(axis=(1, 2))
    return zeiten[:anzahl], werte.astype(np.float32)


# ---------------------------------------------------------------- Zusammenfuehrung

@dataclass
class Signale:
    zeiten_db: np.ndarray
    db: np.ndarray
    lacher: list[float]          # Zeitpunkte aus [gelächter] & Verwandten
    modus_zeiten: np.ndarray
    modus_wert: np.ndarray
    modus_schwelle: float
    modus_invertiert: bool = False

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
        if not len(w):
            return 0.0
        an = w < self.modus_schwelle if self.modus_invertiert else w > self.modus_schwelle
        return float(an.mean())


def sammle(video: Path, tr: Transkript, sig: ModusSignatur,
           schritt: float = 2.0) -> Signale:
    zt, db = lautheit(video)
    lach_arten = ("gelächter", "lachen", "schreien", "applaus")
    lacher = [w.start for w in tr.marker()
              if any(a in w.text.lower() for a in lach_arten)]
    mz, mw = modus_verlauf(video, sig, tr.dauer, schritt)
    return Signale(zt, db, lacher, mz, mw, sig.schwelle, sig.invertiert)
