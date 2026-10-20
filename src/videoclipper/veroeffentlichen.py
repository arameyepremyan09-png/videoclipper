"""Stage 18b — einen ganzen Lauf mit einem Befehl veroeffentlichen.

``clip veroeffentliche [ordner]`` nimmt einen Lauf (Standard: den juengsten
unter ``clips/``) und erledigt, was am 2026-10-21 noch Handarbeit war:

  * YouTube: jeder Clip wird hochgeladen und auf einen eigenen Termin geplant,
    stuendlich ab 10 Uhr (Auftrag des Nutzers, ``[veroeffentlichen]`` in
    settings.toml). Termine, die schon ein anderer Lauf belegt, werden
    uebersprungen.
  * TikTok: jeder Clip geht als Entwurf in den Posteingang der App. TikTok
    nimmt dabei KEINEN Titel an — der Befehl gibt die Titel zum Einfuegen aus.
  * Register: jeder YouTube-Post landet mit Termin und clip_id in Stage 16.

Was erledigt ist, steht in ``json/hochgeladen.json``. Ein zweiter Aufruf macht
dort weiter, wo der erste aufgehoert hat. Das ist kein Komfort, sondern noetig:
TikTok lehnt nach etwa sechs offenen Entwuerfen jeden weiteren ab
(``spam_risk_too_many_pending_share``), und YouTube hat ein Tageskontingent.
"""

from __future__ import annotations

import json
import re
from datetime import date, datetime, time, timedelta
from pathlib import Path
from typing import Any, Callable, Iterable
from zoneinfo import ZoneInfo

from . import hochladen, publish, store
from .settings import einstellungen

STANDARD = {"zeitzone": "Europe/Berlin", "ab": "10:00", "bis": "22:00",
            "abstand_minuten": 60, "vorlauf_minuten": 15}


def konfiguration() -> dict[str, Any]:
    return {**STANDARD, **einstellungen().get("veroeffentlichen", {})}


# --- titel.md ----------------------------------------------------------------

def lies_titel(text: str) -> dict[str, dict[str, str]]:
    """Gegenstueck zu ``ausgabe.Lauf.titel``: {clip_id: {"tiktok", "youtube"}}."""
    titel: dict[str, dict[str, str]] = {}
    for block in re.split(r"^## ", text, flags=re.M)[1:]:
        clip_id = block.splitlines()[0].strip()
        felder = {}
        for kopf, schluessel in (("TikTok", "tiktok"), ("YouTube Shorts", "youtube")):
            m = re.search(rf"\*\*{kopf}\*\*[^\n]*\n[ \t]*\n {{4}}(.+)", block)
            if m:
                felder[schluessel] = m.group(1).strip()
        titel[clip_id] = felder
    return titel


def hashtags(text: str) -> list[str]:
    return re.findall(r"#\w+", text)


# --- Zeitplan ----------------------------------------------------------------

def zeitplan(anzahl: int, frueheste: datetime, *, ab: time, bis: time,
             abstand: timedelta, zone: ZoneInfo,
             belegt: Iterable[datetime] = ()) -> list[datetime]:
    """Die naechsten ``anzahl`` freien Termine im Raster ab..bis.

    Ein Termin gilt als belegt, wenn ein vorhandener naeher als ``abstand``
    liegt — zwei Shorts in derselben Stunde nehmen sich die Reichweite.
    """
    belegt = list(belegt)
    termine: list[datetime] = []
    tag = frueheste.astimezone(zone).date()
    while len(termine) < anzahl:
        t = datetime.combine(tag, ab, zone)
        ende = datetime.combine(tag, bis, zone)
        while t <= ende and len(termine) < anzahl:
            frei = all(abs(t - b) >= abstand for b in belegt + termine)
            if t >= frueheste and frei:
                termine.append(t)
            t += abstand
        tag += timedelta(days=1)
    return termine


def _geplante_youtube_termine(jetzt: datetime) -> list[datetime]:
    """Termine aus dem Register, die noch in der Zukunft liegen."""
    termine = []
    for p in store.posts():
        if p.get("plattform") != "youtube" or not p.get("veroeffentlicht"):
            continue
        try:
            t = datetime.fromisoformat(p["veroeffentlicht"])
        except ValueError:
            continue
        if t.tzinfo and t > jetzt:
            termine.append(t)
    return termine


# --- Stand eines Laufes ------------------------------------------------------

def _stand_pfad(lauf: Path) -> Path:
    return lauf / "json" / "hochgeladen.json"


def lade_stand(lauf: Path) -> dict[str, dict[str, Any]]:
    pfad = _stand_pfad(lauf)
    return json.loads(pfad.read_text(encoding="utf-8")) if pfad.exists() else {}


def speichere_stand(lauf: Path, stand: dict[str, dict[str, Any]]) -> None:
    pfad = _stand_pfad(lauf)
    pfad.parent.mkdir(parents=True, exist_ok=True)
    pfad.write_text(json.dumps(stand, ensure_ascii=False, indent=2), encoding="utf-8")


# --- Ablauf ------------------------------------------------------------------

