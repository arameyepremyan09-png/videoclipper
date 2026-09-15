# Arbeitsstand — hier weitermachen

Stand 2026-09-15. Diese Datei ist die Uebergabe an einen neuen Chat: was
laeuft, was offen ist, mit welchen Befehlen und Werkzeugen gearbeitet wird.
Architektur und Befunde stehen in [CLAUDE.md](CLAUDE.md), die Auftragslage des
Nutzers in [SCHNITTREGELN.md](SCHNITTREGELN.md). Beide gelten zuerst.

## Offene Auftraege

### 1. gRvhvBJExEE — 10 Clips, Entwurf gerendert, Korrektur offen

"COACH RUFT SEINEN VATER AN WEIL ALBERT EINSTEIN ALBANER IST", TikTok
reaction #22, Coachlim Reactions, 1020.5 s. Auftrag des Nutzers: "Erstelle 10
Clips". Layoutbefunde: CLAUDE.md, Nachtrag 2026-09-13 "TikTok-Reaction #22".

| Datei | Stand |
|---|---|
| `data/selections/gRvhvBJExEE.json` | Plan mit 10 Clips (Teaser + Hauptteil), im Repo |
| `config/profiles/coachlim_tiktok_web.yaml` | Profil, im Repo |
| `data/artifacts/whisper_gRvhvBJExEE.txt` | whisper.cpp-Zweitmeinung aller 10 Fenster |
| `data/korrekturen/gRvhvBJExEE.json` | **fehlt noch** |
| Entwurfslauf | `~/videoclipper/clips/2026-09-14_09-13-40` (lokal) |

Befunde aus dem Entwurf (Grenzkontrolle + Cues), noch nicht behoben:

- `_001` Hauptteil endet bei 649.55 in "So und da kam mir keiner was". Hinter
  "Garantie." liegt 648.7-649.15 eine Luecke bei -40 dB, `snappe` nimmt sie
  nicht. Ende neu legen (siehe CLAUDE.md, AbuGoku-Nachtrag: Ende ueber das
  Wort davor, der Pegel zieht nur nach vorn).
- `_004` Ende 882.63 nimmt den Anfang von "Quelle" (882.28) mit. Ende so
  legen, dass "Sache." (881.84-~882.2) ganz drin ist und "Quelle" nicht.
- `_006` (Merkel, REACT_STACK): erster Cue des Hauptteils ist der Fetzen
  "gut." (0.2 s, aus "Ja, gut." vor dem Start) — Start spaeter verankern
  (z. B. auf "schau" 938.44). Teaser-Ende 958.07 pruefen, ob "vermisse" ganz
  ist. Die Follow-Szene (18.4-21.4 s) liegt auf dem Punch-in bei 21.2 s.
- `_007` Follow-Szene (18.6-21.6 s) liegt auf dem Punch-in bei 18.7 s.
- `_009` Ende 444.54 nimmt "Scha-" von "Schaukelt" (444.48) mit; die Pointe
  soll vor der zweideutigen Rueckfrage enden. Ende auf ~444.3 (gewuenschtes
  Ende 444.2 snappt auf "und" 443.96 + 0.35 s).
- `_010` Teaser-Ende 41.63 enthaelt leises "Nein, nein" ohne Untertitel —
  nach "laeuft." enden. Erster Cue des Hauptteils "gehe mal rein die TikTok
  Reactions." ohne "Ich" (Korrektur).
- Untertitel: Korrekturdatei gegen `whisper_gRvhvBJExEE.txt` schreiben. Bekannt:
  "K luegt" -> "KI luegt", "anim" -> "an" bzw. "an den Stream", "Ist nicht
  Dieb" -> "Ist nicht deep", "Kuschlo" -> "Kuschler", "Mit falsch pass" ->
  "Mit falschem Pass", "Was sichte quellen?" -> "Wasserdichte Quellen?",
  "Voiceman" -> "Voicemail", "gegattoos?" -> "Gigant-Tattoos?", "Freesty" ->
  "Freestyle", "Ich brauche ih in mein Discord" -> "Ich brauche ihn in meinem
  Discord", "Fck" -> "***". Jede Regel muss in EINEN Cue passen — die Cues des
  Entwurfs stehen in `json/*.editplan.json` unter `resolved.untertitel`.
- Pruefbogen des Entwurfs noch nicht angesehen (Untertitel auf Gesichtern,
  Punch-in, REACT_STACK-Beschnitt beim Merkel-Clip).

