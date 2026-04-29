# BWC Clipper — Milestone 1: Folder Open + File Enumeration — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make BWC Clipper a real desktop app for the first time: the user clicks "Open folder," picks a case directory in a native dialog, and sees a list of the media files inside (mode-tagged BWC for video / DME for audio). No processing yet, no playback yet — just enumeration and display, with the project's hidden cache directory created at the open step.

**Architecture:** Native folder picker via Electron `dialog.showOpenDialog` (IPC handled in main.js, exposed through the existing preload bridge). Engine gains a `POST /api/project/open` endpoint that walks the picked folder, identifies media files by extension, tags each with `bwc` (video) or `dme` (audio) mode, and returns a manifest. Renderer transitions from an empty state to a project view showing the file list. The project's `.bwcclipper/` cache directory is created during folder-open as the marker that this folder is now a BWC Clipper project.

**Tech Stack:** Continuing from Milestone 0 — Python 3.11 stdlib http.server, Electron 41 (`dialog`, `ipcMain`), React 19 (state lifted in `EditorApp`), pytest, vitest. No new external dependencies.

**Scope of this milestone:**
- Folder-pick IPC (Electron) and exposure through `electronAPI.pickFolder()`.
- Engine `POST /api/project/open` endpoint plus the file-walk + mode-detection logic backing it.
- Editor empty-state view, project view, and the state plumbing that swaps between them.
- `.bwcclipper/` cache directory created on first open.
- Tests for every code unit.

**Out of scope for this milestone (deliberately deferred):**
- File hashing (`source.sha256`) — happens in Milestone 2 when files are actually processed.
- Reading any media metadata (duration, codecs) — requires ffmpeg, plumbed in Milestone 2.
- Pipeline stages, transcripts, playback, clipping — Milestones 2–5.
- Background processing queue — Milestone 6.
- Persistent project state beyond `.bwcclipper/` directory existence (no `project.json` yet — re-opening a folder just re-walks it for V1).
- Per-source cache subdirectories — created on first processing in Milestone 2.

---

## File Structure

```
bwc-clipper/
├── engine/
│   ├── project.py                          NEW — Project model, file walking, mode detection,
│   │                                        cache directory creation.
│   └── server.py                           MODIFY — extend with do_POST + /api/project/open route
├── electron/
│   ├── main.js                             MODIFY — add 'pick-folder' IPC handler
│   └── preload.js                          MODIFY — expose electronAPI.pickFolder
├── editor/
│   ├── api.js                              MODIFY — add apiPost helper
│   ├── EditorApp.jsx                       MODIFY — manage project state + view routing
│   ├── EditorApp.test.jsx                  MODIFY — extend with empty-state + open-flow tests
│   └── components/                         NEW DIRECTORY
│       ├── EmptyState.jsx                  NEW — empty state with "Open folder" button
│       ├── EmptyState.test.jsx             NEW
│       ├── FileListItem.jsx                NEW — single file row in the list
│       ├── FileListItem.test.jsx           NEW
│       ├── ProjectView.jsx                 NEW — top-level project view (path + file list)
│       └── ProjectView.test.jsx            NEW
└── tests/
    ├── test_project.py                     NEW — engine.project unit tests
    └── test_server_project.py              NEW — POST /api/project/open integration tests
```

**Why split the editor components:**
- `EmptyState` and `ProjectView` are mutually exclusive — only one renders at a time.
- `FileListItem` is reused for every file in the manifest; isolating it makes the rendering predictable.
- Each component has one responsibility, fits in <50 lines, and is independently testable.

**Why a separate `tests/test_server_project.py` rather than extending `tests/test_server.py`:**
- The new test file exercises POST behavior, request body parsing, and folder-walking — quite different concerns from the existing endpoint tests. Splitting keeps each test file focused on one part of the API surface.

---

## Reference patterns (from Milestone 0 and Depo Clipper)

| New work in M1 | Pattern reference |
|---|---|
| `engine/project.py` file walking | `pathlib.Path.rglob` / `os.walk`; mirror Depo Clipper's folder validator pattern (`engine/folder_validator.py`) but simpler — we're not validating deposition formats. |
| `do_POST` in `engine/server.py` | Mirror `do_GET` shape: route table, dispatch, JSON in/out. Body parsing via `self.rfile.read(content_length)` then `json.loads`. |
| `pick-folder` IPC in `electron/main.js` | `ipcMain.handle('pick-folder', ...)` returning the path or null. Reference: Depo Clipper's same handler at `Depo-Clipper/electron/main.js` (search "pick-folder"). |
| `electronAPI.pickFolder` in `electron/preload.js` | Identical to existing `getEngineUrl` / `getAppVersion` pattern. |
| React component testing | Same setup as existing `editor/EditorApp.test.jsx`: `@testing-library/react`, `vi.fn()` for stubbing fetch and electronAPI. |

---

## A note on folder-picker testing

Native folder dialogs cannot be exercised by an automated test — they require real user interaction. The plan's testing strategy:

- **`electron/main.js` and `electron/preload.js`:** verified by manual launch (Task 14) — there is no good way to unit-test `dialog.showOpenDialog` without spinning up a real Electron environment.
- **The renderer side of the open flow:** stubbed at the `electronAPI` boundary — `EditorApp.test.jsx` stubs `electronAPI.pickFolder = () => Promise.resolve('/some/path')` and stubs `fetch` to return a synthetic manifest.
- **The engine side of the open flow:** real filesystem operations against `pytest.tmp_path` directories with synthetic empty media files.

This pattern (stub at the edges, exercise everything in the middle) is the same approach Depo Clipper uses for its folder-picker flow.

---

## Tasks

### Task 1: Create milestone-1 branch

**Files:** none

- [ ] **Step 1: Verify clean working tree on main**

```bash
cd "C:/Claude Code Projects/BWC Reviewer"
git status
```

Expected: `working tree clean`. If not, stop and report.

- [ ] **Step 2: Verify on main and up to date with origin/main**

```bash
git rev-parse --abbrev-ref HEAD
git log -1 --oneline
git log -1 --oneline origin/main
```

Expected: `main`, with the last commit being the M0 merge commit (`320a7eb`) on both local and origin.

- [ ] **Step 3: Create and switch to milestone-1 branch**

```bash
git checkout -b milestone-1-folder-open
git rev-parse --abbrev-ref HEAD
```

Expected: `milestone-1-folder-open` returned by the second command.

- [ ] **Step 4: No commit yet — branch creation is the only state change**

---

### Task 2: `engine/project.py` — `walk_media_files` (TDD)

**Files:**
- Create: `tests/test_project.py`
- Create: `engine/project.py`

This task implements one focused function: given a folder path, return a sorted list of media files inside (recursive, dotfiles excluded).

- [ ] **Step 1: Write the failing test**

`tests/test_project.py`:

