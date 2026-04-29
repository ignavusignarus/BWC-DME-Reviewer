# BWC Clipper — Milestone 0: Skeleton — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Produce a launchable Electron desktop app with a Python engine running locally that can talk to each other and serve a "hello, BWC Clipper" UI in a browser-style window. Establishes the project's basic file structure, build tooling (esbuild for the editor, electron-forge for packaging), test infrastructure (pytest + vitest), and the Electron-to-engine communication pattern (HTTP + IPC) that everything later in the project depends on.

**Architecture:** Three processes per launch — Electron main (Node), spawned Python engine (`serve.py` running an `http.server`-based local HTTP server on a random port and printing it to stdout), and Electron renderer (Chromium loading `index.html` with the React editor bundle). Editor talks to engine via `fetch` to `http://127.0.0.1:<port>/api/...`; native operations (folder picker, settings) flow through `contextBridge` exposed APIs into the main process. Mirrors Depo Clipper's split exactly.

**Tech Stack:** Python 3.11 (stdlib `http.server`, no Flask/FastAPI), Node 18+, Electron 41+, electron-forge, React 19, esbuild, pytest, vitest. CAOSL v1.0 license.

**Scope of this milestone:** Pure scaffolding. No folder open. No file enumeration. No transcription pipeline. No real dependency gate. Subsequent milestones layer those on. The end state of this milestone is: `npm start` opens a window that says "BWC Clipper" with the engine version it fetched live from the Python server, `pytest` passes, `npm test` passes.

**Out of scope for this milestone (deliberately deferred to later milestones):**
- Folder picker, file enumeration, project view (Milestone 1).
- Any audio/video processing or pipeline stage (Milestone 2+).
- Real dependency gate with model verification (Milestone 7).
- ffmpeg auto-download (Milestone 7).
- Installer / packaging (Milestone 8).

---

## File Structure

These are the files this milestone creates. Each has one clear responsibility; nothing here exceeds ~200 lines.

```
bwc-clipper/                                    (project root = repo)
├── pyproject.toml                              Python project metadata + deps + pytest config
├── package.json                                Node deps + npm scripts
├── forge.config.js                             electron-forge config (minimal for now)
├── .python-version                             pyenv hint (3.11)
├── README.md                                   updated with dev quickstart
├── index.html                                  HTML shell that hosts editor-bundle.js
├── serve.py                                    Engine entry point — picks a port, starts server, prints it to stdout
├── engine/
│   ├── __init__.py
│   ├── version.py                              BWC_CLIPPER_VERSION constant + get_version()
│   └── server.py                               BaseHTTPRequestHandler with /api/health and /api/version
├── electron/
│   ├── main.js                                 Spawns engine subprocess, opens splash → main window
│   ├── preload.js                              contextBridge exposing electronAPI to renderer
│   ├── splash.html                             Splash window markup
│   └── splash-preload.js                       Splash bridge (just receives status messages for now)
├── editor/
│   ├── main.jsx                                React entry (renders <EditorApp />)
│   ├── EditorApp.jsx                           Top-level component — fetches /api/version and renders title
│   ├── api.js                                  Tiny fetch wrapper around the engine URL
│   └── EditorApp.test.jsx                      vitest test for EditorApp
├── tests/
│   ├── conftest.py                             pytest fixtures (shared)
│   ├── test_version.py                         pytest for engine.version
│   ├── test_server.py                          pytest for engine.server
│   └── test_serve_smoke.py                     pytest end-to-end: start serve.py, hit /api/health, kill
├── scripts/
│   └── build-editor.js                         esbuild driver (called from npm scripts)
├── vitest.config.js                            vitest configuration
└── .gitignore                                  (already exists; add Node/Python build artifacts)
```

**Files that will exist but are touched by later milestones:**
- `vendor/` (binary bundles — Milestone 7)
- `editor/components/`, `editor/state/`, `editor/lib/` (UI components — Milestone 1+)
- `engine/pipeline/` (transcription stages — Milestone 2+)
- `engine/job_manager.py`, `engine/resource_manager.py` (Milestone 6)

---

## A note on TDD discipline

Some tasks in this milestone are "config files and project scaffolding" — TDD does not apply (you cannot write a failing test for whether `package.json` exists). Tasks that produce **code** follow strict TDD: failing test → impl → passing test → commit. Tasks that produce **config/scaffolding** follow: write file → verify with concrete command → commit. Both forms have explicit "verify" steps; neither leaves you guessing whether something worked.

For end-to-end integration (e.g., "Electron spawns engine and the renderer can fetch from it"), tests run in a separate `tests/test_serve_smoke.py` that exercises the engine directly. Manual smoke verification — actually launching `npm start` — is the final gate at the end of the milestone.

---

## Reference patterns (from Depo Clipper, mirror these)

When implementing tasks below, look at the corresponding Depo Clipper file for the exact shape:

| BWC Clipper file | Depo Clipper reference (read for pattern) |
|---|---|
| `serve.py` | `C:\Claude Code Projects\Depo Clipper\Depo-Clipper\serve.py` (just the port-pick + stdout-print pattern; ignore the rest) |
| `engine/server.py` | `serve.py` request-handler pattern |
| `electron/main.js` | `Depo-Clipper\electron\main.js` (especially the engine-spawn and splash-then-main pattern) |
| `electron/preload.js` | `Depo-Clipper\electron\preload.js` (the `contextBridge.exposeInMainWorld('electronAPI', ...)` shape) |
| `electron/splash.html` | `Depo-Clipper\electron\splash.html` |
| `package.json` scripts | `Depo-Clipper\package.json` |
| `forge.config.js` | `Depo-Clipper\forge.config.js` |
| `scripts/build-editor.js` | `Depo-Clipper\package.json` `build:editor` script (it's currently inline; we're extracting it) |

Do **not** copy code wholesale. Mirror the *shape* and *patterns*; the BWC Clipper version of each file should be smaller and focused, since this milestone is just scaffolding.

---

