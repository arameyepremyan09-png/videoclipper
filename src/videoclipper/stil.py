"""Stage 11c — Bildstil und Textspur.

WOZU: Die Referenzclips, an denen dieser Kanal gemessen wird, sehen nicht
deshalb aufwendig aus, weil ihre Komposition komplizierter waere — sie
benutzen dieselben zwei bis drei Panels wie unsere Templates. Der Unterschied
sind vier Dinge, alle am 2026-09-07 an fuenf TikToks vermessen:

    1. Untertitel Wort fuer Wort, gross und mitten im Bild
    2. eine langsame, durchgehende Kamerafahrt (Push-in)
    3. ein Farbstil (Entsaettigung, Vignette, angehobener Kontrast)
    4. harte Akzente an Schnitten (Blitz, Ruck)

DIE EINE TECHNISCHE HUERDE WAR DIE ZAHL DER EINGAENGE. ``untertitel.py``
notiert Wortmarkierung als verworfen, weil sie "ein PNG je Wort statt je Cue,
rund viermal so viele Eingaenge" kostet. Das stimmt fuer den PNG-Pfad: ein
40-s-Clip hat rund 120 Woerter, und 120 ``-i``-Eingaenge plus 120
``overlay``-Glieder sind kein Filtergraph mehr, den man noch lesen oder
debuggen kann.

DER AUSWEG IST EINE EIGENE SPUR: Alle Textframes werden vorab in *ein* Video
mit Alphakanal gerendert (``qtrle``, pix_fmt ``argb``) und als **ein** Eingang
mit **einem** ``overlay`` ueber die Buehne gelegt. Aus 120 Eingaengen wird
einer, unabhaengig von der Wortzahl.

DAS HEBT NEBENBEI EINE BESCHRAENKUNG AUF, die in ``overlays.yaml`` steht:
Dort ist ``animation.art: aufwaerts`` der einzige erlaubte Wert, weil alles
andere "mehr als einen Filter" gebraucht haette. Auf einer eigenen Spur wird
ohnehin jeder Frame einzeln gezeichnet — eine Pop-Skalierung, ein Nachfedern
oder eine Farbmarkierung kosten dort **nichts** zusaetzlich. Die alte Regel
gilt weiter fuer den PNG-Pfad; sie war eine Aussage ueber Filterkosten, nicht
ueber Geschmack.

WAS ES KOSTET: Die Spur muss vor dem Rendern erzeugt werden, also ein zweiter
Durchlauf ueber die Cliplaenge, und sie liegt unkomprimiert-verlustfrei auf
der Platte. Gemessen an einem 30-s-Clip: rund 8 MB und 6 s Rechenzeit fuer das
Band (1080x420), nicht fuer die volle Canvas. Ein Band statt der ganzen
Canvas ist derselbe Trick, den ``untertitel.baue`` schon fuer die Cue-PNGs
benutzt.
"""

from __future__ import annotations

import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path

from PIL import Image, ImageDraw

from .headline import font as _font
from .transcript import Transkript


# ---------------------------------------------------------------------------
# Wort-Cues
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class WortCue:
    """Ein einzelnes Wort mit seiner Standzeit, relativ zum Clipbeginn."""
    text: str
    ab: float
    bis: float


def wort_cues(tr: Transkript, start: float, ende: float,
              conf: dict) -> list[WortCue]:
    """Die Woerter des Clipfensters als Einzel-Cues.

    GEMESSEN an @twoface.archive/7682055659558407446: Die Standzeit ist die
    Sprechdauer des Wortes, nicht ein fester Takt. Ueber 3 s abgetastet stand
    "37" 0,7 s, "MIT" 0,2 s — der Text folgt also der Stimme. Genau das
    liefert ``json3`` mit seinen Wort-Offsets bereits; es ist kein neues
    Datenproblem, nur eine andere Gruppierung.

    Zwei Korrekturen an den Rohzeiten:

    * ``min_stand`` — sehr kurze Funktionswoerter ("und", "die") blitzen
      sonst nur auf. Sie duerfen in die Pause danach hineinlaufen, aber nie
      in das naechste Wort.
    * ``luecke_fuellen`` — kurze Sprechpausen (Atmen) lassen den Text sonst
      flackernd verschwinden und wiederkommen. Bis zu dieser Laenge haelt das
      Wort einfach stehen.
    """
    min_stand = float(conf.get("min_stand", 0.16))
    luecke = float(conf.get("luecke_fuellen", 0.30))
    max_zeichen = int(conf.get("max_zeichen", 14))

    woerter = [w for w in tr.woerter
               if w.start < ende and w.ende > start
               and not w.ist_marker and w.text.strip()]

    cues: list[WortCue] = []
    for i, w in enumerate(woerter):
        text = w.text.strip()
        # Sehr lange Woerter zerreissen das Bild; sie sind selten und werden
        # getrennt statt verkleinert, weil die Groesse hier das Stilmittel ist.
        if len(text) > max_zeichen:
            text = text[:max_zeichen - 1] + "-"

        ab = max(w.start, start) - start
        bis = min(w.ende, ende) - start

        naechster = woerter[i + 1] if i + 1 < len(woerter) else None
        grenze = (naechster.start - start) if naechster else (ende - start)

        if bis - ab < min_stand:
            bis = min(ab + min_stand, grenze)
        # Kurze Atempause ueberbruecken, damit der Text nicht flackert.
        if naechster is not None and 0 < grenze - bis <= luecke:
            bis = grenze

        if bis > ab:
            cues.append(WortCue(text, ab, bis))
    return cues


