"""Stage 00 — Kanaele beobachten und neue Videos ohne Zutun clippen.

``clip beobachte`` laeuft als macOS-Dienst (LaunchAgent) alle zehn Minuten und
fuehrt jedes neue Video eines Kanals aus ``config/kanaele.yaml`` durch:

  1. **Feed.** YouTube gibt je Kanal einen RSS-Feed mit den letzten 15 Videos
     heraus — ohne API-Schluessel und ohne Kontingent. Shorts erkennt man am
     Link (``/shorts/``); sie werden nicht geclippt.
  2. **Pruefung.** ``yt-dlp -J`` liefert Laenge, Live-Status und Untertitel.
     Ein laufender Stream, eine Premiere oder ein Video ohne ``de-orig``
     wartet auf den naechsten Durchgang: YouTube erzeugt die automatischen
     Untertitel oft erst Stunden nach dem Upload. Nach
     ``warte_auf_untertitel_h`` wird selbst transkribiert.
  3. **Schnitt.** Ein Claude-Code-Lauf ohne Mensch (``claude -p``) arbeitet
     den Ablauf je Video aus ARBEITSSTAND.md ab — Layout, Profil, Plan,
     Render, Pruefung. Der Auftrag steht in ``config/automat_auftrag.md``.
  4. **YouTube (Weg A).** ``veroeffentlichen.veroeffentliche`` plant jeden
     Clip oeffentlich ins Stundenraster.
  5. **TikTok (Weg B).** Nur eine Mitteilung. Die Entwuerfe gehen erst raus,
     wenn der Nutzer den Lauf angesehen hat
     (``clip veroeffentliche <lauf> --nur tiktok``).

WARUM DER AGENT NICHT SELBST HOCHLAEDT: Er liest Titel und Transkripte fremder
Kanaele. Was dort steht, darf nie bis zu einem Upload durchreichen. Der Agent
liefert einen Lauf ab; ob der hochgeladen wird, entscheidet dieser Code anhand
von ``lauf.json`` und ``titel.md``. Der Agent bekommt dazu einen leeren
Schluesselordner (``VIDEOCLIPPER_SCHLUESSEL``), keine MCP-Connectoren und
keine Web-Werkzeuge.

WARUM DAS RASTER EINE OBERGRENZE HAT: Acht Kanaele liefern zusammen rund fuenf
lange Videos am Tag, das Raster 10-22 Uhr hat 13 Termine. Ohne Grenze liefe
die Warteschlange jeden Tag weiter in die Zukunft, und ein Clip ginge erst
eine Woche nach dem Video online. Liegt der naechste freie Termin mehr als
``max_vorlauf_tage`` entfernt, wird das Video uebersprungen.

Stand, Protokoll und Agent-Ausgaben liegen unter ``<work>/beobachter/``, nicht
im Repo.
"""

from __future__ import annotations

import fcntl
import json
import os
import plistlib
import shutil
import subprocess
import sys
import urllib.request
import uuid
import xml.etree.ElementTree as ET
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, time, timedelta, timezone
from pathlib import Path
from typing import Any, Callable, Iterator
from zoneinfo import ZoneInfo

import yaml

from . import hochladen, veroeffentlichen
from .settings import CONFIG_DIR, ROOT, arbeitsverzeichnis, einstellungen

STANDARD: dict[str, Any] = {
    "intervall_s": 600,
    "min_dauer_s": 300,
    "max_dauer_s": 4 * 3600,
    "warte_auf_untertitel_h": 4.0,
    "aufgeben_nach_h": 48.0,
    "clips_pro_video": 3,
    "max_vorlauf_tage": 4,
    "min_frei_gb": 40,
    "agent_timeout_min": 240,
    "agent_versuche": 2,
    "modell": "",
    "asr_modell": "~/videoclipper/models/ggml-large-v3-turbo-q5_0.bin",
}

LABEL = "de.videoclipper.beobachter"
FEED = "https://www.youtube.com/feeds/videos.xml?channel_id={}"
NS = {"a": "http://www.w3.org/2005/Atom", "yt": "http://www.youtube.com/xml/schemas/2015"}