## Tasks

### Task 1: Create top-level directory skeleton

**Files:**
- Create: `engine/`, `electron/`, `editor/`, `tests/`, `scripts/` (empty directories)

- [ ] **Step 1: Create directories**

```bash
cd "C:/Claude Code Projects/BWC Reviewer"
mkdir -p engine electron editor tests scripts
```

- [ ] **Step 2: Verify directories exist**

```bash
ls -d engine electron editor tests scripts
```

Expected: all five paths print without error.

- [ ] **Step 3: Add .gitkeep so empty dirs survive in git**

```bash
touch engine/.gitkeep electron/.gitkeep editor/.gitkeep tests/.gitkeep scripts/.gitkeep
```

- [ ] **Step 4: Commit**

```bash
git add engine/ electron/ editor/ tests/ scripts/
git commit -m "scaffold: create top-level directory skeleton"
```

---

### Task 2: Python project metadata (`pyproject.toml`) and version pin

**Files:**
- Create: `pyproject.toml`
- Create: `.python-version`

- [ ] **Step 1: Create `.python-version`**

Contents (one line, no trailing newline ambiguity — just `3.11`):

```
3.11
```

- [ ] **Step 2: Create `pyproject.toml`**

```toml
[build-system]
requires = ["setuptools>=68", "wheel"]
build-backend = "setuptools.build_meta"

[project]
name = "bwc-clipper-engine"
version = "0.0.1"
description = "BWC Clipper Python engine — transcription pipeline, ffmpeg orchestration, clip composition."
authors = [{ name = "Andy Schrader" }]
license = { text = "Consumer Attorney Open Source License v1.0" }
requires-python = ">=3.11,<3.13"

# Milestone 0 has zero runtime deps — pipeline deps land in later milestones.
dependencies = []

[project.optional-dependencies]
dev = [
    "pytest>=7,<9",
    "pytest-timeout>=2.2",
    "ruff>=0.5",
    "requests>=2.31",  # used in tests/test_serve_smoke.py only
]

[tool.setuptools.packages.find]
include = ["engine*"]

[tool.pytest.ini_options]
minversion = "7.0"
testpaths = ["tests"]
addopts = "-v --tb=short"
timeout = 30
markers = [
    "smoke: end-to-end smoke tests that start subprocesses",
]

[tool.ruff]
line-length = 100
target-version = "py311"

[tool.ruff.lint]
select = ["E", "F", "W", "I", "B", "UP", "SIM"]
ignore = ["E501"]
```

- [ ] **Step 3: Create venv and install dev extras**

```bash
python -m venv .venv
.venv/Scripts/python.exe -m pip install --upgrade pip
.venv/Scripts/python.exe -m pip install -e ".[dev]"
```

Expected: pytest, ruff, requests installed in the venv. No errors.

- [ ] **Step 4: Verify pytest is wired**

```bash
.venv/Scripts/python.exe -m pytest --version
```

Expected: pytest version printed.

- [ ] **Step 5: Update `.gitignore` to exclude the venv**

`.gitignore` already excludes `.venv/`. Verify it's listed; no edit needed.

- [ ] **Step 6: Commit**

```bash
git add pyproject.toml .python-version
git commit -m "engine: add pyproject.toml with pytest and ruff configured"
```

---

### Task 3: Node/Electron project metadata (`package.json`)

**Files:**
- Create: `package.json`

- [ ] **Step 1: Create `package.json`**

```json
{
    "name": "bwc-clipper",
    "version": "0.0.1",
    "private": true,
    "description": "Local desktop tool for plaintiff-side review and clipping of body-worn camera video and defense medical exam audio.",
    "author": "Andy Schrader",
    "license": "SEE LICENSE IN LICENSE",
    "main": "electron/main.js",
    "scripts": {
        "start": "electron-forge start",
        "package": "electron-forge package",
        "make": "electron-forge make",
        "build:editor": "node scripts/build-editor.js",
        "watch:editor": "node scripts/build-editor.js --watch",
        "test": "vitest run",
        "test:watch": "vitest"
    },
    "config": {
        "forge": "./forge.config.js"
    },
    "devDependencies": {
        "@electron-forge/cli": "^7.11.1",
        "electron": "^41.2.0",
        "esbuild": "^0.27.3",
        "react": "^19.2.4",
        "react-dom": "^19.2.4",
        "vitest": "^4.1.0",
        "@testing-library/react": "^16.1.0",
        "jsdom": "^25.0.1"
    }
}
```

Note: react/react-dom go in **devDependencies** because esbuild bundles them into `editor-bundle.js` at build time; they're not loaded as Node modules at runtime.

- [ ] **Step 2: Install Node dependencies**

```bash
npm install
```

Expected: `node_modules/` populated; `package-lock.json` written. May take 1-2 minutes.

- [ ] **Step 3: Verify Electron is callable**

```bash
npx electron --version
```

Expected: `v41.x.y` printed.

- [ ] **Step 4: Verify vitest is callable**

```bash
npx vitest --version
```

Expected: vitest version printed.

- [ ] **Step 5: Commit (excluding node_modules)**

```bash
git add package.json package-lock.json
git commit -m "scaffold: add package.json with electron-forge, esbuild, react, vitest"
```

---

### Task 4: Engine version module (TDD)

**Files:**
- Create: `engine/__init__.py` (empty)
- Test: `tests/test_version.py`
- Create: `engine/version.py`

- [ ] **Step 1: Create empty `engine/__init__.py`**

Empty file (zero bytes). Required for Python package recognition.

- [ ] **Step 2: Write the failing test**

`tests/test_version.py`:

```python
"""Tests for engine.version."""
from engine.version import BWC_CLIPPER_VERSION, get_version


def test_version_constant_is_string():
    assert isinstance(BWC_CLIPPER_VERSION, str)
    assert len(BWC_CLIPPER_VERSION) > 0


def test_version_constant_has_year_dot_format():
    """Version is a calver-ish string starting with the year (e.g., 2026.04.29a)."""
    parts = BWC_CLIPPER_VERSION.split(".")
    assert len(parts) >= 2
    assert parts[0].isdigit()
    assert int(parts[0]) >= 2026


def test_get_version_returns_constant():
    assert get_version() == BWC_CLIPPER_VERSION
```

