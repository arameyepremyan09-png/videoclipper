"""Stage 10 — EditPlan.

Der Datenvertrag zwischen AI und Renderer. Die AI fuellt ausschliesslich die
oberen Felder; alles unter ``resolved`` berechnet deterministischer Code und ist
fuer das Modell weder sichtbar noch beschreibbar. Keine Geometrie, keine
Filterketten, keine Pfade, keine ausfuehrbaren Strings von der AI.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class Quelle(BaseModel):
    model_config = ConfigDict(extra="forbid")
    video_id: str
    kanal: str
    orig_start: float


class Zeit(BaseModel):
    model_config = ConfigDict(extra="forbid")
    start: float = Field(ge=0)
    ende: float = Field(gt=0)

    @model_validator(mode="after")
    def _reihenfolge(self):
        if self.ende <= self.start:
            raise ValueError("ende muss nach start liegen")
        return self


class Score(BaseModel):
    model_config = ConfigDict(extra="forbid")
    overall: float = Field(ge=0, le=1)
    reaktion: float = Field(ge=0, le=1)
    klarheit: float = Field(ge=0, le=1)
    payoff: float = Field(ge=0, le=1)


class Aufgeloest(BaseModel):
    """Von Stage 08/09 gefuellt. Reine Zahlen, keine Freiheit mehr."""
    model_config = ConfigDict(extra="forbid")
    start: float
    ende: float
    dauer: float
    modus: str
    modus_anteil: float
    panels: list[dict]
    canvas: tuple[int, int]
    fps: int
    headline_y: int
    # Pflicht-Overlays. Beide sind aus Transkript und Template gerechnet, nicht
    # vom Modell gewaehlt — sie stehen hier, damit im ``.editplan.json`` steht,
    # was tatsaechlich im Bild landet, und nicht erst im fertigen Video.
    untertitel: list[dict] = Field(default_factory=list)
    follow: dict | None = None
    # Strecken, in denen die Quelle in einem anderen Modus steht und der Clip
    # trotzdem weiterlaeuft, mit Fenster, Haltebild und Ersatzpanels — siehe
    # ``layout.einschuebe``. Leer, wo das Template keine vorsieht.
    einschuebe: list[dict] = Field(default_factory=list)
    # Kurzformat: je gezoomtem Panel Fenster, Quell- und Canvasrechteck —
    # siehe ``kurzformat.punch_in``. Leer, wo der Plan keine Pointe nennt.
    punch_in: list[dict] = Field(default_factory=list)
    # Kurzformat mit Teaser: die Quellfenster in Clipreihenfolge, je mit
    # ``start``/``ende``/``dauer`` in der Quelle und ``ab`` im fertigen Clip.
    # Leer bei einem Clip aus einem Stueck. Ist es gesetzt, meinen ``start``
    # und ``ende`` den Hauptteil und ``dauer`` den ganzen Clip.
    segmente: list[dict] = Field(default_factory=list)


class Pointe(BaseModel):
    """Der Moment, fuer den der Clip da ist. Kurzformat, ab 2026-09-11.

    Die AI nennt WANN der Lacher faellt und WER dabei ins Bild gehoert. Wie
    stark gezoomt wird und wie lange hoechstens, steht im Template
    (``kurzformat.punch_in``) — keine Geometrie vom Modell.
    """
    model_config = ConfigDict(extra="forbid")
    t: float = Field(ge=0)                  # Quellzeit, an der die Pointe faellt
    bis: float | None = None                # Ende des Moments, Quellzeit
    fokus: list[str] = Field(default_factory=list)   # Zonennamen; leer = alle

    @model_validator(mode="after")
    def _reihenfolge(self):
        if self.bis is not None and self.bis <= self.t:
            raise ValueError("pointe.bis muss nach pointe.t liegen")
        return self


class EditPlan(BaseModel):
    model_config = ConfigDict(extra="forbid")

    clip_id: str
    quelle: Quelle
    tier: Literal["A", "B"]
    profil: str
    template: str
    template_grund: str

    timing: Zeit
    headline: str = Field(min_length=3, max_length=60)
    sprache: str = "de"
    score: Score
    grund: str
    # Kurzformat: Welcher Moment zuerst laeuft (Quellfenster), und wo darin die
    # Pointe faellt. Ohne Teaser gelten die alten Regeln.
    teaser: Zeit | None = None
    pointe: Pointe | None = None

    resolved: Aufgeloest | None = None

    @model_validator(mode="after")
    def _headline_einzeilig(self):
        if "\n" in self.headline:
            raise ValueError("Headline ist einzeilig; Umbruch macht der Renderer")
        return self
