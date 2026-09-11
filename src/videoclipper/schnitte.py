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


# ---------------------------------------------------------------------------
# Bildgenaue Uebergaenge — fuer die Grenzen in ``snappe``
# ---------------------------------------------------------------------------
#
# ``finde`` tastet im 0.25-s-Raster: Ein Schnitt bei c heisst nur, dass sich
# das Bild irgendwo zwischen c-0.25 und c geaendert hat. Fuer die Meldung "da
# springt etwas" reicht das, fuer eine Clipgrenze nicht. GEMESSEN am
# 2026-09-11 an saiJDq9DM_Y: Der Kanal blendet zwischen Cam und Browser in
# rund 0.3 s ueber, und das Intro endet mit einem harten Schnitt 0.04 s vor
# dem ersten Wort. Beides liegt innerhalb eines einzigen Rasterschritts.

def _bildabstaende(video: Path, von: float, bis: float,
                   fps: float) -> tuple[np.ndarray, np.ndarray]:
    """Jedes Bild zwischen ``von`` und ``bis`` mit seinem Abstand zum Vorgaenger.

    ``abstand[i]`` gehoert zu ``zeiten[i]``, also zu dem Bild, das sich
    veraendert hat — bei einem harten Schnitt ist das das erste neue Bild.
    """
    n = max(2, int(np.ceil((bis - von) * fps)) + 1)
    roh = subprocess.run(
        ["ffmpeg", "-hide_banner", "-loglevel", "error", "-ss", f"{von:.3f}",
         "-i", str(video), "-frames:v", str(n),
         "-vf", "format=gray,scale=96:54", "-f", "rawvideo", "-"],
        check=True, capture_output=True).stdout
    bilder = np.frombuffer(roh, dtype=np.uint8).reshape(-1, 54, 96).astype(np.float32)
    t0 = np.ceil(von * fps - 1e-6) / fps
    zeiten = t0 + np.arange(len(bilder)) / fps
    abstand = np.r_[0.0, np.abs(np.diff(bilder, axis=0)).mean(axis=(1, 2))]
    return zeiten, abstand


def _spanne(zeiten: np.ndarray, abstand: np.ndarray, von: float, bis: float,
            schwelle_min: float = 1.0, faktor: float = 4.0
            ) -> tuple[float, float] | None:
    """Erstes und letztes veraendertes Bild zwischen ``von`` und ``bis``.

    Die Schwelle steht relativ zum Rauschen des Fensters, mindestens aber bei
    ``schwelle_min``. Gemessen an saiJDq9DM_Y (96x54, Graustufen): ruhiges
    Bild 0.1-0.3 je Bildwechsel, Ueberblendung 3-9, harter Schnitt 30-40.
    """
    schwelle = max(schwelle_min, faktor * float(np.median(abstand)))
    idx = np.flatnonzero((zeiten >= von - 1e-6) & (zeiten <= bis + 1e-6)
                         & (abstand > schwelle))
    if not len(idx):
        return None
    return round(float(zeiten[idx[0]]), 3), round(float(zeiten[idx[-1]]), 3)


def uebergaenge(video: Path, schnitte: list[float],
                schritt: float = SCHRITT) -> list[tuple[float, float]]:
    """Die Schnitte aus ``finde`` bildgenau: (erstes veraendertes, erstes neues Bild).

    Benachbarte Meldungen gehoeren zu einem Uebergang — eine Ueberblendung
    ueber 0.3 s erzeugt im 0.25-s-Raster zwei. Findet sich im Fenster kein
    Bild ueber der Schwelle (sehr weiche Blende), gilt das grobe Raster:
    lieber eine Viertelsekunde zu vorsichtig als ein halber Uebergang im Clip.
    """
    if not schnitte:
        return []
    fps = _fps(video)
    gruppen: list[list[float]] = []
    for c in sorted(schnitte):
        if gruppen and c - gruppen[-1][-1] <= 2 * schritt + 1e-6:
            gruppen[-1].append(c)
        else:
            gruppen.append([c])

    spannen = []
    for g in gruppen:
        # Der Wechsel liegt hinter dem Abtastpunkt vor der ersten Meldung; eine
        # Blende kann ein halbes Raster ueber die letzte hinaus nachlaufen.
        von, bis = max(0.0, g[0] - schritt), g[-1] + schritt / 2
        # 0.3 s Ruhe links und rechts, damit der Median das Rauschen misst und
        # nicht die Blende selbst.
        zeiten, abstand = _bildabstaende(video, max(0.0, von - 0.3), bis + 0.3, fps)
        spannen.append(_spanne(zeiten, abstand, von, bis) or (von, g[-1]))
    return spannen


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
