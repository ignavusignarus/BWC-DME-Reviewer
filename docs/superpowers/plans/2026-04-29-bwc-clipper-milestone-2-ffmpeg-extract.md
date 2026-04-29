# BWC Clipper — Milestone 2: ffmpeg Integration + Audio Extraction (Stage 1) — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make BWC Clipper start running real audio processing for the first time. Bundled ffmpeg is downloaded automatically on first launch (Depo Clipper pattern). When the user selects a source file in the project view, the engine extracts each audio track to a 16 kHz mono WAV in the source's per-source cache subdirectory, hashes the source file with SHA-256, writes a `pipeline-state.json`, and the file's row in the UI shows the live processing status — `queued` → `extracting` → `ready`.

**Architecture:** Electron main process downloads ffmpeg + ffprobe binaries to `%LOCALAPPDATA%\BWCClipper\ffmpeg\` on first launch and exports the directory path to the engine via the `BWC_CLIPPER_FFMPEG_DIR` environment variable when spawning `serve.py`. Engine has a single-worker `concurrent.futures.ThreadPoolExecutor` that runs pipeline jobs serially; new requests for already-completed sources are skipped. Pipeline state is persisted in `pipeline-state.json` per source; the UI polls `GET /api/source/state` while a source is processing. Subprocess invocations of ffmpeg/ffprobe are wrapped in `engine/ffmpeg.py`; tests mock `subprocess.run` (no real ffmpeg required for the unit suite).

**Tech Stack:** Python stdlib `subprocess` + `concurrent.futures`, Node `https` + `crypto` for the downloader, ffmpeg/ffprobe binaries (downloaded), continuing React 19 + esbuild for the UI. No new pip dependencies.

**Scope of this milestone:**
- ffmpeg download infrastructure (Electron side) and path discovery (engine side).
- Engine wrappers `find_ffmpeg`, `run_ffmpeg`, `run_ffprobe`, `probe_audio_tracks`.
- Pipeline scaffolding: `engine/pipeline/` package with state persistence, single-worker runner, Stage protocol.
- **Stage 1 only — audio extraction**, including per-track WAV output (`track{N}.wav` under `<cache>/extracted/`), source SHA-256, ffprobe track metadata persisted as `source.json`, and `pipeline-state.json`.
- New engine HTTP endpoints: `POST /api/source/process`, `GET /api/source/state`.
- UI: `FileListItem` shows status indicator; selecting a file auto-triggers processing; `EditorApp` polls state while any source is in progress.

**Out of scope for this milestone (deliberately deferred):**
- Stages 2–8 (normalize, enhance, VAD, transcribe, align, diarize, wearer-detect, output assembly). Stage 2+ arrive in Milestone 3.
- Real "foreground priority" preemption — V1 has FIFO single-worker queueing; switching the active source jumps the new file to the front of the queue, but the in-flight job continues to completion. The full preemptable resource manager is Milestone 6.
- Background processing of unviewed sources — V1 only processes a source when explicitly requested via `/api/source/process`. Auto-queue of all unprocessed sources arrives in Milestone 6.
- Granular ffmpeg progress (real-time `time=` parsing) — V1 reports stage-level state (queued/running/completed/failed) only. Per-stage progress arrives later if needed.
- macOS ffmpeg downloads — V1 Windows-only. macOS download support is a copy of the Depo Clipper pattern when we get to packaging (Milestone 8).

---

## File Structure

```
bwc-clipper/
├── electron/
│   ├── ffmpeg-hashes.json                  NEW — known-good ffmpeg + ffprobe URLs for win64
│   ├── ffmpeg-downloader.js                NEW — download, verify, extract; idempotent
│   └── main.js                             MODIFY — call ffmpeg-downloader on first launch,
│                                            set BWC_CLIPPER_FFMPEG_DIR env when spawning engine
├── engine/
│   ├── ffmpeg.py                           NEW — find_ffmpeg, run_ffmpeg, run_ffprobe,
│   │                                        probe_audio_tracks
│   ├── source.py                           NEW — source-cache helpers (paths, SHA-256)
│   ├── pipeline/                           NEW DIRECTORY
│   │   ├── __init__.py                     NEW
│   │   ├── state.py                        NEW — pipeline-state.json read/write
│   │   ├── extract.py                      NEW — Stage 1 implementation
│   │   └── runner.py                       NEW — single-worker queue + dispatch
│   └── server.py                           MODIFY — add POST /api/source/process,
│                                            GET /api/source/state
├── editor/
│   ├── api.js                              MODIFY — add startPolling helper
│   ├── components/
│   │   ├── FileListItem.jsx                MODIFY — render stage status indicator
│   │   ├── FileListItem.test.jsx           MODIFY — add status tests
│   │   ├── ProjectView.jsx                 MODIFY — propagate per-source status
│   │   └── ProjectView.test.jsx            MODIFY — add status-flow tests
│   ├── EditorApp.jsx                       MODIFY — kick off processing on select,
│   │                                        poll state, update manifest
│   └── EditorApp.test.jsx                  MODIFY — add process-on-select tests
└── tests/
    ├── test_ffmpeg.py                      NEW
    ├── test_source.py                      NEW
    ├── test_pipeline_state.py              NEW
    ├── test_pipeline_extract.py            NEW
    ├── test_pipeline_runner.py             NEW
    └── test_server_source.py               NEW — POST /api/source/process + GET /api/source/state
```

**Why split `engine/source.py` and `engine/project.py`:** project owns folder-level concerns (walk, mode detect, project-level cache); source owns per-file concerns (per-source cache subdirectory, source SHA-256). Both compose, neither subsumes the other.

**Why `engine/pipeline/` is a package, not one big file:** later milestones add 7 more stages. The package boundary is `extract.py`, `normalize.py`, `enhance.py`, etc. — each ~50 lines, each independently testable. `runner.py` is the orchestrator. `state.py` is shared persistence. This decomposition is stable and grows linearly per stage.

---

## Reference patterns

| Plan section | Reference (read for pattern, do not copy verbatim) |
|---|---|
| `electron/ffmpeg-downloader.js` | `Depo-Clipper/electron/ffmpeg-downloader.js` — same shape (download, verify, extract, getFFmpegDir). Simplify: Windows-only for V1, no macOS. |
| `electron/ffmpeg-hashes.json` | `Depo-Clipper/electron/ffmpeg-hashes.json` — same multi-source fallback pattern. Drop darwin entries for V1. |
| `engine/ffmpeg.py` (`probe_audio_tracks`) | `Depo-Clipper/engine/prober.py` — `probe_video()` and `probe_all()` are the rough shape. |
| Single-worker job runner | `Depo-Clipper/engine/job_manager.py` — V1 strips this down to a single `ThreadPoolExecutor(max_workers=1)`. |
| `BWC_CLIPPER_FFMPEG_DIR` env passing | `Depo-Clipper/electron/main.js` — search for the env-var hand-off when spawning Python. |

---

## Testing strategy

- **Engine tests run without a real ffmpeg.** All `subprocess.run` calls are intercepted with `unittest.mock.patch` returning canned `CompletedProcess` or `CalledProcessError` objects. The wrappers in `engine/ffmpeg.py` are pure orchestration; the actual binary execution is verified by the manual launch step.
- **Real-binary integration is verified by Task 16 (manual launch).** The user opens the app, lets ffmpeg download, picks the `Samples/` folder, selects a `.mp4` from `Samples/BWC/`, and watches the row's status flip from `queued` → `extracting` → `ready`. The cache subdirectory then contains a real `track0.wav` they can play.
- **No new pip deps for testing** — `unittest.mock` is stdlib.

---

## Tasks

### Task 1: Create milestone-2 branch

- [ ] **Step 1: Verify clean working tree on main**

```bash
cd "C:/Claude Code Projects/BWC Reviewer"
git status
git rev-parse --abbrev-ref HEAD
git log -1 --oneline
```

Expected: clean, on `main`, last commit is `2d96c33` (M1 merge).

- [ ] **Step 2: Create branch**

```bash
git checkout -b milestone-2-ffmpeg-extract
```

- [ ] **Step 3: No commit; branch created.**

---

### Task 2: `electron/ffmpeg-hashes.json` (Windows-only sources)

**Files:**
- Create: `electron/ffmpeg-hashes.json`

- [ ] **Step 1: Create the file**

```json
{
    "_comment": "FFmpeg + ffprobe download sources for BWC Clipper. Windows-only for V1; macOS arrives in packaging milestone.",
    "win64": {
        "sources": [
            {
                "label": "gyan.dev",
                "url": "https://www.gyan.dev/ffmpeg/builds/ffmpeg-release-essentials.zip",
                "sha256": null,
                "format": "zip"
            },
            {
                "label": "GitHub BtbN",
                "url": "https://github.com/BtbN/FFmpeg-Builds/releases/download/latest/ffmpeg-master-latest-win64-gpl.zip",
                "sha256": null,
                "format": "zip"
            }
        ],
        "note": "sha256 null = no verification yet. After first successful download, capture the hash and pin it here."
    }
}
```

- [ ] **Step 2: Commit**

```bash
git add electron/ffmpeg-hashes.json
git commit -m "electron: add ffmpeg-hashes.json with win64 source fallback chain"
```

---

### Task 3: `electron/ffmpeg-downloader.js`

**Files:**
- Create: `electron/ffmpeg-downloader.js`

This is a Node script the Electron main process imports. Single responsibility: ensure ffmpeg.exe + ffprobe.exe exist in the per-user app data directory. If already present, return their paths immediately. If missing, download from the first working source in `ffmpeg-hashes.json`, verify SHA-256 if pinned, extract the binaries from the zip into the target directory, return paths.

- [ ] **Step 1: Create the file**

```javascript
/*
 * ffmpeg + ffprobe downloader for Windows.
 *
 * On first launch, downloads a release-essentials zip from the first
 * working source in ffmpeg-hashes.json, verifies the SHA-256 if pinned,
 * extracts ffmpeg.exe and ffprobe.exe into:
 *
 *     %LOCALAPPDATA%\BWCClipper\ffmpeg\
 *
 * Subsequent launches find the binaries already present and skip the
 * download. Reports progress via an optional onProgress(fraction)
 * callback so the splash window can show a progress indicator.
 *
 * macOS support arrives in the packaging milestone; this file is
 * Windows-only for V1.
 */

'use strict';

const fs = require('fs');
const path = require('path');
const https = require('https');
const crypto = require('crypto');
const { spawnSync } = require('child_process');
const { app } = require('electron');

const HASHES = require('./ffmpeg-hashes.json');

function getFFmpegDir() {
    // %LOCALAPPDATA%\BWCClipper\ffmpeg on Windows; equivalent on other platforms.
    return path.join(app.getPath('userData'), 'ffmpeg');
}

function ffmpegBinaryName() {
    return process.platform === 'win32' ? 'ffmpeg.exe' : 'ffmpeg';
}

function ffprobeBinaryName() {
    return process.platform === 'win32' ? 'ffprobe.exe' : 'ffprobe';
}

function isInstalled() {
    const dir = getFFmpegDir();
    return fs.existsSync(path.join(dir, ffmpegBinaryName())) &&
           fs.existsSync(path.join(dir, ffprobeBinaryName()));
}

