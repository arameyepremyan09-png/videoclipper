"""Stage 12 — Render.

Ein FFmpeg-Filtergraph pro Clip. Alle Zahlen kommen aus ``EditPlan.resolved``;
hier wird nichts mehr entschieden, nur uebersetzt.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

from .editplan import EditPlan
from .headline import baue as headline_bauen
from .settings import einstellungen


def _gerade(n: float) -> int:
    i = int(round(n))
    return i - (i % 2)


def _panel_kette(quelle: str, p: dict, blur: int) -> tuple[str, str]:
    """Filterkette fuer ein Panel. Gibt (Kette, Ausgangslabel) zurueck."""
    sx, sy, sw, sh = p["src"]
    _, _, dw, dh = p["dst"]
    label = p["name"]

    zone = f"crop={sw}:{sh}:{sx}:{sy}"

    if p["passung"] == "fuellen":
        # Auf das Zielverhaeltnis beschneiden, dann skalieren — nie verzerren.
        ziel_ar, quell_ar = dw / dh, sw / sh
        if quell_ar > ziel_ar:                      # zu breit: seitlich schneiden
            nw, nh = _gerade(sh * ziel_ar), _gerade(sh)
            fokus = p.get("fokus_x")
            mitte = (fokus - sx) if fokus is not None else sw / 2
            ox = int(min(max(mitte - nw / 2, 0), sw - nw))
            oy = 0
        else:                                        # zu hoch: oben/unten schneiden
            nw, nh = _gerade(sw), _gerade(sw / ziel_ar)
            ox, oy = 0, int((sh - nh) / 2)
        kette = (f"[{quelle}]{zone},crop={nw}:{nh}:{ox}:{oy},"
                 f"scale={dw}:{dh},setsar=1[{label}]")
        return kette, label

    # "einpassen": Seitenverhaeltnis bleibt, die Reste tragen einen Blur der
    # eigenen Quelle. Nichts vom Inhalt geht verloren.
    skala = min(dw / sw, dh / sh)
    fw, fh = _gerade(sw * skala), _gerade(sh * skala)

    # Passt die Quelle ohnehin, entfaellt die Blurschicht ganz.
    if (fw, fh) == (dw, dh):
        return f"[{quelle}]{zone},scale={dw}:{dh},setsar=1[{label}]", label

    kette = (
        f"[{quelle}]{zone},scale={dw}:{dh}:force_original_aspect_ratio=increase,"
        f"crop={dw}:{dh},boxblur={blur}:1,setsar=1[{label}_bg];"
        f"[{quelle}]{zone},scale={fw}:{fh},setsar=1[{label}_fg];"
        f"[{label}_bg][{label}_fg]overlay=(W-w)/2:(H-h)/2[{label}]"
    )
    return kette, label


def filtergraph(plan: EditPlan, tmpl: dict) -> str:
    r = plan.resolved
    blur = (tmpl.get("hintergrund") or {}).get("staerke", 24)
    cw, ch = r.canvas

    teile, labels = [], []
    for p in r.panels:
        kette, label = _panel_kette("0:v", p, blur)
        teile.append(kette)
        labels.append(label)

    if len(labels) == 1:
        teile.append(f"[{labels[0]}]null[buehne]")
    else:
        teile.append("".join(f"[{l}]" for l in labels)
                     + f"vstack=inputs={len(labels)}[buehne]")

    # Headline liegt als PNG auf dem zweiten Eingang.
    teile.append(f"[buehne][1:v]overlay=0:0,format=yuv420p[v]")
    return ";".join(teile)


def rendere(plan: EditPlan, tmpl: dict, video: Path, ziel: Path,
            vorschau: bool = False) -> Path:
    r = plan.resolved
    ziel.parent.mkdir(parents=True, exist_ok=True)
    hl = headline_bauen(plan.headline, tmpl, ziel.with_suffix(".headline.png"))

    e = einstellungen()
    encoder = e["platform"]["preview_encoder" if vorschau else "encoder"]
    lufs = (tmpl.get("audio") or {}).get("ziel_lufs", e["output"]["target_lufs"])

    cmd = [
        "ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
        "-ss", f"{r.start:.3f}", "-t", f"{r.dauer:.3f}", "-i", str(video),
        "-i", str(hl),
        "-filter_complex", filtergraph(plan, tmpl),
        "-map", "[v]", "-map", "0:a",
        "-af", f"loudnorm=I={lufs}:TP=-1.5:LRA=11",
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
    teile.append(f"[{vorher}]format=yuv420p[v]")
    return ";".join(teile)


def rendere_countdown(plan, tmpl: dict, videos: dict[str, Path], ziel: Path,
                      vorschau: bool = False) -> Path:
    """Stage 12 fuer Compilations: ein Durchlauf, N Quellen, N Listenzustaende."""
    from .liste import baue_alle

    r = plan.aufgeloest
    ziel.parent.mkdir(parents=True, exist_ok=True)

    kopf_png = headline_bauen(plan.titel, tmpl, ziel.with_suffix(".headline.png"))
    listen = baue_alle(plan, tmpl, ziel.parent)

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
