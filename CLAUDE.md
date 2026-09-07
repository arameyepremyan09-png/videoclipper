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

### Nachtrag 2026-09-05: statisch kommt auch vor

Zwei weitere Videos vermessen, und beide widerlegen die Verallgemeinerung oben.
**Ob ein Video das Layout wechselt, ist eine Eigenschaft des Videos, keine des
Kanals** — gemessen werden muss trotzdem jedes Mal.

| Profil | Quelle | Befund |
|---|---|---|
| `COACHLIM_OMETV_SPLIT` | utB7GTrmLYY | Splitscreen `[0,0,952,798]` / `[953,0,952,798]`, Naht bei y=799. Ueber 420 Messpunkte **100 %** — nur das Schwarzbild bei t=0 faellt raus. |
| `COACHLIM_COUCH` | 4ubrGJLb4FQ | Keine Boxen. Feststehende Kamera auf drei Personen; staerkste statische Kante 13,3 gegen 177,1 im Splitscreen. |

Der Splitscreen bestaetigt die Geometrie von `COACHLIM_OMETV` auf zwei Pixel
genau (953/799 gegen 955/800). Das alte Profil ist also nicht falsch, nur im
alten Schema und damit fuer Stage 04 unlesbar; `COACHLIM_OMETV_SPLIT` ist die
gueltige Fassung.

Bei der Couch-Runde gibt es **nichts zu trennen**, und die Signatur erkennt
deshalb nicht das Layout, sondern den Bildausschnitt: Der Piraten-Zaehler oben
links steht in der weiten Einstellung immer und faellt im nachtraeglich
hineingezoomten Schnitt aus dem Bild. Gemessen exakt zweigipflig — 39..51 mit
Zaehler, 0,2..4,3 ohne, dazwischen kein einziger Messwert. Die Zoomschnitte
machen 1,5 % der Laufzeit aus und sind nie laenger als 6 s; sie brauchen kein
eigenes Template, weil sie derselbe Bildkanal sind, nur enger.

Dieses Material zwingt ausserdem eine Entscheidung, die die anderen Profile
nicht kennen: Die drei Personen sitzen zwischen x=80 und x=1800. Ein
9:16-Fenster ist bei 1080 px Hoehe nur 607 px breit und wuerde zwei von ihnen
abschneiden — bei einem Format, in dem die Reaktion der anderen die Pointe ist.
`COUCH_FULL` passt deshalb das ganze Bild ein und nimmt das kleinere Bildband
(1080x606 auf y=657) in Kauf. Das ist der Preis dafuer, niemanden zu verlieren.

### Nachtrag 2026-09-06: der Modus kann auch der Schnitt sein

Vermessen an 8eotiLpudZ4 ("ICH HOLE MEINEN NEUEN BMW M4 COMPETITION AB",
1920x1080 bei 60 fps, 654 s). Profil `COACHLIM_BMW_VLOG`, Templates
`VLOG_FULL` und `KINO_FULL`.

Dritter Materialtyp: ein **gefuehrter Vlog** mit Handkamera. Die Kantenmessung
ueber 40 Frames findet erwartungsgemaess nichts — staerkste persistente Spalte
4.9, staerkste Zeile 11.1, also noch unter der Couch-Runde mit 13.3, die schon
als "nichts zu trennen" eingestuft war. Boxen gibt es hier nicht und kann es
nicht geben, weil sich die Kamera in jedem Bild bewegt.

**Trotzdem hat das Video zwei Modi, und der zweite ist keine Geometrie der
Quelle, sondern eine Entscheidung des Cutters.** Die Reveal-Sequenz ist
kinematisch geletterboxt: 110.00-134.25 s, lueckenlos ueber 98 Messpunkte im
Abstand von 0.25 s. Das obere Bildband liegt dort auf **exakt 0.00**, waehrend
der Median sonst 110.3 betraegt.

Das erweitert die Modus-Idee um einen Fall, den die Videos vom 2026-09-04 nicht
kannten: Ein Modus muss nicht bedeuten, dass die Quelle anders aufgebaut ist —
er kann auch bedeuten, dass der Schnitt an dieser Stelle anders aussieht. Die
Konsequenz ist dieselbe: eigene Zone, eigenes Template. `KINO` schneidet die
Balken heraus ([0,108,1920,864]), sonst staenden sie ein zweites Mal im
eingepassten Bild und saehen aus wie ein Renderfehler.

Erkannt wird ueber `flaeche` + `invertiert`, nicht ueber eine Kante: Ein
schwarzer Balken hat per Definition keine Struktur, an der sich Kantenstaerke
messen liesse. Die Kante y=108 trennt zwar auch (min 115.9 drinnen gegen p99
24.3 draussen), hat aber Ausreisser bis 154.3 — die Flaechenmessung hat keine.

`VLOG_FULL` passt wie `COUCH_FULL` das ganze Bild ein, hier aber aus einem
anderen Grund: Das Motiv ist ein Auto, also breiter als hoch, und seine
Silhouette ist der Punkt des Videos. Von einer Seitenansicht bliebe in einem
607 px breiten Fenster die Fahrertuer uebrig.

