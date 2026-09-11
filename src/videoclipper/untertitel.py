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

import json
import re
from dataclasses import dataclass
from pathlib import Path

from PIL import Image, ImageDraw

from .headline import font as _font, umbruch
from .transcript import Transkript, Wort

ROOT = Path(__file__).resolve().parents[2]
KORREKTUREN = ROOT / "data" / "korrekturen"


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
    #
    # Ein Wort, das VOR dem Clip beginnt, gehoert nicht hinein. GEMESSEN am
    # 2026-09-11 an saiJDq9DM_Y: "Sternen," war 0.1 s vor dem Clipanfang zu
    # Ende gesprochen, sein Transkriptende reicht aber bis zum naechsten Wort —
    # der erste Cue lautete "Sternen, ob Sydney Friede", obwohl im Ton nur
    # "ob Sidney Friede" zu hoeren ist. Die Toleranz faengt Rundung ab.
    woerter = [w for w in tr.woerter
               if start - 0.05 <= w.start < ende and not w.ist_marker
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
    # Wurde das erste Wort einer Gruppe vom Fensteranfang abgeschnitten?
    angeschnitten = [g[0].start < start for g in gruppen]

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
            # GEMESSEN am 2026-09-11 an saiJDq9DM_Y: Seit ``snappe`` am echten
            # Wortende schneidet, ist der kurze letzte Cue oft kein Fetzen des
            # naechsten Satzes mehr, sondern das letzte Wort selbst, dessen
            # Transkriptende weit hinter dem Clip liegt — "passen.",
            # "verschieben.", "angreifen.". Weggeworfen fehlte in vier von acht
            # Clips genau das Wort der Pointe. Laeuft die Rede ohne Satzende in
            # ihn hinein, gehoert er an den Cue davor; nur ein neuer Satz
            # bleibt draussen.
            vorher = cues[-1] if cues else None
            if (vorher is not None and not _satzende(vorher.text.split()[-1])
                    and c.ab - vorher.bis < pause):
                cues[-1] = Cue(f"{vorher.text} {c.text}", vorher.ab, round(bis, 3))
            continue
        # SPIEGELBILDLICH DAZU, gemessen am 2026-09-08 an ErYc_3POazo: Derselbe
        # Fetzen entsteht am ANFANG. ``snappe`` setzt 0.20 s Vorlauf, und bei
        # durchgehender Rede liegt darin das Ende des vorigen Satzes — der Clip
        # begann mit dem Cue "kann." fuer 0.2 s. Dehnen kann ``min_dauer`` ihn
        # nicht: Die Grenze ist der naechste Cue, nicht das Fensterende. Der
        # Zuschauer liest in der ersten Sekunde also ein Wort ohne Satz, und
        # genau die erste Sekunde entscheidet (siehe Kopf dieses Moduls).
        if i == 0 and angeschnitten[0] and bis - c.ab < min_dauer:
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


# ---------------------------------------------------------------------------
# Handkorrekturen — SCHNITTREGELN.md, Regel 4 ("korrekt sind")
# ---------------------------------------------------------------------------
#
# YouTubes ASR verschreibt sich bei Namen, Fremdwoertern und vor allem bei
# Stotterern: Aus "Mein Hund kann mir auf'n Ruecken tragen" wurde bei
# ErYc_3POazo "Mein Hund kann mein Hand mein Hund kann". Als Untertitel ist
# das schlicht falsch, und es steht im fertigen Clip in Versalien quer ueber
# dem Bild.
#
# KORRIGIERT WIRD DER CUE, NICHT DAS TRANSKRIPT. Das Transkript traegt die
# Zeitachse — Snapping, Kandidaten und Hookpruefung haengen daran. Ein Eingriff
# dort verschoebe Clipgrenzen, nur um einen Buchstaben zu aendern. Der Cue ist
# das Ende der Kette und beeinflusst nichts mehr.
#
# PREIS DIESER ENTSCHEIDUNG: Eine Regel greift nur, wenn die gesuchte Stelle
# vollstaendig in EINEM Cue liegt. Ueber eine Cuegrenze hinweg greift sie
# nicht — deshalb meldet ``pruefe_korrekturen`` jede Regel, die nicht gegriffen
# hat, statt sie still verfallen zu lassen.

def regeln(video_id: str) -> list[dict]:
    """Korrekturregeln zu einem Video, falls hinterlegt."""
    datei = KORREKTUREN / f"{video_id}.json"
    if not datei.exists():
        return []
    daten = json.loads(datei.read_text(encoding="utf-8"))
    return list(daten.get("regeln") or [])


def _ersetze(text: str, regel: dict) -> str:
    return re.sub(re.escape(regel["suche"]), regel["ersetze"], text,
                  flags=re.IGNORECASE)


def korrigiere(cues: list[Cue], video_id: str) -> tuple[list[Cue], set[int]]:
    """Regeln auf die Cues anwenden. Gibt die Nummern zurueck, die gegriffen haben.

    NICHT die Meldungen: Die Regeln gelten fuer ein VIDEO, ein Renderlauf
    schneidet daraus mehrere Clips. Eine Regel fuer Clip 3 greift in Clip 1
    naturgemaess nicht — je Clip gemeldet ergab das bei 22 Regeln und 4 Clips
    rund 60 Zeilen Rauschen, in dem die eine echte Fehlmeldung unterging.
    Wer die Regeln auswertet, muss deshalb ueber den ganzen Lauf zaehlen; das
    tut ``ungenutzte``.
    """
    rs = regeln(video_id)
    if not rs:
        return cues, set()

    getroffen: set[int] = set()
    raus: list[Cue] = []
    for c in cues:
        text = c.text
        for i, r in enumerate(rs):
            neu = _ersetze(text, r)
            if neu != text:
                getroffen.add(i)
                text = neu
        raus.append(Cue(text, c.ab, c.bis) if text != c.text else c)
    return raus, getroffen


def ungenutzte(video_id: str, getroffen: set[int]) -> list[str]:
    """Regeln, die im ganzen Lauf nirgends gegriffen haben.

    Das ist der Fall, der eine Meldung verdient: Die Regel ist falsch
    geschrieben, oder die Stelle liegt ueber einer Cuegrenze und wird deshalb
    nie gefunden. Still verfallen darf sie nicht — dann steht der falsche Text
    im Clip und niemand merkt es.
    """
    rs = regeln(video_id)
    return [f"Korrekturregel ohne Treffer: {r['suche']!r} — falsch geschrieben, "
            f"oder steht sie ueber einer Cuegrenze?"
            for i, r in enumerate(rs) if i not in getroffen]


def korrigiere_text(text: str, video_id: str) -> str:
    """Dieselben Regeln auf einen Fliesstext statt auf Cues.

    Fuer Pruefungen, die den Wortlaut des Clips lesen (``hook.pruefe``). Die
    sollen mit dem vergleichen, was der Zuschauer liest — und das ist der
    korrigierte Untertitel, nicht YouTubes Schreibweise.
    """
    for r in regeln(video_id):
        text = _ersetze(text, r)
    return text
