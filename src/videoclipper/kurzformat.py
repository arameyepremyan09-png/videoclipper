"""Kurzformat — der lustigste Moment zuerst, dann die Geschichte. Ab 2026-09-11.

Zwei Auftraege des Nutzers am selben Tag, der zweite korrigiert den ersten:

1. "Clips sehr kurz, maximal 30 s, am besten 10-15 s, der Lacher in den
   ersten 3-5 Sekunden." Gebaut und mit fuenf Beispielen ausgeliefert.
2. Die Rueckmeldung darauf: "Die Clips sind oft zu kurz, man versteht nicht,
   was der Kontext dahinter ist. Lieber die sehr lustigen Momente am Anfang
   und dann das Video bis mindestens 30 Sekunden oder drueber laufen lassen."

Daraus der Aufbau: ein kurzer TEASER mit dem lustigsten Moment, dann ein harter
Schnitt zurueck an den Anfang der Geschichte, und die laeuft mit Kontext ueber
die Pointe hinaus. Der Moment kommt also zweimal — einmal als Hook, einmal an
seiner Stelle. Einfach ab dem Lacher weiterlaufen haette den Kontext nicht
geliefert: Der liegt vor der Pointe, nicht dahinter.

Was davon Code ist:

* ``segmente``    Teaser und Hauptteil als Folge von Quellfenstern.
* ``pruefe``      Gesamtlaenge, Teaserlaenge und ob die Pointe im Teaser liegt —
                  am gesnappten Clip, nicht am Plan.
* ``punch_in``    harter Zoom auf die Pointe, in jedem Segment, das sie zeigt.
* ``punch_im_einschub`` denselben Zoom dort aus der Ersatzzone nehmen, wo ein
                  Einschub das Panel ersetzt.
* ``follow_conf`` die Follow-Szene hinter den Teaser legen.
* ``verdeckt``    melden, wenn sie trotzdem auf einer Pointe liegt.

Was nicht: WELCHER Moment der Teaser ist, wo die Geschichte anfaengt und wo die
Pointe faellt. Das entscheidet Stage 06 (``EditPlan.teaser``, ``timing``,
``pointe``).
"""

from __future__ import annotations

from . import layout
from .editplan import Pointe


def segmente(teaser: tuple[float, float],
             haupt: tuple[float, float]) -> list[dict]:
    """Die Quellfenster in Clipreihenfolge, mit ihrer Lage im fertigen Clip."""
    out, ab = [], 0.0
    for art, (s, e) in (("teaser", teaser), ("haupt", haupt)):
        out.append({"art": art, "start": round(s, 3), "ende": round(e, 3),
                    "dauer": round(e - s, 3), "ab": round(ab, 3)})
        ab += e - s
    return out


def pruefe(segs: list[dict], pointe: Pointe | None,
           conf: dict) -> tuple[list[str], list[str]]:
    """Haelt der gesnappte Clip die Regeln? Gibt (Abbruchgruende, Hinweise).

    Abbruch: kuerzer als ``dauer_min`` — das ist die Rueckmeldung des Nutzers
    woertlich —, ein Teaser ausserhalb seiner Grenzen, oder eine Pointe, die
    nicht im Teaser liegt (dann zeigt der Hook etwas anderes als den Lacher).
    Hinweis: laenger als das Ziel.
    """
    teaser = segs[0]
    dauer = sum(s["dauer"] for s in segs)
    tmin, tmax = float(conf["teaser"]["min"]), float(conf["teaser"]["max"])
    ziel_min, ziel_max = (float(x) for x in conf["dauer_ziel"])

    fehler, hinweise = [], []
    if dauer < float(conf["dauer_min"]):
        fehler.append(f"{dauer:.1f}s lang — verlangt sind mindestens "
                      f"{float(conf['dauer_min']):.0f}s")
    if not tmin <= teaser["dauer"] <= tmax:
        fehler.append(f"Teaser {teaser['dauer']:.1f}s — erlaubt sind "
                      f"{tmin:.0f}-{tmax:.0f}s")
    if pointe is not None and not teaser["start"] <= pointe.t < teaser["ende"]:
        fehler.append("Die Pointe liegt nicht im Teaser — der Hook zeigte dann "
                      "etwas anderes als den Lacher")
    if not fehler and not ziel_min <= dauer <= ziel_max:
        hinweise.append(f"{dauer:.1f}s — Ziel sind {ziel_min:.0f}-{ziel_max:.0f}s")
    return fehler, hinweise