**Eingeblendete Fremdclips sind der eigentliche Fallstrick dieses Materials.**
Der Kanal schneidet fremde Aufnahmen als kleines Bild auf schwarzem Grund ein —
gemessen bei 224.70-227.50 s (Sponsor) und bis 512.30 s (Nebenclip). Sie sind
kurz, stehen an keiner vorhersagbaren Stelle und ruinieren eine Clipgrenze
lautlos: Der erste Schnitt endete 0.25 s im Sponsorclip, der vierte begann 0.10 s
darin. Beide fielen erst im Standbild des fertigen Clips auf, nicht im QC.
**Clipgrenzen gehoeren deshalb bei diesem Kanal vor dem Rendern gegen die
Bildraender geprueft**, nicht nur gegen Wortgrenzen und Moduslaeufe.

### Nachtrag 2026-09-06: nicht jedes Layout hat eine Kante

Zwei weitere Videos vermessen, und beide brauchten neue Profile. Wichtiger ist
aber, was die Signaturmechanik dabei gelernt hat.

| Profil | Quelle | Befund |
|---|---|---|
| `MARLI_PHONE` | A14FQZsFooQ | Gespiegeltes Zuschauer-Handy `[710,0,500,1080]` (exakt 9:19.5), Facecam `[1444,410,460,260]` (exakt 16:9). 53 % der Laufzeit. |
| `COACHLIM_REACT_YT` | vT1ysIDSpHw | Reagiertes Video formatfuellend, Creator-PiP `[1342,755,578,325]` (exakt 16:9) unten rechts. 91 % der Laufzeit. |

`COACHLIM_REACT_YT` war unauffaellig: Die obere PiP-Kante bei y=755 trennt
ueber 1003 Messpunkte mit einer echten Luecke (88 Werte unter 10, zwischen 10
und 20 kein einziger, der Rest darueber).

**`MARLI_PHONE` hat gar keine brauchbare Kante.** Die Grenze zwischen schwarzem
Rahmen und Handybild existiert nur, solange der Handyinhalt hell ist: gemessen
schwankt sie *innerhalb desselben Modus* zwischen 0,3 (dunkle App) und 119
(heller Homescreen). `ModusSignatur` kann deshalb jetzt auch eine **Flaeche**
statt einer Kante messen (`flaeche`, `invertiert`).

Und dann kam der eigentliche Fehler. Die erste Fassung mass die *Helligkeit*
des Rahmens — sauber gegen Vollbild-Cam und Spiel, aber blind gegen das vierte
Bild dieses Videos: ein Discord-Gitter aus vielen kleinen Zuschauerhandys.
Dessen Kacheln sind dunkle App-Oberflaechen und im Mittel **genauso schwarz wie
ein leerer Rahmen** (0,7 gegen 0,0). Zwei fertig gerenderte Clips liefen auf dem
falschen Bild, und es fiel erst bei der Sichtkontrolle des Rendervorgangs auf —
nicht im QC, denn Dauer und Aufloesung stimmten ja.

Gemessen wird deshalb **Struktur statt Pegel** (`kantenenergie: true`): Kacheln
haben Kanten, ein leerer Rahmen hat keine. Ueber 526 Einzelhandy- und 234
Gitter-Frames als Grundwahrheit liegt Einzelhandy bei Median 0,001 / p95 1,59
und das Gitter bei p5 2,19 / Median 9,86 — dazwischen eine echte Luecke. 96,6 %
richtig, und die wichtige Richtung sitzt: 99,6 % der Gitterbilder werden korrekt
ausgeschlossen.

Zwei Lehren, die ueber dieses Material hinausgehen:

1. **Ein Modus-Anteil von 1,00 heisst nur, dass die Signatur zugestimmt hat.**
   Er ist kein Beweis, dass das richtige Bild darunter liegt. Wer eine neue
   Signatur schreibt, muss mindestens einen gerenderten Frame ansehen.
2. **Die Signatur muss gegen ALLE Bilder eines Videos geprueft werden, nicht
   nur gegen das erwartete Gegenstueck.** Der Kontaktbogen zeigt sie; die
   Schwelle gegen zwei Klassen zu legen und die dritte zu uebersehen ist der
   naheliegende Fehler.

### Nachtrag 2026-09-07: ein Modus ist auch ein Befund

Vermessen an 2aMA9-rIprc ("TUERSTEHER MIT KOLJA GOLDSTEIN", Kanal AgaaMuza,
1920x1080 bei 60 fps, 2558 s). Profil `AGAAMUZA_TUERSTEHER`, Template
`VLOG_FULL`.

Ein Livestream-Mitschnitt vor einer Clubtuer: Handkamera, zwei Hosts, dauernd
wechselnde Gaeste, Twitch-Chat halbtransparent oben links. Die Kantenmessung
ueber 40 Frames findet **weniger als jedes bisher vermessene Video**:

