"""Die Countdown-Liste als Folge von PNG-Overlays.

Ein Zustand pro Segment: die Ziffern 1..n stehen von Anfang an, die
Beschriftungen kommen nacheinander dazu. Weil sich das Bild nur an den
Segmentgrenzen aendert, reichen n Standbilder — genauso wie bei der Headline
ein einziges reicht. Kein libass, kein drawtext, auf beiden Rechnern gleich.
"""

from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

from .headline import font as _font


def _passend(text: str, conf: dict, zeichner: ImageDraw.ImageDraw
             ) -> ImageFont.FreeTypeFont:
    """Groesse so weit senken, bis die Zeile in die erlaubte Breite passt."""
    groesse = conf["schriftgroesse"]
    max_breite = conf.get("max_breite", 820)
    while groesse > 20:
        font = _font(conf, groesse)
        if zeichner.textlength(text, font=font) <= max_breite:
            return font
        groesse -= 2
    return _font(conf, groesse)


def baue_zustand(sichtbar: dict[int, str], tmpl: dict, ziel: Path) -> Path:
    """Ein transparentes PNG in Canvasgroesse fuer genau einen Listenzustand.

    ``sichtbar`` bildet Platz -> Text ab. Nicht enthaltene Plaetze bekommen
    trotzdem ihre Ziffer, aber keinen Text: das leere Geruest ist der Hook.
    """
    conf = tmpl["liste"]
    breite, hoehe = tmpl["canvas"]
    bild = Image.new("RGBA", (breite, hoehe), (0, 0, 0, 0))
    zeichner = ImageDraw.Draw(bild)

    rand = conf.get("rand_staerke", 8)
    farbe = conf.get("farbe", "#FFFFFF")
    rand_farbe = conf.get("rand_farbe", "#000000")
    versalien = conf.get("versalien", False)

    for i in range(conf["plaetze"]):
        platz = i + 1
        y = conf["erste_zeile_y"] + i * conf["zeilenabstand"]

        ziffer_font = _font(conf, conf["schriftgroesse"])
        zeichner.text((conf["ziffer_x"], y), f"{platz}.", font=ziffer_font,
                      fill=farbe, stroke_width=rand, stroke_fill=rand_farbe,
                      anchor="mm")

        text = sichtbar.get(platz)
        if not text:
            continue
        if versalien:
            text = text.upper()
        font = _passend(text, conf, zeichner)
        zeichner.text((conf["text_x"], y), text, font=font, fill=farbe,
                      stroke_width=rand, stroke_fill=rand_farbe, anchor="mm")

    ziel.parent.mkdir(parents=True, exist_ok=True)
    bild.save(ziel)
    return ziel


def baue_alle(plan, tmpl: dict, ordner: Path) -> list[Path]:
    """Ein PNG je Segment, in Abspielreihenfolge."""
    texte = {e.platz: e.text for e in plan.eintraege}
    pfade = []
    for seg in plan.aufgeloest.segmente:
        sichtbar = {p: texte[p] for p in seg["sichtbar"]}
        pfade.append(baue_zustand(
            sichtbar, tmpl, ordner / f"{plan.clip_id}.liste{seg['index']}.png"))
    return pfade
