# Videoclipper

Short-Form-Clipping-Pipeline. Architektur und Entscheidungen stehen im
[Clipper Blueprint](https://claude.ai/code/artifact/f219d5f4-ee82-4f8e-836e-b2bec93de7f5),
der Arbeitskontext in [CLAUDE.md](CLAUDE.md).

## Auf beiden Rechnern arbeiten

Das Repository ist die portable Einheit. Es enthält Code, Konfiguration,
Materialprofile, Templates und den Claude-Kontext. **Videodateien enthält es nie.**

```bash
git clone <dein-remote> videoclipper
cd videoclipper
uv sync
```

Danach läuft Claude Code auf beiden Maschinen mit demselben Kontext, weil
`CLAUDE.md` automatisch geladen wird.

### Was wandert, was bleibt

| | Wandert mit dem Repo | Bleibt lokal |
|---|---|---|
| Code, Konfiguration, Profile, Templates | ja | |
| Transkripte, Signale, EditPlans (Kilobytes) | ja | |
| Quellvideos, Renderergebnisse, Cache (Gigabytes) | | ja |

Deshalb reicht das MacBook mit 256 GB zum Entwickeln vollständig aus: Die
eigentliche Arbeit hängt an den Zwischenartefakten, nicht an den Videodateien.
Einzelne Testvideos laufen auch dort komplett durch; nur der tägliche Batch
gehört auf den Desktop.

### Plattformunterschiede

Drei Werte unterscheiden sich, alles andere ist identisch. Aufgelöst in
`src/videoclipper/settings.py`, konfiguriert in `config/settings.toml`:

| | Windows-Desktop | MacBook Air M4 |
|---|---|---|
| Arbeitsverzeichnis | `F:/videoclipper` | `~/videoclipper` |
| Encoder | `libx264` | `h264_videotoolbox` |
| ASR-Backend | CPU | MLX / Neural Engine |

Maschinenspezifische Abweichungen kommen in `config/local.toml` — die Datei ist
absichtlich nicht im Repo.

## Voraussetzungen

- Python 3.12+ und [uv](https://docs.astral.sh/uv/)
- FFmpeg (Windows: `winget install Gyan.FFmpeg`, macOS: `brew install ffmpeg`)
- yt-dlp — Format-Selektor, `player_client=web_embedded` *und* `--write-auto-subs`
  sind Pflicht, siehe CLAUDE.md

libass wird **nicht** vorausgesetzt: Der Homebrew-Build 8.1.1 bringt weder libass
noch drawtext mit. Der gesamte Textpfad — Headline, Untertitel, Countdown-Liste,
Follow-Aufforderung — läuft deshalb als PNG-Overlay und ist damit auf beiden
Maschinen identisch.

## Struktur

```
assets/fonts/              Anton (OFL) — die Headline-Schrift
config/
  settings.toml            gemeinsame Einstellungen + Plattformblöcke
  overlays.yaml            Untertitel und Follow-Aufforderung — Pflicht in jedem Clip
  scoring.yaml             Bewertungsgewichte, Benchmarks, A/B-Regeln
  scoring.kalibriert.yaml  von `clip kalibriere` erzeugt, überschreibt die Annahmen
  konten.yaml              die eigenen Kanäle
  profiles/                Geometrie der Quelle  (materialabhängig)
  templates/               Zielkomposition       (materialabhängig)
src/videoclipper/          Pipeline              (materialunabhängig)
  transcript.py            Stage 03  json3 → Wörter mit Zeitstempeln
  signals.py               Stage 04  Lautheit, Lachmarker, Layout-Modus
  schnitte.py              Stage 04b harte Bildwechsel in der Quelle
  candidates.py            Stage 05  lokale Maxima → Zeitfenster
  editplan.py              Stage 10  Datenvertrag (pydantic)
  hook.py                  Stage 07  verrät die Headline die Pointe?
  rangliste.py             Stage 07b Clips eines Plans bewerten und sortieren
  snapping.py              Stage 08  Wortgrenzen, Tier A/B
  layout.py                Stage 09  Profil + Template + Modus → Rechtecke
  headline.py              Headline als PNG-Overlay
  untertitel.py            Stage 11a animierte Untertitel  (Pflicht)
  follow.py                Stage 11b Follow-Aufforderung   (Pflicht)
  render.py                Stage 12  FFmpeg-Filtergraph
  qc.py                    Stage 13  ffprobe + Pflichtprüfung vor dem Rendern
  forecast.py              Stage 15  Prognose vor dem Posten
  publish.py               Stage 16  Veröffentlichungsregister, A/B-Zuweisung
  collect.py               Stage 17  Messwerte holen (yt-dlp / manuell)
  scoring.py               Stage 17  Performance-Score
  experiments.py           A/B-Tests (Beta-Posteriors, keine p-Werte)
  report.py                Rangliste, Muster, Lücken
  calibrate.py             Annahmen durch eigene Zahlen ersetzen
  store.py                 JSONL-Ablage
data/artifacts/            Transkripte, Kandidaten — klein, wandert mit
data/selections/           Selektionen (Stage 06) — klein, wandert mit
data/performance/          Posts, Messwerte, Experimente — klein, wandert mit
tests/                     Tests der Rechenteile: `pytest`
work/                      Videodateien, Cache — lokal, nie im Repo
```

Materialabhängig sind ausschließlich `profiles/` und `templates/`. Der Wechsel
von Reaction-Content auf GTA 6 ist das Schreiben zweier YAML-Dateien.

`config/overlays.yaml` steht bewusst daneben und nicht in den Templates: Die
beiden Pflicht-Overlays sehen in jedem Clip gleich aus, hängen also weder an
der Quelle noch an der Zielkomposition. In elf Templates kopiert wären sie elf
Stellen, die auseinanderlaufen.

## Pflicht in jedem Clip

Zwei Overlays liegen auf **jedem** gerenderten Clip. `clip rendere` bricht ab,
wenn ein Template sie nicht trägt — im QC der fertigen Datei wären sie nicht
mehr nachweisbar, denn Dauer, Auflösung und Tonspur stimmen ja trotzdem.

**1. Untertitel mit Animation.** Ein PNG je Cue, eingeblendet über
`enable='between(t,ab,bis)'`. Der Ruck nach oben beim Cue-Wechsel steckt
vollständig im `y`-Ausdruck des `overlay`-Filters — die Animation kostet damit
weder ein zusätzliches Bild noch einen zusätzlichen Filter. Gebrochen wird an
Sprechpause, Satzende, Zeichenzahl oder Standzeit; `[gelächter]` wird nie
gesetzt.

**2. Follow-Aufforderung.** Eine Pille, die von rechts einfliegt, ~2,6 s steht
und rechts wieder hinausfliegt — dorthin, wo auf TikTok der Folgen-Knopf liegt.
Sie steht bei 35 % der Cliplänge, nie im Hook und nie auf der Pointe. Auch hier
ein einziges PNG, die Bewegung im `x`-Ausdruck.

Beide bleiben über TikToks UI-Zone (unterste 192 px); `untertitel.band` und
`follow.masse` brechen ab, wenn ein Template sie hineinschiebt. Alle Werte
stehen in `config/overlays.yaml`; ein Template überschreibt einzelne davon.
Abschalten geht nur mit `aktiv: false` **und** `grund:` — ohne Begründung ist
es ein Fehler.

```bash
# Was tatsächlich im Bild landet, steht im geschriebenen EditPlan:
#   resolved.untertitel  Liste der Cues mit Zeitfenster
#   resolved.follow      Text und Zeitfenster der Aufforderung
```

## Bewertung — welche Clips gehen viral

Der Kreis zurück vom fertigen Clip zur nächsten Selektion. Details und die
gemessenen Befunde stehen in [CLAUDE.md](CLAUDE.md).

```bash
# Vor dem Posten: lohnt sich der Clip, und wann sollte er raus?
clip prognose --headline "Sowas habe ich noch nie gesehen" --dauer 27 \
  --hook "Alter was ist das denn" --payoff 0.7 --postzeit 2026-09-05T19:00

# Nach dem Posten eintragen — Variante wird balanciert zugewiesen
clip registriere --plattform tiktok --url "<url>" --clip-id wxCFBR1_3to_001 \
  --experiment laenge_kurz_vs_tier_a

# Messwerte holen (TikTok und YouTube automatisch, Instagram nicht)
clip sammle

# Was das Creator-Center weiß und die API nicht hergibt
clip trage-nach --post tiktok_7681702356454624544 --watchtime 12.4 --follows 3

# Rangliste, Muster, Lücken
clip bewerte

# A/B-Stand
clip ab status --id laenge_kurz_vs_tier_a

# Annahmen durch die eigenen Zahlen ersetzen (braucht ~8-30 Posts)
clip kalibriere --probe
```

Drei Eigenschaften, die das System von einer bloßen Zahlenanzeige unterscheiden:

- **Es rechnet in Raten, nie in Rohzahlen.** Ein Clip mit 1000 Views und 50
  Likes ist besser als einer mit 5000 Views und 100 Likes.
- **Es vergleicht nur innerhalb desselben Messfensters.** Sonst gewinnt immer
  der ältere Post.
- **Es sagt, wenn es nichts sagen kann.** Fehlende Metriken werden nicht als
  Null gewertet, sondern verringern die ausgewiesene `abdeckung`; unter der
  Reichweitenschwelle erscheint gar kein Score.

Die Gewichte in `config/scoring.yaml` sind zunächst **Annahmen** und dort als
solche markiert. `clip kalibriere` ersetzt sie durch die eigenen Perzentile.

## Ablauf

```bash
# Quelle holen — der Player-Client ist nicht optional, siehe CLAUDE.md
yt-dlp -f "bv[vcodec^=avc1][height<=1080]+ba/b[height<=1080]" \
  --extractor-args "youtube:player_client=web_embedded" \
  --write-auto-subs --sub-langs de-orig --sub-format json3 \
  --merge-output-format mp4 -o "%(id)s.%(ext)s" "<url>"

# Stages 03-05: Transkript, Signale, Kandidaten
clip analyse --video VIDEO.mp4 --transkript VIDEO.de-orig.json3 \
  --video-id VIDEO --profil COACHLIM_TIKTOK_REACT

# Stage 06 liegt dazwischen: die Selektion nach data/selections/VIDEO.json.
# Sie liefert nur strukturiertes JSON — Moment, Länge, Headline, Modus.

# Stage 07: bewerten und sortieren, BEVOR gerendert wird — läuft in Sekunden
clip rangliste --plan data/selections/VIDEO.json \
  --transkript VIDEO.de-orig.json3 --video-id VIDEO

# Stages 08-13: Snapping, Layout, Overlays, Render, QC
clip rendere --plan data/selections/VIDEO.json --video VIDEO.mp4 \
  --transkript VIDEO.de-orig.json3 --video-id VIDEO \
  --profil COACHLIM_TIKTOK_REACT --ausgabe ~/videoclipper/clips
```

`clip rendere` meldet pro Clip, was an Overlays entstanden ist:

```
  vT1ysIDSpHw_001   545.04- 578.99   34.0s  REACT_YT_SPLIT Tier B  Keiner will eine Milf
      Overlays: 23 Untertitel, Follow 11.9-14.5s
      QC: 34.00s 1080x1920 Tier B
```

Steht dort `0 Untertitel`, enthält das Clipfenster kein transkribiertes Wort —
das ist zulässig, aber ein Grund, sich den Clip anzusehen.

Die Analyse legt neben den Kandidaten auch `modus_laeufe` ab — die
zusammenhängenden Strecken eines Layouts. Clipgrenzen gehören in einen Lauf
hinein, nie über einen Wechsel.

## Bildwechsel im Clip

Der Modus sagt, welches Layout vorliegt — nicht, ob das Bild *innerhalb*
desselben Layouts springt. Bei OME.TV-Material bleibt der Splitscreen zu
100 % stehen, während zwanzigmal ein neuer Mensch davorsitzt.

`clip rendere` sucht deshalb in **einem** Durchlauf über die Quelle die harten
Bildwechsel und meldet je Clip, was dazwischenliegt:

```
  utB7GTrmLYY_005   575.24- 604.31   29.1s  OME_SPLIT  Tier B  Warum seid ihr in Canada?
      ! utB7GTrmLYY_005: 1 Bildwechsel im Clip bei 598.75s — der Clip springt dort.
```

Es bricht **nicht** ab: Bei einer Handkamera ist ein Wechsel im Clip normal,
und ob er stört, entscheidet der Blick. Gemessen wird gegen den lokalen
Median, nicht gegen einen festen Schwellwert — sonst meldet jeder Rundgang
mit Handkamera hunderte Schnitte. `--ohne-schnittpruefung` spart den
Durchlauf. Details und Messwerte in [CLAUDE.md](CLAUDE.md).

## Rangliste und Hook

`clip rangliste` bewertet alle Clips eines Selektionsplans, bevor auch nur
einer gerendert ist. Es braucht kein Video, nur den Plan und das Transkript,
und läuft deshalb in Sekunden.

```
 #   prog ausw   dauer tier  payoff  hook      headline
 1   58.4 0.88    41.2s    B     71%  offen     Was hat der denn in der Tasche
 2   55.1 0.82    36.0s    B     64%  ok        Mit Essen spielt man nicht
 …
```

Sortiert wird nach der Prognose (Stage 15) — **aber ein Clip, dessen Headline
die Pointe verrät, rutscht ans Ende**, unabhängig von seiner Punktzahl. Die
Prognose kennt den Clipinhalt nicht, die Hookprüfung schon.

Zwei Zahlen statt einer: `prog` ist die Prognose, `ausw` der Selektionsscore
der AI. Wo beide auseinanderlaufen, sagt die Ausgabe das ausdrücklich — das
ist die interessante Zeile, nicht die mit dem höchsten Wert. Die Prognose ist
unkalibriert (`konfidenz 0.2`); sie ist eine Sortierhilfe für die
Reviewschlange, keine Vorhersage.

### Was die Hookprüfung misst

`hook.pruefe` vergleicht die Headline gegen den **tatsächlichen Inhalt** des
Clipfensters — nicht gegen Annahmen. Zwei Befunde, beide im fertigen Clip nicht
mehr sichtbar:

- **`VERRAET`** — ein Inhaltswort der Headline fällt erst im letzten Drittel
  des Clips und im Aufbau nicht. Dann ist die Frage schon beantwortet, bevor
  jemand den Clip startet. Wörter, die ohnehin früh fallen, gelten nicht als
  Verrat: die ordnen nur ein.
- **`lose`** — kein Wort der Headline kommt im Clip vor. Die Headline
  verspricht dann etwas anderes, als zu sehen ist.

`clip rendere` führt dieselbe Prüfung mit und meldet sie pro Clip. Umgeschrieben
wird nichts — der Code entscheidet WIE, nicht WAS.