| Material | staerkste Spalte | staerkste Zeile |
|---|---|---|
| `COACHLIM_OMETV_SPLIT` | 177,1 | — |
| `COACHLIM_COUCH` ("nichts zu trennen") | 13,3 | — |
| `COACHLIM_BMW_VLOG` ("nichts") | 4,9 | 11,1 |
| **`AGAAMUZA_TUERSTEHER`** | **1,8** | **2,3** |

Der BMW-Vlog hatte trotz fehlender Boxen einen zweiten Modus — die
geletterboxte Reveal-Sequenz. **Hier faellt derselbe Test negativ aus:** Das
obere Bildband liegt bei min 37,3 / Median 110,6, das untere bei min 47,9 /
Median 84,2. Kein einziger Messpunkt geht gegen null, wo der BMW-Vlog exakt
0,00 zeigte. Es wird nie geletterboxt.

**Damit ist dieses Material das erste einmodige im Repo — und das Schema konnte
das nicht ausdruecken.** Jedes Profil bisher hatte zwei Modi. Zwei Ergaenzungen:

- `signatur.immer: true` — es gibt nichts zu unterscheiden. Stage 04 spart sich
  dann den Bilddurchlauf: `clip analyse` laeuft ueber 42 Minuten Material in
  **3,4 s** statt eines vollen Abtastlaufs. Das ist keine abgeschaltete
  Erkennung, sondern eine gemessene Aussage; ob ein Material einmodig ist,
  entscheidet die Kantenmessung beim Anlegen des Profils.
- `signatur.sonst` — der Name des Gegenmodus. Der stand in `cmd_analyse`
  **fest auf `"SOLO"`**, was fuer `COACHLIM_COUCH` schon vorher auf kein
  Template zeigte: Dieses Profil hat gar keinen SOLO-Modus. Der Name gehoert
  ins Profil, nicht in den Code.

Der Twitch-Chat taucht in der Kantenmessung nicht auf, obwohl er durchgehend
im Bild steht — der Text laeuft staendig durch, es gibt also keine persistente
Kante. Er ist damit kein Modus, sondern Bildrauschen, und steht als
`muellzone` im Profil.

### Die Overlay-Standardlage passt nicht zu jedem Template

Ebenfalls am 2026-09-07 aufgefallen, und nur weil ein gerenderter Clip
angesehen wurde: `VLOG_FULL` passt das 16:9-Bild als 1080x606-Band auf
y=657..1263 ein. Die Standardwerte aus `config/overlays.yaml` setzen die
Untertitel auf 1424 — **161 px Luecke, in denen nichts steht.** Der Text
schwebt dann abgekoppelt im Blurfeld, statt am Bild zu haengen.

`VLOG_FULL` ueberschreibt deshalb beide Lagen: Follow-Pille auf 582 (in die
freie Flaeche zwischen Headline und Bild, wo sie nichts verdeckt), Untertitel
auf 1420 (25 px unter der Bildunterkante). Genau dafuer ist der
Override-Mechanismus da — die globalen Werte gelten fuer formatfuellende
Templates, nicht fuer solche mit kleinem Bildband.

Die Lehre ist dieselbe wie beim Modus-Anteil von 1,00: **Zahlen, die
plausibel aussehen, ersetzen keinen Blick auf einen gerenderten Frame.**

Zweiter Fall am selben Tag, und er zeigt den Unterschied zwischen "passt
nicht" und "steht im Weg": Bei `OME_SPLIT` lagen die Untertitel auf
1424..1688 **mitten in den Gesichtern der Creator-Cam**. Ueber vier gerenderte
Clips vermessen sitzen dort Stuhlkante ab y=1378, Haaransatz ab 1391 und
Gesichter bis rund 1660 — die Standardlage trifft sie genau.

Frei ist bei diesem Template nur das Wandband oberhalb der Koepfe:
**1031..1378**, nach oben von der Headline begrenzt, nach unten von den
Personen. Dort hinein passen beide Overlays, wenn das Band von 264 auf 200 px
schrumpft (zwei Zeilen brauchen 142) und die Pille mit nach oben rutscht:

| | Lage |
|---|---|
| Headline unten | 1031 |
| Follow-Pille | 1050..1144 |
| Untertitelband | 1155..1355 |
| Stuhlkante, ab hier Personen | 1378 |

Die Reihenfolge Headline → Pille → Band ist die Zusage aus
`tests/test_overlays.py`; die Pille musste deshalb mitwandern, sie haette
sonst unter dem Band gelegen. **Beide Faelle zusammen sagen dasselbe: Die
Standardlagen in `overlays.yaml` gelten fuer formatfuellende Templates. Wo
zwei Quellen uebereinanderliegen, muss die freie Flaeche gemessen werden,
und zwar am gerenderten Clip, nicht am Template.**

## Bildschnitte — Stage 04b, gemessen am 2026-09-07

Der Modus sagt, *welches Layout* vorliegt. Er sagt nicht, ob das Bild
**innerhalb** desselben Layouts springt. Bei `COACHLIM_OMETV_SPLIT` ist der
Modusanteil 100 % — und trotzdem wechselt das Bild 20-mal komplett, weil auf
OME.TV alle paar Minuten ein neuer Mensch vor der Kamera sitzt.

