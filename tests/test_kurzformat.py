"""Tests fuer das Kurzformat mit Teaser (ab 2026-09-11).

Erst der lustigste Moment, dann die Geschichte mit Kontext, zusammen
mindestens 30 s. Im fertigen Clip ist davon nur noch mit der Stoppuhr etwas zu
pruefen — und ein Punch-in, der im falschen Segment oder zur falschen Zeit
sitzt, faellt im QC der Datei gar nicht auf.
"""

from __future__ import annotations

import pytest
from videoclipper import follow, kurzformat, layout, render
from videoclipper.editplan import Aufgeloest, EditPlan, Pointe


@pytest.fixture
def tmpl():
    return layout.template("DUO_STACK")


@pytest.fixture
def panels(tmpl):
    return layout.panels(layout.profil("COACHLIM_DUO"), tmpl, "DUO")


def _segs(teaser=(200.0, 204.0), haupt=(170.0, 210.0)) -> list[dict]:
    return kurzformat.segmente(teaser, haupt)


def _ein(start: float = 100.0, dauer: float = 40.0) -> list[dict]:
    """Ein Clip aus einem Stueck, wie ``cmd_rendere`` ihn ohne Teaser anlegt."""
    return [{"art": "haupt", "start": start, "ende": start + dauer,
             "dauer": dauer, "ab": 0.0}]


# --- Segmente und Regeln ---------------------------------------------------

def test_teaser_steht_vorn_und_der_hauptteil_schliesst_an():
    s = _segs()
    assert [x["art"] for x in s] == ["teaser", "haupt"]
    assert s[0]["ab"] == 0.0 and s[1]["ab"] == pytest.approx(4.0)
    assert s[1]["dauer"] == pytest.approx(40.0)


def test_sauberer_clip(tmpl):
    fehler, hinweise = kurzformat.pruefe(_segs(), Pointe(t=202.0), tmpl["kurzformat"])
    assert fehler == [] and hinweise == []


def test_unter_30_sekunden_bricht_ab(tmpl):
    """Die Rueckmeldung des Nutzers woertlich: zu kurz, kein Kontext."""
    fehler, _ = kurzformat.pruefe(_segs(haupt=(185.0, 205.0)), Pointe(t=202.0),
                                  tmpl["kurzformat"])
    assert any("mindestens" in f for f in fehler)


@pytest.mark.parametrize("teaser", [(200.0, 201.0), (195.0, 204.0)])
def test_teaser_ausserhalb_seiner_grenzen_bricht_ab(tmpl, teaser):
    fehler, _ = kurzformat.pruefe(_segs(teaser=teaser), Pointe(t=200.5),
                                  tmpl["kurzformat"])
    assert any("Teaser" in f for f in fehler)


def test_pointe_ausserhalb_des_teasers_bricht_ab(tmpl):
    """Dann zeigte der Hook etwas anderes als den Lacher."""
    fehler, _ = kurzformat.pruefe(_segs(), Pointe(t=190.0), tmpl["kurzformat"])
    assert any("Pointe" in f for f in fehler)


def test_laenger_als_ziel_ist_nur_ein_hinweis(tmpl):
    fehler, hinweise = kurzformat.pruefe(_segs(haupt=(130.0, 210.0)),
                                         Pointe(t=202.0), tmpl["kurzformat"])
    assert fehler == [] and hinweise


# --- Punch-in --------------------------------------------------------------

def test_cams_stossen_an_der_naht_zusammen(panels):
    """DUO_STACK setzt beide Cams an die Naht, ohne Luecke und ohne Blurbalken."""
    _, oben = layout.sichtbar(panels[0])
    _, unten = layout.sichtbar(panels[1])
    assert oben == (0, 352, 1080, 608)
    assert unten == (0, 960, 1080, 608)


def test_punch_in_zoomt_im_teaser_und_im_hauptteil(tmpl, panels):
    """Wer bis zur Pointe bleibt, bekommt sie so, wie der Hook sie versprochen hat."""
    punch = kurzformat.punch_in(Pointe(t=202.0), _segs(), panels, tmpl["kurzformat"])
    assert {(e["segment"], round(e["ab"], 3)) for e in punch} == {(0, 2.0), (1, 36.0)}
    assert len(punch) == 4                                   # zwei Panels je Segment


def test_punch_endet_mit_seinem_segment(tmpl, panels):
    """Kurz vor dem Rueckschnitt darf der Zoom nicht in den Hauptteil laufen."""
    s = _segs()
    punch = kurzformat.punch_in(Pointe(t=203.5), s, panels, tmpl["kurzformat"])
    teaser = [e for e in punch if e["segment"] == 0][0]
    assert teaser["bis"] == pytest.approx(s[0]["dauer"])


def test_punch_in_bleibt_im_sichtbaren_rechteck(tmpl, panels):
    """Sonst stuende im Zoom Rahmen oder Schwarz, das vorher nicht zu sehen war."""
    punch = kurzformat.punch_in(Pointe(t=104.0), _ein(), panels, tmpl["kurzformat"])
    assert len(punch) == 2
    for e, p in zip(punch, panels):
        (qx, qy, qw, qh), ziel = layout.sichtbar(p)
        zx, zy, zw, zh = e["quelle"]
        assert qx <= zx and zx + zw <= qx + qw
        assert qy <= zy and zy + zh <= qy + qh
        assert zx % 2 == 0 and zy % 2 == 0 and zw % 2 == 0 and zh % 2 == 0
        assert e["ziel"] == list(ziel)


