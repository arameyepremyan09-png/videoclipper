"""Kommandozeile.

Herstellung:
``clip analyse``  Stages 03-05: Transkript, Signale, Kandidaten -> JSON-Artefakt.
``clip rendere``  Stages 08-13: Snapping, Layout, Render, QC.

``clip frames``   Standbilder aus einem Video, zum Anschauen statt Abspielen.
``clip countdown`` Top-5-Compilation: N Segmente, mitwachsende Liste.

Dazwischen liegt Stage 06, die Selektion. Die liefert strukturiertes JSON und
sonst nichts — keine Geometrie, keine Filterketten.

Bewertung (Stages 15-17), der Kreis zurueck zum Anfang:
``clip prognose``    Stage 15: was sich vor dem Posten sagen laesst.
``clip registriere`` Stage 16: was wann wo veroeffentlicht wurde.
``clip sammle``      Stage 17: Messwerte abrufen.
``clip trage-nach``  Stage 17: Creator-Center-Werte ergaenzen.
``clip bewerte``     Rangliste, Muster, Luecken.
``clip ab``          A/B-Tests anlegen und auswerten.
``clip kalibriere``  Annahmen durch die eigenen Zahlen ersetzen.
"""

from __future__ import annotations

import argparse
import json
from dataclasses import asdict
from pathlib import Path

from . import layout
from .candidates import bilde
from .editplan import Aufgeloest, EditPlan
from . import countdown, frames
from .qc import pruefe
from .render import rendere, rendere_countdown
from .settings import arbeitsverzeichnis, einstellungen
from .signals import ModusSignatur, sammle
from .snapping import snappe
from .transcript import lade_json3

# --- Bewertungssystem ------------------------------------------------------
from datetime import datetime

from . import calibrate, collect, experiments, publish, report, store
from .forecast import Merkmale, prognostiziere
from .scoring import konfiguration


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


def cmd_frames(args: argparse.Namespace) -> None:
    video = frames.aufloesen(args.quelle)
    ziel_dir = Path(args.ziel).expanduser() if args.ziel else video.parent / "frames"
    print(f"Quelle: {video}")

    if args.bei:
        pfade = frames.einzelbilder(video, args.bei, ziel_dir, breite=args.breite)
        for pfad in pfade:
            print(f"  {pfad}")
        return

    spalten, zeilen = (int(x) for x in args.raster.lower().split("x"))
    ziel = ziel_dir / f"{video.stem}_bogen.png"
    karte = frames.kontaktbogen(video, ziel, spalten, zeilen,
                                breite=args.breite or 480, alle=args.alle)

    print(f"  {ziel}")
    # drawtext fehlt im FFmpeg-Build auf dem MacBook, also steht die Zeit
    # nicht im Bild, sondern hier daneben.
    for i in range(0, len(karte), spalten):
        reihe = karte[i:i + spalten]
        print("  " + "  ".join(f"{n:>2}: {t:7.1f}s" for n, t in reihe))


def _quellen(plan: countdown.CountdownPlan) -> dict[str, Path]:
    """video_id -> Datei im Quellordner des Arbeitsverzeichnisses."""
    quell_dir = arbeitsverzeichnis() / "source"
    gefunden = {}
    for e in plan.eintraege:
        treffer = sorted(quell_dir.glob(f"{e.video_id}.*"))
        treffer = [t for t in treffer if t.suffix in (".mp4", ".mkv", ".webm")]
        if not treffer:
            raise FileNotFoundError(
                f"{e.video_id} liegt nicht in {quell_dir}. "
                f"Erst laden: clip frames <url> holt es ebenfalls dorthin.")
        gefunden[e.video_id] = treffer[0]
    return gefunden


def cmd_countdown(args: argparse.Namespace) -> None:
    daten = json.loads(Path(args.plan).expanduser().read_text(encoding="utf-8"))
    plan = countdown.CountdownPlan.model_validate(daten)
    tmpl = layout.template(plan.template)

    for hinweis in countdown.sicherheitszone_pruefen(tmpl):
        print(f"  Hinweis: {hinweis}")

    plan = countdown.loese_auf(plan, tmpl)
    r = plan.aufgeloest
    print(f"{plan.clip_id}: {len(r.segmente)} Segmente, {r.dauer:.1f}s "
          f"({'Tier A' if r.dauer > 63 else 'Tier B'})")
    for seg in r.segmente:
        print(f"   Platz {seg['platz']}  {seg['ab']:6.1f}-{seg['bis']:6.1f}s  "
              f"aus {seg['video_id']} ab {seg['start']:.1f}s")

    ausgabe = Path(args.ausgabe).expanduser() if args.ausgabe else \
        arbeitsverzeichnis() / "clips"
    ziel = ausgabe / f"{plan.clip_id}.mp4"
    rendere_countdown(plan, tmpl, _quellen(plan), ziel, vorschau=args.vorschau)

    b = pruefe(ziel, "A" if r.dauer > 63 else "B")
    marke = "Tier A->B" if b.tier_korrigiert else f"Tier {b.tier}"
    print(f"   QC: {b.dauer:.2f}s {b.breite}x{b.hoehe} {marke}"
          + (f"  {'; '.join(b.hinweise)}" if b.hinweise else ""))
    (ausgabe / f"{plan.clip_id}.countdown.json").write_text(
        plan.model_dump_json(indent=2), encoding="utf-8")
    print(f"   {ziel}")


