"""Top-5-Referenz sichern: Short laden, Aufbau vermessen, die fuenf Momente ausschneiden.

python werkzeuge/top5_referenz.py <url> [<url> ...]

Der Nutzer liefert laufend Top-5-Shorts, die gut ankommen, und die Momente
darin duerfen uebernommen werden. Je Referenz entsteht:

  <work>/referenz/top5/<id>.mp4 + <id>.de-orig.json3   der Short
  <work>/referenz/top5/<id>.liste.png                  Liste im letzten Bild, zum Ablesen
  <work>/referenz/top5/momente/<id>_platz<k>.mp4       Moment: nur das Videofeld, ohne Liste
  data/referenz/top5/<id>.json                         Verzeichnis, reist mit dem Repo

Gemessen, nicht angenommen (drei HallOfClips-Shorts, 2026-09-16):
- Das Videofeld ist ein scharfes Rechteck auf einem Blur derselben Quelle; seine
  linke Kante reicht senkrecht ueber seine ganze Hoehe.
- Platz 5 steht ab Bild 0, jede weitere Zeile erscheint mit dem Schnitt zum
  naechsten Moment. Die Momentgrenze ist deshalb der Schnitt im Videofeld nahe
  dem Aufdecken, nicht das Aufdecken selbst (gemessen 0.03..0.17 s dahinter).

Beschriftung und Emoji stehen nur im Bild, OCR gibt es auf dem Mac nicht:
`label` bleibt null und wird aus <id>.liste.png von Hand eingetragen. Ein
zweiter Lauf behaelt eingetragene Felder (label, emoji, creator, notiz).

Weicht ein Short vom vermessenen Aufbau ab (keine klaren Panelkanten, nicht
fuenf Listenzeilen, Aufdeckreihenfolge falsch), bricht das Skript mit Grund ab
statt Momente an falschen Grenzen zu schneiden.
"""
import datetime
import json
import re
import subprocess
import sys
from pathlib import Path

import numpy as np

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "src"))
from videoclipper.settings import arbeitsverzeichnis  # noqa: E402
from videoclipper.transcript import lade_json3  # noqa: E402

YTDLP = str(REPO / ".venv" / "bin" / "yt-dlp")
# Shorts haben zwei Tonspuren (en-US synchronisiert, de-DE Original), und
# Format 140 gibt es nur als 140-0 / 140-1. Deshalb die Sprache waehlen.
FORMAT = ("bv*[vcodec^=avc1][height>=1080]+ba[language^=de][ext=m4a]"
          "/bv*[vcodec^=avc1][height>=1080]+ba[ext=m4a]/b")
PLAETZE = 5
BEHALTEN = ("label", "emoji", "creator", "notiz")


def _id(url: str) -> str:
    m = re.search(r"(?:shorts/|v=|youtu\.be/)([\w-]{11})", url)
    if not m:
        raise SystemExit(f"Keine YouTube-ID in {url}")
    return m.group(1)


def _laden(url: str, vid: str, ziel: Path) -> dict:
    info = json.loads(subprocess.run([YTDLP, "--skip-download", "-J", "--no-warnings", url],
                                     capture_output=True, text=True, check=True).stdout)
    if not (ziel / f"{vid}.mp4").exists():
        subprocess.run([YTDLP, "-q", "--no-warnings", "-f", FORMAT, "--merge-output-format", "mp4",
                        "--write-auto-subs", "--sub-langs", "de-orig", "--sub-format", "json3",
                        "-o", str(ziel / f"{vid}.%(ext)s"), url], check=True)
    return info


def _fps_und_groesse(video: Path) -> tuple[float, int, int]:
    aus = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries",
                          "stream=r_frame_rate,width,height", "-of", "json", str(video)],
                         capture_output=True, text=True, check=True).stdout
    s = json.loads(aus)["streams"][0]
    z, n = s["r_frame_rate"].split("/")
    return float(z) / float(n), s["width"], s["height"]


def _staerkste(profil: np.ndarray, lo: int, hi: int) -> tuple[int, float]:
    """Staerkste Kante im Bereich und wie deutlich sie ueber ihrer Umgebung liegt."""
    i = int(np.argmax(profil[lo:hi])) + lo
    umgebung = np.median(profil[max(lo, i - 40):min(hi, i + 40)])
    return i, float(profil[i] / max(umgebung, 1e-3))


