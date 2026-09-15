"""Pruefbogen: je Clip eine Zeile Standbilder an den kritischen Stellen.

Aufruf: python pruefbogen.py <laufordner> <zielbild>
Spalten: Anfang, jeder Punch-in (0.3 s hinein), direkt nach dem Rueckschnitt
vom Teaser in den Hauptteil, mitten in der Follow-Szene, kurz vor dem Ende.
"""
import io
import json
import subprocess
import sys
from pathlib import Path

from PIL import Image

lauf, ziel = Path(sys.argv[1]), Path(sys.argv[2])
B, H = 240, 426
zeilen = []
for plan_pfad in sorted((lauf / "json").glob("*.editplan.json")):
    plan = json.loads(plan_pfad.read_text(encoding="utf-8"))
    r, cid = plan["resolved"], plan["clip_id"]
    zeiten = [0.3]
    for ab in sorted({e["ab"] for e in r["punch_in"]}):
        zeiten.append(ab + 0.3)
    if r.get("segmente"):
        zeiten.append(r["segmente"][1]["ab"] + 0.4)
    if r["follow"]:
        zeiten.append((r["follow"]["ab"] + r["follow"]["bis"]) / 2)
    zeiten.append(r["dauer"] - 0.4)
    zeiten = sorted(zeiten)
    bilder = []
    for t in zeiten:
        roh = subprocess.run(
            ["ffmpeg", "-hide_banner", "-loglevel", "error", "-ss", f"{t:.3f}",
             "-i", str(lauf / "mp4" / f"{cid}.mp4"), "-frames:v", "1",
             "-vf", f"scale={B}:{H}", "-f", "image2pipe", "-vcodec", "png", "-"],
            capture_output=True, check=True).stdout
        bilder.append(Image.open(io.BytesIO(roh)).convert("RGB"))
    zeilen.append((cid, zeiten, bilder))

bogen = Image.new("RGB", (B * max(len(z[2]) for z in zeilen), H * len(zeilen)), "white")
for i, (_, _, bilder) in enumerate(zeilen):
    for j, b in enumerate(bilder):
        bogen.paste(b, (j * B, i * H))
bogen.save(ziel)
for cid, zeiten, _ in zeilen:
    print(cid, [round(t, 2) for t in zeiten])
print("->", ziel)