function downloadBuffer(url, onProgress) {
    return new Promise((resolve, reject) => {
        const fetch = (currentUrl, redirectsLeft) => {
            https.get(currentUrl, { headers: { 'User-Agent': 'BWCClipper/0.0.1' } }, (res) => {
                if (res.statusCode >= 300 && res.statusCode < 400 && res.headers.location) {
                    if (redirectsLeft <= 0) return reject(new Error('too many redirects'));
                    return fetch(res.headers.location, redirectsLeft - 1);
                }
                if (res.statusCode !== 200) {
                    return reject(new Error(`download failed: HTTP ${res.statusCode}`));
                }
                const total = parseInt(res.headers['content-length'] || '0', 10);
                const chunks = [];
                let downloaded = 0;
                res.on('data', (chunk) => {
                    chunks.push(chunk);
                    downloaded += chunk.length;
                    if (onProgress && total > 0) onProgress(downloaded / total);
                });
                res.on('end', () => resolve(Buffer.concat(chunks)));
                res.on('error', reject);
            }).on('error', reject);
        };
        fetch(url, 5);
    });
}

function verifySha256(buffer, expected) {
    if (!expected) return; // unpinned
    const actual = crypto.createHash('sha256').update(buffer).digest('hex');
    if (actual !== expected) {
        throw new Error(`SHA-256 mismatch: expected ${expected}, got ${actual}`);
    }
}

function extractBinariesFromZip(zipPath, outDir) {
    // Use PowerShell's built-in Expand-Archive (every Win10+ has it),
    // then walk the extract dir to find ffmpeg.exe and ffprobe.exe.
    const tmpExtract = path.join(outDir, '_extract');
    fs.rmSync(tmpExtract, { recursive: true, force: true });
    fs.mkdirSync(tmpExtract, { recursive: true });

    const result = spawnSync(
        'powershell',
        ['-NoProfile', '-Command', `Expand-Archive -LiteralPath '${zipPath}' -DestinationPath '${tmpExtract}' -Force`],
        { stdio: 'pipe', encoding: 'utf8' }
    );
    if (result.status !== 0) {
        throw new Error(`Expand-Archive failed: ${result.stderr || result.stdout}`);
    }

    // Recursively find ffmpeg.exe and ffprobe.exe and copy them to outDir.
    const findAndCopy = (dir, target) => {
        for (const entry of fs.readdirSync(dir, { withFileTypes: true })) {
            const full = path.join(dir, entry.name);
            if (entry.isDirectory()) {
                const found = findAndCopy(full, target);
                if (found) return found;
            } else if (entry.name === target) {
                fs.copyFileSync(full, path.join(outDir, target));
                return full;
            }
        }
        return null;
    };
    if (!findAndCopy(tmpExtract, ffmpegBinaryName())) {
        throw new Error('ffmpeg.exe not found in zip');
    }
    if (!findAndCopy(tmpExtract, ffprobeBinaryName())) {
        throw new Error('ffprobe.exe not found in zip');
    }

    fs.rmSync(tmpExtract, { recursive: true, force: true });
}

async function ensureInstalled(onProgress) {
    if (isInstalled()) return getFFmpegDir();

    const dir = getFFmpegDir();
    fs.mkdirSync(dir, { recursive: true });

    if (process.platform !== 'win32') {
        throw new Error('ffmpeg auto-download is Windows-only in V1');
    }

    const platformKey = 'win64';
    const sources = (HASHES[platformKey] && HASHES[platformKey].sources) || [];
    if (sources.length === 0) throw new Error(`no sources configured for ${platformKey}`);

    let lastError = null;
    for (const source of sources) {
        try {
            if (onProgress) onProgress({ phase: 'downloading', source: source.label, fraction: 0 });
            const buffer = await downloadBuffer(source.url, (f) => {
                if (onProgress) onProgress({ phase: 'downloading', source: source.label, fraction: f });
            });
            verifySha256(buffer, source.sha256);

            if (onProgress) onProgress({ phase: 'extracting', source: source.label, fraction: 1 });
            const tmpZip = path.join(dir, '_download.zip');
            fs.writeFileSync(tmpZip, buffer);
            try {
                extractBinariesFromZip(tmpZip, dir);
            } finally {
                fs.rmSync(tmpZip, { force: true });
            }

            if (onProgress) onProgress({ phase: 'ready', source: source.label, fraction: 1 });
            return dir;
        } catch (err) {
            console.warn(`[ffmpeg-downloader] source "${source.label}" failed: ${err.message}`);
            lastError = err;
        }
    }
    throw new Error(`all ffmpeg sources failed; last: ${lastError && lastError.message}`);
}

module.exports = {
    getFFmpegDir,
    ffmpegBinaryName,
    ffprobeBinaryName,
    isInstalled,
    ensureInstalled,
};
```

- [ ] **Step 2: No automated test (downloader exercised at launch in Task 16).** Commit.

```bash
git add electron/ffmpeg-downloader.js
git commit -m "electron: add ffmpeg-downloader with win64 source fallback and SHA-256 verify"
```

---

### Task 4: `electron/main.js` — wire downloader into splash + pass `BWC_CLIPPER_FFMPEG_DIR` to engine

**Files:**
- Modify: `electron/main.js`

The downloader runs on the splash screen, before the engine subprocess is spawned. Once it returns, we pass the resolved directory to `serve.py` via the `BWC_CLIPPER_FFMPEG_DIR` env var so `engine/ffmpeg.py` can find the binaries.

- [ ] **Step 1: Add the require near the top of `electron/main.js`**

Find:

```javascript
const { app, BrowserWindow, dialog, ipcMain } = require('electron');
const { spawn } = require('child_process');
const path = require('path');
const fs = require('fs');
```

Add immediately after:

```javascript
const ffmpegDownloader = require('./ffmpeg-downloader');
```

- [ ] **Step 2: Add a global `ffmpegDir` variable below the existing globals**

Find:

```javascript
let mainWindow = null;
let splashWindow = null;
let pythonProcess = null;
let serverPort = null;
let isShuttingDown = false;
```

Replace with:

```javascript
let mainWindow = null;
let splashWindow = null;
let pythonProcess = null;
let serverPort = null;
let isShuttingDown = false;
let ffmpegDir = null;
```

- [ ] **Step 3: Modify `spawnEngine()` to pass the env var**

Find inside `spawnEngine()`:

```javascript
const proc = spawn(py, [servePy], {
    cwd: REPO_ROOT,
    env: { ...process.env, PYTHONUNBUFFERED: '1' },
    stdio: ['ignore', 'pipe', 'pipe'],
});
```

Replace with:

```javascript
const env = { ...process.env, PYTHONUNBUFFERED: '1' };
if (ffmpegDir) env.BWC_CLIPPER_FFMPEG_DIR = ffmpegDir;
const proc = spawn(py, [servePy], {
    cwd: REPO_ROOT,
    env,
    stdio: ['ignore', 'pipe', 'pipe'],
});
```

- [ ] **Step 4: Replace the `app.whenReady()` block to ensure ffmpeg first**

Find:

```javascript
app.whenReady().then(async () => {
    createSplashWindow();
    setSplashStatus('Starting engine…');
    try {
        const { proc, port } = await spawnEngine();
        pythonProcess = proc;
        serverPort = port;
        setSplashStatus('Engine started. Loading editor…');
        createMainWindow();
    } catch (err) {
        console.error('[main] engine startup failed:', err);
        setSplashStatus(`Failed to start engine: ${err.message}`);
        // Leave splash visible so the user sees the error. They can close it manually.
    }
    app.on('activate', () => {
        if (BrowserWindow.getAllWindows().length === 0) createSplashWindow();
    });
});
```

Replace with:

```javascript
app.whenReady().then(async () => {
    createSplashWindow();
    setSplashStatus('Checking ffmpeg…');
    try {
        ffmpegDir = await ffmpegDownloader.ensureInstalled((status) => {
            if (status.phase === 'downloading') {
                const pct = Math.round(status.fraction * 100);
                setSplashStatus(`Downloading ffmpeg from ${status.source}… ${pct}%`);
            } else if (status.phase === 'extracting') {
                setSplashStatus('Extracting ffmpeg…');
            }
        });
    } catch (err) {
        console.error('[main] ffmpeg setup failed:', err);
        setSplashStatus(`Failed to install ffmpeg: ${err.message}`);
        return;
    }

    setSplashStatus('Starting engine…');
    try {
        const { proc, port } = await spawnEngine();
        pythonProcess = proc;
        serverPort = port;
        setSplashStatus('Engine started. Loading editor…');
        createMainWindow();
    } catch (err) {
        console.error('[main] engine startup failed:', err);
        setSplashStatus(`Failed to start engine: ${err.message}`);
    }
    app.on('activate', () => {
        if (BrowserWindow.getAllWindows().length === 0) createSplashWindow();
    });
});
```

- [ ] **Step 5: No automated test for this wiring; verified at launch in Task 16.** Commit.

```bash
git add electron/main.js
git commit -m "electron: ensure ffmpeg before engine spawn; pass dir via env var"
```

---

### Task 5: `engine/ffmpeg.py` — `find_ffmpeg` / `find_ffprobe` (TDD)

**Files:**
- Create: `tests/test_ffmpeg.py`
- Create: `engine/ffmpeg.py`

- [ ] **Step 1: Write the failing test**

`tests/test_ffmpeg.py`:

```python
"""Tests for engine.ffmpeg path discovery."""
import os
from pathlib import Path

import pytest

from engine.ffmpeg import find_ffmpeg, find_ffprobe


def test_find_ffmpeg_uses_bwc_clipper_ffmpeg_dir(tmp_path: Path, monkeypatch):
    fake = tmp_path / "ffmpeg.exe" if os.name == "nt" else tmp_path / "ffmpeg"
    fake.write_bytes(b"")
    monkeypatch.setenv("BWC_CLIPPER_FFMPEG_DIR", str(tmp_path))
    assert find_ffmpeg() == fake


def test_find_ffprobe_uses_bwc_clipper_ffmpeg_dir(tmp_path: Path, monkeypatch):
    fake = tmp_path / "ffprobe.exe" if os.name == "nt" else tmp_path / "ffprobe"
    fake.write_bytes(b"")
    monkeypatch.setenv("BWC_CLIPPER_FFMPEG_DIR", str(tmp_path))
    assert find_ffprobe() == fake


