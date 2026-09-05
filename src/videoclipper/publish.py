"""Stage 16 — Veroeffentlichungsregister.

Haelt fest, welcher Clip wann auf welcher Plattform gelandet ist, unter welcher
Variante und mit welcher Prognose. Ohne diesen Eintrag ist spaeter nicht mehr
rekonstruierbar, warum ein Clip so lief, wie er lief — und dann ist jede
Messung nur noch eine Zahl ohne Ursache.

Die Zuweisung zu A/B-Armen passiert hier, nicht beim Auswerten. Sie ist
BALANCIERT, nicht zufaellig: Bei fuenf Posts pro Experiment liefert eine Muenze
regelmaessig 4:1, und ein Arm mit einem einzigen Post ist wertlos.
"""

from __future__ import annotations

import random
import re
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from . import store
from .scoring import konfiguration

PLATTFORMEN = ("tiktok", "youtube", "instagram")

# Aus einer geposteten URL die plattformseitige ID ziehen.
#
# Alle drei Muster sind am Ende verankert. Ohne die Verankerung liefert
# ``/video/9A`` die ID ``9`` statt gar nichts — zwei verschiedene URLs fallen
# dann auf dieselbe post_id zusammen und der zweite Post ueberschreibt den
# ersten. Gefunden vom Test test_zu_wenige_posts_pro_arm_entscheiden_nicht.
ENDE = r"(?=[/?#]|$)"
MUSTER = {
    "tiktok": re.compile(r"/video/(\d+)" + ENDE),
    "youtube": re.compile(r"(?:shorts/|watch\?v=|youtu\.be/)([\w-]{6,})" + ENDE),
    "instagram": re.compile(r"/(?:reel|p|reels)/([\w-]+)" + ENDE),
}


def extern_id(plattform: str, url: str) -> str | None:
    m = MUSTER[plattform].search(url)
    return m.group(1) if m else None


def naechste_variante(experiment_id: str, seed: int | None = None) -> str:
    """Der Arm mit den wenigsten Posts. Gleichstand wird ausgelost.

    Balanciert statt zufaellig, weil bei kleinen Fallzahlen die Verteilung
    selbst das Ergebnis dominiert.
    """
    exp = store.experiment(experiment_id)
    if exp is None:
        raise ValueError(f"Unbekanntes Experiment: {experiment_id}")

    zaehler = {name: 0 for name in exp["varianten"]}
    for p in store.posts():
        if p.get("experiment") == experiment_id and p.get("variante") in zaehler:
            zaehler[p["variante"]] += 1

    minimum = min(zaehler.values())
    kandidaten = sorted(k for k, v in zaehler.items() if v == minimum)
    rng = random.Random(seed if seed is not None else konfiguration()["ab"]["seed"]
                        + sum(zaehler.values()))
    return rng.choice(kandidaten)


def registriere(plattform: str, url: str, *, clip_id: str | None = None,
                veroeffentlicht: str | datetime | None = None,
                dauer: float | None = None, titel: str = "",
                experiment: str | None = None, variante: str | None = None,
                prognose: dict[str, Any] | None = None,
                notiz: str = "") -> dict[str, Any]:
    """Eine Veroeffentlichung eintragen.

    Ist ``experiment`` gesetzt und ``variante`` nicht, wird der Arm balanciert
    zugewiesen.
    """
    if plattform not in PLATTFORMEN:
        raise ValueError(f"Unbekannte Plattform {plattform!r}. "
                         f"Bekannt: {', '.join(PLATTFORMEN)}")

    ident = extern_id(plattform, url) or url.rstrip("/").rsplit("/", 1)[-1]
    post_id = f"{plattform}_{ident}"

    if experiment and not variante:
        variante = naechste_variante(experiment)

    if isinstance(veroeffentlicht, datetime):
        veroeffentlicht = veroeffentlicht.astimezone().isoformat(timespec="seconds")

    vorhanden = store.post(post_id) or {}
    satz = {
        **vorhanden,
        "post_id": post_id,
        "clip_id": clip_id if clip_id is not None else vorhanden.get("clip_id"),
        "plattform": plattform,
        "extern_id": ident,
        "url": url,
        "titel": titel or vorhanden.get("titel", ""),
        "dauer": dauer if dauer is not None else vorhanden.get("dauer"),
        "veroeffentlicht": veroeffentlicht or vorhanden.get("veroeffentlicht")
                           or store.jetzt(),
        "experiment": experiment if experiment is not None
                      else vorhanden.get("experiment"),
        "variante": variante if variante is not None else vorhanden.get("variante"),
        "prognose": prognose if prognose is not None else vorhanden.get("prognose"),
        "notiz": notiz or vorhanden.get("notiz", ""),
        "erfasst": store.jetzt(),
        "herkunft": "register",
    }
    store.speichere_post(satz)
    return satz


def verknuepfe(post_id: str, clip_id: str) -> dict[str, Any]:
    """Einen vom Sammler gefundenen Post nachtraeglich einem Clip zuordnen.

    Posts, die vor dem Bewertungssystem entstanden sind, haben keine
    ``clip_id``. Ohne sie laesst sich die Prognose nicht gegen das Ergebnis
    halten — die Verknuepfung ist deshalb die Voraussetzung fuer jede
    Kalibrierung.
    """
    p = store.post(post_id)
    if p is None:
        raise ValueError(f"Unbekannter Post: {post_id}")
    satz = {**p, "clip_id": clip_id, "erfasst": store.jetzt()}
    store.speichere_post(satz)
    return satz