#: Was der Agent nie ausfuehren darf. Der leere Schluesselordner ist die
#: eigentliche Sperre; diese Liste faengt den Versuch vorher ab.
VERBOTEN = (
    "Bash(git push:*)", "Bash(git commit:*)", "Bash(curl:*)", "Bash(wget:*)",
    "Bash(*videoclipper.cli poste*)", "Bash(*videoclipper.cli veroeffentliche*)",
    "Bash(*videoclipper.cli verbinde*)", "Bash(*yt-dlp*)",
)

#: Ein Video in diesem Status kommt beim naechsten Durchgang wieder dran.
OFFEN = ("wartet", "in_arbeit", "upload_offen")


class BeobachterFehler(RuntimeError):
    pass


def konfiguration() -> dict[str, Any]:
    return {**STANDARD, **einstellungen().get("beobachten", {})}


def ordner() -> Path:
    pfad = arbeitsverzeichnis() / "beobachter"
    pfad.mkdir(parents=True, exist_ok=True)
    return pfad


def ausgabe_ordner() -> Path:
    """Automatische Laeufe getrennt von den Handlaeufen: ``ausgabe.zuletzt``
    soll fuer ``clip veroeffentliche`` ohne Ordner weiter den eigenen meinen."""
    return arbeitsverzeichnis() / "clips" / "automat"


# --- Kanaele und Feed --------------------------------------------------------

@dataclass(frozen=True)
class Kanal:
    handle: str
    channel_id: str

    @property
    def feed_url(self) -> str:
        return FEED.format(self.channel_id)


def kanaele(pfad: Path = CONFIG_DIR / "kanaele.yaml") -> list[Kanal]:
    daten = yaml.safe_load(pfad.read_text(encoding="utf-8")) or {}
    return [Kanal(k["handle"], k["channel_id"]) for k in daten.get("kanaele", [])]


@dataclass(frozen=True)
class Eintrag:
    video_id: str
    titel: str
    veroeffentlicht: datetime
    short: bool


def lies_feed(text: str) -> list[Eintrag]:
    wurzel = ET.fromstring(text)
    eintraege = []
    for e in wurzel.findall("a:entry", NS):
        link = e.find("a:link", NS)
        eintraege.append(Eintrag(
            video_id=e.findtext("yt:videoId", "", NS),
            titel=e.findtext("a:title", "", NS),
            veroeffentlicht=datetime.fromisoformat(e.findtext("a:published", "", NS)),
            short="/shorts/" in (link.get("href", "") if link is not None else "")))
    return eintraege


