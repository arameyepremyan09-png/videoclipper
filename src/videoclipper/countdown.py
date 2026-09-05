"""Format — Top-5-Countdown.

Eine Compilation ist kein Clip. Der EditPlan beschreibt *ein* Segment aus
*einer* Quelle; hier sind es fuenf Segmente aus bis zu fuenf Quellen, und das
Overlay aendert sich zwischen ihnen. Deshalb ein eigener Datenvertrag statt
einer Erweiterung von ``EditPlan`` — dort wuerde jedes Feld optional werden und
der Vertrag seine Schaerfe verlieren.

Die Arbeitsteilung bleibt: Die AI fuellt ``titel``, ``text`` und die Zeitfenster.
Alles unter ``Aufgeloest`` rechnet dieser Code aus dem Template.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field, model_validator


class Eintrag(BaseModel):
    """Ein Listenplatz mit dem Ausschnitt, der ihn belegt."""
    model_config = ConfigDict(extra="forbid")

    platz: int = Field(ge=1, le=9)
    text: str = Field(min_length=1, max_length=40)
    video_id: str
    start: float = Field(ge=0)
    dauer: float = Field(gt=0)
    # Optionaler Ausschnitt der Quelle (x, y, w, h). Ohne Angabe das Vollbild.
    quelle_box: tuple[int, int, int, int] | None = None


class Aufgeloest(BaseModel):
    """Reine Zahlen. Ab hier gibt es nichts mehr zu entscheiden."""
    model_config = ConfigDict(extra="forbid")

    canvas: tuple[int, int]
    fps: int
    panel: tuple[int, int, int, int]
    dauer: float
    # Reihenfolge der Wiedergabe: Platz 5 zuerst, Platz 1 zuletzt.
    segmente: list[dict]


class CountdownPlan(BaseModel):
    model_config = ConfigDict(extra="forbid")

    clip_id: str
    titel: str = Field(min_length=3, max_length=80)
    template: str = "TOP5_COUNTDOWN"
    sprache: str = "de"
    eintraege: list[Eintrag]
    fps: int = 30
    aufgeloest: Aufgeloest | None = None

    @model_validator(mode="after")
    def _plaetze_vollstaendig(self):
        plaetze = sorted(e.platz for e in self.eintraege)
        if plaetze != list(range(1, len(plaetze) + 1)):
            raise ValueError(f"Plaetze muessen 1..n lueckenlos sein, sind {plaetze}")
        return self


def loese_auf(plan: CountdownPlan, tmpl: dict) -> CountdownPlan:
    """Template + Plan -> konkrete Rechtecke und Zeitfenster."""
    liste = tmpl["liste"]
    if len(plan.eintraege) != liste["plaetze"]:
        raise ValueError(
            f"Template {tmpl['name']} erwartet {liste['plaetze']} Plaetze, "
            f"der Plan hat {len(plan.eintraege)}")

    px, py, pw, ph = tmpl["panels"][0]["ziel"]
    if ph % 2 or pw % 2:
        # In yuv420p rundet der Scaler ungerade Kanten still ab. Lieber hier
        # abbrechen als es dem QC zu ueberlassen.
        raise ValueError(f"Panelmasse muessen gerade sein, sind {pw}x{ph}")

    # Abgespielt wird rueckwaerts: Platz 5 zuerst, Platz 1 als Payoff.
    reihe = sorted(plan.eintraege, key=lambda e: -e.platz)

    segmente, uhr = [], 0.0
    for i, e in enumerate(reihe):
        segmente.append({
            "index": i,
            "platz": e.platz,
            "video_id": e.video_id,
            "start": round(e.start, 3),
            "dauer": round(e.dauer, 3),
            "ab": round(uhr, 3),
            "bis": round(uhr + e.dauer, 3),
            # Nach diesem Segment sind alle Plaetze ab hier abwaerts sichtbar.
            "sichtbar": sorted((x.platz for x in reihe[: i + 1]), reverse=True),
            "quelle_box": list(e.quelle_box) if e.quelle_box else None,
        })
        uhr += e.dauer

    plan.aufgeloest = Aufgeloest(
        canvas=tuple(tmpl["canvas"]), fps=plan.fps,
        panel=(px, py, pw, ph), dauer=round(uhr, 3), segmente=segmente)
    return plan


def sicherheitszone_pruefen(tmpl: dict) -> list[str]:
    """Laeuft Bildinhalt unter TikToks UI? Gibt Hinweise zurueck, bricht nicht ab."""
    hinweise = []
    unten = (tmpl.get("sicherheitszone") or {}).get("unten", 0)
    if not unten:
        return hinweise
    _, hoehe = tmpl["canvas"]
    for p in tmpl["panels"]:
        _, y, _, h = p["ziel"]
        if y + h > hoehe - unten:
            hinweise.append(
                f"Panel '{p['quelle']}' endet bei y={y + h}, "
                f"die UI-Zone beginnt bei y={hoehe - unten}")
    return hinweise
