"""Tests fuer die eigene ASR.

Der Aufruf von whisper.cpp braucht ein Modell und laeuft deshalb nicht im
Test. Was hier falsch sein kann, ist die Umwandlung ins json3-Format — und
genau die entscheidet, ob der Rest der Pipeline das Transkript ueberhaupt
lesen kann. Geprueft wird deshalb gegen den echten Parser aus Stage 03, nicht
gegen eine erwartete Datenstruktur.
"""

from __future__ import annotations

import json

import numpy as np

from videoclipper import asr
from videoclipper.transcript import lade_json3


def _durch_den_parser(worte, tmp_path):
    """ASR-Woerter -> json3 -> Transkript, wie es die Pipeline tut."""
    pfad = tmp_path / "t.json3"
    pfad.write_text(json.dumps(asr._nach_json3(worte), ensure_ascii=False),
                    encoding="utf-8")
    return lade_json3(pfad, "vid", "de")


def test_woerter_kommen_durch_den_parser_zurueck(tmp_path):
    tr = _durch_den_parser([
        {"text": " Hallo", "ab": 1000, "bis": 1400},
        {"text": " Welt", "ab": 1400, "bis": 1900},
    ], tmp_path)
    assert [w.text.strip() for w in tr.woerter] == ["Hallo", "Welt"]
    assert tr.woerter[0].start == 1.0
    assert tr.woerter[1].start == 1.4


def test_millisekunden_werden_zu_sekunden(tmp_path):
    tr = _durch_den_parser([{"text": "a", "ab": 90_000, "bis": 90_500}], tmp_path)
    assert tr.woerter[0].start == 90.0


def test_wortende_wird_auf_das_naechste_wort_gekuerzt(tmp_path):
    """Dieselbe Zusage wie bei YouTube-json3: ein Wort darf nicht in das
    naechste hineinragen, sonst schneidet `snappe` an der falschen Stelle."""
    tr = _durch_den_parser([
        {"text": "a", "ab": 0, "bis": 5000},      # absichtlich zu lang
        {"text": "b", "ab": 1000, "bis": 1500},
    ], tmp_path)
    assert tr.woerter[0].ende <= tr.woerter[1].start


def test_echte_sprechpause_bleibt_stehen(tmp_path):
    """Nur kuerzen, nie verlaengern — sonst verschwaende eine Pause."""
    tr = _durch_den_parser([
        {"text": "a", "ab": 0, "bis": 500},
        {"text": "b", "ab": 4000, "bis": 4500},
    ], tmp_path)
    assert tr.woerter[0].ende == 0.5


def test_leere_segmente_fallen_raus(tmp_path):
    tr = _durch_den_parser([
        {"text": " ", "ab": 0, "bis": 100},
        {"text": "da", "ab": 100, "bis": 600},
    ], tmp_path)
    assert [w.text.strip() for w in tr.woerter] == ["da"]


def test_mindestdauer_verhindert_nullaenge(tmp_path):
    """whisper.cpp liefert gelegentlich from == to. Ein Wort ohne Dauer
    wuerde in `untertitel.schneide` zu einem Cue mit Laenge 0."""
    tr = _durch_den_parser([{"text": "x", "ab": 2000, "bis": 2000}], tmp_path)
    assert tr.woerter[0].ende > tr.woerter[0].start


def test_dauer_ist_das_letzte_wortende(tmp_path):
    tr = _durch_den_parser([
        {"text": "a", "ab": 0, "bis": 500},
        {"text": "b", "ab": 1000, "bis": 2500},
    ], tmp_path)
    assert tr.dauer == 2.5


def test_asr_transkript_hat_keine_marker(tmp_path):
    """Whisper schreibt keine [gelächter]-Marker. Der Test haelt die Aussage
    fest, auf der `lachmarker: 0.0` in ASR-Profilen beruht."""
    tr = _durch_den_parser([
        {"text": "Das", "ab": 0, "bis": 300},
        {"text": "war", "ab": 300, "bis": 600},
        {"text": "lustig", "ab": 600, "bis": 1200},
    ], tmp_path)
    assert tr.marker() == []


# --- Stuecke: Grenzen in Sprechpausen ---------------------------------------

def _rauschen(sekunden: float) -> np.ndarray:
    rng = np.random.default_rng(0)
    return (rng.standard_normal(int(sekunden * 16000)) * 0.1).astype(np.float32)


def test_stuecke_schneiden_in_der_pause():
    """GEMESSEN am 2026-09-15: Blind geschnittene Stuecke legten die letzten
    Woerter alle auf das Stueckende. Die Grenze gehoert in die Pause."""
    x = _rauschen(60)
    for t in (20.0, 41.0):
        x[int(t * 16000):int((t + 0.4) * 16000)] = 0
    schnitte = [a / 16000 for a, _ in asr.stuecke(x)[1:]]
    assert len(schnitte) == 2
    assert 20.0 <= schnitte[0] <= 20.4
    assert 41.0 <= schnitte[1] <= 41.4


def test_kein_stueck_ist_laenger_als_ein_fenster():
    """Ueber 30 s schreibt Whisper das Fenster fort — genau dort driftete die
    Zeitachse der Stundendatei um bis zu 13 s."""
    grenzen = asr.stuecke(_rauschen(300))
    assert all((b - a) / 16000 <= asr.STUECK_MAX for a, b in grenzen)
    assert grenzen[0][0] == 0 and grenzen[-1][1] == 300 * 16000