Nachgemessen an utB7GTrmLYY: Zwischen zwei Gespraechspartnern steht die
**Suchkarte des Kanals** — ein festes Meme-Bild ("Den Käse richtig legen"),
das der Kanal ueber die fremde Cam legt, waehrend die Statuszeile *"Partner
wird gesucht…"* anzeigt. Gemessen ueber 3357 Abtastpunkte im Abstand von
0,25 s als Abstand zu einem Referenzbild der Karte: p5 = 0,81 gegen Median
78,1. Die Schwelle liegt in einer sehr breiten Luecke, die Erkennung ist
eindeutig.

**21 Suchkarten, dazwischen 20 Gespraeche.** Sie sind zwischen 2,0 s und
185,2 s lang; die drei laengsten (185,2 / 115,2 / 106,5 s) tragen die
brauchbaren Clips, die kuerzesten (2,0 / 2,2 / 2,5 s) sind Partner, die sofort
weitergedrueckt haben.

### Die Pointe faellt oft auf die Karte

Das ist der Befund, der die Clipgrenzen bestimmt, und er war nicht zu erwarten:
**Die lustigste Zeile ist haeufig der Kommentar der Streamer, nachdem der
Partner schon weg ist** — und der laeuft dann ueber der Suchkarte.

| Clip | Pointe | Partner weg ab |
|---|---|---|
| Bewerbungsgespraech | "Du machst Bewerbungsgespräch mit dem" 599,4 + Lacher 599,3 | 598,75 |
| Der Dichte | "Der war sympathisch" 215,6 | 216,25 |
| Kuss | "Ach so, er will küssen" 447,6 | 448,00 |

Daraus die Regel, nach der die Selektion schneidet:

> Ein Clip darf in die **folgende** Suchkarte hineinlaufen — sie ist die eigene
> Uebergangskarte des Kanals, und der Ton laeuft dort weiter. Er darf **nie**
> in den naechsten Gespraechspartner laufen.

Eine Grenze, die das verletzt, sieht man dem fertigen Clip nicht an: Dauer,
Aufloesung und Tonspur stimmen. Man sieht es erst im Standbild — derselbe
Fehler wie bei den eingeblendeten Fremdclips im BMW-Vlog.

### Ein fester Schwellwert taugt nicht, der lokale Median schon

Naheliegend waere, den Bild-zu-Bild-Abstand gegen einen festen Wert zu pruefen.
**Das scheitert an der Handkamera:** Im Hausrundgang desselben Videos
(648-834 s) liegt der Abstand dauerhaft ueber jedem Wert, den ein echter
Schnitt anderswo erreicht — ein globaler Schwellwert meldet dort hunderte
Schnitte und ist unbrauchbar.

`schnitte.finde` misst deshalb gegen den **lokalen** Median (Fenster 6 s):
Ein Schnitt ist ein Ausreisser in seiner eigenen Umgebung. Gegen die 42
bekannten Kartenuebergaenge als Grundwahrheit:

| | |
|---|---|
| getroffen | **40 von 42** |
| zusaetzlich gemeldet | 12, davon die meisten echte Wechsel in 2-s-Bloecken |
| verpasst | 648,50 (Karte → Handkamera, lokaler Median schon hoch) und 839,25 (letzter Abtastpunkt, danach kommt kein Bild mehr) |

Gemessen wird ueber das **Vollbild**, nicht ueber die fremde Cam allein: Die
Box allein findet dieselben 40 Uebergaenge, meldet aber 20 statt 12 zusaetzliche.

`clip rendere` sucht die Schnitte in **einem** Durchlauf fuer alle Clips und
meldet je Clip, was dazwischenliegt. Es bricht bewusst nicht ab — bei einer
Handkamera ist ein Wechsel im Clip normal, und ob er stoert, entscheidet der
Blick. `--ohne-schnittpruefung` spart den Durchlauf.

### Dabei gefunden: der letzte Untertitel war ein Fetzen

`snappe` haengt 0,35 s Nachlauf an. Bei durchgehender Rede faengt darin schon
das naechste Wort an, und `untertitel.schneide` machte daraus einen eigenen
Cue. **Drei von acht Clips endeten so** — auf `"E ich"` und `"Ja, ich habe"`,
je 0,35 s lang.

`min_dauer` (0,6 s) stand zwar in `overlays.yaml` mit dem Kommentar "kuerzer
blitzt der Text nur auf", konnte einen Cue aber nur **dehnen**. Am Fensterrand
ist dafuer kein Platz, also blitzte der Fetzen genau so lange auf, wie er lang
war — und der Clip sah aus, als sei er mitten im Satz abgeschnitten. Der
letzte Cue wird jetzt verworfen, wenn er vom Clipende abgeschnitten ist *und*
`min_dauer` nicht erreicht. Mitten im Clip bleibt alles wie es war, sonst
verschwaende Gesprochenes.

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
  LnWKgVfcMMQ **null**. Nachgemessen am 2026-09-05: utB7GTrmLYY hat 23 Marker
  (13 davon `[gelächter]`), 4ubrGJLb4FQ wieder **null**. Nachgemessen am
  2026-09-06: A14FQZsFooQ hat **78** Marker (55 `[gelächter]`, dazu
  `[schreien]`, `[japst]`, `[schnauben]`, `[applaus]`), vT1ysIDSpHw bei
  47413 Zeichen Text **null**. Bilanz: drei von sechs Videos ohne Textkanal —
  kein Ausreißer, sondern der Normalfall. Wo sie fehlen, muss der
  Lacher-Detektor aus der Lautheit kommen; das Materialprofil gewichtet
  `lachmarker` dann auf 0.
