"""Musikbett unter jedem Video — Auftrag des Nutzers vom 2026-10-20.

"Alle Videos sollen einen Soundtrack haben." Ohne Einschraenkung, also auch
unter dem Countdown.

Die Stuecke liegen auf der Maschine, nicht im Repo (``settings.toml``,
Abschnitt ``[soundtrack]``). Hier steht nur, welches Stueck ein Clip bekommt
und wie es unter die Stimme gelegt wird.

ZWEI ENTSCHEIDUNGEN, die nicht offensichtlich sind:

**Die Wahl ist deterministisch, nicht zufaellig.** Leitprinzip 2 verlangt,
dass derselbe Eingang dasselbe Ergebnis liefert. Mit ``random.choice`` laege
unter demselben Clip bei jedem Rerender eine andere Musik, und zwei Laeufe
waeren nicht mehr vergleichbar — genau das, was die Grenzkontrolle und der
Pruefbogen voraussetzen. Der Index kommt deshalb aus einem stabilen Hash der
``clip_id``. ``hash()`` taugt dafuer nicht: Python streut ihn seit 3.3 je
Prozess, zwei Laeufe am selben Clip haetten verschiedene Stuecke.

**Die Musik weicht der Stimme, statt dauerhaft leise zu sein.** Ohne Ducking
muesste das Bett so tief liegen, dass es in den Sprechpausen gar nicht mehr
traegt — und die Pausen sind der Grund, warum es ueberhaupt da ist. Gemischt
wird deshalb mit ``sidechaincompress``: die Stimme steuert, wie weit die Musik
zurueckgeht.

Die Reihenfolge im Graphen ist Absicht: Erst ``loudnorm`` auf die Stimme, dann
die Musik um einen festen Betrag darunter, zum Schluss ein Limiter. Normiert
man stattdessen die Summe, haengt der Stimmpegel davon ab, wie laut das
zufaellig gewaehlte Stueck ist.
"""

from __future__ import annotations

import hashlib
from pathlib import Path

from .settings import einstellungen

# Was FFmpeg als Tonspur oeffnen kann. ``.mp4`` ist dabei: Die Stuecke des
# Nutzers sind YouTube-Mitschnitte ohne Bildspur, und genau so liegen sie im
# Ordner (``videoplayback.mp4``). Geprueft wird nicht die Endung, sondern beim
# Laden, ob eine Tonspur drin ist.
ENDUNGEN = (".mp3", ".m4a", ".aac", ".wav", ".flac", ".ogg", ".opus", ".mp4", ".webm")


def verzeichnis() -> Path:
    """Ordner mit den Stuecken, aus ``settings.toml`` bzw. ``local.toml``."""
    conf = einstellungen().get("soundtrack") or {}
    return Path(conf.get("ordner", "~/Desktop/Soundtracks")).expanduser()


def stuecke(ordner: Path | None = None) -> list[Path]:
    """Alle brauchbaren Dateien, nach Namen sortiert.

    Sortiert, damit die Zuordnung Clip -> Stueck nicht davon abhaengt, in
    welcher Reihenfolge das Dateisystem die Eintraege liefert.
    """
    ordner = ordner or verzeichnis()
    if not ordner.is_dir():
        return []
    return sorted(p for p in ordner.iterdir()
                  if p.is_file() and p.suffix.lower() in ENDUNGEN
                  and not p.name.startswith("."))


def waehle(clip_id: str, ordner: Path | None = None) -> Path | None:
    """Stabil dasselbe Stueck fuer dieselbe ``clip_id``.

    ``hashlib`` statt ``hash()``: Letzteres ist je Prozess gestreut, derselbe
    Clip bekaeme in zwei Laeufen verschiedene Musik.
    """
    alle = stuecke(ordner)
    if not alle:
        return None
    roh = hashlib.sha256(clip_id.encode("utf-8")).digest()
    return alle[int.from_bytes(roh[:8], "big") % len(alle)]


def pflicht() -> bool:
    conf = einstellungen().get("soundtrack") or {}
    return bool(conf.get("pflicht", True))


def konfiguration(tmpl: dict) -> dict:
    """Hauswerte aus ``overlays.yaml``, vom Template ueberschreibbar.

    ``layout.template()`` mischt die Hauswerte bereits unter das Template —
    hier wird nur noch ausgelesen, was dort steht.
    """
    return dict(tmpl.get("soundtrack") or {})


def aktiv(tmpl: dict) -> bool:
    return bool(konfiguration(tmpl).get("aktiv", False))


def _escape(p: Path) -> str:
    return str(p)