def _gerade_ab(n: float) -> int:
    i = int(n)
    return i - (i % 2)


def punch_in(pointe: Pointe, segs: list[dict], panels: list[dict],
             conf: dict) -> list[dict]:
    """Je Segment, das die Pointe zeigt, und je gezoomtem Panel ein Eintrag.

    ``ab``/``bis`` liegen auf der Zeitachse des fertigen Clips; ``segment``
    nennt das Quellfenster, aus dem das Bild kommt — der Renderer baut je
    Segment eine eigene Buehne. Liegt die Pointe im Teaser und im Hauptteil,
    zoomt es beide Male: Wer bis zur Pointe geblieben ist, bekommt sie so, wie
    der Hook sie versprochen hat.

    Die Quellbox ist das sichtbare Rechteck des Panels, um ``zoom`` verkleinert
    und um den Fokus der Zone gelegt (``fokus_x``/``fokus_y``, sonst die
    Mitte). Sie bleibt immer innerhalb des sichtbaren Rechtecks — sonst stuende
    im Zoom Rahmen oder Schwarz, das vorher nicht zu sehen war.

    ``pointe.fokus`` nennt Zonen; leer heisst alle Panels. Ein unbekannter
    Name bricht ab, statt still auf alle zurueckzufallen.
    """
    pc = conf["punch_in"]
    zoom = float(pc["zoom"])
    if zoom <= 1.0:
        return []

    namen = {p["name"] for p in panels}
    if fremd := sorted(set(pointe.fokus) - namen):
        raise ValueError(f"Pointe nennt {', '.join(fremd)} — das Template hat "
                         f"nur {', '.join(sorted(namen))}")

    out = []
    for k, seg in enumerate(segs):
        if not seg["start"] <= pointe.t < seg["ende"]:
            continue
        ab = pointe.t - seg["start"]
        bis = ((pointe.bis - seg["start"]) if pointe.bis is not None
               else ab + float(pc["dauer"]))
        bis = min(max(bis, ab + float(pc["min_dauer"])),
                  ab + float(pc["max_dauer"]), seg["dauer"])
        for p in panels:
            if pointe.fokus and p["name"] not in pointe.fokus:
                continue
            quelle, ziel = _zoombox(p, zoom)
            out.append({
                "segment": k,
                "panel": p["name"],
                "ab": round(seg["ab"] + ab, 3),
                "bis": round(seg["ab"] + bis, 3),
                "quelle": quelle,
                "ziel": ziel,
            })
    return out


def _zoombox(p: dict, zoom: float) -> tuple[list[int], list[int]]:
    """Quellbox des Zooms und Canvasrechteck fuer ein aufgeloestes Panel."""
    (qx, qy, qw, qh), ziel = layout.sichtbar(p)
    zw, zh = _gerade_ab(qw / zoom), _gerade_ab(qh / zoom)
    fx = p["fokus_x"] if p.get("fokus_x") is not None else qx + qw / 2
    fy = p["fokus_y"] if p.get("fokus_y") is not None else qy + qh / 2
    zx = min(max(_gerade_ab(fx - zw / 2), qx), qx + qw - zw)
    zy = min(max(_gerade_ab(fy - zh / 2), qy), qy + qh - zh)
    return [int(zx), int(zy), zw, zh], list(ziel)


