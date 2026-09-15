"""Clipfenster neu transkribieren, gegen das ASR-Transkript legen, einsetzen.

python asr_fenster.py <video> <json3> von:bis [von:bis ...] [--schreiben] [--neu]

Whisper laesst stellenweise Rede aus und dekodiert nicht deterministisch
(asr.transkribiere_fenster). Je Fenster wird einmal neu transkribiert und die
Fassung unter <json3-stamm>.fenster/<von>-<bis>.json abgelegt; ein zweiter
Aufruf benutzt sie wieder (mit --neu nicht). So setzt --schreiben genau die
Fassung ein, die vorher im Vergleich stand. Die Originaldatei wird beim ersten
Schreiben einmalig als <json3>.vorher gesichert.
"""
import json
import shutil
import sys
from pathlib import Path

sys.path.insert(0, 'src')
from videoclipper import asr

MODELL = Path('~/videoclipper/models/ggml-large-v3-turbo-q5_0.bin').expanduser()

args = [a for a in sys.argv[1:] if not a.startswith('--')]
schreiben, neu_rechnen = '--schreiben' in sys.argv, '--neu' in sys.argv
video, pfad = Path(args[0]).expanduser(), Path(args[1]).expanduser()
ablage = pfad.with_name(pfad.name.split('.')[0] + '.fenster')
ablage.mkdir(exist_ok=True)
daten = json.loads(pfad.read_text(encoding='utf-8'))
events = daten['events']


def zeile(evs):
    return ' '.join('%s@%.2f' % (''.join(s.get('utf8', '') for s in e['segs']).strip(),
                                 e['tStartMs'] / 1000) for e in evs)


for spec in args[2:]:
    von, bis = (float(v) for v in spec.split(':'))
    drin = lambda e: von * 1000 <= e['tStartMs'] < bis * 1000
    fassung = ablage / ('%.2f-%.2f.json' % (von, bis))
    if neu_rechnen or not fassung.exists():
        worte = asr.transkribiere_fenster(video, MODELL, von, bis)
        fassung.write_text(json.dumps(asr._nach_json3(worte)['events'], ensure_ascii=False),
                           encoding='utf-8')
    neu = [e for e in json.loads(fassung.read_text(encoding='utf-8')) if drin(e)]
    alt = [e for e in events if drin(e)]
    print('== %s   alt %d / neu %d Woerter' % (spec, len(alt), len(neu)))
    print('  alt: ' + zeile(alt))
    print('  neu: ' + zeile(neu))
    if schreiben:
        events = [e for e in events if not drin(e)] + neu

if schreiben:
    events.sort(key=lambda e: e['tStartMs'])
    sicher = pfad.with_name(pfad.name + '.vorher')
    if not sicher.exists():
        shutil.copy(pfad, sicher)
    daten['events'] = events
    pfad.write_text(json.dumps(daten, ensure_ascii=False), encoding='utf-8')
    print('geschrieben:', pfad)
