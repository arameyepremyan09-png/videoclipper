"""Tests fuer die eigene ASR.

Der Aufruf von whisper.cpp braucht ein Modell und laeuft deshalb nicht im
Test. Was hier falsch sein kann, ist die Umwandlung ins json3-Format — und
genau die entscheidet, ob der Rest der Pipeline das Transkript ueberhaupt
lesen kann. Geprueft wird deshalb gegen den echten Parser aus Stage 03, nicht
gegen eine erwartete Datenstruktur.
"""

from __future__ import annotations

import json

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
