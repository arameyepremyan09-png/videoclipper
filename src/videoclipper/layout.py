"""Stage 09 — Layout.

Materialprofil (Geometrie der Quelle) + Template (Zielkomposition) + erkannter
Modus ergeben konkrete Rechtecke. Rein deklarativ: Der Renderer bekommt Zahlen,
keine Entscheidungen.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import numpy as np
import yaml

from .settings import _deep_merge

ROOT = Path(__file__).resolve().parents[2]

# Overlays, die in jedem Clip gleich aussehen und deshalb nicht elfmal im
# Template stehen. Ein Template darf einzelne Werte ueberschreiben.
UEBERALL = ("sicherheitszone", "untertitel", "follow_hinweis", "kurzformat")


def _lade(ordner: str, name: str) -> dict[str, Any]:
    for pfad in (ROOT / "config" / ordner).glob("*.yaml"):
        daten = yaml.safe_load(pfad.read_text(encoding="utf-8"))
        if daten.get("name") == name:
            return daten
    raise FileNotFoundError(f"{ordner}/{name} nicht gefunden")


def _globale_overlays() -> dict[str, Any]:
    daten = yaml.safe_load(
        (ROOT / "config" / "overlays.yaml").read_text(encoding="utf-8"))
    return {k: daten[k] for k in UEBERALL if k in daten}


def _mit_overlays(tmpl: dict[str, Any]) -> dict[str, Any]:
    """Globale Pflicht-Overlays als Unterlage unter das Template legen.

    Gleiches Muster wie settings.toml/local.toml: Die allgemeine Fassung
    steht unten, das Template schreibt einzelne Werte darueber. Ein Template
    muss also nur nennen, was bei ihm anders ist.
    """
    return _deep_merge(_globale_overlays(), tmpl)


def profil(name: str) -> dict[str, Any]:
    return _lade("profiles", name)


def template(name: str) -> dict[str, Any]:
    return _mit_overlays(_lade("templates", name))


def template_fuer(profil_name: str, modus: str) -> dict[str, Any]:
    """Das Template, das zu diesem Profil und diesem Modus gehoert."""
    for pfad in (ROOT / "config" / "templates").glob("*.yaml"):
        daten = yaml.safe_load(pfad.read_text(encoding="utf-8"))
        if profil_name in (daten.get("default_fuer") or []) \
                and daten.get("gilt_fuer_modus") == modus:
            return _mit_overlays(daten)
    raise FileNotFoundError(f"Kein Template fuer {profil_name}/{modus}")


def panels(prof: dict, tmpl: dict, modus: str) -> list[dict]:
    """Loest Template-Panels gegen die Zonen des Modus auf.

    Ergebnis pro Panel: Quellrechteck (src), Zielrechteck (dst), Passung und
    optional der horizontale Fokus, um den beschnitten wird.
    """
    zonen = prof["modi"][modus]["zonen"]
    cb, ch = tmpl["canvas"]

    # In yuv420p muss jede Panelhoehe gerade sein — sonst rundet der Scaler
    # still ab und die Buehne wird ein paar Pixel zu kurz. Das faellt sonst
    # erst im QC der fertigen Datei auf.
    summe = 0
    for p in tmpl["panels"]:
        _, _, pw, ph = p["ziel"]
        if pw % 2 or ph % 2:
            raise ValueError(
                f"{tmpl['name']}: Panel {p['quelle']} hat ungerade Masse {pw}x{ph}")
        summe += ph
    if summe != ch:
        raise ValueError(
            f"{tmpl['name']}: Panelhoehen summieren zu {summe}, Canvas ist {ch}")

    out = []
    for p in tmpl["panels"]:
        zone = zonen[p["quelle"]]
        out.append({
            "name": p["quelle"],
            "src": list(zone["box"]),
            "dst": list(p["ziel"]),
            "passung": p.get("passung", "fuellen"),
            "ausrichtung": p.get("ausrichtung", "mitte"),
            "fokus_x": zone.get("fokus_x"),
            "fokus_y": zone.get("fokus_y"),
        })
    return out


def _gerade(n: float) -> int:
    i = int(round(n))
    return i - (i % 2)


def sichtbar(p: dict) -> tuple[tuple[int, int, int, int], tuple[int, int, int, int]]:
    """Welcher Quellausschnitt eines Panels wo auf der Canvas steht.

    Gibt (Quellrechteck, Canvasrechteck) zurueck, beide als (x, y, w, h).
    ``render._panel_kette`` baut daraus den Filter, ``kurzformat`` den
    Punch-in — beide aus derselben Rechnung, sonst saesse der Zoom um ein paar
    Pixel neben dem Bild, das er vergroessern soll.

    ``fuellen``   auf das Zielverhaeltnis beschnitten, um ``fokus_x``; das
                  Canvasrechteck ist das ganze Panel.
    ``einpassen`` die ganze Zone; das Canvasrechteck ist der Inhalt ohne
                  Blurreste, gesetzt nach ``ausrichtung`` (mitte, oben, unten).
    """
    sx, sy, sw, sh = p["src"]
    dx, dy, dw, dh = p["dst"]

    if p.get("passung", "fuellen") == "fuellen":
        ziel_ar, quell_ar = dw / dh, sw / sh
        if quell_ar > ziel_ar:                      # zu breit: seitlich schneiden
            nw, nh = _gerade(sh * ziel_ar), _gerade(sh)
            fokus = p.get("fokus_x")
            mitte = (fokus - sx) if fokus is not None else sw / 2
            ox, oy = int(min(max(mitte - nw / 2, 0), sw - nw)), 0
        else:                                        # zu hoch: oben/unten schneiden
            nw, nh = _gerade(sw), _gerade(sw / ziel_ar)
            ox, oy = 0, int((sh - nh) / 2)
        return (sx + ox, sy + oy, nw, nh), (dx, dy, dw, dh)

    skala = min(dw / sw, dh / sh)
    fw, fh = _gerade(sw * skala), _gerade(sh * skala)
    y = {"oben": 0, "unten": dh - fh}.get(p.get("ausrichtung", "mitte"),
                                          (dh - fh) // 2)
    return (sx, sy, sw, sh), (dx + (dw - fw) // 2, dy + y, fw, fh)


# ---------------------------------------------------------------------------
# Einschuebe — ein Clip ueber eine kurze Strecke eines anderen Modus
# ---------------------------------------------------------------------------
#
# WOZU: Seit dem 2026-09-04 gilt, dass Clipgrenzen nie ueber einem
# Layoutwechsel liegen, weil ein Clip mit EINEM Template gerendert wird. Bei
# ErYc_3POazo hat das zwei der besten Stellen gekostet. Bei jd9bSJ7mshM (1:1
# Kaese) waere es fast jede: Der Stream springt 28-mal fuer 2-8 s in die
# Vollbild-Cam, und zwar genau dann, wenn Coachlim auf eine Nachricht
# reagiert. Ein Clip, der davor endet, endet vor der Pointe; einer, der danach
# beginnt, hat keinen Aufbau. Der Nutzer hat fuer dieses Video ausdruecklich
# verlangt, dass "immer die volle Länge des Inhalts" drin ist.
#
# WIE: Das Layout bleibt stehen. Panels, fuer die das Profil eine Ersatzzone
# im anderen Modus nennt, werden waehrend der Strecke aus ihr gespeist (bei
# COACHLIM_KAESE_SNAP die Facecam aus der Vollbild-Cam — dieselbe Kamera,
# derselbe Ausschnitt). Alle anderen halten ihr letztes Bild. Der Zuschauer
# sieht also weiter die Nachricht, auf die reagiert wird, und darueber die
# Reaktion — statt eines Layoutsprungs alle paar Sekunden.
#
# WARUM BILDGENAU: Ein Frame zu frueh steht im oberen Panel das ganze
# Chatlayout verkleinert, ein Frame zu spaet ein Ausschnitt mitten aus der
# Vollbild-Cam. Die Zeiten kommen deshalb aus ``signals.modus_je_bild``, auf
# der Zeitachse des Filtergraphs — nicht aus dem Raster der Analyse.

MIN_BILDER = 2        # kuerzere Laeufe im Inneren sind Rauschen, kein Wechsel
HALTE_ABSTAND = 3     # so viele Bilder liegt das Haltebild vor dem Wechsel


def _laeufe(maske) -> list[tuple[int, int]]:
    """Zusammenhaengende True-Strecken als (erster, letzter) Index."""
    out, i, n = [], 0, len(maske)
    while i < n:
        if maske[i]:
            j = i
            while j + 1 < n and maske[j + 1]:
                j += 1
            out.append((i, j))
            i = j + 1
        else:
            i += 1
    return out


def _glaette(eigen: np.ndarray) -> np.ndarray:
    """Laeufe unter MIN_BILDER Bildern im Inneren gehoeren zu ihrer Umgebung.

    An den Clipraendern bleibt alles, wie es ist: Dort fehlt die Umgebung auf
    einer Seite, und ein Randbild falsch zu glaetten hiesse, genau dieses Bild
    mit dem falschen Panel zu zeigen.
    """
    e = eigen.copy()
    n = len(e)
    for wert in (False, True):
        for i0, i1 in _laeufe(e == wert):
            if i1 - i0 + 1 < MIN_BILDER and i0 > 0 and i1 < n - 1:
                e[i0:i1 + 1] = not wert
    return e


def einschuebe(prof: dict, tmpl: dict, modus: str, fremd: str,
               zeiten, eigen, dauer: float) -> list[dict]:
    """Strecken im Clip, in denen die Quelle in ``fremd`` statt ``modus`` steht.

    ``zeiten``  Zeitstempel JEDES Bildes ab Clipbeginn (Zeitachse des Renderers)
    ``eigen``   je Bild: steht dort ``modus``?
    ``dauer``   Cliplaenge

    Gibt je Strecke das Fenster fuer ``enable`` (``ab``/``bis``), das Haltebild
    (``halten_bei``) und die aufgeloesten Panels zurueck — ``ersatz`` aus der
    Zone des anderen Modus, ``halten`` mit dem Haltebild. Bricht mit
    ValueError ab, wenn eine Strecke nicht ueberbrueckt werden darf: Dann
    gehoert die Clipgrenze woanders hin, und das entscheidet Stage 06, nicht
    dieser Code.
    """
    zeiten = np.asarray(zeiten, dtype=float)
    eigen = _glaette(np.asarray(eigen, dtype=bool))
    if not len(eigen) or eigen.all():
        return []
    if not eigen.any():
        raise ValueError(f"Das Fenster liegt komplett in {fremd}, nicht in {modus}")

    conf = tmpl.get("einschub") or {}
    regel = (prof["modi"].get(fremd) or {}).get("einschub") or {}
    if not conf or regel.get("in") != modus:
        fremd_s = float((~eigen).sum()) / len(eigen) * dauer
        raise ValueError(
            f"{fremd_s:.1f}s {fremd} im Fenster, aber {prof['name']}/{tmpl['name']} "
            f"sehen keinen Einschub vor — die Clipgrenzen gehoeren verschoben")

    max_dauer = float(conf.get("max_dauer", 0.0))
    ersatz_von = regel.get("ersatz") or {}
    zonen = prof["modi"][fremd]["zonen"]
    alle = panels(prof, tmpl, modus)
    ersatz = [dict(p, src=list(zonen[ersatz_von[p["name"]]]["box"]),
                   fokus_x=zonen[ersatz_von[p["name"]]].get("fokus_x"))
              for p in alle if p["name"] in ersatz_von]
    halten = [p for p in alle if p["name"] not in ersatz_von]

    n = len(eigen)
    out = []
    for i0, i1 in _laeufe(~eigen):
        danach = i1 + 1
        ende = float(zeiten[danach]) if danach < n else dauer
        laenge = ende - float(zeiten[i0])
        if laenge > max_dauer:
            raise ValueError(
                f"{fremd}-Strecke {zeiten[i0]:.2f}-{ende:.2f}s im Clip ist "
                f"{laenge:.1f}s lang, {tmpl['name']} ueberbrueckt hoechstens "
                f"{max_dauer:.1f}s — die Clipgrenzen gehoeren verschoben")

        # Haltebild: ein paar Bilder VOR dem Wechsel, nicht das letzte. Das
        # letzte liegt 16.7 ms neben dem ersten fremden, und eine Rundung beim
        # Herausholen gaebe dann ein Bild aus dem anderen Modus. Liegt die
        # Strecke am Clipanfang, gibt es kein Vorher — dann das Bild danach.
        vor = np.flatnonzero(eigen[:i0])[::-1]
        nach = np.flatnonzero(eigen[danach:]) + danach
        kandidaten = vor if len(vor) else nach
        halt = int(kandidaten[min(HALTE_ABSTAND, len(kandidaten)) - 1])

        out.append({
            # 3 ms vor dem ersten fremden Bild, 5 ms vor dem ersten eigenen
            # danach: Die Fenster stehen mit drei Nachkommastellen im Graphen,
            # zwei Bilder liegen 16.7 ms auseinander. Am Clipende bleibt das
            # Fenster offen, damit die Rundung keinen letzten Frame freilegt.
            "ab": round(float(zeiten[i0]) - 0.003, 3),
            "bis": round(ende - 0.005, 3) if danach < n else round(dauer + 1.0, 3),
            "modus": fremd,
            "halten_bei": round(float(zeiten[halt]), 4),
            "ersatz": ersatz,
            "halten": halten,
        })
    return out