def eingang(stueck: Path, conf: dict) -> list[str]:
    """FFmpeg-Argumente fuer den Musikeingang.

    ``-stream_loop -1`` statt des ``aloop``-Filters: Der Filter braucht die
    Laenge in Samples, die im Graphen niemand kennt; der Eingang wiederholt
    sich ohne diese Angabe. Abgeschnitten wird spaeter mit ``atrim``.
    """
    args = []
    if conf.get("schleife", True):
        args += ["-stream_loop", "-1"]
    return args + ["-i", _escape(stueck)]


def kette(index: int, dauer: float, conf: dict, stimme: str, ziel: str,
          lufs: float) -> list[str]:
    """Filterglieder, die ``[stimme]`` und den Musikeingang zu ``[ziel]`` mischen.

    ``stimme`` ist das Label des rohen Tons (ohne ``loudnorm``), ``index`` der
    Eingangsindex der Musik. Zurueck kommen die Glieder in Graphreihenfolge.
    """
    pegel = float(conf.get("pegel_db", -20.0))
    ein = float(conf.get("blende_ein", 0.5))
    aus = float(conf.get("blende_aus", 1.0))
    duck = dict(conf.get("ducking") or {})

    glieder = [
        # Die Stimme zuerst auf den Zielpegel. Danach ist "20 dB darunter" eine
        # feste Groesse und nicht vom gewaehlten Stueck abhaengig.
        f"[{stimme}]loudnorm=I={lufs}:TP=-1.5:LRA=11,"
        f"aformat=sample_rates=48000:channel_layouts=stereo[st_norm]",
    ]

    if duck.get("aktiv", True):
        glieder.append("[st_norm]asplit=2[st_mix][st_duck]")
        stimme_mix, stimme_key = "st_mix", "st_duck"
    else:
        stimme_mix, stimme_key = "st_norm", None

    # Musik: auf Cliplaenge schneiden, auf einen ABSOLUTEN Pegel bringen,
    # Blenden legen.
    #
    # GEMESSEN am 2026-10-20 an x0XeuK8Ejys_008: Die erste Fassung senkte die
    # Musik mit ``volume=-20dB``, also um 20 dB gegen ihren EIGENEN Pegel. In
    # der digitalen Stille bei 11.0 s lag sie dadurch bei -48 dB statt der
    # erwarteten -34, weil das gewaehlte Stueck selbst leise ist. Damit haengt
    # die Lautstaerke des Bettes davon ab, welche Datei der Hash trifft — bei
    # fuenf Stuecken aus verschiedenen Quellen ein Unterschied von zweistelligen
    # dB.
    #
    # Erst auf DENSELBEN Pegel wie die Stimme normieren, dann um ``pegel_db``
    # absenken. Damit ist der Abstand zur Stimme gemeint und eingehalten,
    # unabhaengig davon, welches Stueck der Hash trifft.
    #
    # NICHT in einem Schritt mit ``loudnorm=I=lufs+pegel``: FFmpeg laesst
    # ``TP`` nur zwischen -9 und 0 zu. Ein Ziel von -34 LUFS braucht ein TP
    # darunter, und der Filter bricht mit Exit 222 ab (gemessen am
    # 2026-10-20). Normieren und Absenken sind deshalb zwei Glieder.
    aus_start = max(0.0, dauer - aus)
    glieder.append(
        f"[{index}:a]atrim=0:{dauer:.3f},asetpts=PTS-STARTPTS,"
        f"aformat=sample_rates=48000:channel_layouts=stereo,"
        f"loudnorm=I={lufs}:TP=-1.5:LRA=11,"
        f"volume={pegel:.2f}dB,"
        f"afade=t=in:st=0:d={ein:.3f},"
        f"afade=t=out:st={aus_start:.3f}:d={aus:.3f}[mus_roh]"
    )

    if stimme_key is not None:
        glieder.append(
            f"[mus_roh][{stimme_key}]sidechaincompress="
            f"threshold={float(duck.get('schwelle', 0.03)):.4f}:"
            f"ratio={float(duck.get('verhaeltnis', 8)):g}:"
            f"attack={float(duck.get('attack', 20)):g}:"
            f"release={float(duck.get('release', 400)):g}[mus]"
        )
    else:
        glieder.append("[mus_roh]anull[mus]")

    # ``normalize=0``: amix teilt sonst durch die Zahl der Eingaenge und macht
    # die eben normierte Stimme um 6 dB leiser. ``duration=first`` haelt die
    # Laenge an der Stimme, nicht an der Musik.
    glieder.append(
        f"[{stimme_mix}][mus]amix=inputs=2:normalize=0:duration=first,"
        f"alimiter=limit=0.84[{ziel}]"
    )
    return glieder
