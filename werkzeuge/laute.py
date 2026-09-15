"""0.1-s-Pegel mit dem gerade laufenden Wort — Lachen ist laut und wortlos."""
import subprocess, sys
from pathlib import Path
import numpy as np
sys.path.insert(0, 'src')
from videoclipper.transcript import lade_json3
vid = sys.argv[1]
V = str(Path('~/videoclipper/quellen/%s.mp4' % vid).expanduser())
T = Path('~/videoclipper/quellen/%s.de-orig.json3' % vid).expanduser()
if not T.exists():                  # Twitch: kein YouTube-Transkript, nur die eigene ASR
    T = T.with_name('%s.de-asr.json3' % vid)
tr = lade_json3(T, vid)
for spec in sys.argv[2:]:
    name, a, b = spec.split(':'); a, b = float(a), float(b)
    raw = subprocess.run(['ffmpeg', '-v', 'error', '-ss', str(a), '-t', str(b - a), '-i', V, '-vn', '-ac', '1',
                          '-ar', '16000', '-f', 'f32le', '-'], capture_output=True).stdout
    x = np.frombuffer(raw, np.float32); n = 1600
    print('==', name)
    for i in range(0, len(x) // n, 10):
        cells = []
        for j in range(i, min(i + 10, len(x) // n)):
            t = a + j * 0.1
            db = 20 * np.log10(np.sqrt(np.mean(x[j*n:(j+1)*n] ** 2)) + 1e-9)
            w = next((w.text for w in tr.woerter if w.start <= t + 0.05 < w.ende), '')
            cells.append('%4.0f %-6s' % (db, w[:6]))
        print('  %.1f ' % (a + i * 0.1) + '|'.join(cells))
