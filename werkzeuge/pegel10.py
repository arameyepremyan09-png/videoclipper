"""10-ms-Pegel in Zeilen zu 0.1 s, mit Woertern: python pegel10.py <id> name:von:bis ..."""
import subprocess, sys
from pathlib import Path
import numpy as np
sys.path.insert(0, 'src')
from videoclipper.transcript import lade_json3
vid = sys.argv[1]
V = str(Path('~/videoclipper/quellen/%s.mp4' % vid).expanduser())
tr = lade_json3(Path('~/videoclipper/quellen/%s.de-orig.json3' % vid).expanduser(), vid)
for spec in sys.argv[2:]:
    name, a, b = spec.split(':'); a, b = float(a), float(b)
    raw = subprocess.run(['ffmpeg', '-v', 'error', '-ss', str(a), '-t', str(b - a), '-i', V, '-vn', '-ac', '1',
                          '-ar', '16000', '-f', 'f32le', '-'], capture_output=True).stdout
    x = np.frombuffer(raw, np.float32); n = 160
    db = [20 * np.log10(np.sqrt(np.mean(x[i*n:(i+1)*n] ** 2)) + 1e-9) for i in range(len(x) // n)]
    print('==', name, '  ' + '  '.join('%s@%.2f' % (w.text, w.start) for w in tr.woerter if a - 0.3 <= w.start <= b))
    for i in range(0, len(db), 10):
        print('  %.2f  ' % (a + i * 0.01) + ' '.join('%4.0f' % d for d in db[i:i+10]))
