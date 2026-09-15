"""Grenzkontrolle: Pegel und Woerter an jeder Schnittgrenze der Clips eines Laufs.

Aufruf: PYTHONPATH=src .venv/bin/python grenzkontrolle.py <laufordner> <video> <json3>

Je Grenze die 50-ms-Pegel in dBFS; ``|`` markiert den Schnitt. Ein Schnitt
gehoert in ein Tal (unter -45 dB), nicht in ein Wort. Clips mit Teaser haben
vier Grenzen: Teaser Anfang/Ende, Hauptteil Anfang/Ende.
"""
import json
import sys
from pathlib import Path

from videoclipper.signals import lautheit
from videoclipper.transcript import lade_json3

lauf, video, transkript = (Path(a).expanduser() for a in sys.argv[1:4])
tr = lade_json3(transkript, "x")
zeiten, db = lautheit(video, fenster=0.05)


def zeile(t_schnitt: float, vor: float, nach: float) -> str:
    teile = []
    i0, i1 = int((t_schnitt - vor) / 0.05), int((t_schnitt + nach) / 0.05)
    for i in range(i0, i1):
        if zeiten[i] <= t_schnitt < zeiten[i] + 0.05:
            teile.append("|")
        teile.append(f"{db[i]:.0f}")
    return " ".join(teile)


def woerter(a: float, b: float) -> str:
    return " ".join(f"{w.start:.2f}:{w.text.strip()}" for w in tr.woerter if a <= w.start < b)


for pfad in sorted((lauf / "json").glob("*.editplan.json")):
    r = json.loads(pfad.read_text(encoding="utf-8"))["resolved"]
    segs = r.get("segmente") or [{"art": "haupt", "start": r["start"], "ende": r["ende"]}]
    print(f"\n=== {pfad.name.split('.')[0]}  gesamt {r['dauer']:.2f}s")
    for seg in segs:
        s, e = seg["start"], seg["ende"]
        print(f"  [{seg['art']}] {s:.2f}-{e:.2f} ({e - s:.2f}s)")
        print("    Anfang:", zeile(s, 0.5, 0.5))
        print("      Woerter:", woerter(s - 0.8, s + 0.8))
        print("    Ende:  ", zeile(e, 0.8, 0.6))
        print("      Woerter:", woerter(e - 1.2, e + 0.8))
