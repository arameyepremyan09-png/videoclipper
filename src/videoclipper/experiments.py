"""A/B-Tests.

Kein Signifikanztest. Bei den Fallzahlen dieses Accounts — fuenf Posts pro Arm,
je rund tausend Views — liefert ein p-Wert entweder nichts oder eine
Scheingenauigkeit. Stattdessen Beta-Posteriors: Sie sind ab dem ersten
Datenpunkt lesbar, werden mit jedem weiteren schaerfer und beantworten die
Frage, die tatsaechlich interessiert — "wie wahrscheinlich ist A besser als B"
statt "kann ich die Nullhypothese verwerfen".

Zwei Regeln, beide aus den eigenen Daten begruendet:

**Genau eine Variable pro Experiment.** Wer Hook und Laenge gleichzeitig
aendert, weiss hinterher nicht, welches davon gewirkt hat.

**Kein Doppelpost desselben Clips.** Am 2026-09-04 kamen zwei TikToks auf 2
bzw. 4 Views, waehrend fuenf andere desselben Tages rund 900 erreichten. Das
sieht nach Duplikatsdrosselung aus. Eine Variable wird deshalb ueber mehrere
VERSCHIEDENE Clips randomisiert, nicht durch zweimaliges Hochladen desselben.
"""

from __future__ import annotations

import math
import random
import statistics
from dataclasses import dataclass, field
from typing import Any

from . import store
from .scoring import konfiguration

# Metriken, die ein echtes Zaehlverhaeltnis sind: Ereignisse pro View. Fuer sie
# ist das Beta-Binomial-Modell exakt.
ZAEHLMETRIKEN = {"like_rate": "likes", "kommentar_rate": "kommentare",
                 "share_rate": "shares", "save_rate": "saves",
                 "follow_rate": "follows"}
# Ein Mittelwert von Anteilen, kein Zaehlverhaeltnis. Das Beta-Modell ist hier
# eine Naeherung, die die Views als effektive Stichprobe nimmt.
MITTELMETRIKEN = {"completion_rate"}


@dataclass
class Arm:
    name: str
    posts: list[str] = field(default_factory=list)
    ereignisse: float = 0.0
    views: float = 0.0
    einzelraten: list[float] = field(default_factory=list)

    @property
    def rate(self) -> float | None:
        return self.ereignisse / self.views if self.views else None


@dataclass
class Ergebnis:
    experiment_id: str
    metrik: str
    arme: list[Arm]
    wahrscheinlichkeit: dict[str, float]   # je Arm: P(dieser Arm ist der beste)
    sieger: str | None
    entscheidbar: bool
    benoetigte_views_pro_arm: int | None
    hinweise: list[str] = field(default_factory=list)


# ---------------------------------------------------------------------------

def anlegen(experiment_id: str, variable: str, hypothese: str,
            varianten: dict[str, str], metrik: str = "like_rate") -> dict[str, Any]:
    cfg = konfiguration()["ab"]
    if variable not in cfg["variablen"]:
        raise ValueError(f"Unbekannte Variable {variable!r}. "
                         f"Erlaubt: {', '.join(cfg['variablen'])}")
    if len(varianten) < 2:
        raise ValueError("Ein A/B-Test braucht mindestens zwei Varianten")
    if metrik not in ZAEHLMETRIKEN and metrik not in MITTELMETRIKEN:
        raise ValueError(f"Unbekannte Metrik {metrik!r}")
    if store.experiment(experiment_id):
        raise ValueError(f"Experiment {experiment_id!r} existiert bereits")

    satz = {"experiment_id": experiment_id, "variable": variable,
            "hypothese": hypothese, "varianten": varianten, "metrik": metrik,
            "gestartet": store.jetzt(), "status": "laufend", "ergebnis": None}
    store.speichere_experiment(satz)
    return satz


def _sammle_arme(experiment_id: str, metrik: str, fenster: float) -> list[Arm]:
    exp = store.experiment(experiment_id)
    arme = {name: Arm(name) for name in exp["varianten"]}

    for p in store.posts():
        if p.get("experiment") != experiment_id:
            continue
        variante = p.get("variante")
        if variante not in arme:
            continue
        treffer = store.messung_im_fenster(p["post_id"], fenster)
        if treffer is None or not treffer.brauchbar:
            continue
        m = treffer.messung
        views = m.get("views")
        if not views:
            continue

        arm = arme[variante]
        arm.posts.append(p["post_id"])
        arm.views += views
        if metrik in ZAEHLMETRIKEN:
            wert = m.get(ZAEHLMETRIKEN[metrik])
            if wert is None:
                arm.posts.pop()
                arm.views -= views
                continue
            arm.ereignisse += wert
            arm.einzelraten.append(wert / views)
        else:
            cr = m.get("completion_rate")
            if cr is None:
                arm.posts.pop()
                arm.views -= views
                continue
            arm.ereignisse += cr * views
            arm.einzelraten.append(cr)

    return list(arme.values())


def _p_bester(arme: list[Arm], ziehungen: int, seed: int) -> dict[str, float]:
    """Monte-Carlo ueber die Posteriors. Fester Seed — gleicher Input,
    gleiches Ergebnis, wie bei jeder anderen Stage."""
    rng = random.Random(seed)
    treffer = {a.name: 0 for a in arme}
    for _ in range(ziehungen):
        beste, bester_wert = None, -1.0
        for a in arme:
            # Jeffreys-Prior Beta(0.5, 0.5): schwach genug, um bei Daten sofort
            # nachzugeben, und definiert auch bei null Ereignissen.
            alpha = a.ereignisse + 0.5
            beta = max(a.views - a.ereignisse, 0.0) + 0.5
            wert = rng.betavariate(alpha, beta)
            if wert > bester_wert:
                beste, bester_wert = a.name, wert
        treffer[beste] += 1
    return {k: v / ziehungen for k, v in treffer.items()}


