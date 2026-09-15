"""Beide TikTok-Signaturen alle K Bilder ueber das ganze Video.

A: Kantenstaerke an x=1076, y 250..900 (COACHLIM_TIKTOK_REACT, REACT > 20)
B: Helligkeit der Flaeche [80,250,340,650] (COACHLIM_ABU_TIKTOK, REACT < 18)

python modus_serie.py <video> <K> <ziel.npz>
"""
import subprocess
import sys

import numpy as np

video, K, ziel = sys.argv[1], int(sys.argv[2]), sys.argv[3]
fps = eval(subprocess.run(['ffprobe', '-v', 'error', '-select_streams', 'v:0', '-show_entries',
                           'stream=r_frame_rate', '-of', 'csv=p=0', video],
                          capture_output=True, text=True).stdout.strip())
W, H = 1920, 1080
proc = subprocess.Popen(['ffmpeg', '-v', 'error', '-i', video, '-vf',
                         "select='not(mod(n\\,%d))',format=gray" % K, '-fps_mode', 'vfr',
                         '-f', 'rawvideo', '-pix_fmt', 'gray', '-'], stdout=subprocess.PIPE)
a, b = [], []
while True:
    raw = proc.stdout.read(W * H)
    if len(raw) < W * H:
        break
    g = np.frombuffer(raw, np.uint8).reshape(H, W).astype(np.float32)
    a.append(np.abs(g[250:900, 1076] - g[250:900, 1075]).mean())
    b.append(g[250:900, 80:420].mean())
t = np.arange(len(a)) * K / fps
np.savez(ziel, t=t, a=np.array(a), b=np.array(b))
a, b = np.array(a), np.array(b)
print('Bilder %d, Schritt %.3f s' % (len(t), K / fps))
for name, v in (('A Kante x=1076', a), ('B Flaeche links', b)):
    print('%s: p5 %.1f  p25 %.1f  median %.1f  p75 %.1f  p95 %.1f' % ((name,) + tuple(np.percentile(v, [5, 25, 50, 75, 95]))))
