# BWC Clipper — Handoff

A handoff for the next agent (or human) picking up work on this project. Read this top-to-bottom before touching code; the rest of the documentation tree is referenced from here.

---

## Project in one paragraph

BWC Clipper is a local-only Windows desktop application for plaintiff-side litigation review of body-worn camera (BWC) video and defense medical exam (DME) audio. It ingests a folder of media, runs a self-contained six-stage transcription pipeline (Whisper + speech enhancement + VAD + word-level alignment) on the user's GPU, and presents a reviewer UI in which the auto-generated transcript serves as a navigation aid. Users author and export trial-ready clips. Clips never carry a transcript overlay — the transcript is a tool for the reviewer, not a deliverable on the clip. License is the Consumer Attorney Open Source License (CAOSL) v1.0, same as the user's prior app Depo Clipper.

The defining UX problem this app solves: a 30-minute BWC where the relevant incident is 90 seconds, surrounded by long stretches of silence; or a 60-minute DME exam where actual speech is 30 minutes interleaved with question-pause-answer pacing. Standard linear scrubbing wastes time. Primary navigation is a collapsed-silence timeline (M6+) that compresses non-speech regions out of the way.

---

## State (post M6 burn-in — fixes landed; re-transcribe feature removed)

**M6 burn-in completed 2026-04-30. Six P0 production blockers found and fixed in a single follow-up pass; re-transcribe / context-names feature removed entirely per user direction.**

| M | Title | Merge | What it shipped |
|---|---|---|---|
| M0 | Skeleton | `320a7eb` | Electron + Python engine HTTP + React editor scaffolding; tests in place |
| M1 | Folder open | `2d96c33` | Native folder picker, `POST /api/project/open` walks media files, project view UI |
| M2 | ffmpeg + Stage 1 | `3830948` | Auto-download ffmpeg; audio extraction; per-source cache subdirs; status indicator UI |
| M3 | Stage 2 + chaining | `4a298ca` | Loudness normalize + dynamic-range compress; pipeline chaining infrastructure (`_PIPELINE_STAGES`); stage-aware status strings |
| M4 | Stage 3 + 4 | `4bbc057` | DeepFilterNet 3 enhancement + Silero VAD; `speech-segments.json` artifact; first ML deps |
| M5 | Stage 5 + 6 | `afcc946` | faster-whisper transcribe (with VAD-filter) + WhisperX wav2vec2 word alignment; `transcript.json` per brief §4.8 schema; **real-model integration test harness** |
| M6 | Reviewer UI surfaces | `dd71bb4` | ThreadedHTTPServer + HTTP Range streaming; `/api/source/{audio,video,transcript}` + `/api/project/reviewer-state`; React reviewer view (TopBar / MediaPane / Waveform / Transport / TranscriptPanel / Timeline collapsed+uncompressed); search with Enter cycling; window-level hotkeys (Space, J/K/L, ←/→, Shift+←/→, /, Ctrl+S, Esc); spec at `docs/superpowers/specs/2026-04-29-bwc-clipper-milestone-6-reviewer-ui-design.md` |
| M6.1 | Burn-in fixes | (this commit) | Production blockers found by burn-in: BWC video mode bug, relative media URLs, layout grid blow-out, empty source-switcher dropdown, all-zero segment IDs, missing CSP `media-src`. Plus collapsed-timeline geometry rewritten to percentage widths (always fits container). **Re-transcribe + context-names feature deleted by user request** (see "Removed surfaces" below). |

**Verified post-fix:** All unit + integration tests pass (140 pytest engine, 79 vitest editor — was 230 pre-removal, drop is the deleted re-transcribe tests). User confirmed in real Electron: audio loads via the engine, click-to-seek works, video element renders for BWC sources.

**Remaining work to V1:**

| M | Title | Scope (rough) |
|---|---|---|
| **M7** | **Clip authoring + export** | **Spec §7-8: in/out marks (I, O), Enter saves clip, clip-list sidebar, FFmpeg-driven export to trial-ready MP4. This is the missing leg of "BWC *Clipper*" — without it, the app finds moments but can't cut them.** |
| M8 | Diarization + wearer detection | pyannote 3.1 + wearer-detection heuristic; populate `transcript.json.speakers`; per-speaker color coding |
| M9 | Dependency-gate splash | Replace the implicit "import fails" gate with an explicit splash-screen check + repair flow |
| M10 | Packaging | NSIS per-user installer; installer-time model downloads (~3 GB total); release artifact pipeline |