def test_stille_stuecke_gehen_nicht_an_whisper():
    """Twitchs DMCA-Stummschaltung ist digitales Null; Whisper erfindet dort
    "Vielen Dank."."""
    x = _rauschen(90)
    x[int(25 * 16000):int(70 * 16000)] = 0
    grenzen = asr.stuecke(x)
    assert all(np.abs(x[a:b]).max() > 0 for a, b in grenzen)
    assert sum(b - a for a, b in grenzen) < len(x) - 20 * 16000


def test_woerter_aus_dtw_tokens():
    """Whispers Segmentzeiten lagen gemessen bis zu 12 s daneben; die Woerter
    kommen deshalb aus den DTW-Zeiten der Tokens."""
    roh = {"transcription": [{"tokens": [
        {"text": "[_BEG_]", "t_dtw": 0},
        {"text": " Ich", "t_dtw": 100},
        {"text": " k", "t_dtw": 150},
        {"text": "acken", "t_dtw": 170},
        {"text": ".", "t_dtw": 290},      # der Punkt liegt in der Pause dahinter
        {"text": "[_TT_150]", "t_dtw": 300},
    ]}, {"tokens": [
        {"text": "Ja", "t_dtw": 400},     # Segmentanfang ohne Leerzeichen
    ]}]}
    worte, ohne = asr.woerter_aus_tokens(roh, 60_000)
    assert [w["text"].strip() for w in worte] == ["Ich", "kacken.", "Ja"]
    assert worte[1]["ab"] == 61_500
    assert worte[1]["bis"] == 61_700 + asr.NACHLAUF_MS   # nicht bis zum Punkt
    assert ohne == 0


def test_geraeuschangaben_werden_marker():
    """Whisper schreibt "*Klatschen*" und "* Musik *" in den Text. Als Wort
    stuende das im Untertitel; als Marker ueberspringt es ``untertitel``."""
    roh = {"transcription": [{"tokens": [
        {"text": " *", "t_dtw": 100}, {"text": "Kl", "t_dtw": 110},
        {"text": "atschen", "t_dtw": 120}, {"text": "*", "t_dtw": 130},
    ]}, {"tokens": [
        {"text": " *", "t_dtw": 200}, {"text": " Musik", "t_dtw": 210},
        {"text": " *", "t_dtw": 220},
    ]}, {"tokens": [
        {"text": " Ja", "t_dtw": 300},
    ]}]}
    worte, _ = asr.woerter_aus_tokens(roh, 0)
    assert [w["text"].strip() for w in worte] == ["[klatschen]", "[musik]", "Ja"]


def test_token_ohne_dtw_zeit_faellt_auf_den_offset_zurueck():
    roh = {"transcription": [{"tokens": [
        {"text": " da", "t_dtw": -1, "offsets": {"from": 2000, "to": 2300}},
    ]}]}
    worte, ohne = asr.woerter_aus_tokens(roh, 0)
    assert worte[0]["ab"] == 2000 and ohne == 1


# --- Sprecherwechsel-Marker aus YouTube-Captions ---------------------------

def test_sprecherwechsel_wird_aus_dem_wortlaut_entfernt(tmp_path):
    """GEMESSEN am 2026-09-08: In der englischen `en-orig` von JtWRKErMIGc
    tragen 470 von 3528 Woertern ein fuehrendes ">>". Es ist eine Formatmarke
    des Transkripts, kein gesprochenes Wort — im Untertitel stand es sonst
    mitten im Bild."""
    import json as _json
    pfad = tmp_path / "t.json3"
    pfad.write_text(_json.dumps({"events": [
        {"tStartMs": 0, "dDurationMs": 400, "segs": [{"utf8": ">> Hello.", "tOffsetMs": 0}]},
        {"tStartMs": 400, "dDurationMs": 400, "segs": [{"utf8": " What's", "tOffsetMs": 0}]},
    ]}), encoding="utf-8")
    tr = lade_json3(pfad, "v", "en")
    assert [w.text.strip() for w in tr.woerter] == ["Hello.", "What's"]


def test_pfeile_mitten_im_wort_bleiben_stehen(tmp_path):
    """Entfernt wird nur der fuehrende Marker, nie Inhalt."""
    import json as _json
    pfad = tmp_path / "t.json3"
    pfad.write_text(_json.dumps({"events": [
        {"tStartMs": 0, "dDurationMs": 400, "segs": [{"utf8": "a>>b", "tOffsetMs": 0}]},
    ]}), encoding="utf-8")
    tr = lade_json3(pfad, "v", "en")
    assert tr.woerter[0].text == "a>>b"


def test_wort_das_nur_aus_dem_marker_besteht_faellt_raus(tmp_path):
    import json as _json
    pfad = tmp_path / "t.json3"
    pfad.write_text(_json.dumps({"events": [
        {"tStartMs": 0, "dDurationMs": 400, "segs": [{"utf8": ">>", "tOffsetMs": 0}]},
        {"tStartMs": 400, "dDurationMs": 400, "segs": [{"utf8": " da", "tOffsetMs": 0}]},
    ]}), encoding="utf-8")
    tr = lade_json3(pfad, "v", "en")
    assert [w.text.strip() for w in tr.woerter] == ["da"]
