"""Handy-Fassungen eines Laufs: jeder Clip unter 30 MiB, nach <lauf>/handy/.

Aufruf: PYTHONPATH=src .venv/bin/python werkzeuge/handy.py <laufordner>

Clips ueber 30 MiB erreichen das Handy des Nutzers nicht, nur die Desktop-App
(gemessen bei jedem Lauf seit 2026-09-12; ein 60-s-Clip mit 8 Mbit/s hat rund
60 MiB). Die Originale in mp4/ bleiben unangetastet — das hier ist eine zweite
Datei zum Ansehen und Weiterleiten, kein zweiter Transkodierschritt im
Renderpfad (SCHNITTREGELN Regel 5). 720x1280, Bitrate je Clip aus der Dauer,
Encoder aus settings.toml wie beim Rendern.
"""
import json
import subprocess
import sys
from pathlib import Path

from videoclipper.settings import einstellungen

GRENZE_MIB = 28.0          # Luft unter den 30 MiB fuer Container und Ton
TON_KBPS = 128

lauf = Path(sys.argv[1]).expanduser()
ziel = lauf / 'handy'
ziel.mkdir(exist_ok=True)
encoder = einstellungen()['platform']['encoder']

for mp4 in sorted((lauf / 'mp4').glob('*.mp4')):
    dauer = float(json.loads(subprocess.run(
        ['ffprobe', '-v', 'error', '-show_entries', 'format=duration', '-of', 'json', str(mp4)],
        capture_output=True, text=True).stdout)['format']['duration'])
    video_kbps = int(min(3500, GRENZE_MIB * 8 * 1024 / dauer - TON_KBPS))
    aus = ziel / mp4.name
    subprocess.run(['ffmpeg', '-v', 'error', '-y', '-i', str(mp4), '-vf', 'scale=720:1280',
                    '-c:v', encoder, '-b:v', f'{video_kbps}k', '-maxrate', f'{video_kbps}k',
                    '-bufsize', f'{2 * video_kbps}k', '-c:a', 'aac', '-b:a', f'{TON_KBPS}k',
                    '-movflags', '+faststart', str(aus)], check=True)
    mib = aus.stat().st_size / 1048576
    print('%s  %.1fs  %d kbit/s  %.1f MiB%s' % (mp4.name, dauer, video_kbps, mib,
                                                 '' if mib < 30 else '  UEBER 30 MIB'))
