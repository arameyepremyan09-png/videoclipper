"""Rechenteile des Hochladens. Netzwerk wird nicht beruehrt."""

from videoclipper import hochladen


def test_kleine_datei_ist_ein_stueck():
    assert hochladen.stuecke(3_000_000) == [(0, 2_999_999)]


def test_rest_geht_ins_letzte_stueck():
    c = hochladen.CHUNK
    bereiche = hochladen.stuecke(2 * c + 123)
    assert bereiche == [(0, c - 1), (c, 2 * c + 122)]


def test_stuecke_lueckenlos():
    g = 47_123_456
    b = hochladen.stuecke(g)
    assert b[0][0] == 0 and b[-1][1] == g - 1
    assert all(b[i][1] + 1 == b[i + 1][0] for i in range(len(b) - 1))


def test_tokenordner_ueberschreibbar(tmp_path, monkeypatch):
    monkeypatch.setenv("VIDEOCLIPPER_SCHLUESSEL", str(tmp_path / "k"))
    assert hochladen.verbunden() == {"youtube": False, "tiktok": False}
    hochladen._speichere_token("youtube", {"refresh_token": "x"})
    assert hochladen.verbunden()["youtube"] is True
    assert (tmp_path / "k" / "tokens.json").stat().st_mode & 0o077 == 0