- [ ] **Step 3: Run test to verify it fails**

```bash
.venv/Scripts/python.exe -m pytest tests/test_version.py -v
```

Expected: FAIL with `ModuleNotFoundError: No module named 'engine.version'`.

- [ ] **Step 4: Write minimal implementation**

`engine/version.py`:

```python
"""Engine version. Bump on changes that invalidate the .bwcclipper/ cache schema."""

BWC_CLIPPER_VERSION = "2026.04.29a"


def get_version() -> str:
    return BWC_CLIPPER_VERSION
```

- [ ] **Step 5: Run test to verify it passes**

```bash
.venv/Scripts/python.exe -m pytest tests/test_version.py -v
```

Expected: 3 passed.

- [ ] **Step 6: Commit**

```bash
git add engine/__init__.py engine/version.py tests/test_version.py
git commit -m "engine: add version module with BWC_CLIPPER_VERSION constant"
```

---

### Task 5: Engine HTTP server with `/api/health` (TDD)

**Files:**
- Test: `tests/test_server.py`
- Create: `engine/server.py`

- [ ] **Step 1: Write the failing test**

`tests/test_server.py`:

```python
"""Tests for engine.server.

These tests bind to a free port, start the server, hit it, and shut down.
They use threading.Thread + requests; no subprocess.
"""
import threading
from http.server import HTTPServer

import pytest
import requests

from engine.server import BWCRequestHandler


@pytest.fixture
def running_server():
    """Start engine.server on a random local port. Yield (port, shutdown)."""
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


def test_health_endpoint_returns_200(running_server):
    port = running_server
    response = requests.get(f"http://127.0.0.1:{port}/api/health", timeout=2)
    assert response.status_code == 200


def test_health_endpoint_returns_json_with_status_ok(running_server):
    port = running_server
    response = requests.get(f"http://127.0.0.1:{port}/api/health", timeout=2)
    body = response.json()
    assert body == {"status": "ok"}


def test_unknown_path_returns_404(running_server):
    port = running_server
    response = requests.get(f"http://127.0.0.1:{port}/api/nope", timeout=2)
    assert response.status_code == 404
```

- [ ] **Step 2: Run test to verify it fails**

```bash
.venv/Scripts/python.exe -m pytest tests/test_server.py -v
```

Expected: FAIL with `ModuleNotFoundError: No module named 'engine.server'`.

- [ ] **Step 3: Write minimal implementation**

`engine/server.py`:

```python
"""BWC Clipper local HTTP server.

Stdlib http.server only — no Flask/FastAPI. The handler dispatches GET requests
to a small route table. Future milestones extend this with POST handlers and
WebSocket support; for Milestone 0 we serve only /api/health and /api/version.
"""

import json
import logging
from http.server import BaseHTTPRequestHandler

from engine.version import get_version

logger = logging.getLogger("bwc-clipper.server")


class BWCRequestHandler(BaseHTTPRequestHandler):
    """Routes GET requests to handler methods. JSON in, JSON out."""

    # Suppress default access logging — we use our own logger.
    def log_message(self, format, *args):
        logger.debug("%s - %s", self.address_string(), format % args)

    def do_GET(self):
        routes = {
            "/api/health": self._handle_health,
            "/api/version": self._handle_version,
        }
        handler = routes.get(self.path)
        if handler is None:
            self._send_json(404, {"error": "not found", "path": self.path})
            return
        try:
            handler()
        except Exception as exc:  # pragma: no cover - defensive
            logger.exception("handler crashed for %s", self.path)
            self._send_json(500, {"error": "internal", "detail": str(exc)})

    def _handle_health(self):
        self._send_json(200, {"status": "ok"})

    def _handle_version(self):
        self._send_json(200, {"version": get_version()})

    def _send_json(self, status: int, body: dict):
        payload = json.dumps(body).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(payload)))
        # Permissive CORS — only ever bound to 127.0.0.1, called from the
        # Electron renderer which loads from file:// or app://.
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(payload)
```

- [ ] **Step 4: Run test to verify it passes**

```bash
.venv/Scripts/python.exe -m pytest tests/test_server.py -v
```

Expected: 3 passed.

- [ ] **Step 5: Commit**

```bash
git add engine/server.py tests/test_server.py
git commit -m "engine: add HTTP server with /api/health endpoint"
```

---

### Task 6: Add `/api/version` test (TDD)

**Files:**
- Modify: `tests/test_server.py` (add a test)

- [ ] **Step 1: Add a failing test for `/api/version`**

Append to `tests/test_server.py`:

```python
def test_version_endpoint_returns_engine_version(running_server):
    """Confirms the /api/version handler exposes engine.version.get_version."""
    from engine.version import get_version

    port = running_server
    response = requests.get(f"http://127.0.0.1:{port}/api/version", timeout=2)
    assert response.status_code == 200
    body = response.json()
    assert body == {"version": get_version()}
```

- [ ] **Step 2: Run the test**

```bash
.venv/Scripts/python.exe -m pytest tests/test_server.py::test_version_endpoint_returns_engine_version -v
```

Expected: PASS (the route is already wired in Task 5; this is the verification that it works).

- [ ] **Step 3: Run the full server test suite**

```bash
.venv/Scripts/python.exe -m pytest tests/test_server.py -v
```

Expected: 4 passed.

- [ ] **Step 4: Commit**

```bash
git add tests/test_server.py
git commit -m "engine: add /api/version endpoint test"
```

---

### Task 7: Server entry point `serve.py` (port-to-stdout pattern)

**Files:**
- Create: `serve.py`
- Test: `tests/test_serve_smoke.py`

- [ ] **Step 1: Write the failing smoke test**