# ===========================================================================
# Bewertungssystem
# ===========================================================================

def _kurz(text: str, n: int) -> str:
    text = (text or "").strip().replace("\n", " ")
    return text if len(text) <= n else text[: n - 1] + "\u2026"


def cmd_sammle(args: argparse.Namespace) -> None:
    b = collect.sammle(args.plattform or None, grenze=args.grenze)
    print(f"{b.neu} neue Posts, {b.gemessen} Messungen abgelegt")
    for u in b.uebersprungen:
        print(f"  uebersprungen  {u}")
    for f in b.fehler:
        print(f"  FEHLER         {f}")


def cmd_trage_nach(args: argparse.Namespace) -> None:
    werte = {k: v for k, v in (
        ("views", args.views), ("likes", args.likes),
        ("kommentare", args.kommentare), ("shares", args.shares),
        ("saves", args.saves), ("follows", args.follows),
        ("avg_watchtime", args.watchtime),
        ("completion_rate", args.completion),
        ("profilaufrufe", args.profilaufrufe)) if v is not None}
    if not werte:
        raise SystemExit("Keine Werte angegeben — siehe `clip trage-nach --help`")
    satz = collect.trage_nach(args.post, werte, args.alter)
    print(f"{args.post}: {len(werte)} Werte ergaenzt "
          f"(Alter {satz.get('alter_stunden', '?')} h)")


def cmd_registriere(args: argparse.Namespace) -> None:
    p = publish.registriere(
        args.plattform, args.url, clip_id=args.clip_id, titel=args.titel or "",
        dauer=args.dauer, veroeffentlicht=args.veroeffentlicht,
        experiment=args.experiment, variante=args.variante, notiz=args.notiz or "")
    zusatz = f"  Experiment {p['experiment']} / Arm {p['variante']}" \
        if p.get("experiment") else ""
    print(f"{p['post_id']} eingetragen{zusatz}")


def cmd_prognose(args: argparse.Namespace) -> None:
    postzeit = datetime.fromisoformat(args.postzeit) if args.postzeit else None
    historie = [(z.post["titel"], z.bewertung.score)
                for z in report.sammle_auswertung().gerankt]
    p = prognostiziere(Merkmale(
        headline=args.headline, dauer=args.dauer, plattform=args.plattform,
        hook_text=args.hook or "", payoff_position=args.payoff,
        postzeit=postzeit, hashtags=args.hashtag or []), historie)

    print(f"\nPrognose {p.score:.0f}/100   Konfidenz {p.konfidenz:.0%}"
          f"   {'kalibriert' if p.kalibriert else 'NICHT kalibriert'}")
    print("-" * 66)
    for name, t in p.teile.items():
        balken = "#" * int(round(t.wert * 20))
        print(f"  {name:9} {t.wert:4.2f} {balken:<20}  {t.grund}")
    print(f"\n  Beste Stunden laut Konfiguration: "
          f"{', '.join(f'{h:02d}' for h in p.beste_stunden)} Uhr")
    for h in p.hinweise:
        print(f"  ! {h}")
    print()


def _zeile(z, breite: int = 34) -> str:
    b = z.bewertung
    r = z.rohraten
    def pct(x):
        return f"{x:5.2%}" if x is not None else "    -"
    # Wo die Reichweite fuer kein Urteil reicht, steht auch keine Zahl. Ein
    # Score von 41 neben 4 Views laedt dazu ein, ihn trotzdem zu lesen.
    kopf = f"{b.score:>5.1f}" if b.genug_views else "    -"
    return (f"{kopf}  {z.post['plattform'][:2]:2} "
            f"{(z.post.get('dauer') or 0):>3.0f}s {z.views:>6}  "
            f"{pct(r.get('like_rate'))} {pct(r.get('share_rate'))} "
            f"{pct(r.get('save_rate'))} {pct(r.get('completion_rate'))}  "
            f"{_kurz(z.post['titel'], breite)}")


