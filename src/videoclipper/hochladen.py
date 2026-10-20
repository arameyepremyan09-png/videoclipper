"""Stage 18 — Hochladen auf YouTube und TikTok.

Schliesst den Kreis vor Stage 16: ``clip poste`` laedt einen fertigen Clip hoch
und traegt ihn danach selbst ins Veroeffentlichungsregister ein.

Nur Standardbibliothek. Die Zugangsdaten liegen NICHT im Repo, sondern in
``~/.config/videoclipper/`` (Ordner ueberschreibbar mit VIDEOCLIPPER_SCHLUESSEL):

    youtube_client.json   OAuth-Client "Desktop-App" aus der Google Cloud Console
    tiktok_app.json       {"client_key": "...", "client_secret": "..."}
    tokens.json           Zugriffs- und Refresh-Token, entsteht durch `clip verbinde`

Einschraenkungen der Plattformen (Stand 2026-10, siehe README):
  * YouTube: videos.insert, Scope youtube.upload, resumable Upload.
  * TikTok:  Content Posting API. Solange die App nicht auditiert ist, landet
    JEDER Direct Post auf SELF_ONLY, und das Konto muss privat sein. Der Modus
    ``entwurf`` (video.upload) legt das Video stattdessen in den Entwuerfen der
    TikTok-App ab; dort wird es von Hand veroeffentlicht.
"""

from __future__ import annotations

import base64
import hashlib
import http.server
import json
import os
import secrets
import time
import urllib.error
import urllib.parse
import urllib.request
import webbrowser
from pathlib import Path
from typing import Any

PORT = 8765
REDIRECT = f"http://127.0.0.1:{PORT}/callback/"

GOOGLE_AUTH = "https://accounts.google.com/o/oauth2/v2/auth"
GOOGLE_TOKEN = "https://oauth2.googleapis.com/token"
# force-ssl braucht videos.update, also das Umplanen schon hochgeladener Videos.
YOUTUBE_SCOPE = ("https://www.googleapis.com/auth/youtube.upload "
                 "https://www.googleapis.com/auth/youtube.force-ssl")
YOUTUBE_VIDEOS = "https://www.googleapis.com/youtube/v3/videos"
YOUTUBE_UPLOAD = "https://www.googleapis.com/upload/youtube/v3/videos"

TIKTOK_AUTH = "https://www.tiktok.com/v2/auth/authorize/"
TIKTOK_API = "https://open.tiktokapis.com"
TIKTOK_SCOPES = "user.info.basic,video.upload,video.publish"

SICHTBARKEIT_TIKTOK = {
    "privat": "SELF_ONLY",
    "freunde": "MUTUAL_FOLLOW_FRIENDS",
    "oeffentlich": "PUBLIC_TO_EVERYONE",
}
SICHTBARKEIT_YOUTUBE = {"privat": "private", "freunde": "unlisted",
                        "oeffentlich": "public"}

# TikTok: Stuecke zwischen 5 und 64 MB, nur das letzte darf groesser sein.
# Bis 64 MB geht die Datei in EINEM Stueck hoch. Gemessen am 2026-10-21: drei
# Stuecke a 10 MB kamen vollstaendig an, der Entwurf blieb aber ueber 15 Minuten
# auf PROCESSING_UPLOAD; dieselbe Datei am Stueck war nach 30 s im Posteingang.
CHUNK = 10 * 1024 * 1024
GANZ_BIS = 64 * 1024 * 1024
PLATTFORMEN = ("youtube", "tiktok")


class HochladeFehler(RuntimeError):
    pass


# --- Zugangsdaten ------------------------------------------------------------

def schluesselordner() -> Path:
    ordner = Path(os.environ.get("VIDEOCLIPPER_SCHLUESSEL")
                  or Path.home() / ".config" / "videoclipper")
    ordner.mkdir(parents=True, exist_ok=True)
    os.chmod(ordner, 0o700)
    return ordner


