"""Stage 07b — Rangliste der Clips eines Videos.

Zwischen Selektion (Stage 06) und Rendern (Stage 12) fehlte eine Stufe: Die
Selektion liefert N Kandidaten, und bisher wurden alle N gerendert und in
Planreihenfolge ausgegeben. Welcher zuerst raus soll, stand nirgends.

Hier steht es. Bewertet wird mit dem, was VOR dem Posten bekannt ist — also
mit ``forecast.prognostiziere`` (Stage 15), ergaenzt um die Hookpruefung aus
``hook.py``. Beides braucht kein gerendertes Video, die Rangliste laeuft also
in Sekunden und vor dem teuren Teil.

ZWEI ZAHLEN, NICHT EINE. Die Prognose ist laut ``scoring.yaml`` unkalibriert
und gibt ``konfidenz 0.2`` aus; sie allein waere eine Scheingenauigkeit. Der
Selektionsscore der AI ist eine zweite, unabhaengige Meinung. Wo beide
auseinanderlaufen, steht das in der Ausgabe — das ist die interessante Zeile,
nicht die mit dem hoechsten Wert.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime

from . import hook
from .forecast import Merkmale, Prognose, prognostiziere
from .snapping import snappe
from .transcript import Transkript


@dataclass
class Platz:
    clip_id: str
    headline: str
    start: float
    ende: float
    dauer: float
    tier: str
    modus: str
    auswahl: float                  # score.overall aus der Selektion, 0..1
    prognose: Prognose
    hookbefund: hook.Hookbefund
    payoff: float | None
    hinweise: list[str] = field(default_factory=list)

    @property
    def uneinig(self) -> bool:
        """Widersprechen sich AI-Urteil und Prognose deutlich?

        Beide auf 0..1 gebracht. Ab 0.25 Abstand lohnt ein Blick — dort sagt
        eine der beiden Quellen etwas, das die andere nicht sieht.
        """
        return abs(self.auswahl - self.prognose.score / 100.0) >= 0.25


def bilde(plaene: list[dict], tr: Transkript,
          postzeit: datetime | None = None,
          historie: list[tuple[str, float]] | None = None,
          plattform: str = "tiktok") -> list[Platz]:
    """Alle Clips eines Selektionsplans bewerten und sortieren.

    Gesnappt wird mit derselben Funktion wie beim Rendern, damit die Dauer in
    der Rangliste die ist, die spaeter auch in der Datei steht — sonst rankt
    man Laengen, die es nie gibt.
    """
    plaetze = []
    for roh in plaene:
        start, ende, tier = snappe(tr, roh["timing"]["start"], roh["timing"]["ende"])
        dauer = round(ende - start, 3)
        headline = roh["headline"]

        hb = hook.pruefe(headline, tr, start, ende)
        payoff = hook.payoff_position(tr, start, ende)
        p = prognostiziere(Merkmale(
            headline=headline, dauer=dauer, plattform=plattform,
            hook_text=hook.hook_text(tr, start), payoff_position=payoff,
            postzeit=postzeit), historie or [])

        plaetze.append(Platz(
            clip_id=roh["clip_id"], headline=headline, start=start, ende=ende,
            dauer=dauer, tier=tier, modus=roh.get("modus", "?"),
            auswahl=float(roh.get("score", {}).get("overall", 0.0)),
            prognose=p, hookbefund=hb, payoff=payoff,
            hinweise=list(hb.hinweise)))

    # Sortiert nach Prognose. Ein Clip, dessen Headline die Pointe verraet,
    # rutscht ans Ende — die Prognose sieht das nicht, sie kennt den Clip nicht.
    return sorted(plaetze, key=lambda x: (x.hookbefund.taugt, x.prognose.score),
                  reverse=True)


def tabelle(plaetze: list[Platz]) -> list[str]:
    """Die Rangliste als Zeilen. Formatierung hier, damit die CLI duenn bleibt."""
    zeilen = [
        f"{'#':>2}  {'prog':>5} {'ausw':>4}  {'dauer':>6} {'tier':>4}  "
        f"{'payoff':>6}  {'hook':<9} headline",
        "-" * 96,
    ]
    for i, p in enumerate(plaetze, 1):
        marke = "VERRAET" if p.hookbefund.verraeter else \
                ("lose" if not p.hookbefund.verankert else
                 ("offen" if p.hookbefund.offen else "ok"))
        po = f"{p.payoff:.0%}" if p.payoff is not None else "   -"
        zeilen.append(
            f"{i:>2}  {p.prognose.score:>5.1f} {p.auswahl:>4.2f}  "
            f"{p.dauer:>5.1f}s {p.tier:>4}  {po:>6}  {marke:<9} {p.headline}")
        if p.uneinig:
            zeilen.append(f"      uneinig: AI {p.auswahl:.2f} gegen Prognose "
                          f"{p.prognose.score / 100:.2f} — bitte selbst ansehen")
        for h in p.hinweise:
            zeilen.append(f"      ! {h}")
    return zeilen
