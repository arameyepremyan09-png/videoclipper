"""Frames zum Anschauen.

Kein Stage der Pipeline, sondern ein Werkzeug: Video rein, Standbilder raus,
damit ein Mensch oder ein Modell sich Material ansehen kann, ohne es
abzuspielen. Vermessung von Boxkanten und Modi laeuft weiter ueber Stage 04.

Abgetastet wird ueber echte Bildnummern (``select='not(mod(n,K))'``), nie ueber
den ``fps``-Filter — der laeuft gegen die echte Zeitachse weg.

Zeitstempel werden **nicht** ins Bild geschrieben: drawtext fehlt im
FFmpeg-Build auf dem MacBook. Stattdessen gibt ``kontaktbogen`` die Zuordnung
Kachel -> Sekunde zurueck, und der Aufrufer druckt sie daneben.
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

from .settings import arbeitsverzeichnis


class Fehlt(RuntimeError):
    """Quelle nicht beschaffbar — mit einem Hinweis, was stattdessen geht."""


def _sonde(video: Path) -> tuple[float, float]:
    """(fps, Dauer in Sekunden) aus dem ersten Videostream."""
    roh = subprocess.run(
        ["ffprobe", "-v", "error", "-select_streams", "v:0",
         "-show_entries", "stream=r_frame_rate", "-show_entries", "format=duration",
         "-of", "json", str(video)],
        check=True, capture_output=True, text=True).stdout
    daten = json.loads(roh)
    zaehler, nenner = daten["streams"][0]["r_frame_rate"].split("/")
    fps = float(zaehler) / float(nenner or 1)
    return fps, float(daten["format"]["duration"])


def hole(url: str, ziel_dir: Path | None = None) -> Path:
    """Video per yt-dlp ins Arbeitsverzeichnis laden.

    Format auf avc1 gezwungen (die RX 580 hat kein AV1-Hardware-Decode),
    ``web_embedded`` als Player-Client (der Default lief nach ~10 MB in 403).
    ``--download-sections`` wird bewusst nicht benutzt: gemessen unbrauchbar
    langsam, das ganze Video zu laden ist schneller.
    """
    ziel_dir = ziel_dir or arbeitsverzeichnis()
    cmd = [
        "yt-dlp",
        "-f", "bv*[vcodec^=avc1][height<=1080]+ba/b[vcodec^=avc1]/b",
        "--extractor-args", "youtube:player_client=web_embedded",
        "--no-playlist", "--no-overwrites",
        "-o", str(ziel_dir / "%(extractor)s_%(id)s.%(ext)s"),
        "--print", "after_move:filepath",
        url,
    ]
    lauf = subprocess.run(cmd, capture_output=True, text=True)
    if lauf.returncode != 0:
        raise Fehlt(
            f"yt-dlp kam an {url} nicht heran.\n"
            f"{lauf.stderr.strip()[-500:]}\n\n"
            "Bei TikTok ist das der Normalfall: Der Extractor laeuft dort gegen "
            "ein Slider-CAPTCHA, und das wird nicht umgangen. Lade die Datei "
            "selbst herunter, lege sie ins Arbeitsverzeichnis und uebergib den "
            "lokalen Pfad statt der URL."
        )
    zeilen = [z for z in lauf.stdout.splitlines() if z.strip()]
    if not zeilen:
        raise Fehlt(f"yt-dlp meldete keinen Dateipfad fuer {url}.")
    return Path(zeilen[-1].strip())


def aufloesen(quelle: str) -> Path:
    """Lokaler Pfad oder URL — am Ende liegt eine Datei auf der Platte."""
    if quelle.startswith(("http://", "https://")):
        return hole(quelle)
    pfad = Path(quelle).expanduser()
    if not pfad.exists():
        raise Fehlt(f"{pfad} gibt es nicht.")
    return pfad


def kontaktbogen(video: Path, ziel: Path, spalten: int = 5, zeilen: int = 5,
                 breite: int = 480, alle: int | None = None,
                 ) -> list[tuple[int, float]]:
    """Ein PNG mit ``spalten*zeilen`` Kacheln ueber die volle Laufzeit.

    Gibt die Zuordnung (Kachelnummer, Sekunde) zurueck. Ein Bogen kostet den
    Betrachter einen Blick statt fuenfundzwanzig.
    """
    fps, dauer = _sonde(video)
    kacheln = spalten * zeilen
    gesamt = int(dauer * fps)
    schritt = alle if alle else max(1, gesamt // kacheln)

    ziel.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(
        ["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-i", str(video),
         "-vf", (f"select='not(mod(n,{schritt}))',scale={breite}:-2,"
                 f"tile={spalten}x{zeilen}"),
         "-frames:v", "1", "-fps_mode", "passthrough", str(ziel)],
        check=True)

    return [(i + 1, (i * schritt) / fps)
            for i in range(kacheln) if i * schritt < gesamt]


def einzelbilder(video: Path, zeiten: list[float], ziel_dir: Path,
                 breite: int = 0) -> list[Path]:
    """Volle Frames an genannten Sekunden — fuer Kanten und Ausschnitte."""
    ziel_dir.mkdir(parents=True, exist_ok=True)
    skala = ["-vf", f"scale={breite}:-2"] if breite else []
    raus = []
    for t in zeiten:
        pfad = ziel_dir / f"{video.stem}_{t:09.3f}.png"
        subprocess.run(
            ["ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
             "-ss", f"{t:.3f}", "-i", str(video), *skala,
             "-frames:v", "1", str(pfad)],
            check=True)
        raus.append(pfad)
    return raus
