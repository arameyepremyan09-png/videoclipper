"""Tests fuer Hookpruefung und Rangliste.

Beides sind Urteile ueber einen Plan, nicht ueber eine Datei — sie koennen
also nie im QC auffallen. Eine Headline, die die Pointe verraet, erzeugt einen
technisch einwandfreien Clip, den niemand zu Ende schaut.
"""

from __future__ import annotations

import pytest
from videoclipper import hook, rangliste
from videoclipper.transcript import Transkript, Wort


def _tr(*paare: tuple[str, float, float]) -> Transkript:
    return Transkript("t", "de", tuple(Wort(t, a, b) for t, a, b in paare))


def _rede(text: str, ab: float = 0.0, takt: float = 0.4) -> list:
    """Woerter gleichmaessig auf die Zeitachse legen."""
    return [(w, ab + i * takt, ab + i * takt + takt * 0.9)
            for i, w in enumerate(text.split())]


# --- Verrat -----------------------------------------------------------------

def test_headline_die_die_pointe_nennt_wird_gemeldet():
    """'Klappmesser' faellt erst am Ende — im Titel ist es der Spoiler."""
    tr = _tr(*_rede("guten abend haben sie einen ausweis dabei bitte einmal"),
             *_rede("hier ist ein klappmesser in der jackentasche", ab=10.0))
    b = hook.pruefe("Er hatte ein Klappmesser dabei", tr, 0.0, 15.0)
    assert "klappmesser" in b.verraeter
    assert not b.taugt


def test_wort_das_schon_im_aufbau_faellt_verraet_nichts():
    """Wer den Ausweis von Anfang an nennt, spoilert nicht — er ordnet ein."""
    tr = _tr(*_rede("ausweis bitte einmal den ausweis zeigen danke sehr"),
             *_rede("und was ist das denn hier bitte ausweis", ab=10.0))
    b = hook.pruefe("Was der Ausweis nicht verrät", tr, 0.0, 15.0)
    assert b.verraeter == []
    assert b.taugt


def test_headline_ohne_bezug_zum_clip_wird_gemeldet():
    tr = _tr(*_rede("guten abend einmal den ausweis bitte danke sehr"))
    b = hook.pruefe("Ferrari explodiert auf Autobahn", tr, 0.0, 4.0)
    assert not b.verankert
    assert not b.taugt


def test_offene_headline_wird_erkannt():
    tr = _tr(*_rede("guten abend einmal den ausweis bitte danke"))
    assert hook.pruefe("Was dann passierte", tr, 0.0, 4.0).offen
    assert hook.pruefe("Keiner kam hier rein", tr, 0.0, 4.0).offen
    assert hook.pruefe("Er zeigte den Ausweis", tr, 0.0, 4.0).offen is False


def test_zu_lange_headline_wird_gemeldet():
    tr = _tr(*_rede("guten abend ausweis bitte"))
    b = hook.pruefe("Was hier an dieser Tür in Köln an einem Samstagabend geschah",
                    tr, 0.0, 3.0)
    assert any("Zeichen" in h for h in b.hinweise)


# --- Payoff-Position --------------------------------------------------------

def test_payoff_liegt_dort_wo_am_meisten_gesprochen_wird():
    ruhe = [(f"x{i}", i * 3.0, i * 3.0 + 0.2) for i in range(4)]     # 0..12s duenn
    dicht = _rede("hier faellt jetzt sehr viel text auf einmal hintereinander",
                  ab=13.0, takt=0.25)
    p = hook.payoff_position(_tr(*ruhe, *dicht), 0.0, 20.0)
    assert p is not None and p > 0.55


def test_payoff_ohne_genug_woerter_ist_unbekannt():
    assert hook.payoff_position(_tr(("ja", 1.0, 1.2)), 0.0, 10.0) is None


# --- Rangliste --------------------------------------------------------------

@pytest.fixture
def plaene():
    def eintrag(cid, start, ende, headline, overall):
        return {"clip_id": cid, "modus": "SOLO",
                "quelle": {"video_id": "v", "kanal": "k", "orig_start": start},
                "tier": "B", "profil": "P", "template": "T", "template_grund": "g",
                "timing": {"start": start, "ende": ende}, "headline": headline,
                "score": {"overall": overall, "reaktion": 0.5,
                          "klarheit": 0.5, "payoff": 0.5}, "grund": "g"}
    return [eintrag("a", 0.0, 20.0, "Was dann passierte", 0.9),
            eintrag("b", 30.0, 55.0, "Er hatte ein Klappmesser dabei", 0.8),
            eintrag("c", 60.0, 80.0, "Keiner wollte hier rein", 0.6)]


