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

# ---------------------------------------------------------------------------
# Emoji in der Headline — SCHNITTREGELN.md, Regel 3
# ---------------------------------------------------------------------------
#
# Anton hat keine Emoji-Glyphen; ohne Sonderbehandlung landet ein leeres
# Kaestchen im fertigen Clip (gemessen am ersten Lauf von ErYc_3POazo).
#
# WARUM PNG UND KEIN FONT: Ein Emoji-Font ist plattformabhaengig — auf dem Mac
# "Apple Color Emoji.ttc", auf Windows "seguiemj.ttf" —, und CLAUDE.md haelt
# die Zahl der plattformabhaengigen Stellen bewusst bei drei. Regel 3 laesst
# genau VIER Emojis zu, also ist die Menge endlich: Sie liegen als PNG in
# assets/emoji/ und wandern wie Anton mit dem Repo. Einmal auf einem Rechner
# gerendert, danach auf beiden Maschinen pixelgleich.
#
# Alle vier sind auf eine gemeinsame 160x160-Box normalisiert, damit sie in
# einer Zeile auf derselben Grundlinie stehen.
EMOJI_DIR = ROOT / "assets" / "emoji"
EMOJI = {"\U0001f940": "1f940",   # 🥀 welke Rose
         "\U0001fae9": "1fae9",   # 🫩 Gesicht mit Augenringen
         "\U0001f480": "1f480",   # 💀 Totenkopf
         "\U0001f64f": "1f64f"}   # 🙏 gefaltete Haende
EMOJI_ABSTAND = 0.14               # Anteil der Glyphenbreite als Luecke


def _zerlege(text: str) -> tuple[str, list[str]]:
    """Trennt den Wortlaut von den Emojis.

    Regel 3 setzt sie ans Ende; gefunden werden sie trotzdem ueberall, damit
    eine falsch gesetzte Headline nicht als Kaestchen rendert. ``hook.stil``
    meldet die Fehlstellung getrennt — hier wird nur gezeichnet.
    """
    rumpf = "".join(z for z in text if z not in EMOJI)
    codes = [EMOJI[z] for z in text if z in EMOJI]
    return " ".join(rumpf.split()), codes


def _emoji_bild(code: str, kante: int) -> Image.Image:
    datei = EMOJI_DIR / f"{code}.png"
    if not datei.exists():
        raise FileNotFoundError(f"Emoji fehlt: {datei}")
    return Image.open(datei).convert("RGBA").resize((kante, kante), Image.LANCZOS)


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
    text, emojis = _zerlege(text)
    if conf.get("versalien", True):
        text = text.upper()

    bild = Image.new("RGBA", (breite, hoehe), (0, 0, 0, 0))
    zeichner = ImageDraw.Draw(bild)
    max_breite = conf.get("max_breite", breite - 80)
    max_zeilen = conf.get("max_zeilen", 2)

    rand = conf.get("rand_staerke", 9)

    def emoji_luecke(g: int) -> int:
        """Abstand vor jedem Emoji.

        Der Rand der Schrift zaehlt mit: ``textlength`` misst die Glyphen, der
        schwarze Rand steht aber darueber hinaus. Ohne ihn klebt das erste
        Emoji am letzten Buchstaben — gemessen am ersten Lauf.
        """
        return int(g * 0.92 * EMOJI_ABSTAND) + rand

    def emoji_breite(g: int) -> int:
        """Platz, den der Emojiblock in der letzten Zeile braucht."""
        if not emojis:
            return 0
        return len(emojis) * (int(g * 0.92) + emoji_luecke(g))

    # Groesse so weit reduzieren, bis der Text in die erlaubten Zeilen passt.
    # Die letzte Zeile traegt zusaetzlich den Emojiblock — sonst laeuft die
    # Headline ueber max_breite hinaus, und das faellt erst im Bild auf.
    groesse = conf["schriftgroesse"]
    while groesse > 24:
        schrift = font(conf, groesse)
        zeilen = umbruch(text, schrift, max_breite - emoji_breite(groesse),
                         zeichner, max_zeilen + 1)
        if len(zeilen) <= max_zeilen and all(
                zeichner.textlength(z, font=schrift)
                + (emoji_breite(groesse) if i == len(zeilen) - 1 else 0)
                <= max_breite for i, z in enumerate(zeilen)):
            break
        groesse -= 2
    else:
        schrift = font(conf, groesse)
        zeilen = umbruch(text, schrift, max_breite - emoji_breite(groesse),
                         zeichner, max_zeilen)

    zh = int(groesse * 1.12)
    gesamt = zh * len(zeilen)
    y = conf["y"] - gesamt // 2          # auf der Naht zentriert

    eb = emoji_breite(groesse)
    for i, zeile in enumerate(zeilen):
        letzte = i == len(zeilen) - 1
        # Nur die letzte Zeile teilt sich die Breite mit dem Emojiblock; ihre
        # Textmitte rueckt deshalb um dessen halbe Breite nach links.
        mitte = breite // 2 - (eb // 2 if letzte else 0)
        zeichner.text(
            (mitte, y + i * zh + zh // 2), zeile, font=schrift,
            fill=conf.get("farbe", "#FFFFFF"),
            stroke_width=rand, stroke_fill=conf.get("rand_farbe", "#000000"),
            anchor="mm",
        )
        if letzte and emojis:
            kante, luecke = int(groesse * 0.92), emoji_luecke(groesse)
            x = mitte + int(zeichner.textlength(zeile, font=schrift)) // 2 + luecke
            oben = y + i * zh + zh // 2 - kante // 2
            for code in emojis:
                bild.alpha_composite(_emoji_bild(code, kante), (x, oben))
                x += kante + luecke

    ziel.parent.mkdir(parents=True, exist_ok=True)
    bild.save(ziel)
    return ziel
