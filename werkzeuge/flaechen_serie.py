"""Mehrere Bildflaechen in einem Durchlauf: mittleres R, G, B und Kantenenergie je Flaeche.

Fuer Material mit mehr als zwei Bildern, wo eine einzelne Kante oder Farbe
nicht reicht (Fullcam, Browser, Splitscreen). Ein Decodierlauf fuer alle
Flaechen — bei einer Stunde 1080p60 ist der Decoder der teure Teil.

python flaechen_serie.py <video> <K> <ziel.npz> name=x,y,b,h [name=x,y,b,h ...]

Koordinaten in Quellpixeln (1920x1080); gemessen wird auf einem Viertel.
Im npz je Flaeche <name>_rgb (N x 3) und <name>_kante (N), dazu t.
"""
import subprocess
import sys

import numpy as np

video, K, ziel = sys.argv[1], int(sys.argv[2]), sys.argv[3]
flaechen = {}
for arg in sys.argv[4:]:
    name, box = arg.split('=')
    x, y, b, h = (int(v) for v in box.split(','))
    flaechen[name] = (x // 4, y // 4, max(b // 4, 1), max(h // 4, 1))

fps = eval(subprocess.run(['ffprobe', '-v', 'error', '-select_streams', 'v:0', '-show_entries',
                           'stream=r_frame_rate', '-of', 'csv=p=0', video],
                          capture_output=True, text=True).stdout.strip())
W, H = 480, 270
# Echte Bildnummern statt fps-Filter: der laeuft gegen die Zeitachse weg (CLAUDE.md).
p = subprocess.Popen(['ffmpeg', '-v', 'error', '-i', video,
                      '-vf', "select='not(mod(n\\,%d))',scale=%d:%d" % (K, W, H),
                      '-fps_mode', 'vfr', '-f', 'rawvideo', '-pix_fmt', 'rgb24', '-'],
                     stdout=subprocess.PIPE)
werte = {n: ([], []) for n in flaechen}
while True:
    raw = p.stdout.read(W * H * 3)
    if len(raw) < W * H * 3:
        break
    f = np.frombuffer(raw, np.uint8).reshape(H, W, 3).astype(np.float32)
    for n, (x, y, b, h) in flaechen.items():
        a = f[y:y + h, x:x + b]
        grau = a.mean(axis=2)
        kante = np.abs(np.diff(grau, axis=1)).mean() + np.abs(np.diff(grau, axis=0)).mean()
        werte[n][0].append(a.reshape(-1, 3).mean(axis=0))
        werte[n][1].append(kante)

t = np.arange(len(next(iter(werte.values()))[0])) * K / fps
daten = {'t': t}
for n, (rgb, kante) in werte.items():
    daten[n + '_rgb'] = np.array(rgb)
    daten[n + '_kante'] = np.array(kante)
    hell = np.array(rgb).mean(axis=1)
    print('%-12s hell p5/50/95 %s  kante %s' % (n, np.percentile(hell, [5, 50, 95]).round(1),
                                                np.percentile(kante, [5, 50, 95]).round(2)))
np.savez(ziel, **daten)
print('Bilder', len(t), '->', ziel)
