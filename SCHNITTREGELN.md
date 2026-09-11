# Schnittregeln — gelten bei JEDER Clip-Erstellung

Diese Datei ist die Auftragslage des Nutzers, nicht eine Messung der Pipeline.
Sie steht ueber jeder Heuristik im Code: Wo `candidates.py` einen Lautheitspeak
meldet und diese Regeln widersprechen, gewinnen diese Regeln.

**Vor jedem Renderlauf abarbeiten. Jeder einzelne Clip muss alle fuenf Regeln
erfuellen, sonst wird er nicht gerendert.**

Grundlage ist die Rueckmeldung vom 2026-09-08 zu neun ausgelieferten Clips —
sechs gut, drei schlecht. Die drei schlechten hatten *hoehere* AI-Scores als
zwei der guten (`6T-QuUKYy7w_006` stand mit 0.88 an der Spitze und war
unbrauchbar). **Der Selektionsscore misst also nicht, was der Nutzer bewertet.**
Was er bewertet, steht hier.

---

## Regel 1 — Es muss einen Grund geben dranzubleiben

Wortlaut des Nutzers: *"Es muss ein Grund geben warum der Zuschauer dran
bleibt. Deshalb Clippe die Sachen auch entsprechend angenehm und schreibe eine
gute Text Hook."*

Aus den drei Absagen laesst sich das in drei pruefbare Bedingungen zerlegen.
Alle drei muessen erfuellt sein.

### 1a — Der Clip traegt seinen eigenen Kontext

Begruendung des Nutzers zu `_006` und `_008`: *"Kein Kontext kein Inhalt"*,
*"Kein Kontext, man sieht nichts"*.

Der Clip muss ohne das Video davor verstaendlich sein. Konkret: In den ersten
Sekunden muss fallen oder zu sehen sein, **worauf** reagiert wird. Ein Clip,
der mit einem Kommentar auf etwas Ungezeigtes einsteigt, ist ausgeschlossen —
egal wie laut gelacht wird.

Das ist der haeufigste Fehler und er entsteht mechanisch: `candidates.py`
pflueckt einen Lautheitspeak und legt das Fenster symmetrisch darum. Der
Aufbau liegt dann oft **vor** dem Fensteranfang. Der Anfang gehoert deshalb
nach vorne verschoben, bis der Aufbau drin ist — nicht das Fenster
symmetrisch gehalten.

Gegenprobe am guten Beispiel: `6T-QuUKYy7w_003` beginnt mit *"Warum warst du
im Fullscreen?"* — die Frage baut auf, die Pointe kommt danach.

### 1b — Der Clip endet auf der Pointe, nicht mittendrin

Begruendung zu `_007`: *"es faengt einfach ein neuer Chat im selben Clip an und
endet nichtmal"*.

Zwei Verstoesse in einem Satz, beide eigenstaendig ausschliessend:

- **Kein zweiter Gegenstand im Clip.** Wo ein Bildwechsel (`schnitte.finde`,
  Stage 04b) einen neuen Chat, ein neues TikTok, einen neuen Gespraechspartner
  bringt, ist der Clip vorbei. `clip rendere` meldet solche Wechsel; die
  Meldung ist bei diesem Material **nicht** optional, sondern ein Abbruchgrund
  fuer den betroffenen Clip. Ausnahme wie in CLAUDE.md beschrieben: die eigene
  Uebergangskarte des Kanals, in die ein Clip hineinlaufen darf.
- **Kein offenes Ende.** Der letzte gesprochene Satz muss zu Ende sein und die
  Sache abgeschlossen. Ein Clip, der auf halbem Satz oder vor der Reaktion
  aufhoert, ist keiner.

### 1c — Ein echter Lacher, kein blosser Lautheitspeak

Begruendung zu `_006`: *"kein wirklicher Lacher"*.