```python
"""Tests for engine.project."""
from pathlib import Path

import pytest

from engine.project import walk_media_files


def _touch(path: Path):
    """Create an empty file, including parent directories."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"")


def test_walk_media_files_finds_video_and_audio(tmp_path: Path):
    _touch(tmp_path / "officer-garcia.mp4")
    _touch(tmp_path / "doctor.MP3")
    _touch(tmp_path / "notes.txt")  # not media — should be skipped
    paths = walk_media_files(tmp_path)
    basenames = sorted(p.name for p in paths)
    assert basenames == ["doctor.MP3", "officer-garcia.mp4"]


def test_walk_media_files_recursive(tmp_path: Path):
    _touch(tmp_path / "incident-001" / "officer-a.mp4")
    _touch(tmp_path / "incident-002" / "officer-b.mov")
    paths = walk_media_files(tmp_path)
    basenames = sorted(p.name for p in paths)
    assert basenames == ["officer-a.mp4", "officer-b.mov"]


def test_walk_media_files_skips_dot_directories(tmp_path: Path):
    """Hidden directories like .bwcclipper/ must not be traversed."""
    _touch(tmp_path / ".bwcclipper" / "some-source" / "transcript.json")
    _touch(tmp_path / "real.mp4")
    paths = walk_media_files(tmp_path)
    basenames = [p.name for p in paths]
    assert basenames == ["real.mp4"]


def test_walk_media_files_skips_dotfiles(tmp_path: Path):
    _touch(tmp_path / ".DS_Store")
    _touch(tmp_path / "real.mp4")
    paths = walk_media_files(tmp_path)
    basenames = [p.name for p in paths]
    assert basenames == ["real.mp4"]


def test_walk_media_files_recognizes_supported_extensions(tmp_path: Path):
    """Spec extensions: .mp4 .mov .mkv .avi (video), .mp3 .MP3 .wav .m4a .flac (audio).

    Each filename is unique (basename + extension) to avoid Windows NTFS
    case-insensitive collisions — e.g., ``a.mp3`` and ``a.MP3`` resolve to
    the same file on Windows even though they're distinct on POSIX.
    """
    fixtures = [
        "video1.mp4", "video2.mov", "video3.mkv", "video4.avi",
        "audio1.mp3", "audio2.MP3", "audio3.wav", "audio4.m4a", "audio5.flac",
    ]
    for f in fixtures:
        _touch(tmp_path / f)
    paths = walk_media_files(tmp_path)
    basenames = sorted(p.name for p in paths)
    assert basenames == sorted(fixtures)


def test_walk_media_files_returns_sorted(tmp_path: Path):
    """Result is sorted by absolute path for deterministic UI ordering."""
    _touch(tmp_path / "z.mp4")
    _touch(tmp_path / "a.mp4")
    _touch(tmp_path / "m" / "b.mp4")
    paths = walk_media_files(tmp_path)
    basenames = [p.name for p in paths]
    assert basenames == sorted(basenames)


def test_walk_media_files_raises_on_missing_path(tmp_path: Path):
    missing = tmp_path / "does-not-exist"
    with pytest.raises(FileNotFoundError):
        walk_media_files(missing)


def test_walk_media_files_raises_on_file_path(tmp_path: Path):
    f = tmp_path / "x.mp4"
    f.write_bytes(b"")
    with pytest.raises(NotADirectoryError):
        walk_media_files(f)
```

- [ ] **Step 2: Run, confirm failure**

```bash
.venv/Scripts/python.exe -m pytest tests/test_project.py -v
```

Expected: FAIL with `ModuleNotFoundError: No module named 'engine.project'`.

- [ ] **Step 3: Write `engine/project.py`**

```python
"""BWC Clipper project model.

A "project" in BWC Clipper is just a folder. This module owns the logic for
walking that folder for media files, detecting the per-file mode (BWC video
vs DME audio), and creating the hidden .bwcclipper/ cache directory.

Future milestones extend this module with per-source cache subdirectories
(Milestone 2) and clip persistence (Milestone 5).
"""

from __future__ import annotations

from pathlib import Path

# Extension allowlists. Lowercased on comparison; the source extension casing
# is preserved in the returned manifest.
VIDEO_EXTENSIONS = frozenset({"mp4", "mov", "mkv", "avi"})
AUDIO_EXTENSIONS = frozenset({"mp3", "wav", "m4a", "flac"})
MEDIA_EXTENSIONS = VIDEO_EXTENSIONS | AUDIO_EXTENSIONS


def walk_media_files(folder: Path) -> list[Path]:
    """Recursively enumerate media files under ``folder``.

    Returns a sorted list of absolute paths. Skips:
    - Files and directories whose name starts with a dot.
    - Files whose extension is not in ``MEDIA_EXTENSIONS`` (case-insensitive).

    Raises:
        FileNotFoundError: ``folder`` does not exist.
        NotADirectoryError: ``folder`` is not a directory.
    """
    folder = Path(folder).resolve()
    if not folder.exists():
        raise FileNotFoundError(folder)
    if not folder.is_dir():
        raise NotADirectoryError(folder)

    found: list[Path] = []
    for path in folder.rglob("*"):
        # rglob yields directories too — only files are media.
        if not path.is_file():
            continue
        # Skip anything inside or named as a dotfile/dotdir.
        if any(part.startswith(".") for part in path.relative_to(folder).parts):
            continue
        ext = path.suffix.lstrip(".").lower()
        if ext not in MEDIA_EXTENSIONS:
            continue
        found.append(path)

    found.sort()
    return found
```

- [ ] **Step 4: Run, confirm pass**

```bash
.venv/Scripts/python.exe -m pytest tests/test_project.py -v
```

Expected: 8 passed.

- [ ] **Step 5: Commit**

```bash
git add engine/project.py tests/test_project.py
git commit -m "engine: add walk_media_files for project folder enumeration"
```

---

### Task 3: `engine/project.py` — `detect_mode` (TDD)

**Files:**
- Modify: `tests/test_project.py` (append)
- Modify: `engine/project.py` (append)

Pure function: given a path or extension string, return `"bwc"` or `"dme"`.

- [ ] **Step 1: Write the failing test**

Append to `tests/test_project.py`:

```python
from engine.project import detect_mode


def test_detect_mode_video_is_bwc(tmp_path: Path):
    f = tmp_path / "x.mp4"
    f.write_bytes(b"")
    assert detect_mode(f) == "bwc"


def test_detect_mode_audio_is_dme(tmp_path: Path):
    f = tmp_path / "x.mp3"
    f.write_bytes(b"")
    assert detect_mode(f) == "dme"


def test_detect_mode_uppercase_extension(tmp_path: Path):
    f = tmp_path / "x.MP3"
    f.write_bytes(b"")
    assert detect_mode(f) == "dme"


def test_detect_mode_unknown_extension_raises(tmp_path: Path):
    f = tmp_path / "x.xyz"
    f.write_bytes(b"")
    with pytest.raises(ValueError):
        detect_mode(f)
```

- [ ] **Step 2: Run, confirm failure**

```bash
.venv/Scripts/python.exe -m pytest tests/test_project.py -v -k detect_mode
```