`tests/test_serve_smoke.py`:

```python
"""End-to-end smoke test: launch serve.py as a subprocess, parse the port from
its stdout, hit /api/health over HTTP, then kill the process.

This exercises the same code path Electron will use to spawn the engine.
"""
import os
import subprocess
import sys
import time
from pathlib import Path

import pytest
import requests

REPO_ROOT = Path(__file__).resolve().parent.parent
SERVE_PY = REPO_ROOT / "serve.py"


@pytest.mark.smoke
def test_serve_py_starts_and_serves_health():
    env = os.environ.copy()
    env["PYTHONUNBUFFERED"] = "1"
    proc = subprocess.Popen(
        [sys.executable, str(SERVE_PY)],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        cwd=str(REPO_ROOT),
        env=env,
        text=True,
    )
    try:
        port = None
        deadline = time.time() + 10  # seconds
        while time.time() < deadline:
            line = proc.stdout.readline()
            if not line:
                time.sleep(0.05)
                continue
            line = line.strip()
            if line.startswith("BWC_CLIPPER_PORT="):
                port = int(line.split("=", 1)[1])
                break
        assert port is not None, "serve.py did not print BWC_CLIPPER_PORT= within 10s"

        # Hit /api/health
        response = requests.get(f"http://127.0.0.1:{port}/api/health", timeout=2)
        assert response.status_code == 200
        assert response.json() == {"status": "ok"}
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=3)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait()
```

- [ ] **Step 2: Run the test to verify it fails**

```bash
.venv/Scripts/python.exe -m pytest tests/test_serve_smoke.py -v
```

Expected: FAIL — `serve.py` does not yet exist (FileNotFoundError or assertion error about port not printed).

- [ ] **Step 3: Write `serve.py`**

```python
"""BWC Clipper engine entry point.

Picks a free port on 127.0.0.1, starts the HTTP server, and prints
``BWC_CLIPPER_PORT=<port>`` to stdout so the Electron parent process can
parse it. Keeps running until killed.
"""
import logging
import socket
import sys
from http.server import HTTPServer

from engine.server import BWCRequestHandler
from engine.version import BWC_CLIPPER_VERSION


def pick_free_port() -> int:
    """Bind to port 0, get the OS-assigned port, then release it."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def main() -> int:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
        stream=sys.stderr,
    )
    logger = logging.getLogger("bwc-clipper.serve")

    port = pick_free_port()
    logger.info("starting BWC Clipper engine version %s on port %d", BWC_CLIPPER_VERSION, port)

    # Print the port on a clearly-prefixed line so the parent (Electron)
    # can robustly parse it without confusing log output.
    print(f"BWC_CLIPPER_PORT={port}", flush=True)

    server = HTTPServer(("127.0.0.1", port), BWCRequestHandler)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        logger.info("shutting down")
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 4: Run the smoke test to verify it passes**

```bash
.venv/Scripts/python.exe -m pytest tests/test_serve_smoke.py -v
```

Expected: 1 passed. Subprocess starts, prints port, responds to health check, gets terminated.

- [ ] **Step 5: Run the full pytest suite to make sure nothing else broke**

```bash
.venv/Scripts/python.exe -m pytest -v
```

Expected: 8 passed (3 version + 4 server + 1 smoke).

- [ ] **Step 6: Commit**

```bash
git add serve.py tests/test_serve_smoke.py
git commit -m "engine: add serve.py entry point with port-to-stdout protocol"
```

---

### Task 8: Pytest shared fixtures (`conftest.py`)

**Files:**
- Create: `tests/conftest.py`

- [ ] **Step 1: Write `conftest.py`**

```python
"""Shared pytest fixtures.

For Milestone 0 this is mostly empty — placeholder for the test suite to grow.
The running_server fixture lives in test_server.py because it's specific to
the server test module; if more tests need it, lift it here.
"""
import pytest


@pytest.fixture
def repo_root():
    """Absolute path to the repository root."""
    from pathlib import Path
    return Path(__file__).resolve().parent.parent
```

- [ ] **Step 2: Run pytest to confirm it still works**

```bash
.venv/Scripts/python.exe -m pytest -v
```

Expected: 8 passed (no new tests; conftest doesn't define any).

- [ ] **Step 3: Commit**

```bash
git add tests/conftest.py
git commit -m "tests: add conftest.py with repo_root fixture"
```

---

### Task 9: Editor entry — `index.html` shell

**Files:**
- Create: `index.html`

- [ ] **Step 1: Create `index.html`**

```html
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta http-equiv="Content-Security-Policy" content="default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; connect-src http://127.0.0.1:* ws://127.0.0.1:*;">
    <title>BWC Clipper</title>
    <style>
        html, body { margin: 0; padding: 0; height: 100%; background: #0d1117; color: #c9d1d9;
                     font-family: -apple-system, system-ui, sans-serif; }
        #root { height: 100%; display: flex; align-items: center; justify-content: center; }
    </style>
</head>
<body>
    <div id="root"></div>
    <script src="editor-bundle.js"></script>
</body>
</html>
```

- [ ] **Step 2: Verify it parses (HTML is forgiving — just confirm the file renders in a browser if you want, otherwise no automated check needed)**

No automated check. The `<script>` tag references `editor-bundle.js` which Task 12 produces.

- [ ] **Step 3: Commit**

```bash
git add index.html
git commit -m "editor: add index.html shell"
```

---

### Task 10: Editor — fetch wrapper (`editor/api.js`)

**Files:**
- Create: `editor/api.js`

- [ ] **Step 1: Write `editor/api.js`**

```javascript
/*
 * Tiny fetch wrapper around the engine HTTP server.
 *
 * The engine URL is injected at runtime via window.electronAPI.getEngineUrl().
 * In dev / test environments without electronAPI, defaults to a static
 * environment variable so the editor can be unit-tested in jsdom.
 */

let _cachedBase = null;