`[gelächter]` im Transkript oder ein Lautheitsmaximum reicht **nicht** als
Beleg. Vor der Selektion wird der Wortlaut des Fensters gelesen: Gibt es eine
Zeile, die fuer sich allein komisch ist? Wenn die Antwort nur "sie lachen
dort" lautet, faellt der Kandidat raus.

Bei `_008` lachte niemand, er sagte *"Okay, okay"* — und genau das steht im
Standbild. Ein Standbild aus der Mitte des Kandidaten wird angesehen, bevor
gerendert wird.

---

## Regel 2 — Layout je Format

Der Modus entscheidet das Template (Stage 04 + `layout.template_fuer`). Diese
Tabelle ist die Zuordnung, die der Nutzer vorgibt; sie ersetzt jede eigene
Abwaegung.

| # | Material | Komposition | Template | Stand |
|---|---|---|---|---|
| 1 | **1:1 Kaese** — Coachlim coacht Zuschauer beim Daten | Facecam oben, Chat in der Mitte, fett auf das Wichtigste | `PHONE_STACK` | steht auf `einpassen` mit Blurbalken — **noch nicht umgestellt**, siehe unten |
| 2 | **Gaeste in Fullcam** (auch Coachlim allein in Fullcam) | 16:9 vollstaendig zeigen, nichts beschneiden | `FULLCAM_169` | angelegt 2026-09-08 |
| 3 | **Gaming** | Facecam oben, Spiel unten mittig auf das Wichtigste | `GAME_STACK` | steht auf `einpassen` — dieselbe offene Frage wie Fall 1 |
| 4 | **Reaction auf TikToks** | Facecam oben, TikTok-Video auf volle Breite | `REACT_STACK` | auf `fuellen` umgestellt 2026-09-08 |
| 5 | **Top-5-Format** | mehrere Clips einer Kategorie, siehe Regel 2b | `TOP5_COUNTDOWN` | vorhanden |
| 6 | **Reaction auf YouTube-Videos** | vom Nutzer offengelassen | `REACT_YT_SPLIT` | vorhanden |

**Der untere Feed laeuft in diesem Hausstil von Kante zu Kante.** Gemessen am
2026-09-08 an zwei der genannten Referenzen, beide geladen und angesehen:
`@coachlim.clips25/7677675052585831713` (TikTok-Reaction) und
`@coachlim.clips5/7678435849457028384` (1:1 Kaese). In beiden reicht der untere
Feed ohne einen Pixel Blur bis an beide Bildkanten; die Facecam oben nimmt rund
600 px, die Headline sitzt auf der Naht. "Mittig und angepasst" heisst also
mittig **beschnitten**, nicht verkleinert.

`REACT_STACK` ist danach umgestellt. `PHONE_STACK` und `GAME_STACK` stehen noch
auf `einpassen` und sind bewusst nicht mitgeaendert: Ihre Quellgeometrie ist
eine andere (ein Handy ist 9:19.5, schmaler als die Buehne — dort schneidet
`fuellen` 40 % der Bildschirmhoehe weg statt Rand). Was dort richtig ist, wird
am naechsten Video dieses Typs gemessen, nicht hier vermutet.

Referenzen des Nutzers:

- Fall 1: `@coachlim.clips5/video/7678435849457028384`
- Fall 2: `@pxrzclipz/video/7681812382309420321`, `@coachlimtwitch/video/7662434031421639968`
- Fall 3: `@coach_yarram/video/7682917475842788641`
- Fall 4: `@coachlim.clips25/video/7677675052585831713`
- Fall 5: `@clips_deutschland65/video/7665108832602950944`,
  `@clippinghd765/video/7682367337378467105`,
  `@coachlim.clips5/video/7683161210300157216`,
  `@clippinghd765/video/7680175770270059809`