Expected: FAIL with `ImportError: cannot import name 'detect_mode'`.

- [ ] **Step 3: Append `detect_mode` to `engine/project.py`**

```python
def detect_mode(path: Path) -> str:
    """Return ``"bwc"`` for video media, ``"dme"`` for audio media.

    Mode detection is extension-based for Milestone 1. A future milestone may
    upgrade to ffprobe-based detection (e.g., to handle audio-only `.mp4`
    body-cam exports correctly), but the V1 heuristic is correct for the
    sample set we have today.

    Raises:
        ValueError: ``path`` has no recognized media extension.
    """
    ext = Path(path).suffix.lstrip(".").lower()
    if ext in VIDEO_EXTENSIONS:
        return "bwc"
    if ext in AUDIO_EXTENSIONS:
        return "dme"
    raise ValueError(f"unrecognized media extension: {path}")
```

- [ ] **Step 4: Run, confirm pass**

```bash
.venv/Scripts/python.exe -m pytest tests/test_project.py -v
```

Expected: 12 passed (8 existing walk tests + 4 new detect_mode tests).

- [ ] **Step 5: Commit**

```bash
git add engine/project.py tests/test_project.py
git commit -m "engine: add detect_mode (extension-based bwc/dme classification)"
```

---

### Task 4: `engine/project.py` — `ensure_cache_dir` (TDD)

**Files:**
- Modify: `tests/test_project.py` (append)
- Modify: `engine/project.py` (append)

- [ ] **Step 1: Write the failing test**

Append to `tests/test_project.py`:

```python
from engine.project import ensure_cache_dir


def test_ensure_cache_dir_creates_when_missing(tmp_path: Path):
    cache = ensure_cache_dir(tmp_path)
    assert cache == tmp_path / ".bwcclipper"
    assert cache.is_dir()


def test_ensure_cache_dir_idempotent(tmp_path: Path):
    cache1 = ensure_cache_dir(tmp_path)
    cache2 = ensure_cache_dir(tmp_path)
    assert cache1 == cache2
    assert cache1.is_dir()


def test_ensure_cache_dir_raises_if_blocked_by_file(tmp_path: Path):
    blocker = tmp_path / ".bwcclipper"
    blocker.write_bytes(b"not a directory")
    with pytest.raises(NotADirectoryError):
        ensure_cache_dir(tmp_path)
```

- [ ] **Step 2: Run, confirm failure**

```bash
.venv/Scripts/python.exe -m pytest tests/test_project.py -v -k ensure_cache
```

Expected: FAIL with `ImportError: cannot import name 'ensure_cache_dir'`.

- [ ] **Step 3: Append to `engine/project.py`**

```python
CACHE_DIR_NAME = ".bwcclipper"


def ensure_cache_dir(folder: Path) -> Path:
    """Ensure ``folder/.bwcclipper/`` exists; return its path.

    Idempotent: safe to call repeatedly. Raises ``NotADirectoryError`` if a
    non-directory file already occupies the path.
    """
    folder = Path(folder).resolve()
    cache = folder / CACHE_DIR_NAME
    if cache.exists() and not cache.is_dir():
        raise NotADirectoryError(cache)
    cache.mkdir(exist_ok=True)
    return cache
```

- [ ] **Step 4: Run, confirm pass**

```bash
.venv/Scripts/python.exe -m pytest tests/test_project.py -v
```

Expected: 15 passed.

- [ ] **Step 5: Commit**

```bash
git add engine/project.py tests/test_project.py
git commit -m "engine: add ensure_cache_dir for .bwcclipper/ creation"
```

---

### Task 5: `engine/project.py` — `open_project` orchestrator (TDD)

**Files:**
- Modify: `tests/test_project.py` (append)
- Modify: `engine/project.py` (append)

This composes `walk_media_files` + `detect_mode` + `ensure_cache_dir` and produces the manifest dict the HTTP endpoint will return.

- [ ] **Step 1: Write the failing test**

Append to `tests/test_project.py`:

```python
from engine.project import open_project


def test_open_project_returns_manifest(tmp_path: Path):
    _touch(tmp_path / "officer-a.mp4")
    _touch(tmp_path / "subjects" / "doctor.MP3")
    _touch(tmp_path / "readme.txt")  # ignored

    manifest = open_project(tmp_path)

    assert manifest["folder"] == str(tmp_path.resolve()).replace("\\", "/")
    files = manifest["files"]
    assert len(files) == 2
    by_basename = {f["basename"]: f for f in files}

    assert by_basename["officer-a.mp4"]["mode"] == "bwc"
    assert by_basename["officer-a.mp4"]["extension"] == "mp4"
    assert by_basename["officer-a.mp4"]["size_bytes"] == 0
    assert by_basename["officer-a.mp4"]["path"].endswith("officer-a.mp4")

    assert by_basename["doctor.MP3"]["mode"] == "dme"
    assert by_basename["doctor.MP3"]["extension"] == "MP3"  # case preserved


def test_open_project_creates_cache_directory(tmp_path: Path):
    _touch(tmp_path / "x.mp4")
    open_project(tmp_path)
    assert (tmp_path / ".bwcclipper").is_dir()


def test_open_project_empty_folder_is_valid(tmp_path: Path):
    """No media files is not an error — manifest just has empty files list."""
    manifest = open_project(tmp_path)
    assert manifest["files"] == []


def test_open_project_paths_use_forward_slashes(tmp_path: Path):
    _touch(tmp_path / "subdir" / "x.mp4")
    manifest = open_project(tmp_path)
    assert "\\" not in manifest["files"][0]["path"]
    assert "\\" not in manifest["folder"]


def test_open_project_raises_on_missing_folder(tmp_path: Path):
    missing = tmp_path / "nope"
    with pytest.raises(FileNotFoundError):
        open_project(missing)
```

- [ ] **Step 2: Run, confirm failure**

```bash
.venv/Scripts/python.exe -m pytest tests/test_project.py -v -k open_project
```

Expected: FAIL with `ImportError: cannot import name 'open_project'`.

- [ ] **Step 3: Append to `engine/project.py`**

```python
def open_project(folder: Path) -> dict:
    """Open a folder as a BWC Clipper project.

    1. Validates the folder exists and is a directory (via walk_media_files).
    2. Ensures .bwcclipper/ cache directory exists.
    3. Walks the folder for media files.
    4. Returns a manifest dict for the HTTP endpoint.

    Manifest schema (V1):
        {
            "folder": "<absolute path, forward-slashes>",
            "files": [
                {
                    "basename": "officer-garcia.mp4",
                    "path": "<absolute path, forward-slashes>",
                    "extension": "mp4",          # original casing preserved
                    "mode": "bwc",                # bwc | dme
                    "size_bytes": 123456789
                },
                ...
            ]
        }
    """
    folder = Path(folder).resolve()
    # walk_media_files validates folder exists and is a directory.
    paths = walk_media_files(folder)
    ensure_cache_dir(folder)

    files = []
    for p in paths:
        files.append(
            {
                "basename": p.name,
                "path": str(p).replace("\\", "/"),
                "extension": p.suffix.lstrip("."),
                "mode": detect_mode(p),
                "size_bytes": p.stat().st_size,
            }
        )

    return {
        "folder": str(folder).replace("\\", "/"),
        "files": files,
    }
```

