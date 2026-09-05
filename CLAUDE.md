# Videoclipper

Eigene Short-Form-Clipping-Pipeline: langes Video rein, fertige 9:16-Shorts raus.
Kontrollierbare Alternative zu OpusClip.

**Architekturdokument (immer zuerst lesen):**
https://claude.ai/code/artifact/f219d5f4-ee82-4f8e-836e-b2bec93de7f5

Es enthält die fünfzehn Stages, das EditPlan-Schema, die Materialprofile, Templates,
das Kostenmodell und die Tabelle aller getroffenen Entscheidungen. Architekturfragen
werden dort nachgelesen und dort aktualisiert, nicht neu verhandelt.

## Material

- **Zielmaterial:** GTA-6-Content. Existiert noch nicht (Stand September 2026).
- **Testfeld:** deutscher Reaction-/OME.TV-Content von Coachlim, Quelle sind fremde
  YouTube-Videos.
- Ausgabe: TikTok, Reels, YouTube Shorts. Betrieb täglich, möglichst automatisiert.

Das Briefing sprach von GTA, das Referenzmaterial ist Reaction-Streaming. Beides gilt:
Reaction ist das Testfeld, GTA das Ziel.

## Layout ist nicht statisch — gemessen am 2026-09-04

Das Blueprint nimmt an, die Boxen seien ueber ein Video statisch und ein Profil
reiche deshalb ohne Detektion. **Fuer dieses Material stimmt das nicht.** Beide
gepruefte Videos wechseln im Sekundenbereich zwischen Layouts. Drei sind
vermessen, jeweils ueber 10-14 Frames gemittelte Boxkanten:

| Layout | Quelle | Boxen (x, y, w, h) | Anteil |
|---|---|---|---|
| `REACT` | wxCFBR1_3to | TikTok-Player `[563,103,513,913]` (9:16), Creator-Cam `[1228,691,692,389]` (16:9) | 45 % |
| `GAME` | LnWKgVfcMMQ | Facecam `[1415,0,505,284]` (16:9), Spielfeld `[0,0,1415,1080]` | 95 % |
| `SOLO` | beide | Vollbild-Cam 1920x1080, Creator bei x&nbsp;≈&nbsp;960 | 55 % / 5 % |

Konsequenz fuer die Architektur: Der Modus ist ein **Signal pro Zeitpunkt**
(Stage 04), kein fester Profilwert. Ein Materialprofil beschreibt deshalb
mehrere Modi plus eine Erkennungssignatur; das Template haengt am Modus, nicht
nur am Profil. Clipgrenzen duerfen nie ueber einem Layoutwechsel liegen — die
Analyse legt dafuer `modus_laeufe` im Artefakt ab.

Erkannt wird ueber eine statische Kante, die es nur im Speziallayout gibt:
die rechte Playerkante bei `REACT` (gemessen 48..190 gegen 0,6..7 bei `SOLO`),
die linke Facecam-Kante bei `GAME` (17..21 gegen 0,6). Beide trennen sauber.

`COACHLIM_OMETV` passt auf keines der beiden Videos. Es bleibt unveraendert im
Repo, ist aber fuer dieses Material nicht anwendbar.

## Leitprinzipien

1. **Die AI entscheidet WAS, der Code entscheidet WIE.** Das Modell liefert nur
   strukturiertes JSON (welcher Moment, welche Länge, welcher Hook, welches Template).
   Nie Geometrie, nie Filterketten, nie FFmpeg-Argumente, nie ausführbare Strings.
2. **Jede Stage ist eine reine Funktion JSON → JSON mit content-addressed Cache.**
   Gleicher Input-Hash, Ergebnis aus dem Cache. Ohne das kostet jede Stiländerung
   den vollen Pipeline-Durchlauf.
3. **Nur zwei Schichten dürfen materialabhängig sein:** *Materialprofil* (Geometrie
   der Quelle) und *Template* (Zielkomposition), beide als YAML. Der Wechsel auf
   GTA 6 ist dann das Schreiben zweier Konfigurationsdateien, kein Umbau.

