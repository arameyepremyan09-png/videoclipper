"""Auswertung fuer die Kommandozeile.

Trennt strikt zwischen drei Gruppen, weil sie verschiedene Fragen beantworten:

    gerankt        genug Views fuer ein Urteil ueber den Clip
    ausspielung    zu wenig Views — hier sagt die Zahl etwas ueber die
                   Verteilung, nicht ueber den Inhalt
    unreif         noch keine Reifezeit erreicht

Diese Trennung ist der Grund, warum die Rangliste ueberhaupt taugt: Ein Post
mit vier Views hat keine schlechte Qualitaet, er hat gar keine gemessene.
"""

from __future__ import annotations

import statistics
from dataclasses import dataclass, field
from typing import Any

from . import store
from .scoring import Bewertung, bewerte, konfiguration, raten


@dataclass
class Zeile:
    post: dict[str, Any]
    messung: dict[str, Any]
    bewertung: Bewertung
    rohraten: dict[str, float | None]

    @property
    def views(self) -> int:
        return self.messung.get("views") or 0


@dataclass
class Auswertung:
    gerankt: list[Zeile] = field(default_factory=list)
    ausspielung: list[Zeile] = field(default_factory=list)
    unreif: list[Zeile] = field(default_factory=list)
    ohne_messung: list[dict] = field(default_factory=list)
    mediane: dict[str, float] = field(default_factory=dict)
    fenster: float = 24.0


def sammle_auswertung(fenster: float | None = None,
                      plattform: str | None = None) -> Auswertung:
    cfg = konfiguration()
    fenster = fenster if fenster is not None else cfg["vergleichsfenster"]
    min_views = cfg["glaettung"]["min_views_fuer_urteil"]
    reifezeit = cfg["reifezeit_stunden"]

    posts = [p for p in store.posts()
             if plattform is None or p["plattform"] == plattform]

    # Mediane je Plattform im selben Fenster — Bezugsgroesse der Reichweitenachse.
    roh: list[tuple[dict, dict]] = []
    for p in posts:
        treffer = store.messung_im_fenster(p["post_id"], fenster)
        if treffer is None:
            continue
        roh.append((p, treffer.messung))

    mediane: dict[str, float] = {}
    for pl in {p["plattform"] for p, _ in roh}:
        views = [m.get("views") or 0 for p, m in roh if p["plattform"] == pl]
        if views:
            mediane[pl] = statistics.median(views)

    a = Auswertung(mediane=mediane, fenster=fenster)
    gemessen = {p["post_id"] for p, _ in roh}
    a.ohne_messung = [p for p in posts if p["post_id"] not in gemessen]

    for p, m in roh:
        b = bewerte(m, p["plattform"], p.get("dauer"), mediane.get(p["plattform"]))
        z = Zeile(p, m, b, raten(m, p.get("dauer"), p["plattform"], geglaettet=False))
        if (m.get("alter_stunden") or 0) < reifezeit:
            a.unreif.append(z)
        elif z.views < min_views:
            a.ausspielung.append(z)
        else:
            a.gerankt.append(z)

    a.gerankt.sort(key=lambda z: z.bewertung.score, reverse=True)
    a.ausspielung.sort(key=lambda z: z.views, reverse=True)
    a.unreif.sort(key=lambda z: z.views, reverse=True)
    return a


# ---------------------------------------------------------------------------
# Muster
# ---------------------------------------------------------------------------