def veroeffentliche(lauf: Path, *, plattformen: Iterable[str] = hochladen.PLATTFORMEN,
                    ab_tag: date | None = None, probe: bool = False,
                    melde: Callable[[str], None] = print) -> dict[str, Any]:
    """Laedt jeden Clip des Laufes hoch, der dort noch fehlt.

    Rueckgabe: ``{"tiktok_titel": [(clip_id, titel)], "tiktok_offen": n,
    "youtube_offen": n}`` — offen heisst: beim naechsten Aufruf dran.
    """
    conf = konfiguration()
    zone = ZoneInfo(conf["zeitzone"])
    jetzt = datetime.now(zone)
    plattformen = list(plattformen)

    titel_md = lauf / "titel.md"
    if not titel_md.exists():
        raise hochladen.HochladeFehler(f"{titel_md} fehlt.")
    titel = lies_titel(titel_md.read_text(encoding="utf-8"))
    clips = sorted(p.stem for p in (lauf / "mp4").glob("*.mp4"))
    ohne = [c for c in clips if c not in titel]
    if ohne:
        raise hochladen.HochladeFehler(f"Kein Titel in titel.md fuer: {', '.join(ohne)}")
    if not clips:
        raise hochladen.HochladeFehler(f"Keine Clips in {lauf / 'mp4'}")

    stand = lade_stand(lauf)
    ergebnis: dict[str, Any] = {"tiktok_titel": [], "tiktok_offen": 0, "youtube_offen": 0}
    melde(f"Lauf {lauf.name}: {len(clips)} Clips")

    if "youtube" in plattformen:
        offen = [c for c in clips if "youtube" not in stand.get(c, {})]
        frueheste = jetzt + timedelta(minutes=conf["vorlauf_minuten"])
        if ab_tag:
            frueheste = max(frueheste, datetime.combine(ab_tag, time(0), zone))
        termine = zeitplan(
            len(offen), frueheste, ab=time.fromisoformat(conf["ab"]),
            bis=time.fromisoformat(conf["bis"]),
            abstand=timedelta(minutes=conf["abstand_minuten"]), zone=zone,
            belegt=_geplante_youtube_termine(jetzt))
        melde(f"\nYouTube: {len(offen)} offen")
        for i, (clip_id, termin) in enumerate(zip(offen, termine)):
            t = titel[clip_id]
            yt_titel = t.get("youtube") or re.sub(r"\s*#\w+", "", t.get("tiktok", ""))
            tags = hashtags(t.get("tiktok", ""))
            if probe:
                melde(f"  {clip_id}  {termin:%a %d.%m. %H:%M}  {yt_titel}")
                continue
            try:
                r = hochladen.lade_youtube_hoch(
                    lauf / "mp4" / f"{clip_id}.mp4", yt_titel,
                    beschreibung=" ".join(tags), tags=[h[1:] for h in tags],
                    sichtbarkeit="oeffentlich", zeit=termin.isoformat())
            except hochladen.HochladeFehler as e:
                melde(f"  {clip_id}  FEHLER {e}")
                if "quota" in str(e).lower():
                    melde("  Tageskontingent erschoepft — morgen denselben Befehl erneut.")
                    ergebnis["youtube_offen"] = len(offen) - i
                    break
                ergebnis["youtube_offen"] += 1
                continue
            stand.setdefault(clip_id, {})["youtube"] = {
                "id": r["id"], "url": r["url"], "termin": termin.isoformat()}
            speichere_stand(lauf, stand)
            publish.registriere("youtube", r["url"], clip_id=clip_id, titel=yt_titel,
                                veroeffentlicht=termin, notiz=f"veroeffentliche {lauf.name}")
            melde(f"  {clip_id}  {termin:%a %d.%m. %H:%M}  {r['url']}")

    if "tiktok" in plattformen:
        offen = [c for c in clips if "tiktok" not in stand.get(c, {})]
        melde(f"\nTikTok (Entwuerfe): {len(offen)} offen")
        for i, clip_id in enumerate(offen):
            if probe:
                melde(f"  {clip_id}  Entwurf")
                continue
            try:
                r = hochladen.poste_tiktok(lauf / "mp4" / f"{clip_id}.mp4", "",
                                           modus="entwurf")
            except hochladen.HochladeFehler as e:
                if "too_many_pending" in str(e):
                    ergebnis["tiktok_offen"] = len(offen) - i
                    melde(f"  TikTok nimmt keine weiteren Entwuerfe an — "
                          f"{ergebnis['tiktok_offen']} bleiben fuer den naechsten Aufruf.")
                    break
                melde(f"  {clip_id}  FEHLER {e}")
                ergebnis["tiktok_offen"] += 1
                continue
            stand.setdefault(clip_id, {})["tiktok"] = {
                "publish_id": r["publish_id"], "status": r.get("status"),
                "gesendet": jetzt.isoformat(timespec="seconds")}
            speichere_stand(lauf, stand)
            ergebnis["tiktok_titel"].append((clip_id, titel[clip_id].get("tiktok", "")))
            melde(f"  {clip_id}  im Posteingang")

    return ergebnis
