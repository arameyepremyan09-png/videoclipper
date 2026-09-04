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
data/artifacts/            Transkripte, Kandidaten — klein, wandert mit
data/selections/           Selektionen (Stage 06) — klein, wandert mit
work/                      Videodateien, Cache — lokal, nie im Repo
```

Materialabhängig sind ausschließlich `profiles/` und `templates/`. Der Wechsel
von Reaction-Content auf GTA 6 ist das Schreiben zweier YAML-Dateien.

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
