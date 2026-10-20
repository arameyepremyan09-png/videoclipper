"""Die Countdown-Liste als Folge von PNG-Overlays.

Ein Zustand pro Segment: die Ziffern 1..n stehen von Anfang an, die
Beschriftungen kommen nacheinander dazu. Weil sich das Bild nur an den
Segmentgrenzen aendert, reichen n Standbilder — genauso wie bei der Headline
ein einziges reicht. Kein libass, kein drawtext, auf beiden Rechnern gleich.
"""

from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

from .headline import EMOJI, EMOJI_ABSTAND, _emoji_bild, _zerlege
from .headline import font as _font


def _emoji_masse(conf: dict, groesse: int, anzahl: int) -> tuple[int, int, int]:
    """(Kante, Luecke davor, Breite des ganzen Blocks) fuer ``anzahl`` Emojis.

    In der Liste stehen Emojis groesser als in der Headline: In den
    HallOfClips-Referenzen misst der Totenkopf 70 px gegen 43 px Ziffernhoehe.
    """
    if not anzahl:
        return 0, 0, 0
    kante = int(groesse * conf.get("emoji_faktor", 0.92))
    luecke = int(kante * EMOJI_ABSTAND) + conf.get("rand_staerke", 8)
    return kante, luecke, anzahl * (kante + luecke)


def _pruefe_zeichen(text: str) -> None:
    """Ein Emoji ohne PNG rendert Anton als leeres Kaestchen — lieber abbrechen.

    Die Referenzen nutzen auch 😭 und 🧀; ``assets/emoji/`` traegt nur die vier
    aus Regel 3. Das faellt sonst erst im fertigen Clip auf (CLAUDE.md,
    "Anton hat keine Emoji-Glyphen").
    """
    fremd = sorted({z for z in text if ord(z) >= 0x2000 and z not in EMOJI
                    and not 0xFE00 <= ord(z) <= 0xFE0F})
    if fremd:
        raise ValueError(f"Kein Emoji-PNG fuer {' '.join(fremd)} in {text!r} — "
                         f"vorhanden: {' '.join(EMOJI)}")


def _passend(text: str, anzahl_emoji: int, conf: dict,
             zeichner: ImageDraw.ImageDraw) -> tuple[ImageFont.FreeTypeFont, int]:
    """Groesse so weit senken, bis Zeile samt Emojis in die erlaubte Breite passt."""
    groesse = conf["schriftgroesse"]
    max_breite = conf.get("max_breite", 820)
    while groesse > 20:
        font = _font(conf, groesse)
        _, _, eb = _emoji_masse(conf, groesse, anzahl_emoji)
        if zeichner.textlength(text, font=font) + eb <= max_breite:
            return font, groesse
        groesse -= 2
    return _font(conf, groesse), groesse


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
        _pruefe_zeichen(text)
        text, emojis = _zerlege(text)
        if versalien:
            text = text.upper()
        font, groesse = _passend(text, len(emojis), conf, zeichner)
        kante, luecke, eb = _emoji_masse(conf, groesse, len(emojis))
        # Text und Emojis stehen als Gruppe mittig auf text_x, wie in den
        # Referenzen; ohne Emojis ist das dieselbe Lage wie bisher.
        mitte = conf["text_x"] - eb // 2
        zeichner.text((mitte, y), text, font=font, fill=farbe,
                      stroke_width=rand, stroke_fill=rand_farbe, anchor="mm")
        x = int(mitte + zeichner.textlength(text, font=font) / 2) + luecke
        for code in emojis:
            bild.alpha_composite(_emoji_bild(code, kante), (x, int(y - kante / 2)))
            x += kante + luecke

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
