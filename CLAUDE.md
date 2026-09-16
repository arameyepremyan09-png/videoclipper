# Videoclipper

Eigene Short-Form-Clipping-Pipeline: langes Video rein, fertige 9:16-Shorts raus.
Kontrollierbare Alternative zu OpusClip.

**Architekturdokument (immer zuerst lesen):**
https://claude.ai/code/artifact/f219d5f4-ee82-4f8e-836e-b2bec93de7f5

Es enthält die fünfzehn Stages, das EditPlan-Schema, die Materialprofile, Templates,
das Kostenmodell und die Tabelle aller getroffenen Entscheidungen. Architekturfragen
werden dort nachgelesen und dort aktualisiert, nicht neu verhandelt.

**Arbeitsstand: [ARBEITSSTAND.md](ARBEITSSTAND.md)** — offene Aufträge mit den
Befunden des letzten Entwurfs, Befehle, Prüfwerkzeuge (`werkzeuge/`) und der
bewährte Ablauf je Video. In einem neuen Chat zuerst lesen.

## SCHNITTREGELN.md — vor jedem Clip abarbeiten

**[SCHNITTREGELN.md](SCHNITTREGELN.md) ist die Auftragslage des Nutzers und steht
ueber jeder Heuristik im Code.** Sie wird bei *jeder* Clip-Erstellung gelesen und
Punkt fuer Punkt abgearbeitet, nicht nur bei neuem Material. Kurzfassung:

1. **Dranbleibe-Grund.** Jeder Clip traegt seinen eigenen Kontext (1a), endet auf
   der Pointe statt mittendrin und enthaelt keinen zweiten Gegenstand (1b), und
   hat einen echten Lacher statt nur eines Lautheitspeaks (1c).
2. **Layout je Format.** 1:1-Kaese → `CHAT_STACK`, Fullcam mit Gaesten →
   `FULLCAM_169` (alles zeigen, nicht beschneiden), Gaming → `GAME_STACK`,
   TikTok-Reaction → `REACT_STACK`, Top-5 → `TOP5_COUNTDOWN`.
3. **Hooks** kurz, ohne jedes Satzzeichen, mit Emoji-Paar aus 🥀🫩💀🙏.
4. **Untertitel** verdecken nie ein Gesicht — je Template nachgemessen, am
   gerenderten Frame kontrolliert.
5. **Qualitaet halten, dynamisch schneiden.**
6. **Kurzformat** (ab 2026-09-11, in Erprobung): erst ein Teaser mit dem
   lustigsten Moment (2-7 s, `EditPlan.teaser`), dann harter Schnitt an den
   Anfang der Geschichte, zusammen mindestens 30 s mit vollem Kontext (1a
   gilt). Headline als Uebertreibung, Punch-in auf der Pointe. Die erste
   Fassung (10-15 s, Pointe bei 3-5 s) war laut Nutzer "zu kurz, kein Kontext".

Der Anlass ist gemessen und steht in der Datei: Von neun ausgelieferten Clips
wurden drei abgelehnt, und **die abgelehnten hatten die hoeheren AI-Scores**
(0.88 an der Spitze). Der Selektionsscore misst nicht, was der Nutzer bewertet.

## Material

- **Zielmaterial:** GTA-6-Content. Existiert noch nicht (Stand September 2026).
- **Testfeld:** deutscher Reaction-/OME.TV-Content von Coachlim.
- Ausgabe: TikTok, Reels, YouTube Shorts. Betrieb täglich, möglichst automatisiert.

Das Briefing sprach von GTA, das Referenzmaterial ist Reaction-Streaming. Beides gilt:
Reaction ist das Testfeld, GTA das Ziel.

**Immer fremde Creator, nie eigene Aufnahmen** — auch nach dem GTA-6-Release wird
nicht selbst gespielt. Zwei Quellplattformen:

| | YouTube | Twitch |
|---|---|---|
| Transkript | `de-orig` vorhanden, Primärquelle | **keins — ASR ist Pflicht** |
| Verfügbarkeit | dauerhaft | VOD läuft je nach Kanalstatus nach 7–60 Tagen ab |
| Besonderheit | — | DMCA-Stummschaltungen, Twitch-Clips als Signal |

Der Twitch-Pfad ist damit **nicht** der YouTube-Pfad mit anderer URL. Er braucht
eigene ASR, hat ein Zeitfenster und eigene Fallstricke.

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

### Nachtrag 2026-09-08: derselbe Fehler stand noch in SOLO_FULL

Beim Sichten des ersten gerenderten Clips aus `COACHLIM_HANDYS` aufgefallen —
und es ist **nicht** dasselbe Problem wie oben, sondern seine Ursache eine
Ebene tiefer. `SOLO_FULL` stand auf `passung: einpassen`. Damit wurde die
1920x1080-Cam auf ein 1080x608-Band heruntergerechnet, das auf y=656..1264
in einem Blurfeld schwebte. Zwei Folgen:

1. **Der Kopf war rund ein Drittel so gross wie beabsichtigt.** Bei einem
   Reaktionsformat ist das Gesicht der Inhalt.
2. **Die Untertitel standen 160 px unter der Bildunterkante** — exakt der
   Fehler, der fuer `VLOG_FULL` einen Abschnitt weiter oben schon
   beschrieben ist. Dort behoben, hier nicht.

Das Template widersprach dabei seinem eigenen Kopfkommentar, der seit jeher
sagt, die Cam werde „mittig um fokus_x auf 9:16 beschnitten statt
verkleinert". Der Beleg, dass `fuellen` gemeint war, steht in den Profilen:
**Alle sieben Profile mit einer SOLO-Zone geben `fokus_x` an** (870 bei
`COACHLIM_HANDYS`, 700 bei `MARLI_PHONE`, sonst 960). Und `fokus_x` liest
`render._panel_kette` **ausschliesslich im `fuellen`-Zweig** — unter
`einpassen` war es tote Konfiguration. Sieben Profilautoren haben also
aufgeschrieben, wo beschnitten werden soll, und beschnitten wurde nie.

`VLOG_FULL` und `COUCH_FULL` bleiben bei `einpassen`: Beide haben dafuer
einen gemessenen Grund (drei Personen ueber die volle Breite; ein Auto,
dessen Silhouette der Punkt ist). Bei `SOLO_FULL` steht eine Person mittig
vor einer Wand — seitlich beschneiden kostet nichts als Wand.

**Die Lehre ist eine dritte, ueber die Overlay-Lage hinaus: Eine Einstellung,
die kein Code liest, ist kein Kommentar, sondern ein Fehler.** `fokus_x`
stand in sieben Profilen und wurde nirgends wirksam; das faellt weder im QC
noch im Test auf, weil die Datei formal richtig bleibt. Wer ein Feld ins
Schema aufnimmt, sollte pruefen, ob der Pfad es ueberhaupt erreicht.

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

### Nachtrag 2026-09-08: der untere Feed laeuft von Kante zu Kante

Vermessen an ErYc_3POazo ("COACH UND ABUGOKU REAGIEREN AUF EURE TIKTOKS",
1317.7 s, 1920x1080@60). Profil `COACHLIM_ABU_TIKTOK`, Templates `REACT_STACK`
und `FULLCAM_169`. Zwei Modi, ueber 659 Abtastpunkte sauber getrennt: REACT
42 %, dazwischen Fullcam auf zwei Personen.