def _lade_json(name: str) -> dict[str, Any]:
    pfad = schluesselordner() / name
    if not pfad.exists():
        raise HochladeFehler(f"{pfad} fehlt — siehe README, Abschnitt Hochladen.")
    return json.loads(pfad.read_text(encoding="utf-8"))


def _tokens() -> dict[str, Any]:
    pfad = schluesselordner() / "tokens.json"
    return json.loads(pfad.read_text(encoding="utf-8")) if pfad.exists() else {}


def _speichere_token(plattform: str, daten: dict[str, Any]) -> None:
    alle = _tokens()
    alle[plattform] = daten
    pfad = schluesselordner() / "tokens.json"
    tmp = pfad.with_suffix(".tmp")
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        json.dump(alle, f, indent=2)
    os.replace(tmp, pfad)


def verbunden() -> dict[str, bool]:
    t = _tokens()
    return {p: p in t and bool(t[p].get("refresh_token")) for p in PLATTFORMEN}


# --- HTTP --------------------------------------------------------------------

def _anfrage(url: str, *, daten: bytes | None = None, kopf: dict[str, str] | None = None,
             methode: str | None = None, timeout: int = 120):
    req = urllib.request.Request(url, data=daten, headers=kopf or {}, method=methode)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.status, r.headers, r.read()
    except urllib.error.HTTPError as e:
        # 308 kommt bei Google als Fehler an, ist beim Fortsetzen aber normal.
        if e.code == 308:
            return e.code, e.headers, e.read()
        raise HochladeFehler(f"HTTP {e.code} von {url.split('?')[0]}: "
                             f"{e.read()[:600].decode('utf-8', 'replace')}") from None
    except urllib.error.URLError as e:
        raise HochladeFehler(f"Keine Verbindung zu {url.split('?')[0]}: {e.reason}") from None


def _form(url: str, felder: dict[str, str]) -> dict[str, Any]:
    _, _, body = _anfrage(
        url, daten=urllib.parse.urlencode(felder).encode(),
        kopf={"Content-Type": "application/x-www-form-urlencoded"})
    return json.loads(body)


