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
- yt-dlp — der Format-Selektor *und* `player_client=web_embedded` sind Pflicht, siehe CLAUDE.md

libass wird **nicht** vorausgesetzt: Der Homebrew-Build 8.1.1 bringt weder libass
noch drawtext mit. Die Headline läuft deshalb als PNG-Overlay und ist damit auf
beiden Maschinen identisch.

## Struktur

```
assets/fonts/              Anton (OFL) — die Headline-Schrift
config/
  settings.toml            gemeinsame Einstellungen + Plattformblöcke
  scoring.yaml             Bewertungsgewichte, Benchmarks, A/B-Regeln
  scoring.kalibriert.yaml  von `clip kalibriere` erzeugt, überschreibt die Annahmen
  konten.yaml              die eigenen Kanäle
  profiles/                Geometrie der Quelle  (materialabhängig)
  templates/               Zielkomposition       (materialabhängig)
src/videoclipper/          Pipeline              (materialunabhängig)
  transcript.py            Stage 03  json3 → Wörter mit Zeitstempeln
  signals.py               Stage 04  Lautheit, Lachmarker, Layout-Modus
  candidates.py            Stage 05  lokale Maxima → Zeitfenster
  editplan.py              Stage 10  Datenvertrag (pydantic)
  snapping.py              Stage 08  Wortgrenzen, Tier A/B
  layout.py                Stage 09  Profil + Template + Modus → Rechtecke
  headline.py              Headline als PNG-Overlay
  render.py                Stage 12  FFmpeg-Filtergraph
  qc.py                    Stage 13  ffprobe auf der fertigen Datei
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
  --write-subs --sub-langs de-orig --sub-format json3 \
  --merge-output-format mp4 -o "%(id)s.%(ext)s" "<url>"

# Stages 03-05: Transkript, Signale, Kandidaten
clip analyse --video VIDEO.mp4 --transkript VIDEO.de-orig.json3 \
  --video-id VIDEO --profil COACHLIM_TIKTOK_REACT

# Stage 06 liegt dazwischen: die Selektion nach data/selections/VIDEO.json.
# Sie liefert nur strukturiertes JSON — Moment, Länge, Headline, Modus.

# Stages 08-13: Snapping, Layout, Render, QC
clip rendere --plan data/selections/VIDEO.json --video VIDEO.mp4 \
  --transkript VIDEO.de-orig.json3 --video-id VIDEO \
  --profil COACHLIM_TIKTOK_REACT --ausgabe ~/videoclipper/clips
```

Die Analyse legt neben den Kandidaten auch `modus_laeufe` ab — die
zusammenhängenden Strecken eines Layouts. Clipgrenzen gehören in einen Lauf
hinein, nie über einen Wechsel.
