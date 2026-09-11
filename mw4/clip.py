#!/usr/bin/env python3
"""MW4-Kampagne: Stringout-Reels zu fertigen 9:16-Clips schneiden.

Eigenstaendiges Werkzeug, bewusst getrennt von der Reaction-Pipeline im
uebrigen Repo: Dieses Material hat kein Transkript, keine Sprache und keine
Layoutwechsel, dafuer aber Pflichtelemente aus einem Kampagnenvertrag. Von
dort uebernommen ist nur das Handwerk (PNG-Overlays statt drawtext, weil der
FFmpeg-Build auf dieser Maschine weder libass noch libfreetype hat).

Gemessen am 2026-09-08 an MW4_BetaTopPlays_Stringout_16X9_R1.mp4:
1920x1080, 59.94 fps, 248.8 s, 31 Szenen.
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
from dataclasses import dataclass, asdict
from datetime import datetime
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont, ImageFilter

# ---------------------------------------------------------------------------
# Kampagnenvertrag - diese Werte sind vorgegeben, nicht gewaehlt
# ---------------------------------------------------------------------------

PFLICHT_ZEILE_1 = "MW4 OPEN BETA"      # eine der beiden Pflichtphrasen
PFLICHT_ZEILE_2 = "THIS WEEKEND"       # die andere
MIN_DAUER = 10.0                       # "Video must be AT LEAST 10 seconds long"
SICHERHEIT = 0.5                       # Puffer darauf; exakt 10.0 ist zu knapp,
                                       # wenn eine Plattform beim Transcodieren
                                       # auf ganze Frames rundet
RAND = 0.25                            # Abstand zur Schnittkante: der erste und
                                       # letzte Frame traegt oft den Uebergang

CAPTION_PFLICHTSATZ = ("Pre-order Modern Warfare 4 today and play day one, "
                       "October 23rd")
CAPTION_TAG = "@callofduty"
CAPTION_FTC = "#Ad"                    # allein auf eigener Zeile, erstes Element
CAPTION_HASHTAGS = "#ModernWarfare4 #MW4 #CallOfDuty"   # max. 3 zusaetzliche

# ---------------------------------------------------------------------------
# Zielkomposition - gemessen, siehe Kopf
# ---------------------------------------------------------------------------

CANVAS_B, CANVAS_H = 1080, 1920

# WARUM DAS BILD NICHT DEN GANZEN RAHMEN FUELLT.
#
# Bei 9:16 begrenzt die Hoehe der Quelle, nicht ihre Breite: aus 1080 Zeilen
# ist ein formatfuellender Ausschnitt hoechstens 608 px breit, und der muss
# auf 1080 hochgezogen werden - Faktor 1.8, also rund 80 % erfundene Pixel.
# Das ist Geometrie und keine Encodereinstellung; CRF und Bitrate aendern
# daran nichts.
#
# Gemessen am 2026-09-08: 864 px Breite brauchen nur noch Faktor 1.25. Das
# Bild steht dann als 1080x1295 im Rahmen, oben und unten bleibt Platz - und
# der ist nicht tot, dort stehen ohnehin Pflichttext und Logo.
CROP_B, CROP_H, CROP_X, CROP_Y = 864, 1036, 528, 44
BILD_B, BILD_H, BILD_Y = 1080, 1295, 280

# Die 44 px oben schneiden die Telemetriezeile des Aufnahmerechners weg
# (FPS/GPU/Latenz, gemessen bis x=1201 und damit bis in die Bildmitte).
# Links bleibt die Facecam des fremden Streamers draussen: gemessen endet
# sie bei x=483, der Ausschnitt beginnt bei 528. Der Sub-Goals-Text reicht
# weiter (bis x=605) und laege damit im Bild - deshalb muessen die
# Streamer-Abschnitte ueber AUSSCHLUSS herausfallen, nicht ueber die Geometrie.
#
# Alle Kantenmasse sind gerade. In yuv420p rundet der Scaler ungerade Masse
# still ab und verschiebt damit den ganzen Ausschnitt.

# Zeitbereiche, die nicht in Clips landen duerfen - je Video gemessen, nicht
# geraten. Erkannt wird visuell an einem Kontaktbogen; eine Signatur dafuer
# scheiterte messbar (Facecam dunkel auf dunklem Grund, Sub-Goals
# halbtransparent ueber bewegtem Bild).
AUSSCHLUSS: dict[str, list[tuple[float, float]]] = {
    "MW4_BetaTopPlays_Stringout_16X9_R1": [
        (196.0, 215.0),    # Facecam + Sub-Goals eines fremden Streamers
        (233.0, 249.0),    # HUD und Figurenuntertitel auf Chinesisch; die
                           # Kampagne verlangt englischen Content. Bis 232.5 s
                           # gemessen englisch, ab 234.0 s durchgehend chinesisch.
    ],
}

# Zielaenge eines Clips. Die Kampagne verlangt einen Schnitt statt Rohmaterial
# ("edit the source footage into polished clips") - benachbarte Spielmomente
# duerfen also in einen Clip, die harten Schnitte dazwischen sind der Edit.
ZIEL_MIN, ZIEL_MAX = 25.0, 45.0

UI_ZONE_UNTEN = 192        # TikTok verdeckt hier Caption, Buttons, Soundzeile

LOGO_BREITE = 300
TEXT_Y = 15
# Schaerfung nach dem Skalieren. Gemessen sichtbar an Kanten (Helm, Waffe,
# Gelaender), ohne die Halos, die staerkere Werte erzeugen.
SCHAERFE = "unsharp=5:5:0.7:5:5:0.0"

ENCODER = ["-c:v", "libx264", "-crf", "18", "-preset", "medium",
           "-pix_fmt", "yuv420p"]
# Pegelanpassung, keine Tonaenderung - "only the original audio" bleibt gewahrt.
AUDIO = ["-c:a", "aac", "-b:a", "192k", "-af", "loudnorm=I=-14:TP=-1.5:LRA=11"]


@dataclass
class Segment:
    nr: int
    start: float
    ende: float

    @property
    def dauer(self) -> float:
        return self.ende - self.start


# ---------------------------------------------------------------------------
# Stage 1: Szenen finden
# ---------------------------------------------------------------------------

def dauer_von(video: Path) -> float:
    aus = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "csv=p=0", str(video)],
        capture_output=True, text=True, check=True)
    return float(aus.stdout.strip())


def szenen(video: Path, schwelle: float = 0.25) -> list[float]:
    """Harte Bildwechsel im Stringout. Der Reel ist bereits geschnitten -
    die Szenengrenzen sind also die Grenzen der einzelnen Top Plays."""
    aus = subprocess.run(
        ["ffmpeg", "-hide_banner", "-i", str(video), "-filter_complex",
         f"select='gt(scene,{schwelle})',metadata=print", "-an", "-f", "null", "-"],
        capture_output=True, text=True)
    return [float(m) for m in re.findall(r"pts_time:([0-9.]+)", aus.stderr)]


def _ohne_ausschluss(bereiche: list[list[float]],
                     sperr: list[tuple[float, float]]) -> list[list[float]]:
    """Gesperrte Zeitbereiche aus den Segmenten herausschneiden.

    Ein Segment, das einen gesperrten Bereich ueberlappt, wird geteilt statt
    verworfen - der Teil davor und der Teil danach sind brauchbar.
    """
    for sa, sb in sperr:
        neu = []
        for a, b in bereiche:
            if sb <= a or b <= sa:               # keine Ueberlappung
                neu.append([a, b])
                continue
            if a < sa:
                neu.append([a, sa])
            if b > sb:
                neu.append([sb, b])
        bereiche = neu
    return bereiche


def segmente(video: Path, min_dauer: float = MIN_DAUER,
             ziel_min: float = ZIEL_MIN,
             ziel_max: float = ZIEL_MAX) -> list[Segment]:
    """Szenengrenzen zu Clips verdichten.

    Drei Schritte, jeder aus einer Messung begruendet:

    1. Mikrosegmente (Explosionsblitze, Killcam-Uebergaenge) sind keine
       Schnitte, sondern Ausreisser innerhalb einer Szene.
    2. Gesperrte Bereiche (fremdes Streamer-Overlay) fallen heraus.
    3. Benachbarte Segmente werden zu einem Clip montiert, bis ``ziel_min``
       erreicht ist. Ein einzelnes Segment ist meist 10-18 s lang und schneidet
       den Spielzug an - erst der Zusammenhang mehrerer Momente ergibt einen
       Clip, der ankommt, und die Kampagne verlangt ohnehin einen Schnitt statt
       Rohmaterial.
    """
    grenzen = [0.0] + szenen(video) + [dauer_von(video)]

    roh: list[list[float]] = []
    for a, b in zip(grenzen, grenzen[1:]):
        if roh and (b - a) < 2.0:
            roh[-1][1] = b                   # zu kurz fuer eine eigene Szene
        else:
            roh.append([a, b])

    roh = _ohne_ausschluss(roh, AUSSCHLUSS.get(video.stem, []))

    # Montage: anhaengen, solange der Clip unter ziel_min bleibt und die
    # Obergrenze nicht reisst.
    clips: list[list[float]] = []
    for a, b in roh:
        if clips and (clips[-1][1] - clips[-1][0]) < ziel_min \
                and abs(a - clips[-1][1]) < 0.05 \
                and (b - clips[-1][0]) <= ziel_max:
            clips[-1][1] = b
        else:
            clips.append([a, b])

    raus, nr = [], 0
    for a, b in clips:
        # Gegen die Mindestdauer zaehlt, was nach dem Beschnitt uebrig bleibt,
        # nicht die Rohlaenge - sonst rutschen Clips knapp unter die
        # Vertragsgrenze, weil an beiden Enden RAND abgeht.
        start, ende = a + RAND, b - RAND
        if ende - start >= min_dauer:
            nr += 1
            raus.append(Segment(nr, round(start, 2), round(ende, 2)))
    return raus


# ---------------------------------------------------------------------------
# Stage 2: Overlays - einmal bauen, fuer alle Clips
# ---------------------------------------------------------------------------

def _schrift(groesse: int) -> ImageFont.FreeTypeFont:
    pfad = Path(__file__).resolve().parents[1] / "assets/fonts/Anton-Regular.ttf"
    return ImageFont.truetype(str(pfad), groesse)


def baue_pflichttext(ziel: Path) -> Path:
    """Die beiden Pflichtphrasen, weiss mit schwarzem Rand.

    Steht ueber die volle Cliplaenge. Die Vorgabe nennt keine Mindestdauer,
    und durchgehend ist die einzige Auslegung, die zweifelsfrei erfuellt ist.
    """
    im = Image.new("RGBA", (CANVAS_B, 260), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    for txt, groesse, y in ((PFLICHT_ZEILE_1, 92, 10), (PFLICHT_ZEILE_2, 66, 125)):
        f = _schrift(groesse)
        breite = d.textbbox((0, 0), txt, font=f)[2]
        d.text(((CANVAS_B - breite) // 2, y), txt, font=f,
               fill=(255, 255, 255, 255), stroke_width=9, stroke_fill=(0, 0, 0, 255))
    im.save(ziel)
    return ziel


def baue_logo(quelle: Path, ziel: Path) -> Path:
    """Weisse Logofassung mit weichem Schatten.

    Die gelieferte Datei ist die POS-Variante fuer helle Untergruende; auf
    Gameplay verschwindet ihr schwarzes Wortbild. Umgefaerbt wird ueber den
    Farbton, nicht ueber die Helligkeit - so bleiben die gelben Pixel und die
    teiltransparenten Kanten korrekt. Der Schatten liegt darunter, das Logo
    selbst bleibt unangetastet.
    """
    src = Image.open(quelle).convert("RGBA")
    q = src.load()
    for y in range(src.height):
        for x in range(src.width):
            r, g, b, a = q[x, y]
            if a and not (r > 90 and g > 60 and b < r - 50):
                q[x, y] = (255, 255, 255, a)

    hoehe = int(src.height * LOGO_BREITE / src.width)
    src = src.resize((LOGO_BREITE, hoehe), Image.LANCZOS)

    pad = 36
    leinwand = Image.new("RGBA", (src.width + 2 * pad, src.height + 2 * pad),
                         (0, 0, 0, 0))
    schatten = Image.new("RGBA", leinwand.size, (0, 0, 0, 0))
    schatten.paste((0, 0, 0, 190), (pad + 3, pad + 3), src.split()[3])
    leinwand.alpha_composite(schatten.filter(ImageFilter.GaussianBlur(9)))
    leinwand.alpha_composite(src, (pad, pad))
    leinwand.save(ziel)
    return ziel


# ---------------------------------------------------------------------------
# Stage 3: Rendern
# ---------------------------------------------------------------------------

def rendere(video: Path, seg: Segment, text_png: Path, logo_png: Path,
            ziel: Path) -> None:
    logo_h = Image.open(logo_png).height
    # Das Logo steht mittig zwischen Bildunterkante und UI-Zone.
    frei_ab, frei_bis = BILD_Y + BILD_H, CANVAS_H - UI_ZONE_UNTEN
    logo_y = frei_ab + (frei_bis - frei_ab - logo_h) // 2
    logo_x = (CANVAS_B - Image.open(logo_png).width) // 2

    # Der Untergrund ist ein starker Blur derselben Quelle - so hat der Rahmen
    # keine harte schwarze Kante, sondern traegt die Farben der Szene.
    graph = (
        f"[0:v]split=2[b1][b2];"
        f"[b1]crop=608:1080:656:0,scale={CANVAS_B}:{CANVAS_H},boxblur=30:3[bg];"
        f"[b2]crop={CROP_B}:{CROP_H}:{CROP_X}:{CROP_Y},"
        f"scale={BILD_B}:{BILD_H}:flags=lanczos,{SCHAERFE}[fg];"
        f"[bg][fg]overlay=0:{BILD_Y}[k];"
        f"[k][1:v]overlay=0:{TEXT_Y}[t];"
        f"[t][2:v]overlay={logo_x}:{logo_y}[v]"
    )
    subprocess.run(
        ["ffmpeg", "-hide_banner", "-loglevel", "error",
         "-ss", str(seg.start), "-t", str(round(seg.dauer, 2)), "-i", str(video),
         "-i", str(text_png), "-i", str(logo_png),
         "-filter_complex", graph, "-map", "[v]", "-map", "0:a",
         *ENCODER, *AUDIO, "-movflags", "+faststart", "-y", str(ziel)],
        check=True)


def caption(zusatz: str) -> str:
    """Caption nach Kampagnenvorgabe.

    Reihenfolge ist vorgeschrieben: eigener Text mit Tag, dann der exakte
    Pflichtsatz, dann der FTC-Hinweis allein auf seiner Zeile als erstes
    Hashtag ueberhaupt, danach hoechstens drei weitere.
    """
    return "\n".join([f"{zusatz} {CAPTION_TAG}", CAPTION_PFLICHTSATZ, "",
                      CAPTION_FTC, "", CAPTION_HASHTAGS])


# ---------------------------------------------------------------------------

def main() -> None:
    p = argparse.ArgumentParser(prog="mw4")
    p.add_argument("--video", required=True)
    p.add_argument("--logo", required=True)
    p.add_argument("--ausgabe", required=True, help="Basisordner der Laeufe")
    p.add_argument("--min-dauer", type=float, default=MIN_DAUER + SICHERHEIT)
    p.add_argument("--nur-planen", action="store_true",
                   help="Segmente melden, nichts rendern")
    args = p.parse_args()

    video = Path(args.video).expanduser()
    segs = segmente(video, args.min_dauer)
    print(f"{video.name}: {len(segs)} Clips ab {args.min_dauer:.1f}s")
    for s in segs:
        print(f"  {s.nr:>2}  {s.start:>7.2f} - {s.ende:>7.2f}  {s.dauer:>5.1f}s")
    if args.nur_planen:
        return

    lauf = Path(args.ausgabe).expanduser() / datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    (lauf / "mp4").mkdir(parents=True, exist_ok=True)
    (lauf / "png").mkdir(exist_ok=True)
    (lauf / "json").mkdir(exist_ok=True)

    text_png = baue_pflichttext(lauf / "png/pflichttext.png")
    logo_png = baue_logo(Path(args.logo).expanduser(), lauf / "png/logo.png")

    stamm = video.stem.replace("_Stringout_16X9", "")
    for s in segs:
        ziel = lauf / f"mp4/{stamm}_{s.nr:03d}.mp4"
        rendere(video, s, text_png, logo_png, ziel)
        print(f"  -> {ziel.name}  ({s.dauer:.1f}s)")

    (lauf / "json/lauf.json").write_text(json.dumps({
        "quelle": str(video), "erzeugt": datetime.now().isoformat(timespec="seconds"),
        "clips": [asdict(s) | {"dauer": round(s.dauer, 2)} for s in segs],
    }, indent=2), encoding="utf-8")
    print(f"\n{len(segs)} Clips -> {lauf}")


if __name__ == "__main__":
    main()