def cmd_bewerte(args: argparse.Namespace) -> None:
    a = report.sammle_auswertung(args.fenster, args.plattform)
    kopf = (f"{'score':>5}  {'pl':2} {'dau':>4} {'views':>6}  "
            f"{'like':>5} {'shr':>5} {'save':>5} {'compl':>5}  titel")

    print(f"\nMessfenster {a.fenster:.0f} h   Mediane: "
          + "  ".join(f"{k} {v:.0f}" for k, v in a.mediane.items()))

    if a.gerankt:
        print(f"\nRANGLISTE  ({len(a.gerankt)} Posts mit genug Reichweite)")
        print(kopf)
        print("-" * 92)
        for z in a.gerankt:
            print(_zeile(z))
            for h in z.bewertung.hinweise[:1]:
                print(f"       {h}")
    else:
        print("\nRANGLISTE  leer — kein Post hat Reifezeit und Mindestreichweite "
              "zugleich erreicht")

    if a.ausspielung:
        print(f"\nZU WENIG REICHWEITE FUER EIN URTEIL  ({len(a.ausspielung)})")
        print("  Diese Zahlen sagen etwas ueber die Ausspielung, nicht ueber den Clip.")
        print(kopf)
        print("-" * 92)
        for z in a.ausspielung:
            print(_zeile(z))

    if a.unreif:
        print(f"\nNOCH NICHT REIF  ({len(a.unreif)}, unter "
              f"{konfiguration()['reifezeit_stunden']} h)")
        print(kopf)
        print("-" * 92)
        for z in a.unreif:
            print(_zeile(z))

    m = report.muster(a)
    if m:
        print("\nMUSTER")
        for x in m:
            marke = "belegt" if x.belastbar else f"n={x.fallzahl}, nur Hypothese"
            print(f"  {x.name:22} {x.aussage}  [{marke}]")

    print("\nLUECKEN")
    for l in report.luecken(a):
        print(f"  {l}")
    print()


def cmd_ab(args: argparse.Namespace) -> None:
    if args.ab_befehl == "anlegen":
        varianten = dict(v.split("=", 1) for v in args.variante)
        e = experiments.anlegen(args.id, args.variable, args.hypothese,
                                varianten, args.metrik)
        print(f"Experiment {e['experiment_id']} angelegt "
              f"({e['variable']}, Zielmetrik {e['metrik']})")
        for k, v in varianten.items():
            print(f"  Arm {k}: {v}")
        print("\n  Zuweisung passiert beim Registrieren:")
        print(f"  clip registriere --plattform tiktok --url ... "
              f"--experiment {e['experiment_id']}")
        return

    if args.ab_befehl == "liste":
        alle = store.experimente()
        if not alle:
            print("Keine Experimente angelegt")
            return
        for e in alle:
            print(f"{e['experiment_id']:24} {e['status']:12} "
                  f"{e['variable']:9} -> {e['metrik']}")
        return

    erg = experiments.werte_aus(args.id, args.fenster)
    print(f"\nExperiment {erg.experiment_id}   Zielmetrik {erg.metrik}")
    print("-" * 66)
    for arm in sorted(erg.arme, key=lambda a: a.rate or 0, reverse=True):
        rate = f"{arm.rate:.3%}" if arm.rate is not None else "keine Daten"
        p = erg.wahrscheinlichkeit.get(arm.name)
        print(f"  {arm.name:12} {len(arm.posts):>2} Posts  "
              f"{arm.views:>7.0f} Views  {rate:>11}"
              + (f"   P(bester) {p:.0%}" if p is not None else ""))
    if erg.sieger:
        print(f"\n  ENTSCHIEDEN: {erg.sieger}")
    else:
        print("\n  Noch nicht entschieden.")
    if erg.benoetigte_views_pro_arm:
        print(f"  Fuer eine belastbare Aussage: rund "
              f"{erg.benoetigte_views_pro_arm} Views pro Arm bei diesem Effekt.")
    for h in erg.hinweise:
        print(f"  ! {h}")
    print()


