# BWC Clipper — Design Document

**Status:** Draft for review
**Date:** 2026-04-29
**Prior reference:** `bodycam_transcription_brief.md` (the brief in the project root) is the canonical engineering spec for the transcription pipeline. This document references it by section rather than restating its details.
**Architectural reference:** `Depo-Clipper/` (sibling project at `C:\Claude Code Projects\Depo Clipper\Depo-Clipper`, repo `github.com/ignavusignarus/Depo-Clipper`). BWC Clipper mirrors its patterns — Python engine, Electron desktop wrapper, React UI, PyInstaller `--onedir`, NSIS per-user installer, dependency-gated startup, multi-vendor GPU job system — but is an independent codebase with no shared modules.

---

## 1. Overview

BWC Clipper is a local-only desktop application for plaintiff-side litigation review of body-worn camera (BWC) video and defense medical exam (DME) audio. It ingests media files in a case folder, runs a self-contained transcription pipeline (Whisper + VAD + diarization + speech enhancement), and presents a reviewer UI in which the auto-generated transcript serves as a navigation aid for finding moments of interest in long, often non-speech-dense recordings. The user creates and exports trial-ready clips. Clips never carry a transcript overlay — the transcript is a tool for the reviewer, not a deliverable on the clip.

The defining UX problem this app solves: a 30-minute BWC where the relevant incident is 90 seconds, surrounded by long stretches of silence or non-speech ambient. Standard linear scrubbing wastes time. BWC Clipper's primary navigation is a collapsed-silence timeline that compresses non-speech regions out of the way, with an uncompressed real-time toggle for users who want it.

---

## 2. Goals and non-goals

### V1 goals

- Open a folder, treat it as a project, auto-process every media file inside through the transcription pipeline.
- Auto-detect mode per source — BWC for video files, DME for audio-only files.
- Reviewer UI with click-to-seek transcript, collapsed-silence timeline (default) and uncompressed timeline (toggle), per-source context-names panel, speaker-colored speech segments, full-text search.
- Clip authoring with three creation paths (hotkey, timeline drag, transcript selection).
- Per-clip editor with snap-to-pause boundary tweaking, word-level nudge keys, loop preview.
- Clip export — video sources produce a single MP4; audio sources produce both an audio file and a waveform-rendered MP4. Project-level "Export All."
- Background processing of unviewed sources with automatic re-prioritization when the user switches files.
- Dependency-gated startup — no pipeline fallbacks; missing resources block the gate with a redownload affordance.
- Windows installer (NSIS, per-user, `%LOCALAPPDATA%\BWCClipper`); large models (>50 MB) downloaded by the installer.

### Non-goals for V1 (deliberately deferred)

- Voice-print matching against labeled samples; per-case voice-print database; cross-file speaker re-id.
- Redaction tooling (auto-bleep + transcript replacement for protected names).
- Manual transcript correction with revision history inside the app.
- Transcript exports (DOCX / VTT / TXT).
- PDF clip report and Notice of Intent document (Depo Clipper has these; BWC use case does not require them).
- Automated clip grading and gap-based cut-point analysis. The app assumes manual reviewer judgment for every clip.
- Quality reports per source.
- macOS build (Mac is a secondary target after Windows V1 ships).

### Non-goals overall

- Cloud or remote processing — all audio may be sealed/protected.
- Cross-file clips — every clip belongs to exactly one source file.
- A "library" or "recent matters" view that scans the filesystem outside the open folder.
- A separate batch-process mode — background processing is always on.

---

## 3. Architecture

### 3.1 Codebase shape