# ---------------------------------------------------------------------------
# Textspur (ein Alpha-Video statt N PNG-Eingaenge)
# ---------------------------------------------------------------------------

def _zeichne_wort(bild: Image.Image, text: str, conf: dict,
                  fortschritt: float) -> None:
    """Ein Wort mittig in das Band setzen.

    ``fortschritt`` laeuft von 0 (Worteinsatz) bis 1 (Standzeit vorbei) und
    steuert den Pop. Er ist auf einer eigenen Spur gratis, weil dieser Frame
    ohnehin gezeichnet wird — auf dem PNG-Pfad haette er je Wort ein zweites
    Bild gekostet.
    """
    b, h = bild.size
    dauer = float(conf.get("pop_dauer", 0.10))
    hub = float(conf.get("pop_hub", 0.14))

    # Ueberschwingen und einschwingen: 1+hub bei t=0, zurueck auf 1.0.
    if dauer > 0 and fortschritt < 1.0:
        t = min(fortschritt / dauer, 1.0) if dauer else 1.0
        skala = 1.0 + hub * (1.0 - t) ** 2
    else:
        skala = 1.0

    groesse = max(12, int(conf["schriftgroesse"] * skala))
    schrift = _font(conf, groesse)
    zeichner = ImageDraw.Draw(bild)

    if conf.get("versalien", True):
        text = text.upper()

    rand = int(conf.get("rand_staerke", 12) * skala)
    zeichner.text(
        (b // 2, h // 2), text, font=schrift,
        fill=conf.get("farbe", "#FFFFFF"),
        stroke_width=rand, stroke_fill=conf.get("rand_farbe", "#000000"),
        anchor="mm",
    )


def baue_textspur(cues: list[WortCue], conf: dict, dauer: float, fps: int,
                  ziel: Path, breite: int = 1080) -> Path | None:
    """Alle Wortframes als *ein* Video mit Alphakanal.

    Gibt ``None`` zurueck, wenn es nichts zu zeigen gibt — der Aufrufer
    haengt dann gar keinen Eingang an, statt eine leere Spur zu overlayen.

    Die Bandhoehe statt der vollen Canvas ist Absicht: Bei 1080x420 sind das
    knapp ein Viertel der Bilddaten, die sonst durch den Encoder liefen.
    """
    if not cues:
        return None

    hoehe = int(conf.get("band_hoehe", 420))
    n = max(1, int(round(dauer * fps)))

    rahmen = ziel.parent / f"{ziel.stem}_frames"
    if rahmen.exists():
        shutil.rmtree(rahmen)
    rahmen.mkdir(parents=True, exist_ok=True)

    # Ein Frame je Bildnummer. Leere Frames bleiben vollstaendig transparent;
    # qtrle komprimiert gleiche Flaechen lauflaengencodiert, sie kosten also
    # kaum Platz.
    leer = Image.new("RGBA", (breite, hoehe), (0, 0, 0, 0))
    for i in range(n):
        t = i / fps
        aktiv = next((c for c in cues if c.ab <= t < c.bis), None)
        if aktiv is None:
            leer.save(rahmen / f"f{i:05d}.png")
            continue
        bild = Image.new("RGBA", (breite, hoehe), (0, 0, 0, 0))
        _zeichne_wort(bild, aktiv.text, conf, t - aktiv.ab)
        bild.save(rahmen / f"f{i:05d}.png")

    ziel.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(
        ["ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
         "-framerate", str(fps), "-i", str(rahmen / "f%05d.png"),
         "-c:v", "qtrle", str(ziel)],
        check=True)
    shutil.rmtree(rahmen)
    return ziel


# ---------------------------------------------------------------------------
# Bildstil
# ---------------------------------------------------------------------------

def _push_in(conf: dict, dauer: float, fps: int,
             breite: int, hoehe: int) -> str:
    """Langsame Kamerafahrt auf die Buehne.

    GEMESSEN an @berlinsf1nest/7651952960787828000: Der Ausschnitt wird ueber
    rund 4 s kontinuierlich enger, ohne Halt und ohne Ruck. Das ist der
    guenstigste Weg, ein statisches Bild lebendig aussehen zu lassen — die
    Quelle bleibt dieselbe, es bewegt sich nur der Rahmen.

    WARUM NICHT ``zoompan``: Der Filter rechnet in Bildnummern und rundet die
    Ausgabemasse auf ganze Pixel. Bei einer langsamen Fahrt springt das Bild
    dadurch sichtbar um einen Pixel — genau der Ruck, den es nicht geben
    soll. ``scale`` mit einem Zeitausdruck plus ``crop`` bleibt fliessend,
    weil skaliert und nicht ausgeschnitten wird.
    """
    ziel = float(conf.get("staerke", 1.08))     # Endvergroesserung
    if ziel <= 1.0 or dauer <= 0:
        return ""

    # Linear ueber die volle Cliplaenge. Ein Ease waere hier falsch: Die Fahrt
    # soll nicht auffallen, und jede Beschleunigung tut genau das.
    z = f"(1+({ziel}-1)*min(t/{dauer:.3f}\\,1))"
    return (f"scale=w='ceil({breite}*{z}/2)*2':h='ceil({hoehe}*{z}/2)*2':eval=frame,"
            f"crop={breite}:{hoehe}")


def panel_stil(conf: dict) -> str:
    """Farbe und Vignette **eines Panels**, als Kettenstueck ohne Labels.

    WARUM PRO PANEL UND NICHT AUF DER BUEHNE — gemessen am 2026-09-07, und
    zwar erst am gerenderten Frame, nicht an der Konfiguration:

    Die erste Fassung legte die Vignette auf die fertige Buehne. Bei einem
    gestapelten Template (``OME_SPLIT``, zwei Panels a 960 px) liegt deren
    Zentrum damit auf der **Naht** — also genau auf der Stelle, an der kein
    Inhalt ist. Das Helligkeitsprofil ueber die Bildhoehe war eindeutig:

        y≈937 (Naht)      146
        y≈1071 (Gesicht)   76
        y≈1339 (Gesicht)   51
        y≈1741             21

    Die Vignette machte also die leere Naht am hellsten und dunkelte die
    Gesichter um Faktor 7 ab. Im QC der Datei ist das nicht zu sehen: Dauer,
    Aufloesung und Tonspur stimmen.

    Pro Panel angewandt sitzt jedes Zentrum dort, wo auch das Bild ist. Der
    Preis ist eine Filterkette je Panel statt einer — das ist bei zwei bis
    drei Panels nicht messbar.

    Reihenfolge: erst Farbe, dann Vignette. Umgekehrt wuerde die Abdunklung
    von der Entsaettigung miterfasst und verloere ihre Tiefe.
    """
    if not conf or not conf.get("aktiv", False):
        return ""

    glieder = []
    farbe = conf.get("farbe") or {}
    saettigung = float(farbe.get("saettigung", 1.0))
    kontrast = float(farbe.get("kontrast", 1.0))
    helligkeit = float(farbe.get("helligkeit", 0.0))
    if (saettigung, kontrast, helligkeit) != (1.0, 1.0, 0.0):
        glieder.append(f"eq=saturation={saettigung}:contrast={kontrast}:"
                       f"brightness={helligkeit}")

    vig = conf.get("vignette") or {}
    if vig.get("aktiv"):
        # angle ist der Oeffnungswinkel: kleiner = dunklere Ecken.
        glieder.append(f"vignette=angle={float(vig.get('winkel', 0.9)):.3f}")

    return ",".join(glieder)


def buehnen_stil(conf: dict, dauer: float, fps: int,
                 breite: int, hoehe: int) -> str:
    """Was auf der **fertigen Buehne** liegt: die Kamerafahrt.

    Sie gehoert hierher und nicht ins Panel: Eine Fahrt, die nur ein Panel
    erfasst, sieht aus wie ein Fehler im Layout. Ueber die ganze Buehne ist
    sie eine Kamera, die auf das Bild zugeht.
    """
    if not conf or not conf.get("aktiv", False):
        return ""
    return _push_in(conf.get("push_in") or {}, dauer, fps, breite, hoehe)
