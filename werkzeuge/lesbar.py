"""Transkript zum Lesen: eine Zeile je Satz oder Sprechpause, mit Zeit und Bildtyp.

Stage 06 waehlt durch Lesen, nicht nach Score (SCHNITTREGELN, Ablauf Punkt 4).
Dafuer braucht es das Transkript als Text mit Zeitachse — und bei wechselnden
Layouts den Modus je Zeile, sonst faellt ein Layoutwechsel mitten im Kandidaten
erst beim Rendern auf.

python lesbar.py <json3> [--modi modi.npz] [--von s] [--bis s]

modi.npz: Arrays ``t`` (Sekunden) und ``modus`` (ein Buchstabe je Abtastpunkt),
etwa aus einer Klassifikation ueber flaechen_serie.py. Je Zeile steht der
Buchstabe, der in ihrem Fenster ueberwiegt; ``*`` heisst, das Fenster wechselt.
"""
import argparse
from pathlib import Path

import numpy as np

from videoclipper.transcript import lade_json3

PAUSE = 0.8          # Sekunden Luecke, ab der eine neue Zeile beginnt
MAX_ZEILE = 14.0     # spaetestens nach so vielen Sekunden umbrechen

ap = argparse.ArgumentParser()
ap.add_argument('json3')
ap.add_argument('--modi')
ap.add_argument('--von', type=float, default=0.0)
ap.add_argument('--bis', type=float, default=1e9)
a = ap.parse_args()

tr = lade_json3(Path(a.json3).expanduser(), Path(a.json3).stem.split('.')[0], 'de')
modi = np.load(a.modi, allow_pickle=True) if a.modi else None


def modus(von, bis):
    if modi is None:
        return ''
    m = modi['modus'][(modi['t'] >= von) & (modi['t'] < bis)]
    if len(m) == 0:
        return ' ? '
    werte, n = np.unique(m, return_counts=True)
    return ' %s%s ' % (werte[n.argmax()], '*' if len(werte) > 1 else ' ')


zeile, ab = [], None
for i, w in enumerate(tr.woerter):
    if w.start < a.von or w.start > a.bis:
        continue
    if zeile and (w.start - zeile[-1].ende > PAUSE or w.start - ab > MAX_ZEILE):
        print('%7.2f-%7.2f%s%s' % (ab, zeile[-1].ende, modus(ab, zeile[-1].ende),
                                   ''.join(x.text for x in zeile).strip()))
        zeile = []
    if not zeile:
        ab = w.start
    zeile.append(w)
    if w.text.rstrip().endswith(('.', '?', '!')) and w.ende - ab > 4.0:
        print('%7.2f-%7.2f%s%s' % (ab, w.ende, modus(ab, w.ende),
                                   ''.join(x.text for x in zeile).strip()))
        zeile = []
if zeile:
    print('%7.2f-%7.2f%s%s' % (ab, zeile[-1].ende, modus(ab, zeile[-1].ende),
                               ''.join(x.text for x in zeile).strip()))