async function getBaseUrl() {
    if (_cachedBase) return _cachedBase;
    if (typeof window !== 'undefined' && window.electronAPI?.getEngineUrl) {
        _cachedBase = await window.electronAPI.getEngineUrl();
        return _cachedBase;
    }
    // Test/dev fallback — overridable for unit tests.
    _cachedBase = 'http://127.0.0.1:0';
    return _cachedBase;
}

export function _resetCachedBaseForTests() {
    _cachedBase = null;
}

export async function apiGet(path) {
    const base = await getBaseUrl();
    const response = await fetch(`${base}${path}`);
    if (!response.ok) {
        throw new Error(`API ${path} returned ${response.status}`);
    }
    return response.json();
}
```

- [ ] **Step 2: No automated test for this file alone — it gets exercised by `EditorApp.test.jsx` in Task 13**

Skip to commit.

- [ ] **Step 3: Commit**

```bash
git add editor/api.js
git commit -m "editor: add fetch wrapper around engine URL"
```

---

### Task 11: Editor — `EditorApp` component (TDD via vitest)

**Files:**
- Create: `vitest.config.js`
- Test: `editor/EditorApp.test.jsx`
- Create: `editor/EditorApp.jsx`

- [ ] **Step 1: Create `vitest.config.js`**

```javascript
import { defineConfig } from 'vitest/config';

export default defineConfig({
    test: {
        environment: 'jsdom',
        globals: true,
        include: ['editor/**/*.test.{js,jsx,ts,tsx}'],
    },
    esbuild: {
        jsx: 'automatic',
        loader: 'jsx',
    },
});
```

- [ ] **Step 2: Write the failing test**

`editor/EditorApp.test.jsx`:

```jsx
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import EditorApp from './EditorApp.jsx';
import { _resetCachedBaseForTests } from './api.js';

describe('EditorApp', () => {
    beforeEach(() => {
        _resetCachedBaseForTests();
        // Stub electronAPI before each test
        global.window.electronAPI = {
            getEngineUrl: () => Promise.resolve('http://127.0.0.1:8888'),
        };
        // Stub fetch
        global.fetch = vi.fn((url) => {
            if (url === 'http://127.0.0.1:8888/api/version') {
                return Promise.resolve({
                    ok: true,
                    json: () => Promise.resolve({ version: '2026.04.29a' }),
                });
            }
            return Promise.reject(new Error('unexpected url: ' + url));
        });
    });

    afterEach(() => {
        delete global.window.electronAPI;
        global.fetch = undefined;
    });

    it('renders the app title', () => {
        render(<EditorApp />);
        expect(screen.getByText('BWC Clipper')).toBeDefined();
    });

    it('fetches and displays the engine version', async () => {
        render(<EditorApp />);
        await waitFor(() => {
            expect(screen.getByText(/2026\.04\.29a/)).toBeDefined();
        });
    });
});
```

- [ ] **Step 3: Run the test to verify it fails**

```bash
npx vitest run editor/EditorApp.test.jsx
```

Expected: FAIL — `EditorApp.jsx` does not exist yet.

- [ ] **Step 4: Write `EditorApp.jsx`**

```jsx
import React, { useEffect, useState } from 'react';
import { apiGet } from './api.js';

export default function EditorApp() {
    const [version, setVersion] = useState(null);
    const [error, setError] = useState(null);

    useEffect(() => {
        let cancelled = false;
        apiGet('/api/version')
            .then((data) => {
                if (!cancelled) setVersion(data.version);
            })
            .catch((err) => {
                if (!cancelled) setError(err.message);
            });
        return () => { cancelled = true; };
    }, []);

    return (
        <div style={{ textAlign: 'center' }}>
            <h1 style={{ fontSize: '2.5rem', margin: 0, color: '#5eead4' }}>BWC Clipper</h1>
            <p style={{ marginTop: '0.5rem', color: '#8b949e' }}>
                {error
                    ? `engine error: ${error}`
                    : version
                    ? `engine v${version}`
                    : 'connecting to engine…'}
            </p>
        </div>
    );
}
```

- [ ] **Step 5: Run the test to verify it passes**

```bash
npx vitest run editor/EditorApp.test.jsx
```

Expected: 2 passed.

- [ ] **Step 6: Commit**

```bash
git add vitest.config.js editor/EditorApp.jsx editor/EditorApp.test.jsx
git commit -m "editor: add EditorApp with engine version fetch"
```

---

### Task 12: Editor — `main.jsx` mount point

**Files:**
- Create: `editor/main.jsx`

- [ ] **Step 1: Write `editor/main.jsx`**

```jsx
import React from 'react';
import { createRoot } from 'react-dom/client';
import EditorApp from './EditorApp.jsx';

const container = document.getElementById('root');
if (!container) {
    throw new Error('#root element missing from index.html');
}
createRoot(container).render(<EditorApp />);
```

- [ ] **Step 2: No automated test for the mount point — it's exercised by the manual smoke run at the end of the milestone.**

Skip to commit.

- [ ] **Step 3: Commit**

```bash
git add editor/main.jsx
git commit -m "editor: add main.jsx mount point"
```

---

### Task 13: esbuild build script

**Files:**
- Create: `scripts/build-editor.js`

- [ ] **Step 1: Write `scripts/build-editor.js`**

```javascript
/*
 * esbuild driver for the React editor bundle.
 *
 * Usage:
 *   node scripts/build-editor.js          # one-shot build
 *   node scripts/build-editor.js --watch  # rebuild on change
 *
 * Produces: editor-bundle.js at the repo root, referenced by index.html.
 */

const path = require('path');
const esbuild = require('esbuild');

const watch = process.argv.includes('--watch');
const isProduction = process.env.NODE_ENV === 'production';

const buildOptions = {
    entryPoints: [path.join(__dirname, '..', 'editor', 'main.jsx')],
    bundle: true,
    outfile: path.join(__dirname, '..', 'editor-bundle.js'),
    jsx: 'automatic',
    loader: { '.jsx': 'jsx' },
    define: {
        'process.env.NODE_ENV': JSON.stringify(isProduction ? 'production' : 'development'),
    },
    sourcemap: !isProduction,
    minify: isProduction,
    logLevel: 'info',
};