The user chose clip authoring (formerly slated for M8) as the next milestone over diarization — clip authoring is on the V1 critical path, diarization is ergonomic improvement.

### Removed surfaces (re-transcribe feature)

Burn-in found that the context-name re-transcribe flow could degrade transcripts (faster-whisper hallucinated "Hello, everyone." × 11 with the names-in-prompt construction). User decided to remove the feature entirely rather than tune the prompt. Deleted:

- `editor/components/reviewer/ContextNamesPanel.jsx` + test
- `editor/usePolling.js` + test (only used by re-transcribe)
- `engine/server.py`: `POST /api/source/context` + `POST /api/source/retranscribe` routes
- `engine/pipeline/runner.py`: `rerun_from_stage()` method
- `engine/pipeline/transcribe.py`: `_read_initial_prompt` + `initial_prompt` decoder param
- `tests/test_server_retranscribe.py`, `tests/test_server_context.py`, `tests/test_runner_rerun.py`
- The retranscribe round-trip case in `tests/integration/test_reviewer_endpoints.py`

If you ever want to bring this back: the design lives in spec §7 of the M6 design doc; the engine path was a single `runner.rerun_from_stage("transcribe", ...)` call; the renderer wiring is the `<ContextNamesPanel>` collapsed-details block in the right column.

---

## Where everything lives

Repository: **`https://github.com/ignavusignarus/BWC-DME-Reviewer`** (public). Local working dir: `C:\Claude Code Projects\BWC Reviewer`.

```
bwc-clipper/
├── docs/
│   ├── HANDOFF.md                    YOU ARE HERE
│   ├── superpowers/
│   │   ├── specs/
│   │   │   ├── 2026-04-29-bwc-clipper-design.md                    Source of truth for design (whole project)
│   │   │   └── 2026-04-29-bwc-clipper-milestone-6-reviewer-ui-design.md   M6 design (post-brainstorm)
│   │   └── plans/                    One file per milestone
│   │       ├── 2026-04-29-bwc-clipper-milestone-0-skeleton.md
│   │       ├── 2026-04-29-bwc-clipper-milestone-1-folder-open.md
│   │       ├── 2026-04-29-bwc-clipper-milestone-2-ffmpeg-extract.md
│   │       ├── 2026-04-29-bwc-clipper-milestone-3-normalize-chain.md
│   │       ├── 2026-04-29-bwc-clipper-milestone-4-enhance-vad.md
│   │       ├── 2026-04-29-bwc-clipper-milestone-5-transcribe-align.md
│   │       └── 2026-04-29-bwc-clipper-milestone-6-reviewer-ui.md
├── bodycam_transcription_brief.md    Engineering brief — pipeline parameters by §
├── engine/                           Python — pipeline + HTTP server
│   ├── server.py                     stdlib http.server with route table
│   ├── version.py                    BWC_CLIPPER_VERSION constant
│   ├── ffmpeg.py                     ffmpeg/ffprobe discovery + run wrappers
│   ├── source.py                     per-source cache helpers + SHA-256
│   ├── project.py                    folder walking + mode detection
│   ├── device.py                     CUDA auto-detect (select_device())
│   ├── df_compat.py                  Torchaudio shim for deepfilternet 0.5.6
│   └── pipeline/
│       ├── __init__.py               imports df_compat to install shim
│       ├── state.py                  pipeline-state.json read/write
│       ├── runner.py                 _PIPELINE_STAGES list + single-worker queue
│       ├── extract.py                Stage 1 (ffmpeg)
│       ├── normalize.py              Stage 2 (ffmpeg loudnorm + compress)
│       ├── enhance.py                Stage 3 (DeepFilterNet 3, chunked)
│       ├── vad.py                    Stage 4 (Silero VAD)
│       ├── transcribe.py             Stage 5 (faster-whisper, vad-filtered)
│       └── align.py                  Stage 6 (WhisperX align + transcript.json)
├── electron/
│   ├── main.js                       Spawns engine, splash → main window
│   ├── preload.js                    contextBridge exposing electronAPI
│   ├── splash.html / splash-preload.js
│   ├── ffmpeg-downloader.js          M2's auto-download
│   └── ffmpeg-hashes.json
├── editor/
│   ├── EditorApp.jsx                 Top-level state (manifest + statuses + polling)
│   ├── api.js                        apiGet / apiPost
│   ├── components/
│   │   ├── EmptyState.jsx
│   │   ├── ProjectView.jsx
│   │   └── FileListItem.jsx          Status indicator with stage labels
│   ├── main.jsx
│   └── test-setup.js                 Vitest jest=vi alias for fake timers
├── tests/
│   ├── test_*.py                     Unit suite (110 tests, all mocked)
│   ├── integration/
│   │   ├── conftest.py
│   │   └── test_stages_real_models.py    6 real-model tests, ~12s on GPU
│   └── fixtures/                     gitignored — see conftest for regen
└── serve.py                          Engine entry point — picks port, prints to stdout
```

