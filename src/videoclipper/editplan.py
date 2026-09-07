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

    resolved: Aufgeloest | None = None

    @model_validator(mode="after")
    def _headline_einzeilig(self):
        if "\n" in self.headline:
            raise ValueError("Headline ist einzeilig; Umbruch macht der Renderer")
        return self