## Stack

Python 3.12 komplett, Umgebung über `uv`. FFmpeg als Subprozess. SQLite für Jobstate.
Kein Docker, kein Node, kein Postgres, kein Redis, kein Cloud-Storage — erst wenn eine
zweite Maschine dazukommt.

## Plattform-Abhängigkeiten

Die Pipeline läuft auf beiden Rechnern des Nutzers. Genau drei Stellen sind
plattformabhängig und gehören deshalb in die Konfiguration, nie fest in den Code:

| Stelle | Windows-Desktop | MacBook Air M4 |
|---|---|---|
| Encoder | `libx264` (kein NVENC; `h264_amf` nur für Previews) | `h264_videotoolbox` |
| ASR | CPU-only, langsam | MLX / whisper.cpp mit Metal, deutlich schneller |
| Arbeitsverzeichnis | `F:\` (C: hat nur ~80 GB frei) | externes Volume, interner Speicher ist knapp |

Windows-Desktop: Ryzen 5 5600X, Radeon RX 580, 16 GB. **Kein CUDA, kein ROCm** —
Empfehlungen, die eine NVIDIA-Karte voraussetzen, sind hier falsch.
MacBook Air M4: lüfterlos, drosselt bei längerer Dauerlast.

## Gemessene Fallstricke

- **yt-dlp wählt sonst AV1.** Format-Selektor auf `vcodec^=avc1` zwingen — die RX 580
  hat kein AV1-Hardware-Decode. Auf dem M4 unkritisch.
- **`--download-sections` ist unbrauchbar langsam** (über 7 Minuten für 2 Sekunden).
  Immer das ganze Video laden und lokal schneiden.
- **FFmpeg `drawtext` segfaultet** auf dem Windows-Rechner, weil fontconfig keine
  Konfigurationsdatei findet. Textpfad läuft über ASS/libass mit explizitem `fontfile`.
- **TikTok blockt yt-dlp und stellt ein Slider-CAPTCHA.** Als Quelle unbrauchbar,
  CAPTCHAs werden nicht umgangen. YouTube-Shorts als Ersatz nutzen.
- **YouTube-Transkript `de-orig` im `json3`-Format** liefert Offsets pro Wort, sauberes
  Deutsch mit Satzzeichen und `[gelächter]`-Marker. Primäre Transkriptquelle, eigene
  ASR nur als Fallback. Vorsicht: die Rolling-Window-Struktur (`wWinId`/`aAppend`)
  erzeugt bei naivem Parsen Duplikate.
- **`[gelächter]` ist nicht verlässlich vorhanden.** wxCFBR1_3to hat 9 Marker,
  LnWKgVfcMMQ **null**. Wo sie fehlen, muss der Lacher-Detektor aus der Lautheit
  kommen; das Materialprofil gewichtet `lachmarker` dann auf 0.
- **yt-dlp braucht `--extractor-args "youtube:player_client=web_embedded"`.**
  Der Default lief reproduzierbar nach ~10 MB in HTTP 403; `android_vr` extrahiert
  zwar, bricht beim Download aber ebenso ab. Mit `web_embedded` laufen 1080p-avc1
  vollständig durch.
- **Ein globaler Lautheitsschwellwert taugt hier nicht.** Ein Reaction-Streamer ist
  fast durchgehend laut — die Fenster verschmelzen dann zu wenigen Blöcken über
  Minuten (gemessen: 5 Kandidaten, einer davon 382 s). Stage 05 pflückt deshalb
  lokale Maxima mit erzwungenem Mindestabstand.
- **FFmpegs `fps`-Filter läuft gegen die echte Zeitachse weg.** Beim Abtasten des
  Layouts lagen die Frames um zig Sekunden daneben, obwohl `showinfo` saubere
  `pts_time` meldete. Abgetastet wird deshalb über echte Bildnummern
  (`select='not(mod(n,K))'`), das ist driftfrei.
- **`crop` vor `format=gray` rundet ungerade Kantenmaße still ab** (5 wird zu 4)
  und verschiebt damit jeden Reshape. `format=gray` gehört vor den Crop.
- **Panelhöhen müssen gerade sein.** In yuv420p rundet der Scaler jede ungerade
  Höhe still ab; 607+1313 ergab eine Bühne von 1918 statt 1920 px. Stage 09 prüft
  das jetzt und bricht ab, statt es dem QC zu überlassen.

## Look

Statische Headline pro Clip, kein Karaoke — aus dem Referenzmaterial gemessen, nicht
angenommen. Anton (OFL, kommerziell frei), Versalien, weiß mit dickem schwarzem Rand,
bei `OME_STACK` auf der Naht zwischen den beiden Panels.

**Renderpfad weicht vom Blueprint ab.** Der FFmpeg-Build auf dem MacBook hat weder
libass noch drawtext (kein `--enable-libass`, kein `--enable-libfreetype`) — der
vorgesehene ASS-Pfad ist dort nicht verfügbar. Weil die Headline über die volle
Cliplänge pixelgleich steht, ist ein einzelnes PNG funktional dasselbe wie ein
einzelnes ASS-Event, und es hängt an keiner Buildoption. Templates tragen dafür
`renderer: png_overlay`.

**Inhalt wird vollständig gezeigt, nicht beschnitten.** Inhaltspanels laufen mit
`passung: einpassen`: Seitenverhältnis bleibt, die Reste tragen einen Blur der
eigenen Quelle. Einzige bewusste Ausnahme ist die Spielfeldzone bei `GAME`, die an
der Facecam-Kante endet — rechts davon liegt zwar Spielfläche, sie ist aber
durchgehend von Facecam und Chat überdeckt.

## Bewertungssystem — Stages 15-17, gemessen am 2026-09-05

Der Blueprint sieht das unter "Retention-Feedback (v3)" vor und nennt als Risiko
"Ranking ohne Ground Truth". Das ist diese Schicht: Sie schliesst den Kreis vom
gerenderten Clip zurueck zur Selektion.

| Stage | Modul | Aufgabe |
|---|---|---|
| 15 | `forecast.py` | Prognose vor dem Posten: Hook, Dauer, Payoff, Postzeit, Thema |
| 16 | `publish.py` | Veroeffentlichungsregister, A/B-Zuweisung |
| 17 | `collect.py` / `scoring.py` | Messwerte holen, Performance-Score |

Daten liegen als JSONL in `data/performance/` — nicht in SQLite. Sie wandern mit
dem Repo auf beide Rechner und muessen im Diff lesbar sein; eine Binaerdatei
waere dort ein Merge-Konflikt pro Tag. SQLite bleibt fuer den Jobstate.

### Was die Plattformen hergeben — gemessen, nicht angenommen

| | Views | Likes | Kommentare | Shares | Saves | Watchtime |
|---|---|---|---|---|---|---|
| TikTok | ja | ja | ja | ja (`repost_count`) | ja (`save_count`) | nein |
| YouTube | ja | meist | selten | nein | nein | nein |
| Instagram | **nichts** | | | | | |

**TikTok gibt per yt-dlp ohne Login vollstaendige Engagement-Zahlen heraus** —
`--flat-playlist -J` auf das Profil reicht, inklusive Shares und Saves. Das ist
ungewoehnlich und die belastbarste Datenquelle des Systems. Der Extractor warnt
zwar wegen fehlender Impersonation, liefert aber trotzdem.

**Instagram ist nicht abrufbar.** yt-dlp meldet den Extractor als broken,
WebFetch bekommt nur den Seitentitel. Alle Instagram-Werte kommen per
`clip trage-nach`.

**Watchtime, Completion-Rate und Follows gibt keine der drei heraus.** Sie
tragen zusammen 60 % des Scores und muessen aus dem Creator-Center nachgetragen
werden. Ohne sie meldet jede Bewertung `abdeckung 0.40` und gilt als nicht
belastbar — das ist Absicht, keine Schwaeche.

### Kleine Fallzahlen sind der Hauptfeind

**Gemessen beim ersten Lauf:** Ein YouTube-Short mit 4 Views und 1 Like ergibt
eine Like-Rate von 25 % und stand damit auf **Platz 1 von 10** — vor einem
TikTok mit 1021 Views und 6,7 %. Eine Rate aus vier Beobachtungen ist Rauschen.

Zwei Gegenmittel, beide in `config/scoring.yaml`:

1. **Glaettung** zum Benchmark-Mittelwert, gewichtet mit den Views
   (`prior_views: 150`). Aus 25 % werden 4,1 %; die 6,7 % des grossen Posts
   bleiben bei 6,45 %.
2. **Unter `min_views_fuer_urteil` wird kein Score angezeigt**, sondern ein
   Strich. Wo kein Urteil moeglich ist, gehoert keine Zahl hin.

### Duplikatsdrosselung — kein Doppelpost als A/B-Test

Von sieben TikToks am 2026-09-04 kamen fuenf auf 905-1021 Views und zwei auf
**2 bzw. 4**. Einer der beiden ist derselbe Clip, der auch auf YouTube liegt;
der andere traegt einen fremden Sound (`original sound - pranksforlife`). Das
sieht nach Duplikats- oder Audioerkennung aus.

Konsequenz: Eine A/B-Variable wird ueber **mehrere verschiedene Clips**
randomisiert, nie durch zweimaliges Hochladen desselben Clips. `doppelpost_erlaubt`
steht auf `false`.

### Der Zielkonflikt mit Tier A

Aus denselben sieben Posts, bei praktisch identischer Reichweite:

| Dauer | Views | Like-Rate |
|---|---|---|
| 27 s | 1021 | **6,66 %** |
| 55 s | 967 | 3,41 % |
| 69 s | 907 | 1,87 % |
| 68 s | 920 | 1,20 % |
| 68 s | 905 | 0,55 % |

Sieben Posts eines einzigen Tages sind kein Beweis — Uhrzeit und Thema
variieren mit. Aber die Spanne ist zu gross, um sie zu ignorieren: **Tier A
(>63 s fuer Creator Rewards) koennte mehr Reichweite kosten, als die Auszahlung
einbringt.** Das Experiment `laenge_kurz_vs_tier_a` ist dafuer angelegt und
laeuft; die Altdaten zaehlen nicht mit, weil sie nicht randomisiert entstanden.

### A/B-Tests ohne p-Werte

Bei fuenf Posts pro Arm liefert ein Signifikanztest entweder nichts oder
Scheingenauigkeit. Stattdessen Beta-Posteriors mit Jeffreys-Prior, Monte Carlo
mit festem Seed: lesbar ab dem ersten Datenpunkt, und die Ausgabe nennt, wie
viele Views pro Arm der beobachtete Effekt noch braucht. Entschieden wird ab
85 % statt 95 % — bei diesen Fallzahlen wuerde 95 % nie erreicht und der Test
bliebe folgenlos.

### Kalibrierung

Die Startgewichte sind **Annahmen** und in `scoring.yaml` als solche markiert.
`clip kalibriere` ersetzt sie durch die eigenen Perzentile und schreibt nach
`config/scoring.kalibriert.yaml` — dasselbe Overlay-Muster wie
`settings.toml`/`local.toml`. Die handgepflegte Datei bleibt unberuehrt, das
Overlay ist loeschbar.

Bis dahin gibt jede Prognose `konfidenz 0.2` aus. Noetig sind 8 Posts fuer die
Benchmarks, 25 fuer die Dauerkurve, 30 ueber mindestens 6 verschiedene Stunden
fuer die Postzeit. **Stand 2026-09-05: 10 Posts, alle unter 24 h alt, keiner
kalibrierbar.**


## Monetarisierung

Tier A ist alles über 63 Sekunden gerenderter Dauer (TikTok Creator Rewards verlangt
*über* eine Minute, nicht exakt 60 s). Tier B bleibt unter 60 s und wird **nie**
künstlich gestreckt. QC misst die fertige Datei mit ffprobe. Der Schwellwert steht in
der Konfiguration, weil sich Programmbedingungen ändern.
