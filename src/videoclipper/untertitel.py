"""Stage 11a — Untertitel. Pflicht in jedem Clip.

WARUM UEBERHAUPT: Shorts laufen bei den meisten Zuschauern stumm an. Ohne Text
ist die erste Sekunde leer, und die erste Sekunde entscheidet.

WARUM KEIN KARAOKE: Zwei Gruende, beide hart. Erstens hat der FFmpeg-Build auf
dem MacBook weder libass noch drawtext — der Textpfad ist hier ausschliesslich
PNG-Overlay. Zweitens ist Karaoke nicht der gemessene Hausstil; die Headline
steht laut Materialanalyse pixelgleich ueber die volle Cliplaenge.

WIE DIE ANIMATION MIT WENIG AUFWAND ENTSTEHT: Genauso wie die Countdown-Liste
— ein Standbild je Cue, eingeblendet ueber ``enable``. Der Ruck nach oben beim
Cue-Wechsel steckt komplett im ``y``-Ausdruck des ``overlay``-Filters, den es
ohnehin gibt. Es gibt also kein zusaetzliches Bild und keinen zusaetzlichen
Filter fuer die Animation: sie kostet nichts ausser diesem Ausdruck.

Alternativen, die verworfen wurden, weil sie je Cue ein zweites Bild oder einen
zweiten Filter gebraucht haetten: Einblenden ueber Alpha (``fade`` animiert auf
einem Einzelbild nicht), Pop ueber ``scale`` (Ausdruck je Frame neu skaliert),
Wortmarkierung (ein PNG je Wort statt je Cue, rund viermal so viele Eingaenge).
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from PIL import Image, ImageDraw

from .headline import font as _font, umbruch
from .transcript import Transkript, Wort


@dataclass(frozen=True)
class Cue:
    """Ein Untertitel. Zeiten relativ zum Clipbeginn, nicht zum Video."""
    text: str
    ab: float
    bis: float


def band(tmpl: dict) -> tuple[int, int]:
    """Obere Kante und Hoehe des Untertitelbandes auf der Canvas.

    Bricht ab, wenn das Band in TikToks UI-Zone laeuft. Das ist derselbe
    Fehler wie eine ungerade Panelhoehe: im QC der fertigen Datei nicht zu
    sehen, im Feed aber halb verdeckt.
    """
    conf = tmpl["untertitel"]
    _, hoehe = tmpl["canvas"]
    band_hoehe = int(conf["band_hoehe"])
    oben = int(conf["y"]) - band_hoehe // 2

    unten_frei = hoehe - int((tmpl.get("sicherheitszone") or {}).get("unten", 0))
    if oben + band_hoehe > unten_frei:
        raise ValueError(
            f"{tmpl['name']}: Untertitelband endet bei y={oben + band_hoehe}, "
            f"die UI-Zone beginnt bei y={unten_frei}")
    if oben < 0:
        raise ValueError(f"{tmpl['name']}: Untertitelband beginnt bei y={oben}")
    return oben, band_hoehe


def _satzende(wort: str) -> bool:
    """Endet dieses Wort einen Satz?

    Mindestens zwei Zeichen vor dem Punkt, sonst brechen Initialen ("Maus L.")
    und Ordnungszahlen mitten in der Zeile.
    """
    w = wort.strip()
    return len(w) > 2 and w[-1] in ".!?…"


def schneide(tr: Transkript, start: float, ende: float, conf: dict) -> list[Cue]:
    """Woerter des Clipfensters in lesbare Cues gruppieren.

    Gebrochen wird an der ersten reissenden Grenze: Sprechpause, Satzende,
    Zeichenzahl oder Standzeit. Das Satzende steht bewusst vor der
    Zeichenzahl — sonst laufen zwei Saetze in eine Zeile und der naechste
    Cue beginnt mit dem Rest des vorigen. Ein Cue haelt danach bis zum naechsten, hoechstens aber
    ``max_halten`` Sekunden — sonst steht der Satz noch im Bild, wenn laengst
    etwas anderes passiert.
    """
    satzende = bool(conf.get("satzende", True))
    max_zeichen = int(conf.get("max_zeichen", 42))
    max_dauer = float(conf.get("max_dauer", 2.2))
    pause = float(conf.get("pause", 0.45))
    min_dauer = float(conf.get("min_dauer", 0.6))
    max_halten = float(conf.get("max_halten", 0.9))

    # ``[gelaechter]`` und Geschwister sind Annotationen von YouTube, keine
    # gesprochenen Woerter. Als Untertitel gesetzt waeren sie schlicht falsch.
    woerter = [w for w in tr.woerter
               if w.start < ende and w.ende > start and not w.ist_marker
               and w.text.strip()]

    gruppen: list[list[Wort]] = []
    for w in woerter:
        if not gruppen:
            gruppen.append([w])
            continue
        aktuell = gruppen[-1]
        bisher = " ".join(x.text.strip() for x in aktuell)
        reisst = (
            w.start - aktuell[-1].ende >= pause
            or (satzende and _satzende(aktuell[-1].text))
            or len(bisher) + 1 + len(w.text.strip()) > max_zeichen
            or w.ende - aktuell[0].start > max_dauer
        )
        (gruppen.append([w]) if reisst else aktuell.append(w))

    roh = [Cue(" ".join(x.text.strip() for x in g),
               max(g[0].start, start) - start,
               min(g[-1].ende, ende) - start)
           for g in gruppen]

    cues: list[Cue] = []
    fenster = ende - start
    for i, c in enumerate(roh):
        letzter = i + 1 == len(roh)
        grenze = fenster if letzter else roh[i + 1].ab
        bis = min(max(c.bis, c.ab + min_dauer), c.bis + max_halten, grenze, fenster)
        if bis - c.ab <= 0.05:            # vom Fensterrand zerdrueckt
            continue
        # GEMESSEN am 2026-09-07 an utB7GTrmLYY: Drei von acht Clips endeten auf
        # einem 0.35-s-Fetzen ("E ich", "Ja, ich habe"). Ursache ist der
        # Nachlauf aus ``snappe`` — er haengt 0.35 s an, und bei durchgehender
        # Rede faengt darin schon das naechste Wort an. Mitten im Clip kann
        # ``min_dauer`` einen kurzen Cue noch dehnen; am Fensterrand ist dafuer
        # kein Platz, deshalb blitzt der Fetzen genau so lange auf, wie er lang
        # ist. Lesbar ist das nicht, und es sieht aus, als sei mitten im Satz
        # abgeschnitten worden.
        #
        # Verworfen: den Clip bis zur naechsten Wortgrenze verlaengern. Das
        # verschiebt die Grenze, die Stage 06 bewusst gesetzt hat, und laeuft
        # bei diesem Material in den naechsten Gespraechspartner.
        if letzter and bis >= fenster - 1e-6 and bis - c.ab < min_dauer:
            continue
        cues.append(Cue(c.text, round(c.ab, 3), round(bis, 3)))
    return cues


def baue(cues: list[Cue], tmpl: dict, ordner: Path, clip_id: str) -> list[Path]:
    """Ein PNG je Cue, nur so hoch wie das Band.

    Nicht in Canvasgroesse: Bei 40 Cues waeren das 40 x 1080x1920 RGBA im
    Speicher des Encoders. Das Band ist ein Achtel davon und liegt ohnehin
    immer an derselben x-Position.
    """
    conf = tmpl["untertitel"]
    breite, _ = tmpl["canvas"]
    _, band_hoehe = band(tmpl)

    max_breite = int(conf.get("max_breite", breite - 120))
    max_zeilen = int(conf.get("max_zeilen", 2))
    rand = int(conf.get("rand_staerke", 8))
    farbe = conf.get("farbe", "#FFFFFF")
    rand_farbe = conf.get("rand_farbe", "#000000")
    versalien = bool(conf.get("versalien", True))

    ordner.mkdir(parents=True, exist_ok=True)
    pfade: list[Path] = []

    for i, cue in enumerate(cues):
        text = cue.text.upper() if versalien else cue.text
        bild = Image.new("RGBA", (breite, band_hoehe), (0, 0, 0, 0))
        zeichner = ImageDraw.Draw(bild)

        # Wie bei der Headline: verkleinern, bis der Text in die Zeilen passt.
        groesse = int(conf["schriftgroesse"])
        while groesse > 28:
            schrift = _font(conf, groesse)
            zeilen = umbruch(text, schrift, max_breite, zeichner, max_zeilen + 1)
            if len(zeilen) <= max_zeilen and all(
                    zeichner.textlength(z, font=schrift) <= max_breite
                    for z in zeilen):
                break
            groesse -= 2
        else:
            schrift = _font(conf, groesse)
            zeilen = umbruch(text, schrift, max_breite, zeichner, max_zeilen)

        zh = int(groesse * 1.16)
        oben = (band_hoehe - zh * len(zeilen)) // 2
        for z, zeile in enumerate(zeilen):
            zeichner.text((breite // 2, oben + z * zh + zh // 2), zeile,
                          font=schrift, fill=farbe, stroke_width=rand,
                          stroke_fill=rand_farbe, anchor="mm")

        ziel = ordner / f"{clip_id}.ut{i:03d}.png"
        bild.save(ziel)
        pfade.append(ziel)

    return pfade


def y_ausdruck(cue: Cue, oben: int, conf: dict) -> str:
    """Der animierte ``y``-Wert fuer genau diesen Cue.

    Der Cue faehrt aus ``hub`` Pixeln von unten in seine Lage, quadratisch
    gedaempft (schnell los, weich an). ``max``/``min`` klemmen den Fortschritt
    auf 0..1, damit Randframes ausserhalb des ``enable``-Fensters nichts
    Wildes rechnen.
    """
    a = conf.get("animation") or {}
    d = float(a.get("dauer", 0.14))
    hub = int(a.get("hub", 26))
    if d <= 0 or hub == 0:
        return str(oben)
    p = f"max(min((t-{cue.ab:.3f})/{d:.3f},1),0)"
    return f"{oben}+{hub}*pow(1-{p},2)"