def _json(url: str, koerper: dict[str, Any], token: str) -> dict[str, Any]:
    _, _, body = _anfrage(
        url, daten=json.dumps(koerper).encode(), kopf={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json; charset=UTF-8"})
    return json.loads(body)


# --- OAuth im Browser (Loopback) --------------------------------------------

def _warte_auf_code(auth_url: str, state: str, timeout: int = 300) -> str:
    antwort: dict[str, str] = {}

    class Handler(http.server.BaseHTTPRequestHandler):
        def do_GET(self):
            teile = urllib.parse.urlparse(self.path)
            if teile.path != "/callback/":
                self.send_response(404)
                self.end_headers()
                return
            antwort.update({k: v[0] for k, v in urllib.parse.parse_qs(teile.query).items()})
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.end_headers()
            self.wfile.write("<h3>Verbunden. Du kannst dieses Fenster schliessen.</h3>"
                             .encode())

        def log_message(self, *a):
            pass

    server = http.server.HTTPServer(("127.0.0.1", PORT), Handler)
    server.timeout = 5
    print(f"Browser oeffnet sich. Falls nicht, diese Adresse aufrufen:\n{auth_url}\n")
    webbrowser.open(auth_url)
    ende = time.time() + timeout
    try:
        while "code" not in antwort and "error" not in antwort and time.time() < ende:
            server.handle_request()
    finally:
        server.server_close()

    if "error" in antwort:
        raise HochladeFehler(f"Anmeldung abgelehnt: {antwort['error']} "
                             f"{antwort.get('error_description', '')}")
    if "code" not in antwort:
        raise HochladeFehler("Zeitueberschreitung — keine Antwort aus dem Browser.")
    if antwort.get("state") != state:
        raise HochladeFehler("State stimmt nicht — Anmeldung abgebrochen.")
    return antwort["code"]


def _verifier() -> str:
    return secrets.token_urlsafe(64)[:96]


# --- YouTube -----------------------------------------------------------------

def _youtube_client() -> dict[str, Any]:
    cfg = _lade_json("youtube_client.json")
    c = cfg.get("installed") or cfg.get("web")
    if not c:
        raise HochladeFehler("youtube_client.json: Client-Typ muss 'Desktop-App' sein.")
    return c


def verbinde_youtube() -> None:
    c = _youtube_client()
    verifier, state = _verifier(), secrets.token_urlsafe(16)
    challenge = base64.urlsafe_b64encode(
        hashlib.sha256(verifier.encode()).digest()).rstrip(b"=").decode()
    url = GOOGLE_AUTH + "?" + urllib.parse.urlencode({
        "client_id": c["client_id"], "redirect_uri": REDIRECT,
        "response_type": "code", "scope": YOUTUBE_SCOPE, "state": state,
        "access_type": "offline", "prompt": "consent",
        "code_challenge": challenge, "code_challenge_method": "S256"})
    code = _warte_auf_code(url, state)
    t = _form(GOOGLE_TOKEN, {
        "client_id": c["client_id"], "client_secret": c.get("client_secret", ""),
        "code": code, "code_verifier": verifier, "redirect_uri": REDIRECT,
        "grant_type": "authorization_code"})
    if "refresh_token" not in t:
        raise HochladeFehler(f"Kein Refresh-Token erhalten: {t}")
    _speichere_token("youtube", {
        "access_token": t["access_token"], "refresh_token": t["refresh_token"],
        "ablauf": time.time() + t["expires_in"]})


def _youtube_token() -> str:
    t = _tokens().get("youtube")
    if not t:
        raise HochladeFehler("YouTube nicht verbunden — `clip verbinde youtube`.")
    if time.time() < t["ablauf"] - 60:
        return t["access_token"]
    c = _youtube_client()
    neu = _form(GOOGLE_TOKEN, {
        "client_id": c["client_id"], "client_secret": c.get("client_secret", ""),
        "refresh_token": t["refresh_token"], "grant_type": "refresh_token"})
    t.update(access_token=neu["access_token"], ablauf=time.time() + neu["expires_in"])
    _speichere_token("youtube", t)
    return t["access_token"]


def lade_youtube_hoch(datei: Path, titel: str, beschreibung: str = "",
                      tags: list[str] | None = None, sichtbarkeit: str = "privat",
                      zeit: str | None = None) -> dict[str, str]:
    """Resumable Upload. ``zeit`` (ISO 8601 mit Zeitzone) plant die Freigabe."""
    token = _youtube_token()
    if "#shorts" not in (titel + beschreibung).lower():
        beschreibung = (beschreibung + "\n\n#Shorts").strip()

    status: dict[str, Any] = {
        "privacyStatus": SICHTBARKEIT_YOUTUBE[sichtbarkeit],
        "selfDeclaredMadeForKids": False}
    if zeit:
        # publishAt gilt nur fuer Videos, die bis dahin privat sind.
        status.update(privacyStatus="private", publishAt=zeit)

    meta = {"snippet": {"title": titel[:100], "description": beschreibung,
                        "tags": tags or [], "categoryId": "24"},
            "status": status}
    groesse = datei.stat().st_size
    _, kopf, _ = _anfrage(
        YOUTUBE_UPLOAD + "?uploadType=resumable&part=snippet,status",
        daten=json.dumps(meta).encode(), kopf={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json; charset=UTF-8",
            "X-Upload-Content-Length": str(groesse),
            "X-Upload-Content-Type": "video/mp4"})
    sitzung = kopf["Location"]

    letzter: Exception | None = None
    for versuch in range(5):
        try:
            _, _, body = _anfrage(
                sitzung, daten=datei.read_bytes(), methode="PUT",
                kopf={"Content-Type": "video/mp4", "Content-Length": str(groesse)},
                timeout=600)
            video = json.loads(body)
            return {"id": video["id"], "url": f"https://www.youtube.com/shorts/{video['id']}"}
        except (HochladeFehler, OSError, ValueError) as e:
            letzter = e
            time.sleep(2 ** versuch)
    raise HochladeFehler(f"YouTube-Upload gescheitert: {letzter}")


def plane_youtube_um(video_id: str, zeit: str) -> dict[str, Any]:
    """Freigabezeit eines noch nie veroeffentlichten Videos verschieben.

    videos.update loescht jedes Feld im status-Part, das fehlt — deshalb wird
    der ganze Part mitgeschickt, nicht nur publishAt.
    """
    token = _youtube_token()
    _, _, body = _anfrage(
        YOUTUBE_VIDEOS + "?part=status", methode="PUT",
        daten=json.dumps({"id": video_id, "status": {
            "privacyStatus": "private", "publishAt": zeit,
            "selfDeclaredMadeForKids": False, "embeddable": True,
            "publicStatsViewable": True, "license": "youtube"}}).encode(),
        kopf={"Authorization": f"Bearer {token}",
              "Content-Type": "application/json; charset=UTF-8"})
    return json.loads(body)["status"]


# --- TikTok ------------------------------------------------------------------

def _tiktok_app() -> dict[str, str]:
    return _lade_json("tiktok_app.json")


def _tiktok_redirect(app: dict[str, str]) -> str:
    """TikTok verlangt https. Dann zeigt redirect_uri auf eine statische Seite,
    die den Code an den lokalen Empfaenger (REDIRECT) weiterreicht."""
    return app.get("redirect_uri") or REDIRECT


def verbinde_tiktok() -> None:
    app = _tiktok_app()
    redirect = _tiktok_redirect(app)
    verifier, state = _verifier(), secrets.token_urlsafe(16)
    # TikTok erwartet den SHA-256 hexadezimal, nicht base64url wie Google.
    challenge = hashlib.sha256(verifier.encode()).hexdigest()
    url = TIKTOK_AUTH + "?" + urllib.parse.urlencode({
        "client_key": app["client_key"], "scope": TIKTOK_SCOPES,
        "response_type": "code", "redirect_uri": redirect, "state": state,
        "code_challenge": challenge, "code_challenge_method": "S256"})
    code = _warte_auf_code(url, state)
    t = _form(f"{TIKTOK_API}/v2/oauth/token/", {
        "client_key": app["client_key"], "client_secret": app["client_secret"],
        "code": code, "grant_type": "authorization_code",
        "redirect_uri": redirect, "code_verifier": verifier})
    if "access_token" not in t:
        raise HochladeFehler(f"TikTok hat kein Token geliefert: {t}")
    _speichere_token("tiktok", _tiktok_token_satz(t))


def _tiktok_token_satz(t: dict[str, Any]) -> dict[str, Any]:
    return {"access_token": t["access_token"], "refresh_token": t["refresh_token"],
            "open_id": t.get("open_id"), "scope": t.get("scope"),
            "ablauf": time.time() + t["expires_in"]}


def _tiktok_token() -> str:
    t = _tokens().get("tiktok")
    if not t:
        raise HochladeFehler("TikTok nicht verbunden — `clip verbinde tiktok`.")
    if time.time() < t["ablauf"] - 60:
        return t["access_token"]
    app = _tiktok_app()
    neu = _form(f"{TIKTOK_API}/v2/oauth/token/", {
        "client_key": app["client_key"], "client_secret": app["client_secret"],
        "grant_type": "refresh_token", "refresh_token": t["refresh_token"]})
    if "access_token" not in neu:
        raise HochladeFehler(f"TikTok-Token laesst sich nicht erneuern: {neu}")
    _speichere_token("tiktok", _tiktok_token_satz(neu))
    return neu["access_token"]


def _tiktok_pruefe(antwort: dict[str, Any]) -> dict[str, Any]:
    fehler = antwort.get("error", {})
    if fehler.get("code", "ok") != "ok":
        raise HochladeFehler(f"TikTok: {fehler.get('code')} — {fehler.get('message')}")
    return antwort.get("data", {})


def stuecke(groesse: int, chunk: int = CHUNK,
            ganz_bis: int = GANZ_BIS) -> list[tuple[int, int]]:
    """Byte-Bereiche (von, bis einschliesslich). Der Rest geht ins letzte Stueck."""
    if groesse <= max(chunk, ganz_bis):
        return [(0, groesse - 1)]
    n = groesse // chunk
    return [(i * chunk, (i + 1) * chunk - 1 if i < n - 1 else groesse - 1)
            for i in range(n)]


def poste_tiktok(datei: Path, titel: str, modus: str = "entwurf",
                 sichtbarkeit: str = "privat") -> dict[str, Any]:
    """``entwurf``: Video landet in den Entwuerfen der App (Scope video.upload).
    ``direkt``: Direct Post (video.publish); ohne Audit nur SELF_ONLY."""
    token = _tiktok_token()
    groesse = datei.stat().st_size
    bereiche = stuecke(groesse)
    quelle = {"source": "FILE_UPLOAD", "video_size": groesse,
              "chunk_size": bereiche[0][1] - bereiche[0][0] + 1 if len(bereiche) > 1
              else groesse,
              "total_chunk_count": len(bereiche)}

    if modus == "direkt":
        info = _tiktok_pruefe(_json(
            f"{TIKTOK_API}/v2/post/publish/creator_info/query/", {}, token))
        erlaubt = info.get("privacy_level_options", [])
        wunsch = SICHTBARKEIT_TIKTOK[sichtbarkeit]
        if wunsch not in erlaubt:
            raise HochladeFehler(
                f"TikTok erlaubt fuer dieses Konto nur {erlaubt}, nicht {wunsch}. "
                "Ohne bestandenes Audit ist das nur SELF_ONLY.")
        grenze = info.get("max_video_post_duration_sec")
        init = _tiktok_pruefe(_json(
            f"{TIKTOK_API}/v2/post/publish/video/init/", {
                "post_info": {"title": titel[:2200], "privacy_level": wunsch,
                              "disable_duet": True, "disable_stitch": True,
                              "disable_comment": False},
                "source_info": quelle}, token))
        if grenze:
            init["max_dauer"] = grenze
    else:
        init = _tiktok_pruefe(_json(
            f"{TIKTOK_API}/v2/post/publish/inbox/video/init/",
            {"source_info": quelle}, token))

    with datei.open("rb") as f:
        for von, bis in bereiche:
            f.seek(von)
            stueck = f.read(bis - von + 1)
            _anfrage(init["upload_url"], daten=stueck, methode="PUT", timeout=600, kopf={
                "Content-Type": "video/mp4", "Content-Length": str(len(stueck)),
                "Content-Range": f"bytes {von}-{bis}/{groesse}"})

    return warte_auf_tiktok(init["publish_id"], token)


def warte_auf_tiktok(publish_id: str, token: str, sekunden: int = 300) -> dict[str, Any]:
    ende = time.time() + sekunden
    d: dict[str, Any] = {}
    while time.time() < ende:
        d = _tiktok_pruefe(_json(f"{TIKTOK_API}/v2/post/publish/status/fetch/",
                                 {"publish_id": publish_id}, token))
        if d.get("status") in ("PUBLISH_COMPLETE", "SEND_TO_USER_INBOX"):
            return {"publish_id": publish_id, **d}
        if d.get("status") == "FAILED":
            raise HochladeFehler(f"TikTok: {d.get('fail_reason', 'unbekannter Fehler')}")
        time.sleep(5)
    raise HochladeFehler(f"TikTok verarbeitet noch (Stand {d.get('status')}) — "
                         f"publish_id {publish_id}, spaeter nachsehen.")