def test_find_ffmpeg_raises_if_not_found(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("BWC_CLIPPER_FFMPEG_DIR", str(tmp_path))
    monkeypatch.setenv("PATH", "")  # no system fallback
    with pytest.raises(FileNotFoundError):
        find_ffmpeg()


def test_find_ffmpeg_falls_back_to_path(tmp_path: Path, monkeypatch):
    """If BWC_CLIPPER_FFMPEG_DIR not set, search PATH."""
    monkeypatch.delenv("BWC_CLIPPER_FFMPEG_DIR", raising=False)
    fake_dir = tmp_path / "binstub"
    fake_dir.mkdir()
    fake = fake_dir / ("ffmpeg.exe" if os.name == "nt" else "ffmpeg")
    fake.write_bytes(b"")
    monkeypatch.setenv("PATH", str(fake_dir))
    assert find_ffmpeg() == fake
```

- [ ] **Step 2: Run, confirm FAIL**

```bash
.venv/Scripts/python.exe -m pytest tests/test_ffmpeg.py -v
```

Expected: `ModuleNotFoundError`.

- [ ] **Step 3: Create `engine/ffmpeg.py`**

```python
"""ffmpeg / ffprobe binary discovery and subprocess wrappers.

The Electron main process downloads ffmpeg.exe and ffprobe.exe to a per-user
directory and passes the path to the engine via the BWC_CLIPPER_FFMPEG_DIR
environment variable. If that variable is not set (e.g., when running tests
or when the user has system ffmpeg installed), fall back to searching PATH.
"""

from __future__ import annotations

import os
import shutil
from pathlib import Path

FFMPEG_BINARY = "ffmpeg.exe" if os.name == "nt" else "ffmpeg"
FFPROBE_BINARY = "ffprobe.exe" if os.name == "nt" else "ffprobe"


def _find_binary(name: str) -> Path:
    bundled_dir = os.environ.get("BWC_CLIPPER_FFMPEG_DIR")
    if bundled_dir:
        candidate = Path(bundled_dir) / name
        if candidate.is_file():
            return candidate
    on_path = shutil.which(name)
    if on_path:
        return Path(on_path)
    raise FileNotFoundError(
        f"{name} not found — checked BWC_CLIPPER_FFMPEG_DIR={bundled_dir!r} and system PATH"
    )


def find_ffmpeg() -> Path:
    return _find_binary(FFMPEG_BINARY)


def find_ffprobe() -> Path:
    return _find_binary(FFPROBE_BINARY)
```

- [ ] **Step 4: Run, confirm 4 passed**

```bash
.venv/Scripts/python.exe -m pytest tests/test_ffmpeg.py -v
```

- [ ] **Step 5: Commit**

```bash
git add engine/ffmpeg.py tests/test_ffmpeg.py
git commit -m "engine: add find_ffmpeg / find_ffprobe with env var override"
```

---

### Task 6: `engine/ffmpeg.py` — `run_ffmpeg`, `run_ffprobe` subprocess wrappers (TDD)

**Files:**
- Modify: `tests/test_ffmpeg.py` (append)
- Modify: `engine/ffmpeg.py` (append)

These wrappers run ffmpeg/ffprobe with given arguments, capture output, raise on non-zero exit.

- [ ] **Step 1: Append tests**

```python
from unittest.mock import patch, MagicMock

from engine.ffmpeg import run_ffmpeg, run_ffprobe


def test_run_ffmpeg_invokes_subprocess_with_resolved_binary(tmp_path: Path, monkeypatch):
    fake = tmp_path / ("ffmpeg.exe" if os.name == "nt" else "ffmpeg")
    fake.write_bytes(b"")
    monkeypatch.setenv("BWC_CLIPPER_FFMPEG_DIR", str(tmp_path))
    fake_completed = MagicMock(returncode=0, stdout="", stderr="")
    with patch("engine.ffmpeg.subprocess.run", return_value=fake_completed) as run_mock:
        run_ffmpeg(["-i", "in.mp4", "out.wav"])
    args, kwargs = run_mock.call_args
    cmd = args[0]
    assert Path(cmd[0]) == fake
    assert cmd[1:] == ["-i", "in.mp4", "out.wav"]
    assert kwargs["check"] is True
    assert kwargs["capture_output"] is True
    assert kwargs["text"] is True


def test_run_ffmpeg_raises_with_stderr_on_failure(tmp_path: Path, monkeypatch):
    import subprocess

    fake = tmp_path / ("ffmpeg.exe" if os.name == "nt" else "ffmpeg")
    fake.write_bytes(b"")
    monkeypatch.setenv("BWC_CLIPPER_FFMPEG_DIR", str(tmp_path))
    err = subprocess.CalledProcessError(1, ["ffmpeg"], stderr="boom: invalid input")
    with patch("engine.ffmpeg.subprocess.run", side_effect=err):
        with pytest.raises(RuntimeError) as exc_info:
            run_ffmpeg(["-i", "missing.mp4", "out.wav"])
    assert "boom: invalid input" in str(exc_info.value)


def test_run_ffprobe_returns_stdout(tmp_path: Path, monkeypatch):
    fake = tmp_path / ("ffprobe.exe" if os.name == "nt" else "ffprobe")
    fake.write_bytes(b"")
    monkeypatch.setenv("BWC_CLIPPER_FFMPEG_DIR", str(tmp_path))
    fake_completed = MagicMock(returncode=0, stdout='{"streams":[]}', stderr="")
    with patch("engine.ffmpeg.subprocess.run", return_value=fake_completed):
        out = run_ffprobe(["-show_streams", "input.mp4"])
    assert out == '{"streams":[]}'
```

- [ ] **Step 2: Run, confirm new tests FAIL**

```bash
.venv/Scripts/python.exe -m pytest tests/test_ffmpeg.py -v -k "run_ffmpeg or run_ffprobe"
```

- [ ] **Step 3: Append to `engine/ffmpeg.py`**

```python
import subprocess


def run_ffmpeg(args: list[str], *, timeout: float | None = None) -> str:
    """Run ffmpeg with the given arguments. Returns captured stdout.

    Raises:
        RuntimeError: ffmpeg exited non-zero. The exception message includes
            the captured stderr.
    """
    binary = find_ffmpeg()
    try:
        result = subprocess.run(
            [str(binary), *args],
            check=True,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        return result.stdout
    except subprocess.CalledProcessError as exc:
        raise RuntimeError(f"ffmpeg failed (exit {exc.returncode}): {exc.stderr}") from exc


def run_ffprobe(args: list[str], *, timeout: float | None = None) -> str:
    """Run ffprobe with the given arguments. Returns captured stdout."""
    binary = find_ffprobe()
    try:
        result = subprocess.run(
            [str(binary), *args],
            check=True,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        return result.stdout
    except subprocess.CalledProcessError as exc:
        raise RuntimeError(f"ffprobe failed (exit {exc.returncode}): {exc.stderr}") from exc
```

- [ ] **Step 4: Run, confirm 7 passed (4 existing + 3 new)**

```bash
.venv/Scripts/python.exe -m pytest tests/test_ffmpeg.py -v
```

- [ ] **Step 5: Commit**

```bash
git add engine/ffmpeg.py tests/test_ffmpeg.py
git commit -m "engine: add run_ffmpeg and run_ffprobe subprocess wrappers"
```

---

### Task 7: `engine/ffmpeg.py` — `probe_audio_tracks` (TDD)

**Files:**
- Modify: `tests/test_ffmpeg.py` (append)
- Modify: `engine/ffmpeg.py` (append)

`probe_audio_tracks(path)` returns a list of dicts, one per audio stream: index, codec_name, sample_rate, channels, duration. Backed by ffprobe `-show_streams -select_streams a -of json`.

- [ ] **Step 1: Append tests**

```python
import json as _json

from engine.ffmpeg import probe_audio_tracks


def test_probe_audio_tracks_parses_stream_list(tmp_path: Path, monkeypatch):
    fake = tmp_path / ("ffprobe.exe" if os.name == "nt" else "ffprobe")
    fake.write_bytes(b"")
    monkeypatch.setenv("BWC_CLIPPER_FFMPEG_DIR", str(tmp_path))

    ffprobe_output = _json.dumps({
        "streams": [
            {
                "index": 1,
                "codec_type": "audio",
                "codec_name": "aac",
                "sample_rate": "48000",
                "channels": 2,
                "duration": "120.5",
            },
            {
                "index": 2,
                "codec_type": "audio",
                "codec_name": "aac",
                "sample_rate": "48000",
                "channels": 1,
                "duration": "120.5",
            },
        ]
    })
    fake_completed = MagicMock(returncode=0, stdout=ffprobe_output, stderr="")
    with patch("engine.ffmpeg.subprocess.run", return_value=fake_completed):
        tracks = probe_audio_tracks(Path("input.mp4"))
    assert len(tracks) == 2
    assert tracks[0] == {
        "index": 1, "codec_name": "aac",
        "sample_rate": 48000, "channels": 2, "duration_seconds": 120.5,
    }
    assert tracks[1]["channels"] == 1


def test_probe_audio_tracks_returns_empty_for_no_audio(tmp_path: Path, monkeypatch):
    fake = tmp_path / ("ffprobe.exe" if os.name == "nt" else "ffprobe")
    fake.write_bytes(b"")
    monkeypatch.setenv("BWC_CLIPPER_FFMPEG_DIR", str(tmp_path))
    fake_completed = MagicMock(returncode=0, stdout='{"streams":[]}', stderr="")
    with patch("engine.ffmpeg.subprocess.run", return_value=fake_completed):
        tracks = probe_audio_tracks(Path("video-only.mp4"))
    assert tracks == []


def test_probe_audio_tracks_handles_missing_optional_fields(tmp_path: Path, monkeypatch):
    """Some sources omit duration in stream metadata; treat as None."""
    fake = tmp_path / ("ffprobe.exe" if os.name == "nt" else "ffprobe")
    fake.write_bytes(b"")
    monkeypatch.setenv("BWC_CLIPPER_FFMPEG_DIR", str(tmp_path))
    fake_completed = MagicMock(
        returncode=0,
        stdout=_json.dumps({"streams": [{
            "index": 0, "codec_type": "audio", "codec_name": "pcm_s16le",
            "sample_rate": "16000", "channels": 1,
        }]}),
        stderr="",
    )
    with patch("engine.ffmpeg.subprocess.run", return_value=fake_completed):
        tracks = probe_audio_tracks(Path("clean.wav"))
    assert tracks[0]["duration_seconds"] is None
```

- [ ] **Step 2: Run, confirm new tests FAIL**

```bash
.venv/Scripts/python.exe -m pytest tests/test_ffmpeg.py -v -k probe_audio
```

- [ ] **Step 3: Append to `engine/ffmpeg.py`**

```python
import json


def probe_audio_tracks(path: Path) -> list[dict]:
    """Run ffprobe to enumerate audio tracks in ``path``.

    Returns a list of dicts (one per audio stream) with keys:
    index, codec_name, sample_rate, channels, duration_seconds.
    Returns [] if the file has no audio streams.
    """
    output = run_ffprobe([
        "-v", "error",
        "-show_streams",
        "-select_streams", "a",
        "-of", "json",
        str(path),
    ])
    data = json.loads(output)
    tracks = []
    for stream in data.get("streams", []):
        if stream.get("codec_type") != "audio":
            continue
        duration_str = stream.get("duration")
        tracks.append({
            "index": int(stream["index"]),
            "codec_name": stream.get("codec_name", ""),
            "sample_rate": int(stream.get("sample_rate", 0)),
            "channels": int(stream.get("channels", 0)),
            "duration_seconds": float(duration_str) if duration_str else None,
        })
    return tracks
```

- [ ] **Step 4: Run, confirm 10 passed**

```bash
.venv/Scripts/python.exe -m pytest tests/test_ffmpeg.py -v
```

- [ ] **Step 5: Commit**

```bash
git add engine/ffmpeg.py tests/test_ffmpeg.py
git commit -m "engine: add probe_audio_tracks for ffprobe stream enumeration"
```

---

### Task 8: `engine/source.py` — per-source cache helpers + SHA-256 (TDD)

**Files:**
- Create: `tests/test_source.py`
- Create: `engine/source.py`

A "source" is one media file inside a project folder. Per-source cache lives at `<folder>/.bwcclipper/<source-stem>/`. Functions: `source_cache_dir(folder, source_path)` → ensures the dir exists and returns it; `compute_source_sha256(path)` → returns hex digest, cached in `source_cache_dir/source.sha256`.

- [ ] **Step 1: Write the failing test**

`tests/test_source.py`:

```python
"""Tests for engine.source per-source cache helpers."""
import hashlib
from pathlib import Path

import pytest


def _touch(p: Path, content: bytes = b""):
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_bytes(content)


def test_source_cache_dir_creates_per_source_subdir(tmp_path: Path):
    from engine.source import source_cache_dir

    project = tmp_path
    source = project / "officer-garcia.mp4"
    _touch(source)

    cache = source_cache_dir(project, source)
    assert cache == project / ".bwcclipper" / "officer-garcia"
    assert cache.is_dir()


def test_source_cache_dir_idempotent(tmp_path: Path):
    from engine.source import source_cache_dir

    source = tmp_path / "x.mp4"
    _touch(source)
    a = source_cache_dir(tmp_path, source)
    b = source_cache_dir(tmp_path, source)
    assert a == b


def test_source_cache_dir_uses_basename_stem(tmp_path: Path):
    """Cache subdir is keyed by basename without extension."""
    from engine.source import source_cache_dir

    source = tmp_path / "subdir" / "doctor.MP3"
    _touch(source)
    cache = source_cache_dir(tmp_path, source)
    assert cache.name == "doctor"


def test_compute_source_sha256_returns_hex(tmp_path: Path):
    from engine.source import compute_source_sha256, source_cache_dir

    source = tmp_path / "x.mp4"
    _touch(source, b"hello world")
    cache = source_cache_dir(tmp_path, source)

    digest = compute_source_sha256(source, cache)
    expected = hashlib.sha256(b"hello world").hexdigest()
    assert digest == expected


def test_compute_source_sha256_caches_to_disk(tmp_path: Path):
    from engine.source import compute_source_sha256, source_cache_dir

    source = tmp_path / "x.mp4"
    _touch(source, b"abc")
    cache = source_cache_dir(tmp_path, source)
    digest = compute_source_sha256(source, cache)
    cached_file = cache / "source.sha256"
    assert cached_file.is_file()
    assert cached_file.read_text(encoding="utf-8").strip() == digest


def test_compute_source_sha256_uses_cache_if_present(tmp_path: Path):
    """If the cached hash matches the file's content, the cached value is returned
    without re-hashing. Trick: write the wrong digest and confirm it's returned."""
    from engine.source import compute_source_sha256, source_cache_dir

    source = tmp_path / "x.mp4"
    _touch(source, b"real-content")
    cache = source_cache_dir(tmp_path, source)
    # Inject a wrong-but-valid-looking cached digest
    (cache / "source.sha256").write_text("a" * 64, encoding="utf-8")

    # First call: returns cached "wrong" value because we don't verify
    # contents — caller is responsible for invalidating cache when source
    # changes (handled at a higher level, e.g., by file mtime check at the
    # project layer in a future milestone).
    assert compute_source_sha256(source, cache) == "a" * 64
```

- [ ] **Step 2: Run, confirm FAIL**

```bash
.venv/Scripts/python.exe -m pytest tests/test_source.py -v
```

- [ ] **Step 3: Create `engine/source.py`**

```python
"""Per-source cache helpers for BWC Clipper.

A "source" is one media file inside the project folder. Each source gets a
cache subdirectory at ``<project>/.bwcclipper/<source-stem>/`` for transcripts,
extracted audio, waveforms, and other derived artifacts.
"""

from __future__ import annotations

import hashlib
from pathlib import Path

from engine.project import ensure_cache_dir


def source_cache_dir(project_folder: Path, source_path: Path) -> Path:
    """Ensure the per-source cache subdirectory exists; return its path.

    Cache subdir name is the source file's basename stem (no extension).
    Two sources with the same stem (e.g., ``video.mp4`` and ``video.MP3``)
    would collide; we don't guard against that today — the project's media
    file enumeration in M1 doesn't surface that case for any real folder
    we've seen, and stems are stable across runs.
    """
    project_cache = ensure_cache_dir(project_folder)
    sub = project_cache / source_path.stem
    sub.mkdir(exist_ok=True)
    return sub


def compute_source_sha256(source_path: Path, cache_dir: Path) -> str:
    """Compute (or read cached) SHA-256 hex digest of ``source_path``.

    The digest is cached as plain text in ``<cache_dir>/source.sha256``. If
    that file exists, it's returned verbatim — the caller is responsible for
    deciding when the cache is stale (e.g., on source-file mtime change).
    """
    cache_file = cache_dir / "source.sha256"
    if cache_file.is_file():
        return cache_file.read_text(encoding="utf-8").strip()

    h = hashlib.sha256()
    with source_path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    digest = h.hexdigest()
    cache_file.write_text(digest, encoding="utf-8")
    return digest
```

- [ ] **Step 4: Run, confirm 6 passed**

```bash
.venv/Scripts/python.exe -m pytest tests/test_source.py -v
```

- [ ] **Step 5: Commit**

```bash
git add engine/source.py tests/test_source.py
git commit -m "engine: add per-source cache helpers and SHA-256 caching"
```

---

### Task 9: `engine/pipeline/state.py` — read/write `pipeline-state.json` (TDD)

**Files:**
- Create: `engine/pipeline/__init__.py` (empty)
- Create: `tests/test_pipeline_state.py`
- Create: `engine/pipeline/state.py`

- [ ] **Step 1: Create empty `engine/pipeline/__init__.py`**

```python
"""BWC Clipper pipeline package — per-stage transcription orchestration."""
```

- [ ] **Step 2: Write the failing test**

`tests/test_pipeline_state.py`:

```python
"""Tests for engine.pipeline.state — pipeline-state.json read/write."""
from datetime import datetime, timezone
from pathlib import Path

from engine.pipeline.state import (
    PipelineState,
    StageStatus,
    load_state,
    save_state,
    update_stage,
)


def test_pipeline_state_default(tmp_path: Path):
    state = PipelineState.empty()
    assert state.stages == {}


def test_save_then_load_roundtrip(tmp_path: Path):
    state = PipelineState.empty()
    state = update_stage(
        state,
        "extract",
        status=StageStatus.RUNNING,
        started_at=datetime(2026, 4, 29, 12, 0, tzinfo=timezone.utc),
    )
    save_state(tmp_path, state)
    loaded = load_state(tmp_path)
    assert loaded.stages["extract"]["status"] == "running"
    assert loaded.stages["extract"]["started_at"] == "2026-04-29T12:00:00+00:00"


def test_load_state_returns_empty_when_file_missing(tmp_path: Path):
    state = load_state(tmp_path)
    assert state.stages == {}


def test_update_stage_overwrites_keys(tmp_path: Path):
    state = PipelineState.empty()
    state = update_stage(state, "extract", status=StageStatus.RUNNING)
    state = update_stage(
        state,
        "extract",
        status=StageStatus.COMPLETED,
        outputs=["a.wav", "b.wav"],
    )
    assert state.stages["extract"]["status"] == "completed"
    assert state.stages["extract"]["outputs"] == ["a.wav", "b.wav"]


def test_stage_status_values():
    assert StageStatus.QUEUED.value == "queued"
    assert StageStatus.RUNNING.value == "running"
    assert StageStatus.COMPLETED.value == "completed"
    assert StageStatus.FAILED.value == "failed"
```

- [ ] **Step 3: Run, confirm FAIL**

```bash
.venv/Scripts/python.exe -m pytest tests/test_pipeline_state.py -v
```

- [ ] **Step 4: Create `engine/pipeline/state.py`**

```python
"""Pipeline state persistence (pipeline-state.json).

One file per source cache subdirectory. Tracks per-stage status and
arbitrary per-stage metadata (timestamps, output paths, error message).
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any

SCHEMA_VERSION = "1.0"
STATE_FILENAME = "pipeline-state.json"


class StageStatus(str, Enum):
    QUEUED = "queued"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


@dataclass
class PipelineState:
    schema_version: str = SCHEMA_VERSION
    stages: dict[str, dict] = field(default_factory=dict)

    @classmethod
    def empty(cls) -> "PipelineState":
        return cls()


def load_state(cache_dir: Path) -> PipelineState:
    file = cache_dir / STATE_FILENAME
    if not file.is_file():
        return PipelineState.empty()
    raw = json.loads(file.read_text(encoding="utf-8"))
    return PipelineState(
        schema_version=raw.get("schema_version", SCHEMA_VERSION),
        stages=raw.get("stages", {}),
    )


def save_state(cache_dir: Path, state: PipelineState) -> None:
    cache_dir.mkdir(parents=True, exist_ok=True)
    file = cache_dir / STATE_FILENAME
    file.write_text(
        json.dumps(
            {"schema_version": state.schema_version, "stages": state.stages},
            indent=2,
            default=_serialize,
        ),
        encoding="utf-8",
    )


def update_stage(
    state: PipelineState,
    name: str,
    *,
    status: StageStatus | None = None,
    started_at: datetime | None = None,
    completed_at: datetime | None = None,
    outputs: list[str] | None = None,
    error: str | None = None,
) -> PipelineState:
    existing = state.stages.get(name, {})
    merged = dict(existing)
    if status is not None:
        merged["status"] = status.value
    if started_at is not None:
        merged["started_at"] = started_at.isoformat()
    if completed_at is not None:
        merged["completed_at"] = completed_at.isoformat()
    if outputs is not None:
        merged["outputs"] = list(outputs)
    if error is not None:
        merged["error"] = error
    new_stages = dict(state.stages)
    new_stages[name] = merged
    return PipelineState(schema_version=state.schema_version, stages=new_stages)


def _serialize(obj: Any):
    if isinstance(obj, datetime):
        return obj.isoformat()
    raise TypeError(f"unserializable: {type(obj)}")
```

- [ ] **Step 5: Run, confirm 5 passed**

```bash
.venv/Scripts/python.exe -m pytest tests/test_pipeline_state.py -v
```

- [ ] **Step 6: Commit**

```bash
git add engine/pipeline/__init__.py engine/pipeline/state.py tests/test_pipeline_state.py
git commit -m "engine: add pipeline state persistence with stage status tracking"
```

---

### Task 10: `engine/pipeline/extract.py` — Stage 1 implementation (TDD)

**Files:**
- Create: `tests/test_pipeline_extract.py`
- Create: `engine/pipeline/extract.py`

The Extract stage: probe audio tracks, then extract each to a 16 kHz mono PCM s16le WAV at `<cache_dir>/extracted/track{N}.wav`. Updates pipeline-state.json with output paths.

- [ ] **Step 1: Write the failing test**

`tests/test_pipeline_extract.py`:

```python
"""Tests for engine.pipeline.extract."""
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

from engine.pipeline.extract import run_extract_stage
from engine.pipeline.state import StageStatus, load_state


def _touch(p: Path, content: bytes = b""):
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_bytes(content)


def test_run_extract_stage_creates_extracted_subdir_and_wav_files(tmp_path: Path):
    project = tmp_path
    source = project / "officer.mp4"
    _touch(source, b"some-bytes")
    cache_dir = project / ".bwcclipper" / "officer"
    cache_dir.mkdir(parents=True)

    # Mock the ffmpeg/ffprobe wrappers — we're testing orchestration.
    with patch("engine.pipeline.extract.probe_audio_tracks") as probe_mock, \
         patch("engine.pipeline.extract.run_ffmpeg") as ffmpeg_mock:
        probe_mock.return_value = [
            {"index": 1, "codec_name": "aac", "sample_rate": 48000, "channels": 2, "duration_seconds": 12.0},
            {"index": 2, "codec_name": "aac", "sample_rate": 48000, "channels": 1, "duration_seconds": 12.0},
        ]
        ffmpeg_mock.return_value = ""  # ffmpeg succeeds
        outputs = run_extract_stage(source, cache_dir)

    # Two outputs, one per track
    assert len(outputs) == 2
    expected_track0 = cache_dir / "extracted" / "track0.wav"
    expected_track1 = cache_dir / "extracted" / "track1.wav"
    assert outputs[0] == expected_track0
    assert outputs[1] == expected_track1

    # extracted/ directory is created
    assert (cache_dir / "extracted").is_dir()

    # ffmpeg was called twice with the expected -map and resampling args
    assert ffmpeg_mock.call_count == 2
    # First call: track 0 (stream index 1 from probe)
    call0_args = ffmpeg_mock.call_args_list[0][0][0]
    assert "-map" in call0_args
    assert "0:1" in call0_args  # stream index 1
    assert "-ac" in call0_args and "1" in call0_args  # mono
    assert "-ar" in call0_args and "16000" in call0_args  # 16 kHz
    assert "-c:a" in call0_args and "pcm_s16le" in call0_args
    assert str(expected_track0) in call0_args


def test_run_extract_stage_writes_pipeline_state(tmp_path: Path):
    source = tmp_path / "officer.mp4"
    _touch(source, b"x")
    cache_dir = tmp_path / ".bwcclipper" / "officer"
    cache_dir.mkdir(parents=True)

    with patch("engine.pipeline.extract.probe_audio_tracks") as probe_mock, \
         patch("engine.pipeline.extract.run_ffmpeg") as _ffmpeg_mock:
        probe_mock.return_value = [
            {"index": 0, "codec_name": "aac", "sample_rate": 48000, "channels": 1, "duration_seconds": 5.0},
        ]
        run_extract_stage(source, cache_dir)

    state = load_state(cache_dir)
    extract = state.stages["extract"]
    assert extract["status"] == "completed"
    assert "started_at" in extract and "completed_at" in extract
    assert len(extract["outputs"]) == 1


def test_run_extract_stage_writes_source_metadata(tmp_path: Path):
    """source.json captures the ffprobe track list for later milestones to consume."""
    import json as _json

    source = tmp_path / "officer.mp4"
    _touch(source, b"x")
    cache_dir = tmp_path / ".bwcclipper" / "officer"
    cache_dir.mkdir(parents=True)

    with patch("engine.pipeline.extract.probe_audio_tracks") as probe_mock, \
         patch("engine.pipeline.extract.run_ffmpeg", return_value=""):
        probe_mock.return_value = [
            {"index": 1, "codec_name": "aac", "sample_rate": 48000, "channels": 2, "duration_seconds": 12.0},
        ]
        run_extract_stage(source, cache_dir)

    metadata_file = cache_dir / "source.json"
    assert metadata_file.is_file()
    metadata = _json.loads(metadata_file.read_text(encoding="utf-8"))
    assert metadata["audio_tracks"][0]["index"] == 1
    assert metadata["audio_tracks"][0]["channels"] == 2


def test_run_extract_stage_marks_failed_on_ffmpeg_error(tmp_path: Path):
    source = tmp_path / "officer.mp4"
    _touch(source, b"x")
    cache_dir = tmp_path / ".bwcclipper" / "officer"
    cache_dir.mkdir(parents=True)

    with patch("engine.pipeline.extract.probe_audio_tracks") as probe_mock, \
         patch("engine.pipeline.extract.run_ffmpeg", side_effect=RuntimeError("boom")):
        probe_mock.return_value = [{"index": 0, "codec_name": "aac", "sample_rate": 48000, "channels": 1, "duration_seconds": 5.0}]
        with pytest.raises(RuntimeError, match="boom"):
            run_extract_stage(source, cache_dir)

    state = load_state(cache_dir)
    extract = state.stages["extract"]
    assert extract["status"] == "failed"
    assert "boom" in extract.get("error", "")


def test_run_extract_stage_raises_for_no_audio_tracks(tmp_path: Path):
    source = tmp_path / "officer.mp4"
    _touch(source, b"x")
    cache_dir = tmp_path / ".bwcclipper" / "officer"
    cache_dir.mkdir(parents=True)

    with patch("engine.pipeline.extract.probe_audio_tracks", return_value=[]):
        with pytest.raises(ValueError, match="no audio"):
            run_extract_stage(source, cache_dir)
```

- [ ] **Step 2: Run, confirm FAIL**

```bash
.venv/Scripts/python.exe -m pytest tests/test_pipeline_extract.py -v
```

- [ ] **Step 3: Create `engine/pipeline/extract.py`**

```python
"""Stage 1: audio extraction.

Probes the source media for audio tracks, then runs ffmpeg once per track
to produce a 16 kHz mono PCM WAV at ``<cache_dir>/extracted/track{N}.wav``.
Writes per-stage status to pipeline-state.json.
"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from engine.ffmpeg import probe_audio_tracks, run_ffmpeg
from engine.pipeline.state import (
    StageStatus,
    load_state,
    save_state,
    update_stage,
)

STAGE_NAME = "extract"


def run_extract_stage(source_path: Path, cache_dir: Path) -> list[Path]:
    """Run audio extraction on ``source_path``, writing outputs into
    ``cache_dir/extracted/``. Returns the list of output WAV paths.

    Updates pipeline-state.json with running/completed/failed status.

    Raises:
        ValueError: source has no audio tracks.
        RuntimeError: ffmpeg subprocess failed.
    """
    state = load_state(cache_dir)
    state = update_stage(
        state,
        STAGE_NAME,
        status=StageStatus.RUNNING,
        started_at=datetime.now(timezone.utc),
    )
    save_state(cache_dir, state)

    try:
        tracks = probe_audio_tracks(source_path)
        if not tracks:
            raise ValueError(f"no audio tracks found in {source_path}")

        # Persist ffprobe output as source.json so later milestones can consume
        # it without re-probing.
        import json as _json
        (cache_dir / "source.json").write_text(
            _json.dumps({"audio_tracks": tracks}, indent=2),
            encoding="utf-8",
        )

        out_dir = cache_dir / "extracted"
        out_dir.mkdir(parents=True, exist_ok=True)
        outputs: list[Path] = []

        for n, track in enumerate(tracks):
            out = out_dir / f"track{n}.wav"
            run_ffmpeg([
                "-y",
                "-i", str(source_path),
                "-map", f"0:{track['index']}",
                "-ac", "1",
                "-ar", "16000",
                "-c:a", "pcm_s16le",
                str(out),
            ])
            outputs.append(out)

        state = load_state(cache_dir)
        state = update_stage(
            state,
            STAGE_NAME,
            status=StageStatus.COMPLETED,
            completed_at=datetime.now(timezone.utc),
            outputs=[str(p) for p in outputs],
        )
        save_state(cache_dir, state)
        return outputs

    except Exception as exc:
        state = load_state(cache_dir)
        state = update_stage(
            state,
            STAGE_NAME,
            status=StageStatus.FAILED,
            completed_at=datetime.now(timezone.utc),
            error=str(exc),
        )
        save_state(cache_dir, state)
        raise
```

- [ ] **Step 4: Run, confirm 4 passed**

```bash
.venv/Scripts/python.exe -m pytest tests/test_pipeline_extract.py -v
```

- [ ] **Step 5: Commit**

```bash
git add engine/pipeline/extract.py tests/test_pipeline_extract.py
git commit -m "engine: add Stage 1 extract — per-track 16 kHz mono WAV via ffmpeg"
```

---

### Task 11: `engine/pipeline/runner.py` — single-worker job runner (TDD)

**Files:**
- Create: `tests/test_pipeline_runner.py`
- Create: `engine/pipeline/runner.py`

A `PipelineRunner` holds a `ThreadPoolExecutor(max_workers=1)`. `submit_extract(project_folder, source_path)` queues an extract job and returns immediately; the work runs on the worker thread. `get_status(project_folder, source_path)` reads the pipeline-state.json and combines it with the in-memory job registry to return one of: `idle`, `queued`, `running`, `completed`, `failed`. Idempotent: submitting an already-completed source returns `completed` immediately without re-running.

- [ ] **Step 1: Write the failing test**

`tests/test_pipeline_runner.py`:

```python
"""Tests for engine.pipeline.runner — single-worker job dispatch."""
import time
from pathlib import Path
from unittest.mock import patch

import pytest


def _touch(p: Path, content: bytes = b""):
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_bytes(content)


def test_runner_get_status_idle_for_unprocessed_source(tmp_path: Path):
    from engine.pipeline.runner import PipelineRunner

    source = tmp_path / "x.mp4"
    _touch(source, b"x")

    runner = PipelineRunner()
    try:
        status = runner.get_status(tmp_path, source)
        assert status == "idle"
    finally:
        runner.shutdown()


def test_runner_submit_extract_runs_then_marks_completed(tmp_path: Path):
    from engine.pipeline.runner import PipelineRunner

    source = tmp_path / "x.mp4"
    _touch(source, b"x")

    runner = PipelineRunner()
    try:
        with patch("engine.pipeline.extract.probe_audio_tracks") as probe_mock, \
             patch("engine.pipeline.extract.run_ffmpeg", return_value=""):
            probe_mock.return_value = [
                {"index": 0, "codec_name": "aac", "sample_rate": 48000, "channels": 1, "duration_seconds": 1.0},
            ]
            future = runner.submit_extract(tmp_path, source)
            future.result(timeout=5)
        status = runner.get_status(tmp_path, source)
        assert status == "completed"
    finally:
        runner.shutdown()


def test_runner_get_status_failed_after_extract_error(tmp_path: Path):
    from engine.pipeline.runner import PipelineRunner

    source = tmp_path / "x.mp4"
    _touch(source, b"x")

    runner = PipelineRunner()
    try:
        with patch("engine.pipeline.extract.probe_audio_tracks") as probe_mock, \
             patch("engine.pipeline.extract.run_ffmpeg", side_effect=RuntimeError("boom")):
            probe_mock.return_value = [{"index": 0, "codec_name": "aac", "sample_rate": 48000, "channels": 1, "duration_seconds": 1.0}]
            future = runner.submit_extract(tmp_path, source)
            with pytest.raises(RuntimeError):
                future.result(timeout=5)
        assert runner.get_status(tmp_path, source) == "failed"
    finally:
        runner.shutdown()


def test_runner_submit_idempotent_when_already_completed(tmp_path: Path):
    """Submitting a source whose pipeline-state.json shows extract=completed
    returns a completed Future immediately without re-running ffmpeg."""
    from engine.pipeline.runner import PipelineRunner

    source = tmp_path / "x.mp4"
    _touch(source, b"x")

    runner = PipelineRunner()
    try:
        with patch("engine.pipeline.extract.probe_audio_tracks") as probe_mock, \
             patch("engine.pipeline.extract.run_ffmpeg", return_value="") as ffmpeg_mock:
            probe_mock.return_value = [
                {"index": 0, "codec_name": "aac", "sample_rate": 48000, "channels": 1, "duration_seconds": 1.0},
            ]
            runner.submit_extract(tmp_path, source).result(timeout=5)
            initial_call_count = ffmpeg_mock.call_count
            # Second submit should not invoke ffmpeg again.
            runner.submit_extract(tmp_path, source).result(timeout=5)
            assert ffmpeg_mock.call_count == initial_call_count
    finally:
        runner.shutdown()
```

- [ ] **Step 2: Run, confirm FAIL**

```bash
.venv/Scripts/python.exe -m pytest tests/test_pipeline_runner.py -v
```

- [ ] **Step 3: Create `engine/pipeline/runner.py`**

```python
"""Single-worker pipeline job runner.

Holds a ``concurrent.futures.ThreadPoolExecutor(max_workers=1)`` and an
in-memory registry of in-flight jobs keyed by source path. Submissions
return a Future immediately; the worker runs jobs serially.

For Milestone 2 the only stage is ``extract``. Later milestones add a
``submit_full_pipeline`` that chains extract → normalize → enhance → ...
"""

from __future__ import annotations

import threading
from concurrent.futures import Future, ThreadPoolExecutor
from pathlib import Path

from engine.pipeline.extract import run_extract_stage
from engine.pipeline.state import StageStatus, load_state
from engine.source import source_cache_dir


class PipelineRunner:
    def __init__(self):
        self._executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="bwc-pipeline")
        self._jobs: dict[str, Future] = {}
        self._lock = threading.Lock()

    def submit_extract(self, project_folder: Path, source_path: Path) -> Future:
        """Queue an extract job. If the source already has extract=completed,
        return a pre-resolved Future without queueing.
        """
        cache_dir = source_cache_dir(project_folder, source_path)
        state = load_state(cache_dir)
        if state.stages.get("extract", {}).get("status") == StageStatus.COMPLETED.value:
            f: Future = Future()
            f.set_result(None)
            return f

        key = str(source_path)
        with self._lock:
            existing = self._jobs.get(key)
            if existing and not existing.done():
                return existing
            future = self._executor.submit(run_extract_stage, source_path, cache_dir)
            self._jobs[key] = future
            return future

    def get_status(self, project_folder: Path, source_path: Path) -> str:
        """Return one of: idle, queued, running, completed, failed.

        Combines the persisted pipeline-state.json with the in-memory job
        registry so transient "queued" state is visible before the worker
        picks up the job.
        """
        cache_dir = source_cache_dir(project_folder, source_path)
        state = load_state(cache_dir)
        extract = state.stages.get("extract", {})
        persisted = extract.get("status")
        if persisted in (StageStatus.COMPLETED.value, StageStatus.FAILED.value):
            return persisted

        key = str(source_path)
        with self._lock:
            job = self._jobs.get(key)
        if job is None:
            return "idle"
        if job.done():
            # Race: the job finished but state.json hasn't been re-read yet.
            # Re-read.
            state = load_state(cache_dir)
            extract = state.stages.get("extract", {})
            return extract.get("status", "idle")
        if job.running():
            return "running"
        return "queued"

    def shutdown(self):
        self._executor.shutdown(wait=False, cancel_futures=True)
```

- [ ] **Step 4: Run, confirm 4 passed**

```bash
.venv/Scripts/python.exe -m pytest tests/test_pipeline_runner.py -v
```

- [ ] **Step 5: Commit**

```bash
git add engine/pipeline/runner.py tests/test_pipeline_runner.py
git commit -m "engine: add single-worker pipeline runner with idempotent submit"
```

---

### Task 12: `engine/server.py` — `/api/source/process` and `/api/source/state` endpoints (TDD)

**Files:**
- Create: `tests/test_server_source.py`
- Modify: `engine/server.py`

`POST /api/source/process` — body: `{folder: "...", source: "..."}` — submits an extract job, returns `{status: "queued"|"running"|"completed"|...}`.

`GET /api/source/state?folder=...&source=...` — returns the same shape.

The handler holds a single shared `PipelineRunner` instance.

- [ ] **Step 1: Write the failing test**

`tests/test_server_source.py`:

```python
"""Tests for /api/source/process and /api/source/state."""
import threading
from http.server import HTTPServer
from pathlib import Path
from unittest.mock import patch

import pytest
import requests

from engine.server import BWCRequestHandler, reset_pipeline_runner


@pytest.fixture(autouse=True)
def _isolate_pipeline_runner():
    """Reset the module-level pipeline runner before each test so that
    in-flight jobs and the executor's thread don't leak across tests."""
    reset_pipeline_runner()
    yield
    reset_pipeline_runner()


@pytest.fixture
def running_server():
    server = HTTPServer(("127.0.0.1", 0), BWCRequestHandler)
    port = server.server_address[1]
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield port
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)


def _touch(p: Path, content: bytes = b""):
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_bytes(content)


def test_process_endpoint_submits_extract_and_returns_status(running_server, tmp_path: Path):
    source = tmp_path / "officer.mp4"
    _touch(source, b"x")

    with patch("engine.pipeline.extract.probe_audio_tracks") as probe_mock, \
         patch("engine.pipeline.extract.run_ffmpeg", return_value=""):
        probe_mock.return_value = [{"index": 0, "codec_name": "aac", "sample_rate": 48000, "channels": 1, "duration_seconds": 1.0}]
        response = requests.post(
            f"http://127.0.0.1:{running_server}/api/source/process",
            json={"folder": str(tmp_path), "source": str(source)},
            timeout=5,
        )
    assert response.status_code == 200
    body = response.json()
    assert body["status"] in ("queued", "running", "completed")


def test_state_endpoint_idle_for_unprocessed_source(running_server, tmp_path: Path):
    source = tmp_path / "officer.mp4"
    _touch(source, b"x")

    response = requests.get(
        f"http://127.0.0.1:{running_server}/api/source/state",
        params={"folder": str(tmp_path), "source": str(source)},
        timeout=5,
    )
    assert response.status_code == 200
    assert response.json() == {"status": "idle"}


def test_state_endpoint_completed_after_extract(running_server, tmp_path: Path):
    source = tmp_path / "officer.mp4"
    _touch(source, b"x")

    with patch("engine.pipeline.extract.probe_audio_tracks") as probe_mock, \
         patch("engine.pipeline.extract.run_ffmpeg", return_value=""):
        probe_mock.return_value = [{"index": 0, "codec_name": "aac", "sample_rate": 48000, "channels": 1, "duration_seconds": 1.0}]
        # Submit and wait for completion
        requests.post(
            f"http://127.0.0.1:{running_server}/api/source/process",
            json={"folder": str(tmp_path), "source": str(source)},
            timeout=5,
        )
        # Poll until completed (max 5s)
        import time
        deadline = time.time() + 5
        status = None
        while time.time() < deadline:
            r = requests.get(
                f"http://127.0.0.1:{running_server}/api/source/state",
                params={"folder": str(tmp_path), "source": str(source)},
                timeout=5,
            )
            status = r.json()["status"]
            if status == "completed":
                break
            time.sleep(0.05)
        assert status == "completed"


def test_process_endpoint_400_for_missing_fields(running_server):
    response = requests.post(
        f"http://127.0.0.1:{running_server}/api/source/process",
        json={"folder": "/some/path"},  # missing 'source'
        timeout=5,
    )
    assert response.status_code == 400


def test_state_endpoint_400_for_missing_query_params(running_server):
    response = requests.get(
        f"http://127.0.0.1:{running_server}/api/source/state",
        timeout=5,
    )
    assert response.status_code == 400
```

- [ ] **Step 2: Run, confirm FAIL**

```bash
.venv/Scripts/python.exe -m pytest tests/test_server_source.py -v
```

- [ ] **Step 3: Modify `engine/server.py` to add the new endpoints**

Replace the imports block at the top of `engine/server.py`:

Find:

```python
import json
import logging
from http.server import BaseHTTPRequestHandler
from pathlib import Path
from typing import Callable

from engine.project import open_project
from engine.version import get_version
```

Replace with:

```python
import json
import logging
from http.server import BaseHTTPRequestHandler
from pathlib import Path
from typing import Callable
from urllib.parse import parse_qs, urlsplit

from engine.pipeline.runner import PipelineRunner
from engine.project import open_project
from engine.version import get_version
```

Add a module-level singleton accessor near the top of the file (just above the `class BWCRequestHandler` definition):

```python
# Module-level singleton runner shared across all request handler instances
# (BaseHTTPRequestHandler is instantiated per request, so we cannot store the
# runner on `self`). Tests reset this between cases via reset_pipeline_runner().
_RUNNER: PipelineRunner | None = None


def get_pipeline_runner() -> PipelineRunner:
    global _RUNNER
    if _RUNNER is None:
        _RUNNER = PipelineRunner()
    return _RUNNER


def reset_pipeline_runner() -> None:
    """Test-only hook: discards any in-flight jobs and resets the runner."""
    global _RUNNER
    if _RUNNER is not None:
        _RUNNER.shutdown()
    _RUNNER = None
```

Then find the existing `_post_routes`:

```python
    def _post_routes(self) -> dict[str, Callable[[dict], tuple[int, dict]]]:
        return {
            "/api/project/open": self._handle_project_open,
        }
```

Replace with:

```python
    def _post_routes(self) -> dict[str, Callable[[dict], tuple[int, dict]]]:
        return {
            "/api/project/open": self._handle_project_open,
            "/api/source/process": self._handle_source_process,
        }
```

Find `do_GET`:

```python
    def do_GET(self):
        handler = self._get_routes().get(self.path)
        if handler is None:
            self._send_json(404, {"error": "not found", "path": self.path})
            return
        try:
            status, body = handler()
            self._send_json(status, body)
        except Exception as exc:  # pragma: no cover - defensive
            logger.exception("GET handler crashed for %s", self.path)
            self._send_json(500, {"error": "internal", "detail": str(exc)})
```

Replace with (adds query-aware routing for /api/source/state):

```python
    def do_GET(self):
        split = urlsplit(self.path)
        # Static GET routes (no query params consulted)
        handler = self._get_routes().get(split.path)
        if handler is not None:
            try:
                status, body = handler()
                self._send_json(status, body)
            except Exception as exc:  # pragma: no cover
                logger.exception("GET handler crashed for %s", self.path)
                self._send_json(500, {"error": "internal", "detail": str(exc)})
            return

        # Query-driven routes
        if split.path == "/api/source/state":
            try:
                status, body = self._handle_source_state(parse_qs(split.query))
                self._send_json(status, body)
            except Exception as exc:  # pragma: no cover
                logger.exception("/api/source/state crashed")
                self._send_json(500, {"error": "internal", "detail": str(exc)})
            return

        self._send_json(404, {"error": "not found", "path": split.path})
```

At the bottom of the class, before `_send_json`, add the two new handlers:

```python
    def _handle_source_process(self, body: dict) -> tuple[int, dict]:
        folder = body.get("folder")
        source = body.get("source")
        if not isinstance(folder, str) or not folder:
            return 400, {"error": "missing 'folder' field"}
        if not isinstance(source, str) or not source:
            return 400, {"error": "missing 'source' field"}
        runner = get_pipeline_runner()
        runner.submit_extract(Path(folder), Path(source))
        status = runner.get_status(Path(folder), Path(source))
        return 200, {"status": status}

    def _handle_source_state(self, query: dict) -> tuple[int, dict]:
        folder_list = query.get("folder", [])
        source_list = query.get("source", [])
        if not folder_list or not source_list:
            return 400, {"error": "missing 'folder' or 'source' query parameter"}
        status = get_pipeline_runner().get_status(
            Path(folder_list[0]), Path(source_list[0])
        )
        return 200, {"status": status}
```

- [ ] **Step 4: Run new tests, confirm 5 passed**

```bash
.venv/Scripts/python.exe -m pytest tests/test_server_source.py -v
```

- [ ] **Step 5: Run full pytest suite**

```bash
.venv/Scripts/python.exe -m pytest -v
```

Expected: all tests pass (cumulative count grows by ~30 from this milestone).

- [ ] **Step 6: Commit**

```bash
git add engine/server.py tests/test_server_source.py
git commit -m "engine: add /api/source/process and /api/source/state endpoints"
```

---

### Task 13: `editor/components/FileListItem.jsx` — render stage status indicator (TDD)

**Files:**
- Modify: `editor/components/FileListItem.test.jsx` (append)
- Modify: `editor/components/FileListItem.jsx`

Add a small status indicator to the right of the file size. Statuses: `idle` (no badge), `queued` (gray dot + "queued"), `running` (animated dot + "extracting…"), `completed` (green check), `failed` (red x + "failed").

- [ ] **Step 1: Append tests**

Append to `editor/components/FileListItem.test.jsx`:

```jsx
describe('FileListItem status indicator', () => {
    it('renders no status indicator when status is undefined', () => {
        const { container } = render(
            <FileListItem file={sampleFile} selected={false} onSelect={() => {}} />,
        );
        expect(container.querySelector('[data-status]')).toBeNull();
    });

    it('renders running status', () => {
        render(
            <FileListItem
                file={sampleFile}
                selected={false}
                onSelect={() => {}}
                status="running"
            />,
        );
        expect(screen.getByText(/extracting/i)).toBeDefined();
    });

    it('renders queued status', () => {
        render(
            <FileListItem
                file={sampleFile}
                selected={false}
                onSelect={() => {}}
                status="queued"
            />,
        );
        expect(screen.getByText(/queued/i)).toBeDefined();
    });

    it('renders completed status with checkmark', () => {
        const { container } = render(
            <FileListItem
                file={sampleFile}
                selected={false}
                onSelect={() => {}}
                status="completed"
            />,
        );
        const indicator = container.querySelector('[data-status="completed"]');
        expect(indicator).not.toBeNull();
    });

    it('renders failed status', () => {
        render(
            <FileListItem
                file={sampleFile}
                selected={false}
                onSelect={() => {}}
                status="failed"
            />,
        );
        expect(screen.getByText(/failed/i)).toBeDefined();
    });
});
```

- [ ] **Step 2: Run, confirm new tests FAIL**

```bash
npx vitest run editor/components/FileListItem.test.jsx
```

- [ ] **Step 3: Replace `editor/components/FileListItem.jsx`** (add status prop and rendering)

```jsx
import React from 'react';

const MODE_LABELS = { bwc: 'BWC', dme: 'DME' };
const MODE_COLORS = {
    bwc: { bg: '#0e3a4a', fg: '#5eead4' },
    dme: { bg: '#3a2d0e', fg: '#fbbf24' },
};

const STATUS_LABELS = {
    queued: 'queued',
    running: 'extracting…',
    completed: '',
    failed: 'failed',
};

const STATUS_COLORS = {
    queued: '#6e7681',
    running: '#fbbf24',
    completed: '#22c55e',
    failed: '#f87171',
};

function formatSize(bytes) {
    if (bytes < 1024) return `${bytes} B`;
    if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
    if (bytes < 1024 * 1024 * 1024) return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
    return `${(bytes / (1024 * 1024 * 1024)).toFixed(2)} GB`;
}

function StatusIndicator({ status }) {
    if (!status) return null;
    const color = STATUS_COLORS[status] ?? '#6e7681';
    const label = STATUS_LABELS[status] ?? status;
    const glyph = status === 'completed' ? '✓' : status === 'failed' ? '✗' : '●';
    return (
        <span
            data-status={status}
            style={{
                display: 'inline-flex',
                alignItems: 'center',
                gap: 4,
                color,
                fontSize: '0.75rem',
                marginLeft: '0.75rem',
                minWidth: 80,
                justifyContent: 'flex-end',
            }}
        >
            <span aria-hidden="true">{glyph}</span>
            {label && <span>{label}</span>}
        </span>
    );
}

export default function FileListItem({ file, selected, onSelect, status }) {
    const modeStyle = MODE_COLORS[file.mode] || { bg: '#21262d', fg: '#8b949e' };
    return (
        <div
            role="option"
            aria-selected={selected ? 'true' : 'false'}
            onClick={() => onSelect(file)}
            style={{
                display: 'flex',
                alignItems: 'center',
                padding: '0.5rem 0.75rem',
                borderRadius: 4,
                cursor: 'pointer',
                background: selected ? '#1c2733' : 'transparent',
                borderLeft: selected ? '3px solid #5eead4' : '3px solid transparent',
                marginBottom: 2,
            }}
        >
            <span
                style={{
                    background: modeStyle.bg,
                    color: modeStyle.fg,
                    fontSize: '0.7rem',
                    fontWeight: 600,
                    padding: '2px 6px',
                    borderRadius: 3,
                    marginRight: '0.75rem',
                    minWidth: 36,
                    textAlign: 'center',
                }}
            >
                {MODE_LABELS[file.mode] ?? file.mode}
            </span>
            <span style={{ flex: 1, color: '#c9d1d9', fontFamily: 'system-ui, sans-serif' }}>
                {file.basename}
            </span>
            <span style={{ color: '#6e7681', fontSize: '0.85rem' }}>
                {formatSize(file.size_bytes)}
            </span>
            <StatusIndicator status={status} />
        </div>
    );
}
```

- [ ] **Step 4: Run, confirm all 11 FileListItem tests pass (6 existing + 5 new)**

```bash
npx vitest run editor/components/FileListItem.test.jsx
```

- [ ] **Step 5: Commit**

```bash
git add editor/components/FileListItem.jsx editor/components/FileListItem.test.jsx
git commit -m "editor: add status indicator to FileListItem"
```

---

### Task 14: `editor/components/ProjectView.jsx` — pass per-source status through (TDD)

**Files:**
- Modify: `editor/components/ProjectView.test.jsx` (append)
- Modify: `editor/components/ProjectView.jsx`

`ProjectView` accepts a new prop `statuses` — a `{ [path]: status }` map — and passes the right status to each `FileListItem`.

- [ ] **Step 1: Append tests**

```jsx
describe('ProjectView status propagation', () => {
    it('passes statuses to file rows by path', () => {
        const statuses = {
            'C:/case-folder/a.mp4': 'running',
            'C:/case-folder/b.MP3': 'completed',
        };
        const { container } = render(
            <ProjectView
                manifest={sampleManifest}
                selectedPath={null}
                onSelectFile={() => {}}
                onCloseProject={() => {}}
                statuses={statuses}
            />,
        );
        expect(container.querySelector('[data-status="running"]')).not.toBeNull();
        expect(container.querySelector('[data-status="completed"]')).not.toBeNull();
    });

    it('does not require statuses prop', () => {
        // Backwards-compatible: missing statuses doesn't break rendering.
        render(
            <ProjectView
                manifest={sampleManifest}
                selectedPath={null}
                onSelectFile={() => {}}
                onCloseProject={() => {}}
            />,
        );
        expect(screen.getByText('a.mp4')).toBeDefined();
    });
});
```

- [ ] **Step 2: Run, confirm new tests FAIL (or pass trivially if statuses is undefined safe)**

```bash
npx vitest run editor/components/ProjectView.test.jsx
```

- [ ] **Step 3: Modify `editor/components/ProjectView.jsx`**

Find the `FileListItem` invocation:

```jsx
<FileListItem
    key={file.path}
    file={file}
    selected={file.path === selectedPath}
    onSelect={onSelectFile}
/>
```

Replace with:

```jsx
<FileListItem
    key={file.path}
    file={file}
    selected={file.path === selectedPath}
    onSelect={onSelectFile}
    status={statuses?.[file.path]}
/>
```

Update the function signature:

```jsx
export default function ProjectView({ manifest, selectedPath, onSelectFile, onCloseProject, statuses }) {
```

- [ ] **Step 4: Run, confirm 8 ProjectView tests pass (6 existing + 2 new)**

```bash
npx vitest run editor/components/ProjectView.test.jsx
```

- [ ] **Step 5: Commit**

```bash
git add editor/components/ProjectView.jsx editor/components/ProjectView.test.jsx
git commit -m "editor: thread per-source statuses through ProjectView to FileListItem"
```

---

### Task 15: `editor/EditorApp.jsx` — kick off processing on select + poll state (TDD)

**Files:**
- Modify: `editor/EditorApp.test.jsx` (rewrite the existing tests, add polling tests)
- Modify: `editor/EditorApp.jsx`

When the user selects a file, EditorApp:
1. Sets the selected path.
2. Calls `POST /api/source/process` to kick off extraction.
3. Starts a polling loop that GETs `/api/source/state` every 1000 ms for any source whose status is `queued` or `running`.
4. Updates the `statuses` state object passed to `ProjectView`.

- [ ] **Step 1: Replace `editor/EditorApp.test.jsx`**

```jsx
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { render, screen, fireEvent, waitFor, act } from '@testing-library/react';
import EditorApp from './EditorApp.jsx';
import { _resetCachedBaseForTests } from './api.js';

const SAMPLE_MANIFEST = {
    folder: 'C:/case-folder',
    files: [
        { basename: 'officer.mp4', path: 'C:/case-folder/officer.mp4', extension: 'mp4', mode: 'bwc', size_bytes: 1024 },
    ],
};

function setupFetchStub({ initialStatus = 'idle', sequence = [] } = {}) {
    let stateCalls = 0;
    return vi.fn((url, opts) => {
        if (url.endsWith('/api/project/open')) {
            return Promise.resolve({ ok: true, json: () => Promise.resolve(SAMPLE_MANIFEST) });
        }
        if (url.endsWith('/api/source/process')) {
            return Promise.resolve({ ok: true, json: () => Promise.resolve({ status: 'queued' }) });
        }
        if (url.includes('/api/source/state')) {
            const next = sequence[stateCalls] ?? sequence[sequence.length - 1] ?? initialStatus;
            stateCalls += 1;
            return Promise.resolve({ ok: true, json: () => Promise.resolve({ status: next }) });
        }
        return Promise.reject(new Error('unexpected url: ' + url));
    });
}

describe('EditorApp', () => {
    beforeEach(() => {
        _resetCachedBaseForTests();
        vi.useFakeTimers();
        global.window.electronAPI = {
            getEngineUrl: () => Promise.resolve('http://127.0.0.1:8888'),
            pickFolder: vi.fn(() => Promise.resolve('C:/case-folder')),
        };
    });

    afterEach(() => {
        vi.useRealTimers();
        delete global.window.electronAPI;
        global.fetch = undefined;
    });

    it('renders the empty state on mount', () => {
        global.fetch = setupFetchStub();
        render(<EditorApp />);
        expect(screen.getByRole('button', { name: /open folder/i })).toBeDefined();
    });

    it('opens a folder, renders project view', async () => {
        global.fetch = setupFetchStub();
        render(<EditorApp />);
        fireEvent.click(screen.getByRole('button', { name: /open folder/i }));
        await waitFor(() => expect(screen.getByText('officer.mp4')).toBeDefined());
    });

    it('kicks off processing on file select', async () => {
        global.fetch = setupFetchStub({ sequence: ['queued', 'running', 'completed'] });
        render(<EditorApp />);
        fireEvent.click(screen.getByRole('button', { name: /open folder/i }));
        await waitFor(() => expect(screen.getByText('officer.mp4')).toBeDefined());

        fireEvent.click(screen.getByText('officer.mp4'));

        await waitFor(() => {
            expect(global.fetch).toHaveBeenCalledWith(
                'http://127.0.0.1:8888/api/source/process',
                expect.objectContaining({
                    method: 'POST',
                    body: JSON.stringify({ folder: 'C:/case-folder', source: 'C:/case-folder/officer.mp4' }),
                }),
            );
        });
    });

    it('polls source state and updates UI to completed', async () => {
        global.fetch = setupFetchStub({ sequence: ['running', 'running', 'completed'] });
        render(<EditorApp />);
        fireEvent.click(screen.getByRole('button', { name: /open folder/i }));
        await waitFor(() => expect(screen.getByText('officer.mp4')).toBeDefined());
        fireEvent.click(screen.getByText('officer.mp4'));

        // First poll → running
        await act(async () => {
            await vi.advanceTimersByTimeAsync(1000);
        });
        // Second poll → completed
        await act(async () => {
            await vi.advanceTimersByTimeAsync(1000);
        });
        await act(async () => {
            await vi.advanceTimersByTimeAsync(1000);
        });

        await waitFor(() => {
            const row = document.querySelector('[data-status="completed"]');
            expect(row).not.toBeNull();
        });
    });
});
```

- [ ] **Step 2: Run, confirm new tests FAIL**

```bash
npx vitest run editor/EditorApp.test.jsx
```

- [ ] **Step 3: Replace `editor/EditorApp.jsx`**

```jsx
import React, { useEffect, useRef, useState } from 'react';
import { apiPost, apiGet } from './api.js';
import EmptyState from './components/EmptyState.jsx';
import ProjectView from './components/ProjectView.jsx';

const POLL_INTERVAL_MS = 1000;
const ACTIVE_STATUSES = new Set(['queued', 'running']);

export default function EditorApp() {
    const [manifest, setManifest] = useState(null);
    const [selectedPath, setSelectedPath] = useState(null);
    const [statuses, setStatuses] = useState({});
    const [error, setError] = useState(null);
    const pollHandle = useRef(null);

    async function openFolder() {
        setError(null);
        const folderPath = await window.electronAPI.pickFolder();
        if (!folderPath) return;
        try {
            const result = await apiPost('/api/project/open', { path: folderPath });
            setManifest(result);
            setSelectedPath(null);
            setStatuses({});
        } catch (err) {
            setError(err.message);
        }
    }

    function closeProject() {
        setManifest(null);
        setSelectedPath(null);
        setStatuses({});
        setError(null);
        stopPolling();
    }

    async function selectFile(file) {
        setSelectedPath(file.path);
        setStatuses((s) => ({ ...s, [file.path]: 'queued' }));
        try {
            const resp = await apiPost('/api/source/process', {
                folder: manifest.folder,
                source: file.path,
            });
            setStatuses((s) => ({ ...s, [file.path]: resp.status }));
            if (ACTIVE_STATUSES.has(resp.status)) {
                startPolling(file.path);
            }
        } catch (err) {
            setStatuses((s) => ({ ...s, [file.path]: 'failed' }));
            setError(err.message);
        }
    }

    function startPolling(path) {
        stopPolling();
        pollHandle.current = setInterval(async () => {
            try {
                const params = new URLSearchParams({ folder: manifest.folder, source: path });
                const resp = await apiGet(`/api/source/state?${params.toString()}`);
                setStatuses((s) => ({ ...s, [path]: resp.status }));
                if (!ACTIVE_STATUSES.has(resp.status)) {
                    stopPolling();
                }
            } catch (err) {
                console.warn('[poll] state fetch failed:', err);
            }
        }, POLL_INTERVAL_MS);
    }

    function stopPolling() {
        if (pollHandle.current) {
            clearInterval(pollHandle.current);
            pollHandle.current = null;
        }
    }

    useEffect(() => () => stopPolling(), []);

    return (
        <div style={{ width: '100%', height: '100%', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
            {manifest === null ? (
                <div>
                    <EmptyState onOpenFolder={openFolder} />
                    {error && (
                        <p style={{ marginTop: '1rem', color: '#f87171', textAlign: 'center' }}>{error}</p>
                    )}
                </div>
            ) : (
                <ProjectView
                    manifest={manifest}
                    selectedPath={selectedPath}
                    onSelectFile={selectFile}
                    onCloseProject={closeProject}
                    statuses={statuses}
                />
            )}
        </div>
    );
}
```

- [ ] **Step 4: Run, confirm all editor tests pass**

```bash
npm test
```

Expected total: 4 EditorApp + 3 EmptyState + 11 FileListItem + 8 ProjectView = 26 tests.

- [ ] **Step 5: Commit**

```bash
git add editor/EditorApp.jsx editor/EditorApp.test.jsx
git commit -m "editor: trigger processing on select; poll state for live status"
```

---

### Task 16: Manual launch verification

**Files:** none (verification, no commit)

This task verifies the full end-to-end flow with a real Electron launch, real ffmpeg download, and a real BWC video.

- [ ] **Step 1: If a previous ffmpeg is cached, optionally remove to re-test the download flow**

```bash
# Optional — only if you want to re-exercise the download path:
# powershell -Command "Remove-Item -Recurse -Force '$env:LOCALAPPDATA\BWCClipper\ffmpeg' -ErrorAction SilentlyContinue"
```

- [ ] **Step 2: Build editor + run all tests one more time**

```bash
npm run build:editor
.venv/Scripts/python.exe -m pytest -v
npm test
```

- [ ] **Step 3: Launch the app**

```bash
npm start
```

Expected manual verification:
- Splash shows `Checking ffmpeg…` then either `Downloading ffmpeg from <source>… N%` (first launch) or proceeds directly to `Starting engine…` (second+ launch).
- Main window opens.
- Click "Open folder" → pick `Samples/`. File list shows the 7 sample media files.
- Click `Samples/BWC/<some>.mp4`. Status indicator on that row should flip from blank → `extracting…` (yellow dot) → `✓` (green checkmark) within ~30 seconds.
- Inspect `Samples/.bwcclipper/<source-stem>/extracted/` — there should be one or more `track{N}.wav` files. Open one in any audio player to confirm it's real audio.
- Click a different file — its status indicator goes through the same cycle.
- Already-completed files stay `✓` if you click them again (no re-processing).
- Close the app → no orphan `python.exe` or `ffmpeg.exe` processes.

- [ ] **Step 4: If anything fails, debug — do NOT commit until manual flow works**

---

### Task 17: README — update with M2 status

**Files:**
- Modify: `README.md`

- [ ] **Step 1: Edit `README.md`**

Replace:

```
> **Status:** Milestone 1 of 8 complete — folder open + file enumeration. Run `npm start` to launch; pick a folder containing `.mp4`/`.mp3` files and the app lists them with mode badges (BWC for video, DME for audio).
```

With:

```
> **Status:** Milestone 2 of 8 complete — ffmpeg integration + audio extraction. App downloads ffmpeg on first launch, extracts each media file's audio tracks to 16 kHz mono WAVs in the project's hidden cache, and shows live processing status on each file row.
```

- [ ] **Step 2: Commit**

```bash
git add README.md
git commit -m "docs: update status to M2 complete"
```

---

### Task 18: Push, merge to main, clean up

- [ ] **Step 1: Push the branch**

```bash
git push -u origin milestone-2-ffmpeg-extract
```

- [ ] **Step 2: Switch to main and merge**

```bash
git checkout main
git merge --no-ff milestone-2-ffmpeg-extract -m "$(cat <<'EOF'
Merge milestone 2: ffmpeg integration + audio extraction (Stage 1)

Bundled ffmpeg auto-download on first launch (Depo Clipper pattern,
Windows-only V1). Engine ffmpeg/ffprobe wrappers in engine/ffmpeg.py.
New engine/source.py with per-source cache helpers and SHA-256.
New engine/pipeline/ package with state persistence, single-worker
runner, and Stage 1 audio extraction producing 16 kHz mono WAVs per
audio track. New endpoints: POST /api/source/process and
GET /api/source/state. UI: FileListItem renders live status; selecting
a file kicks off processing and polls for completion.

Test coverage: 30+ new unit tests across ffmpeg, source, pipeline.state,
pipeline.extract, pipeline.runner, server endpoints; 7+ new editor
tests across FileListItem, ProjectView, and EditorApp polling. Manual
launch verified end-to-end against the user's Samples/ folder.

Out of scope (deferred to M3+): normalize, enhance, VAD, transcribe,
align, diarize, wearer-detect, output assembly. Background processing
of unviewed sources arrives in M6.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

- [ ] **Step 3: Push main and clean up**

```bash
git push origin main
git push origin --delete milestone-2-ffmpeg-extract
git branch -d milestone-2-ffmpeg-extract
```

- [ ] **Step 4: Verify final state**

```bash
git log --oneline --graph -10
```

---

## What this milestone leaves you with

- The first stage of the transcription pipeline running for real, end-to-end, on the user's Windows machine.
- ffmpeg + ffprobe correctly bundled on first launch and wired through to the engine.
- The pipeline scaffolding (state, runner, Stage protocol) that all subsequent stages will plug into.
- Per-source cache directories with real artifacts inside, hash-keyed and idempotent on re-run.
- Live UI feedback during processing — the foundation for the per-stage progress that later milestones extend.

## Next milestone (preview, not part of this plan)

**Milestone 3: Loudness normalize + speech enhance + VAD (Stages 2–4).** Three more stages chained after extract. Each stage outputs a new WAV in the cache (`normalized.wav`, `enhanced.wav`, plus `speech-segments.json` from VAD). DeepFilterNet 3 ONNX bundled (size permitting) or installer-time downloaded. Silero VAD ONNX bundled. The status indicator on FileListItem starts showing per-stage progress (`extracting → normalizing → enhancing → detecting speech → ready`).