- **Ein Lacher-Detektor aus dem Ton allein funktioniert nicht — gemessen, nicht
  vermutet.** Am 2026-09-06 an A14FQZsFooQ geprueft, wo 59 Marker die Wahrheit
  liefern. Von 40 gepflueckten Spitzen treffen:

  | Verfahren | Treffer (±4 s) |
  |---|---|
  | reine Lautheit | 28 % |
  | Lautheit × wortlos (Lachen wird nicht transkribiert) | 20 % |
  | Lautheit × Huellkurvenmodulation 3–8 Hz | 12 % |
  | alle drei kombiniert | 15 % |
  | **gleichverteilte Punkte (Zufallsbasis)** | **18 %** |

  Nur die reine Lautheit liegt ueberhaupt ueber dem Zufall, und das knapp. Die
  beiden „schlaueren" Merkmale sind *schlechter* als Raten. Konsequenz: Bei
  markerlosem Material ist Stage 05 ein **Lautheitsdetektor, kein
  Lacherdetektor**. Die Auswahl der lustigen Stellen passiert dann in Stage 06
  durch Lesen des Transkripts — nicht durch ein Signal. Das ist keine Luecke,
  die man mit einem besseren Schwellwert schliesst.
- **Das letzte Wort eines `json3`-Ereignisses bekommt das falsche Ende.**
  Gemessen am 2026-09-06: Es erbt `basis + dDurationMs`, also das Ende des
  Rolling-Windows statt das Ende des Wortes — bei vT1ysIDSpHw endet `" vor."`
  auf 547,88 s, während das nächste Ereignis schon bei 546,04 s beginnt. Der
  Überhang bleibt innerhalb eines Ereignisses unsichtbar und schlägt erst über
  Ereignisgrenzen zu: Er zerschnitt die Untertitel-Cues an falschen Stellen und
  verschob in `snappe` jede Endgrenze nach hinten. `lade_json3` kürzt jedes
  Wortende jetzt auf den Beginn des nächsten Wortes — nur kürzen, nie
  verlängern, sonst verschwände eine echte Sprechpause.

- **`--write-subs` lädt `de-orig` nicht.** Gemessen am 2026-09-05: yt-dlp meldet
  nur „There are no subtitles for the requested languages" und lädt das Video
  trotzdem — der Fehler fällt also erst auf, wenn Stage 03 die fehlende Datei
  sucht. `de-orig` ist eine *automatische* Caption und braucht deshalb
  `--write-auto-subs`. Der Befehl im README ist entsprechend korrigiert.
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
- **yt-dlps `web_embedded` funktioniert nicht mehr.** Gemessen am 2026-09-05:
  Der Client extrahiert gar nicht mehr, `tv`, `ios`, `mweb` und `web_safari`
  ebenso wenig. Der **Default-Client** liefert wieder 31 Formate inklusive avc1
  und laedt vollstaendig durch. Die Angabe oben galt am 2026-09-04 und ist
  ueberholt — der Extractor ist eine bewegliche Groesse, kein Fixpunkt.
- **Und einen Tag spaeter reicht auch der Default nicht mehr.** Gemessen am
  2026-09-06: Extraktion laeuft, der Download bricht aber reproduzierbar nach
  ~10 MB mit `HTTP Error 403: Forbidden` ab — zweimal an derselben Stelle, auch
  mit `-N 8 --retries infinite`. yt-dlp warnt dabei selbst: *"The extractor
  specified to use impersonation ... but no impersonate target is available."*
  Genau das ist die Ursache. Gegenmittel:

  ```bash
  uv pip install "yt-dlp[default,curl-cffi]"
  .venv/bin/yt-dlp --impersonate chrome ...
  ```

  Damit laufen 830 MB am Stueck durch. **Das Homebrew-yt-dlp bringt curl_cffi
  nicht mit** — der Aufruf muss also ueber das venv gehen, nicht ueber
  `/opt/homebrew/bin/yt-dlp`. Die Lehre aus drei Revisionen dieser Notiz in
  drei Tagen: Der Ingest ist der instabilste Teil der Pipeline. Wenn ein
  Download abbricht, liegt es fast nie am Format-Selektor.
- **TikTok ist als Quelle doch abrufbar.** Ebenfalls am 2026-09-05 gemessen:
  Einzelvideos per URL laufen ohne CAPTCHA durch (2,6 MB in Sekunden). Die
  Notiz oben gilt fuer Suche und Massenabruf, nicht fuer die einzelne URL.