- [ ] **Step 4: Run, confirm pass**

```bash
.venv/Scripts/python.exe -m pytest tests/test_project.py -v
```

Expected: 20 passed.

- [ ] **Step 5: Commit**

```bash
git add engine/project.py tests/test_project.py
git commit -m "engine: add open_project orchestrator returning manifest dict"
```

---

### Task 6: `engine/server.py` — POST handler infrastructure (TDD)

**Files:**
- Create: `tests/test_server_project.py`
- Modify: `engine/server.py`

Refactor BWCRequestHandler to support POST. The route table grows to two: GET routes and POST routes. Body parsing is shared. The new endpoint `POST /api/project/open` reads `{"path": "..."}`, calls `open_project`, returns the manifest.

- [ ] **Step 1: Write the failing test**

`tests/test_server_project.py`:

```python
"""Tests for /api/project/open endpoint."""
import json
import threading
from http.server import HTTPServer
from pathlib import Path

import pytest
import requests

from engine.server import BWCRequestHandler


@pytest.fixture
def running_server():
    """Start engine.server on a random local port. Yield port."""
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


def _touch(path: Path):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"")


def test_open_project_endpoint_returns_200_and_manifest(running_server, tmp_path: Path):
    _touch(tmp_path / "officer.mp4")
    _touch(tmp_path / "doctor.MP3")

    response = requests.post(
        f"http://127.0.0.1:{running_server}/api/project/open",
        json={"path": str(tmp_path)},
        timeout=5,
    )
    assert response.status_code == 200
    body = response.json()
    assert body["folder"] == str(tmp_path.resolve()).replace("\\", "/")
    assert len(body["files"]) == 2
    modes = {f["basename"]: f["mode"] for f in body["files"]}
    assert modes == {"officer.mp4": "bwc", "doctor.MP3": "dme"}


def test_open_project_creates_cache_dir(running_server, tmp_path: Path):
    response = requests.post(
        f"http://127.0.0.1:{running_server}/api/project/open",
        json={"path": str(tmp_path)},
        timeout=5,
    )
    assert response.status_code == 200
    assert (tmp_path / ".bwcclipper").is_dir()


def test_open_project_returns_404_for_missing_folder(running_server, tmp_path: Path):
    missing = tmp_path / "does-not-exist"
    response = requests.post(
        f"http://127.0.0.1:{running_server}/api/project/open",
        json={"path": str(missing)},
        timeout=5,
    )
    assert response.status_code == 404
    body = response.json()
    assert "error" in body


def test_open_project_returns_400_for_file_path(running_server, tmp_path: Path):
    f = tmp_path / "file.mp4"
    f.write_bytes(b"")
    response = requests.post(
        f"http://127.0.0.1:{running_server}/api/project/open",
        json={"path": str(f)},
        timeout=5,
    )
    assert response.status_code == 400


def test_open_project_returns_400_for_missing_body(running_server):
    response = requests.post(
        f"http://127.0.0.1:{running_server}/api/project/open",
        timeout=5,
    )
    assert response.status_code == 400


def test_open_project_returns_400_for_malformed_json(running_server):
    response = requests.post(
        f"http://127.0.0.1:{running_server}/api/project/open",
        data=b"not json",
        headers={"Content-Type": "application/json"},
        timeout=5,
    )
    assert response.status_code == 400


def test_open_project_returns_400_when_path_field_missing(running_server):
    response = requests.post(
        f"http://127.0.0.1:{running_server}/api/project/open",
        json={"folder": "/some/place"},  # wrong field name
        timeout=5,
    )
    assert response.status_code == 400


def test_unknown_post_path_returns_404(running_server):
    response = requests.post(
        f"http://127.0.0.1:{running_server}/api/nope",
        json={},
        timeout=5,
    )
    assert response.status_code == 404
```

- [ ] **Step 2: Run, confirm failure**

```bash
.venv/Scripts/python.exe -m pytest tests/test_server_project.py -v
```

Expected: 8 tests fail. The reason will be either `405 Method Not Allowed` (default `BaseHTTPRequestHandler` behavior for unimplemented methods) or `501 Unsupported method` — anything other than the expected status codes counts as failure.

- [ ] **Step 3: Replace `engine/server.py`**

Full file contents — this refactors the module to have GET/POST route tables and shared request-body parsing:

```python
"""BWC Clipper local HTTP server.

Stdlib http.server only — no Flask/FastAPI. The handler dispatches GET and
POST requests to small route tables. Each handler returns a tuple
(status_code, body_dict). Future milestones extend the route tables.
"""

import json
import logging
from http.server import BaseHTTPRequestHandler
from pathlib import Path
from typing import Callable

from engine.project import open_project
from engine.version import get_version

logger = logging.getLogger("bwc-clipper.server")


class BWCRequestHandler(BaseHTTPRequestHandler):
    """Routes requests to handler methods. JSON in, JSON out."""

    def log_message(self, format, *args):
        logger.debug("%s - %s", self.address_string(), format % args)

    def _get_routes(self) -> dict[str, Callable[[], tuple[int, dict]]]:
        return {
            "/api/health": self._handle_health,
            "/api/version": self._handle_version,
        }

    def _post_routes(self) -> dict[str, Callable[[dict], tuple[int, dict]]]:
        return {
            "/api/project/open": self._handle_project_open,
        }

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

    def do_POST(self):
        handler = self._post_routes().get(self.path)
        if handler is None:
            self._send_json(404, {"error": "not found", "path": self.path})
            return
        body = self._read_json_body()
        if body is None:
            return  # error already sent by _read_json_body
        try:
            status, response_body = handler(body)
            self._send_json(status, response_body)
        except Exception as exc:  # pragma: no cover - defensive
            logger.exception("POST handler crashed for %s", self.path)
            self._send_json(500, {"error": "internal", "detail": str(exc)})

    def _read_json_body(self) -> dict | None:
        """Read and parse the request body as JSON. Sends 400 on failure and
        returns None; otherwise returns the parsed dict.
        """
        length_header = self.headers.get("Content-Length")
        if not length_header:
            self._send_json(400, {"error": "missing Content-Length / empty body"})
            return None
        try:
            content_length = int(length_header)
        except ValueError:
            self._send_json(400, {"error": "invalid Content-Length"})
            return None
        if content_length <= 0:
            self._send_json(400, {"error": "empty body"})
            return None
        raw = self.rfile.read(content_length)
        try:
            data = json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            self._send_json(400, {"error": "malformed JSON", "detail": str(exc)})
            return None
        if not isinstance(data, dict):
            self._send_json(400, {"error": "body must be a JSON object"})
            return None
        return data

    # ── GET handlers ──

    def _handle_health(self) -> tuple[int, dict]:
        return 200, {"status": "ok"}

    def _handle_version(self) -> tuple[int, dict]:
        return 200, {"version": get_version()}

    # ── POST handlers ──

    def _handle_project_open(self, body: dict) -> tuple[int, dict]:
        path_str = body.get("path")
        if not isinstance(path_str, str) or not path_str:
            return 400, {"error": "missing 'path' field"}
        try:
            manifest = open_project(Path(path_str))
        except FileNotFoundError:
            return 404, {"error": "folder not found", "path": path_str}
        except NotADirectoryError:
            return 400, {"error": "path is not a directory", "path": path_str}
        return 200, manifest

    # ── Response helper ──

    def _send_json(self, status: int, body: dict):
        payload = json.dumps(body).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(payload)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(payload)
```

