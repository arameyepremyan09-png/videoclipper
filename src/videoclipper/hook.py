"""Stage 07 — Hookpruefung.

Die Headline ist das einzige Textfeld, das die AI liefert, und sie entscheidet,
ob jemand ueberhaupt stehenbleibt. Zwei Fehler kann sie machen, und beide sind
im fertigen Clip nicht mehr zu sehen:

1. **Sie verraet die Pointe.** "Er findet ein Klappmesser in der Tasche" ist
   keine Frage mehr — wer das liest, brauucht den Clip nicht. Messbar: Woerter
   der Headline, die im *letzten* Drittel des Clips fallen und im ersten nicht.
2. **Sie haengt in der Luft.** Eine Headline, deren Woerter im Clip gar nicht
   vorkommen, verspricht etwas anderes, als der Clip liefert. Der Zuschauer
   springt dann in der ersten Sekunde ab, und das ist teurer als ein schwacher
   Hook.

Beides ist eine Eigenschaft des Paares (Headline, Clipfenster) — also weder
Geometrie noch Zielkomposition, sondern eine Pruefung auf dem Plan. Sie laeuft
deshalb hier und nicht in ``forecast.py``: Die Prognose bewertet den Hook gegen
Annahmen aus ``scoring.yaml``, diese Pruefung vergleicht ihn gegen den
tatsaechlichen Inhalt des Clips.

Was hier NICHT passiert: Die Headline wird nicht umgeschrieben. Der Code
entscheidet WIE, nicht WAS — er meldet, das Umschreiben bleibt Stage 06.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from .forecast import STOPP
from .transcript import Transkript

# Woerter, die eine Frage offenlassen statt sie zu beantworten. Sie sind kein
# Qualitaetsbeweis — sie zeigen nur, dass die Headline zurueckhaelt.
OFFEN = {
    "was", "wer", "wie", "warum", "wieso", "wann", "wo", "wen", "wem",
    "keiner", "niemand", "jeder", "sowas", "dieser", "diese", "plötzlich",
    "dann", "passiert", "danach", "gleich", "einfach", "nie", "immer",
}


def _woerter(text: str) -> list[str]:
    return [w for w in re.findall(r"[\wäöüßÄÖÜ]+", text.lower()) if w]


def _inhaltswoerter(text: str) -> set[str]:
    """Woerter, die tatsaechlich etwas benennen. Fuellwoerter fliegen raus."""
    return {w for w in _woerter(text) if len(w) >= 4 and w not in STOPP}


@dataclass
class Hookbefund:
    headline: str
    zeichen: int
    verraeter: list[str] = field(default_factory=list)
    verankert: bool = True
    offen: bool = False
    hinweise: list[str] = field(default_factory=list)

    @property
    def taugt(self) -> bool:
        """Kein Ausschlusskriterium getroffen."""
        return not self.verraeter and self.verankert


def pruefe(headline: str, tr: Transkript, start: float, ende: float,
           payoff_ab: float = 0.66, max_zeichen: int = 42) -> Hookbefund:
    """Verraet die Headline den Clip? Und haengt sie ueberhaupt an ihm?

    ``payoff_ab`` ist der Anteil der Cliplaenge, ab dem die Pointe erwartet
    wird — alles danach gilt als Verratszone.
    """
    b = Hookbefund(headline, len(headline))
    eigene = _inhaltswoerter(headline)

    grenze = start + (ende - start) * payoff_ab
    vorn = _inhaltswoerter(tr.text_zwischen(start, grenze))
    hinten = _inhaltswoerter(tr.text_zwischen(grenze, ende))

    # Verraeter: steht in der Pointe, aber nicht im Aufbau. Woerter, die vorn
    # ohnehin fallen, verraten nichts — sie beschreiben nur, worum es geht.
    b.verraeter = sorted(eigene & hinten - vorn)
    if b.verraeter:
        b.hinweise.append(
            f"Verraet die Pointe: {', '.join(b.verraeter)} "
            f"faellt erst nach {grenze - start:.0f}s und steht schon im Titel")

    # Verankert: mindestens ein Inhaltswort kommt im Clip vor. Ohne das
    # verspricht die Headline etwas, das der Clip nicht einloest.
    if eigene:
        b.verankert = bool(eigene & (vorn | hinten))
        if not b.verankert:
            b.hinweise.append(
                "Kein Wort der Headline faellt im Clip — sie verspricht etwas "
                "anderes, als zu sehen ist")
    else:
        b.hinweise.append("Headline hat keine Inhaltswoerter")

    b.offen = bool(set(_woerter(headline)) & OFFEN) or headline.rstrip().endswith("?")
    if not b.offen:
        b.hinweise.append("Kein offenes Element — die Headline stellt keine Frage")

    if b.zeichen > max_zeichen:
        b.hinweise.append(
            f"{b.zeichen} Zeichen: laenger als {max_zeichen}, im Feed nicht "
            f"in einem Blick lesbar")

    return b


def hook_text(tr: Transkript, start: float, fenster: float = 3.0) -> str:
    """Der Wortlaut der ersten Sekunden — das, was ``forecast`` als Hook wertet."""
    return tr.text_zwischen(start, start + fenster)


def payoff_position(tr: Transkript, start: float, ende: float) -> float | None:
    """Wo im Clip die dichteste Sprechstelle liegt, als Anteil 0..1.

    Eine Naeherung, keine Pointenerkennung: Bei markerlosem Material gibt es
    kein Lachsignal (siehe CLAUDE.md), und ein Lacherdetektor aus dem Ton
    allein liegt gemessen unter dem Zufall. Die Wortdichte sagt immerhin, wo
    im Clip am meisten passiert.
    """
    dauer = ende - start
    if dauer <= 0:
        return None
    woerter = [w for w in tr.woerter if start <= w.start < ende and not w.ist_marker]
    if len(woerter) < 5:
        return None

    fenster = max(dauer / 6.0, 2.0)
    beste, bester_wert = None, -1
    t = start
    while t < ende:
        n = sum(1 for w in woerter if t <= w.start < t + fenster)
        if n > bester_wert:
            beste, bester_wert = t + fenster / 2, n
        t += fenster / 2
    return round(min(max((beste - start) / dauer, 0.0), 1.0), 3)