```
bwc-clipper/
├── engine/                 Python — transcription pipeline, ffmpeg orchestration,
│                           clip composition, export, job and resource manager,
│                           hardware backend, dependency gate.
├── electron/               Node — desktop wrapper, splash with dependency gate UI,
│                           native folder picker, ffmpeg auto-download, splash
│                           preload, main process.
├── editor/                 React (esbuild-bundled) — reviewer UI: media pane,
│                           timeline, transcript panel, clip composer, export modal.
├── serve.py                Local HTTP server bridging Electron to engine.
├── editor.html / index.html
├── editor-bundle.js        esbuild output (committed for development convenience).
├── vendor/                 Bundled binaries (ffmpeg, Silero VAD ONNX, etc.).
├── tests/                  pytest for engine; vitest for editor.
├── benchmarks/             Pipeline performance fixtures and metrics.
├── scripts/                Build, packaging, model-download helpers.
├── forge.config.js         electron-forge configuration.
├── package.json            Editor and Electron dependencies.
├── pyproject.toml          Engine dependencies and packaging metadata.
└── docs/                   This document, future plans, architecture notes.
```

This is the Depo Clipper layout, transposed. Independent codebase — no shared modules with Depo Clipper. Patterns transfer; code does not.

### 3.2 Process model at runtime

1. User launches Electron desktop app.
2. Splash window opens; runs the dependency gate (verify ffmpeg present, verify all model files present and hash-matched, verify Python venv healthy).
3. Splash dismisses on success; engine HTTP server (`serve.py`) starts as a child process on a random localhost port.
4. Main window loads; React UI connects to the engine over HTTP and a WebSocket for progress events.
5. User picks a folder.
6. Engine enumerates media files, hashes them, checks for cached transcripts, queues unprocessed files into the job manager.
7. The first file the user selects gets head-of-queue priority. Background workers process the rest.
8. UI polls / receives progress events; renders timeline and transcript as cache appears.

### 3.3 Stack