def _benoetigte_views(a: Arm, b: Arm, schwelle: float) -> int | None:
    """Grobe Stichprobenschaetzung pro Arm fuer den beobachteten Effekt.

    Normal-Approximation, einseitig, Power 0.8. Bewusst als Groessenordnung
    zu lesen: Sie sagt, ob noch drei Posts fehlen oder dreihundert.
    """
    p1, p2 = a.rate, b.rate
    if p1 is None or p2 is None or abs(p1 - p2) < 1e-9:
        return None
    z_a = abs(_z(schwelle))
    z_b = 0.8416                      # Power 0.80
    n = ((z_a + z_b) ** 2 * (p1 * (1 - p1) + p2 * (1 - p2))) / (p1 - p2) ** 2
    return int(math.ceil(n))


def _z(p: float) -> float:
    """Quantil der Standardnormalverteilung (Acklam-Naeherung, reicht hier)."""
    if not 0 < p < 1:
        return 0.0
    a = [-3.969683028665376e+01, 2.209460984245205e+02, -2.759285104469687e+02,
         1.383577518672690e+02, -3.066479806614716e+01, 2.506628277459239e+00]
    b = [-5.447609879822406e+01, 1.615858368580409e+02, -1.556989798598866e+02,
         6.680131188771972e+01, -1.328068155288572e+01]
    c = [-7.784894002430293e-03, -3.223964580411365e-01, -2.400758277161838e+00,
         -2.549732539343734e+00, 4.374664141464968e+00, 2.938163982698783e+00]
    d = [7.784695709041462e-03, 3.224671290700398e-01, 2.445134137142996e+00,
         3.754408661907416e+00]
    pl, ph = 0.02425, 1 - 0.02425
    if p < pl:
        q = math.sqrt(-2 * math.log(p))
        return (((((c[0]*q+c[1])*q+c[2])*q+c[3])*q+c[4])*q+c[5]) / \
               ((((d[0]*q+d[1])*q+d[2])*q+d[3])*q+1)
    if p > ph:
        q = math.sqrt(-2 * math.log(1 - p))
        return -(((((c[0]*q+c[1])*q+c[2])*q+c[3])*q+c[4])*q+c[5]) / \
                ((((d[0]*q+d[1])*q+d[2])*q+d[3])*q+1)
    q, r = p - 0.5, (p - 0.5) ** 2
    return (((((a[0]*r+a[1])*r+a[2])*r+a[3])*r+a[4])*r+a[5])*q / \
           (((((b[0]*r+b[1])*r+b[2])*r+b[3])*r+b[4])*r+1)


def werte_aus(experiment_id: str, fenster: float | None = None) -> Ergebnis:
    exp = store.experiment(experiment_id)
    if exp is None:
        raise ValueError(f"Unbekanntes Experiment: {experiment_id}")

    cfg = konfiguration()["ab"]
    fenster = fenster if fenster is not None else konfiguration()["vergleichsfenster"]
    metrik = exp["metrik"]
    arme = _sammle_arme(experiment_id, metrik, fenster)

    hinweise: list[str] = []
    mager = [a.name for a in arme if len(a.posts) < cfg["min_posts_pro_arm"]]
    if mager:
        hinweise.append(
            f"Arm(e) {', '.join(mager)} unter {cfg['min_posts_pro_arm']} Posts — "
            "kein Ergebnis, egal wie deutlich der Unterschied aussieht")

    if any(a.views == 0 for a in arme):
        return Ergebnis(experiment_id, metrik, arme, {}, None, False, None,
                        hinweise + ["Mindestens ein Arm hat keine Messwerte"])

    wahrsch = _p_bester(arme, cfg["ziehungen"], cfg["seed"])
    fuehrend = max(wahrsch, key=wahrsch.get)
    entscheidbar = (not mager) and wahrsch[fuehrend] >= cfg["entscheidungsschwelle"]

    geordnet = sorted(arme, key=lambda a: a.rate or 0, reverse=True)
    noetig = _benoetigte_views(geordnet[0], geordnet[-1],
                               cfg["entscheidungsschwelle"]) if len(arme) >= 2 else None

    # Pooling ueber Posts unterschaetzt die Unsicherheit, wenn die Posts stark
    # streuen. Das wird gemeldet, nicht stillschweigend hingenommen.
    for a in arme:
        if len(a.einzelraten) >= 3:
            m = statistics.mean(a.einzelraten)
            if m > 0 and statistics.pstdev(a.einzelraten) / m > 0.6:
                hinweise.append(
                    f"Arm {a.name}: die Einzelposts streuen stark "
                    f"(±{statistics.pstdev(a.einzelraten)/m:.0%}) — die "
                    "zusammengefasste Rate wirkt sicherer, als sie ist")

    if metrik in MITTELMETRIKEN:
        hinweise.append(f"{metrik} ist ein Mittelwert, kein Zaehlverhaeltnis — "
                        "das Modell ist hier eine Naeherung")
    if not entscheidbar and wahrsch[fuehrend] < cfg["entscheidungsschwelle"]:
        hinweise.append(
            f"P({fuehrend}) = {wahrsch[fuehrend]:.0%}, Schwelle "
            f"{cfg['entscheidungsschwelle']:.0%} — weiter laufen lassen")

    return Ergebnis(experiment_id, metrik, arme, wahrsch,
                    fuehrend if entscheidbar else None, entscheidbar, noetig,
                    hinweise)