def cmd_kalibriere(args: argparse.Namespace) -> None:
    e = calibrate.kalibriere(schreiben=not args.probe)
    print(f"Grundlage: {e.grundlage} bewertbare Posts")
    if e.geschrieben:
        ziel = "nicht geschrieben (--probe)" if args.probe else str(calibrate.OVERLAY)
        print(f"Kalibriert: {', '.join(sorted(e.geschrieben))}  ->  {ziel}")
    else:
        print("Nichts kalibriert — die Startannahmen bleiben stehen.")
    for u in e.uebersprungen:
        print(f"  offen  {u}")


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

    f = sub.add_parser("frames", help="Standbilder zum Anschauen")
    f.add_argument("quelle", help="lokaler Pfad oder URL")
    f.add_argument("--raster", default="5x5", help="Kacheln des Kontaktbogens")
    f.add_argument("--alle", type=int, metavar="N",
                   help="jedes N-te Bild statt gleichmaessig ueber die Laufzeit")
    f.add_argument("--bei", type=float, action="append", metavar="SEK",
                   help="Einzelbild an dieser Sekunde, mehrfach moeglich")
    f.add_argument("--breite", type=int, default=0, help="0 = Originalbreite")
    f.add_argument("--ziel")
    f.set_defaults(func=cmd_frames)

    c = sub.add_parser("countdown", help="Top-5-Compilation rendern")
    c.add_argument("--plan", required=True)
    c.add_argument("--ausgabe")
    c.add_argument("--vorschau", action="store_true")
    c.set_defaults(func=cmd_countdown)

    # --- Bewertungssystem --------------------------------------------------
    s_ = sub.add_parser("sammle", help="Messwerte von den Plattformen holen")
    s_.add_argument("--plattform", action="append",
                    choices=list(publish.PLATTFORMEN))
    s_.add_argument("--grenze", type=int, default=60)
    s_.set_defaults(func=cmd_sammle)

    t = sub.add_parser("trage-nach", help="Creator-Center-Werte ergaenzen")
    t.add_argument("--post", required=True)
    t.add_argument("--views", type=int)
    t.add_argument("--likes", type=int)
    t.add_argument("--kommentare", type=int)
    t.add_argument("--shares", type=int)
    t.add_argument("--saves", type=int)
    t.add_argument("--follows", type=int)
    t.add_argument("--watchtime", type=float, help="Durchschnitt in Sekunden")
    t.add_argument("--completion", type=float, help="Anteil 0..1")
    t.add_argument("--profilaufrufe", type=int)
    t.add_argument("--alter", type=float, help="Alter in Stunden zum Messzeitpunkt")
    t.set_defaults(func=cmd_trage_nach)

    g = sub.add_parser("registriere", help="Veroeffentlichung eintragen")
    g.add_argument("--plattform", required=True, choices=list(publish.PLATTFORMEN))
    g.add_argument("--url", required=True)
    g.add_argument("--clip-id", dest="clip_id")
    g.add_argument("--titel")
    g.add_argument("--dauer", type=float)
    g.add_argument("--veroeffentlicht", help="ISO-Zeitstempel")
    g.add_argument("--experiment")
    g.add_argument("--variante")
    g.add_argument("--notiz")
    g.set_defaults(func=cmd_registriere)

    v = sub.add_parser("prognose", help="Bewertung vor dem Posten")
    v.add_argument("--headline", required=True)
    v.add_argument("--dauer", type=float, required=True)
    v.add_argument("--plattform", default="tiktok", choices=list(publish.PLATTFORMEN))
    v.add_argument("--hook", help="Transkript der ersten Sekunden")
    v.add_argument("--payoff", type=float, help="Position der Pointe, 0..1")
    v.add_argument("--postzeit", help="ISO-Zeitstempel der geplanten Veroeffentlichung")
    v.add_argument("--hashtag", action="append")
    v.set_defaults(func=cmd_prognose)

    b = sub.add_parser("bewerte", help="Rangliste, Muster, Luecken")
    b.add_argument("--fenster", type=float)
    b.add_argument("--plattform", choices=list(publish.PLATTFORMEN))
    b.set_defaults(func=cmd_bewerte)

    ab = sub.add_parser("ab", help="A/B-Tests")
    absub = ab.add_subparsers(dest="ab_befehl", required=True)
    aba = absub.add_parser("anlegen")
    aba.add_argument("--id", required=True)
    aba.add_argument("--variable", required=True)
    aba.add_argument("--hypothese", required=True)
    aba.add_argument("--variante", action="append", required=True,
                     metavar="NAME=BESCHREIBUNG")
    aba.add_argument("--metrik", default="like_rate")
    absub.add_parser("liste")
    abs_ = absub.add_parser("status")
    abs_.add_argument("--id", required=True)
    abs_.add_argument("--fenster", type=float)
    ab.set_defaults(func=cmd_ab)

    k = sub.add_parser("kalibriere", help="Annahmen durch eigene Zahlen ersetzen")
    k.add_argument("--probe", action="store_true", help="nur zeigen, nicht schreiben")
    k.set_defaults(func=cmd_kalibriere)

    args = p.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
