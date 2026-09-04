"""Kommandozeile.

``clip analyse``  Stages 03-05: Transkript, Signale, Kandidaten -> JSON-Artefakt.
``clip rendere``  Stages 08-13: Snapping, Layout, Render, QC.

Dazwischen liegt Stage 06, die Selektion. Die liefert strukturiertes JSON und
sonst nichts — keine Geometrie, keine Filterketten.
"""

from __future__ import annotations

import argparse
import json
from dataclasses import asdict
from pathlib import Path

from . import layout
from .candidates import bilde
from .editplan import Aufgeloest, EditPlan
from .qc import pruefe
from .render import rendere
from .settings import arbeitsverzeichnis, einstellungen
from .signals import ModusSignatur, sammle
from .snapping import snappe
from .transcript import lade_json3


def _artefakte() -> Path:
    p = Path(__file__).resolve().parents[2] / "data" / "artifacts"
    p.mkdir(parents=True, exist_ok=True)
    return p


def cmd_analyse(args: argparse.Namespace) -> None:
    video = Path(args.video).expanduser()
    prof = layout.profil(args.profil)
    tr = lade_json3(Path(args.transkript).expanduser(), args.video_id,
                    prof["quelle"].get("sprache", "de"))

    s = prof["signatur"]
    sig = ModusSignatur(s["modus"], kante_x=s.get("kante_x"),
                        kante_y=s.get("kante_y"),
                        bereich=tuple(s["bereich"]), schwelle=s["schwelle"])

    print(f"Transkript: {len(tr.woerter)} Woerter, {tr.dauer:.0f}s, "
          f"{len(tr.marker())} Marker")
    signale = sammle(video, tr, sig, schritt=args.schritt)
    anteil = float((signale.modus_wert > sig.schwelle).mean())
    print(f"Layout {sig.name}: {anteil:.0%} der Laufzeit")

    # Modus-Laeufe: zusammenhaengende Strecken eines Layouts. Die Selektion
    # braucht sie, um Clipgrenzen nicht mitten durch einen Layoutwechsel zu legen.
    aktiv = signale.modus_wert > sig.schwelle
    laeufe, i = [], 0
    while i < len(aktiv):
        j = i
        while j + 1 < len(aktiv) and aktiv[j + 1] == aktiv[i]:
            j += 1
        laeufe.append({
            "modus": sig.name if bool(aktiv[i]) else "SOLO",
            "start": round(float(signale.modus_zeiten[i]), 2),
            "ende": round(float(signale.modus_zeiten[j]) + args.schritt, 2),
        })
        i = j + 1

    kand = bilde(tr, signale, prof.get("signale", {}), maximal=args.anzahl)
    ziel = _artefakte() / f"kandidaten_{args.video_id}.json"
    ziel.write_text(json.dumps({
        "video_id": args.video_id,
        "profil": args.profil,
        "modus_name": sig.name,
        "modus_anteil_gesamt": anteil,
        "dauer": tr.dauer,
        "modus_laeufe": laeufe,
        "kandidaten": [asdict(k) for k in kand],
    }, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"{len(kand)} Kandidaten -> {ziel}")


def cmd_rendere(args: argparse.Namespace) -> None:
    plaene = json.loads(Path(args.plan).expanduser().read_text(encoding="utf-8"))
    video = Path(args.video).expanduser()
    prof = layout.profil(args.profil)
    tr = lade_json3(Path(args.transkript).expanduser(), args.video_id,
                    prof["quelle"].get("sprache", "de"))
    ausgabe = Path(args.ausgabe).expanduser() if args.ausgabe else \
        arbeitsverzeichnis() / "clips"

    for roh in plaene:
        modus = roh.pop("modus")
        anteil = roh.pop("modus_anteil", 1.0)
        tmpl = layout.template_fuer(args.profil, modus)

        start, ende, tier = snappe(tr, roh["timing"]["start"], roh["timing"]["ende"])
        roh["template"] = tmpl["name"]
        plan = EditPlan.model_validate(roh)
        plan.tier = tier
        plan.resolved = Aufgeloest(
            start=start, ende=ende, dauer=round(ende - start, 3),
            modus=modus, modus_anteil=anteil,
            panels=layout.panels(prof, tmpl, modus),
            canvas=tuple(tmpl["canvas"]),
            fps=int(einstellungen()["output"]["fps"]),
            headline_y=tmpl["headline"]["y"],
        )

        ziel = ausgabe / f"{plan.clip_id}.mp4"
        print(f"  {plan.clip_id}  {start:7.2f}-{ende:7.2f}  "
              f"{ende-start:5.1f}s  {tmpl['name']:12s} Tier {tier}  {plan.headline}")
        rendere(plan, tmpl, video, ziel, vorschau=args.vorschau)

        b = pruefe(ziel, tier)
        marke = "Tier A->B" if b.tier_korrigiert else f"Tier {b.tier}"
        print(f"      QC: {b.dauer:.2f}s {b.breite}x{b.hoehe} {marke}"
              + (f"  {'; '.join(b.hinweise)}" if b.hinweise else ""))

        (ausgabe / f"{plan.clip_id}.editplan.json").write_text(
            plan.model_dump_json(indent=2), encoding="utf-8")


def main() -> None:
    p = argparse.ArgumentParser(prog="clip")
    sub = p.add_subparsers(required=True)

    a = sub.add_parser("analyse", help="Transkript, Signale, Kandidaten")
    a.add_argument("--video", required=True)
    a.add_argument("--transkript", required=True)
    a.add_argument("--video-id", required=True)
    a.add_argument("--profil", required=True)
    a.add_argument("--schritt", type=float, default=2.0)
    a.add_argument("--anzahl", type=int, default=40)
    a.set_defaults(func=cmd_analyse)

    r = sub.add_parser("rendere", help="Snapping, Layout, Render, QC")
    r.add_argument("--plan", required=True)
    r.add_argument("--video", required=True)
    r.add_argument("--transkript", required=True)
    r.add_argument("--video-id", required=True)
    r.add_argument("--profil", required=True)
    r.add_argument("--ausgabe")
    r.add_argument("--vorschau", action="store_true")
    r.set_defaults(func=cmd_rendere)

    args = p.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
