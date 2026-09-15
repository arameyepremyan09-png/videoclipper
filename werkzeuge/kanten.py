"""Persistente Kanten: Gibt es Boxen, die ueber das ganze Video stehen?

Je Bild die mittlere |dx| jeder Spalte und |dy| jeder Zeile (Graustufen,
Vollbild 1920x1080), dann der Median ueber alle Bilder. Eine Box-Kante steht
in fast jedem Bild und hat deshalb einen hohen Median; Bildinhalt wandert und
mittelt sich weg. Vergleichswerte in CLAUDE.md (Splitscreen 177, Couch 13.3,
BMW-Vlog 4.9 / 11.1, Tuersteher 1.8 / 2.3).

python kanten.py <video> <von> <bis> <n>
"""
import subprocess
import sys

import numpy as np

video = sys.argv[1]
von, bis, n = float(sys.argv[2]), float(sys.argv[3]), int(sys.argv[4])
W, H = 1920, 1080
spalten, zeilen, hell_oben, hell_unten = [], [], [], []
for t in np.linspace(von, bis, n):
    raw = subprocess.run(['ffmpeg', '-v', 'error', '-ss', '%.3f' % t, '-i', video, '-frames:v', '1',
                          '-vf', 'format=gray', '-f', 'rawvideo', '-pix_fmt', 'gray', '-'],
                         capture_output=True).stdout
    if len(raw) != W * H:
        continue
    g = np.frombuffer(raw, np.uint8).reshape(H, W).astype(np.float32)
    spalten.append(np.abs(np.diff(g, axis=1)).mean(axis=0))
    zeilen.append(np.abs(np.diff(g, axis=0)).mean(axis=1))
    hell_oben.append(g[:100].mean())
    hell_unten.append(g[-100:].mean())

S = np.median(np.array(spalten), axis=0)
Z = np.median(np.array(zeilen), axis=0)
print('Bilder:', len(spalten))
for name, v in (('Spalte', S), ('Zeile', Z)):
    innen = v[3:-3]
    top = np.argsort(innen)[::-1][:6] + 3
    print('staerkste persistente %s: ' % name + '  '.join('%d:%.1f' % (i, v[i]) for i in top),
          '| Median %.1f' % np.median(innen))
print('Bildband oben  min %.1f / median %.1f' % (min(hell_oben), np.median(hell_oben)))
print('Bildband unten min %.1f / median %.1f' % (min(hell_unten), np.median(hell_unten)))