Danach: finaler Lauf MIT Schnittpruefung, Grenzkontrolle, Pruefbogen,
Commit, Push, die 10 MP4 mit SendUserFile schicken (ueber 30 MiB erreichen
das Handy nicht, nur die Desktop-App).

### 2. SBNhQNelfqA — Krimi-Storys, pausiert

"ICH REAGIERE AUF DIE KRIMI STORYS VON MEINEN ZUSCHAUERN 💀", Coachlim,
1731 s. Der Nutzer hat es zugunsten von gRvhvBJExEE zurueckgestellt; ob noch
gewuenscht, vorher fragen. Video und Transkript liegen lokal in
`~/videoclipper/quellen/`, das Transkript zusaetzlich unter
`data/artifacts/sub_SBNhQNelfqA.de-orig.json3`. Kein Plan, kein Profil.

Bild: fast durchgehend Coach allein im selben lila Zimmer wie bei
gRvhvBJExEE (aber anders sitzend, Gesicht bei x ~900 — Fokus neu messen),
dazu eine Dokumentansicht (schwarzer Grund, Brief mittig, Cam oben rechts)
um 583-657 s. Zuschauer erzaehlen am Telefon ihre Taten "in GTA".
Transkript hat Marker ([gelächter], [schreien]).

Kandidaten, am Kontaktbogen und Transkript gesichtet:

| Stelle | Inhalt | Lacher |
|---|---|---|
| 325-470 s | Einbruch in die Schule, Hauptschulpruefung fotografiert, trotzdem eine Zwei. "Du warst sogar zu dumm zum Abschreiben?", "ich dachte Abitur", "Nicht mal Pestalozzi gibt solche Storys", "Was war daran smart?", 448-468: "Hast du dir die Schloesser deiner Schule schon angeschaut?" | [gelächter] 455, 461; Bild 462.5 |
| 583-657 s | Strafanzeige "Angriff auf Vollstreckungsbeamte", Roller mit 120 km/h: "Welchen asiatischen Chip hast du benutzt?" - "Mein Cousin" - "Ist dein Cousin Dr. Doofenshmirtz?" - "Aus Ankara ist er gekommen." - "Ich bin tot." | [gelächter] 600, 606, 634, 644, 648; Bild 600-603 |
| 737-817 s | "Haettest du die Klaukuenste mal im Deutschunterricht eingesetzt, bisschen Rechtschreibung geklaut", zwei Jahre Bewaehrung, "vier ist weniger als fuenf" | [schreien] 807 |
| 1558-1710 s | Bayerische Polizei: "Kann es sein, dass Sie gar keinen Fuehrerschein haben?", "mein Vater muss morgen arbeiten", Rock and Roll, Linkin Park, "ich mache jetzt 'The End' an, weil ich bin jetzt am Ende" - der Polizist lacht mit | [gelächter] 1569, 1644, 1670; Bild 1667-1699 |

### 3. Ausgeliefert, Rueckmeldung des Nutzers steht aus

- 0-OqdAjLq_0 (Therapiestunde mit Eli), 5 Clips, 2026-09-11
- 8haLC71kEDg (Among Us bei EliasN97), 5 Clips, 2026-09-12
- OUR-LdR97fE (Koefte-Vlog bei AbuGoku), 5 Clips, 2026-09-13

## Befehle

Alles aus dem Repo-Ordner. Das venv des Repos laeuft mit `PYTHONPATH=src`
(die versteckte `.pth` ist in CLAUDE.md unter "Gemessene Fallstricke"
beschrieben). `uv run` legt ein `uv.lock` an — vermeiden oder nicht committen.