**Fall 2 ist eine Korrektur an `SOLO_FULL`.** Dessen Kopfkommentar begruendet
ausfuehrlich, warum die Vollbild-Cam auf 9:16 *beschnitten* gehoert ("der Kopf
bleibt gross, das ist der Punkt des Formats"). Der Nutzer will bei Fullcam mit
Gaesten das Gegenteil: alles zeigen. Der Grund ist derselbe wie bei
`COUCH_FULL` — sitzen mehrere Personen im Bild, schneidet ein 607 px breites
9:16-Fenster die Haelfte davon weg, und bei einem Gespraechsformat ist die
Reaktion des anderen die Pointe. `SOLO_FULL` bleibt fuer eine einzelne Person
allein vor der Wand richtig.

### 2b — Top-5

- Die Clips muessen **einer Kategorie** folgen ("Die besten CoachLim
  Talentshow Momente", "Top 5 Coach x AbuGoku Momente", "… (Anmachsprueche)").
  Sie duerfen aus einem einzigen Video kommen; die Kategorie ist die
  Bedingung, nicht die Quellenvielfalt.
- **Der lustigste Clip steht am Anfang, also auf Platz 5.** Das ist Absicht:
  Wer mit dem Staerksten einsteigt, glaubt, es kann nur besser werden.
  (`countdown.py` deckt in der gemessenen Reihenfolge 5 → 1 auf; die Zuordnung
  Qualitaet → Platz ist deshalb umgekehrt zur Erwartung.)

---

## Regel 3 — Hooks: kurz, lustig, ohne Satzzeichen, mit Emoji

- **Keine Satzzeichen.** Kein Bindestrich, kein Punkt, kein Komma, kein
  Fragezeichen, kein Ausrufezeichen, kein Doppelpunkt, keine
  Anfuehrungszeichen. Nur Text.
- **Kuerzer als bisher.** Die 42-Zeichen-Grenze aus `hook.pruefe` bleibt die
  Obergrenze, Ziel sind deutlich weniger.
- **Emoji-Paar am Ende**, ausschliesslich aus 🥀 🫩 💀 🙏, in Kombinationen wie
  `🙏🫩`, `🥀💀`, `🥀🫩`, `💀🙏`.
- Verschiedene Clips als Referenz nutzen, nicht immer dieselbe Satzform.

**Folge fuer `hook.pruefe`:** Der Test `offen` akzeptierte bisher ein
Fragezeichen als Beleg dafuer, dass die Headline etwas offenlaesst. Das faellt
mit dieser Regel weg — offen bleibt eine Headline jetzt nur noch ueber ein
Wort aus `OFFEN` ("warum", "wer", "was", "wie" …). `hook.stil` prueft die
Formregeln mechanisch und meldet jeden Verstoss; sie schreibt nichts um.

---

## Regel 4 — Untertitel duerfen nichts Wichtiges verdecken

*"Passe die Untertitel immer so an, dass die ansprechend aussehen, korrekt sind
und nicht die Gesichter oder was anderes Wichtiges verdecken."*

Drei getrennte Forderungen:

- **Lage.** Die Standardlage aus `config/overlays.yaml` (y=1556, Band
  1424..1688) gilt fuer formatfuellende Templates. Jedes Template mit
  Bildband oder mehreren Panels misst die freie Flaeche selbst nach und
  ueberschreibt `untertitel.y`. Das ist bereits fuer `VLOG_FULL` (Band unter
  dem Bild) und `OME_SPLIT` (Wandband ueber den Koepfen) so gemacht — das
  Muster gilt ab jetzt fuer jedes neue Template.
- **Nachgemessen wird am gerenderten Frame**, nicht am Template. Ein Standbild
  je neuem Template ansehen, bevor der Lauf durchlaeuft.
- **Korrekt.** Das YouTube-Transkript verschreibt sich bei Namen und
  Fremdwoertern. Offensichtlich falsche Cues im Clipfenster werden vor dem
  Rendern korrigiert.

---

## Regel 5 — Qualitaet halten, Clips dynamischer machen

*"Versuche die Qualitaet immer gut zu halten und mache die Clips dynamischer,
ich lasse dir da freien Lauf."*

Ausgelegt als:

- Quelle immer in 1080p avc1, Encoder nach `settings.toml`, kein zweiter
  Transkodierschritt zwischen Schnitt und Ausgabe.
- Dynamik heisst nicht Effekt: tote Sekunden am Anfang und Ende wegschneiden,
  Cues eng am Sprechrhythmus fuehren, keine Standzeit ohne Ton oder Bewegung.
- Bei mehreren Panels ist die Bewegung im Bild schon da; bei einem statischen
  Vollbild traegt sie der Schnitt.

---

## Regel 6 — Kurzformat: der lustigste Moment zuerst, dann die Geschichte (ab 2026-09-11, in Erprobung)

Erster Auftrag: *"Lass uns das so bauen, dass die Clips sehr kurz sind,
maximal 30 Sekunden, am besten 10-15 Sekunden. [...] Der Lacher-Moment soll
direkt in den ersten 3-5 Sekunden sein. Die Visual Hook soll eine
Übertreibung des Szenarios sein."*

Rueckmeldung auf fuenf Beispiele davon, am selben Tag: *"Die Clips sind oft zu
kurz, man versteht nicht, was der Kontext hinter denen ist. Lieber einfach die
sehr lustigen Momente am Anfang und dann das Video bis mindestens 30 Sekunden
oder drüber laufen lassen, dadurch hat man eine gute Hook und der Zuschauer
ist mehr bereit, das Video zu schauen."*

Gebaut als Teaser plus Geschichte:

- **Teaser (2-7 s).** Der lustigste Moment laeuft zuerst. Die Selektion nennt
  ihn als eigenes Quellfenster (`teaser`) und die Pointe darin (`pointe.t`);
  liegt die Pointe nicht im Teaser, wird nicht gerendert.
- **Dann die Geschichte.** Harter Schnitt an den Anfang des Gespraechs; von
  dort laeuft der Clip mit Kontext ueber die Pointe hinaus (`timing`). Der
  Moment kommt also zweimal. Einfach ab dem Lacher weiterlaufen haette den
  Kontext nicht geliefert — der liegt vor der Pointe, nicht dahinter.
- **Mindestens 30 s**, darunter wird nicht gerendert. Ziel 30-60 s, darueber
  ein Hinweis.
- **Die Headline bleibt die Uebertreibung des Szenarios**, Regel 3 gilt
  weiter. `hook.pruefe` meldet bei diesem Stil "kein offenes Element" — das
  ist erwartet, eine Uebertreibung ist eine Aussage.
- **Punch-in** (harter Zoom 1.3x auf die Gesichter) auf der Pointe, im Teaser
  und an ihrer Stelle im Hauptteil. Die Follow-Szene steht im Hauptteil, nie
  im Teaser.

**Verhaeltnis zu Regel 1a:** gilt wieder uneingeschraenkt — der Hauptteil
traegt seinen Kontext selbst. Der Teaser steht davor, er ersetzt ihn nicht.

**Verworfen:** die erste Fassung (10-15 s, Pointe bei 3-5 s, Kontext nur in
der Headline). Ergebnis laut Nutzer: zu kurz, kein Kontext.

Stand: Fuenf Beispiele der zweiten Fassung aus 0-OqdAjLq_0 am 2026-09-11,
Rueckmeldung steht aus.

---

## Ablaufprotokoll je Lauf

1. Quelle laden, `de-orig` vorher pruefen (`yt-dlp --list-subs`).
2. Layout vermessen, Profil und Modi anlegen oder bestaetigen.
3. Template nach Regel 2 waehlen — nicht nach `default_fuer`, wenn beides
   auseinanderfaellt.
4. Kandidaten aus Transkript **lesen**, nicht aus dem Score uebernehmen.
5. Je Kandidat Regel 1a/1b/1c pruefen; Grenzen gegen `modus_laeufe` und
   `schnitte.finde` legen.
6. Headline nach Regel 3, `hook.stil` + `hook.pruefe` muessen sauber sein.
7. Ein Standbild aus der Mitte ansehen (Regel 1c und Regel 4).
8. Rendern, QC lesen.