def punch_im_einschub(punch: list[dict], einschuebe: list[dict],
                      conf: dict) -> tuple[list[dict], list[str]]:
    """Punch-in und Einschub im selben Fenster — ab 2026-09-16.

    Waehrend eines Einschubs zeigt ein Panel nicht mehr seine eigene Zone
    (siehe ``layout.einschuebe``). Ein Punch-in mit der Quellbox des Live-Panels
    schnitte dort also eine Stelle aus dem ANDEREN Bild — bei I-mbVr4qgFs die
    Facecam-Koordinaten aus einer Vollbild-Cam, die zudem eigene Zoomschnitte
    hat. Deshalb wird jeder Eintrag an den Einschubgrenzen geteilt:

    * ausserhalb bleibt er, wie er ist;
    * innen zoomt ein **Ersatz**-Panel aus seiner Ersatzzone, mit derselben
      Rechnung wie live (``_zoombox``);
    * ein **gehaltenes** Panel zoomt dort nicht — sein Bild ist ein Standbild,
      das im Graphen nicht als Videoeingang vorliegt. Das wird gemeldet.

    Beide Listen stehen auf der Clipachse und tragen ``segment``.
    """
    zoom = float(conf["punch_in"]["zoom"])
    out: list[dict] = []
    hinweise: list[str] = []
    for e in punch:
        stuecke = [(e["ab"], e["bis"], None)]
        for x in einschuebe:
            if x.get("segment", 0) != e.get("segment", 0):
                continue
            neu = []
            for a, b, ersatz in stuecke:
                if ersatz is not None or b <= x["ab"] or x["bis"] <= a:
                    neu.append((a, b, ersatz))
                    continue
                if a < x["ab"]:
                    neu.append((a, x["ab"], None))
                neu.append((max(a, x["ab"]), min(b, x["bis"]), x))
                if x["bis"] < b:
                    neu.append((x["bis"], b, None))
            stuecke = neu
        for a, b, x in stuecke:
            if b - a <= 0.0:
                continue
            if x is None:
                out.append(dict(e, ab=round(a, 3), bis=round(b, 3)))
                continue
            ersatz = [p for p in x["ersatz"] if p["name"] == e["panel"]]
            if not ersatz:
                hinweise.append(f"Punch-in auf {e['panel']} faellt {a:.2f}-{b:.2f}s "
                                f"in einen Einschub mit gehaltenem Bild — dort kein Zoom")
                continue
            quelle, ziel = _zoombox(ersatz[0], zoom)
            out.append(dict(e, ab=round(a, 3), bis=round(b, 3),
                            quelle=quelle, ziel=ziel))
    return out, hinweise


def follow_conf(fw_conf: dict, segs: list[dict], conf: dict) -> dict:
    """Die Follow-Konfiguration, so verschoben, dass sie erst im Hauptteil beginnt.

    Im Teaser hat der Zuschauer noch nicht entschieden, ob er bleibt — eine
    Aufforderung dort fragt zu frueh. ``follow.platziere`` bleibt unveraendert;
    es bekommt nur eine andere Schranke.
    """
    if len(segs) < 2:
        return fw_conf
    fk = conf.get("follow_hinweis") or {}
    neu = dict(fw_conf)
    neu["nicht_vor"] = max(float(fw_conf.get("nicht_vor", 3.0)),
                           segs[1]["ab"] + float(fk.get("abstand", 1.0)))
    return neu


def verdeckt(ab: float, bis: float, punch: list[dict]) -> list[str]:
    """Meldung, wenn die Follow-Szene auf einem Punch-in liegt."""
    for e in punch:
        if ab < e["bis"] and e["ab"] < bis:
            return [f"Follow-Szene {ab:.1f}-{bis:.1f}s liegt auf der Pointe bei "
                    f"{e['ab']:.1f}s — Plan pruefen"]
    return []