- **macOS setzt `UF_HIDDEN` auf die `.pth` im venv.** `site.py` ueberspringt
  seit 3.12 versteckte `.pth`-Dateien kommentarlos (Zeile 176). Damit faellt der
  Editable-Install still aus und `clip` stirbt mit `ModuleNotFoundError`, obwohl
  die Datei da ist und auf den richtigen Pfad zeigt. Das Flag kommt nach jeder
  Neuinstallation zurueck. Gegenmittel: `chflags nohidden
  .venv/lib/python3.12/site-packages/*.pth`, oder dauerhaft
  `PYTHONPATH=src .venv/bin/python -m videoclipper.cli` statt `clip`.
- **`-af` weigert sich bei Streams aus `filter_complex`** und bricht mit Exit
  234 ab. In Compilations muss `loudnorm` deshalb *in* den Graphen, hinter
  `concat`. Bei Einzelclips bleibt `-af` richtig, weil der Ton dort direkt aus
  dem Eingang kommt.
- **Panelhöhen müssen gerade sein.** In yuv420p rundet der Scaler jede ungerade
  Höhe still ab; 607+1313 ergab eine Bühne von 1918 statt 1920 px. Stage 09 prüft
  das jetzt und bricht ab, statt es dem QC zu überlassen.

## Pflicht in jedem Clip — zwei Overlays, ab 2026-09-06

Beides gilt fuer **jeden** gerenderten Clip, nicht nur fuer neue Formate.
Die Werte stehen zentral in `config/overlays.yaml` und werden von
`layout.template()` unter jedes Template gemischt — nicht elfmal kopiert,
weil sie weder von der Quelle noch von der Zielkomposition abhaengen und
damit nach Leitprinzip 3 in keine der beiden materialabhaengigen Schichten
gehoeren. Ein Template nennt nur, was bei ihm anders ist.

`qc.pflichtelemente` prueft das **vor** dem Rendern und bricht ab. Das ist
Absicht: Ein Clip ohne diese Overlays hat trotzdem die richtige Dauer, die
richtige Aufloesung und eine Tonspur — das nachtraegliche QC der Datei kann
ihn also nicht von einem fertigen unterscheiden. Abschalten geht nur mit
`aktiv: false` **plus** `grund:` im Template; ohne Begruendung ist es ein
Fehler, damit ein verschwundenes Overlay nicht als Einstellung durchgeht.

### 1. Untertitel mit Animation

Ein PNG je Cue, eingeblendet ueber `enable='between(t,ab,bis)'` — dieselbe
Mechanik wie die Countdown-Liste. **Die Animation kostet weder ein zweites
Bild noch einen zweiten Filter:** Der Cue faehrt aus 26 px von unten in seine
Lage, und das steckt vollstaendig im `y`-Ausdruck des `overlay`-Filters, den
es ohnehin gibt. Gemessen am fertigen Clip: 22 → 12 → 4 → 0 px Versatz ueber
0,14 s.

Verworfen, weil je Cue teurer: Alpha-Einblenden (`fade` animiert auf einem
Einzelbild nicht), Pop ueber `scale` (Ausdruck je Frame neu skaliert),
Wortmarkierung (ein PNG je Wort statt je Cue, rund viermal so viele
Eingaenge). Karaoke scheidet ohnehin aus — kein libass, kein drawtext, und
der gemessene Hausstil ist statisch.

Das Cue-PNG ist nur so hoch wie das Band (1080x264 statt 1080x1920). Bei
23 Cues sind das ein Achtel der Bilddaten im Encoder.

Gebrochen wird an der ersten reissenden Grenze: Sprechpause (0,45 s),
**Satzende**, Zeichenzahl (42), Standzeit (2,2 s). Das Satzende steht vor der
Zeichenzahl, sonst laufen zwei Saetze in eine Zeile und der naechste Cue
beginnt mit dem Rest des vorigen — gemessen an vT1ysIDSpHw: aus
`"vor. Also, ich bin die Sage, bin 26"` wurde `"Stell dich vor."` +
`"Also, ich bin die Sage, bin 26 Jahre"`. Initialen brechen nicht
(`"Gute Maus L."` bleibt zusammen), `[gelaechter]` wird nie gesetzt.

**Dabei fiel ein Fehler im Transkriptparser auf, der aelter ist als die
Untertitel.** Das *letzte* Wort eines Rolling-Window-Ereignisses bekam
`basis + dDurationMs`, also das Ende des Fensters statt das Ende des Wortes.
Bei vT1ysIDSpHw endet `" vor."` dadurch auf 547,88 s, waehrend das naechste
Ereignis schon bei 546,04 s beginnt — 2,3 s Ueberhang. Innerhalb eines
Ereignisses faellt das nie auf, ueber Ereignisgrenzen hinweg zerschnitt es
die Cues an falschen Stellen und verschob in `snappe` jede Endgrenze nach
hinten. Jedes Wortende wird jetzt auf den Beginn des naechsten Wortes
gekuerzt (nie verlaengert, eine echte Sprechpause bleibt also stehen).
Ueber alle neun lokalen Transkripte bleibt danach kein Ueberhang ueber der
50-ms-Mindestdauer.

