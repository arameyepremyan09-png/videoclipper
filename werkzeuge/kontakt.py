"""Kontaktbogen: Bilder zu festen Zeiten, 6 Spalten, Zeit in jede Kachel.

python kontakt.py <video> <ziel.png> <t1> <t2> ...   oder   --alle <von> <bis> <n>
"""
import subprocess
import sys

import numpy as np
from PIL import Image, ImageDraw

video, ziel = sys.argv[1], sys.argv[2]
if sys.argv[3] == '--alle':
    von, bis, n = float(sys.argv[4]), float(sys.argv[5]), int(sys.argv[6])
    zeiten = list(np.linspace(von, bis, n))
else:
    zeiten = [float(x) for x in sys.argv[3:]]

B, H, SP = 384, 216, 6
kacheln = []
for t in zeiten:
    raw = subprocess.run(['ffmpeg', '-v', 'error', '-ss', '%.3f' % t, '-i', video, '-frames:v', '1',
                          '-vf', 'scale=%d:%d' % (B, H), '-f', 'rawvideo', '-pix_fmt', 'rgb24', '-'],
                         capture_output=True).stdout
    img = Image.frombytes('RGB', (B, H), raw) if len(raw) == B * H * 3 else Image.new('RGB', (B, H))
    d = ImageDraw.Draw(img)
    d.rectangle([0, 0, 70, 16], fill=(0, 0, 0))
    d.text((3, 2), '%.1f' % t, fill=(255, 255, 0))
    kacheln.append(img)

zeilen = (len(kacheln) + SP - 1) // SP
bogen = Image.new('RGB', (SP * B, zeilen * H))
for i, k in enumerate(kacheln):
    bogen.paste(k, ((i % SP) * B, (i // SP) * H))
bogen.save(ziel)
print(ziel, len(kacheln))
