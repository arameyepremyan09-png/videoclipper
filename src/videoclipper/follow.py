"""Stage 11b — Follow-Aufforderung. Pflicht in jedem Clip.

WARUM MITTEN IM CLIP: ``scoring.yaml`` gewichtet ``konversion`` — Follows pro
View — mit 0.20 und nennt sie "das Ziel des Accounts". Zugleich traegt
``retention`` 0.40, und genau die Zahl fehlt bislang in jeder Messung: Es ist
also nicht belegt, dass nennenswert viele Zuschauer bis zum Ende bleiben. Eine
Aufforderung im Abspann erreicht nur, wer ohnehin geblieben ist. Sie steht
deshalb nach dem Hook und vor der Pointe.

WIE DIE ANIMATION MIT WENIG AUFWAND ENTSTEHT: dieselbe Regel wie beim
Untertitel — ein einziges Standbild, die Bewegung steckt im ``x``-Ausdruck des
``overlay``-Filters. Die Pille fliegt von rechts ein und rechts wieder hinaus,
weil auf TikTok dort die Buttonleiste mit dem Folgen-Knopf liegt: Die Bewegung
zeigt dorthin, wo geklickt werden soll.

Der Text ist Konfiguration, nicht Modellausgabe. Die AI entscheidet WAS im Clip
passiert, nicht welche Marketingformel darunter steht.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from PIL import Image, ImageDraw

from .headline import font as _font


@dataclass(frozen=True)
class Hinweis:
    """Zeitfenster der Aufforderung, relativ zum Clipbeginn."""
    text: str
    ab: float
    bis: float


def platziere(dauer: float, conf: dict) -> tuple[Hinweis | None, list[str]]:
    """Wann die Aufforderung steht. Gibt (Hinweis, Meldungen) zurueck.

    Regel: ``ab_anteil`` der Cliplaenge, aber nie im Hook und nie so spaet,
    dass sie in die Pointe laeuft. Passt sie bei kurzen Clips nicht mehr, wird
    sie bis ``min_dauer`` gestaucht — darunter wird sie weggelassen und
    gemeldet, statt sie an eine falsche Stelle zu zwingen.
    """
    laenge = float(conf.get("dauer", 2.6))
    min_laenge = float(conf.get("min_dauer", 1.6))
    nicht_vor = float(conf.get("nicht_vor", 3.0))
    nicht_nach = float(conf.get("nicht_nach_ende", 2.0))
    anteil = float(conf.get("ab_anteil", 0.35))
    text = str(conf.get("text", "FOLGEN FÜR MEHR"))

    platz = dauer - nicht_vor - nicht_nach
    if platz < min_laenge:
        return None, [
            f"Follow-Aufforderung faellt aus: {dauer:.1f}s Clip laesst zwischen "
            f"{nicht_vor:.1f}s und {dauer - nicht_nach:.1f}s nur {max(platz, 0):.1f}s"]

    meldungen = []
    if laenge > platz:
        meldungen.append(
            f"Follow-Aufforderung auf {platz:.1f}s gekuerzt "
            f"(statt {laenge:.1f}s), der Clip ist nur {dauer:.1f}s lang")
        laenge = platz

    ab = min(max(dauer * anteil, nicht_vor), dauer - nicht_nach - laenge)
    return Hinweis(text, round(ab, 3), round(ab + laenge, 3)), meldungen


def masse(tmpl: dict) -> tuple[int, int, int, int]:
    """Pillenrechteck (x, y, breite, hoehe) auf der Canvas.

    Bricht ab, wenn die Pille in TikToks UI-Zone laeuft — gleiche Begruendung
    wie beim Untertitelband.
    """
    conf = tmpl["follow_hinweis"]
    breite, hoehe = tmpl["canvas"]
    text = str(conf.get("text", ""))
    if conf.get("versalien", True):
        text = text.upper()

    schrift = _font(conf, int(conf["schriftgroesse"]))
    messer = ImageDraw.Draw(Image.new("RGBA", (8, 8)))
    kasten = messer.textbbox((0, 0), text, font=schrift)
    tw, th = kasten[2] - kasten[0], kasten[3] - kasten[1]

    px, py = int(conf.get("polsterung_x", 42)), int(conf.get("polsterung_y", 22))
    pw = tw + 2 * px
    ph = th + 2 * py
    # Gerade Masse: in yuv420p rundet der Scaler ungerade Kanten still ab.
    pw += pw % 2
    ph += ph % 2

    x = (breite - pw) // 2
    y = int(conf["y"]) - ph // 2

    unten_frei = hoehe - int((tmpl.get("sicherheitszone") or {}).get("unten", 0))
    if y + ph > unten_frei:
        raise ValueError(
            f"{tmpl['name']}: Follow-Pille endet bei y={y + ph}, "
            f"die UI-Zone beginnt bei y={unten_frei}")
    if y < 0:
        raise ValueError(f"{tmpl['name']}: Follow-Pille beginnt bei y={y}")
    return x, y, pw, ph


def baue(tmpl: dict, ziel: Path) -> Path:
    """Die Pille als einzelnes PNG, genau so gross wie sie selbst."""
    conf = tmpl["follow_hinweis"]
    _, _, pw, ph = masse(tmpl)

    text = str(conf.get("text", ""))
    if conf.get("versalien", True):
        text = text.upper()
    schrift = _font(conf, int(conf["schriftgroesse"]))

    bild = Image.new("RGBA", (pw, ph), (0, 0, 0, 0))
    zeichner = ImageDraw.Draw(bild)
    rand = int(conf.get("pille_rand_staerke", 5))
    zeichner.rounded_rectangle(
        [rand // 2, rand // 2, pw - 1 - rand // 2, ph - 1 - rand // 2],
        radius=int(conf.get("radius", 26)),
        fill=conf.get("pille_farbe", "#01FC19"),
        outline=conf.get("pille_rand_farbe", "#000000"), width=rand)
    zeichner.text((pw // 2, ph // 2), text, font=schrift,
                  fill=conf.get("farbe", "#000000"), anchor="mm")

    ziel.parent.mkdir(parents=True, exist_ok=True)
    bild.save(ziel)
    return ziel


def x_ausdruck(h: Hinweis, x0: int, canvas_breite: int, pw: int,
               conf: dict) -> str:
    """Der animierte ``x``-Wert: von rechts herein, nach rechts hinaus.

    Beide Enden im selben Ausdruck. Die zwei Summanden sind ausserhalb ihrer
    jeweiligen Einschwingzeit exakt 0, ueberlagern sich also nicht — ausser bei
    einer Standzeit unter der doppelten Animationsdauer, und dort ist der Rest
    ein sauberes Durchschwingen statt eines Sprungs.
    """
    a = conf.get("animation") or {}
    d = float(a.get("dauer", 0.28))
    if d <= 0:
        return str(x0)
    hub = canvas_breite - x0 + 8            # bis vollstaendig aus dem Bild
    ein = f"max(min((t-{h.ab:.3f})/{d:.3f},1),0)"
    aus = f"max(min(({h.bis:.3f}-t)/{d:.3f},1),0)"
    return f"{x0}+{hub}*(pow(1-{ein},2)+pow(1-{aus},2))"