- **Python 3.11.** faster-whisper, whisperx, pyannote.audio 3.1, silero-vad, deepfilternet, torch (CUDA 12.x or MPS), pydantic, click, ffmpeg-python wrapper.
- **Node + Electron.** electron-forge for packaging, electron 41+, vitest for editor tests.
- **React 19 + esbuild.** No build framework; esbuild bundles `editor/main.jsx` to `editor-bundle.js`.
- **Bundled binaries.** ffmpeg (auto-downloaded on first launch using Depo Clipper's `ffmpeg-downloader.js` pattern), Silero VAD ONNX (small enough to bundle), DeepFilterNet ONNX (≈50 MB threshold — likely bundled).
- **Installer-time downloads.** large-v3 (≈3 GB), pyannote 3.1 pipeline (≈100 MB), wav2vec2 alignment models. NSIS hands a download list to a Windows-side dep-downloader (Depo Clipper pattern).

### 3.4 License

Consumer Attorney Open Source License (CAOSL) v1.0 — same terms as Depo Clipper. Free for plaintiff/consumer attorneys and non-commercial use; defense practitioners require a separate written license agreement.

---

## 4. Project layout — the folder is the project

When the user opens a folder, BWC Clipper treats the folder as the project. No external project file. The folder is the canonical state.

```
my-case-folder/
├── officer-garcia.mp4              user-supplied source media
├── officer-lee.mp4
├── ent-doctor.MP3
├── clips/                          clip exports (created by app)
│   ├── 001 - Officer admits speeding.mp4
│   ├── 003 - Doctor pause re prior history.mp3
│   └── 003 - Doctor pause re prior history.waveform.mp4
└── .bwcclipper/                    cache + state (hidden)
    ├── officer-garcia/
    │   ├── source.sha256           SHA-256 of source file (cache key)
    │   ├── transcript.json         per brief §4.8 schema
    │   ├── waveform.bin            cached waveform peaks
    │   ├── speech-segments.json    VAD output (drives collapsed timeline)
    │   ├── context.json            per-source context names + locations
    │   └── pipeline-state.json     which stages completed; for resume
    ├── officer-lee/...
    ├── ent-doctor/...
    ├── clips.json                  canonical clip list
    └── clip-exports.json           per-clip last-export hash (span + params)
                                    used to skip unchanged re-exports
```

**Invariants:**

- Cache directory keyed by source basename; all cache contents are addressable per-source. If a source file is deleted, its cache directory remains until the user explicitly cleans it.
- `source.sha256` is the cache key. If the user replaces a same-named file with different content, the hash mismatch triggers reprocessing (Depo Clipper `portable_cache.py` pattern).
- `clips.json` defines clips by `{source_basename, in_seconds, out_seconds, name, exhibit_number, notes, created_at}`. Files in `clips/` are reproducible — delete and re-export and you get the same outputs.
- Application state in the running app must be derivable from the folder contents. Closing and reopening the folder is lossless.

---

## 5. Transcription pipeline

The full engineering specification is in `bodycam_transcription_brief.md`. This section defines what BWC Clipper does **on top of** that spec — the integration with the rest of the app and the deviations from the brief.

### 5.1 Stages (per brief)

In order: **extract → normalize → enhance → VAD → transcribe → align → diarize → wearer-detect → output**.

- **Extract** (brief §4.1). Multi-track aware: Axon BWC often has per-officer mics on separate tracks; each track is processed independently and re-merged at the speaker-assignment step.
- **Normalize + compress** (brief §4.2). Two-pass loudnorm, then `acompressor`, then high/low-pass band-limit.
- **Enhance** (brief §4.3). DeepFilterNet 3 only — no `arnndn` fallback (see §5.3).
- **VAD** (brief §4.4). Silero VAD with brief's parameters. Output drives the collapsed-silence timeline, not just the transcription input.
- **Transcribe** (brief §4.5). faster-whisper / WhisperX `large-v3`. Brief's anti-hallucination decoder parameters apply verbatim. WhisperX forced word alignment is non-negotiable — required for click-to-seek and for clip word-level nudging.
- **Diarize** (brief §4.6). pyannote 3.1 pipeline on the **original** (un-enhanced) audio.
- **Wearer detect** (brief §4.7). BWC mode only. Heuristic: highest mean-RMS cluster with >25% of total speech time → "Wearer." DME mode skips this step entirely; speakers are labeled "Speaker 1" / "Speaker 2" / etc. by first appearance order until the user re-labels.

### 5.2 Outputs from the pipeline (per source)

| File                        | Purpose                                                              |
|-----------------------------|----------------------------------------------------------------------|
| `transcript.json`           | Canonical structured transcript (per brief §4.8 schema, schema version 1.0). |
| `speech-segments.json`      | VAD output (start, end pairs). Drives the collapsed-silence timeline.       |
| `waveform.bin`              | Pre-computed peaks for fast timeline rendering.                         |
| `context.json`              | User-provided context names + locations. Persists between sessions.        |
| `pipeline-state.json`       | Per-stage completion timestamps. Allows resume after interrupted runs. |

V1 does **not** produce VTT, TXT, or DOCX. The transcript exists inside the app for navigation; clips do not carry it.

### 5.3 Deviations from the brief

- **No fallbacks.** The brief allows `arnndn` if DeepFilterNet 3 is unavailable, and "no-enhance" mode if DF3 over-suppresses quiet speech. BWC Clipper drops both: dependency gate ensures DF3 is present and loadable; the pipeline always runs all stages. If the user experiences over-suppression on a specific file, that becomes a tuning issue handled by adjusting parameters, not by skipping a stage.
- **No CPU-fallback within stages.** GPU is checked at startup. CPU mode is supported as an **app-wide configuration** (selected at install or in settings), not as a runtime fallback inside an otherwise-GPU pipeline.
- **VTT / TXT / DOCX outputs are deferred.** The pipeline writes only `transcript.json`. Other formats are V2.

### 5.4 Per-source context names

When the user opens a source, a context panel appears showing the names and locations expected to occur in that recording. Editing the panel and clicking "Apply" invalidates the **transcribe** and **align** stages of that source's cache. Earlier stages (extract / normalize / enhance / VAD / diarize) remain valid: extract/normalize/enhance/VAD don't depend on the prompt, and diarization runs on the original un-enhanced audio independently of any text. The transcribe and align stages re-run with the updated initial prompt, then **wearer-detect** re-runs because it depends on the speaker-to-segment mapping post-alignment.

The context panel is a small productivity feature, but high-value: per the brief, context names dramatically improve proper-noun recall. The user shouldn't have to remember to fill it in **before** processing — they should be able to refine after seeing what the transcript looks like.

### 5.5 Mode-aware parameters

| Parameter                        | BWC mode                                  | DME mode                                  |
|----------------------------------|-------------------------------------------|-------------------------------------------|
| Min/max speakers (pyannote)      | min 2, max 6                              | min 2, max 4                              |
| Wearer detection                 | Run                                       | Skipped                                   |
| Initial prompt template          | "law enforcement body-worn camera..."     | "defense medical examination..."          |
| Compressor ratio                 | 4:1 (default), 6:1 if soft speakers       | 3:1 (less aggressive — quieter source)    |

Detection is automatic at file ingest: if the file has a video stream, it is BWC mode; if audio-only, DME mode. The user can override per source if needed (e.g., a body-cam audio-only export should still be BWC mode).

---

## 6. Reviewer UI

### 6.1 Layout

```
┌─────────────────────────────────────────┬──────────────────────────────┐
│                                         │  Search…  ▢                  │
│         Media pane                      │  ┌─────────────────────────┐ │
│   (video for BWC, prominent             │  │ 00:14  Officer:  ...    │ │
│    waveform for DME)                    │  │ 04:36  Officer:  ...    │ │
│                                         │  │ 14:27  Officer:  ...    │ │
│                                         │  │ 14:33  Subject:  ...    │ │
│   Transport: ⏯ ◀◀ ▶▶  I/O marks         │  │ ...                     │ │
│             J/K/L  ±5s skip             │  │                         │ │
│                                         │  │ Transcript scrolls in   │ │
├─────────────────────────────────────────┤  │ sync with playback.     │ │
│  Timeline area:                         │  │                         │ │
│   [ collapsed-silence default ]         │  │                         │ │
│   [ ⇄ uncompressed toggle  ]            │  │                         │ │
│   speaker-colored speech segments       │  └─────────────────────────┘ │
│   striped bars for collapsed silences   │  Context names: [edit panel] │
└─────────────────────────────────────────┴──────────────────────────────┘
   Top bar:  source picker · pipeline progress · ⏵ telemetry · export · ☰
```

Sidebar (collapsible, default off): clip list for the current source.

### 6.2 Mode differences (BWC vs DME)

- **Media pane.** BWC: full video player with audio. DME: audio-only player with the waveform displayed prominently (replacing the video area). Same transport controls, same hotkeys.
- **Speaker colors.** BWC: wearer is fixed (e.g., teal); subjects 1..N rotate through a palette. DME: the first-detected speaker is the doctor (label editable), subsequent are patient / others.
- **Wearer label.** Present in BWC, absent in DME.

### 6.3 Timeline

Two views, single toggle.

- **Collapsed-silence (default).** Each speech segment renders at full width proportional to its own duration; non-speech regions render as fixed-width striped bars (clickable to expand a single silence inline; a top-bar button expands all). Time is shown numerically at the playhead, not spatially across the track. Clicking inside a speech segment seeks to that point. Speaker color shows on each speech segment.
- **Uncompressed.** Standard real-time ruler. Speech segments rendered as colored regions on a dark track; silences are the gaps between them. Same click-to-seek behavior. Same hotkeys.

Both views render from `speech-segments.json` + `transcript.json`.

### 6.4 Transcript panel

Click any utterance to seek. Active utterance scrolls into view as the playhead advances. Words with `low_confidence` flagged in the transcript JSON are underlined in amber. Speaker labels color-coded to match the timeline. Search bar filters in real time, highlighting all matches across the transcript and adding markers to the timeline at each match position.

### 6.5 Context names panel

Per-source. Two text areas: "Names you expect to hear" (one per line), "Locations." A small "Apply and re-transcribe" button. While re-transcription runs, transcript panel shows the previous transcript with a banner indicating it's stale.

### 6.6 Hotkeys

| Key       | Action                                               |
|-----------|------------------------------------------------------|
| Space     | Play / pause                                         |
| J / K / L | Reverse / pause / forward (NLE convention)           |
| ← / →     | Skip backward / forward 5 s                          |
| Shift+← / →| Skip backward / forward 1 s                         |
| I         | Set in-point at playhead                             |
| O         | Set out-point at playhead                            |
| Enter     | Save current in/out as a new clip                    |
| Esc       | Clear current in/out marks                           |
| / or Ctrl+F | Focus search                                       |
| Ctrl+S    | Save project state (auto-save also runs continuously)|
| ⇄ button  | Toggle timeline collapsed/uncompressed view          |

**Hotkey scoping.** The bindings above apply when the project view (media pane / timeline / transcript / clip list) has focus. The clip editor (§7.3) defines its own bindings that **override** the project-view defaults while the editor is open: `←/→` becomes word-boundary nudge (instead of 5 s skip), `L` becomes loop preview (instead of forward-shuttle). Closing the clip editor restores the project-view bindings. The text-search input captures all letter keys while focused, regardless of context.

---

## 7. Clip authoring and editor

### 7.1 Three creation paths

1. **Hotkey while playing.** **I** sets in-point at playhead, **O** sets out-point, **Enter** opens the save modal (name / exhibit number / notes).
2. **Drag on the timeline.** Click-drag a span on either timeline view; release opens the save modal.
3. **From the transcript.** Select a passage of transcript text (across one or more utterances), right-click → "Make clip from selection." In/out are set to the first selected word's start and the last word's end.

In all three paths, the save modal pre-fills name from the first few words of transcript inside the span.

### 7.2 Clip list

Sidebar (collapsible). Shows: exhibit number, name, source basename, duration, tiny inline waveform thumbnail of the clip's span. Right-click on a clip: Open in editor / Export this clip / Duplicate / Delete / Reveal output file (if exported).

### 7.3 Clip editor

Click any clip in the list to open the focused per-clip editor (replaces the project view, similar to Depo Clipper's clip editor):

```
┌──────────────────────────────────────────────────────────┐
│  Clip preview (loops in/out)                  [name]     │
│                                               [exh #]    │
│                                               [notes]    │
├──────────────────────────────────────────────────────────┤
│  Two-layer timeline showing clip span + ~5 s context:    │
│                                                          │
│   ░░ waveform ████ ░ ████████ ░░ █████████ ░ ████ ░░    │
│        ▲ in handle              ▼ out handle             │
│   ──── speech segment colored bar ──────                 │
│   transcript words rendered inline beneath, time-aligned │
└──────────────────────────────────────────────────────────┘
                  [Save]  [Discard]  [Delete]
```

**Boundary tweaking:**

- Drag the in/out handles along the waveform; preview updates live.
- Snap-to-pause (default): handles snap to nearest VAD silence boundary as you drag. Hold **Shift** to drag freely.
- Word-level nudging: ←/→ moves the selected handle to previous/next word boundary; Shift+←/→ moves by 100 ms.
- Loop preview: **L** plays the clip from in to out on repeat while you tweak.

The clip editor expands any collapsed silences within its display window — you must see what's actually inside the clip.

### 7.4 No clip grading or QA segmentation

This app assumes manual review and editing for every clip. There is no automatic grading, no gap-based cut-point analysis, no QA segmentation. Snap-to-pause, word nudging, and loop preview are the assists; the user's judgment is final.

---

## 8. Export

### 8.1 Single clip export

Right-click a clip → Export this clip. Engine job runs: ffmpeg cut from source media, applied container, written to `clips/<exhibit-number> - <name>.<ext>`.

- **Video sources (BWC):** one MP4 output. 1080p (matched to source if lower), normalized quality presets, hardware-encoded if available (NVENC / AMF / QSV / VideoToolbox in priority).
- **Audio sources (DME):** **two** outputs per clip:
  1. `<exhibit-number> - <name>.mp3` (or `.wav` if user prefers — settings flag, default mp3 320 kbps).
  2. `<exhibit-number> - <name>.waveform.mp4` — MP4 with the clip audio plus a moving waveform visualization rendered against a dark card with case caption / exhibit number / source filename.

No transcript overlay on any clip output.

### 8.2 Project-level "Export All"

Top-bar button. Runs the entire current `clips.json` as a job batch. Per-clip progress; a single failure does not block the rest. Output goes to `clips/`.

**Skip-when-unchanged cache.** `.bwcclipper/clip-exports.json` records, per clip ID, a SHA-256 of the export-relevant fields: source SHA-256, in-seconds, out-seconds, output extension, encoder preset, and audio-mode flag. If a clip's expected output file already exists in `clips/` and its current export hash matches the recorded one, the export is skipped. Editing any export-relevant field invalidates the entry.

### 8.3 File naming

`<3-digit-zero-padded-exhibit-number> - <sanitized-name>.<ext>`. Example: `001 - Officer admits speeding.mp4`. Sanitization: replace `/`, `\`, `:`, `*`, `?`, `"`, `<`, `>`, `|` with `-`. If exhibit number is missing, file is named with the clip's UUID short prefix.

---

## 9. Job system and resource management

Match Depo Clipper's pattern. Single central job manager in `engine/job_manager.py`; `engine/resource_manager.py` mediates GPU and disk-bandwidth contention.

### 9.1 Job types

- **Transcription stage jobs.** One per stage per source: `extract`, `normalize`, `enhance`, `vad`, `transcribe`, `align`, `diarize`, `wearer-detect`, `assemble-output`. Granular so progress is meaningful and so re-running one stage (e.g., re-transcribe with new context names) doesn't redo earlier work.
- **Waveform-cache jobs.** Generates `waveform.bin` for fast timeline rendering.
- **Clip export jobs.** One per clip; emits one or two outputs depending on source mode.

### 9.2 Priority

- **Foreground priority.** The currently-active source in the UI. Its stages run before background sources.
- **Background priority.** Other unprocessed sources in the open folder.
- **User-action priority.** Clip exports triggered by the user, especially "Export All," preempt background transcription jobs (transcription jobs are paused at stage boundaries; in-flight Whisper inference is not interrupted mid-file but yields after).

When the user switches to a different source mid-pipeline-run on the previously-active file, the previously-active file's remaining stages drop to background priority and the newly-selected file's stages become foreground.

### 9.3 GPU resource model

- Whisper inference: one job at a time per GPU.
- pyannote diarization: one job at a time per GPU; can run on a different GPU than Whisper if multiple are present (rare for the target hardware).
- Hardware video encoding (clip export): can run concurrently with Whisper if the encoder is independent of the compute path (NVENC alongside CUDA inference is fine; AMF alongside ROCm is fine).

Resource manager assigns affinities. CPU mode disables GPU-only jobs and runs everything on CPU at lower throughput; user is informed at install time.

### 9.4 Telemetry

Live CPU / RSS / GPU sparkline in the top bar (Depo Clipper pattern, vendor-specific samplers: nvidia-smi, rocm-smi, Apple Silicon).

---

## 10. Dependency gate

Mirror Depo Clipper's startup gate, with stricter checks because there are no fallbacks.

### 10.1 What gets verified at every launch

- **ffmpeg binary** present and version-compatible (auto-download on first launch).
- **Python venv** healthy, all pinned dependencies importable (faster-whisper, whisperx, pyannote.audio, silero-vad, deepfilternet, torch, etc.).
- **Bundled small models** present and hash-verified (Silero VAD ONNX, optionally DeepFilterNet ONNX if its size lands under the 50 MB bundling threshold).
- **Installer-time large models** present and hash-verified (faster-whisper large-v3 CT2 weights, pyannote 3.1 pipeline cache, wav2vec2 alignment models).
- **GPU runtime** detection (CUDA / ROCm / MPS / QSV / VideoToolbox availability matched against user's selected mode).

### 10.2 Failure handling

If any check fails, the splash screen shows the failure and a single primary action: **Repair / Redownload**. This re-runs the installer-time download steps for missing/corrupt items. No "skip and continue" option — the pipeline cannot run safely with missing components.

---

## 11. Packaging

### 11.1 Installer

NSIS-driven Windows installer, per-user installation to `%LOCALAPPDATA%\BWCClipper`. No UAC prompt. PyInstaller `--onedir` (NOT `--onefile`) for the engine to avoid CrowdStrike / Carbon Black flagging in corporate environments. Same approach as Depo Clipper.

### 11.2 Model download at install time

NSIS post-install step downloads:

- faster-whisper large-v3 CT2 weights (≈3 GB)
- pyannote/speaker-diarization-3.1 pipeline (≈100 MB)
- wav2vec2 alignment model (≈300 MB)

To: `%LOCALAPPDATA%\BWCClipper\models\`. Download progress shown in the installer UI. Cache layout matches what the engine expects on launch.

A "lite installer" build mode (`LITE_BUILD=1`) skips installer-time downloads and triggers them on first launch instead — for distribution channels that can't host the large bundle.

### 11.3 Updates

Out of scope for V1. Manual reinstall.

### 11.4 macOS

Out of scope for V1. Future: `py2app`, signed and notarized.

---

## 12. Testing strategy

### 12.1 Unit (engine)

- Audio extraction: known fixtures → expected sample rate, channel count, duration, multi-track behavior.
- VAD: synthetic audio with known silence / speech regions → segment boundaries within 100 ms.
- Output schema: validated against pydantic models.
- Clip composition: in/out alignment with source frame rate; word-snap behavior.
- Hash computation and cache invalidation.

### 12.2 Integration (engine)

Fixture set: 5–10 short clips (30–120 s each) drawn from the user's `Samples/` folder, with manually verified ground-truth transcripts:
- Officer-only speech.
- Multi-speaker BWC.
- Distant subject in BWC.
- Heavy traffic noise BWC.
- Wind / radio chatter BWC.
- Indoor multi-speaker DME (each of the three current samples).
- DME with periods of silence (doctor reading notes).

Tracked metrics across pipeline changes (regression on any one is a build failure):
- WER overall and per-speaker.
- Word-level timestamp drift.
- Hallucination rate (segments matching known hallucination patterns).
- Missed-speech rate.
- Wearer-detection accuracy.

### 12.3 Editor (UI)

vitest unit tests for hooks, state reducers, timeline coordinate math (collapsed↔real-time mapping), clip-state transitions. Manual smoke tests via the dev mode (`npm start`).

### 12.4 Manual review burn-in

Process 3–5 hours of real BWC + DME audio across diverse sample sets. Review with the human-reviewer UI in mind, flagging failure modes that automated metrics miss (correctly transcribed but wrong speaker assignment, snap-to-pause snapping in the wrong place, etc.).

---

## 13. Implementation order (high level)

This is the rough phasing, to be expanded by the writing-plans skill.

1. **Skeleton.** Repo shape, electron-forge scaffold, esbuild config, engine HTTP server, splash + dependency gate stub. Empty UI loads.
2. **Folder open + file enumeration.** Project view lists media files, no processing yet.
3. **Pipeline stages 1–4 (extract, normalize, enhance, VAD).** End-to-end with progress and cache. UI shows progress; no transcript yet.
4. **Pipeline stages 5–6 (transcribe + align).** Transcript JSON written to cache. Transcript panel renders. Click-to-seek works.
5. **Pipeline stages 7–8 (diarize + wearer-detect).** Speaker colors light up.
6. **Timeline views.** Uncompressed first (simpler), then collapsed-silence with click-expand and toggle.
7. **Search + context names panel.** Plus stage-7 cache invalidation when context changes.
8. **Clip authoring.** Hotkey path first, then drag, then transcript-selection.
9. **Clip editor.** Snap-to-pause, word nudge, loop.
10. **Export.** Single clip first, then Export All. Audio dual-output.
11. **Background processing + foreground priority.** Job manager and resource manager.
12. **Dependency gate.**
13. **NSIS installer + model download.**
14. **Integration test suite.**
15. **Burn-in and tuning.**

Each step produces a runnable, testable artifact. The pipeline gets a usable UI early so we can dogfood as we build.

---

## 14. Risks and open questions

### Risks

- **Whisper hallucination inside long VAD-flagged segments.** Monitor `compression_ratio` and `avg_logprob` per segment; flag low-confidence inline in the transcript UI. Not solvable in V1 without moving upstream of Whisper.
- **GPU OOM on long files with `large-v3`.** Mitigation: chunk by VAD boundaries; chunk size exposed as a config knob.
- **Diarization speaker count instability on short utterances.** Mitigation: configured `min_speakers` / `max_speakers` per mode; user can manually merge or split clusters in V2.
- **Word-alignment drift on overlapping speech.** Mitigation: alignment confidence carried through to transcript; overlapping spans flagged.
- **Axon `.mp4` codec variants.** Mitigation: bundled ffmpeg with full codec support; test against real Evidence.com exports during burn-in.
- **Corporate-environment AV/EDR.** Mitigation: `--onedir` PyInstaller, per-user install, no UAC.
- **DeepFilterNet over-suppressing quiet legitimate speech.** With no fallback, this becomes a parameter-tuning issue. Burn-in should include soft-speaker fixtures specifically.

### Defaults selected for V1 (so the implementation plan isn't blocked)

- **Speaker color palette.** Wearer / first speaker: teal (`#5eead4`). Subjects 1..N: amber (`#fbbf24`), violet (`#c084fc`), rose (`#fb7185`), sky (`#7dd3fc`), lime (`#a3e635`), then cycle. Chosen for dark-background contrast and color-blind safety (Deuteranopia-distinguishable). Revisit after burn-in if any pair confuses in real footage.
- **Exhibit-number autoincrement.** Pure sequential per project, three-digit zero-padded, starting at 001. User can manually edit any clip's exhibit number; the auto-increment only assigns to clips that have no number set yet.
- **Transcript search.** Literal substring (case-insensitive) in V1. Phonetic / fuzzy is V2.

---

## 15. Decisions log (this brainstorm)

| Decision                                                                         | Choice                                                       |
|----------------------------------------------------------------------------------|--------------------------------------------------------------|
| Self-contained pipeline vs consume-only reviewer                                 | Self-contained, built into the app                           |
| One unified app (BWC + DME) vs two apps                                          | One app, mode-aware                                          |
| Project / folder model                                                           | Folder-as-project; cache in `.bwcclipper/`; clips in `clips/`|
| Audio-source clip output                                                         | Both raw audio (mp3) and waveform-MP4                        |
| Default navigation                                                               | Collapsed-silence timeline + uncompressed toggle             |
| Codebase / shared library with Depo Clipper                                      | Independent codebase; no shared library                      |
| Models bundled vs downloaded                                                     | >50 MB downloaded by installer; smaller bundled              |
| Background processing                                                            | Always on; foreground source priority                        |
| Pipeline fallbacks                                                               | None; dependency-gated startup                               |
| Clip grading                                                                     | None; manual review only                                     |
| Clip report / Notice of Intent                                                   | Out of V1                                                    |
| Cross-file clips                                                                 | Out of scope                                                 |