def _spearman(xs: list[float], ys: list[float]) -> float | None:
    """Rangkorrelation. Robuster als Pearson, weil Social-Metriken schief sind
    und ein einzelner viraler Ausreisser sonst alles bestimmt."""
    n = len(xs)
    if n < 4:
        return None

    def raenge(w: list[float]) -> list[float]:
        sortiert = sorted(range(n), key=lambda i: w[i])
        r = [0.0] * n
        i = 0
        while i < n:
            j = i
            while j + 1 < n and w[sortiert[j + 1]] == w[sortiert[i]]:
                j += 1
            mittel = (i + j) / 2 + 1
            for k in range(i, j + 1):
                r[sortiert[k]] = mittel
            i = j + 1
        return r

    rx, ry = raenge(xs), raenge(ys)
    mx, my = statistics.mean(rx), statistics.mean(ry)
    zaehler = sum((a - mx) * (b - my) for a, b in zip(rx, ry))
    nenner = (sum((a - mx) ** 2 for a in rx) * sum((b - my) ** 2 for b in ry)) ** 0.5
    return zaehler / nenner if nenner else None


@dataclass
class Muster:
    name: str
    aussage: str
    staerke: float | None
    fallzahl: int
    belastbar: bool


def muster(a: Auswertung) -> list[Muster]:
    """Zusammenhaenge, die die Daten hergeben — mit ehrlicher Fallzahl.

    Ab vier Punkten wird gerechnet, ab zwoelf gilt das Ergebnis als belastbar.
    Alles dazwischen ist eine Hypothese fuer den naechsten A/B-Test, nicht mehr.
    """
    zeilen = a.gerankt
    ergebnis: list[Muster] = []

    # Dauer gegen Engagement — der Zielkonflikt mit der Tier-A-Strategie.
    paare = [(z.post["dauer"], z.rohraten.get("like_rate"))
             for z in zeilen if z.post.get("dauer") and z.rohraten.get("like_rate")]
    if len(paare) >= 4:
        r = _spearman([p[0] for p in paare], [p[1] for p in paare])
        if r is not None:
            richtung = ("laengere Clips schneiden schlechter ab" if r < -0.3 else
                        "laengere Clips schneiden besser ab" if r > 0.3 else
                        "kein erkennbarer Zusammenhang")
            ergebnis.append(Muster(
                "Dauer -> Like-Rate", f"{richtung} (rho {r:+.2f})", r,
                len(paare), len(paare) >= 12))

    # Postzeit gegen Reichweite.
    zeit = [(int(z.post["veroeffentlicht"][11:13]), z.views)
            for z in zeilen if z.post.get("veroeffentlicht")]
    stunden = {h for h, _ in zeit}
    if len(zeit) >= 4 and len(stunden) >= 3:
        r = _spearman([t[0] for t in zeit], [float(t[1]) for t in zeit])
        if r is not None:
            ergebnis.append(Muster(
                "Postzeit -> Views",
                f"spaeter am Tag {'mehr' if r > 0 else 'weniger'} Views "
                f"(rho {r:+.2f})", r, len(zeit), len(zeit) >= 12))
    elif zeit:
        ergebnis.append(Muster(
            "Postzeit -> Views",
            f"alle Posts liegen in {len(stunden)} Stunde(n) — Postzeit ist "
            "nicht variiert worden und damit nicht auswertbar",
            None, len(zeit), False))

    return ergebnis


def luecken(a: Auswertung) -> list[str]:
    """Welche Metriken fehlen und was dadurch nicht bewertbar ist."""
    alle = a.gerankt + a.ausspielung + a.unreif
    if not alle:
        return ["Keine Messungen vorhanden — `clip sammle` ausfuehren"]

    fehlt: dict[str, int] = {}
    for z in alle:
        for feld in store.NUR_INTERN:
            if z.messung.get(feld) is None:
                fehlt[feld] = fehlt.get(feld, 0) + 1

    text = []
    n = len(alle)
    for feld, anzahl in sorted(fehlt.items(), key=lambda kv: -kv[1]):
        if anzahl:
            text.append(f"{feld}: fehlt bei {anzahl}/{n} Posts")
    if fehlt.get("completion_rate") or fehlt.get("avg_watchtime"):
        text.append("-> Retention traegt 40 % des Scores und ist damit ungedeckt. "
                    "`clip trage-nach` fuellt sie aus dem Creator-Center.")
    return text
