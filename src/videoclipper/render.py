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