### 2. Follow-Aufforderung waehrend des Clips

Eine Pille im gemessenen Gruen `#01FC19`, die von rechts einfliegt, rund
2,6 s steht und rechts wieder hinausfliegt — auf TikTok liegt dort die
Buttonleiste mit dem Folgen-Knopf, die Bewegung zeigt also dorthin, wo
geklickt werden soll. Auch das ist ein einziges PNG; die Bewegung steckt im
`x`-Ausdruck.

**Warum nicht am Ende:** `scoring.yaml` gewichtet `retention` mit 0,40, und
genau `completion_rate` ist die Zahl, die in jeder bisherigen Messung fehlt —
es ist also nicht belegt, dass nennenswert viele Zuschauer bis zum Schluss
bleiben. Eine Aufforderung im Abspann erreicht nur, wer ohnehin geblieben
ist. Gesetzt wird sie bei 35 % der Cliplaenge, nie in den ersten 3 s (der
Hook gehoert dem Clip) und nie in den letzten 2 s (die Pointe auch). Passt
sie nicht mehr, wird sie bis 1,6 s gestaucht und darunter weggelassen **und
gemeldet**, statt an eine falsche Stelle gezwungen.

`konversion` — Follows pro View — ist mit 0,20 die drittstaerkste Achse des
Scores und laut `scoring.yaml` "das Ziel des Accounts". Dieses Overlay ist
die einzige Stelle der Pipeline, die direkt darauf einzahlt.

### Wo sie liegen

Beide bleiben ueber TikToks UI-Zone (unterste 192 px), und
`untertitel.band` / `follow.masse` **brechen ab**, wenn ein Template sie
hineinschiebt. Drei Textebenen teilen sich die Canvas; ein Test prueft ueber
alle Templates, dass sie sich nicht beruehren:

| Ebene | Lage (Standard) |
|---|---|
| Headline | je Template, 170..1031 |
| Follow-Pille | 1243..1337 |
| Untertitelband | 1424..1688 |
| UI-Zone ab | 1728 |

`TOP5_COUNTDOWN` ist der einzige dokumentierte Ausnahmefall: Untertitel
`aktiv: false` mit Grund — die Segmente kommen aus bis zu fuenf Quellen,
deren Transkripte der `CountdownPlan` gar nicht mitfuehrt; der Textkanal des
Formats ist die mitwachsende Liste. Die Follow-Pille hat es trotzdem, tiefer
gesetzt (y=1650), weil zwischen Liste (endet 765) und Panel (beginnt 812)
keine freie Flaeche liegt.

## Hook und Rangliste — Stages 07/07b, ab 2026-09-07

Zwischen Selektion (Stage 06) und Rendern lag eine Luecke: Die Selektion
liefert N Kandidaten, gerendert wurden alle N in Planreihenfolge. Welcher
zuerst raus soll, stand nirgends — und ob die Headline taugt, auch nicht.

### Die Headline kann zwei Fehler machen, die kein QC sieht

`hook.pruefe` vergleicht die Headline gegen den **tatsaechlichen Inhalt des
Clipfensters**. Das unterscheidet sie von `forecast._hook`, das den Hook gegen
Annahmen aus `scoring.yaml` bewertet und den Clip gar nicht kennt.

1. **Verrat.** Ein Inhaltswort der Headline faellt erst im letzten Drittel des
   Clips und im Aufbau nicht. Dann ist die Frage beantwortet, bevor jemand den
   Clip startet. Woerter, die ohnehin frueh fallen, zaehlen ausdruecklich
   *nicht* als Verrat — die ordnen nur ein, worum es geht.
2. **Lose Headline.** Kein Wort der Headline kommt im Clip vor. Sie verspricht
   dann etwas anderes, als zu sehen ist, und der Zuschauer springt in der
   ersten Sekunde ab. Das ist teurer als ein schwacher Hook.

Umgeschrieben wird nichts. Der Code entscheidet WIE, nicht WAS — er meldet,
das Umschreiben bleibt Stage 06.

### Rangliste: zwei Zahlen, nicht eine

`clip rangliste` bewertet alle Clips eines Plans, bevor einer gerendert ist —
ohne Video, nur Plan plus Transkript, also in Sekunden. Sortiert wird nach der
Prognose (Stage 15), **aber ein Clip mit verraeterischer Headline rutscht ans
Ende**, unabhaengig von seiner Punktzahl.

Angezeigt werden Prognose *und* Selektionsscore der AI. Wo beide um mehr als
0,25 auseinanderliegen, sagt die Ausgabe das ausdruecklich. Der Grund ist
derselbe wie beim Bewertungssystem: Die Prognose ist unkalibriert und gibt
`konfidenz 0.2` aus. Eine einzelne Zahl waere hier Scheingenauigkeit; zwei
unabhaengige Urteile, die sich widersprechen, sind eine brauchbare Information.

Gesnappt wird mit derselben `snappe`, die auch der Renderer benutzt — sonst
rankt man Laengen, die in der fertigen Datei nie vorkommen.