def test_punch_in_zoomt_um_das_gesicht(tmpl, panels):
    """Eli sitzt rechts unter der Mitte — der Ausschnitt folgt ihm."""
    e = kurzformat.punch_in(Pointe(t=104.0, fokus=["cam_rechts"]), _ein(), panels,
                            tmpl["kurzformat"])[0]
    zx, zy, zw, zh = e["quelle"]
    p = panels[1]
    assert zx <= p["fokus_x"] <= zx + zw
    assert zy <= p["fokus_y"] <= zy + zh
    assert zx + zw / 2 > p["src"][0] + p["src"][2] / 2      # rechts der Boxmitte


def test_unbekannter_fokus_bricht_ab(tmpl, panels):
    with pytest.raises(ValueError, match="cam_mitte"):
        kurzformat.punch_in(Pointe(t=104.0, fokus=["cam_mitte"]), _ein(), panels,
                            tmpl["kurzformat"])


def test_punch_fenster_wird_begrenzt(tmpl, panels):
    conf = tmpl["kurzformat"]
    lang = kurzformat.punch_in(Pointe(t=104.0, bis=110.0), _ein(), panels, conf)
    assert lang[0]["bis"] - lang[0]["ab"] == pytest.approx(conf["punch_in"]["max_dauer"])
    kurz = kurzformat.punch_in(Pointe(t=104.0, bis=104.1), _ein(), panels, conf)
    assert kurz[0]["bis"] - kurz[0]["ab"] == pytest.approx(conf["punch_in"]["min_dauer"])


# --- Follow ----------------------------------------------------------------

@pytest.mark.parametrize("teaser_dauer", [2.0, 4.5, 7.0])
def test_follow_steht_im_hauptteil(tmpl, teaser_dauer):
    """Im Teaser hat der Zuschauer noch nicht entschieden, ob er bleibt."""
    s = kurzformat.segmente((300.0, 300.0 + teaser_dauer), (260.0, 295.0))
    conf = kurzformat.follow_conf(tmpl["follow_hinweis"], s, tmpl["kurzformat"])
    h, _ = follow.platziere(sum(x["dauer"] for x in s), conf)
    assert h is not None and h.ab >= s[1]["ab"]


def test_ohne_teaser_bleibt_follow_wie_es_war(tmpl):
    assert kurzformat.follow_conf(tmpl["follow_hinweis"], _ein(), tmpl["kurzformat"]) \
        is tmpl["follow_hinweis"]


def test_follow_auf_der_pointe_wird_gemeldet():
    punch = [{"ab": 10.0, "bis": 11.6}]
    assert kurzformat.verdeckt(9.0, 12.0, punch)
    assert kurzformat.verdeckt(12.0, 15.0, punch) == []


# --- Filtergraph -----------------------------------------------------------

def _plan(tmpl, panels, segs, punch) -> EditPlan:
    plan = EditPlan.model_validate({
        "clip_id": "t", "quelle": {"video_id": "v", "kanal": "k", "orig_start": 0.0},
        "tier": "B", "profil": "COACHLIM_DUO", "template": "DUO_STACK",
        "template_grund": "-",
        "timing": {"start": segs[-1]["start"], "ende": segs[-1]["ende"]},
        "headline": "TEST HEADLINE 💀🙏", "grund": "-",
        "score": {"overall": 0.5, "reaktion": 0.5, "klarheit": 0.5, "payoff": 0.5}})
    plan.resolved = Aufgeloest(
        start=segs[-1]["start"], ende=segs[-1]["ende"],
        dauer=sum(s["dauer"] for s in segs), modus="DUO", modus_anteil=1.0,
        panels=panels, canvas=tuple(tmpl["canvas"]), fps=30,
        headline_y=tmpl["headline"]["y"], punch_in=punch,
        segmente=segs if len(segs) > 1 else [])
    return plan


def test_graph_mit_teaser_haengt_zwei_buehnen_aneinander(tmpl, panels):
    s = _segs()
    punch = kurzformat.punch_in(Pointe(t=202.0), s, panels, tmpl["kurzformat"])
    g = render.filtergraph_teile(_plan(tmpl, panels, s, punch), tmpl, -14.0)
    assert "concat=n=2:v=1:a=0[buehne]" in g
    assert "[0:a][1:a]concat=n=2:v=0:a=1,loudnorm" in g
    # Punch-in je Segment aus seinem eigenen Eingang, in Segmentzeit.
    assert "[0:v]crop=" in g and "[1:v]crop=" in g
    assert "between(t,2.000," in g and "between(t,32.000," in g
    # Die Headline ist der erste PNG-Eingang nach den beiden Videoeingaengen.
    assert "[buehne][2:v]overlay" in g


def test_einzelpfad_bleibt_ein_eingang(tmpl, panels):
    s = _ein()
    punch = kurzformat.punch_in(Pointe(t=104.0), s, panels, tmpl["kurzformat"])
    g = render.filtergraph(_plan(tmpl, panels, s, punch), tmpl)
    assert "concat" not in g and "[1:v]crop" not in g
    assert "vstack=inputs=2[buehne]" in g and "[1:v]overlay" in g