def hole_feed(kanal: Kanal) -> list[Eintrag]:
    anfrage = urllib.request.Request(kanal.feed_url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(anfrage, timeout=30) as antwort:
        return lies_feed(antwort.read().decode("utf-8"))


# --- Stand -------------------------------------------------------------------

def _stand_pfad() -> Path:
    return ordner() / "stand.json"


def lade_stand(pfad: Path | None = None) -> dict[str, Any]:
    pfad = pfad or _stand_pfad()
    if not pfad.exists():
        return {"kanaele": {}, "videos": {}}
    return json.loads(pfad.read_text(encoding="utf-8"))


def speichere_stand(stand: dict[str, Any], pfad: Path | None = None) -> None:
    pfad = pfad or _stand_pfad()
    zwischen = pfad.with_suffix(".tmp")
    zwischen.write_text(json.dumps(stand, ensure_ascii=False, indent=2), encoding="utf-8")
    zwischen.replace(pfad)


def nimm_auf(stand: dict[str, Any], kanal: Kanal, eintraege: list[Eintrag],
             jetzt: datetime) -> list[Eintrag]:
    """Traegt neue Feed-Eintraege ein und gibt sie zurueck.

    Der erste Abruf eines Kanals markiert alles als gesehen und liefert nichts:
    Der Dienst soll ab jetzt beobachten, nicht die letzten 15 Videos nachholen.
    Shorts werden eingetragen, aber gleich als uebersprungen.
    """
    k = stand["kanaele"].get(kanal.channel_id)
    if k is None:
        stand["kanaele"][kanal.channel_id] = {
            "handle": kanal.handle, "seit": jetzt.isoformat(timespec="seconds"),
            "gesehen": [e.video_id for e in eintraege]}
        return []

    # Ein Video, das vor dem Start schon oeffentlich war, aber erst jetzt im
    # Feed auftaucht (privat -> oeffentlich), gehoert nicht zum Auftrag.
    seit = datetime.fromisoformat(k["seit"]) - timedelta(days=1)
    neu = [e for e in eintraege
           if e.video_id not in k["gesehen"] and e.video_id not in stand["videos"]
           and e.veroeffentlicht >= seit]
    for e in neu:
        stand["videos"][e.video_id] = {
            "kanal": kanal.handle, "titel": e.titel,
            "veroeffentlicht": e.veroeffentlicht.isoformat(),
            "entdeckt": jetzt.isoformat(timespec="seconds"),
            "status": "uebersprungen" if e.short else "wartet",
            "grund": "Short" if e.short else "", "versuche": 0}
    k["gesehen"] = (k["gesehen"] + [e.video_id for e in neu])[-200:]
    return neu


# --- Entscheidung je Video ---------------------------------------------------

@dataclass(frozen=True)
class Entscheidung:
    art: str                       # "los" | "warten" | "ueberspringen"
    grund: str = ""
    transkript: str | None = None  # "youtube" | "asr"


def entscheide(meta: dict[str, Any], conf: dict[str, Any], alter_h: float,
               sprache: str) -> Entscheidung:
    """Was mit einem Video passiert, nur aus den Metadaten von ``yt-dlp -J``."""
    live = meta.get("live_status")
    if live in ("is_live", "is_upcoming", "post_live"):
        return Entscheidung("warten", f"live_status {live}")
    dauer = float(meta.get("duration") or 0)
    if dauer < conf["min_dauer_s"]:
        return Entscheidung("ueberspringen", f"{dauer:.0f} s, kuerzer als {conf['min_dauer_s']} s")
    if dauer > conf["max_dauer_s"]:
        return Entscheidung("ueberspringen", f"{dauer / 3600:.1f} h, laenger als "
                                             f"{conf['max_dauer_s'] / 3600:.1f} h")
    if sprache in (meta.get("automatic_captions") or {}):
        return Entscheidung("los", transkript="youtube")
    if alter_h < conf["warte_auf_untertitel_h"]:
        return Entscheidung("warten", f"noch kein {sprache}")
    return Entscheidung("los", f"kein {sprache} nach {alter_h:.0f} h", transkript="asr")


def naechster_termin(jetzt: datetime) -> datetime:
    """Der erste freie YouTube-Termin im Raster von ``clip veroeffentliche``."""
    v = veroeffentlichen.konfiguration()
    zone = ZoneInfo(v["zeitzone"])
    return veroeffentlichen.zeitplan(
        1, jetzt.astimezone(zone) + timedelta(minutes=v["vorlauf_minuten"]),
        ab=time.fromisoformat(v["ab"]), bis=time.fromisoformat(v["bis"]),
        abstand=timedelta(minutes=v["abstand_minuten"]), zone=zone,
        belegt=veroeffentlichen._geplante_youtube_termine(jetzt))[0]


# --- Werkzeuge ---------------------------------------------------------------

def _umgebung(**extra: str) -> dict[str, str]:
    env = dict(os.environ)
    env["PYTHONPATH"] = str(ROOT / "src")
    env.update(extra)
    return env


def _laufe(befehl: list[str], *, timeout: float | None = None,
           env: dict[str, str] | None = None, eingabe: str | None = None) -> str:
    try:
        r = subprocess.run(befehl, cwd=ROOT, env=env or _umgebung(), input=eingabe,
                           capture_output=True, text=True, timeout=timeout)
    except subprocess.TimeoutExpired as e:
        raise BeobachterFehler(f"{Path(befehl[0]).name}: nach {timeout:.0f} s abgebrochen") from e
    if r.returncode != 0:
        rest = (r.stderr or r.stdout).strip().splitlines()[-3:]
        raise BeobachterFehler(f"{Path(befehl[0]).name}: {' | '.join(rest)}")
    return r.stdout


def _yt_dlp() -> str:
    lokal = ROOT / ".venv" / "bin" / "yt-dlp"
    return str(lokal) if lokal.exists() else "yt-dlp"


def _url(video_id: str) -> str:
    return f"https://www.youtube.com/watch?v={video_id}"


def metadaten(video_id: str) -> dict[str, Any]:
    return json.loads(_laufe([_yt_dlp(), "-J", "--skip-download", _url(video_id)],
                             timeout=120))


def lade(video_id: str, transkript_art: str, conf: dict[str, Any]) -> tuple[Path, Path]:
    """Quelle und Transkript nach ``<work>/quellen/``; Vorhandenes bleibt."""
    quellen = arbeitsverzeichnis() / "quellen"
    quellen.mkdir(parents=True, exist_ok=True)
    muster = str(quellen / f"{video_id}.%(ext)s")
    ingest = einstellungen()["ingest"]
    video = quellen / f"{video_id}.mp4"
    if not video.exists():
        _laufe([_yt_dlp(), "-f", ingest["format_selector"], "--merge-output-format", "mp4",
                "--retries", str(ingest["max_retries"]), "-o", muster, _url(video_id)],
               timeout=3 * 3600)

    if transkript_art == "youtube":
        sprache = einstellungen()["transkript"]["youtube_sub_lang"]
        transkript = quellen / f"{video_id}.{sprache}.json3"
        if not transkript.exists():
            _laufe([_yt_dlp(), "--skip-download", "--write-auto-subs", "--sub-langs", sprache,
                    "--sub-format", "json3", "-o", muster, _url(video_id)], timeout=300)
    else:
        transkript = quellen / f"{video_id}.de-asr.json3"
        if not transkript.exists():
            _laufe([sys.executable, "-m", "videoclipper.cli", "transkribiere",
                    "--video", str(video), "--video-id", video_id,
                    "--modell", str(Path(conf["asr_modell"]).expanduser()),
                    "--ziel", str(transkript)], timeout=4 * 3600)

    for pfad in (video, transkript):
        if not pfad.exists():
            raise BeobachterFehler(f"{pfad.name} fehlt nach dem Laden")
    return video, transkript


def frei_gb() -> float:
    return shutil.disk_usage(arbeitsverzeichnis()).free / 1e9


def mitteilung(text: str, titel: str = "Videoclipper") -> None:
    """macOS-Mitteilung. Scheitert sie, steht der Text trotzdem im Protokoll."""
    def esc(s: str) -> str:
        return s.replace("\\", "\\\\").replace('"', '\\"')
    try:
        subprocess.run(["osascript", "-e",
                        f'display notification "{esc(text)}" with title "{esc(titel)}"'],
                       capture_output=True, timeout=10)
    except (OSError, subprocess.TimeoutExpired):
        pass


# --- Agent -------------------------------------------------------------------

def auftrag(video_id: str, v: dict[str, Any], dauer_s: float, video: Path,
            transkript: Path, transkript_art: str, conf: dict[str, Any],
            ergebnis: Path) -> str:
    vorlage = (CONFIG_DIR / "automat_auftrag.md").read_text(encoding="utf-8")
    asr = ("Das Transkript ist eigene ASR: jedes Clipfenster mit `asr_fenster.py` "
           "zweitmeinen und die bessere Fassung einsetzen." if transkript_art == "asr" else "")
    return vorlage.format(
        kanal=v["kanal"], titel=v["titel"], video_id=video_id,
        dauer_min=round(dauer_s / 60), video=video, transkript=transkript,
        transkript_art="YouTube de-orig" if transkript_art == "youtube" else "eigene ASR",
        clips=conf["clips_pro_video"], ausgabe=ausgabe_ordner(), asr_hinweis=asr,
        arbeit=arbeitsverzeichnis(), ergebnis=ergebnis)


def agent_befehl(conf: dict[str, Any], session_id: str, name: str) -> list[str]:
    """``claude -p`` ohne Rueckfragen. Der Auftrag kommt ueber stdin — die
    Listen-Optionen (``--disallowedTools``) wuerden ihn sonst verschlucken."""
    befehl = ["claude", "-p", "--output-format", "json",
              "--permission-mode", "auto", "--permission-prompts", "none",
              "--strict-mcp-config", "--tools", "Bash,Read,Write,Edit,Glob,Grep",
              "--session-id", session_id, "--name", name,
              "--add-dir", str(arbeitsverzeichnis())]
    soundtracks = Path(einstellungen().get("soundtrack", {}).get("ordner", "")).expanduser()
    if soundtracks.is_dir():
        befehl += ["--add-dir", str(soundtracks)]
    if conf["modell"]:
        befehl += ["--model", conf["modell"]]
    return befehl + ["--disallowedTools", *VERBOTEN]


def clippe(video_id: str, v: dict[str, Any], dauer_s: float, video: Path,
           transkript: Path, transkript_art: str, conf: dict[str, Any]) -> dict[str, Any]:
    """Laesst den Agenten schneiden. Rueckgabe: seine Ergebnisdatei."""
    ergebnis = ordner() / "ergebnis" / f"{video_id}.json"
    ergebnis.parent.mkdir(exist_ok=True)
    ergebnis.unlink(missing_ok=True)
    leer = ordner() / "ohne_schluessel"
    leer.mkdir(exist_ok=True)

    session_id = str(uuid.uuid4())
    v["session"] = session_id
    prompt = auftrag(video_id, v, dauer_s, video, transkript, transkript_art, conf, ergebnis)
    ausgabe = _laufe(agent_befehl(conf, session_id, f"automat {video_id}"),
                     timeout=conf["agent_timeout_min"] * 60, eingabe=prompt,
                     env=_umgebung(VIDEOCLIPPER_SCHLUESSEL=str(leer)))
    protokoll = ordner() / "agent" / f"{video_id}.json"
    protokoll.parent.mkdir(exist_ok=True)
    protokoll.write_text(ausgabe, encoding="utf-8")

    if not ergebnis.exists():
        raise BeobachterFehler("Agent beendet ohne Ergebnisdatei")
    return json.loads(ergebnis.read_text(encoding="utf-8"))


def pruefe_lauf(lauf: Path, video_id: str, basis: Path) -> list[str]:
    """Was gegen den Upload eines Agentenlaufes spricht. Leer heisst: hochladen."""
    try:
        lauf.resolve().relative_to(basis.resolve())
    except ValueError:
        return [f"{lauf} liegt nicht unter {basis}"]
    lauf_json = lauf / "json" / "lauf.json"
    if not lauf_json.exists():
        return [f"{lauf_json} fehlt"]
    fehler = []
    if json.loads(lauf_json.read_text(encoding="utf-8")).get("video_id") != video_id:
        fehler.append(f"lauf.json gehoert nicht zu {video_id}")
    clips = sorted(p.stem for p in (lauf / "mp4").glob("*.mp4"))
    if not clips:
        fehler.append("keine MP4")
    titel_md = lauf / "titel.md"
    if not titel_md.exists():
        fehler.append("titel.md fehlt")
    else:
        titel = veroeffentlichen.lies_titel(titel_md.read_text(encoding="utf-8"))
        ohne = [c for c in clips if not titel.get(c, {}).get("youtube")]
        if ohne:
            fehler.append(f"kein YouTube-Titel fuer {', '.join(ohne)}")
    return fehler


# --- Durchgang ---------------------------------------------------------------

@contextmanager
def sperre() -> Iterator[bool]:
    """Ein Durchgang zur Zeit. Der Dienst startet alle zehn Minuten, ein
    Schnitt dauert Stunden — der naechste Start kehrt dann sofort um."""
    with (ordner() / "sperre").open("w") as f:
        try:
            fcntl.flock(f, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            yield False
            return
        try:
            yield True
        finally:
            fcntl.flock(f, fcntl.LOCK_UN)


def _stempel(melde: Callable[[str], None]) -> Callable[[str], None]:
    return lambda text: melde(f"{datetime.now():%Y-%m-%d %H:%M:%S}  {text}")


def lade_hoch(video_id: str, v: dict[str, Any], melde: Callable[[str], None]) -> None:
    lauf = Path(v["lauf"])
    try:
        r = veroeffentlichen.veroeffentliche(lauf, plattformen=["youtube"],
                                             melde=lambda t: melde(f"  {t.strip()}"))
    except hochladen.HochladeFehler as e:
        v.update(status="upload_offen", grund=str(e))
        melde(f"{video_id}: Upload gescheitert — {e}")
        return
    if r["youtube_offen"]:
        v.update(status="upload_offen", grund=f"{r['youtube_offen']} Clips noch offen")
        return
    termine = sorted(e["youtube"]["termin"] for e in veroeffentlichen.lade_stand(lauf).values()
                     if "youtube" in e)
    erster = datetime.fromisoformat(termine[0]) if termine else None
    v.update(status="geplant", grund="", termine=termine)
    text = (f"{v['kanal']}: {len(termine)} Clips auf YouTube geplant"
            + (f", ab {erster:%a %d.%m. %H:%M}" if erster else "")
            + ". TikTok wartet auf dich.")
    melde(text)
    mitteilung(text)


def bearbeite(video_id: str, v: dict[str, Any], conf: dict[str, Any], jetzt: datetime,
              speichere: Callable[[], None], melde: Callable[[str], None]) -> None:
    if v["status"] == "upload_offen":
        lade_hoch(video_id, v, melde)
        return

    alter_h = (jetzt - datetime.fromisoformat(v["veroeffentlicht"])).total_seconds() / 3600
    # Aufgegeben wird nach der Wartezeit seit dem Entdecken, nicht seit dem
    # Upload: War der Mac zwei Tage aus, ist ein neues Video sonst sofort tot.
    wartet_h = (jetzt - datetime.fromisoformat(v["entdeckt"])).total_seconds() / 3600
    if wartet_h > conf["aufgeben_nach_h"]:
        v.update(status="fehler", grund=f"nach {wartet_h:.0f} h aufgegeben: {v.get('grund', '')}")
        mitteilung(f"{v['kanal']}: {v['titel'][:60]} aufgegeben — {v['grund']}")
        return

    try:
        meta = metadaten(video_id)
    except (BeobachterFehler, json.JSONDecodeError) as e:
        v["grund"] = f"yt-dlp -J: {e}"
        return
    sprache = einstellungen()["transkript"]["youtube_sub_lang"]
    e = entscheide(meta, conf, alter_h, sprache)
    if e.art == "warten":
        v["grund"] = e.grund
        return
    if e.art == "ueberspringen":
        v.update(status="uebersprungen", grund=e.grund)
        melde(f"{video_id}: uebersprungen — {e.grund}")
        return

    if (frei := frei_gb()) < conf["min_frei_gb"]:
        v["grund"] = f"nur {frei:.0f} GB frei"
        mitteilung(f"Beobachter pausiert: nur {frei:.0f} GB frei auf der Platte.")
        return
    termin = naechster_termin(jetzt)
    if termin - jetzt > timedelta(days=conf["max_vorlauf_tage"]):
        v.update(status="uebersprungen", grund=f"Raster voll bis {termin:%d.%m. %H:%M}")
        melde(f"{video_id}: uebersprungen — {v['grund']}")
        return

    v.update(status="in_arbeit", grund=e.grund, transkript=e.transkript)
    speichere()
    melde(f"{video_id}: {v['kanal']} — {v['titel']}  ({meta.get('duration', 0) / 60:.0f} min, "
          f"Transkript {e.transkript})")
    try:
        video, transkript = lade(video_id, e.transkript, conf)
        melde(f"{video_id}: geladen, Agent startet")
        erg = clippe(video_id, v, float(meta.get("duration") or 0), video, transkript,
                     e.transkript, conf)
    except (BeobachterFehler, json.JSONDecodeError) as fehler:
        v["versuche"] = v.get("versuche", 0) + 1
        endgueltig = v["versuche"] >= conf["agent_versuche"]
        v.update(status="fehler" if endgueltig else "wartet", grund=str(fehler))
        melde(f"{video_id}: FEHLER ({v['versuche']}. Versuch) — {fehler}")
        if endgueltig:
            mitteilung(f"{v['kanal']}: Clippen gescheitert — {fehler}")
        return

    if erg.get("status") != "fertig":
        v.update(status="nichts", grund=erg.get("grund", ""))
        melde(f"{video_id}: keine Clips — {v['grund']}")
        mitteilung(f"{v['kanal']}: keine Clips aus {v['titel'][:50]} — {v['grund']}")
        return

    lauf = Path(str(erg.get("lauf", ""))).expanduser()
    if fehler := pruefe_lauf(lauf, video_id, ausgabe_ordner()):
        v.update(status="fehler", grund="; ".join(fehler), lauf=str(lauf))
        melde(f"{video_id}: Lauf nicht hochgeladen — {v['grund']}")
        mitteilung(f"{v['kanal']}: Lauf fertig, aber nicht hochgeladen — {v['grund']}")
        return
    v.update(status="upload_offen", lauf=str(lauf), grund="")
    speichere()
    lade_hoch(video_id, v, melde)


def durchgang(*, probe: bool = False, nur_video: str | None = None,
              melde: Callable[[str], None] = print) -> None:
    melde = _stempel(melde)
    conf = konfiguration()
    with sperre() as frei:
        if not frei:
            melde("Ein anderer Durchgang laeuft noch.")
            return
        jetzt = datetime.now(timezone.utc)
        stand = lade_stand()

        for kanal in kanaele():
            erst = kanal.channel_id not in stand["kanaele"]
            try:
                neu = nimm_auf(stand, kanal, hole_feed(kanal), jetzt)
            except (OSError, ET.ParseError) as e:
                melde(f"{kanal.handle}: Feed nicht erreichbar — {e}")
                continue
            if erst:
                melde(f"{kanal.handle}: beobachtet ab jetzt")
            for e in neu:
                melde(f"{kanal.handle}: neu {e.video_id}{' (Short)' if e.short else ''} {e.titel}")
        speichere_stand(stand)

        offen = sorted((vid for vid, v in stand["videos"].items() if v["status"] in OFFEN),
                       key=lambda vid: stand["videos"][vid]["veroeffentlicht"])
        if nur_video:
            offen = [vid for vid in offen if vid == nur_video]
        if probe:
            for vid in offen:
                v = stand["videos"][vid]
                melde(f"offen {vid} [{v['status']}] {v['kanal']}: {v['titel']}")
            return
        for vid in offen:
            bearbeite(vid, stand["videos"][vid], conf, datetime.now(timezone.utc),
                      lambda: speichere_stand(stand), melde)
            speichere_stand(stand)


def status(melde: Callable[[str], None] = print, anzahl: int = 25) -> None:
    stand = lade_stand()
    for cid, k in stand["kanaele"].items():
        melde(f"Kanal {k['handle']:<20} seit {k['seit'][:16]}")
    videos = sorted(stand["videos"].items(), key=lambda kv: kv[1]["entdeckt"])[-anzahl:]
    if videos:
        melde("")
    for vid, v in videos:
        melde(f"{v['entdeckt'][:16]}  {vid}  {v['status']:<13} {v['kanal']:<18} "
              f"{v['titel'][:45]}" + (f"  — {v['grund']}" if v.get("grund") else ""))

    tiktok = [v for v in stand["videos"].values() if v["status"] == "geplant"
              and not any("tiktok" in e for e in
                          veroeffentlichen.lade_stand(Path(v["lauf"])).values())]
    if tiktok:
        melde("\nTikTok wartet auf dich (Weg B):")
        for v in tiktok:
            melde(f"  {v['kanal']}: {v['titel'][:50]}\n    {v['lauf']}")


# --- Dienst ------------------------------------------------------------------

def plist_pfad() -> Path:
    return Path.home() / "Library" / "LaunchAgents" / f"{LABEL}.plist"


def plist(conf: dict[str, Any]) -> bytes:
    python = ROOT / ".venv" / "bin" / "python"
    protokoll = ordner() / "beobachter.log"
    return plistlib.dumps({
        "Label": LABEL,
        # caffeinate haelt den Mac wach, solange ein Durchgang laeuft — ein
        # Schnitt dauert Stunden, und der Ruhezustand wuerde ihn anhalten.
        "ProgramArguments": ["/usr/bin/caffeinate", "-i",
                             str(python if python.exists() else sys.executable),
                             "-m", "videoclipper.cli", "beobachte"],
        "WorkingDirectory": str(ROOT),
        "EnvironmentVariables": {"PATH": os.environ.get("PATH", "/usr/bin:/bin"),
                                 "PYTHONPATH": str(ROOT / "src")},
        "StartInterval": int(conf["intervall_s"]),
        "RunAtLoad": True,
        "StandardOutPath": str(protokoll),
        "StandardErrorPath": str(protokoll),
    })


def installiere_dienst() -> Path:
    pfad = plist_pfad()
    pfad.parent.mkdir(parents=True, exist_ok=True)
    pfad.write_bytes(plist(konfiguration()))
    domaene = f"gui/{os.getuid()}"
    subprocess.run(["launchctl", "bootout", f"{domaene}/{LABEL}"], capture_output=True)
    subprocess.run(["launchctl", "bootstrap", domaene, str(pfad)], check=True)
    return pfad


def entferne_dienst() -> None:
    subprocess.run(["launchctl", "bootout", f"gui/{os.getuid()}/{LABEL}"], capture_output=True)
    plist_pfad().unlink(missing_ok=True)
