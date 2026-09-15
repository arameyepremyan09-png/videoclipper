"""Fullcam-Erkennung ueber Farbe: Coachs Zimmer ist lila (Blau > Gruen).

Je K-tem Bild: mittleres (B - G) links [80:420, 250:900] und in der Mitte
[700:1200, 300:700], dazu die Helligkeit links. python lila_serie.py <video> <K> <ziel.npz>
"""
import subprocess, sys
import numpy as np
video, K, ziel = sys.argv[1], int(sys.argv[2]), sys.argv[3]
fps = eval(subprocess.run(['ffprobe', '-v', 'error', '-select_streams', 'v:0', '-show_entries',
                           'stream=r_frame_rate', '-of', 'csv=p=0', video], capture_output=True, text=True).stdout.strip())
W, H = 480, 270                      # auf ein Viertel verkleinert, reicht fuer Flaechenmittel
p = subprocess.Popen(['ffmpeg', '-v', 'error', '-i', video, '-vf', "select='not(mod(n\\,%d))',scale=%d:%d" % (K, W, H),
                      '-fps_mode', 'vfr', '-f', 'rawvideo', '-pix_fmt', 'rgb24', '-'], stdout=subprocess.PIPE)
links, mitte, hell = [], [], []
while True:
    raw = p.stdout.read(W * H * 3)
    if len(raw) < W * H * 3:
        break
    f = np.frombuffer(raw, np.uint8).reshape(H, W, 3).astype(np.float32)
    l = f[62:225, 20:105]; m = f[75:175, 175:300]
    links.append((l[..., 2] - l[..., 1]).mean()); mitte.append((m[..., 2] - m[..., 1]).mean()); hell.append(l.mean())
t = np.arange(len(links)) * K / fps
np.savez(ziel, t=t, links=np.array(links), mitte=np.array(mitte), hell=np.array(hell))
print('Bilder', len(t), 'p5/p50/p95 links', np.percentile(links, [5, 50, 95]).round(1), 'mitte', np.percentile(mitte, [5, 50, 95]).round(1))