```bash
# Tests
PYTHONPATH=src .venv/bin/python -m pytest -q

# Quelle: erst Untertitel pruefen, dann laden (Default-Client, Stand 2026-09-13)
.venv/bin/yt-dlp --list-subs --skip-download "https://www.youtube.com/watch?v=ID"
cd ~/videoclipper/quellen && ~/Desktop/VideoClipper/repo/.venv/bin/yt-dlp -f "299+140" --merge-output-format mp4 -o "ID.%(ext)s" "URL"
cd ~/videoclipper/quellen && ~/Desktop/VideoClipper/repo/.venv/bin/yt-dlp --skip-download --write-auto-subs --sub-langs de-orig --sub-format json3 -o "ID.%(ext)s" "URL"

# Rendern (mit Schnittpruefung; --ohne-schnittpruefung nur mit Grund)
PYTHONPATH=src .venv/bin/python -m videoclipper.cli rendere --plan data/selections/ID.json \
  --video ~/videoclipper/quellen/ID.mp4 --transkript ~/videoclipper/quellen/ID.de-orig.json3 \
  --video-id ID --profil PROFIL --ausgabe ~/videoclipper/clips

# whisper.cpp-Zweitmeinung fuer ein Fenster
ffmpeg -v error -ss 600 -t 50 -i ~/videoclipper/quellen/ID.mp4 -vn -ac 1 -ar 16000 /tmp/x.wav
whisper-cli -m ~/videoclipper/models/ggml-large-v3-turbo-q5_0.bin -l de -bs 5 -f /tmp/x.wav
```

Lokale Pfade (nicht im Repo): Quellen `~/videoclipper/quellen/`, Laeufe
`~/videoclipper/clips/<zeitstempel>/{mp4,json,png}`, Modelle
`~/videoclipper/models/`.

## Werkzeuge in `werkzeuge/`

Handgeschriebene Pruefskripte, die jeden Lauf begleiten. Aufruf aus dem
Repo-Ordner mit `PYTHONPATH=src .venv/bin/python werkzeuge/<skript>`.

| Skript | Zweck |
|---|---|
| `grenzkontrolle.py <lauf> <video> <json3>` | 50-ms-Pegel und Woerter an jeder Schnittgrenze (Teaser und Hauptteil); ein Schnitt gehoert in ein Tal, nicht ins Wort |
| `pruefbogen.py <lauf> <ziel.png>` | je Clip Standbilder an Anfang, Punch-in, Rueckschnitt, Follow-Szene, Ende |
| `pegel10.py <id> name:von:bis ...` | 10-ms-Pegel mit Woertern — findet die Luecke zwischen zwei Woertern |
| `laute.py <id> name:von:bis ...` | 0.1-s-Pegel mit laufendem Wort — Lachen ist laut und wortlos |
| `kontakt.py <video> <ziel.png> <t1> <t2> ...` oder `--alle <von> <bis> <n>` | Kontaktbogen, Zeit in jeder Kachel |
| `kanten.py <video> <von> <bis> <n>` | persistente Kanten: gibt es Boxen im Layout? |
| `modus_serie.py <video> <K> <ziel.npz>` | Kante x=1076 und Flaechenhelligkeit alle K Bilder |
| `lila_serie.py <video> <K> <ziel.npz>` | Fullcam ueber Farbe (Blau - Gruen), fuer Coachs lila Zimmer |

## Ablauf je Video, wie er sich bewaehrt hat

1. `--list-subs`, dann Video (1080p avc1) und `de-orig`-json3 laden.
2. Transkript lesbar machen, Kandidaten **lesen** (Regel 1c: die Zeile muss
   allein komisch sein). Marker fehlen oft — dann am Standbild pruefen, ob
   gelacht wird (`kontakt.py` genau an der Pointe).
3. Layout: `kanten.py` + Kontaktbogen ueber das ganze Video; bei wechselnden
   Bildern eine Zeitreihe (`modus_serie.py`, `lila_serie.py`). Clipgrenzen nie
   ueber einen Layoutwechsel — ausser in `FULLCAM_169`, das jedes Bild ganz zeigt.
4. Profil anlegen oder bestaetigen, Template nach Regel 2.
5. Plan schreiben: Teaser (2-8 s, Pointe darin) + Hauptteil, zusammen >= 30 s,
   Headline nach Regel 3 (kurz, keine Satzzeichen, Emoji-Paar).
6. Entwurf rendern, dann `grenzkontrolle.py`, Cues aus den EditPlans,
   `pruefbogen.py`. Grenzen im Wort mit `pegel10.py` nachmessen.
7. whisper.cpp-Zweitmeinung, Korrekturdatei gegen die Cues des Entwurfs.
8. Final rendern, erneut pruefen, committen, pushen, ausliefern.

## Repo

Alles liegt auf `main` und ist gepusht. Alle lokalen und entfernten Branches
sind in `main` enthalten; `stash@{0}` ist alter mw4-Stand, ebenfalls
enthalten. Loeschen nur auf Wunsch des Nutzers. Der Nutzer sagt "Stash" fuer
Branch.
