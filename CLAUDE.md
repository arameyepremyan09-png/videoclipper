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

## Look

Statische Headline pro Clip, kein Karaoke — aus dem Referenzmaterial gemessen, nicht
angenommen. Anton (OFL, kommerziell frei), Versalien, weiß mit dickem schwarzem Rand,
bei `OME_STACK` auf der Naht zwischen den beiden Panels.

## Monetarisierung

Tier A ist alles über 63 Sekunden gerenderter Dauer (TikTok Creator Rewards verlangt
*über* eine Minute, nicht exakt 60 s). Tier B bleibt unter 60 s und wird **nie**
künstlich gestreckt. QC misst die fertige Datei mit ffprobe. Der Schwellwert steht in
der Konfiguration, weil sich Programmbedingungen ändern.
