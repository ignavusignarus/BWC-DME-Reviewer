# BWC Clipper

Local-only desktop tool for plaintiff-side review and clipping of body-worn camera (BWC) video and defense medical exam (DME) audio. The app ingests a folder of media, runs a self-contained transcription pipeline (Whisper + VAD + diarization + speech enhancement) on the user's GPU, and presents a reviewer UI in which the auto-generated transcript serves as a navigation aid for finding moments of interest in long, often non-speech-dense recordings. The user creates and exports trial-ready clips. Clips never carry a transcript overlay — the transcript is a tool for the reviewer, not a deliverable on the clip.

> **Status:** Milestone 4 of 8 complete — full pre-AI pipeline (Stages 1–4). After extracting audio (Stage 1) and normalizing it (Stage 2), the engine runs DeepFilterNet 3 speech enhancement (Stage 3) and Silero voice activity detection (Stage 4). VAD output is persisted as `speech-segments.json` per source. The UI status indicator cycles through `extracting…` → `normalizing…` → `enhancing…` → `detecting speech…` → `✓`.

## License

Released under the [Consumer Attorney Open Source License (CAOSL), Version 1.0](LICENSE).

- **Consumer attorneys** — Free for all use, including commercial use in law practice.
- **Non-commercial use** — Free for anyone for education, research, legal aid, and pro bono work.
- **Defense practitioners** (as defined in the License) — Requires a separate written license agreement from the Licensor.

## Documents

- **Design spec:** [`docs/superpowers/specs/2026-04-29-bwc-clipper-design.md`](docs/superpowers/specs/2026-04-29-bwc-clipper-design.md)
- **Transcription pipeline brief:** [`bodycam_transcription_brief.md`](bodycam_transcription_brief.md) — engineering specification for the transcription side of the pipeline; the design doc references it by section.

## Architecture (one paragraph)

Independent codebase mirroring the patterns of [Depo Clipper](https://github.com/ignavusignarus/Depo-Clipper). Python engine for the transcription pipeline, ffmpeg orchestration, clip composition, export, and job/resource management. Electron desktop wrapper with a dependency-gated splash. React UI bundled by esbuild for the reviewer. PyInstaller `--onedir` for the engine. Per-user NSIS installer to `%LOCALAPPDATA%\BWCClipper` — no UAC. Large models (faster-whisper large-v3, pyannote 3.1, wav2vec2 alignment) downloaded by the installer; small models bundled. Local-only: no cloud, no telemetry, no remote processing.

## What the app does

1. Open a folder containing media files (BWC `.mp4` / DME `.mp3` / etc.).
2. App auto-detects mode per source (video → BWC, audio → DME) and runs the full transcription pipeline on the foreground source first, then queues the rest in the background.
3. Reviewer UI shows the media plus a click-to-seek transcript and a **collapsed-silence timeline** that compresses non-speech regions out of the way (uncompressed real-time view available as a toggle).
4. User authors clips by hotkey (I / O / Enter), timeline drag, or transcript text-selection. A per-clip editor offers snap-to-pause boundary tweaking, word-level nudge keys, and loop preview.
5. Export — video sources produce one MP4; audio sources produce both an audio file and a waveform-rendered MP4. No transcript overlay on any output.

See the design spec for full detail.

## Development

### First-time setup

```bash
# Python engine
python -m venv .venv
.venv/Scripts/python.exe -m pip install --upgrade pip      # Windows
# .venv/bin/python -m pip install --upgrade pip            # macOS/Linux
.venv/Scripts/python.exe -m pip install -e ".[dev]"

# Node + Electron
npm install
```

#### GPU acceleration (optional)

The default install pulls the CPU build of PyTorch. DeepFilterNet 3 enhancement
and (in later milestones) Whisper transcription run several times faster on
NVIDIA GPUs. To upgrade an existing venv to CUDA-enabled torch:

```bash
.venv/Scripts/python.exe -m pip install --index-url https://download.pytorch.org/whl/cu121 --upgrade torch torchaudio
```

Verify CUDA is detected:

```bash
.venv/Scripts/python.exe -c "import torch; print('CUDA available:', torch.cuda.is_available())"
```

Auto-detection of CUDA at runtime is handled by torch / DeepFilterNet directly
once the CUDA wheels are installed; no engine code changes are required.

### Run the desktop app

```bash
npm run build:editor   # bundle React editor
npm start              # launch Electron, which spawns the Python engine
```

### Run tests

```bash
.venv/Scripts/python.exe -m pytest    # engine tests
npm test                              # editor tests (vitest)
```

### Watch mode for editor development

```bash
npm run watch:editor   # rebuilds editor-bundle.js on change
```

You'll need to reload the Electron window manually (Ctrl+R) to pick up changes.

## Architecture (one diagram)

```
┌─────────────────────────┐         spawn         ┌──────────────────────┐
│  Electron main process  │ ────────────────────► │  Python engine       │
│  (electron/main.js)     │                       │  (serve.py)          │
│                         │ ◄──── stdout: port ── │                      │
│                         │                       │  http.server on      │
│                         │                       │  127.0.0.1:<port>    │
└────────┬────────────────┘                       └──────────┬───────────┘
         │ contextBridge                                     │ HTTP /api/*
         ▼                                                   │
┌─────────────────────────┐    fetch()                       │
│  Renderer (Chromium)    │ ─────────────────────────────────┘
│  (index.html →          │
│   editor-bundle.js →    │
│   React EditorApp)      │
└─────────────────────────┘
```

Three processes per launch. Engine listens only on loopback. Editor talks to it
over plain HTTP; native operations (folder picker, settings) go through
`window.electronAPI.*` exposed by `electron/preload.js` to the main process.
