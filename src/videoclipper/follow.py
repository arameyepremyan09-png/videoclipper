"""Stage 11b — Follow-Aufforderung. Pflicht in jedem Clip.

WARUM MITTEN IM CLIP: ``scoring.yaml`` gewichtet ``konversion`` — Follows pro
View — mit 0.20 und nennt sie "das Ziel des Accounts". Zugleich traegt
``retention`` 0.40, und genau die Zahl fehlt bislang in jeder Messung: Es ist
also nicht belegt, dass nennenswert viele Zuschauer bis zum Ende bleiben. Eine
Aufforderung im Abspann erreicht nur, wer ohnehin geblieben ist. Sie steht
deshalb nach dem Hook und vor der Pointe.

WAS SEIT DEM 2026-09-08 IM BILD STEHT: nicht mehr eine Pille mit Text, sondern
der **runde Folgen-Knopf** der App — roter Kreis mit weissem Plus —, auf den
ein Mauszeiger hereinfaehrt, drueckt, und der danach weiss mit Haken wird. Der
Knopf poppt auf und am Ende wieder weg. Entschieden vom Nutzer am 2026-09-08.

WIE DAS OHNE libass UND OHNE drawtext GEHT: Der Renderpfad kennt genau ein
Mittel — ein PNG, eingeblendet ueber ``enable='between(t,ab,bis)'``, mit
Ausdruecken fuer x und y. Daraus folgt die Aufteilung der Animation:

  * **Bewegung ist ein Ausdruck.** Der Mauszeiger ist EIN Bild, das ueber
    x/y faehrt — genau wie frueher die Pille. Kostet einen Eingang.
  * **Groesse und Zustand sind Bilder.** ``scale`` laesst sich nicht ueber die
    Zeit ausdruecken (der Ausdruck wuerde je Frame neu skalieren, siehe
    CLAUDE.md). Pop, Druck und Wegpoppen sind deshalb eine FOLGE kurz
    geschalteter Standbilder — dasselbe Verfahren wie die Countdown-Liste,
    nur mit 1-2 Frames je Zustand statt Sekunden.

Das sind rund 20 Eingaenge statt einem. Vertretbar, weil sie klein sind (je
ein Quadrat von rund 200 px) und weil ``enable`` sie ausserhalb ihres Fensters
nicht komponiert. Die Untertitel eines 47-s-Clips bringen zum Vergleich 39 mit.

Der ``text`` bleibt in der Konfiguration und im EditPlan stehen, obwohl im Bild
kein Text mehr vorkommt: Er ist das Protokoll, welche Aufforderung gemeint war.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from pathlib import Path

from PIL import Image, ImageDraw

# Ueberabtastung beim Zeichnen. Kreise und der Haken haben schraege Kanten;
# 4x zeichnen und herunterrechnen ist die billigste Kantenglaettung, die PIL
# hergibt, und der Knopf wird nur ein Dutzend Mal je Clip gezeichnet.
UEBER = 4

# Die Silhouette des Mauszeigers, auf Hoehe 1.0 normiert, Spitze auf (0,0).
ZEIGER = [(0.00, 0.00), (0.00, 0.86), (0.21, 0.67), (0.34, 0.98),
          (0.47, 0.92), (0.34, 0.62), (0.57, 0.60)]

# Der Zeitplan als Anteile des Fensters, nicht als Sekunden: ``platziere``
# staucht das Fenster bei kurzen Clips bis auf ``min_dauer``, und dann soll die
# Animation schneller laufen statt abgeschnitten zu werden.
TAKT = {
    "pop_ein":  (0.00, 0.15),
    "ruhe_rot": (0.15, 0.42),
    "druck":    (0.42, 0.50),
    "umschlag": (0.50, 0.62),
    "ruhe_weiss": (0.62, 0.86),
    "pop_aus":  (0.86, 1.00),
    "anflug":   (0.14, 0.42),
    "gedrueckt": (0.42, 0.66),
    "abflug":   (0.66, 0.90),
}

# Skalenleitern. Die Ueberschwinger sind der "Pop": ueber 1.0 hinaus und zurueck.
POP_EIN = (0.25, 0.58, 0.86, 1.08, 1.18, 1.08, 1.01)
DRUCK = (0.93, 0.86, 0.89)
# (Knopfskala, Ringskala, Deckkraft). Der Ring muss in jedem Zustand GROESSER
# sein als der Knopf, sonst liegt er darunter und ist nicht zu sehen — genau
# das passierte in der ersten Fassung beim Ringwert 1.10 gegen Knopf 1.16.
# Die Deckkraft laeuft nicht auf null aus: Bei 0 waere der letzte Zustand ein
# leeres Bild, und der Ring blitzte nur einmal statt zu verpuffen.
UMSCHLAG = ((1.16, 1.30, 235), (1.08, 1.52, 130), (1.01, 1.74, 55))
POP_AUS = (1.10, 0.94, 0.72, 0.44, 0.16)

# Abzug am Ende jedes Zustandsfensters. ``between`` schliesst beide Raender
# ein — ohne die Luecke waeren an der Nahtstelle zwei Zustaende gleichzeitig
# aktiv, also zwei Knoepfe verschiedener Groesse uebereinander. Eine
# Millisekunde ist bei 30 fps ein Dreissigstel Frame und damit unsichtbar.
LUECKE = 0.001


@dataclass(frozen=True)
class Hinweis:
    """Zeitfenster der Aufforderung, relativ zum Clipbeginn."""
    text: str
    ab: float
    bis: float


@dataclass(frozen=True)
class Stueck:
    """Ein Overlay-Eingang der Szene: ein Bild plus Fenster und Lage.

    ``name`` ist der Dateiname ohne Ordner. Zwei Stuecke duerfen denselben
    Namen tragen (der Mauszeiger kommt zweimal vor) — gezeichnet wird das Bild
    dann einmal, als Eingang steht es zweimal im Graphen, weil jeder Eingang
    genau ein ``overlay`` bedient.
    """
    name: str
    ab: float
    bis: float
    x: str
    y: str
    zeichnung: dict = field(default_factory=dict)


def platziere(dauer: float, conf: dict) -> tuple[Hinweis | None, list[str]]:
    """Wann die Aufforderung steht. Gibt (Hinweis, Meldungen) zurueck.

    Regel: ``ab_anteil`` der Cliplaenge, aber nie im Hook und nie so spaet,
    dass sie in die Pointe laeuft. Passt sie bei kurzen Clips nicht mehr, wird
    sie bis ``min_dauer`` gestaucht — darunter wird sie weggelassen und
    gemeldet, statt sie an eine falsche Stelle zu zwingen.
    """
    laenge = float(conf.get("dauer", 3.0))
    min_laenge = float(conf.get("min_dauer", 1.8))
    nicht_vor = float(conf.get("nicht_vor", 3.0))
    nicht_nach = float(conf.get("nicht_nach_ende", 2.0))
    anteil = float(conf.get("ab_anteil", 0.35))
    text = str(conf.get("text", "FOLGEN"))

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


# ---------------------------------------------------------------------------
# Geometrie
# ---------------------------------------------------------------------------

def _gerade(n: float) -> int:
    i = int(math.ceil(n))
    return i + (i % 2)


def buehne(conf: dict) -> int:
    """Kantenlaenge der Knopf-PNGs.

    GROESSER ALS DER KNOPF, und das ist der Grund: Im Moment des Klicks laeuft
    ein Ring nach aussen (``UMSCHLAG``, bis 1.72 x Radius). Er gehoert auf
    dasselbe Bild, sonst braeuchte er eigene Eingaenge. Die PNG-Flaeche ist
    also die Flaeche des Rings, nicht die des Knopfes.
    """
    d = int(conf.get("durchmesser", 112))
    rand = int(conf.get("rand_staerke", 6))
    return _gerade(d * max(r for _, r, _d in UMSCHLAG) + 2 * rand + 6)


def masse(tmpl: dict) -> tuple[int, int, int, int]:
    """Das Rechteck des KNOPFES (x, y, breite, hoehe) auf der Canvas.

    Nicht die PNG-Flaeche — die ist wegen des Klickrings groesser. Was hier
    steht, ist der Platz, den der Knopf dauerhaft belegt; daran messen die
    Layouttests, ob er in die UI-Zone oder ins Untertitelband laeuft. Der Ring
    reicht fuer rund ein Zehntel Sekunde darueber hinaus und ist bewusst nicht
    Teil des Vertrages: Er ist ein Aufblitzen, kein Element.
    """
    conf = tmpl["follow_hinweis"]
    breite, hoehe = tmpl["canvas"]
    d = int(conf.get("durchmesser", 112))
    rand = int(conf.get("rand_staerke", 6))

    k = _gerade(d * max(POP_EIN) + 2 * rand + 4)
    x = (breite - k) // 2
    y = int(conf["y"]) - k // 2

    unten_frei = hoehe - int((tmpl.get("sicherheitszone") or {}).get("unten", 0))
    if y + k > unten_frei:
        raise ValueError(
            f"{tmpl['name']}: Follow-Knopf endet bei y={y + k}, "
            f"die UI-Zone beginnt bei y={unten_frei}")
    if y < 0:
        raise ValueError(f"{tmpl['name']}: Follow-Knopf beginnt bei y={y}")
    return x, y, k, k


def _zentrum(tmpl: dict) -> tuple[int, int]:
    breite, _ = tmpl["canvas"]
    return breite // 2, int(tmpl["follow_hinweis"]["y"])


def _zeiger_masse(conf: dict) -> tuple[int, int, int]:
    """(Breite, Hoehe, Polster) des Zeiger-PNGs. Die Spitze liegt auf (p, p)."""
    c = conf.get("cursor") or {}
    h = int(c.get("hoehe", 104))
    p = int(math.ceil(h * 0.07)) + 2
    return _gerade(h * ZEIGER[-1][0] + 2 * p), _gerade(h + 2 * p), p


# ---------------------------------------------------------------------------
# Zeichnen
# ---------------------------------------------------------------------------

def _kreis(z: ImageDraw.ImageDraw, mx: float, my: float, r: float,
           fuellung, umriss, breite: float) -> None:
    z.ellipse([mx - r, my - r, mx + r, my + r], fill=fuellung,
              outline=umriss, width=max(int(breite), 1))


def _plus(z: ImageDraw.ImageDraw, mx: float, my: float, r: float, farbe) -> None:
    arm, dicke = r * 0.52, r * 0.22
    z.rounded_rectangle([mx - arm, my - dicke, mx + arm, my + dicke],
                        radius=dicke, fill=farbe)
    z.rounded_rectangle([mx - dicke, my - arm, mx + dicke, my + arm],
                        radius=dicke, fill=farbe)


def _haken(z: ImageDraw.ImageDraw, mx: float, my: float, r: float, farbe) -> None:
    dicke = max(r * 0.20, 1.0)
    punkte = [(mx - r * 0.40, my + r * 0.02),
              (mx - r * 0.10, my + r * 0.32),
              (mx + r * 0.42, my - r * 0.32)]
    z.line(punkte, fill=farbe, width=int(dicke))
    # PIL zeichnet keine runden Enden — die Kappen sind Kreise auf den Ecken.
    for px, py in punkte:
        z.ellipse([px - dicke / 2, py - dicke / 2, px + dicke / 2, py + dicke / 2],
                  fill=farbe)


def knopf_bild(conf: dict, skala: float, weiss: bool,
               ring: float | None = None, ring_deckung: int = 200) -> Image.Image:
    """Ein Zustand des Knopfes: Groesse, Farbe, optional der Klickring."""
    k = buehne(conf)
    s = UEBER
    bild = Image.new("RGBA", (k * s, k * s), (0, 0, 0, 0))
    z = ImageDraw.Draw(bild)
    m = k * s / 2
    d = int(conf.get("durchmesser", 112))
    r = d * s * skala / 2
    rand = int(conf.get("rand_staerke", 6)) * s

    if ring:
        # Der Ring wird nach aussen duenner und blasser — er "verpufft".
        rr = d * s * ring / 2
        farbe = conf.get("ring_farbe", "#FFFFFF")
        rgb = tuple(int(farbe.lstrip("#")[i:i + 2], 16) for i in (0, 2, 4))
        z.ellipse([m - rr, m - rr, m + rr, m + rr],
                  outline=rgb + (max(0, min(255, ring_deckung)),),
                  width=max(int(rand * 1.5 * ring_deckung / 235), 1))

    _kreis(z, m, m, r,
           conf.get("farbe_nachher" if weiss else "farbe_vorher",
                    "#FFFFFF" if weiss else "#FE2C55"),
           conf.get("rand_farbe", "#000000"), rand)

    zeichen = conf.get("zeichen_nachher" if weiss else "zeichen_vorher",
                       "#12121A" if weiss else "#FFFFFF")
    (_haken if weiss else _plus)(z, m, m, r, zeichen)

    return bild.resize((k, k), Image.LANCZOS)


def zeiger_bild(conf: dict, gedrueckt: bool = False) -> Image.Image:
    """Der Mauszeiger. ``gedrueckt`` ist die kurz gestauchte Klickstellung."""
    bw, bh, p = _zeiger_masse(conf)
    c = conf.get("cursor") or {}
    h = int(c.get("hoehe", 104)) * (0.90 if gedrueckt else 1.0)
    s = UEBER

    bild = Image.new("RGBA", (bw * s, bh * s), (0, 0, 0, 0))
    z = ImageDraw.Draw(bild)
    punkte = [(p * s + x * h * s, p * s + y * h * s) for x, y in ZEIGER]
    z.polygon(punkte, fill=c.get("farbe", "#FFFFFF"),
              outline=c.get("rand_farbe", "#000000"),
              width=max(int(h * 0.055 * s), 1))
    return bild.resize((bw, bh), Image.LANCZOS)


# ---------------------------------------------------------------------------
# Die Szene
# ---------------------------------------------------------------------------

def _leiter(ab: float, bis: float, werte) -> list[tuple[float, float, object]]:
    """Ein Zeitfenster gleichmaessig auf eine Zustandsleiter aufteilen."""
    n = len(werte)
    schritt = (bis - ab) / n
    return [(ab + i * schritt, ab + (i + 1) * schritt - LUECKE, w)
            for i, w in enumerate(werte)]


def szene(h: Hinweis, tmpl: dict) -> list[Stueck]:
    """Die vollstaendige Klickszene als Folge von Overlay-Eingaengen.

    Reihenfolge ist Zeichenreihenfolge: der Knopf zuerst, der Mauszeiger
    darueber — er drueckt schliesslich darauf.
    """
    conf = tmpl["follow_hinweis"]
    cw, ch = tmpl["canvas"]
    cx, cy = _zentrum(tmpl)
    k = buehne(conf)
    w = h.bis - h.ab

    def t(name: str) -> tuple[float, float]:
        a, b = TAKT[name]
        return h.ab + a * w, h.ab + b * w

    kx, ky = str(cx - k // 2), str(cy - k // 2)
    stuecke: list[Stueck] = []

    def knopf(ab: float, bis: float, skala: float, weiss: bool,
              ring: float | None = None, deckung: int = 200) -> None:
        marke = "w" if weiss else "r"
        name = f"knopf_{marke}{int(skala * 100):03d}"
        if ring:
            name += f"_ring{int(ring * 100):03d}"
        stuecke.append(Stueck(name, ab, bis, kx, ky,
                              {"art": "knopf", "skala": skala, "weiss": weiss,
                               "ring": ring, "deckung": deckung}))

    for ab, bis, s in _leiter(*t("pop_ein"), POP_EIN):
        knopf(ab, bis, s, False)
    a, b = t("ruhe_rot")
    knopf(a, b - LUECKE, 1.0, False)
    for ab, bis, s in _leiter(*t("druck"), DRUCK):
        knopf(ab, bis, s, False)
    for ab, bis, (s, ring, deckung) in _leiter(*t("umschlag"), UMSCHLAG):
        knopf(ab, bis, s, True, ring, deckung)
    a, b = t("ruhe_weiss")
    knopf(a, b - LUECKE, 1.0, True)
    for ab, bis, s in _leiter(*t("pop_aus"), POP_AUS):
        knopf(ab, bis, s, True)

    # --- Mauszeiger ---------------------------------------------------------
    c = conf.get("cursor") or {}
    _, _, p = _zeiger_masse(conf)
    zx = cx + int(c.get("ziel_dx", 14)) - p          # Spitze auf dem Knopf
    zy = cy + int(c.get("ziel_dy", 16)) - p
    sx = cw + 30                                      # ausserhalb, rechts
    sy = min(cy + int(c.get("start_dy", 520)), ch - 40)

    def fahrt(ab: float, bis: float, von: tuple[int, int], nach: tuple[int, int],
              ease: str) -> tuple[str, str]:
        """Ausdruecke fuer eine Fahrt. ``ease`` waehlt aus- oder einlaufend."""
        p_ = f"max(min((t-{ab:.3f})/{max(bis - ab, 1e-3):.3f},1),0)"
        # aus: schnell los, weich an.  ein: weich los, schnell weg.
        #
        # Der Anflug lief zuerst mit Exponent 3. Im Filmstreifen sah das aus,
        # als bliebe der Zeiger auf halbem Weg stehen: Bei p=0.5 sind damit
        # schon 87 % der Strecke zurueckgelegt, der Rest kriecht. 2.2 verteilt
        # die Bewegung sichtbarer und bremst trotzdem vor dem Knopf ab.
        f = f"pow(1-{p_},2.2)" if ease == "aus" else f"(1-pow({p_},3))"
        return (f"{nach[0]}+({von[0] - nach[0]})*{f}",
                f"{nach[1]}+({von[1] - nach[1]})*{f}")

    ab, bis = t("anflug")
    ax, ay = fahrt(ab, bis, (sx, sy), (zx, zy), "aus")
    stuecke.append(Stueck("zeiger", ab, bis, ax, ay, {"art": "zeiger"}))

    ab, bis = t("gedrueckt")
    stuecke.append(Stueck("zeiger_druck", ab, bis, str(zx), str(zy),
                          {"art": "zeiger", "gedrueckt": True}))

    ab, bis = t("abflug")
    bx, by = fahrt(ab, bis, (zx, zy), (sx, sy), "ein")
    stuecke.append(Stueck("zeiger", ab, bis, bx, by, {"art": "zeiger"}))
    return stuecke


def baue(tmpl: dict, ordner: Path, clip_id: str, h: Hinweis) -> list[Path]:
    """Ein PNG je Stueck der Szene, in genau der Reihenfolge von ``szene``.

    Gleichnamige Stuecke teilen sich die Datei; der Pfad steht dann mehrfach
    in der Liste, weil jeder ``overlay`` seinen eigenen Eingang braucht.
    """
    conf = tmpl["follow_hinweis"]
    ordner.mkdir(parents=True, exist_ok=True)
    fertig: dict[str, Path] = {}
    pfade: list[Path] = []

    for s in szene(h, tmpl):
        if s.name not in fertig:
            ziel = ordner / f"{clip_id}.fw_{s.name}.png"
            z = s.zeichnung
            bild = (zeiger_bild(conf, bool(z.get("gedrueckt")))
                    if z["art"] == "zeiger"
                    else knopf_bild(conf, z["skala"], z["weiss"], z.get("ring"),
                                    int(z.get("deckung", 200))))
            bild.save(ziel)
            fertig[s.name] = ziel
        pfade.append(fertig[s.name])
    return pfade
