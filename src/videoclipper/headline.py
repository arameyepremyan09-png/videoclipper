"""Headline als PNG-Overlay.

Das Blueprint sieht ASS via libass vor, weil ``drawtext`` auf dem Windows-Rechner
an fehlendem fontconfig scheitert. Der FFmpeg-Build auf diesem Mac hat *weder*
libass *noch* drawtext (kein --enable-libass, kein --enable-libfreetype), damit
ist der vorgesehene Pfad hier nicht verfuegbar.

Weil die Headline laut Materialanalyse ueber die volle Cliplaenge pixelgleich
steht, ist ein einzelnes PNG funktional dasselbe wie ein einzelnes ASS-Event —
und es haengt an keiner FFmpeg-Buildoption, also auf beiden Rechnern identisch.
"""

from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parents[2]
SCHRIFTEN = ROOT / "assets" / "fonts"


def font(conf: dict, groesse: int) -> ImageFont.FreeTypeFont:
    """Schriftdatei aus einem Konfigurationsblock. Fehlt sie, ist das ein Fehler."""
    datei = SCHRIFTEN / f"{conf['schrift']}-Regular.ttf"
    if not datei.exists():
        raise FileNotFoundError(f"Schrift fehlt: {datei}")
    return ImageFont.truetype(str(datei), groesse)


def umbruch(text: str, font: ImageFont.FreeTypeFont, max_breite: int,
            zeichner: ImageDraw.ImageDraw, max_zeilen: int) -> list[str]:
    woerter, zeilen, aktuell = text.split(), [], ""
    for w in woerter:
        probe = f"{aktuell} {w}".strip()
        if zeichner.textlength(probe, font=font) <= max_breite or not aktuell:
            aktuell = probe
        else:
            zeilen.append(aktuell)
            aktuell = w
    if aktuell:
        zeilen.append(aktuell)
    return zeilen[:max_zeilen]


def baue(text: str, tmpl: dict, ziel: Path) -> Path:
    """Erzeugt ein transparentes PNG in Canvasgroesse mit der gesetzten Headline."""
    conf = tmpl["headline"]
    breite, hoehe = tmpl["canvas"]
    if conf.get("versalien", True):
        text = text.upper()

    bild = Image.new("RGBA", (breite, hoehe), (0, 0, 0, 0))
    zeichner = ImageDraw.Draw(bild)
    max_breite = conf.get("max_breite", breite - 80)
    max_zeilen = conf.get("max_zeilen", 2)

    # Groesse so weit reduzieren, bis der Text in die erlaubten Zeilen passt.
    groesse = conf["schriftgroesse"]
    while groesse > 24:
        schrift = font(conf, groesse)
        zeilen = umbruch(text, schrift, max_breite, zeichner, max_zeilen + 1)
        if len(zeilen) <= max_zeilen and all(
                zeichner.textlength(z, font=schrift) <= max_breite for z in zeilen):
            break
        groesse -= 2
    else:
        schrift = font(conf, groesse)
        zeilen = umbruch(text, schrift, max_breite, zeichner, max_zeilen)

    rand = conf.get("rand_staerke", 9)
    zh = int(groesse * 1.12)
    gesamt = zh * len(zeilen)
    y = conf["y"] - gesamt // 2          # auf der Naht zentriert

    for i, zeile in enumerate(zeilen):
        zeichner.text(
            (breite // 2, y + i * zh + zh // 2), zeile, font=schrift,
            fill=conf.get("farbe", "#FFFFFF"),
            stroke_width=rand, stroke_fill=conf.get("rand_farbe", "#000000"),
            anchor="mm",
        )

    ziel.parent.mkdir(parents=True, exist_ok=True)
    bild.save(ziel)
    return ziel
