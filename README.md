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
- FFmpeg mit libass (Windows: `winget install Gyan.FFmpeg`, macOS: `brew install ffmpeg`)

## Struktur

```
config/
  settings.toml            gemeinsame Einstellungen + Plattformblöcke
  profiles/                Geometrie der Quelle  (materialabhängig)
  templates/               Zielkomposition       (materialabhängig)
src/videoclipper/          Pipeline              (materialunabhängig)
data/artifacts/            Transkripte, EditPlans — klein, wandert mit
work/                      Videodateien, Cache — lokal, nie im Repo
```

Materialabhängig sind ausschließlich `profiles/` und `templates/`. Der Wechsel
von Reaction-Content auf GTA 6 ist das Schreiben zweier YAML-Dateien.