- [ ] **Step 4: Run, confirm new tests pass**

```bash
.venv/Scripts/python.exe -m pytest tests/test_server_project.py -v
```

Expected: 8 passed.

- [ ] **Step 5: Run the full pytest suite — make sure existing tests still pass**

```bash
.venv/Scripts/python.exe -m pytest -v
```

Expected: all tests pass (4 server + 1 smoke + 3 version + 20 project + 8 new = 36 tests).

- [ ] **Step 6: Commit**

```bash
git add engine/server.py tests/test_server_project.py
git commit -m "engine: add POST handling and /api/project/open endpoint"
```

---

### Task 7: `electron/main.js` — `pick-folder` IPC handler

**Files:**
- Modify: `electron/main.js`

- [ ] **Step 1: Edit `electron/main.js` — add `dialog` to imports and an IPC handler**

Find the line:

```javascript
const { app, BrowserWindow, ipcMain } = require('electron');
```

Replace with:

```javascript
const { app, BrowserWindow, dialog, ipcMain } = require('electron');
```

Then find the existing IPC handler block:

```javascript
ipcMain.handle('get-engine-url', () => {
    if (!serverPort) throw new Error('engine not yet started');
    return `http://127.0.0.1:${serverPort}`;
});
ipcMain.handle('get-app-version', () => app.getVersion());
```

Append a third handler immediately after:

```javascript
ipcMain.handle('pick-folder', async () => {
    const result = await dialog.showOpenDialog(mainWindow ?? undefined, {
        title: 'Open BWC Clipper project folder',
        properties: ['openDirectory', 'createDirectory'],
    });
    if (result.canceled || result.filePaths.length === 0) {
        return null;
    }
    return result.filePaths[0];
});
```

- [ ] **Step 2: Verify with manual smoke launch (folder picker visibility)**

This handler can only be exercised manually. Defer to Task 14 — for now, build the editor and confirm the app still launches without crashing:

```bash
npm run build:editor
```

Expected: `[build-editor] built editor-bundle.js`. No errors.

- [ ] **Step 3: Commit**

```bash
git add electron/main.js
git commit -m "electron: add pick-folder IPC handler using dialog.showOpenDialog"
```

---

### Task 8: `electron/preload.js` — expose `pickFolder`

**Files:**
- Modify: `electron/preload.js`

- [ ] **Step 1: Edit `electron/preload.js`**

Find:

```javascript
contextBridge.exposeInMainWorld('electronAPI', {
    getEngineUrl: () => ipcRenderer.invoke('get-engine-url'),
    getAppVersion: () => ipcRenderer.invoke('get-app-version'),
});
```

Replace with:

```javascript
contextBridge.exposeInMainWorld('electronAPI', {
    getEngineUrl: () => ipcRenderer.invoke('get-engine-url'),
    getAppVersion: () => ipcRenderer.invoke('get-app-version'),
    pickFolder: () => ipcRenderer.invoke('pick-folder'),
});
```

- [ ] **Step 2: No automated check (preload is exercised at runtime)**

- [ ] **Step 3: Commit**

```bash
git add electron/preload.js
git commit -m "electron: expose electronAPI.pickFolder"
```

---

### Task 9: `editor/api.js` — add `apiPost` helper

**Files:**
- Modify: `editor/api.js`

- [ ] **Step 1: Append `apiPost` after `apiGet`**

Find the existing end of `editor/api.js`:

```javascript
export async function apiGet(path) {
    const base = await getBaseUrl();
    const response = await fetch(`${base}${path}`);
    if (!response.ok) {
        throw new Error(`API ${path} returned ${response.status}`);
    }
    return response.json();
}
```

Append immediately after:

```javascript
export async function apiPost(path, body) {
    const base = await getBaseUrl();
    const response = await fetch(`${base}${path}`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body),
    });
    if (!response.ok) {
        let detail = '';
        try {
            const errorBody = await response.json();
            detail = errorBody.error ? `: ${errorBody.error}` : '';
        } catch (_) { /* not JSON */ }
        throw new Error(`API ${path} returned ${response.status}${detail}`);
    }
    return response.json();
}
```

- [ ] **Step 2: No new test in this task — `apiPost` gets exercised through `EditorApp.test.jsx` updates in Task 13**

- [ ] **Step 3: Commit**

```bash
git add editor/api.js
git commit -m "editor: add apiPost helper for POST endpoints"
```

---

### Task 10: `editor/components/EmptyState.jsx` (TDD)

**Files:**
- Create: `editor/components/EmptyState.test.jsx`
- Create: `editor/components/EmptyState.jsx`

- [ ] **Step 1: Write the failing test**

`editor/components/EmptyState.test.jsx`:

```jsx
import { describe, expect, it, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import EmptyState from './EmptyState.jsx';

describe('EmptyState', () => {
    it('renders the open-folder button', () => {
        render(<EmptyState onOpenFolder={() => {}} />);
        expect(screen.getByRole('button', { name: /open folder/i })).toBeDefined();
    });

    it('calls onOpenFolder when the button is clicked', () => {
        const onOpenFolder = vi.fn();
        render(<EmptyState onOpenFolder={onOpenFolder} />);
        fireEvent.click(screen.getByRole('button', { name: /open folder/i }));
        expect(onOpenFolder).toHaveBeenCalledTimes(1);
    });

    it('renders an explanatory headline', () => {
        render(<EmptyState onOpenFolder={() => {}} />);
        // We don't assert exact wording — just that the user gets some context
        // beyond a bare button. Match against the app name.
        expect(screen.getByText(/BWC Clipper/i)).toBeDefined();
    });
});
```

- [ ] **Step 2: Run, confirm failure**

```bash
npx vitest run editor/components/EmptyState.test.jsx
```

Expected: FAIL — `Failed to resolve import "./EmptyState.jsx"`.

- [ ] **Step 3: Create `editor/components/EmptyState.jsx`**

```jsx
import React from 'react';

export default function EmptyState({ onOpenFolder }) {
    return (
        <div style={{ textAlign: 'center', maxWidth: 540, padding: 24 }}>
            <h1 style={{ fontSize: '2rem', margin: 0, color: '#5eead4' }}>BWC Clipper</h1>
            <p style={{ marginTop: '0.75rem', color: '#8b949e', lineHeight: 1.5 }}>
                Open a folder containing body-worn camera video or defense medical exam audio
                to begin reviewing.
            </p>
            <button
                onClick={onOpenFolder}
                style={{
                    marginTop: '1.5rem',
                    padding: '0.75rem 1.5rem',
                    fontSize: '1rem',
                    background: '#1f6feb',
                    color: '#fff',
                    border: 'none',
                    borderRadius: 6,
                    cursor: 'pointer',
                }}
            >
                Open folder
            </button>
        </div>
    );
}
```

- [ ] **Step 4: Run, confirm pass**

```bash
npx vitest run editor/components/EmptyState.test.jsx
```

Expected: 3 passed.

- [ ] **Step 5: Commit**

```bash
git add editor/components/EmptyState.jsx editor/components/EmptyState.test.jsx
git commit -m "editor: add EmptyState component with open-folder CTA"
```

---

### Task 11: `editor/components/FileListItem.jsx` (TDD)

**Files:**
- Create: `editor/components/FileListItem.test.jsx`
- Create: `editor/components/FileListItem.jsx`

- [ ] **Step 1: Write the failing test**

`editor/components/FileListItem.test.jsx`:

```jsx
import { describe, expect, it, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import FileListItem from './FileListItem.jsx';

const sampleFile = {
    basename: 'officer-garcia.mp4',
    path: 'C:/case/officer-garcia.mp4',
    extension: 'mp4',
    mode: 'bwc',
    size_bytes: 12_345_678,
};

describe('FileListItem', () => {
    it('renders the basename', () => {
        render(<FileListItem file={sampleFile} selected={false} onSelect={() => {}} />);
        expect(screen.getByText('officer-garcia.mp4')).toBeDefined();
    });

    it('renders the mode badge (BWC for video)', () => {
        render(<FileListItem file={sampleFile} selected={false} onSelect={() => {}} />);
        expect(screen.getByText(/BWC/i)).toBeDefined();
    });

    it('renders DME for audio mode', () => {
        const audio = { ...sampleFile, mode: 'dme', basename: 'doctor.MP3' };
        render(<FileListItem file={audio} selected={false} onSelect={() => {}} />);
        expect(screen.getByText(/DME/i)).toBeDefined();
    });

    it('renders human-readable size', () => {
        render(<FileListItem file={sampleFile} selected={false} onSelect={() => {}} />);
        // 12,345,678 bytes ≈ 11.8 MB
        expect(screen.getByText(/11\.8 MB|12 MB|11 MB/)).toBeDefined();
    });

    it('calls onSelect when clicked', () => {
        const onSelect = vi.fn();
        render(<FileListItem file={sampleFile} selected={false} onSelect={onSelect} />);
        fireEvent.click(screen.getByText('officer-garcia.mp4'));
        expect(onSelect).toHaveBeenCalledWith(sampleFile);
    });

    it('renders selected styling when selected=true', () => {
        const { container } = render(
            <FileListItem file={sampleFile} selected={true} onSelect={() => {}} />,
        );
        // We just assert the container has an aria-selected attribute we can check
        const item = container.querySelector('[aria-selected]');
        expect(item).not.toBeNull();
        expect(item.getAttribute('aria-selected')).toBe('true');
    });
});
```

- [ ] **Step 2: Run, confirm failure**

```bash
npx vitest run editor/components/FileListItem.test.jsx
```

Expected: FAIL — `Failed to resolve import "./FileListItem.jsx"`.

- [ ] **Step 3: Create `editor/components/FileListItem.jsx`**

```jsx
import React from 'react';

const MODE_LABELS = { bwc: 'BWC', dme: 'DME' };
const MODE_COLORS = {
    bwc: { bg: '#0e3a4a', fg: '#5eead4' },
    dme: { bg: '#3a2d0e', fg: '#fbbf24' },
};

function formatSize(bytes) {
    if (bytes < 1024) return `${bytes} B`;
    if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
    if (bytes < 1024 * 1024 * 1024) return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
    return `${(bytes / (1024 * 1024 * 1024)).toFixed(2)} GB`;
}

export default function FileListItem({ file, selected, onSelect }) {
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
        </div>
    );
}
```

- [ ] **Step 4: Run, confirm pass**

```bash
npx vitest run editor/components/FileListItem.test.jsx
```

Expected: 6 passed.

- [ ] **Step 5: Commit**

```bash
git add editor/components/FileListItem.jsx editor/components/FileListItem.test.jsx
git commit -m "editor: add FileListItem component"
```

---

### Task 12: `editor/components/ProjectView.jsx` (TDD)

**Files:**
- Create: `editor/components/ProjectView.test.jsx`
- Create: `editor/components/ProjectView.jsx`

- [ ] **Step 1: Write the failing test**

`editor/components/ProjectView.test.jsx`:

```jsx
import { describe, expect, it, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import ProjectView from './ProjectView.jsx';

const sampleManifest = {
    folder: 'C:/case-folder',
    files: [
        { basename: 'a.mp4', path: 'C:/case-folder/a.mp4', extension: 'mp4', mode: 'bwc', size_bytes: 1024 },
        { basename: 'b.MP3', path: 'C:/case-folder/b.MP3', extension: 'MP3', mode: 'dme', size_bytes: 2048 },
    ],
};

describe('ProjectView', () => {
    it('renders the folder path in the header', () => {
        render(
            <ProjectView
                manifest={sampleManifest}
                selectedPath={null}
                onSelectFile={() => {}}
                onCloseProject={() => {}}
            />,
        );
        expect(screen.getByText(/C:\/case-folder/)).toBeDefined();
    });

    it('renders a row per file', () => {
        render(
            <ProjectView
                manifest={sampleManifest}
                selectedPath={null}
                onSelectFile={() => {}}
                onCloseProject={() => {}}
            />,
        );
        expect(screen.getByText('a.mp4')).toBeDefined();
        expect(screen.getByText('b.MP3')).toBeDefined();
    });

    it('marks the selected file', () => {
        const { container } = render(
            <ProjectView
                manifest={sampleManifest}
                selectedPath="C:/case-folder/a.mp4"
                onSelectFile={() => {}}
                onCloseProject={() => {}}
            />,
        );
        const selected = container.querySelector('[aria-selected="true"]');
        expect(selected).not.toBeNull();
        expect(selected.textContent).toContain('a.mp4');
    });

    it('calls onSelectFile with the file when a row is clicked', () => {
        const onSelectFile = vi.fn();
        render(
            <ProjectView
                manifest={sampleManifest}
                selectedPath={null}
                onSelectFile={onSelectFile}
                onCloseProject={() => {}}
            />,
        );
        fireEvent.click(screen.getByText('b.MP3'));
        expect(onSelectFile).toHaveBeenCalledWith(
            expect.objectContaining({ basename: 'b.MP3', mode: 'dme' }),
        );
    });

    it('shows a "no media files" message for an empty manifest', () => {
        const empty = { folder: 'C:/empty', files: [] };
        render(
            <ProjectView
                manifest={empty}
                selectedPath={null}
                onSelectFile={() => {}}
                onCloseProject={() => {}}
            />,
        );
        expect(screen.getByText(/no media files/i)).toBeDefined();
    });

    it('calls onCloseProject when the close button is clicked', () => {
        const onCloseProject = vi.fn();
        render(
            <ProjectView
                manifest={sampleManifest}
                selectedPath={null}
                onSelectFile={() => {}}
                onCloseProject={onCloseProject}
            />,
        );
        fireEvent.click(screen.getByRole('button', { name: /close/i }));
        expect(onCloseProject).toHaveBeenCalledTimes(1);
    });
});
```

- [ ] **Step 2: Run, confirm failure**

```bash
npx vitest run editor/components/ProjectView.test.jsx
```

Expected: FAIL — `Failed to resolve import "./ProjectView.jsx"`.

- [ ] **Step 3: Create `editor/components/ProjectView.jsx`**

```jsx
import React from 'react';
import FileListItem from './FileListItem.jsx';

export default function ProjectView({ manifest, selectedPath, onSelectFile, onCloseProject }) {
    return (
        <div
            style={{
                display: 'flex',
                flexDirection: 'column',
                width: '100%',
                height: '100%',
                padding: '1rem',
                boxSizing: 'border-box',
            }}
        >
            <div
                style={{
                    display: 'flex',
                    alignItems: 'center',
                    paddingBottom: '0.75rem',
                    borderBottom: '1px solid #21262d',
                    marginBottom: '0.75rem',
                }}
            >
                <div style={{ flex: 1, minWidth: 0 }}>
                    <div style={{ fontSize: '0.8rem', color: '#6e7681' }}>Project folder</div>
                    <div
                        style={{
                            fontFamily: 'ui-monospace, monospace',
                            fontSize: '0.9rem',
                            color: '#c9d1d9',
                            whiteSpace: 'nowrap',
                            overflow: 'hidden',
                            textOverflow: 'ellipsis',
                        }}
                        title={manifest.folder}
                    >
                        {manifest.folder}
                    </div>
                </div>
                <button
                    onClick={onCloseProject}
                    style={{
                        background: 'transparent',
                        color: '#8b949e',
                        border: '1px solid #30363d',
                        borderRadius: 4,
                        padding: '0.4rem 0.8rem',
                        cursor: 'pointer',
                    }}
                >
                    Close
                </button>
            </div>

            {manifest.files.length === 0 ? (
                <div style={{ color: '#6e7681', textAlign: 'center', padding: '2rem' }}>
                    No media files in this folder. Drop in some `.mp4` / `.mp3` files and reopen.
                </div>
            ) : (
                <div role="listbox" style={{ overflowY: 'auto', flex: 1 }}>
                    {manifest.files.map((file) => (
                        <FileListItem
                            key={file.path}
                            file={file}
                            selected={file.path === selectedPath}
                            onSelect={onSelectFile}
                        />
                    ))}
                </div>
            )}
        </div>
    );
}
```

- [ ] **Step 4: Run, confirm pass**

```bash
npx vitest run editor/components/ProjectView.test.jsx
```

Expected: 6 passed.

- [ ] **Step 5: Commit**

```bash
git add editor/components/ProjectView.jsx editor/components/ProjectView.test.jsx
git commit -m "editor: add ProjectView component with file list and close action"
```

---

### Task 13: `editor/EditorApp.jsx` — wire empty-state ↔ project-view (TDD)

**Files:**
- Modify: `editor/EditorApp.test.jsx` (rewrite)
- Modify: `editor/EditorApp.jsx` (rewrite)

This task replaces both EditorApp files. The new EditorApp manages a single piece of state (`manifest` — null when no project, the full manifest dict when a project is open). Folder-pick → POST `/api/project/open` → set manifest.

- [ ] **Step 1: Replace `editor/EditorApp.test.jsx`**

```jsx
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import EditorApp from './EditorApp.jsx';
import { _resetCachedBaseForTests } from './api.js';

const SAMPLE_MANIFEST = {
    folder: 'C:/case-folder',
    files: [
        { basename: 'officer.mp4', path: 'C:/case-folder/officer.mp4', extension: 'mp4', mode: 'bwc', size_bytes: 1024 },
    ],
};

describe('EditorApp', () => {
    beforeEach(() => {
        _resetCachedBaseForTests();
        global.window.electronAPI = {
            getEngineUrl: () => Promise.resolve('http://127.0.0.1:8888'),
            pickFolder: vi.fn(() => Promise.resolve('C:/case-folder')),
        };
        global.fetch = vi.fn((url, opts) => {
            if (url === 'http://127.0.0.1:8888/api/project/open' && opts?.method === 'POST') {
                return Promise.resolve({
                    ok: true,
                    json: () => Promise.resolve(SAMPLE_MANIFEST),
                });
            }
            return Promise.reject(new Error('unexpected url: ' + url));
        });
    });

    afterEach(() => {
        delete global.window.electronAPI;
        global.fetch = undefined;
    });

    it('renders the empty state on mount', () => {
        render(<EditorApp />);
        expect(screen.getByRole('button', { name: /open folder/i })).toBeDefined();
    });

    it('opens a folder, calls /api/project/open, and renders the project view', async () => {
        render(<EditorApp />);
        fireEvent.click(screen.getByRole('button', { name: /open folder/i }));
        await waitFor(() => {
            expect(screen.getByText('officer.mp4')).toBeDefined();
        });
        expect(window.electronAPI.pickFolder).toHaveBeenCalledTimes(1);
        expect(global.fetch).toHaveBeenCalledWith(
            'http://127.0.0.1:8888/api/project/open',
            expect.objectContaining({
                method: 'POST',
                body: JSON.stringify({ path: 'C:/case-folder' }),
            }),
        );
    });

    it('does nothing if the user cancels the folder dialog', async () => {
        window.electronAPI.pickFolder = vi.fn(() => Promise.resolve(null));
        render(<EditorApp />);
        fireEvent.click(screen.getByRole('button', { name: /open folder/i }));
        // Wait a tick to confirm no fetch fired
        await new Promise((r) => setTimeout(r, 10));
        expect(global.fetch).not.toHaveBeenCalled();
        // Still on empty state
        expect(screen.getByRole('button', { name: /open folder/i })).toBeDefined();
    });

    it('returns to empty state when the project is closed', async () => {
        render(<EditorApp />);
        fireEvent.click(screen.getByRole('button', { name: /open folder/i }));
        await waitFor(() => {
            expect(screen.getByText('officer.mp4')).toBeDefined();
        });
        fireEvent.click(screen.getByRole('button', { name: /close/i }));
        expect(screen.getByRole('button', { name: /open folder/i })).toBeDefined();
        expect(screen.queryByText('officer.mp4')).toBeNull();
    });

    it('renders an inline error if /api/project/open fails', async () => {
        global.fetch = vi.fn(() =>
            Promise.resolve({
                ok: false,
                status: 404,
                json: () => Promise.resolve({ error: 'folder not found' }),
            }),
        );
        render(<EditorApp />);
        fireEvent.click(screen.getByRole('button', { name: /open folder/i }));
        await waitFor(() => {
            expect(screen.getByText(/folder not found/i)).toBeDefined();
        });
    });
});
```

- [ ] **Step 2: Run, confirm failures (current EditorApp doesn't have folder-open behavior)**

```bash
npx vitest run editor/EditorApp.test.jsx
```

Expected: FAIL on the new test cases (the existing rendering test may pass or fail depending on whether `EditorApp` still references the version-fetch logic — that logic is being replaced).

- [ ] **Step 3: Replace `editor/EditorApp.jsx`**

```jsx
import React, { useState } from 'react';
import { apiPost } from './api.js';
import EmptyState from './components/EmptyState.jsx';
import ProjectView from './components/ProjectView.jsx';

export default function EditorApp() {
    const [manifest, setManifest] = useState(null);
    const [selectedPath, setSelectedPath] = useState(null);
    const [error, setError] = useState(null);

    async function openFolder() {
        setError(null);
        const folderPath = await window.electronAPI.pickFolder();
        if (!folderPath) return; // user cancelled
        try {
            const result = await apiPost('/api/project/open', { path: folderPath });
            setManifest(result);
            setSelectedPath(null);
        } catch (err) {
            setError(err.message);
        }
    }

    function closeProject() {
        setManifest(null);
        setSelectedPath(null);
        setError(null);
    }

    function selectFile(file) {
        setSelectedPath(file.path);
    }

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
                />
            )}
        </div>
    );
}
```

- [ ] **Step 4: Run the full vitest suite**

```bash
npm test
```

Expected: all tests pass — 5 EditorApp + 3 EmptyState + 6 FileListItem + 6 ProjectView = 20 tests.

- [ ] **Step 5: Commit**

```bash
git add editor/EditorApp.jsx editor/EditorApp.test.jsx
git commit -m "editor: wire empty-state and project-view in EditorApp"
```

---

### Task 14: Manual launch verification

**Files:** none (verification step, no commit)

This task verifies the full end-to-end flow with a real Electron launch and a real folder.

- [ ] **Step 1: Build the editor bundle**

```bash
npm run build:editor
```

Expected: `[build-editor] built editor-bundle.js`.

- [ ] **Step 2: Run the full test suites once more**

```bash
.venv/Scripts/python.exe -m pytest -v
npm test
```

Expected: all tests pass.

- [ ] **Step 3: Launch the app**

```bash
npm start
```

Expected manual verification:
- Splash → main window opens.
- Main window shows "BWC Clipper" + "Open folder" button (the new empty state).
- Clicking the button opens a native folder picker.
- Picking the `Samples/` folder (which has BWC and DME subfolders with real files) shows the project view with all 7 sample files listed (4 BWC `.mp4` + 3 DME `.MP3`), each tagged with the right mode badge.
- Each file shows a human-readable size.
- Clicking a file highlights it; the selection is mutually exclusive.
- Clicking "Close" returns to the empty state.
- Cancelling the folder picker leaves the empty state intact.
- After closing the app, no orphan `python.exe` processes remain.

- [ ] **Step 4: If anything fails, debug — do NOT commit until the manual flow works**

- [ ] **Step 5: Spot-check that `.bwcclipper/` was created in the picked folder**

```bash
ls -la "C:/Claude Code Projects/BWC Reviewer/Samples/.bwcclipper" 2>&1
```

Expected: directory exists. (After verification, you can leave it; it's gitignored.)

- [ ] **Step 6: This is verification-only — no commit**

---

### Task 15: README — update with M1 capabilities

**Files:**
- Modify: `README.md`

- [ ] **Step 1: Edit `README.md`**

In the section "## What the app does", item 1 currently reads:

```
1. Open a folder containing media files (BWC `.mp4` / DME `.mp3` / etc.).
```

This is still accurate. No edit needed for that line.

Replace the "**Status:**" line near the top (currently `> **Status:** Pre-implementation. Design spec is complete; implementation plan is being written.`) with:

```
> **Status:** Milestone 1 of 8 complete — folder open + file enumeration. Use `npm start` to launch; pick a folder containing `.mp4`/`.mp3` files and the app lists them.
```

- [ ] **Step 2: Commit**

```bash
git add README.md
git commit -m "docs: update status to M1 complete"
```

---

### Task 16: Push, merge to main, clean up

**Files:** none

- [ ] **Step 1: Push the branch to origin**

```bash
git push -u origin milestone-1-folder-open
```

- [ ] **Step 2: Switch to main and merge**

```bash
git checkout main
git merge --no-ff milestone-1-folder-open -m "$(cat <<'EOF'
Merge milestone 1: folder open + file enumeration