### Payoff-Position ist eine Naeherung, keine Pointenerkennung

`hook.payoff_position` sucht die dichteste Sprechstelle im Clip. Das ist
bewusst schwach: Bei markerlosem Material gibt es kein Lachsignal, und ein
Lacherdetektor aus dem Ton allein liegt gemessen **unter dem Zufall** (siehe
Fallstricke). Die Wortdichte sagt immerhin, wo im Clip am meisten passiert.

### Dabei gefunden: `snappe` konnte eine negative Dauer liefern

Gemessen am 2026-09-07. Liegt das gewuenschte Fenster hinter dem letzten
transkribierten Wort, zog `min(tr.dauer, ...)` das Ende **vor** den Anfang —
`snappe` gab dann `start=59.8, ende=52.76` zurueck, und FFmpeg haette ein
negatives `-t` bekommen. Das Transkript endet regelmaessig vor dem Video, nach
dem letzten Wort laufen oft noch Bilder; der Fall ist also nicht konstruiert,
sondern trifft jeden Clip am Videoende. Bei `en <= s` gilt jetzt das
ungesnappte Fenster.

## Look

Statische Headline pro Clip, kein Karaoke — aus dem Referenzmaterial gemessen, nicht
angenommen. Anton (OFL, kommerziell frei), Versalien, weiß mit dickem schwarzem Rand,
bei `OME_STACK` auf der Naht zwischen den beiden Panels.

Das gilt für die **Headline**. Die Untertitel darunter wechseln je Cue und
rucken beim Wechsel nach oben — siehe „Pflicht in jedem Clip". Auch das ist
kein Karaoke: Es bewegt sich nichts *innerhalb* eines Cues, und es bleibt ein
Standbild je Cue.

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


## Format: TOP5_COUNTDOWN — vermessen am 2026-09-05

Bis hierher erzeugt die Pipeline **einen** Clip aus **einer** Quelle. Der
Countdown ist das erste Format, das das aufbricht: fuenf Segmente aus bis zu
fuenf Quellen, darueber eine Liste, die sich von Platz 5 nach Platz 1 fuellt.

Vermessen an `@phrai92/7673568784648539424` (2,2 Mio. Views, 11,58 % Like-Rate,
1,02 % Share-Rate, 48,7 s). Kein Wert im Template ist geschaetzt:

| Groesse | Messwert | Herkunft |
|---|---|---|
| Headlinefarbe | `#01FC19` | Median aus 32796 Pixeln |
| Zeilenabstand der Liste | 89 px | Abstand der Textzeilen selbst |
| Panel | `[60, 812, 960, 916]` | scharfe Zone gegen Blur-Untergrund |
| Freie Zone unten | 192 px | Panelunterkante bei y=1728 |
| Aufdeckzeiten | 0 / 8,5 / 18,0 / 25,5 / 36,5 s | 98 Abtastpunkte |

**Die Segmente werden zum Ende hin laenger** (8,5 / 9,5 / 7,5 / 11,0 / 12,2 s).
Der Payoff bekommt am meisten Zeit.

**Der Hook ist das leere Geruest.** Die Ziffern 1..5 stehen ab Sekunde 0 da, die
Beschriftungen kommen einzeln dazu. Vier unbeschriftete Zeilen sind eine offene
Frage, die erst bei Sekunde 36,5 beantwortet wird — und sie funktioniert ohne
ein einziges gesprochenes Wort.

Das hat eine Konsequenz fuer Stage 15: **`forecast.py` bewertet den Hook aus dem
Transkript und wuerde dieses Format verreissen.** Ein visueller Hook ist dort
gar nicht vorgesehen. Das ist eine Luecke im Modell, keine Frage der
Kalibrierung.

### Die UI-Zone ist real

TikTok verdeckt die unteren ~192 px mit Caption, Buttons und Soundzeile. Die
Referenz laesst sie konsequent frei. `GAME_STACK` tut das nicht — sein unteres
Panel laeuft auf `[0, 606, 1080, 1314]` bis y=1920 und verliert dort
Bildinhalt. `countdown.sicherheitszone_pruefen` meldet solche Faelle; es bricht
bewusst nicht ab, weil die Zone eine Plattformeigenschaft ist und sich aendern
kann.

### Warum ein eigener Datenvertrag

`EditPlan` beschreibt ein Segment aus einer Quelle. Haette der Countdown darin
Platz finden sollen, waere jedes Feld optional geworden und der Vertrag haette
seine Schaerfe verloren. `CountdownPlan` steht deshalb daneben, mit derselben
Trennung: Die AI fuellt `titel`, `text` und die Zeitfenster, alles unter
`aufgeloest` rechnet der Code aus dem Template.

## Monetarisierung

Tier A ist alles über 63 Sekunden gerenderter Dauer (TikTok Creator Rewards verlangt
*über* eine Minute, nicht exakt 60 s). Tier B bleibt unter 60 s und wird **nie**
künstlich gestreckt. QC misst die fertige Datei mit ffprobe. Der Schwellwert steht in
der Konfiguration, weil sich Programmbedingungen ändern.