async function main() {
    if (watch) {
        const ctx = await esbuild.context(buildOptions);
        await ctx.watch();
        console.log('[build-editor] watching for changes…');
    } else {
        await esbuild.build(buildOptions);
        console.log('[build-editor] built editor-bundle.js');
    }
}

main().catch((err) => {
    console.error('[build-editor] failed:', err);
    process.exit(1);
});
```

- [ ] **Step 2: Run a one-shot build to verify it produces `editor-bundle.js`**

```bash
npm run build:editor
```

Expected: `[build-editor] built editor-bundle.js` printed; `editor-bundle.js` exists at repo root and is non-empty.

- [ ] **Step 3: Verify the bundle**

```bash
ls -la editor-bundle.js
```

Expected: non-zero size (typically >100 KB after React bundling).

- [ ] **Step 4: Add `editor-bundle.js` to `.gitignore`**

It's already in `.gitignore` from the initial commit — verify with grep:

```bash
grep editor-bundle .gitignore
```

Expected: `editor-bundle.js` line printed.

- [ ] **Step 5: Commit the build script**

```bash
git add scripts/build-editor.js
git commit -m "build: add esbuild driver for editor bundle"
```

---

### Task 14: Electron preload — `contextBridge` shape

**Files:**
- Create: `electron/preload.js`

- [ ] **Step 1: Write `electron/preload.js`**

```javascript
/*
 * Renderer-side bridge to the main process.
 *
 * Exposes window.electronAPI with only the operations the renderer needs.
 * Milestone 0 surface area: getEngineUrl, getAppVersion. Future milestones
 * add folder picker, settings, dependency status, etc.
 */
const { contextBridge, ipcRenderer } = require('electron');