Per-source cache layout (created by the engine at runtime; under the user's project folder):

```
my-case-folder/
├── officer-garcia.mp4
├── doctor.MP3
└── .bwcclipper/                      Hidden, gitignore-friendly
    ├── officer-garcia/
    │   ├── source.sha256
    │   ├── source.json               ffprobe track metadata
    │   ├── pipeline-state.json       per-stage status
    │   ├── extracted/track0.wav      Stage 1 output
    │   ├── normalized/track0.wav     Stage 2
    │   ├── enhanced/track0.wav       Stage 3
    │   ├── speech-segments.json      Stage 4
    │   ├── transcribe-raw.json       Stage 5 intermediate
    │   └── transcript.json           Stage 6 — canonical, brief §4.8 schema
    └── doctor/...
```

---

## Architecture in one diagram

```
┌─────────────────────────┐         spawn         ┌──────────────────────┐
│  Electron main process  │ ────────────────────► │  Python engine       │
│  (electron/main.js)     │  passes               │  (serve.py + engine) │
│                         │  BWC_CLIPPER_FFMPEG_  │                      │
│                         │  DIR env var          │  http.server on      │
│                         │ ◄──── stdout: port ── │  127.0.0.1:<port>    │
└────────┬────────────────┘                       └──────────┬───────────┘
         │ contextBridge (preload.js)                        │ HTTP /api/*
         ▼                                                   │
┌─────────────────────────┐    fetch()                       │
│  Renderer (Chromium)    │ ─────────────────────────────────┘
│  (index.html →          │
│   editor-bundle.js →    │
│   React EditorApp)      │
└─────────────────────────┘
```

The engine runs as a child process of Electron, listening only on loopback. It picks a random free port and prints `BWC_CLIPPER_PORT=<n>` to stdout; Electron parses that line and exposes the URL to the renderer via `electronAPI.getEngineUrl()`.

The pipeline runs inside the engine on a single-worker `ThreadPoolExecutor`. `_PIPELINE_STAGES` in `engine/pipeline/runner.py` is the canonical extension point — append a `(name, callable)` tuple to add a stage. M3's chaining infrastructure handles the rest (skip-when-completed, stage-aware status reporting, error capture).

---

## Environment

**Hardware target:** Windows 11 + NVIDIA GPU (RTX 3090/4090/5080 class). Tested on RTX 5080 (Blackwell, sm_120). CPU-only mode is supported but slow.

**Python:** 3.11 in `.venv/` at the repo root. **Use the `py` launcher** (`py -3.11 -m venv .venv`) to ensure 3.11 specifically — system Python on the dev machine is 3.14, and pyproject.toml's `requires-python = ">=3.11,<3.13"` will reject newer.

**Torch:** `2.7.0+cu128` for the dev machine (RTX 5080 needs cu128; older Ada/Turing GPUs work with cu121 on torch 2.5+). Install via:

```bash
.venv/Scripts/python.exe -m pip install --index-url https://download.pytorch.org/whl/cu128 \
    torch==2.7.0+cu128 torchaudio==2.7.0+cu128
```

**Other ML deps** (`deepfilternet 0.5.6`, `silero-vad >=5.0`, `faster-whisper >=1.2`, `whisperx >=3.1`) come from `pip install -e ".[dev]"`.

**ffmpeg:** Auto-downloaded by Electron on first launch into `%APPDATA%\bwc-clipper\ffmpeg\`. The engine reads `BWC_CLIPPER_FFMPEG_DIR` env var (set by Electron) to find it. For ad-hoc Python scripts and integration tests, set the env var manually:

```bash
export BWC_CLIPPER_FFMPEG_DIR="C:/Users/<you>/AppData/Roaming/bwc-clipper/ffmpeg"
```

**Models cached at:**
- DeepFilterNet 3: `%LOCALAPPDATA%\DeepFilterNet\DeepFilterNet\Cache\DeepFilterNet3\`
- faster-whisper large-v3: `~/.cache/huggingface/hub/`
- WhisperX wav2vec2: same HF hub cache
- ~3 GB total, downloaded on first inference

**Run commands:**

```bash
# Unit tests (fast, all mocked)
.venv/Scripts/python.exe -m pytest

# Integration tests (real models, ~12 s on GPU, requires ffmpeg discoverable)
BWC_CLIPPER_FFMPEG_DIR="..." .venv/Scripts/python.exe -m pytest -m integration

# Editor tests (vitest)
npm test

# Build editor bundle
npm run build:editor

# Launch the desktop app
npm start
```

---

## How to pick up work

1. **Read this file first.**
2. **Read the spec:** `docs/superpowers/specs/2026-04-29-bwc-clipper-design.md`. It's the source of truth for design decisions; updates to architecture should propagate there.
3. **Read the brief** (`bodycam_transcription_brief.md`) for transcription pipeline parameters by section. Each pipeline stage's docstring references the brief section it implements.
4. **Read the most recent merged milestone's plan** (`docs/superpowers/plans/2026-04-29-bwc-clipper-milestone-5-transcribe-align.md`) to see how the existing pattern is structured.
5. **Skim memory files** at `~/.claude/projects/C--Claude-Code-Projects-BWC-Reviewer/memory/` (if running under Claude Code on the original dev workstation) — these capture user preferences, environment quirks, and lessons learned.

For a new milestone:
- Invoke the `superpowers:brainstorming` skill if scope is uncertain, otherwise `superpowers:writing-plans` directly with the milestone scope.
- Plans live at `docs/superpowers/plans/YYYY-MM-DD-<feature-name>.md`.
- Execute with `superpowers:subagent-driven-development` (or inline if the milestone is small).
- Branch named `milestone-N-<short-name>`. Merge with `--no-ff` to preserve milestone boundaries in `git log --graph`.

---

## Workflow patterns established

**Stage protocol** (every pipeline stage follows this):

1. Module-level model singleton with lazy load (`_get_<model>` accessor)
2. A small helper function (`<verb>_audio_file()` or similar) wrapping the heavy ML call — **tests mock at this boundary**, not deeper
3. `run_<stage>_stage(cache_dir)` orchestrator that:
   - Marks status RUNNING in pipeline-state.json
   - Pre-validates ALL input file paths (fail fast before any expensive work)
   - Calls the helper(s)
   - Writes outputs
   - Marks status COMPLETED
   - On any exception: marks status FAILED with error string, then re-raises

See `engine/pipeline/normalize.py` for the canonical example. **Don't deviate from this protocol unless you have a concrete reason** — the runner's chained-execution and resume-from-failure logic depends on it.

**Test layering:**

- Unit tests: 100% mocked at the helper boundary. Fast (~10 s for 110 tests). Verify orchestration, schema, error paths.
- Integration tests (`@pytest.mark.integration`): real models on real audio fixtures. Slow (~12 s on GPU for 6 tests; minutes on CPU). Verify API compatibility, model output shape, real-world failure modes.
- Both fixtures (15 s `sample_short.wav`, 90 s `sample_long.wav`) are **required** — short catches API-shape bugs, long catches scale/limit bugs (e.g., the cuDNN long-sequence limit on enhance only manifested at >5 minutes of audio).
- See `tests/integration/conftest.py` for fixture regeneration commands.

**When integration tests catch bugs:** fix the code, then add a smaller-scoped integration test that would have caught it. Don't merge until the new test fails on the buggy code and passes on the fix.

**Git pattern per milestone:** branch off main → atomic commits during work → all tests green → push branch to origin → switch to main → `git merge --no-ff <branch> -m "Merge milestone N: ..."` with a comprehensive message describing what shipped + bugs caught + scope deferred → push main → delete branch local + remote.

---

## Critical lessons learned

These are recorded in `memory/feedback_*` files; summary here:

1. **Mock-based unit tests are insufficient for ML pipelines.** Always pair them with a real-model integration harness. M5 had 7 real bugs; 4 were caught by the harness on first run, the rest by manual launch on production audio.
2. **Long-audio integration coverage matters too.** A 15-second fixture caught most M5 bugs but missed two (3× duration mismatch, cuDNN long-sequence failure). Always include a fixture longer than your stage's longest single-call capacity. For DF3 specifically, longer than 60 seconds.
3. **LLM plan reviewers can be confidently wrong.** The plan reviewer asserted faster-whisper used `logprob_threshold` (no underscore) based on the brief's documentation; the actual API is `log_prob_threshold` (with underscore). Manual launch caught it. Don't trust review-only validation for API names; verify with `inspect.signature`.
4. **Library subprocess calls don't honor your custom env vars.** WhisperX shells out to `ffmpeg` via subprocess and only finds it via PATH. The engine prepends the ffmpeg dir to `os.environ["PATH"]` at startup (in `serve.py`) AND in integration tests' autouse session fixture.
5. **deepfilternet 0.5.6 + torchaudio 2.6+** has a hard incompatibility (`torchaudio.backend.common` was removed). `engine/df_compat.py` synthesizes the legacy module at import time. Remove this when deepfilternet ships a fixed version.
6. **`vad_filter=True` in faster-whisper is essential.** Without it, long stretches of silence (typical in DME audio between questions) produce hallucinated phrases like "Thanks for watching." The fix is one parameter.
7. **DeepFilterNet 3 must chunk for long audio.** cuDNN's `CUDNN_STATUS_NOT_SUPPORTED` triggers on sequences over a few minutes. 60-second chunks at 48 kHz work cleanly on a 16 GB VRAM GPU.

---

## Known issues (non-blocking)

- **Test flake on Windows:** `tests/test_server_source.py::test_unknown_post_path_returns_404` rarely flakes because the engine sends 404 before reading the request body, causing a TCP connection-reset on Windows. Not blocking; documented in `memory/feedback_bwc_test_flake.md`.
- **Some align segments fall back to original timestamps:** WhisperX's wav2vec2 backtrack fails on a few segments per file (typically <5%). The fallback behavior preserves the segment-level timestamps but doesn't have word-level. Acceptable for V1; could investigate in M7+ if downstream features need word-level on every segment.
- **VAD parameter tuning for DME:** Brief §4.4 parameters were chosen for BWC. On the Heather Williams ENT exam they detected 1,225 segments with 45% silence skipped, which is reasonable, but could be tuned. Worth burn-in testing across multiple sources before fixing.

### M6 burn-in fixes summary

Manual burn-in 2026-04-30 found six P0 production blockers + assorted polish. All addressed in this commit. Full audit (with file:line refs and severity ranking) is at `docs/BURN-IN-2026-04-30.md`. Headline fixes:

- **BWC video played as audio** — `MediaPane.jsx` checked `mode === 'video'` but engine emits `'bwc'`; `<video>` never rendered.
- **Relative media URLs** — `MediaPane.jsx` used `/api/source/audio?...` which resolved to `file:///api/...` under Electron. Now prefixed with `engineBase` from `ReviewerContext`.
- **CSP missing `media-src`** — `index.html`'s CSP only had `connect-src`; `<audio>`/`<video>` loads were silently CSP-blocked. Added `media-src http://127.0.0.1:* blob:`.
- **Layout grid blow-out** — `ReviewerView.jsx` used `grid-template-columns: 1fr 360px`; long-audio collapsed timeline pushed transcript column off-screen at x≈17000px. Now `minmax(0, 1fr) 360px`.
- **Source-switcher dropdown empty** — `TopBar.jsx` filtered on `f.completed` which the engine never set. `engine/project.py:open_project` now reads `pipeline-state.json` per file and populates `completed: bool`.
- **All segment IDs were 0** — faster-whisper's `Segment.id` is always 0 with `vad_filter=True`. Auto-scroll-to-active was always scrolling to segment 0. `engine/pipeline/transcribe.py` now assigns sequential IDs via `enumerate()`; renderer also defensively renumbers cached transcripts on receive.
- **Collapsed-timeline geometry** — fixed-pixel silence cells (24 px each) + `flex-shrink: 0` blew the cell sum past viewport on long audio (overflow:hidden clipped most cells). Rewrote `useTimelineGeometry` to percentage widths summing to 100 % of container: 25 % silence-budget shared evenly across silence cells, 75 % speech split proportional to duration. Expanded silence gets 20 %.

Smaller fixes folded in:

- `transcribe.py` no longer reads `context.json` or builds an `initial_prompt` (was the source of "Hello, everyone." × 11 hallucinations).
- `engine/server.py` adds `do_OPTIONS` so cross-origin browser clients pass CORS preflight.
- `Waveform.jsx` closes its `AudioContext` after decode (avoids the ~6 hardware-context cap).
- `EditorApp.jsx` polling auto-routes to reviewer on `completed` (no more "click the file twice").
- `Transport.jsx` / `TranscriptPanel.jsx` / `Timeline.jsx` render `H:MM:SS` for ≥60-min audio.

### Dev harness for QA

`dev_server.py` + `dev-chrome.html` + `dev-shim.js` (all at repo root) are a small Chrome harness that lets you drive the renderer outside of Electron. Useful for diagnosing renderer bugs without rebuilding the desktop app. **Not loaded by Electron — production still uses `index.html`.** See top of `dev_server.py` for run instructions.

---

## Resuming work — quick start

**M6 status:** burn-in done, fixes shipped. Tests green: 140 pytest engine + 79 vitest editor (was 230 pre-removal — re-transcribe deletion accounts for the drop).

```bash
cd "C:/Claude Code Projects/BWC Reviewer"
npm start
```

The recommended quick smoke test for the next session:

1. Open `Samples/` → click DME ENT → reviewer view loads instantly (cached). Audio plays. Click a transcript line → audio jumps. Search "doctor" → 2 matches highlighted, gold dots on timeline, Enter cycles. Toggle ⇄ uncompressed timeline.
2. Click sja00161 (BWC, 12:31, fully cached) → `<video>` element renders, plays.
3. Top dropdown lists both completed sources; click switches between them.

If anything's broken: open Electron DevTools (Ctrl+Shift+I) before doing anything that loads media — the "audio loaded but doesn't play" symptom is almost always a CSP block visible in console.

**If smoke test is clean:**
- Push main to origin if not already pushed.
- Begin M7 prep. The spec calls for pyannote 3.1 diarization + wearer detection + a dependency-gate splash. The runner's `_PIPELINE_STAGES` list is the extension point — adding diarize/wearer-detect after `align` makes `rerun_from_stage("transcribe", ...)` automatically invalidate them, per the M6 spec's forward-compat note.

---

## What "done" looks like for shipping V1

The spec's §2 explicitly defines V1 scope. The remaining gap to V1:

- **Reviewer UI** (M6 + M6.1 burn-in): ✅ done.
- **Clip authoring + export** (next, M7 in current numbering): the spec's §7-8 features. The missing leg of "BWC *Clipper*". This is the largest remaining piece of work.
- **Diarization + wearer detection**: pyannote 3.1 speaker labels + per-speaker color coding. Ergonomic improvement, not on V1 critical path.
- **Dependency gate splash**: replace the implicit "import fails" gate with an explicit splash-screen check + repair flow.
- **Packaging**: NSIS installer, model bundling.

The pipeline engine is feature-complete after M5. Everything else is UI + packaging.