Native folder picker via electronAPI.pickFolder. Engine endpoint
POST /api/project/open walks the picked folder for media files,
detects BWC vs DME mode by extension, returns a manifest. Editor
renders empty state → project view; file selection is state-only
(no playback yet — that arrives with the pipeline in Milestone 2).
.bwcclipper/ cache directory is created on folder open as the
marker that the folder is now a BWC Clipper project.

Test coverage: 28 new tests across engine.project (20 unit) and
the POST endpoint (8 integration); 14 new editor tests across
EmptyState, FileListItem, ProjectView, and EditorApp routing.

Out of scope (deferred to later milestones): file hashing, media
metadata reading, transcript pipeline, playback, clip authoring.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

- [ ] **Step 3: Push main**

```bash
git push origin main
```

- [ ] **Step 4: Delete the merged branch (local + remote)**

```bash
git push origin --delete milestone-1-folder-open
git branch -d milestone-1-folder-open
```

- [ ] **Step 5: Verify final state**

```bash
git log --oneline --graph -10
```

Expected: a merge commit at the tip of main, with the milestone-1 commits visible as a side branch in the graph.

---

## What this milestone leaves you with

- The first interactive surface of BWC Clipper: the user can navigate the desktop, pick a case folder, and see what's inside.
- A real engine API endpoint pattern (`POST` with JSON body, error mapping to status codes) that the rest of the project will extend.
- Component boundaries (`EmptyState`, `ProjectView`, `FileListItem`) that Milestone 2 onwards will compose with the player + transcript + timeline.
- The first time `.bwcclipper/` exists on disk — Milestone 2 will populate it with per-source cache subdirectories.

## Next milestone (preview, not part of this plan)

**Milestone 2: Audio extraction + preprocessing.** Bundled ffmpeg auto-download (Depo Clipper pattern). New engine module `engine/pipeline/extract.py` that runs ffmpeg to extract per-track 16 kHz mono WAVs from a media file into the source's per-file cache subdirectory. Loudness normalize + compress (per brief §4.2). Pipeline state file `pipeline-state.json` that tracks per-stage completion. UI: progress indicator on each FileListItem ("extracting..." / "normalized" / "ready").