def vermessen(video: Path, fps: float, W: int, H: int) -> dict:
    # Durchlauf A, 10 Bilder je Sekunde ueber echte Bildnummern (CLAUDE.md:
    # der fps-Filter laeuft gegen die Zeitachse weg).
    K = max(1, round(fps / 10))
    p = subprocess.Popen(["ffmpeg", "-v", "error", "-i", str(video), "-vf",
                          f"select='not(mod(n\\,{K}))',format=gray", "-vsync", "0",
                          "-f", "rawvideo", "-pix_fmt", "gray", "-"], stdout=subprocess.PIPE)
    gx_summe, zeilen, profil, n = np.zeros((H, W - 1)), np.zeros(H), [], 0
    while len(raw := p.stdout.read(W * H)) == W * H:
        f = np.frombuffer(raw, np.uint8).reshape(H, W).astype(np.int16)
        gx, gy = np.abs(np.diff(f, axis=1)), np.abs(np.diff(f, axis=0))
        gx_summe += gx
        zeilen[:-1] += gy[:, W // 4:3 * W // 4].mean(axis=1)
        profil.append(gx[:, int(W * 0.21):int(W * 0.93)].mean(axis=1))
        n += 1
    p.wait()
    gx_mittel = gx_summe / n
    zeilen /= n
    profil = np.array(profil)

    # Kante bei Index i liegt zwischen Pixel i und i+1. Links/rechts in der
    # unteren Bildhaelfte, wo das Panel sicher liegt.
    spalten = np.zeros(W)
    spalten[:-1] = gx_mittel[H // 2:H - 150].mean(axis=0)
    links, dl = _staerkste(spalten, 0, W // 3)
    rechts, dr = _staerkste(spalten, 2 * W // 3, W - 1)
    # Oben/unten NICHT als staerkste Zeile suchen: die Listenzeilen darueber
    # haben genauso starke waagrechte Kanten (erster Versuch landete auf der
    # Unterkante von Platz 5, y=847 statt 900). Stattdessen: so weit die
    # linke Panelkante senkrecht reicht, dann auf die Zeilenkante verfeinern.
    # Ausserhalb liegt die Kante bei 0.2, innen im Median bei 37 (uYAMGga5wr0);
    # dunkle Bildstellen am Rand druecken sie innen aber stellenweise unter die
    # Haelfte. Deshalb niedrige Schwelle und Luecken bis LUECKE Zeilen.
    LUECKE = 40
    kante = gx_mittel[:, links]
    an = np.flatnonzero(kante > 0.1 * np.median(kante[H // 2:H - 150]))
    lauf = np.split(an, np.flatnonzero(np.diff(an) > LUECKE) + 1)
    lauf = next((r for r in lauf if r[0] <= H // 2 <= r[-1]), None)
    if lauf is None:
        raise SystemExit(f"{video.name}: linke Panelkante x={links} reicht nicht durch die Bildmitte")
    oben_roh, unten_roh = int(lauf[0]), int(lauf[-1])
    oben, do = _staerkste(zeilen, max(0, oben_roh - 20), oben_roh + 20)
    unten, du = _staerkste(zeilen, unten_roh - 20, min(H - 1, unten_roh + 20))
    if min(dl, dr, do, du) < 3:
        raise SystemExit(f"{video.name}: keine klaren Panelkanten (Deutlichkeit links {dl:.1f}, "
                         f"rechts {dr:.1f}, oben {do:.1f}, unten {du:.1f}) — Aufbau weicht ab, "
                         f"von Hand vermessen")
    panel = [links + 1, oben + 1, rechts - links, unten - oben]

    # Textbaender oberhalb des Panels im letzten Bild; die unteren fuenf sind
    # die Liste (Platz 1 oben), alles darueber die Headline.
    ende = profil[-15:, :panel[1]].mean(axis=0)
    baender, y = [], 0
    while y < len(ende):
        if ende[y] > 6:
            y0 = y
            while y < len(ende) and ende[y] > 6:
                y += 1
            if y - y0 > 12:
                baender.append((y0, y))
        y += 1
    if len(baender) < PLAETZE + 1:
        raise SystemExit(f"{video.name}: {len(baender)} Textbaender ueber dem Panel, erwartet "
                         f"Headline + {PLAETZE} Listenzeilen")
    liste, kopf = baender[-PLAETZE:], baender[:-PLAETZE]

    aufgedeckt = {}
    for platz, (a, b) in zip(range(1, PLAETZE + 1), liste):
        s = profil[:, a:b].mean(axis=1)
        # Halber Endpegel, nicht Perzentilmitte: Platz 5 steht ab Bild 0, dort
        # liegt die Perzentilmitte im Rauschen des vollen Pegels.
        idx = int(np.argmax(s > 0.5 * np.median(s[-15:])))
        aufgedeckt[platz] = idx * K / fps
    reihe = [aufgedeckt[k] for k in range(PLAETZE, 0, -1)]
    if (aufgedeckt[PLAETZE] > 1.0 or min(reihe[1:]) < 1.0
            or any(b <= a for a, b in zip(reihe, reihe[1:]))):
        raise SystemExit(f"{video.name}: Aufdeckzeiten nicht 5 -> 1 aufsteigend: "
                         + ", ".join(f"P{k} {aufgedeckt[k]:.1f}s" for k in range(PLAETZE, 0, -1)))

    return {"panel": panel, "headline_zeilen": [list(b) for b in kopf],
            "listenzeilen": {str(k): list(b) for k, b in zip(range(1, PLAETZE + 1), liste)},
            "aufgedeckt": aufgedeckt}


def bildwechsel(video: Path, panel: list[int], fps: float) -> np.ndarray:
    """Durchlauf B, jedes Bild: mittlere Differenz im Videofeld zum Vorbild."""
    x, y, w, h = panel
    S = 160
    p = subprocess.Popen(["ffmpeg", "-v", "error", "-i", str(video), "-vf",
                          f"crop={w}:{h}:{x}:{y},scale={S}:{S},format=gray",
                          "-f", "rawvideo", "-pix_fmt", "gray", "-"], stdout=subprocess.PIPE)
    d, vor = [0.0], None
    while len(raw := p.stdout.read(S * S)) == S * S:
        f = np.frombuffer(raw, np.uint8).astype(np.int16)
        if vor is not None:
            d.append(float(np.abs(f - vor).mean()))
        vor = f
    p.wait()
    return np.array(d)


def momentgrenzen(aufgedeckt: dict, d: np.ndarray, fps: float) -> tuple[list[float], list[str]]:
    """Schnitt im Videofeld nahe jedem Aufdecken. Grenze = erstes Bild des neuen Moments."""
    grenzen, hinweise = [0.0], []
    for platz in range(PLAETZE - 1, 0, -1):
        t = aufgedeckt[platz]
        a, b = max(1, int((t - 0.6) * fps)), min(len(d), int((t + 0.25) * fps))
        i = a + int(np.argmax(d[a:b]))
        ruhe = np.median(d[max(1, a - int(fps)):b])
        if d[i] < 4 * max(ruhe, 0.5):
            hinweise.append(f"Platz {platz}: kein klarer Schnitt bei {t:.2f}s "
                            f"(Differenz {d[i]:.1f} gegen Ruhe {ruhe:.1f}), Aufdeckzeit genommen")
            i = int(round(t * fps))
        grenzen.append(i / fps)
    grenzen.append(len(d) / fps)
    return grenzen, hinweise


def schnitte_im_moment(d: np.ndarray, ab: float, bis: float, fps: float) -> list[float]:
    """Harte Schnitte im Moment, Sekunden ab Momentbeginn.

    Ein Schnitt ist eine einzelne Spitze, schnelle Bewegung ein Block. Gegen
    einen Median gemessen zaehlte die erste Fassung 195 Schnitte in 8 s: Die
    Quellen sind 30 fps im 60-fps-Short, jedes zweite Bild ist ein Duplikat
    mit Differenz 0, und der Median faellt auf null. Gemessen wird deshalb
    gegen das Maximum der Nachbarn; an R8HNyeyCsWE ist das Ergebnis fuer
    Faktor 2.0 bis 3.0 identisch und deckt sich mit ffmpegs Szenenerkennung.
    """
    R = 4
    schnitte = []
    for i in range(int(ab * fps) + 2, min(len(d), int(bis * fps) - 1)):
        nachbarn = np.concatenate([d[max(1, i - R):i], d[i + 1:i + R + 1]])
        if d[i] > 20 and d[i] >= 2.5 * nachbarn.max():
            schnitte.append(round(i / fps - ab, 2))
    return schnitte


def ausschneiden(video: Path, panel: list[int], ab: float, bis: float, fps: float,
                 ziel: Path) -> None:
    """Bilder round(ab*fps) .. round(bis*fps)-1, ueber Bildnummern.

    Zeitbasiert ging es in beide Richtungen schief: Mit -ss ab -t (bis-ab) lag
    das erste Bild des naechsten Moments noch im Ausschnitt (3 von 15), mit auf
    halbe Bilder gelegten Raendern fehlte bei 10 von 15 ein Bild. trim zaehlt
    Bilder ab Dateibeginn — bei 60-s-Shorts kostet das Dekodieren ab 0 nichts.
    """
    x, y, w, h = panel
    w, h = w - w % 2, h - h % 2    # yuv420p, siehe CLAUDE.md "Panelhoehen muessen gerade sein"
    a, b = round(ab * fps), round(bis * fps)
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", str(video),
                    "-vf", f"trim=start_frame={a}:end_frame={b},setpts=PTS-STARTPTS,"
                           f"crop={w}:{h}:{x}:{y}",
                    "-af", f"atrim=start={a / fps:.6f}:end={b / fps:.6f},asetpts=PTS-STARTPTS",
                    "-c:v", "libx264", "-crf", "16", "-preset", "slow", "-pix_fmt", "yuv420p",
                    "-c:a", "aac", "-b:a", "192k", "-movflags", "+faststart", str(ziel)], check=True)


def liste_bild(video: Path, panel: list[int], t: float, ziel: Path) -> None:
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-ss", f"{t:.3f}", "-i", str(video),
                    "-frames:v", "1", "-vf", f"crop=iw:{panel[1]}:0:0", str(ziel)], check=True)


def verarbeite(url: str) -> None:
    vid = _id(url)
    quelle = arbeitsverzeichnis() / "referenz" / "top5"
    (quelle / "momente").mkdir(parents=True, exist_ok=True)
    verzeichnis = REPO / "data" / "referenz" / "top5"
    verzeichnis.mkdir(parents=True, exist_ok=True)

    info = _laden(url, vid, quelle)
    video = quelle / f"{vid}.mp4"
    fps, W, H = _fps_und_groesse(video)
    m = vermessen(video, fps, W, H)
    d = bildwechsel(video, m["panel"], fps)
    grenzen, hinweise = momentgrenzen(m["aufgedeckt"], d, fps)

    j3 = quelle / f"{vid}.de-orig.json3"
    tr = lade_json3(j3, vid) if j3.exists() else None
    if tr is None:
        hinweise.append("kein de-orig-Transkript")

    json_pfad = verzeichnis / f"{vid}.json"
    alt = {}
    if json_pfad.exists():
        alt = {e["platz"]: e for e in json.loads(json_pfad.read_text(encoding="utf-8"))["momente"]}

    momente = []
    for i, platz in enumerate(range(PLAETZE, 0, -1)):
        ab, bis = grenzen[i], grenzen[i + 1]
        datei = quelle / "momente" / f"{vid}_platz{platz}.mp4"
        ausschneiden(video, m["panel"], ab, bis, fps, datei)
        eintrag = {"platz": platz, "reihenfolge": i + 1,
                   "ab": round(ab, 3), "bis": round(bis, 3), "dauer": round(bis - ab, 3),
                   "label": None, "emoji": None, "creator": None, "notiz": None,
                   "schnitte_im_moment": schnitte_im_moment(d, ab, bis, fps),
                   "text": tr.text_zwischen(ab, bis) if tr else None,
                   "datei": str(datei.relative_to(arbeitsverzeichnis()))}
        for feld in BEHALTEN:
            if alt.get(platz, {}).get(feld) is not None:
                eintrag[feld] = alt[platz][feld]
        momente.append(eintrag)

    liste_bild(video, m["panel"], grenzen[-1] - 0.3, quelle / f"{vid}.liste.png")

    views, likes = info.get("view_count"), info.get("like_count")
    daten = {
        "id": vid, "url": f"https://www.youtube.com/shorts/{vid}",
        "kanal": info.get("channel"), "kanal_id": info.get("uploader_id"),
        "titel": info.get("title"), "hochgeladen": info.get("upload_date"),
        "erfasst": datetime.date.today().isoformat(),
        "views": views, "likes": likes,
        "like_rate": round(likes / views, 4) if views and likes else None,
        "dauer": round(len(d) / fps, 3), "fps": fps, "canvas": [W, H],
        "geometrie": {k: m[k] for k in ("panel", "headline_zeilen", "listenzeilen")},
        "momente": momente,
    }
    json_pfad.write_text(json.dumps(daten, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    print(f"{vid}  {daten['kanal']}  {views} Views  {daten['titel']}")
    print(f"  Panel {m['panel']}")
    for e in momente:
        print(f"  Platz {e['platz']}  {e['ab']:6.2f}-{e['bis']:6.2f}s ({e['dauer']:5.2f}s, "
              f"{len(e["schnitte_im_moment"])} Schnitte)  {(e['text'] or '')[:60]}")
    for h in hinweise:
        print(f"  ! {h}")
    offen = [e["platz"] for e in momente if e["label"] is None]
    if offen:
        print(f"  Beschriftung offen fuer Platz {offen}: {quelle / (vid + '.liste.png')}")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        raise SystemExit(__doc__)
    for u in sys.argv[1:]:
        verarbeite(u)
