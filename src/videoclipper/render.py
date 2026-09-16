"""Stage 12 — Render.

Ein FFmpeg-Filtergraph pro Clip. Alle Zahlen kommen aus ``EditPlan.resolved``;
hier wird nichts mehr entschieden, nur uebersetzt.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

from . import follow, layout, untertitel
from .editplan import EditPlan
from .headline import baue as headline_bauen
from .settings import einstellungen


def _panel_kette(quelle: str, p: dict, blur: int) -> tuple[str, str]:
    """Filterkette fuer ein Panel. Gibt (Kette, Ausgangslabel) zurueck.

    Die Geometrie rechnet ``layout.sichtbar`` — hier wird sie nur uebersetzt.
    """
    sx, sy, sw, sh = p["src"]
    dx, dy, dw, dh = p["dst"]
    label = p["name"]
    (qx, qy, qw, qh), (cx, cy, fw, fh) = layout.sichtbar(p)

    zone = f"crop={sw}:{sh}:{sx}:{sy}"

    if p["passung"] == "fuellen":
        # Auf das Zielverhaeltnis beschneiden, dann skalieren — nie verzerren.
        kette = (f"[{quelle}]{zone},crop={qw}:{qh}:{qx - sx}:{qy - sy},"
                 f"scale={dw}:{dh},setsar=1[{label}]")
        return kette, label

    # "einpassen": Seitenverhaeltnis bleibt, die Reste tragen einen Blur der
    # eigenen Quelle. Nichts vom Inhalt geht verloren.
    # Passt die Quelle ohnehin, entfaellt die Blurschicht ganz.
    if (fw, fh) == (dw, dh):
        return f"[{quelle}]{zone},scale={dw}:{dh},setsar=1[{label}]", label

    kette = (
        f"[{quelle}]{zone},scale={dw}:{dh}:force_original_aspect_ratio=increase,"
        f"crop={dw}:{dh},boxblur={blur}:1,setsar=1[{label}_bg];"
        f"[{quelle}]{zone},scale={fw}:{fh},setsar=1[{label}_fg];"
        f"[{label}_bg][{label}_fg]overlay={cx - dx}:{cy - dy}[{label}]"
    )
    return kette, label


def ueberlagerungen(plan: EditPlan, tmpl: dict) -> list[dict]:
    """Die PNG-Eingaenge nach der Buehne, in genau dieser Reihenfolge.

    Je Eintrag ein ``overlay``: Position und optional das Zeitfenster. Die
    Animation steckt in den x/y-Ausdruecken und kostet deshalb weder ein
    zweites Bild noch einen zweiten Filter — siehe ``untertitel`` und
    ``follow``.

    Reihenfolge ist Absicht: Headline zuunterst, Untertitel darueber, die
    Follow-Pille zuoberst. Wenn sich zwei ueberschneiden, gewinnt die
    Aufforderung, weil sie nur wenige Sekunden steht.
    """
    r = plan.resolved
    cw, _ = r.canvas
    eintraege: list[dict] = [{"art": "headline", "x": "0", "y": "0"}]

    if r.untertitel:
        oben, _ = untertitel.band(tmpl)
        conf = tmpl["untertitel"]
        for c in r.untertitel:
            cue = untertitel.Cue(c["text"], c["ab"], c["bis"])
            eintraege.append({
                "art": "untertitel",
                "x": "0",
                "y": untertitel.y_ausdruck(cue, oben, conf),
                "enable": f"between(t,{cue.ab:.3f},{cue.bis:.3f})",
            })

    if r.follow:
        # Die Klickszene ist keine einzelne Einblendung mehr, sondern eine
        # Folge: Knopfzustaende (Pop, Druck, Umschlag, Wegpoppen) und darueber
        # der Mauszeiger. Ein Eintrag je Stueck, in der Reihenfolge, in der
        # ``follow.baue`` die Bilder liefert.
        h = follow.Hinweis(r.follow["text"], r.follow["ab"], r.follow["bis"])
        for s in follow.szene(h, tmpl):
            eintraege.append({
                "art": "follow",
                "x": s.x,
                "y": s.y,
                "enable": f"between(t,{s.ab:.3f},{s.bis:.3f})",
            })

    return eintraege


def _overlay(vorher: str, eingang: int, u: dict, raus: str) -> str:
    """Ein overlay-Glied. Ausdruecke in Anfuehrungszeichen: sie enthalten Kommas."""
    teil = f"[{vorher}][{eingang}:v]overlay=x='{u['x']}':y='{u['y']}'"
    if u.get("enable"):
        teil += f":enable='{u['enable']}'"
    return teil + f"[{raus}]"


def _einschub_ketten(einschuebe: list[dict], blur: int, vorher: str,
                     eingang: int, quelle: str = "0:v", versatz: float = 0.0,
                     suffix: str = "") -> tuple[list[str], str, int]:
    """Filterglieder fuer die Einschuebe (siehe ``layout.einschuebe``).

    Zwei Arten Panel, zwei Arten Quelle:

    * **Ersatz** kommt live aus dem Video (``0:v``), nur aus einer anderen
      Zone. Alle Einschuebe eines Clips nutzen dieselbe Zone — deshalb EINE
      Kette je Panel, eingeblendet ueber die Summe der Fenster. Eine Kette je
      Einschub hiesse eine eigene Skalierung mit Blur ueber alle Bilder des
      Clips, je Einschub.
    * **Halten** kommt aus einem Standbild, einem eigenen Eingang je
      Einschub. Es laeuft durch dieselbe ``_panel_kette`` wie das Live-Panel —
      Zuschnitt, Einpassen, Blur —, sonst saehe das gehaltene Bild anders aus
      als das Bild davor, und genau dieser Uebergang soll nicht auffallen.

    ``eingang`` ist der Index des ersten Haltebildes. Gibt die Glieder, das
    Label danach und den Index des naechsten freien Eingangs zurueck.

    Mit Teaser baut ``filtergraph_teile`` je Segment eine eigene Buehne; dann
    kommen hier nur die Einschuebe dieses Segments an, ``quelle`` ist sein
    Eingang und ``versatz`` sein Beginn auf der Clipachse — die Fenster stehen
    wie beim Punch-in auf der Clipachse, der Filter rechnet in Segmentzeit.
    """
    teile: list[str] = []
    if not einschuebe:
        return teile, vorher, eingang

    def zwischen(e: dict) -> str:
        return f"between(t,{e['ab'] - versatz:.3f},{e['bis'] - versatz:.3f})"

    panels: dict[tuple, dict] = {}
    fenster: dict[tuple, list[str]] = {}
    for e in einschuebe:
        for p in e["ersatz"]:
            k = (p["name"], tuple(p["src"]))
            panels[k] = p
            fenster.setdefault(k, []).append(zwischen(e))
    for i, (k, p) in enumerate(panels.items()):
        kette, label = _panel_kette(quelle, dict(p, name=f"ers{i}_{p['name']}{suffix}"),
                                    blur)
        teile.append(kette)
        teile.append(f"[{vorher}][{label}]overlay=x={p['dst'][0]}:y={p['dst'][1]}:"
                     f"enable='{'+'.join(fenster[k])}'[{label}_auf]")
        vorher = f"{label}_auf"

    for n, e in enumerate(einschuebe):
        if not e["halten"]:
            continue
        for p in e["halten"]:
            kette, label = _panel_kette(f"{eingang}:v",
                                        dict(p, name=f"halt{n}_{p['name']}{suffix}"),
                                        blur)
            teile.append(kette)
            teile.append(f"[{vorher}][{label}]overlay=x={p['dst'][0]}:y={p['dst'][1]}:"
                         f"enable='{zwischen(e)}'[{label}_auf]")
            vorher = f"{label}_auf"
        eingang += 1
    return teile, vorher, eingang


def _punch_ketten(eintraege: list[dict], vorher: str, quelle: str = "0:v",
                  versatz: float = 0.0,
                  praefix: str = "punch") -> tuple[list[str], str]:
    """Kurzformat: je Panel ein engerer Ausschnitt, nur im Fenster der Pointe.

    Ein Punch-in ist nichts anderes als dasselbe Panel aus einer kleineren
    Quellbox: ausgeschnitten, auf das Canvasrechteck des Panels skaliert und
    dort daruebergelegt (siehe ``kurzformat.punch_in``). Er liegt unter
    Headline, Untertiteln und Follow — gezoomt wird das Bild, nicht die Schrift.

    ``versatz`` ist der Beginn des Segments auf der Clipachse: Eine Buehne je
    Segment hat ihre eigene Zeit, die Eintraege stehen auf der des Clips.
    """
    teile: list[str] = []
    for i, e in enumerate(eintraege):
        qx, qy, qw, qh = e["quelle"]
        cx, cy, cw, ch = e["ziel"]
        teile.append(f"[{quelle}]crop={qw}:{qh}:{qx}:{qy},scale={cw}:{ch},"
                     f"setsar=1[{praefix}{i}]")
        teile.append(f"[{vorher}][{praefix}{i}]overlay=x={cx}:y={cy}:"
                     f"enable='between(t,{e['ab'] - versatz:.3f},"
                     f"{e['bis'] - versatz:.3f})'[{praefix}{i}_auf]")
        vorher = f"{praefix}{i}_auf"
    return teile, vorher


def _buehne(quelle: str, r, blur: int, suffix: str = "") -> tuple[list[str], str]:
    """Die Panels einer Quelle zur Buehne gestapelt. Gibt (Glieder, Label).

    ``suffix`` haelt die Labels auseinander, wenn mehrere Segmente je eine
    eigene Buehne bauen (``filtergraph_teile``).
    """
    teile, labels = [], []
    for p in r.panels:
        kette, label = _panel_kette(quelle, dict(p, name=p["name"] + suffix), blur)
        teile.append(kette)
        labels.append(label)
    ziel = f"buehne{suffix}"
    if len(labels) == 1:
        teile.append(f"[{labels[0]}]null[{ziel}]")
    else:
        teile.append("".join(f"[{l}]" for l in labels)
                     + f"vstack=inputs={len(labels)}[{ziel}]")
    return teile, ziel


def filtergraph(plan: EditPlan, tmpl: dict) -> str:
    r = plan.resolved
    blur = (tmpl.get("hintergrund") or {}).get("staerke", 24)
    teile, _ = _buehne("0:v", r, blur)

    # Eingang 0 ist das Video. Danach kommt je Einschub mit gehaltenen Panels
    # ein Haltebild, danach die PNGs in der Reihenfolge, in der ``rendere`` sie
    # anhaengt. Die Einschuebe liegen UNTER Headline, Untertiteln und Follow:
    # Sie ersetzen Teile der Buehne, nicht die Schrift darauf.
    haltebilder = sum(1 for e in r.einschuebe if e["halten"])
    glieder, vorher, _ = _einschub_ketten(r.einschuebe, blur, "buehne", 1)
    teile += glieder
    glieder, vorher = _punch_ketten(r.punch_in, vorher)
    teile += glieder
    for i, u in enumerate(ueberlagerungen(plan, tmpl)):
        raus = f"ov{i}"
        teile.append(_overlay(vorher, 1 + haltebilder + i, u, raus))
        vorher = raus
    teile.append(f"[{vorher}]format=yuv420p[v]")
    return ";".join(teile)


def filtergraph_teile(plan: EditPlan, tmpl: dict, lufs: float) -> str:
    """Mehrere Quellfenster hintereinander — Teaser, dann Hauptteil.

    Je Segment eine eigene Buehne aus seinem eigenen Eingang, mit seinem
    Punch-in, dann ``concat``. Erst auf der fertigen Folge liegen Headline,
    Untertitel und Follow, mit Zeiten auf der Clipachse. So bleibt jede Buehne
    dieselbe Kette wie im Einzelpfad — nur der Eingang ist ein anderer.

    Der Ton kommt je Segment aus seinem Eingang und laeuft durch ``concat``;
    ``loudnorm`` steht deshalb im Graphen, weil ``-af`` Streams aus
    ``filter_complex`` ablehnt (Exit 234, siehe CLAUDE.md).

    Eingaenge: erst ein Video je Segment, dann die Haltebilder der Einschuebe
    in Segmentreihenfolge, dann die PNGs. Die Einschuebe liegen je Segment auf
    seiner Buehne, unter dem Punch-in — dieselbe Schichtung wie im Einzelpfad.
    """
    r = plan.resolved
    blur = (tmpl.get("hintergrund") or {}).get("staerke", 24)
    n = len(r.segmente)
    haltebilder = sum(1 for e in r.einschuebe if e["halten"])

    teile, stufen = [], []
    eingang = n
    for k, seg in enumerate(r.segmente):
        glieder, label = _buehne(f"{k}:v", r, blur, suffix=f"_s{k}")
        teile += glieder
        glieder, label, eingang = _einschub_ketten(
            [e for e in r.einschuebe if e.get("segment", 0) == k], blur, label,
            eingang, quelle=f"{k}:v", versatz=seg["ab"], suffix=f"_s{k}")
        teile += glieder
        eigene = [e for e in r.punch_in if e.get("segment", 0) == k]
        glieder, label = _punch_ketten(eigene, label, quelle=f"{k}:v",
                                       versatz=seg["ab"], praefix=f"punch_s{k}_")
        teile += glieder
        stufen.append(label)
    teile.append("".join(f"[{s}]" for s in stufen)
                 + f"concat=n={n}:v=1:a=0[buehne]")
    teile.append("".join(f"[{k}:a]" for k in range(n))
                 + f"concat=n={n}:v=0:a=1,loudnorm=I={lufs}:TP=-1.5:LRA=11[a]")

    vorher = "buehne"
    for i, u in enumerate(ueberlagerungen(plan, tmpl)):
        raus = f"ov{i}"
        teile.append(_overlay(vorher, n + haltebilder + i, u, raus))
        vorher = raus
    teile.append(f"[{vorher}]format=yuv420p[v]")
    return ";".join(teile)


def _overlay_bilder(plan: EditPlan, tmpl: dict, bilder_dir: Path) -> list[Path]:
    """Alle PNGs in der Reihenfolge, die ``ueberlagerungen`` erwartet.

    ``bilder_dir`` ist der PNG-Ordner des Laufes, nicht der Ordner der MP4:
    Die Overlays sind Zwischenschritt, nicht Ergebnis, und liegen deshalb
    getrennt von dem, was hochgeladen wird (siehe ``ausgabe.py``).
    """
    r = plan.resolved
    bilder_dir.mkdir(parents=True, exist_ok=True)
    bilder = [headline_bauen(plan.headline, tmpl,
                             bilder_dir / f"{plan.clip_id}.headline.png")]

    if r.untertitel:
        cues = [untertitel.Cue(c["text"], c["ab"], c["bis"]) for c in r.untertitel]
        bilder += untertitel.baue(cues, tmpl, bilder_dir, plan.clip_id)
    if r.follow:
        h = follow.Hinweis(r.follow["text"], r.follow["ab"], r.follow["bis"])
        bilder += follow.baue(tmpl, bilder_dir, plan.clip_id, h)
    return bilder


def _haltebild(video: Path, start: float, t: float, ziel: Path) -> Path:
    """Das Standbild eines Einschubs als PNG, in voller Quellaufloesung.

    Gesucht wird nah am Bild (eine Sekunde davor) statt ab Clipbeginn — sonst
    dekodierte jeder Einschub den halben Clip. Die Zeitachse bleibt dabei
    dieselbe: Mit ``-ss`` vor ``-i`` ist ``t`` im Filter immer die Quellzeit
    minus Suchpunkt, das Bild bei ``start + t`` liegt also bei ``t - lokal``.
    ``select`` nimmt das erste Bild ab dort; die 4 ms Vorhalt fangen die
    Rundung ab, das Bild davor liegt 16.7 ms frueher.
    """
    lokal = max(t - 1.0, 0.0)
    subprocess.run(
        ["ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
         "-ss", f"{start + lokal:.4f}", "-i", str(video),
         "-vf", rf"select='gte(t\,{max(t - lokal - 0.004, 0.0):.4f})'",
         "-frames:v", "1", "-fps_mode", "passthrough", str(ziel)],
        check=True)
    return ziel


def _haltebilder(plan: EditPlan, video: Path, bilder_dir: Path) -> list[Path]:
    """Ein Standbild je Einschub mit gehaltenen Panels, Reihenfolge wie im Graphen.

    ``halten_bei`` steht in der Zeit des eigenen Segments — mit Teaser also ab
    dessen Quellbeginn, nicht ab dem des Hauptteils.
    """
    r = plan.resolved
    bilder_dir.mkdir(parents=True, exist_ok=True)

    def beginn(e: dict) -> float:
        return r.segmente[e.get("segment", 0)]["start"] if r.segmente else r.start

    return [_haltebild(video, beginn(e), e["halten_bei"],
                       bilder_dir / f"{plan.clip_id}.halt{k:02d}.png")
            for k, e in enumerate(r.einschuebe) if e["halten"]]


def rendere(plan: EditPlan, tmpl: dict, video: Path, ziel: Path,
            vorschau: bool = False, bilder_dir: Path | None = None) -> Path:
    r = plan.resolved
    ziel.parent.mkdir(parents=True, exist_ok=True)
    ordner = bilder_dir or ziel.parent
    halte = _haltebilder(plan, video, ordner)
    bilder = _overlay_bilder(plan, tmpl, ordner)

    e = einstellungen()
    encoder = e["platform"]["preview_encoder" if vorschau else "encoder"]
    lufs = (tmpl.get("audio") or {}).get("ziel_lufs", e["output"]["target_lufs"])

    cmd = ["ffmpeg", "-hide_banner", "-loglevel", "error", "-y"]
    if r.segmente:
        # Teaser und Hauptteil: ein Eingang je Quellfenster, der Ton im Graphen.
        for seg in r.segmente:
            cmd += ["-ss", f"{seg['start']:.3f}", "-t", f"{seg['dauer']:.3f}",
                    "-i", str(video)]
        graph = filtergraph_teile(plan, tmpl, lufs)
        karten = ["-map", "[v]", "-map", "[a]"]
    else:
        cmd += ["-ss", f"{r.start:.3f}", "-t", f"{r.dauer:.3f}", "-i", str(video)]
        graph = filtergraph(plan, tmpl)
        karten = ["-map", "[v]", "-map", "0:a",
                  "-af", f"loudnorm=I={lufs}:TP=-1.5:LRA=11"]
    # Reihenfolge der Eingaenge wie im Graphen: Haltebilder, dann PNGs.
    for bild in halte + bilder:
        cmd += ["-i", str(bild)]
    cmd += [
        "-filter_complex", graph,
        *karten,
        "-r", str(r.fps),
        "-c:v", encoder, "-b:v", "1500k" if vorschau else "8000k",
        "-c:a", "aac", "-b:a", "160k",
        "-movflags", "+faststart",
        str(ziel),
    ]
    subprocess.run(cmd, check=True)
    return ziel


# ---------------------------------------------------------------------------
# Compilation (TOP5_COUNTDOWN)
# ---------------------------------------------------------------------------

def _segment_kette(idx: int, seg: dict, panel: tuple[int, int, int, int],
                   canvas: tuple[int, int], blur: int, fps: int) -> str:
    """Ein Quellsegment auf die volle Buehne bringen: Blur hinten, Inhalt vorn."""
    cw, ch = canvas
    px, py, pw, ph = panel
    zone = f"crop={seg['quelle_box'][2]}:{seg['quelle_box'][3]}:" \
           f"{seg['quelle_box'][0]}:{seg['quelle_box'][1]}," if seg["quelle_box"] else ""

    return (
        # Hintergrund: eigene Quelle, formatfuellend, unscharf.
        f"[{idx}:v]{zone}scale={cw}:{ch}:force_original_aspect_ratio=increase,"
        f"crop={cw}:{ch},boxblur={blur}:1,setsar=1[bg{idx}];"
        # Inhalt: vollstaendig eingepasst, nie beschnitten, Kanten gerade.
        f"[{idx}:v]{zone}scale={pw}:{ph}:force_original_aspect_ratio=decrease:"
        f"force_divisible_by=2,setsar=1[fg{idx}];"
        f"[bg{idx}][fg{idx}]overlay={px}+({pw}-w)/2:{py}+({ph}-h)/2,"
        f"fps={fps},format=yuv420p,setsar=1[seg{idx}]"
    )


def filtergraph_countdown(plan, tmpl: dict, lufs: float) -> str:
    r = plan.aufgeloest
    blur = (tmpl.get("hintergrund") or {}).get("staerke", 24)
    n = len(r.segmente)

    teile = [_segment_kette(i, seg, r.panel, r.canvas, blur, r.fps)
             for i, seg in enumerate(r.segmente)]

    # Ton der Segmente auf ein gemeinsames Format bringen, sonst weigert sich concat.
    teile += [f"[{i}:a]aformat=sample_rates=48000:channel_layouts=stereo,"
              f"asetpts=PTS-STARTPTS[sa{i}]" for i in range(n)]

    teile.append("".join(f"[seg{i}][sa{i}]" for i in range(n))
                 + f"concat=n={n}:v=1:a=1[cv][ca_roh]")
    # loudnorm muss in den Graphen: ``-af`` weigert sich bei Streams, die aus
    # einem filter_complex kommen, und bricht mit Exit 234 ab.
    teile.append(f"[ca_roh]loudnorm=I={lufs}:TP=-1.5:LRA=11[ca]")

    # Headline liegt konstant oben; danach je Segment ein Listenzustand.
    kopf = n                      # Eingangsindex des Headline-PNG
    teile.append(f"[cv][{kopf}:v]overlay=0:0[o_kopf]")
    vorher = "o_kopf"
    for i, seg in enumerate(r.segmente):
        # Das letzte Segment laeuft bis zum Ende: obere Grenze offen lassen,
        # damit Rundung an der Nahtstelle keinen Frame ohne Liste erzeugt.
        bis = f",{seg['bis']:.3f}" if i < n - 1 else f",{r.dauer + 1:.3f}"
        raus = f"o{i}"
        teile.append(f"[{vorher}][{kopf + 1 + i}:v]"
                     f"overlay=0:0:enable='between(t,{seg['ab']:.3f}{bis})'[{raus}]")
        vorher = raus

    # Die Klickszene liegt ueber allem und kommt deshalb als letzte Eingaenge —
    # ein Eingang je Stueck, gleiche Reihenfolge wie ``follow.baue``.
    if r.follow:
        h = follow.Hinweis(r.follow["text"], r.follow["ab"], r.follow["bis"])
        for j, s in enumerate(follow.szene(h, tmpl)):
            raus = f"o_follow{j}"
            teile.append(
                f"[{vorher}][{kopf + 1 + n + j}:v]"
                f"overlay=x='{s.x}':y='{s.y}':"
                f"enable='between(t,{s.ab:.3f},{s.bis:.3f})'[{raus}]")
            vorher = raus

    teile.append(f"[{vorher}]format=yuv420p[v]")
    return ";".join(teile)


def rendere_countdown(plan, tmpl: dict, videos: dict[str, Path], ziel: Path,
                      vorschau: bool = False, bilder_dir: Path | None = None) -> Path:
    """Stage 12 fuer Compilations: ein Durchlauf, N Quellen, N Listenzustaende."""
    from .liste import baue_alle

    r = plan.aufgeloest
    ziel.parent.mkdir(parents=True, exist_ok=True)
    bilder_dir = bilder_dir or ziel.parent
    bilder_dir.mkdir(parents=True, exist_ok=True)

    kopf_png = headline_bauen(plan.titel, tmpl,
                              bilder_dir / f"{plan.clip_id}.headline.png")
    listen = baue_alle(plan, tmpl, bilder_dir)

    e = einstellungen()
    encoder = e["platform"]["preview_encoder" if vorschau else "encoder"]
    lufs = (tmpl.get("audio") or {}).get("ziel_lufs", e["output"]["target_lufs"])

    cmd = ["ffmpeg", "-hide_banner", "-loglevel", "error", "-y"]
    for seg in r.segmente:
        quelle = videos.get(seg["video_id"])
        if quelle is None:
            raise FileNotFoundError(f"Kein Video fuer {seg['video_id']}")
        cmd += ["-ss", f"{seg['start']:.3f}", "-t", f"{seg['dauer']:.3f}",
                "-i", str(quelle)]
    cmd += ["-i", str(kopf_png)]
    for p in listen:
        cmd += ["-i", str(p)]
    if r.follow:
        h = follow.Hinweis(r.follow["text"], r.follow["ab"], r.follow["bis"])
        for pfad in follow.baue(tmpl, bilder_dir, plan.clip_id, h):
            cmd += ["-i", str(pfad)]

    cmd += [
        "-filter_complex", filtergraph_countdown(plan, tmpl, lufs),
        "-map", "[v]", "-map", "[ca]",
        "-r", str(r.fps),
        "-c:v", encoder, "-b:v", "1500k" if vorschau else "8000k",
        "-c:a", "aac", "-b:a", "160k",
        "-movflags", "+faststart",
        str(ziel),
    ]
    subprocess.run(cmd, check=True)
    return ziel