Der Anlass war nicht das Material, sondern eine **Rueckmeldung des Nutzers zu
neun ausgelieferten Clips** — sechs gut, drei schlecht. Die drei abgelehnten
hatten die *hoeheren* AI-Scores; `6T-QuUKYy7w_006` stand mit 0.88 an der
Spitze und war unbrauchbar ("kein Kontext, kein Inhalt, kein wirklicher
Lacher"). **Der Selektionsscore misst nicht, was der Nutzer bewertet.** Was er
bewertet, steht seither in [SCHNITTREGELN.md](SCHNITTREGELN.md); die Datei
wird vor jedem Renderlauf abgearbeitet.

**Zum ersten Mal wurden die Referenzen selbst geladen und vermessen**, statt
den Hausstil aus den eigenen Clips abzuleiten. Das hat sofort eine Annahme
widerlegt, die seit dem 2026-09-04 im Repo stand: `REACT_STACK` passte den
TikTok-Player ein, weil er in der Quelle bereits 9:16 ist und "deshalb nie
beschnitten" werden duerfe. Ergebnis war ein 739 px breites Video zwischen
zwei 170 px breiten Blurbalken. In beiden Referenzen des Nutzers
(`@coachlim.clips25/7677675052585831713`, `@coachlim.clips5/7678435849457028384`)
laeuft der untere Feed **ohne einen Pixel Blur von Bildkante zu Bildkante**.
"Mittig und angepasst" heisst mittig *beschnitten*. `REACT_STACK` steht jetzt
auf `fuellen`; der Preis sind rund 15 % oben und unten, und das trifft bei
einem TikTok den Rand, nicht das Motiv.

`PHONE_STACK` und `GAME_STACK` stehen bewusst weiter auf `einpassen`: Ein
Handy ist 9:19.5 und damit schmaler als die Buehne — dort schneidet `fuellen`
40 % der Bildschirmhoehe weg statt Rand. Was dort richtig ist, wird am
naechsten Video dieses Typs gemessen.

### Drei Dinge, die erst am gerenderten Frame auffielen

Alle drei standen vorher nicht im Repo, alle drei waren im QC unsichtbar:

1. **Anton hat keine Emoji-Glyphen.** Die neue Hookregel verlangt ein
   Emoji-Paar am Ende jeder Headline — gerendert wurde ein leeres Kaestchen.
   Weil Regel 3 genau **vier** Emojis zulaesst, ist die Menge endlich: Sie
   liegen jetzt als PNG in `assets/emoji/` und wandern wie Anton mit dem Repo.
   Ein Emoji-Font waere die naheliegende Loesung gewesen und die falsche — er
   ist plattformabhaengig (Apple Color Emoji gegen seguiemj), und die Zahl der
   plattformabhaengigen Stellen bleibt bei drei. `.gitignore` hat dafuer eine
   ausdrueckliche Ausnahme von `*.png`.
2. **Die Standard-Overlaylagen sassen mitten im Gesicht.** Im gefuellten
   Player liegt das Gesicht des reagierten Videos auf y=965..1501; die
   Follow-Pille stand auf der Stirn (1243..1337), das Untertitelband auf dem
   Mund (1424..1688). `REACT_STACK` setzt beide jetzt an die Raender —
   Pille auf 713..807 ueber dem Gesicht, Band auf 1556..1724 darunter.
   **Dabei ein Detail, das nicht offensichtlich ist:** Das Band wurde von 264
   auf 168 px *verkleinert*, um den Text tiefer zu bekommen. Der Text steht im
   Band zentriert, also zieht jedes ueberschuessige Pixel Bandhoehe ihn wieder
   nach oben. Schmaler heisst hier tiefer.
3. **Der erste Cue war ein Fetzen** — derselbe Fehler wie beim letzten Cue,
   nur spiegelbildlich. `snappe` setzt 0.20 s Vorlauf, und bei durchgehender
   Rede liegt darin das Ende des vorigen Satzes: Der Clip begann mit "kann."
   fuer 0.2 s. Dehnen kann `min_dauer` ihn nicht, weil die Grenze der naechste
   Cue ist und nicht das Fensterende. Die Regel fuer den letzten Cue steht
   seit dem 2026-09-07 im Repo; die fuer den ersten fehlte.

### Untertitel duerfen falsch sein, und sie waren es

Regel 4 des Nutzers verlangt ausdruecklich **korrekte** Untertitel. YouTubes
ASR verschreibt sich bei Stotterern: Aus "Mein Hund kann mir auf'n Ruecken
tragen" wurde "Mein Hund kann mein Hand mein Hund kann", und das stand in
Versalien quer im Bild.

Korrigiert wird deshalb der **Cue**, nicht das Transkript — das Transkript
traegt die Zeitachse, an der Snapping, Kandidaten und Hookpruefung haengen.
Die Regeln liegen je Video in `data/korrekturen/<video_id>.json` und greifen
in `untertitel.korrigiere` nach dem Schnitt der Cues. Preis: Eine Regel muss
vollstaendig in *einen* Cue passen, also unter `max_zeichen`. Deshalb meldet
`korrigiere` jede Regel, die nicht gegriffen hat, statt sie still verfallen zu
lassen.

Gegengeprueft wurde mit whisper.cpp auf demselben 47-s-Fenster — nicht als
Ersatz fuer das Transkript, sondern als **Zweitmeinung** dort, wo eine Zeile
offensichtlich Unsinn ist. Das hat vier Korrekturen belegt und zwei weitere
verhindert: Wo beide ASRs verschiedenen Unsinn hoeren, wird nichts erfunden.

### Und ein Grenzfall, den die Signatur nicht kann

Dieselbe Warnung wie bei `COACHLIM_HANDYS`, und sie ist hier erneut gemessen:
Die Flaechensignatur erkennt "Browser-Capture", nicht "TikTok-Player". Bei
340 s zeigt der Kanal ein TikTok-**Profilgitter** im selben Browser; die linke
Flaeche ist dort ebenfalls schwarz (4.9), das Bild laeuft also als REACT durch
und wuerde mit der Playerbox gerendert. Ein Trennmerkmal wurde gesucht und
nicht gefunden — die Kantenenergie derselben Flaeche liegt ueber alle 659
Punkte zwischen 0 und 4 und trennt gar nichts.

### Nachtrag 2026-09-08: vier Clips aus ErYc_3POazo, drei Befunde

Der erste Lauf mit den Schnittregeln als Arbeitsanweisung. Von den urspruenglich
sechs Kandidaten sind vier geblieben; die beiden anderen scheiterten an Regel 2,
und daran zeigt sich, was die Modusgrenzen wirklich kosten:

- **Der Bungee-Anruf** (643-666 s) hat die Pointe genau auf dem Layoutwechsel.
  Gemessen im 0.4-s-Raster springt das Bild bei **664.8 s** auf Fullcam, waehrend
  "das ist fett" bis 665.96 s laeuft. Ein REACT-Clip muesste vor der Pointe
  enden, ein FULLCAM-Clip haette keinen Aufbau — Regel 1a. Nicht schneidbar.
- **Der China-Preis** (796-817 s) liegt ueber drei Laeufen: FULLCAM 790-798,
  REACT 798-806, FULLCAM 806-858. Das Ratespiel um den Preis faellt genau in
  den mittleren. Ebenfalls nicht schneidbar.

Beides ist kein Fehler der Pipeline, sondern der Preis dafuer, dass ein Clip
mit **einem** Template gerendert wird. Er ist hoeher als gedacht: Zwei der
besten Stellen des Videos sind unbrauchbar.

**Die 2-s-Abtastung von `clip analyse` reicht fuer die Raender nicht.** Sie
sagt "REACT 590-666"; der Wechsel liegt tatsaechlich bei 664.8. Wer eine
Clipgrenze in die Naehe eines Laufendes legt, muss dort nachmessen — bei
`ErYc_3POazo_004` lagen zwischen Laufbeginn und Clipbeginn 0.24 s, und im
laufenden Fullcam steckt bei 215.5-218.0 s ein **2.5 s langer REACT-Einschub**,
den das 2-s-Raster als einen einzigen Punkt sieht.

### Zwei Fehler in Werkzeugen, die ich selbst gebaut habe

1. **`hook.pruefe` meldete die richtigen Headlines als Spoiler.** Ein Wort aus
   `OFFEN` zaehlte als Inhaltswort und wurde damit zum Verraeter, sobald
   dasselbe Fragewort spaet im Clip faellt: "WARUM WARTET ER KEINE ZWEI TAGE"
   galt als Spoiler, weil bei 13 von 20 s jemand "Warum hast du nicht einfach
   die Flasche bestellt?" fragt. Ein OFFEN-Wort kann per Definition nichts
   verraten — und seit Regel 3 Satzzeichen verbietet, ist es das *einzige*
   Mittel, eine Headline offen zu halten. Der Fehlalarm traf also genau die
   Headlines, die die Regel richtig umsetzen.

2. **Die Korrekturmeldung war je Clip statt je Lauf.** Die Regeln gelten fuer
   ein Video, ein Lauf schneidet daraus mehrere Clips — eine Regel fuer Clip 3
   greift in Clip 1 naturgemaess nicht. Bei 23 Regeln und 4 Clips waren das
   rund 60 Zeilen "ohne Treffer", in denen eine echte Fehlmeldung untergegangen
   waere. `korrigiere` gibt jetzt die Nummern zurueck, die gegriffen haben;
   `ungenutzte` meldet am Ende des Laufes, was nirgends gegriffen hat.

**Beide Fehler haben dieselbe Form:** ein Pruefwerkzeug, das so laut ist, dass
man es abschaltet, ist schlechter als keins. Das ist die Kehrseite der Regel
"melden statt still verfallen lassen".

### Und `FULLCAM_169` zum ersten Mal gerendert

Zwischen Headline und Bildband liegen genau **150 px** frei — das Kantenmass
des Follow-Knopfes. Bei y=620 lag er 38 px im Bild und sass auf der LED-Leiste.
`y: 582` und `max_zeilen: 2` gehoeren deshalb zusammen: Bei drei erlaubten
Headlinezeilen reicht die Headline bis 520 und der Knopf passt nicht mehr
darueber. Seit Regel 3 sind Headlines ohnehin kurz.

### Nachtrag 2026-09-11: Stream mit Instagram-Browser, vier Grenzfehler

Vermessen an saiJDq9DM_Y ("Bleibt Sidney fuer immer Single?! Eli ueber
Sidneys Zukunft", Kanal Elijello, 708.4 s, 1920x1080@60). Profil
`ELIASN97_STREAM`, Templates `FULLCAM_169` und neu `FOTO_STACK`. Acht Clips,
zwei davon Tier A (74.8 s und 69.5 s, beide ohne Streckung).

Das Video sind **zwei aneinandergesetzte Streams** (blaues Trikot bis 394 s,
danach gestreiftes Hemd) mit denselben zwei Modi: Eli allein in Fullcam und
ein Browser mit Instagram-Post plus Facecam unten rechts. Die Signatur misst
wie bei `MARLI_PHONE` Struktur statt Pegel — links unten liegt in der Cam eine
glatte Wand, im Browser die Instagram-Navigation. Ueber 2833 Punkte: FULLCAM
0.61..1.76, BROWSER 2.68..9.93, dazwischen kein einziger Wert. Die Helligkeit
trennt nicht, beide liegen bei 17..24.

Der Browser zeigt drei verschiedene Seiten, und nur eine passt zur Box: den
Hochzeitspost (ab 147.5 s Sidneys Foto), eine fussball.de-Tabelle mit der
Facecam **oben rechts** (246.4-249.0 s) und einen YouTube-Shorts-Player
(398-451 s). Dieselbe Grenze wie bei `COACHLIM_ABU_TIKTOK`: Die Signatur
erkennt "Browser", nicht "Post". Im Shorts-Player laeuft ein fremder Clip
genau des Moments, den `_003` zeigt — ein Beleg, dass die Stelle traegt, und
der Grund, sie nicht ein zweites Mal zu schneiden.

`FOTO_STACK` ist die Komposition von `REACT_STACK` mit anderen Massen: Die
Facecam ist vom OBS-Rahmen auf 1.91:1 beschnitten, das obere Panel deshalb
566 statt 606 hoch. Am gerenderten Frame liegt Sidneys Gesicht auf 900..1185,
der Follow-Knopf auf Fliege und Kragen (1267..1413), der Untertitel auf der
Brust. Mittig zwischen Naht und Band waere Gesicht — der Knopf steht immer
bei x=540 und darf laut `tests/test_overlays.py` nicht ueber die Headline.

### Vier Fehler an den Clipgrenzen, alle im QC unsichtbar

1. **Der Vorlauf kannte keine Bilder.** Das Intro endet mit einem harten
   Schnitt 0.04 s vor dem ersten Wort; 0.20 s Vorlauf zeigten zehn Bilder
   Intro — im ersten Bild, also im Vorschaubild. Ein zweiter Anfang lag im
   Rest einer 0.3-s-Ueberblendung von OBS. `schnitte.uebergaenge` misst die
   Schnitte aus Stage 04b jetzt bildgenau nach (ruhiges Bild 0.1..0.3 je
   Bildwechsel, Blende 3..9, harter Schnitt 30..40), und
   `snappe(sperren=...)` zieht Vor- und Nachlauf aus ihnen heraus. Das ist
   der Fehler aus dem BMW-Vlog vom 2026-09-06, jetzt im Code statt in der
   Handkontrolle.
2. **Der Nachlauf haengte Stille an.** "angreifen." steht im Transkript bis
   543.12 s, gesprochen ist es um 541.0 zu Ende, danach hat der Cutter 1.8 s
   stummgeschaltet. `snappe(pegel=...)` endet jetzt an der ersten Pause von
   0.2 s unter -50 dBFS hinter dem letzten Wort; eine einzelne leise Stelle
   ist nur eine Silbenluecke ("an-grei-fen" fiel auf -53). Das Ende wandert
   nur nach vorn. Vier von acht Clips hatten bis zu 2.5 s Stille am Ende.
3. **Dann fehlte das Wort der Pointe.** Mit dem ehrlichen Ende sah der letzte
   Cue aus wie ein vom Clipende abgeschnittener Fetzen und wurde verworfen —
   "passen.", "zusammen.", "verschieben.", "angreifen.". Ein kurzer letzter
   Cue haengt jetzt am Cue davor, wenn kein Satzende dazwischenliegt; nur ein
   neuer Satz bleibt draussen. Spiegelbildlich standen Woerter, die vor dem
   Clip gesprochen waren, im ersten Cue ("Sternen, ob Sydney Friede"), weil
   ihr Transkriptende bis zum naechsten Wort reicht. Sie fallen jetzt raus.
4. **Die Hookpruefung las YouTubes Schreibweise.** Die ASR schreibt
   "Sydney", Titel und Headline "Sidney" — jede Headline mit dem Namen galt
   als lose. `hook.pruefe` wendet jetzt dieselben Korrekturregeln an wie die
   Untertitel (`untertitel.korrigiere_text`).

Was bleibt: Wo zwei Woerter ohne Pause ineinanderlaufen, erreicht kein
Wortzeitstempel den Verschluss dazwischen. Bei `_007` liegt er in
10-ms-Fenstern gemessen bei 627.09..627.13 s ("aus" | "Guck"); das Ende sitzt
bei 627.03 im "s", weil der naechste erreichbare Punkt (627.19) ein "G"
mitnaehme. Und `clip rangliste` rechnet ohne Video, also ohne beide Zusaetze:
Dort ist `_005` 77.8 s lang, gerendert 74.8 s.

Nicht geschnitten, mit Grund: die Erklaerung Standesamt gegen Feier
(333-393 s, kein Lacher, Regel 1c), "Sie ist ein Phantom" (555-595 s, "diese
Person" verweist auf den Clip davor, Regel 1a) und die Fotostrecke 628-675 s
(Karussell, kein Lacher).

### Nachtrag 2026-09-12: Among Us bei EliasN97 — drei Bilder, die Signatur trennt eins

Vermessen an 8haLC71kEDg ("WIEDERWAERTIGER LETZTE REIHE SQUAD! Among Us Chaos
mit Mert, Coach, Danny & Co.", Kanal EliasN97, 3878 s, 1920x1080@60). Profil
`ELIASN97_AMONGUS`, Templates `ELI_SPIEL_STACK` und `FULLCAM_169`.

Im Spiel sitzt Elis Facecam als Bild im Bild unten mittig, im selben silbernen
OBS-Rahmen mit FOKUS-Plakette wie bei `ELIASN97_STREAM`. Der Rahmen ist oben
dicker als an den Seiten, die Plakette ragt unten ins Bild; die Box
`[700,688,528,268]` liegt innen an allen Zierecken. Die Signatur ist die linke
Innenkante (x=696) und trennt ueber 7757 Punkte sauber: Median 114.6 im Spiel,
22 % unter 12.

**Fullcam und Browser sind fuer die Signatur dasselbe.** Zwischen den Runden
zeigt der Stream Eli im Vollbild, das Gluecksrad oder das Streamlabs-Dashboard;
die beiden letzten mit der Facecam unten LINKS. Unterschieden werden sie hier
an der rosa Abo-Ziel-Box: in Fullcam oben links, sonst oben mittig. Gemessen
alle 0.5 s: Fullcam 3248.0-3357.5 s, davor Dashboard, danach Rad. Die Box
rutscht dazwischen kurz aus dem Bild (3253.0-3254.5) — das ist kein Wechsel.

Zwei der besten Stellen enden deshalb vor ihrem Lacher: "Aufmerksamkeitsspanne
von 8 Sekunden" vor "Poet werden" (Rad ab 3357.5), "Ein Alibi braucht nur ein
Moerder" vor dem Lacher bei 3616 (Spiel endet 3602.5). Die Mitspieler sind nur
im Ton; wo einer auf die Webcam eines anderen reagiert ("Er schwitzt, sein
Gesicht ist rot"), sieht der Zuschauer nur Eli.

**Vier Grenzen lagen im Wort, alle im QC unsichtbar.** Nachgemessen in 10- und
50-ms-Fenstern an jeder Grenze des Entwurfs, beide Segmente je Clip:

- `_004` endete bei 3356.51 mitten in "jetzt?" (-16 dB; die Senke kommt erst
  bei 3356.66), der Hauptteil von `_003` bei 3598.51 in "Ja". Beide Enden
  liegen jetzt in der gemessenen Senke.
- Der Teaser von `_005` endete bei 3304.91, 0.35 s in "Richtig". Das naechste
  Wortende zum gewuenschten Ende war das eines `[gelaechter]`-Markers, und
  Marker waren von der Pegelmessung ausgenommen. `snappe` misst jetzt auch
  dort, aber nur eine Luecke, die in den letzten 0.5 s des Markers beginnt
  (`MARKER_AUSKLANG`) — die Stille mitten im Marker kann das Lachen sein.
- Der Hauptteil von `_002` begann 0.25 s in einem gerufenen "Wo ist Maus?",
  das YouTube gar nicht transkribiert hat; im Transkript steht dort nur das
  ueberlange "safe." des Ereignisses davor.

Die Schnittsperre zog das Ende von `_001` vor "Cam" (486.17), weil 0.1 s
spaeter "GAME COMPLETE" einblendet. Der Wechsel liegt nur im Spielpanel, die
Facecam laeuft durch — gerendert ist deshalb mit `--ohne-schnittpruefung`.

Was bleibt: `snappe` kennt als Einsatz nur Stille unter -50 dB, keine Senke.
Wo zwei Woerter nur durch ein Tal getrennt sind, beginnt ein Segment deshalb
0.20 s vor dem Wort, auch wenn das im vorigen liegt. Beim Hauptteil von
`_005` faellt das mit der OBS-Blende vom Dashboard in die Fullcam zusammen
(3247.73-3247.93): Er beginnt mit 0.08 s ausklingendem "Okay".

### Nachtrag 2026-09-13: Essens-Vlog bei AbuGoku — kein Marker, der Lacher steht im Bild

Vermessen an OUR-LdR97fE ("ALI ZEIGT MIR DIE BESTE KÖFTE IN BERLIN", Kanal
AbuGoku, 1046 s, 1920x1080@59.94). Profil `ABUGOKU_VLOG`, Template
`FULLCAM_169`.

Einmodig wie der Tuersteher-Vlog (staerkste persistente Spalte 6.0 gegen
Median 3.9, Zeile 6.0 gegen 4.6, nie geletterboxt), aber anders als dort
**montiert**: Totale auf den Tisch, Nahaufnahmen, Essen von oben. Die
Einstellung wechselt alle paar Sekunden, der Gegenstand nicht. Gerendert ist
deshalb MIT Schnittpruefung — sie haelt die Grenzen aus den Uebergaengen
heraus, und die gemeldeten Wechsel im Clip sind Kamerawechsel im selben
Gespraech, kein zweiter Gegenstand (Regel 1b). Werbung (Wolt, Einblendung
"Code: ABU") liegt bei 525-543 s.

**Kein einziger Marker in 3171 Woertern, und der Pegel ersetzt ihn nicht.**
Vier Stimmen am Tisch plus Strasse, kaum eine wortlose Stelle. Jeder der fuenf
Lacher ist am Standbild belegt (Kontaktbogen genau an der Pointe), nur einer
auch im Ton: Nach "Ihre Bestellung ist da" zeigt der 10-ms-Pegel bei
156.7-157.7 s Stoesse im Abstand von 0.2 s mit Taelern dazwischen — das Muster
von Lachen, in 0.1-s-Fenstern nicht zu sehen. Und das Bild entscheidet auch
andersherum: Beim Trainingsanzug (942-982 s) lacht der Tisch laut, aber ohne
Bild ist nicht zu verstehen, wer wem was angetan hat. Der Kandidat fiel nach
Regel 1a weg.

**Der Ingest hat sich wieder bewegt.** Am 2026-09-13 lieferte
`player_client=web_embedded` nur noch Vorschaubilder (n-Challenge ungeloest),
`tv` brach ab, `android_vr`, `mweb` und `ios` hatten kein 1080p-avc1. Der
Default-Client ohne Extractor-Args lud Format 299 (1080p60 avc1) vollstaendig.

**Drei Grenzen lagen im Wort, alle erst am Pegel sichtbar:**

- Der Teaser von `_003` endete auf "Krass, das heißt,". Hinter "Krass" liegt
  gemessen eine Luecke (347.00-347.34, -29..-32 dB), aber `snappe` erkennt sie
  nicht — auch dann nicht, wenn das gewuenschte Ende genau in ihr steht. Das
  json3-Ende von "Krass" reicht bis 347.80, und das Tal wird gegen das laute
  Viertel seiner Umgebung gemessen. Die ist hinter dem Ausruf selbst leise
  (Lachen, Atmen): p75 -20.9, Tal-Grenze also -30.9, die Luecke bei -29.2 —
  1.7 dB zu wenig. **Eine Luecke in leiser Umgebung ist fuer `snappe` kein
  Tal.** Geendet wird jetzt ueber das Wort davor: Ein gewuenschtes Ende bei
  346.95 snappt auf "sie." (346.56), die 0.35 s Nachlauf enden bei 346.91 —
  "Krass" ist drin, "das heißt" nicht. Der Pegel kann das Ende nur nach vorn
  ziehen, deshalb muss der Nachlauf des Wortes davor schon passen.
- Der Teaser von `_001` begann mit "sagt,": 0.20 s Vorlauf vor "ich" (52.28)
  lagen in "sagt" (51.90-52.19). Verankert ist er jetzt am Wort danach
  ("weiß", 52.36); der Vorlauf endet dann in der Luecke dahinter.
- Der Hauptteil von `_002` begann in "Berlin": Bei 124.2 laufen "Berlin",
  "Krass" und "Ali" ohne Luecke ineinander. Er beginnt jetzt zwei Saetze
  frueher in der Luecke nach "wissen." (122.14).

`clip rangliste` kennt den Teaser nicht und meldet dort "VERRAET", wo das
Kurzformat die Pointe absichtlich zuerst zeigt. Beim Rendern prueft
`hook.pruefe` mit Teaser und meldet es nicht.

### Nachtrag 2026-09-13: TikTok-Reaction #22 — Farbe statt Kante, und gemischte Clips

Vermessen an gRvhvBJExEE ("COACH RUFT SEINEN VATER AN WEIL ALBERT EINSTEIN
ALBANER IST", TikTok reaction #22, Kanal Coachlim Reactions, 1020.5 s,
1920x1080@59.94). Profil `COACHLIM_TIKTOK_WEB`, Templates `FULLCAM_169` und
`REACT_STACK`. Zehn Clips.

**Das Profil vom 2026-09-04 passt auf dieselbe Serie nicht mehr.**
`COACHLIM_TIKTOK_REACT` erkennt REACT an der rechten Playerkante x=1076 —
hier liegt dort nie eine. Ueber 17 TikTok-Bilder steht nur die Cam fest
(x=1226, y=689); der Player sitzt je nach Beitrag woanders, der
Merkel-Foto-Beitrag reicht von x=438 bis 1199. Und das Video hat vier Bilder
statt zwei: TikTok mit Cam, andere Webseite mit Cam (Kuschel-Anbieter, Berner
Zeitung, KI-Antwort), Webseite ohne Cam (Google), Coach allein.

**Fullcam erkennt die Farbe, nicht die Helligkeit.** Die Helligkeit der
linken Flaeche hielt 602-753 s fuer Fullcam; darin liegen 52 s Google und
Berner Zeitung, beide dunkel wie das Zimmer. Coachs Zimmer ist lila:
(Blau - Gruen) ueber [80,250,340,650] liegt in Fullcam bei 54..80, sonst unter
10, ueber 4078 Punkte zweigipflig. `ModusSignatur` kann keine Farbe — die
Clips sind gegen diese Messung gelegt, nicht gegen die Signatur im Profil.

**Die besten Stellen wechseln mitten im Gedanken das Bild.** Coach sieht ein
TikTok und schimpft danach in der Fullcam. Ein Clip hat ein Template: Ein
`REACT_STACK` schnitte in der Fullcam Coachs Zimmer als "Player" zurecht, ein
`FULLCAM_169` zeigt das TikTok nur kleiner. Vier der zehn Clips laufen deshalb
ganz in `FULLCAM_169` — das ist die Abwaegung Kontext gegen Bildgroesse, und
der Kontext gewinnt (Regel 1a). Nur der Merkel-Clip liegt ganz im TikTok und
bekommt `REACT_STACK`.

Nicht geschnitten, mit Grund: "Christin, Alhamdulillah" (213-245 s, zwischen
TikTok und Reaktion 11.7 s ohne ein Wort, Regel 5), "Knast wegen Datenschutz"
(190-212 s, mit Kontext keine 30 s), Georg auf dem Sofa (523-551 s, der Witz
ist zu explizit).

### Nachtrag 2026-09-15: der erste Twitch-VOD — ASR braucht eine eigene Zeitachse

Vermessen an dwitch_j9snk5q6 (Coachlim-Twitch-Stream, vom Nutzer als Datei
geliefert, 3599.7 s, 1920x1080@60). Profil `COACHLIM_TWITCH`, Templates
`FULLCAM_169` und `REACT_STACK`. Zwoelf Clips.

Drei Bilder, alle 0.25 s ueber 14382 Punkte vermessen (`flaechen_serie.py`):
Fullcam im lila Zimmer, TikTok im Browser mit Cam unten rechts (648-1637 s,
Player exakt die Box von `COACHLIM_TIKTOK_REACT`) und ein Discord-Splitscreen
(1768-1833 s, 2032-2139 s). Keine einzelne Flaeche trennt alle drei; die
Signatur im Profil trennt nur "TikTok-Seitenleiste" von "Rest", die Clips sind
gegen die Flaechenmessung gelegt. **Twitch hat 899.7-1081.4 s stummgeschaltet**
— digitales Null (Peak -inf) ueber 181.7 s, waehrend Coach redet. Genau der
Fall, den der Twitch-Abschnitt unten vorhersagt; `silencedetect` findet ihn in
Sekunden, dort wird nichts geschnitten.

**Der eigentliche Aufwand war die ASR, und keiner ihrer vier Fehler war am
Transkript zu erkennen.** Jeder sah aus wie ein brauchbarer Text:

1. **Schleifen.** Mit Textkontext blieb whisper.cpp nach Musik und Stille haengen
   ("Warte." 60-mal, "Wallah." 29-mal) und schleppte das ueber gesprochene
   Strecken — Minute 15-21 und 50-59 hatten 4-11 Woerter je Minute. `-mc 0`.
2. **Drift ueber die Stunde.** In einem Lauf lag die Zeitachse 5-13 s daneben;
   Woerter standen in gemessener Stille. Seither in Stuecken unter 30 s, in
   Pausen geschnitten (`asr.stuecke`), alle in einem Aufruf.
3. **Auch in Stuecken sind Whispers Segmentzeiten falsch** — bis 12 s, und am
   Stueckende stapelten sich 1428 von 4647 Woertern auf einer Zeit. Die
   Wortzeiten kommen jetzt aus DTW je Token (`-dtw large.v3.turbo`). **Das geht
   nur mit `-nfa`:** Mit Flash-Attention liefert whisper.cpp fuer jeden Token
   -1, ohne jede Meldung. DTW folgt der Lautheit, liegt aber systematisch
   0.15-0.6 s hinter dem Einsatz; `snappe._einsatz` holt das zurueck, wo davor
   Stille liegt. Wo Musik darunter liegt, bleiben die 0.2 s Vorlauf.
4. **Whisper laesst Rede aus, und nicht jedes Mal dieselbe.** Das Setup des
   Zitat-Clips ("Kein Zitat trifft mich ...") fehlte im Stundenlauf, in einem
   frueheren Lauf war es da. `werkzeuge/asr_fenster.py` transkribiert jedes
   Clipfenster ein zweites Mal, legt beide Fassungen nebeneinander und setzt die
   bessere ein. Von zwoelf Fenstern war die zweite Fassung achtmal besser und
   viermal schlechter ("kracken" statt "kacken", "Tod oder Tod?") — deshalb
   entscheidet der Vergleich, nicht der Code.

Dazu: Whisper schreibt Geraeuschangaben in den Text ("*Klatschen*",
"* Musik *"). Sie werden jetzt zu Markern und stehen damit nicht im Untertitel.
Die Stunde braucht so 11.5 min auf dem M4.

**Die DTW-Verspaetung trifft `snappe` genau dort, wo keine Stille liegt.**
`_einsatz` findet den Toneinsatz nur hinter Stille unter -50 dB (zwei
50-ms-Fenster), `_luecke` verwirft ein Tal, das vor Wortanfang + 0.1 s
beginnt — und mit einem zu spaeten Wortanfang liegt das echte Tal genau dort.
Im Entwurf lagen so vier Grenzen im Wort, am schlimmsten I1 und I2
(`_009`/`_010`): "Alleine" setzt bei 1591.93 s ein, DTW sagt 1592.18, die
einzige Senke ist 1591.82-1591.92 — `_009` endete 0.4 s in "Allei-". Fuer
diesen Lauf sind sieben Wortanfaenge im Transkript von Hand an den gemessenen
Einsatz gerueckt ("Kein" 1277.85, "Von" 856.60, "Hat" 1149.30, "Bruder."
1591.55, "Alleine," 1592.08, "getan." 1428.85, "nicht." 259.50; das
Transkript liegt deshalb unter `data/artifacts/`). Dazu eine Falle in
`_luecke`: Liegt das gewuenschte Ende in einem Stillefenster, das kuerzer als
`STILLE_MIN` ist, gibt es keinen Schnittpunkt — auch keinen Tal-Schnitt. Das
Ende von `_009` steht deshalb auf 1591.82 (Tal) statt 1591.87 (50 ms Stille).
Und ein Ende in einer langsam ausklingenden Senke nimmt deren TIEFSTEN Punkt,
nicht ihren Anfang: Bei `_006` klingt "getan" ab 1429.05 aus, `snappe` schnitt
bei 1429.62 — 0.4 s in den Wisch zur 2013-Folie, am fertigen Clip klar zu
sehen. Gewuenscht ist deshalb das Wortende davor ("nicht"), und die 0.35 s
Nachlauf enden genau vor dem Wisch: Der beginnt bildgenau bei 1429.033 s
(Differenz im Player-Ausschnitt, 60 Bilder/s), "getan" klingt bei ~1429.06
aus. **Mit Schnittpruefung ging das nicht:** `schnitte.uebergaenge` misst den
Uebergang am GANZEN Bild, samt TikTok-Seitenleiste, und `_aus_uebergaengen`
zog das Ende damit auf 1428.78 — vor "gut getan", der Clip endete auf "hat
Coach nicht". `_006` ist deshalb als einziger Clip einzeln ohne
Schnittpruefung gerendert; die des Fensters lief in drei Laeufen davor. Wie
die falschen Bildwechsel-Meldungen oben: gemessen wird das Bild der Quelle,
nicht das des Clips. Die eigentliche Loesung waere ein Einsatz auch im
Tal, nicht nur in Stille — die Luecke steht schon im Nachtrag vom 2026-09-12.

**Foto-TikToks brauchen eine andere Overlay-Lage als Video-TikToks.** Coachs
Glow-up-TikTok ist eine Diashow mit Jahreszahl und Bildunterschrift je Foto.
Mit `REACT_STACK` stand der Follow-Knopf auf Mund und Kinn und das
Untertitelband auf "Der dicke Bankwaermer" und "Coach war Stamm Spieler" —
beides am gerenderten Frame gemessen, nicht am Template. `REACT_FOTO_STACK`
(Modus `REACT_FOTO`, dieselbe Geometrie) setzt den Knopf links auf den
Oberkoerper und das Band zwischen Jahreszahl und Unterschrift; die Masse je
Folie stehen im Template.

Und `schnitte.finde` meldet im Browser-Layout Wechsel, die im Clip gar nicht
zu sehen sind: Bei 1423.25 s und 1461.0 s wechselte die TikTok-Seitenleiste,
im Player stand dieselbe Folie (am Kontaktbogen im 0.1-s-Raster geprueft).
Gemessen wird das ganze Bild, gerendert werden nur Player und Cam.

Was sonst bleibt: Was Whisper gar nicht hoert, kann `snappe` nicht treffen.
Hinter "fusioniert" sagt Coach einen tuerkischen Fluch ohne Transkript, ein
Ende dort haette auf dem naechsten Wort gelegen. Der Teaser von `_003` nimmt
deshalb den Satz danach.

Nicht geschnitten, mit Grund: die Songs der Discord-Anrufer (sexuell, das
Alter der Anrufer ist unbekannt), der Schueler, der von der Schule geflogen ist,
AZs erster Rap (explizit), die Scheidungsgeschichte (kein Lacher) und
"24-Stunden-VOD um 2 Uhr nachts" (Regel 1c: am Standbild lacht niemand).

### Nachtrag 2026-09-16: 1:1 Kaese mit grosser Facecam — Teaser und Einschub zusammen

Vermessen an I-mbVr4qgFs ("ZUSCHAUER WILL BEI EINER 19 JÄHRIGEN MUTTER KÄSE
LEGEN", Coachlim, 2291 s, 1920x1080@59.94). Profil `COACHLIM_KAESE_GROSSCAM`,
Templates `PHONE_STACK` und `FULLCAM_169`. Sechs Clips.

**Dasselbe Format, eine andere Geometrie.** Wie bei jd9bSJ7mshM teilen
Zuschauer ihr Snapchat und Coachlim diktiert, aber die Facecam ist
`[637,0,776,436]` statt `[706,0,680,382]` und der Chat beginnt bei y=438. Das
alte Profil haette die Cam seitlich angeschnitten und ihre Unterkante als
helle Linie in den Chat gelegt. Signatur und Einschubregel bleiben gleich;
die rechte Flaeche trennt ueber 9155 Punkte (6846 unter 1.0, 2265 ueber 30).
Die Handys der Anrufer sind verschieden breit (x=825..1288), die Box nimmt
das breiteste.

**Die Vollbild-Cam ist hier NICHT die verkleinerte Facecam.** Das Profil von
jd9bSJ7mshM stellt das fest, und der Einschub baut darauf. Hier hat die
Vollbild-Cam eigene Zoomschnitte: Die Kantenkorrelation zwischen Facecam und
Vollbild liegt bei 691 s bei 0.07, die Poster sind dort rund 1.3x groesser.
Fuer den Einschub reicht das — das obere Panel zeigt kurz die nahe
Einstellung, wie im Original geschnitten. **Ein Punch-in in dieser Strecke
haette mit Facecam-Koordinaten aber eine falsche Stelle aus dem Vollbild
geschnitten.** `kurzformat.punch_im_einschub` teilt den Zoom deshalb an den
Einschubgrenzen und nimmt innen die Ersatzzone; ein gehaltenes Panel zoomt
dort nicht und wird gemeldet.

**Teaser und Einschub gingen bis heute nicht zusammen** — `cmd_rendere`
lehnte jeden Plan mit Teaser ab, sobald das Template Einschuebe kennt, also
jeden `PHONE_STACK`-Clip im Kurzformat. Beim Kaese-Format ist die Vollbild-
Strecke aber fast immer die Reaktion. Jetzt misst `cmd_rendere` die Einschuebe
je Segment; die Fenster stehen wie der Punch-in auf der Clipachse und nennen
ihr Segment, `halten_bei` bleibt in Segmentzeit. `filtergraph_teile` legt sie
je Buehne unter den Punch-in; die Haltebilder kommen als Eingaenge nach den
Videos und vor den PNGs.

**Ein Kontaktbogen kann Kacheln verwechseln.** Die Uebersicht zeigte bei
1300, 1708, 1868 und 2074 s scheinbar ein Schwarzbild mit "LIVE ... 1zu1
käse spielt EA Sports FC 26". Die Messreihe sagte an allen vier Stellen
Chatlayout, und drei Abrufmethoden (Suche vor/nach `-i`, `select`) zeigten
dasselbe Bild: Die Zeile ist eine Titelleiste ueber dem Chat, und die Kachel
daneben trug das Bild. Wo Messung und Kontaktbogen sich widersprechen, das
Einzelbild in voller Aufloesung holen.

**Der Chat entscheidet, was die Pointe ist.** Im Transkript stand beim
Katzen-Clip nur "hat viel Blut verloren die Arme, schick ab" — wer was
schreibt, stand erst im Bild: Sie schreibt, die Katze haette die OP fast nicht
ueberlebt, und direkt darunter geht "Brauchst du eine kleine Kuschel Einheit
zum aufmuntern" raus. Ihre Antwort "Haette nix dagegen :)" ist der Phoenix aus
der Asche. Bei diesem Format die Chatzone ausschneiden und lesen, bevor die
Grenzen stehen.

**Fuenf Grenzen lagen im Entwurf falsch, alle erst in der Grenzkontrolle
sichtbar.** Die lehrreichste: Hinter "also da kannst krachen [schreien]"
liegen 0.5 s Stille (139.05-139.53), dann "Warum macht die nicht Schluss". Der
Marker reicht im Transkript bis 139.56, die Stille beginnt 0.51 s vor seinem
Ende — `MARKER_AUSKLANG` liess bis dahin nur 0.50 s zu, und der Clip endete
in "Warum macht". Die Schranke steht jetzt auf 0.6 (Test
`test_stille_hinter_einem_schrei_marker_ist_das_ende`). Die anderen vier
waren Anfaenge und Enden ohne Luecke im Ton ("mir doch mal", "Dann", "Warte
mal", "stimmt."); sie sind ueber benachbarte Woerter mit echter Stille neu
verankert, nicht im Code geloest.

**Eine Falle beim Gegentest:** Wer eine Konstante per `sed` umstellt, den Test
laufen laesst und in derselben Sekunde zuruecksetzt, bekommt von Python den
alten Wert — die `.pyc` gilt als aktuell, weil Groesse und Zeitstempel (in
Sekunden) gleich sind. Die Nachrechnung von `snappe` lief mit 0.5, obwohl 0.6
in der Datei stand. Nach so einem Hin und Her `__pycache__` loeschen.

Nicht geschnitten, mit Grund: alles ab 1830 s, wo ein Anrufer mit Ausweis
beweisen will, dass er nicht 17 ist, und ein anderer mit einer 17-Jaehrigen
schreibt ("Willst du in Knast?") — Minderjaehrige plus Sexuelles, egal wie
laut gelacht wird. "Mach Stream aus" (1490-1640 s, das Handy ist aus, ohne den
Chat versteht man nichts, und kurz danach "Du bist 17, nein 19"). "Du hilfst
mir geschlagen zu werden" (1030-1090 s, Regel 1c: am Standbild lacht niemand).
Die Dessous-Anspielung bei 1146 s (Vollbild-Strecke 11.5 s, `PHONE_STACK`
ueberbrueckt hoechstens 10 s, und ohne `_002` fehlt der Kontext).

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

- **Auf einem Reaction-Video wählt YouTubes ASR die Sprache des REAGIERTEN
  Videos, nicht die des Kanals.** Gemessen am 2026-09-08 an JtWRKErMIGc
  ("20 FRAUEN VS RAPPER QUAVO", Kanal Coachlim Reactions): Es gibt **kein
  `de-orig`**. Angeboten werden `en-orig` — das Original, also die englische
  Show — und `de`, eine Maschinenübersetzung davon. Beide enthalten den Dialog
  der Show; der deutsche Kommentar des Creators, also das eigentliche Produkt,
  steht in keinem von beiden. Stichproben aus `en-orig` bei 120 s, 400 s,
  800 s und 1200 s: 3528 Wörter, **kein einziges Deutsch**.

  Das ist kein Downloadfehler, den ein anderer Sprachcode behebt — die
  Tonspur ist zweisprachig und die ASR hat sich für die dominante entschieden.
  Ein Transkript ohne den Kommentar ist hier wertlos: Stage 06 sucht die
  lustigen Stellen durch Lesen, und Untertitel sind Pflicht in jedem Clip.

  **Damit ist die eigene ASR aus dem Fallback ein Regelfall geworden** und in
  `asr.py` implementiert (`clip transkribiere`, whisper.cpp als Subprozess wie
  FFmpeg). Sie schreibt `json3`, nicht ein eigenes Format — `lade_json3` liest
  es dann unverändert und keine spätere Stage merkt, woher das Transkript
  kommt. Prüfe bei jedem Reaction-Video **vor** dem Download, ob `de-orig`
  überhaupt angeboten wird: `yt-dlp --list-subs` kostet Sekunden, der Fehler
  fällt sonst erst in Stage 03 auf.

  **Und die eigene ASR loest das Problem nur halb.** Auf JtWRKErMIGc
  gemessen: whisper.cpp mit `-l de` transkribiert nicht den deutschen
  Kommentar, sondern **uebersetzt** den englischen Showton ins Deutsche —
  "Ja, weil wenn ich einen Hügel gebe, ist es wie ein Ja" ist kein Satz des
  Creators, sondern eine Fehluebersetzung. Nur 8 % der 1418 Woerter sind
  ueberhaupt deutsche Funktionswoerter, und stellenweise haengt der Decoder
  in Wiederholungsschleifen (17-mal "Hey" am Stueck). `-l auto` mit
  Beam-Search 5 liefert **wortgleich** dasselbe — es liegt nicht an den
  Parametern, sondern daran, dass der Showton den Kommentar ueberdeckt.

  Konsequenz fuer das Rendern: Gerendert wurde mit **`en-orig`**, also
  YouTubes eigener ASR der Show. Die ist sauber (3528 Woerter, 2,24 W/s,
  27 wiederholungsfreie 30-s-Fenster gegen 5 im ASR-Transkript) und
  untertitelt das, was im Clip tatsaechlich zu hoeren ist. Headline deutsch,
  Untertitel englisch — richtige fremdsprachige Untertitel sind besser als
  falsche deutsche. Der ASR-Lauf bleibt trotzdem richtig: Er hat die Frage
  ueberhaupt erst entscheidbar gemacht.

  Whisper schreibt **keine** `[gelächter]`-Marker. Bei ASR-Material gehört
  `lachmarker` im Profil deshalb zwingend auf 0 — derselbe Fall wie bei den
  drei markerlosen YouTube-Transkripten.
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

**Seit dem 2026-09-08 eine Klickszene, keine Pille.** Der runde Folgen-Knopf
der App — roter Kreis `#FE2C55` mit weissem Plus — poppt auf, ein Mauszeiger
faehrt von rechts unten herein, drueckt ihn, und der Knopf wird mit einem
nach aussen verpuffenden Ring weiss und traegt einen Haken. Danach faehrt der
Zeiger wieder hinaus und der Knopf poppt weg. Rund 3 s. Entscheidung des
Nutzers; die Wahl zwischen Textpille, rundem App-Knopf und Pille mit
Plus-Icon wurde ihm vorgelegt.

**Was das ueber den Renderpfad sagt, ist der eigentliche Punkt.** Es gibt
genau ein Mittel: ein PNG, geschaltet ueber `enable`, mit Ausdruecken fuer x
und y. Daraus folgt die Aufteilung zwangslaeufig:

| | |
|---|---|
| **Bewegung** | ein Ausdruck. Der Zeiger ist EIN Bild, das ueber x/y faehrt — kostet einen Eingang, wie die alte Pille. |
| **Groesse und Zustand** | Bilder. `scale` laesst sich nicht ueber die Zeit ausdruecken; Pop, Druck und Wegpoppen sind eine FOLGE kurz geschalteter Standbilder, 1-2 Frames je Zustand. |

Das sind 23 Eingaenge statt einem. Vertretbar, weil sie klein sind und
`enable` sie ausserhalb ihres Fensters nicht komponiert — die Untertitel
eines 47-s-Clips bringen zum Vergleich 39 mit.

Drei Dinge, die beim Bauen nicht offensichtlich waren:

- **Der Klickring muss groesser sein als der Knopf.** In der ersten Fassung
  lag der erste Ringzustand bei 1.10 gegen einen Knopf bei 1.16 — also
  darunter und unsichtbar. Und seine Deckkraft lief linear auf **null** aus,
  womit der letzte Ringzustand ein leeres Bild war. Von drei Ringzustaenden
  war einer zu sehen.
- **`between` schliesst beide Raender ein.** Ohne 1 ms Abzug am Ende jedes
  Zustandsfensters sind an der Nahtstelle zwei Knoepfe verschiedener Groesse
  gleichzeitig aktiv.
- **Ein Exponent von 3 sieht aus wie ein Hänger.** Beim Anflug des Zeigers
  sind mit `pow(1-p,3)` bei halber Zeit schon 87 % der Strecke zurueckgelegt;
  der Rest kriecht. 2.2 verteilt die Bewegung sichtbar und bremst trotzdem ab.

Der Knopf ist mit 150 px Kantenmass deutlich groesser als die alte Pille
(94 px) und passte deshalb in mehreren Templates nicht mehr an seinen Platz.
`COUCH_FULL`, `VLOG_FULL` und `FULLCAM_169` ruecken von 582 auf 620,
`REACT_STACK` von 760 auf 790. **`OME_SPLIT` bekommt einen kleineren Knopf**
(64 px statt 112): Frei ist dort nur das Wandband zwischen Headline und
Untertitelband, gemessene 124 px — und ein Woanders gibt es nicht, weil
ober- und unterhalb Gesichter stehen.

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
| Follow-Knopf | 1215..1365 |
| Untertitelband | 1424..1688 |
| UI-Zone ab | 1728 |

`TOP5_COUNTDOWN` ist der einzige dokumentierte Ausnahmefall: Untertitel
`aktiv: false` mit Grund — die Segmente kommen aus bis zu fuenf Quellen,
deren Transkripte der `CountdownPlan` gar nicht mitfuehrt; der Textkanal des
Formats ist die mitwachsende Liste. Der Follow-Knopf sitzt trotzdem drin, tiefer
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

### `hook.pruefe` setzt voraus, dass Headline und Transkript dieselbe Sprache sprechen

Gemessen am 2026-09-08 an JtWRKErMIGc. Bei einem Reaction-Video auf eine
fremdsprachige Quelle ist das nicht mehr gegeben: Die Headline ist deutsch
(der Kanal ist deutsch), das Transkript des Clipfensters englisch (die Show
ist englisch). `hook.pruefe` vergleicht Headline-Woerter gegen den Wortlaut
des Fensters und meldet dann **jede** Headline als "lose" — kein Wort kommt
im Clip vor.

Das ist ein Fehlalarm, kein Befund, und er ist nicht harmlos: "lose" ist laut
demselben Abschnitt der teurere der beiden Headline-Fehler. Wo Headline und
Ton verschiedene Sprachen haben, sagt der Test nichts aus und die Meldung
gehoert ignoriert. Ein echter Verrat waere in diesem Aufbau ohnehin nur
sichtbar, wenn man die Headline gegen eine Uebersetzung prueft — und die hat
die Pipeline nicht.

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

## Ablage der Ergebnisse — ein Lauf, ein Ordner, ab 2026-09-08

Bis hierher schrieb jeder Renderlauf flach in `<work>/clips/`. Nach acht
vermessenen Videos lagen dort **206 Eintraege** aus einem Dutzend Laeufen, und
weil MP4, EditPlan und Headline-PNG desselben Clips sich den Namensstamm
teilen, standen sie auch noch verschraenkt:

```
4ubrGJLb4FQ_001.editplan.json
4ubrGJLb4FQ_001.headline.png
4ubrGJLb4FQ_001.mp4
4ubrGJLb4FQ_002.editplan.json
...
```

Welcher Lauf welchen Clip erzeugt hat, stand danach nur noch im Zeitstempel
der Datei. Und wer die fertigen Clips aufs Handy ziehen wollte, musste sie aus
den Zwischenschritten heraussuchen — bei drei Dateien je Clip sind zwei davon
Ausschuss fuer diesen Zweck.

Deshalb bekommt jeder **Aufruf** einen eigenen Ordner, benannt nach seinem
Startzeitpunkt, und darunter liegen die Dateitypen getrennt:

```
clips/2026-09-08_14-30-15/
  mp4/    die fertigen Clips
  json/   EditPlans + lauf.json
  png/    Headline, Untertitel, Follow
```

Die drei Ordner trennen nicht Dateiendungen, sondern **Lebensdauern**:

| | |
|---|---|
| `mp4/` | verlaesst den Rechner — am Stueck kopierbar, ohne Beifang |
| `json/` | ueberlebt die Videodateien: welcher Ausschnitt, welche Headline |
| `png/` | reiner Zwischenstand, jederzeit loeschbar — der Renderer baut ihn neu |

`png/` ist der Grund, warum die Trennung mehr ist als Ordnungsliebe: Ein Clip
mit 23 Untertitel-Cues erzeugt 25 PNGs und **eine** MP4. Flach abgelegt sind
96 % der Eintraege im Ordner Zwischenstand.

**Ein Lauf ist der Aufruf, nicht das Video.** Werden zwei Videos in einem
Rutsch geschnitten, gehoeren ihre Clips zusammen — sie entstehen aus derselben
Absicht und werden am selben Tag gepostet. Die Zuordnung zum Video steckt
ohnehin in jedem Clipnamen und zusaetzlich in `lauf.json`.

Zwei Entscheidungen im Ordnernamen, beide nicht kosmetisch:

- **Kein Doppelpunkt.** ISO-Zeit waere `14:30:15`; `:` ist auf Windows in
  Dateinamen verboten, und das Repo laeuft auf beiden Maschinen.
- **`%Y-%m-%d_%H-%M-%S`, nicht `%d.%m.%Y`.** So sortiert der Ordnername als
  Text chronologisch, und `ausgabe.zuletzt` muss die Namen nicht parsen.

Faellt ein zweiter Lauf in dieselbe Sekunde — zwei Aufrufe aus einem Skript —,
bekommt er ein `_2` angehaengt. Ein Lauf ueberschreibt nie einen anderen; das
waere genau der alte Zustand, nur mit Ordnern drumherum.

`--ausgabe` benennt seither den **Basisordner**, nicht das Ziel selbst. Der
Altbestand in `clips/` bleibt unangetastet liegen: `ausgabe.zuletzt` erkennt
einen Lauf am `mp4/`-Unterordner und uebergeht alles andere.

### Twitch

- **Keine Untertitel, keine Audio-Ereignisse.** ASR ist auf diesem Pfad Pflicht, und
  damit auch der Lachmarker-Ersatz: Gelächter muss aus dem Audiosignal kommen, nicht
  aus dem Transkript. Die Signalgewichte im Materialprofil müssen das abbilden.
- **VODs sind vergänglich** (je nach Kanalstatus etwa 7 bis 60 Tage — vor dem
  Produktivbetrieb gegen die aktuellen Twitch-Bedingungen prüfen). Daraus folgt eine
  Priorität, die YouTube nicht hat: Ein VOD, das bald abläuft, wird zuerst geholt.
  Das gehört in die Job-Priorisierung, nicht in einen Cronjob nach Gefühl.
- **DMCA-Stummschaltungen**: Twitch schaltet Audio bei erkannter Musik stumm — teils
  minutenlang. Solche Bereiche zerstören ASR und Momenterkennung lautlos. Sie müssen
  vor der Kandidatenbildung erkannt (durchgehende digitale Stille bei laufendem Bild)
  und ausgeschlossen werden.
- **Twitch-Clips sind ein geschenktes Signal.** Die Community erstellt selbst Clips der
  besten Momente, mit Viewcount und Zeitbezug zum VOD (`twitch:clips` in yt-dlp). Das
  ist erstens ein kostenloser Momentdetektor und zweitens die Lösung für das
  Kaltstartproblem beim Ranking: echte Popularitätsdaten statt geratener Scores.
  Vor eigener Detektion immer zuerst prüfen, ob Clips existieren.

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
