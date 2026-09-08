"""Tests fuer die Laufablage.

Was hier falsch sein kann, kostet keinen Renderfehler, sondern Ordnung: Zwei
Laeufe, die sich denselben Ordner teilen, ueberschreiben einander lautlos —
die zweite MP4 traegt denselben Clipnamen wie die erste. Genau das war der
Zustand vorher, nur ohne Ordner.
"""

from __future__ import annotations

from datetime import datetime

from videoclipper import ausgabe


# --- Der Ordnername ist Datum und Uhrzeit ----------------------------------

def test_ordner_heisst_nach_datum_und_uhrzeit(tmp_path):
    lauf = ausgabe.neuer_lauf(tmp_path, datetime(2026, 9, 8, 14, 30, 15))
    assert lauf.name == "2026-09-08_14-30-15"


def test_ordnername_enthaelt_keinen_doppelpunkt(tmp_path):
    """ISO-Zeit haette ``14:30:15``, und ``:`` ist auf Windows in Dateinamen
    verboten. Das Repo laeuft auf beiden Maschinen."""
    lauf = ausgabe.neuer_lauf(tmp_path, datetime(2026, 9, 8, 14, 30, 15))
    assert ":" not in lauf.name


def test_ordnernamen_sortieren_chronologisch(tmp_path):
    """Als Text sortiert dieselbe Reihenfolge wie in der Zeit — sonst muesste
    ``zuletzt`` die Namen parsen."""
    frueh = ausgabe.neuer_lauf(tmp_path, datetime(2026, 9, 8, 9, 5, 0)).name
    spaet = ausgabe.neuer_lauf(tmp_path, datetime(2026, 9, 8, 14, 30, 15)).name
    assert sorted([spaet, frueh]) == [frueh, spaet]


# --- Jeder Aufruf bekommt einen eigenen Ordner -----------------------------

def test_zweiter_lauf_in_derselben_sekunde_bekommt_eigenen_ordner(tmp_path):
    """Zwei Aufrufe aus einem Skript koennen in dieselbe Sekunde fallen.
    Der zweite darf die Clips des ersten nicht ueberschreiben."""
    zeit = datetime(2026, 9, 8, 14, 30, 15)
    a = ausgabe.neuer_lauf(tmp_path, zeit)
    b = ausgabe.neuer_lauf(tmp_path, zeit)
    assert a.wurzel != b.wurzel
    assert b.name == "2026-09-08_14-30-15_2"


def test_dritter_lauf_zaehlt_weiter(tmp_path):
    zeit = datetime(2026, 9, 8, 14, 30, 15)
    namen = [ausgabe.neuer_lauf(tmp_path, zeit).name for _ in range(3)]
    assert namen[-1] == "2026-09-08_14-30-15_3"
    assert len(set(namen)) == 3


# --- MP4 getrennt von JSON und PNG -----------------------------------------

def test_die_drei_unterordner_entstehen_sofort(tmp_path):
    """Auch wenn der Lauf abbricht: Ein leerer ``mp4``-Ordner ist eine
    ehrlichere Auskunft als ein fehlender."""
    lauf = ausgabe.neuer_lauf(tmp_path)
    assert {p.name for p in lauf.wurzel.iterdir()} == {"mp4", "json", "png"}
    assert all(p.is_dir() for p in lauf.wurzel.iterdir())


def test_mp4_liegt_nicht_neben_json_und_png(tmp_path):
    lauf = ausgabe.neuer_lauf(tmp_path)
    assert lauf.clip("v_001").parent == lauf.mp4
    assert lauf.editplan("v_001").parent == lauf.json
    assert lauf.mp4 != lauf.json != lauf.png != lauf.mp4


def test_clip_und_editplan_teilen_den_stamm(tmp_path):
    """Derselbe Clip, zwei Ordner — die Zuordnung laeuft ueber den Namen."""
    lauf = ausgabe.neuer_lauf(tmp_path)
    assert lauf.clip("abc_007").stem == lauf.editplan("abc_007").stem.split(".")[0]


# --- lauf.json sagt, woraus der Ordner entstanden ist ----------------------

def test_notiere_schreibt_nach_json(tmp_path):
    lauf = ausgabe.neuer_lauf(tmp_path)
    pfad = lauf.notiere(video_id="6T-QuUKYy7w", profil="COACHLIM_X")
    assert pfad.parent == lauf.json
    import json as _json
    daten = _json.loads(pfad.read_text(encoding="utf-8"))
    assert daten["video_id"] == "6T-QuUKYy7w"
    assert daten["lauf"] == lauf.name


def test_notiere_ergaenzt_statt_zu_ersetzen(tmp_path):
    """Ein zweites Video im selben Lauf soll den ersten Eintrag nicht loeschen."""
    lauf = ausgabe.neuer_lauf(tmp_path)
    lauf.notiere(video_id="a", clips=3)
    lauf.notiere(profil="P")
    import json as _json
    daten = _json.loads((lauf.json / "lauf.json").read_text(encoding="utf-8"))
    assert daten == {"video_id": "a", "clips": 3, "profil": "P", "lauf": lauf.name}


# --- zuletzt ---------------------------------------------------------------

def test_zuletzt_findet_den_juengsten_lauf(tmp_path):
    ausgabe.neuer_lauf(tmp_path, datetime(2026, 9, 8, 9, 0, 0))
    neu = ausgabe.neuer_lauf(tmp_path, datetime(2026, 9, 8, 18, 0, 0))
    assert ausgabe.zuletzt(tmp_path).wurzel == neu.wurzel


def test_zuletzt_ohne_laeufe_ist_none(tmp_path):
    assert ausgabe.zuletzt(tmp_path) is None


def test_zuletzt_uebergeht_fremde_ordner(tmp_path):
    """Im Altbestand liegen unter clips/ auch Ordner ohne mp4/ — etwa das
    alte ``overlays/``. Die sind keine Laeufe."""
    (tmp_path / "overlays").mkdir()
    lauf = ausgabe.neuer_lauf(tmp_path, datetime(2026, 9, 8, 9, 0, 0))
    assert ausgabe.zuletzt(tmp_path).wurzel == lauf.wurzel
