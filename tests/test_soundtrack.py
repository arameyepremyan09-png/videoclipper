"""Tests fuer das Musikbett (ab 2026-10-20).

Zwei Dinge sind hier wichtig und im fertigen Clip nicht zu sehen: dass
derselbe Clip IMMER dasselbe Stueck bekommt, und dass die Stimme vor dem
Mischen normiert wird. Beides faellt im QC nicht auf — die Datei hat auch mit
falscher Musik die richtige Dauer und eine Tonspur.
"""

from __future__ import annotations

import subprocess
import sys

import pytest
from videoclipper import layout, soundtrack


@pytest.fixture
def ordner(tmp_path):
    """Drei leere Dateien reichen: gewaehlt wird ueber den Namen, nicht den Inhalt."""
    for name in ("b.mp3", "a.m4a", "c.mp4"):
        (tmp_path / name).write_bytes(b"")
    return tmp_path


@pytest.fixture
def conf():
    return soundtrack.konfiguration(layout.template("FULLCAM_169"))


# --- Wahl ------------------------------------------------------------------

def test_stuecke_sind_sortiert_und_ohne_fremdes(ordner):
    (ordner / "notiz.txt").write_text("kein Ton")
    (ordner / ".DS_Store").write_bytes(b"")
    assert [p.name for p in soundtrack.stuecke(ordner)] == ["a.m4a", "b.mp3", "c.mp4"]


def test_derselbe_clip_bekommt_immer_dasselbe_stueck(ordner):
    erst = soundtrack.waehle("x0XeuK8Ejys_003", ordner)
    assert all(soundtrack.waehle("x0XeuK8Ejys_003", ordner) == erst
               for _ in range(5))


def test_die_wahl_ueberlebt_einen_prozesswechsel(ordner):
    """``hash()`` wuerde das nicht: Python streut ihn je Prozess.

    Ohne das laege unter demselben Clip bei jedem Rerender eine andere Musik,
    und zwei Laeufe waeren nicht mehr vergleichbar.
    """
    code = ("import sys;from pathlib import Path;"
            "sys.path.insert(0, 'src');"
            "from videoclipper import soundtrack;"
            f"print(soundtrack.waehle('abc_007', Path({str(ordner)!r})).name)")
    laeufe = {subprocess.run([sys.executable, "-c", code], capture_output=True,
                             text=True, check=True).stdout.strip()
              for _ in range(2)}
    assert laeufe == {soundtrack.waehle("abc_007", ordner).name}


def test_verschiedene_clips_verteilen_sich(ordner):
    """Nicht jeder Clip eines Laufes soll dieselbe Musik tragen."""
    gewaehlt = {soundtrack.waehle(f"video_{k:03d}", ordner).name for k in range(30)}
    assert len(gewaehlt) == 3


def test_leerer_ordner_gibt_nichts(tmp_path):
    assert soundtrack.waehle("egal", tmp_path) is None
    assert soundtrack.waehle("egal", tmp_path / "gibtsnicht") is None


# --- Filterkette -----------------------------------------------------------

def test_kette_normiert_die_stimme_vor_dem_mischen(conf):
    """Sonst haengt der Stimmpegel davon ab, wie laut das Stueck zufaellig ist."""
    glieder = soundtrack.kette(3, 25.0, conf, stimme="stimme_roh", ziel="a",
                               lufs=-14.0)
    assert glieder[0].startswith("[stimme_roh]loudnorm=I=-14.0")
    assert glieder[-1].endswith("[a]")


def test_kette_duckt_die_musik_unter_die_stimme(conf):
    glieder = soundtrack.kette(3, 25.0, conf, stimme="s", ziel="a", lufs=-14.0)
    graph = ";".join(glieder)
    assert "sidechaincompress" in graph
    # Die Stimme wird gespalten: einmal zum Mischen, einmal als Steuersignal.
    assert "asplit=2[st_mix][st_duck]" in graph
    assert "[mus_roh][st_duck]sidechaincompress" in graph


def test_ohne_ducking_bleibt_die_musik_durchgehend_leise(conf):
    ohne = dict(conf, ducking={"aktiv": False})
    graph = ";".join(soundtrack.kette(3, 25.0, ohne, stimme="s", ziel="a",
                                      lufs=-14.0))
    assert "sidechaincompress" not in graph and "asplit" not in graph


def test_amix_teilt_den_pegel_nicht(conf):
    """``normalize=1`` wuerde die eben normierte Stimme um 6 dB leiser machen."""
    graph = ";".join(soundtrack.kette(3, 25.0, conf, stimme="s", ziel="a",
                                      lufs=-14.0))
    assert "amix=inputs=2:normalize=0:duration=first" in graph


def test_musik_wird_auf_einen_absoluten_pegel_gebracht(conf):
    """``pegel_db`` ist der Abstand zur Stimme, nicht zum eigenen Pegel.

    GEMESSEN am 2026-10-20: Mit ``volume=-20dB`` lag das Bett je nach Stueck
    zweistellig danebem — gesenkt wurde gegen den Pegel der Datei, nicht gegen
    die normierte Stimme.
    """
    glieder = soundtrack.kette(3, 25.0, conf, stimme="s", ziel="a", lufs=-14.0)
    musik = next(g for g in glieder if "[mus_roh]" in g)
    # Erst auf den Stimmpegel, dann 20 dB darunter — in EINEM loudnorm ginge
    # es nicht, FFmpeg laesst TP nur zwischen -9 und 0 zu (Exit 222).
    assert "loudnorm=I=-14.0:TP=-1.5" in musik
    assert "volume=-20.00dB" in musik
    assert musik.index("loudnorm") < musik.index("volume=")


def test_blende_aus_liegt_am_clipende(conf):
    glieder = soundtrack.kette(3, 25.0, conf, stimme="s", ziel="a", lufs=-14.0)
    musik = next(g for g in glieder if "afade=t=out" in g)
    # 25 s Clip, 1 s Ausblende -> Start bei 24
    assert "afade=t=out:st=24.000:d=1.000" in musik
    assert "atrim=0:25.000" in musik


def test_kurzer_clip_bekommt_keine_negative_ausblende(conf):
    """Bei einem Clip, der kuerzer als die Ausblende ist, darf st nicht unter 0."""
    glieder = soundtrack.kette(3, 0.5, conf, stimme="s", ziel="a", lufs=-14.0)
    assert "afade=t=out:st=0.000" in ";".join(glieder)


# --- Hauswerte -------------------------------------------------------------

def test_soundtrack_haengt_unter_jedem_template():
    """Wie Untertitel und Follow: Hausregel, kein Template-Wert (Leitprinzip 3)."""
    for name in ("FULLCAM_169", "REACT_STACK", "TOP5_HALLOFCLIPS", "VLOG_FULL"):
        assert soundtrack.aktiv(layout.template(name)), name


def test_schleife_setzt_stream_loop(conf, tmp_path):
    datei = tmp_path / "a.mp3"
    datei.write_bytes(b"")
    assert soundtrack.eingang(datei, conf)[:2] == ["-stream_loop", "-1"]
    ohne = dict(conf, schleife=False)
    assert soundtrack.eingang(datei, ohne) == ["-i", str(datei)]