@pytest.fixture
def tr_lang():
    """Drei Fenster, von denen genau eines eine verraeterische Headline hat.

    Fenster a (0-20s) und c (60-80s) verankern ihre Headline im Aufbau.
    Fenster b (30-55s) nennt 'klappmesser' erst nach zwei Dritteln — genau der
    Fall, den die Pruefung finden soll.
    """
    w = []
    w += _rede("was dann passierte war schon sehr komisch und passierte "
               "einfach so ohne grund passierte das alles", ab=0.0, takt=1.0)
    w += _rede("guten abend einmal bitte den ausweis zeigen danke sehr "
               "schoenen abend wuensche ich noch viel spass", ab=30.0, takt=1.0)
    # ...und erst hier, nach zwei Dritteln des Fensters, faellt das Wort:
    w += _rede("hier ist ein klappmesser gewesen", ab=48.0, takt=1.0)
    w += _rede("keiner wollte hier rein heute abend niemand wollte hier rein "
               "einfach keiner wollte rein hier", ab=60.0, takt=1.0)
    return _tr(*sorted(w, key=lambda x: x[1]))


def test_rangliste_sortiert_absteigend(plaene, tr_lang):
    plaetze = rangliste.bilde(plaene, tr_lang)
    assert len(plaetze) == 3
    werte = [(p.hookbefund.taugt, p.prognose.score) for p in plaetze]
    assert werte == sorted(werte, reverse=True)


def test_verraterische_headline_rutscht_ans_ende(plaene, tr_lang):
    """Die Prognose kennt den Clipinhalt nicht — die Hookpruefung schon."""
    plaetze = rangliste.bilde(plaene, tr_lang)
    assert [p.clip_id for p in plaetze][-1] == "b"
    assert plaetze[-1].hookbefund.verraeter == ["klappmesser"]


def test_kein_platz_hat_eine_negative_dauer(plaene, tr_lang):
    """Regression: liegt ein Fenster hinter dem letzten Wort, zog `snappe`
    das Ende vor den Anfang und FFmpeg bekam ein negatives ``-t``."""
    kurz = _tr(*_rede("nur ein kurzes transkript hier"))
    for p in rangliste.bilde(plaene, kurz):
        assert p.dauer > 0, p.clip_id
        assert p.ende > p.start


def test_rangliste_nutzt_dieselbe_dauer_wie_der_renderer(plaene, tr_lang):
    """Sonst rankt man Laengen, die in der fertigen Datei nie vorkommen."""
    from videoclipper.snapping import snappe
    for p in rangliste.bilde(plaene, tr_lang):
        roh = next(x for x in plaene if x["clip_id"] == p.clip_id)
        s, e, tier = snappe(tr_lang, roh["timing"]["start"], roh["timing"]["ende"])
        assert (p.start, p.ende, p.tier) == (s, e, tier)


def test_tabelle_hat_eine_zeile_pro_clip(plaene, tr_lang):
    zeilen = rangliste.tabelle(rangliste.bilde(plaene, tr_lang))
    kopf = [z for z in zeilen if z.strip().startswith(("1 ", "2 ", "3 "))]
    assert len(kopf) == 3


def test_ein_fragewort_verraet_nichts():
    """OFFEN-Woerter halten zurueck, sie benennen nicht.

    Gemessen am 2026-09-08: "WARUM WARTET ER KEINE ZWEI TAGE" wurde als
    Spoiler gemeldet, weil im letzten Drittel des Clips jemand "Warum hast du
    nicht einfach die Flasche bestellt?" fragt. Seit Satzzeichen verboten sind,
    ist ein OFFEN-Wort das einzige Mittel, eine Headline offen zu halten — der
    Fehlalarm traf also genau die richtigen Headlines.
    """
    tr = _tr(*_rede("ich habe zwei tage gewartet und dann kam nichts"),
             *_rede("warum hast du das eigentlich gemacht", ab=10.0))
    b = hook.pruefe("WARUM WARTET ER KEINE ZWEI TAGE", tr, 0.0, 14.0)
    assert b.verraeter == []
    assert b.verankert and b.offen