contextBridge.exposeInMainWorld('electronAPI', {
    getEngineUrl: () => ipcRenderer.invoke('get-engine-url'),
    getAppVersion: () => ipcRenderer.invoke('get-app-version'),
});
```

- [ ] **Step 2: No automated test (Electron preload is exercised at runtime). Commit.**

```bash
git add electron/preload.js
git commit -m "electron: add preload with electronAPI bridge"
```

---

### Task 15: Splash window

**Files:**
- Create: `electron/splash.html`
- Create: `electron/splash-preload.js`

- [ ] **Step 1: Write `electron/splash.html`**

```html
<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <title>BWC Clipper</title>
    <style>
        html, body { margin: 0; padding: 0; height: 100%; background: #0d1117; color: #c9d1d9;
                     font-family: -apple-system, system-ui, sans-serif;
                     display: flex; align-items: center; justify-content: center;
                     -webkit-user-select: none; }
        .splash { text-align: center; }
        h1 { font-size: 2rem; margin: 0; color: #5eead4; }
        .status { margin-top: 1rem; color: #8b949e; font-size: 0.9rem; }
    </style>
</head>
<body>
    <div class="splash">
        <h1>BWC Clipper</h1>
        <p class="status" id="status">Starting engine…</p>
    </div>
    <script src="splash-preload.js"></script>
</body>
</html>
```

Note: in Electron, splash-preload.js is loaded as a *preload script*, not via `<script src>`. The `<script>` tag here is harmless — Electron's BrowserWindow with a preload set ignores it. We include it only because if you ever load splash.html in a regular browser (e.g., for design iteration), the preload's status-update function should be reachable. Done either way, the splash works.

- [ ] **Step 2: Write `electron/splash-preload.js`**

```javascript
/*
 * Splash window preload. Listens for status messages from the main process
 * and updates the visible "Starting engine…" line.
 */
const { ipcRenderer } = require('electron');

ipcRenderer.on('splash-status', (_event, message) => {
    const el = document.getElementById('status');
    if (el) el.textContent = message;
});
```

- [ ] **Step 3: Commit**

```bash
git add electron/splash.html electron/splash-preload.js
git commit -m "electron: add splash window with status preload"
```

---

### Task 16: Electron main process — open window only (no engine yet)

**Files:**
- Create: `electron/main.js` (initial, smaller version — engine spawn arrives in Task 17)

This task creates a minimal `main.js` that just opens a window and loads `index.html`. Task 17 wires the engine subprocess in. Splitting the work this way keeps each step verifiable.

- [ ] **Step 1: Write `electron/main.js` (initial version)**

```javascript
/*
 * BWC Clipper Electron main process.
 *
 * Milestone 0 responsibilities:
 *   - Open splash window on startup.
 *   - Spawn the Python engine subprocess (added in Task 17).
 *   - When the engine signals "ready," dismiss splash and open main window
 *     pointing at index.html (added in Task 17).
 *   - Handle 'get-engine-url' and 'get-app-version' IPC requests.
 *
 * For Task 16, only the main-window-open logic is here; engine spawn arrives
 * next. We open the main window directly so we can verify the renderer loads
 * the editor bundle before adding subprocess complexity.
 */
const { app, BrowserWindow, ipcMain } = require('electron');
const path = require('path');

let mainWindow = null;

// Placeholder until Task 17 — main window will fetch this URL via electronAPI.
let _engineUrl = 'http://127.0.0.1:0';

function createMainWindow() {
    mainWindow = new BrowserWindow({
        width: 1280,
        height: 800,
        webPreferences: {
            preload: path.join(__dirname, 'preload.js'),
            contextIsolation: true,
            nodeIntegration: false,
            sandbox: true,
        },
    });
    mainWindow.loadFile(path.join(__dirname, '..', 'index.html'));
    mainWindow.on('closed', () => { mainWindow = null; });
}

ipcMain.handle('get-engine-url', () => _engineUrl);
ipcMain.handle('get-app-version', () => app.getVersion());

app.whenReady().then(() => {
    createMainWindow();
    app.on('activate', () => {
        if (BrowserWindow.getAllWindows().length === 0) createMainWindow();
    });
});

app.on('window-all-closed', () => {
    if (process.platform !== 'darwin') app.quit();
});
```

- [ ] **Step 2: Build the editor bundle so `index.html` has something to load**

```bash
npm run build:editor
```

Expected: `editor-bundle.js` (re)built.

- [ ] **Step 3: Add a minimal `forge.config.js` so `npm start` works**

`forge.config.js`:

```javascript
module.exports = {
    packagerConfig: {
        name: 'BWC Clipper',
        executableName: 'bwc-clipper',
        appBundleId: 'law.panish.bwcclipper',
        asar: true,
        ignore: [
            /^\/\.venv($|\/)/,
            /^\/node_modules\/electron\/dist\//,
            /^\/tests($|\/)/,
            /^\/docs($|\/)/,
            /^\/\.bwcclipper($|\/)/,
            /^\/Samples($|\/)/,
            /^\/clips($|\/)/,
            /^\/\.git($|\/)/,
            /^\/\.gitignore$/,
        ],
    },
    rebuildConfig: {},
    makers: [
        { name: '@electron-forge/maker-zip', platforms: ['darwin', 'linux', 'win32'] },
    ],
    plugins: [],
};
```

- [ ] **Step 4: Manually launch and verify**

```bash
npm start
```

Expected:
- A window opens.
- It shows "BWC Clipper" + "engine error: API /api/version returned …" (because the engine isn't running yet — that's expected for this task).
- Closing the window shuts the app down.

This is the manual smoke check for Task 16. Engine integration follows in Task 17.

- [ ] **Step 5: Commit**

```bash
git add electron/main.js forge.config.js
git commit -m "electron: open main window loading index.html (no engine yet)"
```

---

### Task 17: Electron main process — spawn engine and bridge URL to renderer

**Files:**
- Modify: `electron/main.js` (add subprocess spawn + splash-then-main flow)

This is the largest task in this milestone — it wires Electron to the engine. It's structured so each sub-step is verifiable.

- [ ] **Step 1: Replace `electron/main.js` with the full version**

```javascript
/*
 * BWC Clipper Electron main process.
 */
const { app, BrowserWindow, ipcMain } = require('electron');
const { spawn } = require('child_process');
const path = require('path');
const fs = require('fs');

let mainWindow = null;
let splashWindow = null;
let pythonProcess = null;
let serverPort = null;
let isShuttingDown = false;

const REPO_ROOT = path.resolve(__dirname, '..');

function pythonExecutable() {
    const candidates = [
        path.join(REPO_ROOT, '.venv', 'Scripts', 'python.exe'),  // Windows venv
        path.join(REPO_ROOT, '.venv', 'bin', 'python'),          // POSIX venv
    ];
    for (const c of candidates) {
        if (fs.existsSync(c)) return c;
    }
    // Fall back to system python on PATH; will surface as a clear startup
    // failure if neither venv is present.
    return process.platform === 'win32' ? 'python.exe' : 'python3';
}

function createSplashWindow() {
    splashWindow = new BrowserWindow({
        width: 480,
        height: 320,
        frame: false,
        resizable: false,
        center: true,
        webPreferences: {
            preload: path.join(__dirname, 'splash-preload.js'),
            contextIsolation: true,
            nodeIntegration: false,
            sandbox: true,
        },
    });
    splashWindow.loadFile(path.join(__dirname, 'splash.html'));
    splashWindow.on('closed', () => { splashWindow = null; });
}

function setSplashStatus(message) {
    if (splashWindow && !splashWindow.isDestroyed()) {
        splashWindow.webContents.send('splash-status', message);
    }
}

function spawnEngine() {
    return new Promise((resolve, reject) => {
        const py = pythonExecutable();
        const servePy = path.join(REPO_ROOT, 'serve.py');
        if (!fs.existsSync(servePy)) {
            reject(new Error(`serve.py not found at ${servePy}`));
            return;
        }
        console.log(`[main] spawning engine: ${py} ${servePy}`);
        const proc = spawn(py, [servePy], {
            cwd: REPO_ROOT,
            env: { ...process.env, PYTHONUNBUFFERED: '1' },
            stdio: ['ignore', 'pipe', 'pipe'],
        });

        let portResolved = false;
        const PORT_TIMEOUT_MS = 15000;
        const timeoutHandle = setTimeout(() => {
            if (!portResolved) {
                portResolved = true;
                proc.kill();
                reject(new Error(`engine did not print BWC_CLIPPER_PORT= within ${PORT_TIMEOUT_MS}ms`));
            }
        }, PORT_TIMEOUT_MS);

        let stdoutBuffer = '';
        proc.stdout.on('data', (chunk) => {
            stdoutBuffer += chunk.toString('utf8');
            const lines = stdoutBuffer.split('\n');
            stdoutBuffer = lines.pop();  // keep partial trailing line
            for (const line of lines) {
                const trimmed = line.trim();
                if (trimmed.startsWith('BWC_CLIPPER_PORT=')) {
                    if (!portResolved) {
                        portResolved = true;
                        clearTimeout(timeoutHandle);
                        const port = parseInt(trimmed.slice('BWC_CLIPPER_PORT='.length), 10);
                        resolve({ proc, port });
                        return;
                    }
                } else if (trimmed) {
                    console.log('[engine stdout]', trimmed);
                }
            }
        });

        proc.stderr.on('data', (chunk) => {
            const text = chunk.toString('utf8');
            for (const line of text.split('\n')) {
                if (line.trim()) console.log('[engine stderr]', line.trim());
            }
        });

        proc.on('error', (err) => {
            if (!portResolved) {
                portResolved = true;
                clearTimeout(timeoutHandle);
                reject(err);
            }
        });

        proc.on('exit', (code, signal) => {
            console.log(`[main] engine exited code=${code} signal=${signal}`);
            if (!isShuttingDown) {
                if (mainWindow && !mainWindow.isDestroyed()) {
                    mainWindow.webContents.send('engine-exited', { code, signal });
                }
            }
        });
    });
}

function createMainWindow() {
    mainWindow = new BrowserWindow({
        width: 1280,
        height: 800,
        show: false,
        webPreferences: {
            preload: path.join(__dirname, 'preload.js'),
            contextIsolation: true,
            nodeIntegration: false,
            sandbox: true,
        },
    });
    mainWindow.loadFile(path.join(REPO_ROOT, 'index.html'));
    mainWindow.once('ready-to-show', () => {
        mainWindow.show();
        if (splashWindow && !splashWindow.isDestroyed()) splashWindow.close();
    });
    mainWindow.on('closed', () => { mainWindow = null; });
}

ipcMain.handle('get-engine-url', () => {
    if (!serverPort) throw new Error('engine not yet started');
    return `http://127.0.0.1:${serverPort}`;
});
ipcMain.handle('get-app-version', () => app.getVersion());

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

app.on('before-quit', () => {
    isShuttingDown = true;
    if (pythonProcess) {
        try { pythonProcess.kill(); } catch (_) {}
        pythonProcess = null;
    }
});

app.on('window-all-closed', () => {
    if (process.platform !== 'darwin') app.quit();
});
```

- [ ] **Step 2: Rebuild the editor bundle (no JSX changes, but be safe)**

```bash
npm run build:editor
```

- [ ] **Step 3: Manually launch and verify the full flow**

```bash
npm start
```

Expected:
- Splash window opens with "Starting engine…", then briefly "Engine started. Loading editor…"
- Splash dismisses; main window opens.
- Main window shows: "BWC Clipper" / "engine v2026.04.29a" (live-fetched from the Python engine).
- Closing main window quits the app and the Python subprocess exits cleanly.

If anything in this list fails, debug before proceeding. The integration here is what every later milestone depends on.

- [ ] **Step 4: Verify the engine subprocess is actually killed on quit**

After closing the main window:

```bash
# On Windows (Git Bash):
ps -W | grep python

# Or via PowerShell:
# Get-Process | Where-Object { $_.ProcessName -eq 'python' }
```

Expected: no orphan `python.exe` running serve.py.

- [ ] **Step 5: Commit**

```bash
git add electron/main.js
git commit -m "electron: spawn engine subprocess, bridge URL to renderer via splash flow"
```

---

### Task 18: Run the full test suite end-to-end

**Files:** none (verification step)

- [ ] **Step 1: Run pytest**

```bash
.venv/Scripts/python.exe -m pytest -v
```

Expected: 8 passed (3 version + 4 server + 1 smoke + 0 conftest-only).

- [ ] **Step 2: Run vitest**

```bash
npm test
```

Expected: 2 passed (EditorApp render + version fetch).

- [ ] **Step 3: Build the editor in production mode**

```bash
NODE_ENV=production npm run build:editor
```

Expected: bundle minified, ~larger compression. No errors.

- [ ] **Step 4: Manual launch**

```bash
npm start
```

Expected: same as Task 17 Step 3 — full flow works.

- [ ] **Step 5: This is a verification-only task; no commit**

---

### Task 19: README dev quickstart and architecture note

**Files:**
- Modify: `README.md`

- [ ] **Step 1: Append a development quickstart section to README.md**

Add the markdown content shown below to `README.md`, inserted after the "Documents" section. The outer ` ```markdown ... ``` ` fence in this plan is presentational only — copy everything *between* those outer fences into the README, including the inner code fences (which must remain triple-backtick fences in the final README).

```markdown
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
```

- [ ] **Step 2: Verify the README renders by viewing it (manual)**

Open `README.md` in any markdown viewer or just `cat` it — confirm headings, code fences, and the diagram are intact.

- [ ] **Step 3: Commit**

```bash
git add README.md
git commit -m "docs: add development quickstart and architecture diagram"
```

---

### Task 20: Push and verify on GitHub

**Files:** none (push only)

- [ ] **Step 1: Push to origin**

```bash
git push
```

Expected: pushes to `main` on `origin` (https://github.com/ignavusignarus/BWC-DME-Reviewer).

- [ ] **Step 2: Verify on GitHub**

```bash
gh repo view ignavusignarus/BWC-DME-Reviewer --json defaultBranchRef,latestRelease,name 2>&1
```

Or open the URL in a browser:
https://github.com/ignavusignarus/BWC-DME-Reviewer

Expected: latest commit shown is "docs: add development quickstart and architecture diagram" (or whatever the final commit ended up being). README displays in the repo home view.

- [ ] **Step 3: Confirm Milestone 0 is done**

The milestone is done when:
- ✅ `npm start` opens a window showing "BWC Clipper" with the engine version live-fetched from the Python server.
- ✅ `pytest` passes (8 tests).
- ✅ `npm test` passes (2 tests).
- ✅ Closing the window cleanly stops the Python subprocess.
- ✅ Repo on GitHub has README, LICENSE, code, tests, plan, spec.

---

## What this milestone leaves you with

- A repo that builds and runs, with a launchable desktop app and a bidirectional Electron ↔ Python communication channel verified end-to-end.
- Test infrastructure for both sides (pytest + vitest), with each having at least one meaningful test that exercises real behavior.
- The exact patterns Milestone 1 will extend: `BWCRequestHandler`'s route table, `electronAPI`'s preload bridge, `EditorApp`'s fetch-on-mount pattern.
- Zero technical debt — every file in this milestone is at its final size and shape; subsequent milestones add files or extend route tables, but don't refactor what exists.

## Next milestone (preview, not part of this plan)

**Milestone 1: Folder open + file enumeration.** Native folder picker via `electronAPI.pickFolder()`. New engine endpoint `POST /api/project/open` that takes a folder path, walks it for media files, returns a manifest. New UI: "Open folder" button → file list. No processing yet, no transcripts. Will be its own plan document — `docs/superpowers/plans/<date>-bwc-clipper-milestone-1-folder-open.md`.
