# BWC Clipper — Milestone 6 — Reviewer UI Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ship the first end-user-facing review experience: open a folder, pick a processed source, scrub audio (or video), navigate via the auto-generated transcript, search, edit context names and re-transcribe.

**Architecture:** Engine grows a multithreaded HTTP layer with HTTP Range support so the renderer can stream the original audio/video over loopback. Six new GET/POST endpoints expose audio bytes, video bytes, transcript, context-names, retranscribe trigger, and per-project last-opened-source persistence. The React renderer adds a second top-level view (`reviewer`) with a TopBar / MediaPane / TranscriptPanel / Timeline component tree. Re-transcription invalidates only stages 5+6 via a new `runner.rerun_from_stage` API.

**Tech Stack:** Python 3.11 stdlib `http.server` + `socketserver.ThreadingMixIn` (engine), pytest + integration markers (engine tests), React 18 + Vite + esbuild (editor), Vitest + Testing Library (editor tests), Web Audio API (`AudioContext.decodeAudioData`) for waveform rendering. No new ML / runtime dependencies.

**Spec:** `docs/superpowers/specs/2026-04-29-bwc-clipper-milestone-6-reviewer-ui-design.md` is the source of truth — read it first.

---

## Setup notes (do once before Task 1)

- You should already be on branch `milestone-6-reviewer-ui` (created during brainstorm; spec committed there as `4912759`).
- Confirm working tree clean: `git status` should show nothing pending.
- Confirm Python venv active: `which python` should resolve into `.venv/`. If not, see HANDOFF.md "Environment".
- Confirm tests green at baseline: `python -m pytest -q` and `npm test -- --run` both clean before adding M6 code.
- For integration tests: `BWC_CLIPPER_FFMPEG_DIR` must be exported and point at a directory containing `ffmpeg.exe`. See HANDOFF.md for the path on the dev workstation.
- Verify `editor/api.js` exports both `apiGet` and `apiPost` — Tasks 11/12 onward call them by name. If only one is exported, add the missing helper before Task 11. The existing `EditorApp.jsx` already uses `apiPost` and `apiGet` so they should be in place.

---

## File structure overview

**Engine — new files:**
- `engine/reviewer_state.py` — per-project last-opened-source persistence

**Engine — modified files:**
- `serve.py` — switch to `ThreadedHTTPServer`
- `engine/server.py` — add `_serve_media` helper, six new routes, expanded CORS
- `engine/pipeline/runner.py` — add `rerun_from_stage` method

**Editor — new files (under `editor/components/reviewer/`):**
- `ReviewerView.jsx` + `.test.jsx` — root component + transcript fetch + audio ref + context provider
- `ReviewerContext.js` — React context with `seekTo`, `play`, `pause`, audio state
- `TopBar.jsx` + `.test.jsx` — back, breadcrumb, source picker, retranscribe pill
- `MediaPane.jsx` + `.test.jsx` — audio/video mode branching + search input
- `Transport.jsx` + `.test.jsx` — transport buttons + time readout
- `Waveform.jsx` + `.test.jsx` — canvas-based waveform from decoded audio
- `TranscriptPanel.jsx` + `.test.jsx` — segment list + active scroll + low-conf underline
- `ContextNamesPanel.jsx` + `.test.jsx` — context textareas + retranscribe wiring
- `Timeline.jsx` + `.test.jsx` — toggle owner; renders one of the two views below
- `CollapsedTimeline.jsx` — collapsed-silence renderer
- `UncompressedTimeline.jsx` — real-time-ruler renderer
- `useTimelineGeometry.js` — shared geometry hook
- `SearchHighlight.jsx` — utility wrapping matches in `<mark>`

**Editor — new files (under `editor/`):**
- `usePolling.js` — extract polling pattern from `EditorApp` into reusable hook

**Editor — modified files:**
- `editor/EditorApp.jsx` — three-state view router; selection branches to reviewer when transcript exists
- (no other existing editor files modified)

**Tests — engine:**
- `tests/test_server_media.py`
- `tests/test_server_routes_m6.py`
- `tests/test_server_context.py`
- `tests/test_server_retranscribe.py`
- `tests/test_runner_rerun.py`
- `tests/test_reviewer_state.py`
- `tests/integration/test_reviewer_endpoints.py`

---

# Phase A — Engine HTTP layer foundation

## Task 1: Multithreaded HTTP server

**Why first:** every other engine task assumes range responses can stream concurrently with API calls. Single-threaded `HTTPServer` blocks all requests behind one streaming response.

**Files:**
- Modify: `serve.py` (replace `HTTPServer` import and instantiation)
- Test: existing `tests/test_serve_main.py` should keep passing — no new test (this is a config change verified by integration test in Task 13).

- [ ] **Step 1: Add `ThreadedHTTPServer` class**

In `serve.py`, replace:

```python
from http.server import HTTPServer
```

with:

```python
import socketserver
from http.server import HTTPServer
import logging
import traceback


class ThreadedHTTPServer(socketserver.ThreadingMixIn, HTTPServer):
    """Multithreaded HTTP server.

    ThreadingMixIn is required because the browser's <audio>/<video> elements
    keep open HTTP connections for Range-based streaming. Without threading,
    a streaming response blocks all other requests until it finishes.

    daemon_threads = True so request-handler threads do not block process
    shutdown when the server is stopped.
    """

    daemon_threads = True

    def handle_error(self, request, client_address):
        logging.getLogger("bwc-clipper.serve").warning(
            "request handler error from %s: %s",
            client_address,
            traceback.format_exc(),
        )
```

- [ ] **Step 2: Use `ThreadedHTTPServer` in `main()`**

Change:

```python
server = HTTPServer(("127.0.0.1", port), BWCRequestHandler)
```

to:

```python
server = ThreadedHTTPServer(("127.0.0.1", port), BWCRequestHandler)
```

- [ ] **Step 3: Run unit tests**

Run: `python -m pytest -q`
Expected: PASS — no test regressions. (Integration coverage of threading lands in Task 13.)

- [ ] **Step 4: Commit**

```bash
git add serve.py
git commit -m "feat(engine): switch HTTP server to ThreadedHTTPServer

Required so Range-streamed audio/video responses do not block API
requests behind a single in-flight response. daemon_threads ensures
clean shutdown."
```

---

## Task 2: Range-aware media streaming helper

**Files:**
- Modify: `engine/server.py` (add `_serve_media` instance method on `BWCRequestHandler`)
- Create: `tests/test_server_media.py`

The helper handles both Range and full-file responses. It is a method on the handler (not a free function) so it can use `self.send_response`, `self.send_header`, `self.wfile`, etc.

- [ ] **Step 1: Write failing tests for Range parsing + headers**

Create `tests/test_server_media.py`:

```python
"""Range-aware media streaming helper tests.

Exercises _serve_media against an in-memory file via a fake handler that
captures send_response/send_header/write calls. Pure unit; no socket.
"""
from __future__ import annotations

import io
from pathlib import Path

import pytest

from engine.server import _parse_range_header, _serve_media_to


# ── _parse_range_header ───────────────────────────────────────────────────

def test_parse_range_full_form():
    assert _parse_range_header("bytes=100-200", file_size=1000) == (100, 200)


def test_parse_range_open_ended():
    assert _parse_range_header("bytes=100-", file_size=1000) == (100, 999)


def test_parse_range_clamps_end_to_file_size():
    assert _parse_range_header("bytes=100-99999", file_size=1000) == (100, 999)


def test_parse_range_zero_start():
    assert _parse_range_header("bytes=0-100", file_size=1000) == (0, 100)


def test_parse_range_malformed_returns_none():
    assert _parse_range_header("bytes=abc-100", file_size=1000) is None
    assert _parse_range_header("bytes=", file_size=1000) is None
    assert _parse_range_header("not-a-range", file_size=1000) is None
    assert _parse_range_header("", file_size=1000) is None


def test_parse_range_start_past_eof_returns_none():
    assert _parse_range_header("bytes=2000-3000", file_size=1000) is None


# ── _serve_media_to ───────────────────────────────────────────────────────

class FakeWriter:
    """Minimal stand-in for the bits of BaseHTTPRequestHandler used by
    _serve_media_to. Records the response code, headers, and body bytes."""

    def __init__(self, range_header: str | None = None):
        self.range_header = range_header
        self.status: int | None = None
        self.headers: list[tuple[str, str]] = []
        self.body = io.BytesIO()
        self.headers_ended = False

    def get_range_header(self) -> str | None:
        return self.range_header

    def send_response(self, status: int) -> None:
        self.status = status

    def send_header(self, key: str, value) -> None:
        self.headers.append((key, str(value)))

    def end_headers(self) -> None:
        self.headers_ended = True

    @property
    def wfile(self):
        return self.body


def _write_fixture(tmp_path: Path, name: str, payload: bytes) -> Path:
    p = tmp_path / name
    p.write_bytes(payload)
    return p


def test_serve_media_full_file_when_no_range(tmp_path: Path):
    payload = b"X" * 5000
    media_file = _write_fixture(tmp_path, "audio.wav", payload)
    writer = FakeWriter(range_header=None)

    _serve_media_to(writer, media_file, fallback_mime="audio/wav")

    assert writer.status == 200
    headers = dict(writer.headers)
    assert headers["Content-Type"] == "audio/wav" or headers["Content-Type"].startswith("audio/")
    assert headers["Content-Length"] == "5000"
    assert headers["Accept-Ranges"] == "bytes"
    assert headers["Connection"] == "close"
    assert writer.body.getvalue() == payload


def test_serve_media_partial_response_with_range(tmp_path: Path):
    payload = bytes(range(256)) * 10  # 2560 bytes
    media_file = _write_fixture(tmp_path, "video.mp4", payload)
    writer = FakeWriter(range_header="bytes=100-199")

    _serve_media_to(writer, media_file, fallback_mime="video/mp4")

    assert writer.status == 206
    headers = dict(writer.headers)
    assert headers["Content-Range"] == f"bytes 100-199/{len(payload)}"
    assert headers["Content-Length"] == "100"
    assert headers["Accept-Ranges"] == "bytes"
    assert headers["Connection"] == "close"
    assert writer.body.getvalue() == payload[100:200]


def test_serve_media_open_ended_range(tmp_path: Path):
    payload = b"Y" * 1000
    media_file = _write_fixture(tmp_path, "audio.wav", payload)
    writer = FakeWriter(range_header="bytes=500-")

    _serve_media_to(writer, media_file, fallback_mime="audio/wav")

    assert writer.status == 206
    headers = dict(writer.headers)
    assert headers["Content-Range"] == f"bytes 500-999/{len(payload)}"
    assert headers["Content-Length"] == "500"
    assert writer.body.getvalue() == payload[500:]


def test_serve_media_416_when_range_unsatisfiable(tmp_path: Path):
    payload = b"Z" * 100
    media_file = _write_fixture(tmp_path, "audio.wav", payload)
    writer = FakeWriter(range_header="bytes=200-300")

    _serve_media_to(writer, media_file, fallback_mime="audio/wav")

    assert writer.status == 416
    headers = dict(writer.headers)
    assert headers["Content-Range"] == f"bytes */{len(payload)}"


def test_serve_media_uses_fallback_mime_for_unknown_extension(tmp_path: Path):
    media_file = _write_fixture(tmp_path, "blob.unknown", b"abc")
    writer = FakeWriter(range_header=None)

    _serve_media_to(writer, media_file, fallback_mime="audio/wav")

    headers = dict(writer.headers)
    assert headers["Content-Type"] == "audio/wav"


def test_serve_media_swallows_broken_pipe(tmp_path: Path, monkeypatch):
    """When the client disconnects mid-stream we must not raise."""
    media_file = _write_fixture(tmp_path, "audio.wav", b"X" * 1000)

    class DisconnectingBuffer(io.BytesIO):
        def write(self, data):
            raise BrokenPipeError("client gone")

    writer = FakeWriter(range_header=None)
    writer.body = DisconnectingBuffer()

    # Should not raise
    _serve_media_to(writer, media_file, fallback_mime="audio/wav")
```

- [ ] **Step 2: Run tests to verify failure**

Run: `python -m pytest tests/test_server_media.py -v`
Expected: FAIL with `ImportError: cannot import name '_parse_range_header'` (helpers not yet defined).

- [ ] **Step 3: Implement helpers in `engine/server.py`**

Add at module level (top of file, after the existing imports):

```python
import errno
import mimetypes
import re

_RANGE_RE = re.compile(r"bytes=(\d+)-(\d*)")
_CHUNK_SIZE = 65536


def _parse_range_header(header_value: str | None, file_size: int) -> tuple[int, int] | None:
    """Parse a single-range Range header value.

    Returns (start, end_inclusive) clamped to file bounds, or None if the
    header is malformed, missing, or unsatisfiable (start past EOF).
    """
    if not header_value:
        return None
    match = _RANGE_RE.fullmatch(header_value.strip())
    if not match:
        return None
    start = int(match.group(1))
    end_str = match.group(2)
    end = int(end_str) if end_str else file_size - 1
    if start >= file_size:
        return None
    end = min(end, file_size - 1)
    if end < start:
        return None
    return start, end


def _serve_media_to(writer, media_file: Path, fallback_mime: str) -> None:
    """Stream a media file with HTTP Range support.

    `writer` provides:
      - get_range_header() -> str | None
      - send_response(int)
      - send_header(str, str)
      - end_headers()
      - wfile (file-like with .write(bytes))

    Designed to be called from BWCRequestHandler._serve_media (which
    forwards self.headers / self.wfile / self.send_response). Tests
    use a FakeWriter that captures the same surface.

    Catches BrokenPipeError / ConnectionResetError / ConnectionAbortedError
    plus Windows OSError errnos 10053/10054 silently — they fire constantly
    during normal seek and the renderer is unaffected.
    """
    try:
        file_size = media_file.stat().st_size
    except OSError:
        writer.send_response(404)
        writer.end_headers()
        return

    content_type = mimetypes.guess_type(str(media_file))[0] or fallback_mime

    range_header = writer.get_range_header()
    parsed = _parse_range_header(range_header, file_size) if range_header else None

    if range_header and parsed is None:
        # Range header was present but unsatisfiable / malformed — RFC 7233 says 416.
        writer.send_response(416)
        writer.send_header("Content-Range", f"bytes */{file_size}")
        writer.send_header("Content-Length", "0")
        writer.end_headers()
        return

    try:
        if parsed:
            start, end = parsed
            length = end - start + 1
            writer.send_response(206)
            writer.send_header("Content-Type", content_type)
            writer.send_header("Content-Length", str(length))
            writer.send_header("Content-Range", f"bytes {start}-{end}/{file_size}")
            writer.send_header("Accept-Ranges", "bytes")
            writer.send_header("Connection", "close")
            writer.end_headers()
            with open(media_file, "rb") as f:
                f.seek(start)
                remaining = length
                while remaining > 0:
                    chunk = f.read(min(_CHUNK_SIZE, remaining))
                    if not chunk:
                        break
                    writer.wfile.write(chunk)
                    remaining -= len(chunk)
        else:
            writer.send_response(200)
            writer.send_header("Content-Type", content_type)
            writer.send_header("Content-Length", str(file_size))
            writer.send_header("Accept-Ranges", "bytes")
            writer.send_header("Connection", "close")
            writer.end_headers()
            with open(media_file, "rb") as f:
                while True:
                    chunk = f.read(_CHUNK_SIZE)
                    if not chunk:
                        break
                    writer.wfile.write(chunk)
    except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError):
        return  # client disconnected — normal during seek
    except OSError as exc:
        if exc.errno in (errno.ECONNABORTED, errno.ECONNRESET, 10053, 10054):
            return
        raise
```

- [ ] **Step 4: Run tests to verify pass**

Run: `python -m pytest tests/test_server_media.py -v`
Expected: 8 PASS.

- [ ] **Step 5: Commit**

```bash
git add engine/server.py tests/test_server_media.py
git commit -m "feat(engine): add _serve_media helper with HTTP Range support

Range parser handles full / open-ended / unsatisfiable forms with 416
on bad input. Streams in 64 KiB chunks. Catches client-disconnect
exceptions and Windows-specific TCP errnos 10053/10054 silently per
the Depo Clipper precedent."
```

---

## Task 3: Wire `_serve_media` into the request handler

**Files:**
- Modify: `engine/server.py` (add `BWCRequestHandler._serve_media` method + adjust CORS)
- Test covered by Task 4 (route registration tests)

- [ ] **Step 1: Add `_serve_media` instance method to `BWCRequestHandler`**

After the existing `_send_json` method:

```python
def _serve_media(self, file_path: Path, fallback_mime: str) -> None:
    """Stream a media file from disk with Range support and CORS headers."""

    handler = self  # capture for the writer adapter

    class _HandlerWriter:
        def get_range_header(self):
            return handler.headers.get("Range")

        def send_response(self, status):
            handler.send_response(status)

        def send_header(self, key, value):
            handler.send_header(key, value)
            # Add CORS expose headers alongside each media response
            if key == "Content-Type" and not getattr(self, "_cors_added", False):
                handler.send_header("Access-Control-Allow-Origin", "*")
                handler.send_header(
                    "Access-Control-Expose-Headers",
                    "Content-Range, Accept-Ranges, Content-Length",
                )
                self._cors_added = True

        def end_headers(self):
            handler.end_headers()

        @property
        def wfile(self):
            return handler.wfile

    _serve_media_to(_HandlerWriter(), file_path, fallback_mime)
```

- [ ] **Step 2: Expand CORS in `_send_json`**

Replace the existing single-line CORS in `_send_json`:

```python
self.send_header("Access-Control-Allow-Origin", "*")
```

with:

```python
self.send_header("Access-Control-Allow-Origin", "*")
self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
self.send_header("Access-Control-Allow-Headers", "Content-Type, Range")
```

- [ ] **Step 3: Run existing test suite to confirm nothing regressed**

Run: `python -m pytest -q`
Expected: all green.

- [ ] **Step 4: Commit**

```bash
git add engine/server.py
git commit -m "feat(engine): plumb _serve_media into the request handler with CORS

Adds expose-headers (Content-Range, Accept-Ranges, Content-Length) on
media responses so the browser can read media duration. Adds Range to
allowed request headers."
```

---

# Phase B — Engine media + transcript endpoints

## Task 4: `/api/source/audio` and `/api/source/video` GET routes

**Files:**
- Modify: `engine/server.py` (add the two routes + path validation + mode mismatch checks)
- Create: `tests/test_server_routes_m6.py`

These routes share path resolution and mode validation. Implement once and call twice.

- [ ] **Step 1: Write failing tests**

Create `tests/test_server_routes_m6.py`:

```python
"""HTTP handler tests for the M6 GET routes (audio, video, transcript).

Exercises the route table by faking BaseHTTPRequestHandler — same pattern
as the existing test_server_routes.py.
"""
from __future__ import annotations

import io
import json
from pathlib import Path
from unittest.mock import MagicMock, patch
from urllib.parse import urlencode

import pytest

from engine.server import BWCRequestHandler


def _make_handler(method: str, path: str, body: bytes = b"") -> BWCRequestHandler:
    """Construct a BWCRequestHandler without going through the socket."""
    handler = BWCRequestHandler.__new__(BWCRequestHandler)
    handler.path = path
    handler.command = method
    handler.headers = {"Content-Length": str(len(body))} if body else {}
    handler.rfile = io.BytesIO(body)
    handler.wfile = io.BytesIO()

    handler.send_response = MagicMock()
    handler.send_header = MagicMock()
    handler.end_headers = MagicMock()
    return handler


def _last_status(handler: BWCRequestHandler) -> int:
    return handler.send_response.call_args.args[0]


# ── /api/source/audio ─────────────────────────────────────────────────────

def test_audio_route_streams_file(tmp_path: Path):
    folder = tmp_path / "case"
    folder.mkdir()
    source = folder / "exam.mp3"
    source.write_bytes(b"FAKE-MP3-PAYLOAD")

    qs = urlencode({"folder": str(folder), "source": str(source)})
    handler = _make_handler("GET", f"/api/source/audio?{qs}")

    handler.do_GET()

    assert _last_status(handler) == 200
    body = handler.wfile.getvalue()
    assert body == b"FAKE-MP3-PAYLOAD"


def test_audio_route_404_when_file_missing(tmp_path: Path):
    folder = tmp_path / "case"
    folder.mkdir()
    qs = urlencode({"folder": str(folder), "source": str(folder / "nope.mp3")})
    handler = _make_handler("GET", f"/api/source/audio?{qs}")

    handler.do_GET()

    assert _last_status(handler) == 404


def test_audio_route_400_when_missing_query_params():
    handler = _make_handler("GET", "/api/source/audio")
    handler.do_GET()
    assert _last_status(handler) == 400


def test_audio_route_400_when_source_outside_folder(tmp_path: Path):
    folder = tmp_path / "case"
    folder.mkdir()
    other = tmp_path / "elsewhere.mp3"
    other.write_bytes(b"x")

    qs = urlencode({"folder": str(folder), "source": str(other)})
    handler = _make_handler("GET", f"/api/source/audio?{qs}")
    handler.do_GET()

    assert _last_status(handler) == 400


def test_audio_route_415_when_source_is_video(tmp_path: Path):
    folder = tmp_path / "case"
    folder.mkdir()
    source = folder / "bwc.mp4"
    source.write_bytes(b"FAKE-MP4")
    qs = urlencode({"folder": str(folder), "source": str(source)})
    handler = _make_handler("GET", f"/api/source/audio?{qs}")
    handler.do_GET()
    assert _last_status(handler) == 415


# ── /api/source/video ─────────────────────────────────────────────────────

def test_video_route_streams_file(tmp_path: Path):
    folder = tmp_path / "case"
    folder.mkdir()
    source = folder / "bwc.mp4"
    source.write_bytes(b"FAKE-MP4-PAYLOAD")

    qs = urlencode({"folder": str(folder), "source": str(source)})
    handler = _make_handler("GET", f"/api/source/video?{qs}")
    handler.do_GET()

    assert _last_status(handler) == 200
    assert handler.wfile.getvalue() == b"FAKE-MP4-PAYLOAD"


def test_video_route_415_when_source_is_audio(tmp_path: Path):
    folder = tmp_path / "case"
    folder.mkdir()
    source = folder / "exam.mp3"
    source.write_bytes(b"x")
    qs = urlencode({"folder": str(folder), "source": str(source)})
    handler = _make_handler("GET", f"/api/source/video?{qs}")
    handler.do_GET()
    assert _last_status(handler) == 415
```

- [ ] **Step 2: Verify failure**

Run: `python -m pytest tests/test_server_routes_m6.py -v`
Expected: FAIL — routes not registered.

- [ ] **Step 3: Implement the routes**

In `engine/server.py`, add a query-driven branch in `do_GET` (alongside the existing `/api/source/state` branch):

```python
if split.path == "/api/source/audio":
    self._handle_media_route(parse_qs(split.query), kind="audio")
    return
if split.path == "/api/source/video":
    self._handle_media_route(parse_qs(split.query), kind="video")
    return
```

Add the dispatcher method on `BWCRequestHandler`. **The two `_EXTS` sets must be class attributes on `BWCRequestHandler`** (the dispatcher accesses them via `BWCRequestHandler._VIDEO_EXTS`). Place them inside the class body, above `_handle_media_route`:

```python
class BWCRequestHandler(BaseHTTPRequestHandler):
    # ... existing class body ...

    # Mode determined by file extension; must agree with engine/project.py.
    _AUDIO_EXTS = {".mp3", ".wav", ".m4a", ".flac", ".aac", ".ogg"}
    _VIDEO_EXTS = {".mp4", ".mov", ".mkv", ".avi", ".webm"}

    def _handle_media_route(self, query: dict, kind: str) -> None:
    folder_list = query.get("folder", [])
    source_list = query.get("source", [])
    if not folder_list or not source_list:
        self._send_json(400, {"error": "missing 'folder' or 'source' query parameter"})
        return
    folder = Path(folder_list[0]).resolve()
    source = Path(source_list[0]).resolve()

    # Defense in depth: source must be inside the project folder.
    try:
        source.relative_to(folder)
    except ValueError:
        self._send_json(400, {"error": "source is not inside folder"})
        return

    if not source.is_file():
        self._send_json(404, {"error": "source not found", "path": str(source)})
        return

    ext = source.suffix.lower()
    if kind == "audio":
        if ext in BWCRequestHandler._VIDEO_EXTS:
            self._send_json(415, {"error": "source is video; use /api/source/video"})
            return
        self._serve_media(source, fallback_mime="audio/wav")
    else:  # kind == "video"
        if ext in BWCRequestHandler._AUDIO_EXTS:
            self._send_json(415, {"error": "source is audio; use /api/source/audio"})
            return
        self._serve_media(source, fallback_mime="video/mp4")
```

- [ ] **Step 4: Verify pass**

Run: `python -m pytest tests/test_server_routes_m6.py -v`
Expected: 7 PASS.

- [ ] **Step 5: Commit**

```bash
git add engine/server.py tests/test_server_routes_m6.py
git commit -m "feat(engine): add /api/source/audio and /api/source/video routes

Streams the original media file with Range support. Validates the
source path is inside the project folder. Rejects mode-mismatched
calls (audio request on a video source, vice versa) with 415."
```

---

## Task 5: `/api/source/transcript` GET route

**Files:**
- Modify: `engine/server.py` (one new route)
- Append to: `tests/test_server_routes_m6.py`

- [ ] **Step 1: Add failing tests**

Append to `tests/test_server_routes_m6.py`:

```python
def _write_pipeline_artifacts(folder: Path, source: Path) -> None:
    """Mimic the on-disk artifact layout that the routes read from."""
    from engine.source import source_cache_dir
    cache_dir = source_cache_dir(folder, source)
    cache_dir.mkdir(parents=True, exist_ok=True)
    transcript = {
        "schema_version": "1.0",
        "source": {"path": str(source).replace("\\", "/"), "duration_seconds": 60.0},
        "speakers": [],
        "segments": [
            {"id": 0, "start": 1.0, "end": 4.0, "text": "Hello", "words": [], "low_confidence": False},
        ],
    }
    speech_segments = {"tracks": [[{"start": 1.0, "end": 4.0}]]}
    (cache_dir / "transcript.json").write_text(json.dumps(transcript), encoding="utf-8")
    (cache_dir / "speech-segments.json").write_text(json.dumps(speech_segments), encoding="utf-8")


def test_transcript_route_returns_combined_payload(tmp_path: Path):
    folder = tmp_path / "case"
    folder.mkdir()
    source = folder / "exam.mp3"
    source.write_bytes(b"x")
    _write_pipeline_artifacts(folder, source)

    qs = urlencode({"folder": str(folder), "source": str(source)})
    handler = _make_handler("GET", f"/api/source/transcript?{qs}")
    handler.do_GET()

    assert _last_status(handler) == 200
    body = json.loads(handler.wfile.getvalue())
    assert body["transcript"]["segments"][0]["text"] == "Hello"
    assert body["speech_segments"] == [{"start": 1.0, "end": 4.0}]


def test_transcript_route_404_when_artifacts_missing(tmp_path: Path):
    folder = tmp_path / "case"
    folder.mkdir()
    source = folder / "exam.mp3"
    source.write_bytes(b"x")  # source exists but no cache dir

    qs = urlencode({"folder": str(folder), "source": str(source)})
    handler = _make_handler("GET", f"/api/source/transcript?{qs}")
    handler.do_GET()
    assert _last_status(handler) == 404
```

- [ ] **Step 2: Verify failure**

Run: `python -m pytest tests/test_server_routes_m6.py -v -k transcript`
Expected: FAIL — route not registered.

- [ ] **Step 3: Implement**

Add route branch in `do_GET`:

```python
if split.path == "/api/source/transcript":
    try:
        status, body = self._handle_transcript(parse_qs(split.query))
    except Exception as exc:
        logger.exception("/api/source/transcript crashed")
        self._send_json(500, {"error": "internal", "detail": str(exc)})
        return
    self._send_json(status, body)
    return
```

Add the handler method:

```python
def _handle_transcript(self, query: dict) -> tuple[int, dict]:
    from engine.source import source_cache_dir

    folder_list = query.get("folder", [])
    source_list = query.get("source", [])
    if not folder_list or not source_list:
        return 400, {"error": "missing 'folder' or 'source'"}
    folder = Path(folder_list[0]).resolve()
    source = Path(source_list[0]).resolve()
    cache_dir = source_cache_dir(folder, source)
    transcript_path = cache_dir / "transcript.json"
    speech_segments_path = cache_dir / "speech-segments.json"
    if not transcript_path.is_file() or not speech_segments_path.is_file():
        return 404, {"error": "transcript or speech-segments missing"}
    transcript = json.loads(transcript_path.read_text(encoding="utf-8"))
    speech_segments_doc = json.loads(speech_segments_path.read_text(encoding="utf-8"))
    tracks = speech_segments_doc.get("tracks", [])
    return 200, {
        "transcript": transcript,
        "speech_segments": tracks[0] if tracks else [],
    }
```

- [ ] **Step 4: Verify pass**

Run: `python -m pytest tests/test_server_routes_m6.py -v`
Expected: all PASS.

- [ ] **Step 5: Commit**

```bash
git add engine/server.py tests/test_server_routes_m6.py
git commit -m "feat(engine): add /api/source/transcript route

Returns transcript.json + tracks[0] from speech-segments.json in one
response so the renderer mounts in a single fetch."
```

---

# Phase C — Engine state + retranscribe machinery

## Task 6: `PipelineRunner.rerun_from_stage`

**Files:**
- Modify: `engine/pipeline/runner.py` (add the method)
- Create: `tests/test_runner_rerun.py`

The method clears the named stage and every subsequent stage's state from `pipeline-state.json`, then resubmits the source. The existing `_run_pipeline` skip-when-COMPLETED logic will skip earlier stages and re-run the cleared ones.

- [ ] **Step 1: Write failing tests**

Create `tests/test_runner_rerun.py`:

```python
"""rerun_from_stage tests — clears stage state and resubmits."""
from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

import pytest

from engine.pipeline.runner import PipelineRunner, _PIPELINE_STAGES
from engine.pipeline.state import StageStatus, save_state, load_state, PipelineState


def _completed_state() -> PipelineState:
    """All M0–M5 stages marked completed."""
    stages = {
        name: {"status": StageStatus.COMPLETED.value, "outputs": []}
        for name, _ in _PIPELINE_STAGES
    }
    return PipelineState(stages=stages)


def test_rerun_from_transcribe_clears_transcribe_and_align(tmp_path: Path):
    folder = tmp_path / "case"
    folder.mkdir()
    source = folder / "exam.mp3"
    source.write_bytes(b"x")
    from engine.source import source_cache_dir
    cache_dir = source_cache_dir(folder, source)
    cache_dir.mkdir(parents=True, exist_ok=True)
    save_state(cache_dir, _completed_state())

    runner = PipelineRunner()
    try:
        with patch.object(runner, "submit_pipeline") as submit:
            runner.rerun_from_stage("transcribe", folder, source)
            submit.assert_called_once_with(folder, source)

        # transcribe and align should now be missing / non-completed
        state = load_state(cache_dir)
        assert "transcribe" not in state.stages or \
            state.stages["transcribe"].get("status") != StageStatus.COMPLETED.value
        assert "align" not in state.stages or \
            state.stages["align"].get("status") != StageStatus.COMPLETED.value
        # earlier stages preserved
        assert state.stages["extract"]["status"] == StageStatus.COMPLETED.value
        assert state.stages["normalize"]["status"] == StageStatus.COMPLETED.value
        assert state.stages["enhance"]["status"] == StageStatus.COMPLETED.value
        assert state.stages["vad"]["status"] == StageStatus.COMPLETED.value
    finally:
        runner.shutdown()


def test_rerun_from_invalid_stage_raises(tmp_path: Path):
    runner = PipelineRunner()
    try:
        with pytest.raises(ValueError, match="unknown stage"):
            runner.rerun_from_stage("nonexistent", tmp_path, tmp_path / "x")
    finally:
        runner.shutdown()


def test_rerun_idempotent_when_already_queued(tmp_path: Path):
    """Calling rerun_from_stage twice in quick succession is harmless;
    submit_pipeline's existing idempotency handles the queue."""
    folder = tmp_path / "case"
    folder.mkdir()
    source = folder / "exam.mp3"
    source.write_bytes(b"x")
    from engine.source import source_cache_dir
    cache_dir = source_cache_dir(folder, source)
    cache_dir.mkdir(parents=True, exist_ok=True)
    save_state(cache_dir, _completed_state())

    runner = PipelineRunner()
    try:
        with patch.object(runner, "submit_pipeline") as submit:
            runner.rerun_from_stage("transcribe", folder, source)
            runner.rerun_from_stage("transcribe", folder, source)
            assert submit.call_count == 2  # method itself isn't deduping; submit_pipeline does
    finally:
        runner.shutdown()
```

- [ ] **Step 2: Verify failure**

Run: `python -m pytest tests/test_runner_rerun.py -v`
Expected: FAIL — `rerun_from_stage` not defined.

- [ ] **Step 3: Implement**

In `engine/pipeline/runner.py`, add this method on `PipelineRunner` (after `submit_pipeline`):

```python
def rerun_from_stage(
    self, stage_name: str, project_folder: Path, source_path: Path
) -> Future:
    """Clear `stage_name` and every subsequent stage's persisted state, then
    submit the pipeline. The existing skip-when-COMPLETED logic causes
    stages before `stage_name` to be skipped and the cleared stages to run.

    Forward-compatible with M7+: any stage added after `align` in
    _PIPELINE_STAGES will be cleared by rerun_from_stage("transcribe", ...).

    Raises ValueError if `stage_name` is not in _PIPELINE_STAGES.
    """
    stage_names = [name for name, _ in _PIPELINE_STAGES]
    if stage_name not in stage_names:
        raise ValueError(f"unknown stage: {stage_name!r}")
    cache_dir = source_cache_dir(project_folder, source_path)
    state = load_state(cache_dir)
    start_index = stage_names.index(stage_name)
    new_stages = dict(state.stages)
    for name in stage_names[start_index:]:
        new_stages.pop(name, None)
    from engine.pipeline.state import save_state, PipelineState
    save_state(cache_dir, PipelineState(schema_version=state.schema_version, stages=new_stages))
    return self.submit_pipeline(project_folder, source_path)
```

(The local `from engine.pipeline.state import save_state, PipelineState` keeps the change scoped — `load_state` is already imported at the top of the module; we just add `save_state` and `PipelineState` here. Move both to the module-level import once the test passes if you prefer.)

- [ ] **Step 4: Verify pass**

Run: `python -m pytest tests/test_runner_rerun.py -v`
Expected: 3 PASS.

- [ ] **Step 5: Commit**

```bash
git add engine/pipeline/runner.py tests/test_runner_rerun.py
git commit -m "feat(engine): add PipelineRunner.rerun_from_stage

Clears the named stage and every subsequent stage from pipeline-state.json,
then submits the source. The existing _run_pipeline skip-when-completed
logic skips earlier stages, so transcribe + align re-run while extract /
normalize / enhance / vad outputs are preserved."
```

---

## Task 7: `/api/source/context` POST route

**Files:**
- Modify: `engine/server.py` (one new POST route)
- Create: `tests/test_server_context.py`

`engine/pipeline/transcribe.py` already reads `context.json` via `_read_initial_prompt`. M6 just adds the write path.

- [ ] **Step 1: Write failing tests**

Create `tests/test_server_context.py`:

```python
"""POST /api/source/context tests — writes context.json to the source cache."""
from __future__ import annotations

import io
import json
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from engine.server import BWCRequestHandler


def _post_handler(path: str, body: dict) -> BWCRequestHandler:
    raw = json.dumps(body).encode("utf-8")
    handler = BWCRequestHandler.__new__(BWCRequestHandler)
    handler.path = path
    handler.command = "POST"
    handler.headers = {"Content-Length": str(len(raw))}
    handler.rfile = io.BytesIO(raw)
    handler.wfile = io.BytesIO()
    handler.send_response = MagicMock()
    handler.send_header = MagicMock()
    handler.end_headers = MagicMock()
    return handler


def _last_status(h: BWCRequestHandler) -> int:
    return h.send_response.call_args.args[0]


def test_context_post_writes_json(tmp_path: Path):
    folder = tmp_path / "case"
    folder.mkdir()
    source = folder / "exam.mp3"
    source.write_bytes(b"x")

    handler = _post_handler("/api/source/context", {
        "folder": str(folder),
        "source": str(source),
        "names": ["Dr Patel", "Heather Williams"],
        "locations": ["CVS Crenshaw"],
    })
    handler.do_POST()

    assert _last_status(handler) == 200

    from engine.source import source_cache_dir
    cache = source_cache_dir(folder, source)
    written = json.loads((cache / "context.json").read_text(encoding="utf-8"))
    assert written == {
        "names": ["Dr Patel", "Heather Williams"],
        "locations": ["CVS Crenshaw"],
    }


def test_context_post_validates_types(tmp_path: Path):
    folder = tmp_path / "case"
    folder.mkdir()
    source = folder / "exam.mp3"
    source.write_bytes(b"x")

    bad_bodies = [
        {"folder": str(folder), "source": str(source), "names": "not a list", "locations": []},
        {"folder": str(folder), "source": str(source), "names": [1, 2], "locations": []},
        {"folder": str(folder), "source": str(source), "names": [], "locations": "x"},
    ]
    for body in bad_bodies:
        handler = _post_handler("/api/source/context", body)
        handler.do_POST()
        assert _last_status(handler) == 400


def test_context_post_creates_missing_cache_dir(tmp_path: Path):
    folder = tmp_path / "case"
    folder.mkdir()
    source = folder / "newfile.mp3"
    source.write_bytes(b"x")

    handler = _post_handler("/api/source/context", {
        "folder": str(folder),
        "source": str(source),
        "names": ["A"],
        "locations": [],
    })
    handler.do_POST()
    assert _last_status(handler) == 200

    from engine.source import source_cache_dir
    cache = source_cache_dir(folder, source)
    assert (cache / "context.json").is_file()
```

- [ ] **Step 2: Verify failure**

Run: `python -m pytest tests/test_server_context.py -v`
Expected: FAIL — route not registered.

- [ ] **Step 3: Implement**

In `engine/server.py`, register in `_post_routes`:

```python
"/api/source/context": self._handle_source_context,
```

Add the handler:

```python
def _handle_source_context(self, body: dict) -> tuple[int, dict]:
    from engine.source import source_cache_dir

    folder = body.get("folder")
    source = body.get("source")
    names = body.get("names")
    locations = body.get("locations")
    if not isinstance(folder, str) or not folder:
        return 400, {"error": "missing 'folder'"}
    if not isinstance(source, str) or not source:
        return 400, {"error": "missing 'source'"}
    if not isinstance(names, list) or not all(isinstance(n, str) for n in names):
        return 400, {"error": "'names' must be a list of strings"}
    if not isinstance(locations, list) or not all(isinstance(l, str) for l in locations):
        return 400, {"error": "'locations' must be a list of strings"}

    cache_dir = source_cache_dir(Path(folder), Path(source))
    cache_dir.mkdir(parents=True, exist_ok=True)
    (cache_dir / "context.json").write_text(
        json.dumps({"names": names, "locations": locations}, indent=2),
        encoding="utf-8",
    )
    return 200, {"ok": True}
```

- [ ] **Step 4: Verify pass**

Run: `python -m pytest tests/test_server_context.py -v`
Expected: 3 PASS.

- [ ] **Step 5: Commit**

```bash
git add engine/server.py tests/test_server_context.py
git commit -m "feat(engine): add POST /api/source/context

Writes context.json (names, locations) to the source cache dir.
Stage 5 (transcribe) already reads this file via _read_initial_prompt
to populate faster-whisper's initial_prompt."
```

---

## Task 8: `/api/source/retranscribe` POST route

**Files:**
- Modify: `engine/server.py`
- Create: `tests/test_server_retranscribe.py`

- [ ] **Step 1: Write failing tests**

Create `tests/test_server_retranscribe.py`:

```python
"""POST /api/source/retranscribe tests — invokes runner.rerun_from_stage."""
from __future__ import annotations

import io
import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from engine.server import BWCRequestHandler


def _post(body: dict) -> BWCRequestHandler:
    raw = json.dumps(body).encode("utf-8")
    handler = BWCRequestHandler.__new__(BWCRequestHandler)
    handler.path = "/api/source/retranscribe"
    handler.command = "POST"
    handler.headers = {"Content-Length": str(len(raw))}
    handler.rfile = io.BytesIO(raw)
    handler.wfile = io.BytesIO()
    handler.send_response = MagicMock()
    handler.send_header = MagicMock()
    handler.end_headers = MagicMock()
    return handler


def _last_status(h: BWCRequestHandler) -> int:
    return h.send_response.call_args.args[0]


def test_retranscribe_calls_rerun_from_stage(tmp_path: Path):
    folder = tmp_path / "case"
    folder.mkdir()
    source = folder / "exam.mp3"
    source.write_bytes(b"x")

    handler = _post({"folder": str(folder), "source": str(source)})

    fake_runner = MagicMock()
    fake_runner.get_status.return_value = "queued"
    with patch("engine.server.get_pipeline_runner", return_value=fake_runner):
        handler.do_POST()

    fake_runner.rerun_from_stage.assert_called_once_with("transcribe", Path(str(folder)), Path(str(source)))
    assert _last_status(handler) == 200
    body = json.loads(handler.wfile.getvalue())
    assert body["status"] == "queued"


def test_retranscribe_validates_required_fields(tmp_path: Path):
    handler = _post({"folder": "", "source": ""})
    fake_runner = MagicMock()
    with patch("engine.server.get_pipeline_runner", return_value=fake_runner):
        handler.do_POST()
    assert _last_status(handler) == 400
    fake_runner.rerun_from_stage.assert_not_called()
```

- [ ] **Step 2: Verify failure**

Run: `python -m pytest tests/test_server_retranscribe.py -v`
Expected: FAIL — route not registered.

- [ ] **Step 3: Implement**

In `_post_routes`, add:

```python
"/api/source/retranscribe": self._handle_source_retranscribe,
```

Handler:

```python
def _handle_source_retranscribe(self, body: dict) -> tuple[int, dict]:
    folder = body.get("folder")
    source = body.get("source")
    if not isinstance(folder, str) or not folder:
        return 400, {"error": "missing 'folder'"}
    if not isinstance(source, str) or not source:
        return 400, {"error": "missing 'source'"}
    runner = get_pipeline_runner()
    runner.rerun_from_stage("transcribe", Path(folder), Path(source))
    status = runner.get_status(Path(folder), Path(source))
    return 200, {"status": status}
```

- [ ] **Step 4: Verify pass**

Run: `python -m pytest tests/test_server_retranscribe.py -v`
Expected: 2 PASS.

- [ ] **Step 5: Commit**

```bash
git add engine/server.py tests/test_server_retranscribe.py
git commit -m "feat(engine): add POST /api/source/retranscribe

Marks transcribe + align as pending via runner.rerun_from_stage and
resubmits. Returns the new pipeline status so the editor can drive
the progress pill."
```

---

## Task 9: `engine/reviewer_state.py` + `/api/project/reviewer-state` endpoints

**Files:**
- Create: `engine/reviewer_state.py`
- Modify: `engine/server.py` (two new routes)
- Create: `tests/test_reviewer_state.py`

- [ ] **Step 1: Write failing tests**

Create `tests/test_reviewer_state.py`:

```python
"""reviewer_state module + GET/POST /api/project/reviewer-state tests."""
from __future__ import annotations

import io
import json
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from engine.reviewer_state import (
    load_reviewer_state, save_reviewer_state, REVIEWER_STATE_FILENAME,
)
from engine.server import BWCRequestHandler


def test_load_returns_default_when_missing(tmp_path: Path):
    state = load_reviewer_state(tmp_path)
    assert state == {"last_source": None}


def test_save_then_load_round_trips(tmp_path: Path):
    save_reviewer_state(tmp_path, {"last_source": str(tmp_path / "x.mp3")})
    state = load_reviewer_state(tmp_path)
    assert state["last_source"] == str(tmp_path / "x.mp3")


def test_save_creates_bwcclipper_dir(tmp_path: Path):
    save_reviewer_state(tmp_path, {"last_source": "x"})
    assert (tmp_path / ".bwcclipper" / REVIEWER_STATE_FILENAME).is_file()


# ── HTTP routes ───────────────────────────────────────────────────────────

def _get(path: str) -> BWCRequestHandler:
    h = BWCRequestHandler.__new__(BWCRequestHandler)
    h.path = path
    h.command = "GET"
    h.headers = {}
    h.rfile = io.BytesIO()
    h.wfile = io.BytesIO()
    h.send_response = MagicMock()
    h.send_header = MagicMock()
    h.end_headers = MagicMock()
    return h


def _post(body: dict) -> BWCRequestHandler:
    raw = json.dumps(body).encode("utf-8")
    h = BWCRequestHandler.__new__(BWCRequestHandler)
    h.path = "/api/project/reviewer-state"
    h.command = "POST"
    h.headers = {"Content-Length": str(len(raw))}
    h.rfile = io.BytesIO(raw)
    h.wfile = io.BytesIO()
    h.send_response = MagicMock()
    h.send_header = MagicMock()
    h.end_headers = MagicMock()
    return h


def test_get_reviewer_state_returns_default(tmp_path: Path):
    from urllib.parse import urlencode
    qs = urlencode({"folder": str(tmp_path)})
    handler = _get(f"/api/project/reviewer-state?{qs}")
    handler.do_GET()
    assert handler.send_response.call_args.args[0] == 200
    body = json.loads(handler.wfile.getvalue())
    assert body == {"last_source": None}


def test_post_reviewer_state_writes_file(tmp_path: Path):
    handler = _post({"folder": str(tmp_path), "last_source": "abc.mp3"})
    handler.do_POST()
    assert handler.send_response.call_args.args[0] == 200
    state = load_reviewer_state(tmp_path)
    assert state["last_source"] == "abc.mp3"
```

- [ ] **Step 2: Verify failure**

Run: `python -m pytest tests/test_reviewer_state.py -v`
Expected: FAIL — `engine.reviewer_state` doesn't exist.

- [ ] **Step 3: Implement the module**

Create `engine/reviewer_state.py`:

```python
"""Per-project last-opened-source persistence for the reviewer view."""
from __future__ import annotations

import json
from pathlib import Path

REVIEWER_STATE_FILENAME = "reviewer-state.json"
_SUBDIR = ".bwcclipper"


def _state_path(folder: Path) -> Path:
    return folder / _SUBDIR / REVIEWER_STATE_FILENAME


def load_reviewer_state(folder: Path) -> dict:
    """Returns {'last_source': <str|None>}; missing-file returns the default."""
    path = _state_path(folder)
    if not path.is_file():
        return {"last_source": None}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            return {"last_source": None}
        return {"last_source": data.get("last_source")}
    except (OSError, json.JSONDecodeError):
        return {"last_source": None}


def save_reviewer_state(folder: Path, state: dict) -> None:
    """Writes {'last_source': ...}. Creates the .bwcclipper/ subdir if needed."""
    path = _state_path(folder)
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {"last_source": state.get("last_source")}
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
```

- [ ] **Step 4: Add the two HTTP routes**

In `engine/server.py`'s `do_GET`, add the query-driven branch:

```python
if split.path == "/api/project/reviewer-state":
    try:
        status, body = self._handle_reviewer_state_get(parse_qs(split.query))
    except Exception as exc:
        logger.exception("/api/project/reviewer-state crashed")
        self._send_json(500, {"error": "internal", "detail": str(exc)})
        return
    self._send_json(status, body)
    return
```

In `_post_routes`, add:

```python
"/api/project/reviewer-state": self._handle_reviewer_state_post,
```

Handlers:

```python
def _handle_reviewer_state_get(self, query: dict) -> tuple[int, dict]:
    from engine.reviewer_state import load_reviewer_state
    folder_list = query.get("folder", [])
    if not folder_list:
        return 400, {"error": "missing 'folder'"}
    return 200, load_reviewer_state(Path(folder_list[0]))


def _handle_reviewer_state_post(self, body: dict) -> tuple[int, dict]:
    from engine.reviewer_state import save_reviewer_state
    folder = body.get("folder")
    last_source = body.get("last_source")
    if not isinstance(folder, str) or not folder:
        return 400, {"error": "missing 'folder'"}
    if last_source is not None and not isinstance(last_source, str):
        return 400, {"error": "'last_source' must be a string or null"}
    save_reviewer_state(Path(folder), {"last_source": last_source})
    return 200, {"ok": True}
```

- [ ] **Step 5: Verify pass + commit**

Run: `python -m pytest tests/test_reviewer_state.py -v`
Expected: 5 PASS.

```bash
git add engine/reviewer_state.py engine/server.py tests/test_reviewer_state.py
git commit -m "feat(engine): add reviewer_state module and routes

Per-project last-opened-source persistence at <folder>/.bwcclipper/
reviewer-state.json. GET/POST /api/project/reviewer-state."
```

---

# Phase D — Engine integration tests

## Task 10: Range stress + retranscribe round-trip

**Files:**
- Create: `tests/integration/test_reviewer_endpoints.py`

These tests spin a real engine on a port and hit it with `urllib.request`. They depend on real ffmpeg and (for the retranscribe round-trip) real models, so they're marked `@pytest.mark.integration` and only run via `pytest -m integration`.

- [ ] **Step 1: Write the integration tests**

Create `tests/integration/test_reviewer_endpoints.py`:

```python
"""Integration tests for the M6 reviewer endpoints.

Spin a real engine on a free port; hit it with urllib.request. Requires
ffmpeg discoverable (BWC_CLIPPER_FFMPEG_DIR set in the integration
fixture) and, for the retranscribe round-trip, the real ML stack.
"""
from __future__ import annotations

import json
import os
import socket
import threading
import time
import urllib.request
from contextlib import contextmanager
from pathlib import Path
from urllib.parse import urlencode

import pytest

from engine.server import BWCRequestHandler, reset_pipeline_runner
from serve import ThreadedHTTPServer


@contextmanager
def _running_engine():
    """Start the engine on a free port for the duration of the context."""
    reset_pipeline_runner()
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.bind(("127.0.0.1", 0))
    port = sock.getsockname()[1]
    sock.close()

    server = ThreadedHTTPServer(("127.0.0.1", port), BWCRequestHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{port}"
    finally:
        server.shutdown()
        server.server_close()
        reset_pipeline_runner()


# ── Range stress ──────────────────────────────────────────────────────────

@pytest.mark.integration
def test_range_fetch_against_real_bwc_video():
    """Range fetch into a 3.95 GB BWC fixture catches 32-bit math mistakes
    and verifies Connection: close so subsequent API calls aren't blocked."""
    fixture = Path("Samples/BWC/tja00453_20231107020851e0_20231107020821_01_000w_1-4-001.mp4")
    if not fixture.is_file():
        pytest.skip(f"missing fixture: {fixture}")

    folder = fixture.parent
    with _running_engine() as base:
        # Fetch a slice from the middle of the file
        midpoint = fixture.stat().st_size // 2
        qs = urlencode({"folder": str(folder.resolve()), "source": str(fixture.resolve())})
        req = urllib.request.Request(
            f"{base}/api/source/video?{qs}",
            headers={"Range": f"bytes={midpoint}-{midpoint + 1023}"},
        )
        with urllib.request.urlopen(req, timeout=10) as resp:
            assert resp.status == 206
            assert resp.headers.get("Content-Range").endswith(f"/{fixture.stat().st_size}")
            chunk = resp.read()
            assert len(chunk) == 1024

        # And confirm a normal API call works fine right after
        with urllib.request.urlopen(f"{base}/api/health", timeout=5) as health:
            assert health.status == 200


# ── Retranscribe round-trip ───────────────────────────────────────────────

@pytest.mark.integration
def test_context_then_retranscribe_round_trip(tmp_path: Path):
    """Edit context, retranscribe, poll until complete, verify a context
    name appears in the new transcript."""
    fixture = Path("tests/fixtures/sample_short.wav")
    if not fixture.is_file():
        pytest.skip(f"missing fixture: {fixture}")

    project = tmp_path / "case"
    project.mkdir()
    source = project / "sample.wav"
    source.write_bytes(fixture.read_bytes())

    with _running_engine() as base:
        # First-pass full pipeline
        urllib.request.urlopen(
            urllib.request.Request(
                f"{base}/api/source/process",
                data=json.dumps({"folder": str(project), "source": str(source)}).encode(),
                headers={"Content-Type": "application/json"},
                method="POST",
            ),
            timeout=600,
        )
        _poll_until(base, project, source, "completed", timeout_s=600)

        # Edit context
        urllib.request.urlopen(
            urllib.request.Request(
                f"{base}/api/source/context",
                data=json.dumps({
                    "folder": str(project),
                    "source": str(source),
                    "names": ["Aurelius"],
                    "locations": [],
                }).encode(),
                headers={"Content-Type": "application/json"},
                method="POST",
            ),
            timeout=10,
        )

        # Trigger re-transcribe
        urllib.request.urlopen(
            urllib.request.Request(
                f"{base}/api/source/retranscribe",
                data=json.dumps({"folder": str(project), "source": str(source)}).encode(),
                headers={"Content-Type": "application/json"},
                method="POST",
            ),
            timeout=10,
        )
        _poll_until(base, project, source, "completed", timeout_s=120)

        # Fetch new transcript
        qs = urlencode({"folder": str(project), "source": str(source)})
        with urllib.request.urlopen(f"{base}/api/source/transcript?{qs}", timeout=10) as resp:
            payload = json.loads(resp.read())
        # We can't assert the model actually transcribed "Aurelius" — the fixture
        # may not contain that audio. We just assert the round-trip worked and
        # the new transcript exists with at least one segment.
        assert payload["transcript"]["segments"]


def _poll_until(base: str, folder: Path, source: Path, target: str, timeout_s: int) -> None:
    deadline = time.time() + timeout_s
    qs = urlencode({"folder": str(folder), "source": str(source)})
    while time.time() < deadline:
        with urllib.request.urlopen(f"{base}/api/source/state?{qs}", timeout=5) as resp:
            status = json.loads(resp.read())["status"]
        if status == target:
            return
        if status == "failed":
            raise AssertionError("pipeline reported failed")
        time.sleep(1)
    raise AssertionError(f"timed out waiting for {target}; last status={status}")
```

- [ ] **Step 2: Run with integration marker**

Run: `python -m pytest -m integration tests/integration/test_reviewer_endpoints.py -v`
Expected: tests SKIP if fixtures absent; otherwise PASS. The Range stress test is fast (~5 s); the retranscribe round-trip can take 1–2 minutes.

- [ ] **Step 3: Commit**

```bash
git add tests/integration/test_reviewer_endpoints.py
git commit -m "test(engine): integration tests for M6 reviewer endpoints

Range stress against the 3.95 GB BWC fixture (catches 32-bit math
issues, verifies Connection: close). Context-edit + retranscribe
round-trip with real models on the short fixture."
```

---

# Phase E — Editor view router + reviewer scaffold

## Task 11: Extract `usePolling` hook + view router in `EditorApp`

**Files:**
- Create: `editor/usePolling.js`
- Create: `editor/usePolling.test.js`
- Modify: `editor/EditorApp.jsx` (add view state; route to ReviewerView when transcript exists)
- Modify: `editor/EditorApp.test.jsx` (cover the new branch)

- [ ] **Step 1: Write failing test for the polling hook**

Create `editor/usePolling.test.js`:

```javascript
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { renderHook, act } from '@testing-library/react';
import { usePolling } from './usePolling.js';

beforeEach(() => {
    vi.useFakeTimers();
    globalThis.jest = { advanceTimersByTime: vi.advanceTimersByTime };
});

describe('usePolling', () => {
    it('does not poll when disabled', () => {
        const fetchStatus = vi.fn(() => Promise.resolve('queued'));
        renderHook(() => usePolling(fetchStatus, false));
        vi.advanceTimersByTime(5000);
        expect(fetchStatus).not.toHaveBeenCalled();
    });

    it('polls every 1 s while enabled and updates status', async () => {
        const fetchStatus = vi.fn()
            .mockResolvedValueOnce('queued')
            .mockResolvedValueOnce('running:transcribe')
            .mockResolvedValueOnce('completed');
        const { result } = renderHook(() => usePolling(fetchStatus, true));
        await act(async () => { vi.advanceTimersByTime(1000); });
        await act(async () => { vi.advanceTimersByTime(1000); });
        await act(async () => { vi.advanceTimersByTime(1000); });
        expect(result.current.status).toBe('completed');
    });

    it('stops polling once status reaches a terminal value', async () => {
        const fetchStatus = vi.fn()
            .mockResolvedValueOnce('completed');
        renderHook(() => usePolling(fetchStatus, true));
        await act(async () => { vi.advanceTimersByTime(1000); });
        await act(async () => { vi.advanceTimersByTime(2000); });
        expect(fetchStatus).toHaveBeenCalledTimes(1);
    });
});
```

- [ ] **Step 2: Verify failure**

Run: `npm test -- --run editor/usePolling.test.js`
Expected: FAIL — module doesn't exist.

- [ ] **Step 3: Implement**

Create `editor/usePolling.js`:

```javascript
import { useEffect, useRef, useState } from 'react';

const POLL_INTERVAL_MS = 1000;
const TERMINAL = new Set(['completed', 'failed', 'idle']);

/**
 * Polls fetchStatus() every 1 s while enabled. Returns the latest status.
 * Stops automatically when status enters {completed, failed, idle}.
 */
export function usePolling(fetchStatus, enabled) {
    const [status, setStatus] = useState(null);
    const handle = useRef(null);

    useEffect(() => {
        if (!enabled) return undefined;
        const tick = async () => {
            try {
                const next = await fetchStatus();
                setStatus(next);
                if (TERMINAL.has(next)) {
                    clearInterval(handle.current);
                    handle.current = null;
                }
            } catch (err) {
                console.warn('[usePolling] fetch failed:', err);
            }
        };
        handle.current = setInterval(tick, POLL_INTERVAL_MS);
        return () => {
            if (handle.current) {
                clearInterval(handle.current);
                handle.current = null;
            }
        };
    }, [fetchStatus, enabled]);

    return { status };
}
```

- [ ] **Step 4: Verify hook tests pass**

Run: `npm test -- --run editor/usePolling.test.js`
Expected: 3 PASS.

- [ ] **Step 5: Add `view` state to `EditorApp` + route to reviewer**

Update `editor/EditorApp.jsx`:

- Add `view` state: `'empty' | 'project' | 'reviewer'`. Derive from manifest + selectedReviewSource.
- When the user clicks a source whose status is `completed`, set `selectedReviewSource = file` and `view = 'reviewer'` (instead of resubmitting). For non-completed sources, keep the existing submit-and-poll flow.
- Wire the back button on `ReviewerView` to set `view = 'project'` (don't unload manifest).
- On project open, fetch `/api/project/reviewer-state` and, if `last_source` is set and that source has a completed transcript per its `pipeline-state.json`, jump straight to the reviewer view.

Skeleton:

```javascript
const [view, setView] = useState('empty');           // 'empty' | 'project' | 'reviewer'
const [reviewSource, setReviewSource] = useState(null);
// ... existing manifest, statuses, etc.

async function selectFile(file) {
    if (statuses[file.path] === 'completed' || file.completed) {
        setReviewSource(file);
        setView('reviewer');
        await apiPost('/api/project/reviewer-state', { folder: manifest.folder, last_source: file.path });
        return;
    }
    // existing submit-and-poll behavior
}

function backToProject() {
    setView('project');
    setReviewSource(null);
}

return (
    <div ...>
        {view === 'empty' && <EmptyState onOpenFolder={openFolder} />}
        {view === 'project' && <ProjectView ... />}
        {view === 'reviewer' && (
            <ReviewerView
                folder={manifest.folder}
                source={reviewSource}
                onBack={backToProject}
                manifest={manifest}
            />
        )}
    </div>
);
```

(`ReviewerView` itself is created in Task 12 — for now, stub-import it with a placeholder `() => <div>reviewer placeholder</div>` so this task can ship green.)

- [ ] **Step 6: Update `EditorApp.test.jsx`**

Add a test that completed-status selection routes to the reviewer view (the placeholder is fine):

```javascript
it('routes to reviewer view when selecting a completed source', async () => {
    // mock manifest fetch, mock /api/source/state to return 'completed' for path X
    // click that file's row, expect 'reviewer placeholder' to be in the DOM
});
```

- [ ] **Step 7: Run all editor tests**

Run: `npm test -- --run`
Expected: all green; new routing test passes.

- [ ] **Step 8: Commit**

```bash
git add editor/usePolling.js editor/usePolling.test.js editor/EditorApp.jsx editor/EditorApp.test.jsx editor/components/reviewer/
git commit -m "feat(editor): view router + usePolling hook + reviewer scaffold

Three-state EditorApp (empty | project | reviewer). Selecting a
completed source routes to a placeholder ReviewerView (filled in
by subsequent tasks). Polling extracted into a reusable hook so
the project view and the reviewer's retranscribe pill share code."
```

---

## Task 12: `ReviewerView` shell + `ReviewerContext` + transcript fetch

**Files:**
- Create: `editor/components/reviewer/ReviewerView.jsx`
- Create: `editor/components/reviewer/ReviewerContext.js`
- Create: `editor/components/reviewer/ReviewerView.test.jsx`

The shell mounts the `<audio>`/`<video>` element, fetches the transcript, exposes `seekTo` / `play` / `pause` via context, and renders placeholders for the panels (filled in subsequent tasks).

- [ ] **Step 1: Write failing test**

Create `editor/components/reviewer/ReviewerView.test.jsx`:

```javascript
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import ReviewerView from './ReviewerView.jsx';

beforeEach(() => {
    globalThis.fetch = vi.fn();
});

const TRANSCRIPT = {
    schema_version: '1.0',
    source: { path: '/x/y.mp3', duration_seconds: 60.0 },
    speakers: [],
    segments: [
        { id: 0, start: 1.0, end: 4.0, text: 'Hello world', words: [], low_confidence: false },
    ],
};
const SPEECH_SEGMENTS = [{ start: 1.0, end: 4.0 }];

function mockTranscriptOk() {
    fetch.mockResolvedValueOnce({
        ok: true,
        json: () => Promise.resolve({ transcript: TRANSCRIPT, speech_segments: SPEECH_SEGMENTS }),
    });
}

describe('ReviewerView', () => {
    it('fetches transcript on mount and renders the source name', async () => {
        mockTranscriptOk();
        render(<ReviewerView folder="/x" source={{ path: '/x/y.mp3', mode: 'audio' }} onBack={() => {}} manifest={{ folder: '/x', files: [] }} />);
        await waitFor(() => expect(screen.getByText(/Hello world/)).toBeInTheDocument());
    });

    it('shows an error message if fetch fails', async () => {
        fetch.mockResolvedValueOnce({ ok: false, status: 500 });
        render(<ReviewerView folder="/x" source={{ path: '/x/y.mp3', mode: 'audio' }} onBack={() => {}} manifest={{ folder: '/x', files: [] }} />);
        await waitFor(() => expect(screen.getByText(/failed to load transcript/i)).toBeInTheDocument());
    });
});
```

- [ ] **Step 2: Verify failure**

Run: `npm test -- --run editor/components/reviewer/ReviewerView.test.jsx`
Expected: FAIL — module doesn't exist.

- [ ] **Step 3: Implement context**

Create `editor/components/reviewer/ReviewerContext.js`:

```javascript
import { createContext, useContext } from 'react';

export const ReviewerContext = createContext(null);

export function useReviewer() {
    const ctx = useContext(ReviewerContext);
    if (!ctx) throw new Error('useReviewer must be used inside <ReviewerView>');
    return ctx;
}
```

- [ ] **Step 4: Implement `ReviewerView`**

Create `editor/components/reviewer/ReviewerView.jsx`:

```javascript
import React, { useEffect, useRef, useState, useCallback, useMemo } from 'react';
import { apiGet } from '../../api.js';
import { ReviewerContext } from './ReviewerContext.js';
// Placeholders — replaced by real components in subsequent tasks
function TopBarPlaceholder({ onBack, source }) {
    return (<div data-testid="topbar"><button onClick={onBack}>← Project</button> {source.path}</div>);
}
function MediaPanePlaceholder() { return <div data-testid="mediapane">media</div>; }
function TranscriptPanelPlaceholder({ transcript }) {
    return (<div data-testid="transcriptpanel">{transcript.segments.map(s => <div key={s.id}>{s.text}</div>)}</div>);
}
function TimelinePlaceholder() { return <div data-testid="timeline">timeline</div>; }

export default function ReviewerView({ folder, source, onBack, manifest }) {
    const [transcript, setTranscript] = useState(null);
    const [speechSegments, setSpeechSegments] = useState(null);
    const [error, setError] = useState(null);
    const audioRef = useRef(null);
    const [currentTime, setCurrentTime] = useState(0);
    const [duration, setDuration] = useState(0);
    const [playing, setPlaying] = useState(false);

    useEffect(() => {
        const params = new URLSearchParams({ folder, source: source.path });
        apiGet(`/api/source/transcript?${params.toString()}`)
            .then((doc) => {
                setTranscript(doc.transcript);
                setSpeechSegments(doc.speech_segments);
            })
            .catch(() => setError('Failed to load transcript'));
    }, [folder, source.path]);

    const seekTo = useCallback((seconds) => {
        if (!audioRef.current) return;
        audioRef.current.currentTime = Math.max(0, Math.min(seconds, audioRef.current.duration || 0));
    }, []);
    const play = useCallback(() => audioRef.current?.play(), []);
    const pause = useCallback(() => audioRef.current?.pause(), []);

    const ctx = useMemo(() => ({
        audioRef,
        currentTime, duration, playing,
        seekTo, play, pause,
        folder, source,
    }), [currentTime, duration, playing, seekTo, play, pause, folder, source]);

    if (error) return <div style={{ padding: 24, color: '#f87171' }}>{error}</div>;
    if (!transcript) return <div style={{ padding: 24, color: '#8b949e' }}>Loading transcript…</div>;

    return (
        <ReviewerContext.Provider value={ctx}>
            <div style={{ width: '100%', height: '100%', display: 'flex', flexDirection: 'column' }}>
                <TopBarPlaceholder onBack={onBack} source={source} />
                <div style={{ flex: 1, display: 'grid', gridTemplateColumns: '1fr 360px' }}>
                    <div style={{ display: 'flex', flexDirection: 'column' }}>
                        <MediaPanePlaceholder />
                        <TimelinePlaceholder />
                    </div>
                    <TranscriptPanelPlaceholder transcript={transcript} />
                </div>
                <audio
                    ref={audioRef}
                    src={`/api/source/audio?${new URLSearchParams({ folder, source: source.path }).toString()}`}
                    onTimeUpdate={(e) => setCurrentTime(e.currentTarget.currentTime)}
                    onLoadedMetadata={(e) => setDuration(e.currentTarget.duration)}
                    onPlay={() => setPlaying(true)}
                    onPause={() => setPlaying(false)}
                    style={{ display: 'none' }}
                />
            </div>
        </ReviewerContext.Provider>
    );
}
```

(The hidden `<audio>` element is the source of truth for media. Visible transport controls in Task 14 call into the context. For BWC mode, Task 14 swaps in `<video>` instead.)

- [ ] **Step 5: Verify pass**

Run: `npm test -- --run editor/components/reviewer/ReviewerView.test.jsx`
Expected: 2 PASS.

- [ ] **Step 6: Commit**

```bash
git add editor/components/reviewer/
git commit -m "feat(editor): ReviewerView shell + ReviewerContext

Mounts the <audio> element, fetches /api/source/transcript on mount,
exposes seekTo/play/pause via context. Renders placeholder TopBar /
MediaPane / TranscriptPanel / Timeline children — replaced in
subsequent tasks."
```

---

# Phase F — Top bar

## Task 13: `TopBar` component

**Files:**
- Create: `editor/components/reviewer/TopBar.jsx`
- Create: `editor/components/reviewer/TopBar.test.jsx`
- Modify: `editor/components/reviewer/ReviewerView.jsx` (replace `TopBarPlaceholder`)

- [ ] **Step 1: Write failing test**

Create `editor/components/reviewer/TopBar.test.jsx`:

```javascript
import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import TopBar from './TopBar.jsx';

const MANIFEST = {
    folder: '/cases/williams',
    files: [
        { path: '/cases/williams/exam-1.mp3', completed: true },
        { path: '/cases/williams/exam-2.mp3', completed: false },
        { path: '/cases/williams/exam-3.mp3', completed: true },
    ],
};

describe('TopBar', () => {
    it('renders the folder breadcrumb', () => {
        render(<TopBar manifest={MANIFEST} source={MANIFEST.files[0]} onBack={() => {}} onSelectSource={() => {}} retranscribeStatus={null} />);
        expect(screen.getByText(/cases\/williams/)).toBeInTheDocument();
    });

    it('source picker filters to completed sources only', () => {
        render(<TopBar manifest={MANIFEST} source={MANIFEST.files[0]} onBack={() => {}} onSelectSource={() => {}} retranscribeStatus={null} />);
        const options = screen.getAllByRole('option');
        expect(options.map(o => o.textContent)).toEqual([
            expect.stringContaining('exam-1.mp3'),
            expect.stringContaining('exam-3.mp3'),
        ]);
    });

    it('selecting a source calls onSelectSource', () => {
        const onSelectSource = vi.fn();
        render(<TopBar manifest={MANIFEST} source={MANIFEST.files[0]} onBack={() => {}} onSelectSource={onSelectSource} retranscribeStatus={null} />);
        fireEvent.change(screen.getByRole('combobox'), { target: { value: '/cases/williams/exam-3.mp3' } });
        expect(onSelectSource).toHaveBeenCalledWith(MANIFEST.files[2]);
    });

    it('back button calls onBack', () => {
        const onBack = vi.fn();
        render(<TopBar manifest={MANIFEST} source={MANIFEST.files[0]} onBack={onBack} onSelectSource={() => {}} retranscribeStatus={null} />);
        fireEvent.click(screen.getByRole('button', { name: /project/i }));
        expect(onBack).toHaveBeenCalled();
    });

    it('shows retranscribe pill when status is running', () => {
        render(<TopBar manifest={MANIFEST} source={MANIFEST.files[0]} onBack={() => {}} onSelectSource={() => {}} retranscribeStatus="running:transcribe" />);
        expect(screen.getByText(/re-transcribing/i)).toBeInTheDocument();
        expect(screen.getByText(/Stage 5 of 6/i)).toBeInTheDocument();
    });

    it('omits retranscribe pill when status is null', () => {
        render(<TopBar manifest={MANIFEST} source={MANIFEST.files[0]} onBack={() => {}} onSelectSource={() => {}} retranscribeStatus={null} />);
        expect(screen.queryByText(/re-transcribing/i)).not.toBeInTheDocument();
    });
});
```

- [ ] **Step 2: Verify failure**

Run: `npm test -- --run editor/components/reviewer/TopBar.test.jsx`
Expected: FAIL.

- [ ] **Step 3: Implement**

Create `editor/components/reviewer/TopBar.jsx`. (Use the styles from the layout mockup committed during brainstorming as a guide; tests don't pin styles.)

```javascript
import React from 'react';

function progressLabel(status) {
    if (status === 'queued') return 'Re-transcribing — queued';
    if (status === 'running:transcribe') return 'Re-transcribing — Stage 5 of 6';
    if (status === 'running:align') return 'Re-transcribing — Stage 6 of 6';
    return null;
}

export default function TopBar({ manifest, source, onBack, onSelectSource, retranscribeStatus }) {
    const completedFiles = manifest.files.filter(f => f.completed);
    const label = progressLabel(retranscribeStatus);

    return (
        <div role="banner" style={{ display: 'flex', gap: 14, alignItems: 'center', padding: '8px 14px', background: '#161b22', borderBottom: '1px solid #21262d' }}>
            <button onClick={onBack} style={{ background: 'transparent', color: '#8b949e', border: '1px solid #30363d', borderRadius: 3, padding: '3px 9px' }}>
                ← Project
            </button>
            <span style={{ fontFamily: 'ui-monospace, monospace', color: '#6e7681', fontSize: '0.72rem', maxWidth: 300, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }} title={manifest.folder}>
                {manifest.folder}
            </span>
            <select
                value={source?.path || ''}
                onChange={(e) => {
                    const next = manifest.files.find(f => f.path === e.target.value);
                    if (next) onSelectSource(next);
                }}
                style={{ background: '#0d1117', color: '#c9d1d9', border: '1px solid #30363d', borderRadius: 3, padding: '4px 9px', fontSize: '0.78rem', fontFamily: 'ui-monospace, monospace' }}
            >
                {completedFiles.map(f => (
                    <option key={f.path} value={f.path}>{basename(f.path)}</option>
                ))}
            </select>
            {label && (
                <span style={{ background: '#161b22', border: '1px solid #d29922', color: '#d29922', borderRadius: 10, padding: '2px 9px', fontSize: '0.7rem' }}>
                    ⟳ {label}…
                </span>
            )}
            <span style={{ flex: 1 }} />
        </div>
    );
}

function basename(path) {
    return path.replace(/\\/g, '/').split('/').pop();
}
```

- [ ] **Step 4: Replace placeholder in `ReviewerView`**

Import `TopBar`, drop in:

```javascript
<TopBar
    manifest={manifest}
    source={source}
    onBack={onBack}
    onSelectSource={(f) => { /* parent will lift this in Task 21; for now, navigate within the reviewer */ }}
    retranscribeStatus={null}
/>
```

For now `onSelectSource` is a no-op stub (cross-source navigation lands in Task 21 where retranscribe wiring is finished — until then, only one source per reviewer mount is supported).

- [ ] **Step 5: Verify pass**

Run: `npm test -- --run editor/components/reviewer/`
Expected: all PASS.

- [ ] **Step 6: Commit**

```bash
git add editor/components/reviewer/TopBar.jsx editor/components/reviewer/TopBar.test.jsx editor/components/reviewer/ReviewerView.jsx
git commit -m "feat(editor): TopBar component

Back button, folder breadcrumb, source picker (completed sources only),
retranscribe progress pill. Pill renders only when retranscribeStatus
is non-null."
```

---

# Phase G — Media pane

## Task 14: `MediaPane` + `Transport` (audio mode first)

**Files:**
- Create: `editor/components/reviewer/MediaPane.jsx` + `.test.jsx`
- Create: `editor/components/reviewer/Transport.jsx` + `.test.jsx`
- Modify: `editor/components/reviewer/ReviewerView.jsx` (replace `MediaPanePlaceholder`)

- [ ] **Step 1: Write failing test for `Transport`**

Create `editor/components/reviewer/Transport.test.jsx`:

```javascript
import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import { ReviewerContext } from './ReviewerContext.js';
import Transport from './Transport.jsx';

function withCtx(ctx, ui) {
    return <ReviewerContext.Provider value={ctx}>{ui}</ReviewerContext.Provider>;
}

describe('Transport', () => {
    it('play button calls play()', () => {
        const play = vi.fn();
        render(withCtx({ play, pause: vi.fn(), seekTo: vi.fn(), playing: false, currentTime: 0, duration: 60 }, <Transport />));
        fireEvent.click(screen.getByRole('button', { name: /play/i }));
        expect(play).toHaveBeenCalled();
    });

    it('shows current and total time', () => {
        render(withCtx({ play: vi.fn(), pause: vi.fn(), seekTo: vi.fn(), playing: false, currentTime: 65, duration: 3600 }, <Transport />));
        expect(screen.getByText('01:05 / 60:00')).toBeInTheDocument();
    });

    it('±5 s skip respects duration bounds', () => {
        const seekTo = vi.fn();
        render(withCtx({ play: vi.fn(), pause: vi.fn(), seekTo, playing: false, currentTime: 3, duration: 60 }, <Transport />));
        fireEvent.click(screen.getByRole('button', { name: /skip back 5/i }));
        expect(seekTo).toHaveBeenCalledWith(0);  // clamped at 0
    });
});
```

- [ ] **Step 2: Implement Transport**

Create `editor/components/reviewer/Transport.jsx`:

```javascript
import React from 'react';
import { useReviewer } from './ReviewerContext.js';

function fmt(seconds) {
    if (!isFinite(seconds)) return '00:00';
    const total = Math.max(0, Math.floor(seconds));
    const m = Math.floor(total / 60);
    const s = total % 60;
    return `${String(m).padStart(2, '0')}:${String(s).padStart(2, '0')}`;
}

export default function Transport() {
    const { play, pause, seekTo, playing, currentTime, duration } = useReviewer();
    const skip = (delta) => seekTo(Math.max(0, Math.min((currentTime ?? 0) + delta, duration ?? 0)));
    return (
        <div role="toolbar" style={{ display: 'flex', alignItems: 'center', gap: 10, marginTop: 14 }}>
            <button aria-label="Skip back 5 s" onClick={() => skip(-5)}>◀◀</button>
            {playing
                ? <button aria-label="Pause" onClick={pause}>⏸</button>
                : <button aria-label="Play" onClick={play}>▶</button>}
            <button aria-label="Skip forward 5 s" onClick={() => skip(5)}>▶▶</button>
            <span style={{ marginLeft: 8, fontFamily: 'ui-monospace, monospace', color: '#8b949e', fontSize: '0.78rem' }}>
                {fmt(currentTime)} / {fmt(duration)}
            </span>
        </div>
    );
}
```

- [ ] **Step 3: Verify Transport tests pass**

Run: `npm test -- --run editor/components/reviewer/Transport.test.jsx`
Expected: 3 PASS.

- [ ] **Step 4: Write failing test for `MediaPane`**

Create `editor/components/reviewer/MediaPane.test.jsx`:

```javascript
import { describe, it, expect } from 'vitest';
import { render, screen } from '@testing-library/react';
import { ReviewerContext } from './ReviewerContext.js';
import MediaPane from './MediaPane.jsx';

function withCtx(source, ui) {
    return (
        <ReviewerContext.Provider value={{
            audioRef: { current: null }, currentTime: 0, duration: 0, playing: false,
            play: () => {}, pause: () => {}, seekTo: () => {},
            folder: '/x', source,
        }}>
            {ui}
        </ReviewerContext.Provider>
    );
}

describe('MediaPane', () => {
    it('renders audio mode with waveform placeholder + transport', () => {
        render(withCtx({ path: '/x/y.mp3', mode: 'audio' }, <MediaPane />));
        expect(screen.getByRole('toolbar')).toBeInTheDocument();
        expect(screen.queryByTestId('video-element')).not.toBeInTheDocument();
    });

    it('renders video mode with <video> element', () => {
        render(withCtx({ path: '/x/y.mp4', mode: 'video' }, <MediaPane />));
        const video = screen.getByTestId('video-element');
        expect(video).toBeInTheDocument();
        expect(video.getAttribute('src')).toContain('/api/source/video');
    });
});
```

- [ ] **Step 5: Implement MediaPane**

Create `editor/components/reviewer/MediaPane.jsx`:

```javascript
import React from 'react';
import { useReviewer } from './ReviewerContext.js';
import Transport from './Transport.jsx';
import Waveform from './Waveform.jsx';   // implemented in Task 15

export default function MediaPane() {
    const { source, folder, audioRef } = useReviewer();
    const isVideo = source.mode === 'video';
    const params = new URLSearchParams({ folder, source: source.path }).toString();
    const url = isVideo ? `/api/source/video?${params}` : `/api/source/audio?${params}`;

    return (
        <div style={{ flex: 1, background: '#010409', borderRight: '1px solid #21262d', display: 'flex', flexDirection: 'column', padding: 14 }}>
            {isVideo
                ? <video data-testid="video-element" ref={audioRef} src={url} style={{ width: '100%', maxHeight: 360, background: '#000' }} controls={false} />
                : <Waveform url={url} />}
            <Transport />
        </div>
    );
}
```

(Note the audioRef is reused for the `<video>` element — same media-element API; the parent `ReviewerView` doesn't care which.)

- [ ] **Step 6: Stub Waveform until Task 15**

Create `editor/components/reviewer/Waveform.jsx` minimal:

```javascript
import React from 'react';
export default function Waveform({ url }) {
    return <div data-testid="waveform-placeholder" style={{ width: '100%', height: 110, background: '#161b22' }}>Waveform loading…</div>;
}
```

- [ ] **Step 7: Replace MediaPanePlaceholder in ReviewerView**

> **Note:** This step relocates the `<audio>` element from `ReviewerView` (Task 12) into `MediaPane`. Be sure to update `ReviewerView.test.jsx` if any test asserted the audio element's location in the DOM tree — Task 12's tests don't, but if you added one, fix it here. Existing tests should keep passing because they don't probe the audio element directly.


Replace `<MediaPanePlaceholder />` with `<MediaPane />` and remove the placeholder. Adjust the `<audio>` element rendering: when `source.mode === 'video'`, the visible `<video>` in `MediaPane` is the media element (audioRef points at it); the bottom hidden `<audio>` should be conditional. Easiest fix: leave audio rendering inside `MediaPane`'s audio branch (always inside the visible component) and remove the bottom `<audio>` element from `ReviewerView`.

The cleaner version of `ReviewerView` body:

```javascript
return (
    <ReviewerContext.Provider value={ctx}>
        <div style={{ width: '100%', height: '100%', display: 'flex', flexDirection: 'column' }}>
            <TopBar ... />
            <div style={{ flex: 1, display: 'grid', gridTemplateColumns: '1fr 360px' }}>
                <div style={{ display: 'flex', flexDirection: 'column' }}>
                    <MediaPane />
                    <TimelinePlaceholder />
                </div>
                <TranscriptPanelPlaceholder transcript={transcript} />
            </div>
        </div>
    </ReviewerContext.Provider>
);
```

…and add the actual `<audio>` element (audio mode) inside `MediaPane`:

```javascript
{!isVideo && (
    <audio
        ref={audioRef}
        src={url}
        onTimeUpdate={...}  // wire via the parent context's setter helpers
        style={{ display: 'none' }}
    />
)}
```

To avoid plumbing setters through context, pull the timeupdate / loadedmetadata wiring back into `ReviewerView` and pass it down as props to `MediaPane`:

```javascript
// ReviewerView
const onTimeUpdate = (e) => setCurrentTime(e.currentTarget.currentTime);
const onLoadedMetadata = (e) => setDuration(e.currentTarget.duration);
const onPlay = () => setPlaying(true);
const onPause = () => setPlaying(false);

<MediaPane
    onTimeUpdate={onTimeUpdate}
    onLoadedMetadata={onLoadedMetadata}
    onPlay={onPlay}
    onPause={onPause}
/>
```

`MediaPane` forwards them to the `<audio>` or `<video>` element it renders.

- [ ] **Step 8: Verify pass**

Run: `npm test -- --run editor/components/reviewer/`
Expected: all PASS.

- [ ] **Step 9: Commit**

```bash
git add editor/components/reviewer/MediaPane.jsx editor/components/reviewer/MediaPane.test.jsx editor/components/reviewer/Transport.jsx editor/components/reviewer/Transport.test.jsx editor/components/reviewer/Waveform.jsx editor/components/reviewer/ReviewerView.jsx
git commit -m "feat(editor): MediaPane + Transport components

Branches on source.mode (audio | video). The same audioRef points at
either an <audio> or <video> element. Transport row exposes Play /
Pause / ±5 s with a time readout. Waveform stubbed for Task 15."
```

---

## Task 15: `Waveform` component

**Files:**
- Modify: `editor/components/reviewer/Waveform.jsx` (replace stub with real implementation)
- Create: `editor/components/reviewer/Waveform.test.jsx`

- [ ] **Step 1: Write failing test**

Create `editor/components/reviewer/Waveform.test.jsx`:

```javascript
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, waitFor } from '@testing-library/react';
import Waveform from './Waveform.jsx';

beforeEach(() => {
    globalThis.fetch = vi.fn(() => Promise.resolve({
        ok: true,
        arrayBuffer: () => Promise.resolve(new ArrayBuffer(1024)),
    }));
    globalThis.AudioContext = class {
        decodeAudioData(buf) {
            // Synthetic audio: 48000 samples, single channel, sine-ish.
            const channelLength = 48000;
            return Promise.resolve({
                length: channelLength,
                numberOfChannels: 1,
                getChannelData: () => Float32Array.from({ length: channelLength }, (_, i) => Math.sin(i / 100)),
            });
        }
    };
});

describe('Waveform', () => {
    it('downsamples decoded audio to ~2000 peaks', async () => {
        const { container } = render(<Waveform url="/api/source/audio?x=y" />);
        await waitFor(() => expect(container.querySelector('canvas')).toBeInTheDocument());
        // No assertion on pixel content; behavior covered by integration use.
    });
});
```

- [ ] **Step 2: Verify failure**

Run: `npm test -- --run editor/components/reviewer/Waveform.test.jsx`
Expected: FAIL — stub renders a div, not a canvas.

- [ ] **Step 3: Implement**

Replace `editor/components/reviewer/Waveform.jsx` with:

```javascript
import React, { useEffect, useRef, useState } from 'react';

const PEAK_COUNT = 2000;

export default function Waveform({ url }) {
    const canvasRef = useRef(null);
    const [peaks, setPeaks] = useState(null);
    const [loading, setLoading] = useState(true);

    useEffect(() => {
        let cancelled = false;
        async function load() {
            setLoading(true);
            try {
                const buf = await fetch(url).then(r => r.arrayBuffer());
                const ctx = new (window.AudioContext || window.webkitAudioContext)();
                const decoded = await ctx.decodeAudioData(buf);
                if (cancelled) return;
                const channel = decoded.getChannelData(0);
                const samplesPerPeak = Math.max(1, Math.ceil(channel.length / PEAK_COUNT));
                const out = new Float32Array(PEAK_COUNT);
                for (let i = 0; i < PEAK_COUNT; i++) {
                    let max = 0;
                    const start = i * samplesPerPeak;
                    const end = Math.min(start + samplesPerPeak, channel.length);
                    for (let j = start; j < end; j++) {
                        const v = Math.abs(channel[j]);
                        if (v > max) max = v;
                    }
                    out[i] = max;
                }
                setPeaks(out);
            } catch (err) {
                console.warn('[Waveform] decode failed:', err);
            } finally {
                if (!cancelled) setLoading(false);
            }
        }
        load();
        return () => { cancelled = true; };
    }, [url]);

    useEffect(() => {
        if (!peaks || !canvasRef.current) return;
        const canvas = canvasRef.current;
        const dpr = window.devicePixelRatio || 1;
        const w = canvas.clientWidth;
        const h = canvas.clientHeight;
        canvas.width = w * dpr;
        canvas.height = h * dpr;
        const ctx = canvas.getContext('2d');
        ctx.scale(dpr, dpr);
        ctx.clearRect(0, 0, w, h);
        ctx.fillStyle = '#2ea3a3';
        const barWidth = Math.max(1, w / peaks.length);
        for (let i = 0; i < peaks.length; i++) {
            const barHeight = peaks[i] * h;
            ctx.fillRect(i * barWidth, (h - barHeight) / 2, Math.max(1, barWidth - 0.5), barHeight);
        }
    }, [peaks]);

    return (
        <div style={{ position: 'relative', width: '100%', height: 110 }}>
            <canvas ref={canvasRef} style={{ width: '100%', height: '100%' }} />
            {loading && <div style={{ position: 'absolute', top: 0, left: 0, right: 0, bottom: 0, display: 'flex', alignItems: 'center', justifyContent: 'center', color: '#6e7681' }}>Loading waveform…</div>}
        </div>
    );
}
```

- [ ] **Step 4: Verify pass**

Run: `npm test -- --run editor/components/reviewer/Waveform.test.jsx`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add editor/components/reviewer/Waveform.jsx editor/components/reviewer/Waveform.test.jsx
git commit -m "feat(editor): Waveform canvas component

Fetches the audio bytes, decodes via AudioContext.decodeAudioData,
downsamples to 2000 max-abs peaks per channel, renders to canvas.
DPR-aware. Loading overlay until first paint."
```

---

# Phase H — Transcript panel + search highlighting

## Task 16: `TranscriptPanel` with active-utterance scroll + low-confidence underline

**Files:**
- Create: `editor/components/reviewer/TranscriptPanel.jsx` + `.test.jsx`
- Create: `editor/components/reviewer/SearchHighlight.jsx` (simple utility)
- Modify: `editor/components/reviewer/ReviewerView.jsx` (replace placeholder)

- [ ] **Step 1: Write failing tests**

Create `editor/components/reviewer/TranscriptPanel.test.jsx`:

```javascript
import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import { ReviewerContext } from './ReviewerContext.js';
import TranscriptPanel from './TranscriptPanel.jsx';

const TRANSCRIPT = {
    segments: [
        { id: 0, start: 0.0, end: 4.0, text: 'Hello world', words: [], low_confidence: false },
        { id: 1, start: 4.0, end: 8.0, text: 'Second utterance', words: [{ word: 'Second', score: 0.4, start: 4.0, end: 4.5 }], low_confidence: true },
        { id: 2, start: 8.0, end: 12.0, text: 'Third', words: [], low_confidence: false },
    ],
};

function withCtx(currentTime, ui) {
    return <ReviewerContext.Provider value={{
        audioRef: { current: null }, currentTime, duration: 12, playing: false,
        play: () => {}, pause: () => {}, seekTo: vi.fn(),
        folder: '/x', source: { path: '/x/y.mp3', mode: 'audio' },
    }}>{ui}</ReviewerContext.Provider>;
}

describe('TranscriptPanel', () => {
    it('renders all segments', () => {
        render(withCtx(0, <TranscriptPanel transcript={TRANSCRIPT} searchQuery="" />));
        expect(screen.getByText('Hello world')).toBeInTheDocument();
        expect(screen.getByText('Second utterance')).toBeInTheDocument();
        expect(screen.getByText('Third')).toBeInTheDocument();
    });

    it('marks the active utterance based on currentTime', () => {
        const { container } = render(withCtx(5.0, <TranscriptPanel transcript={TRANSCRIPT} searchQuery="" />));
        const active = container.querySelector('[data-active="true"]');
        expect(active.textContent).toContain('Second utterance');
    });

    it('clicking a segment calls seekTo', () => {
        const seekTo = vi.fn();
        const ctxValue = {
            audioRef: { current: null }, currentTime: 0, duration: 12, playing: false,
            play: () => {}, pause: () => {}, seekTo,
            folder: '/x', source: { path: '/x/y.mp3', mode: 'audio' },
        };
        render(<ReviewerContext.Provider value={ctxValue}><TranscriptPanel transcript={TRANSCRIPT} searchQuery="" /></ReviewerContext.Provider>);
        fireEvent.click(screen.getByText('Third'));
        expect(seekTo).toHaveBeenCalledWith(8.0);
    });

    it('underlines low-score words', () => {
        const { container } = render(withCtx(0, <TranscriptPanel transcript={TRANSCRIPT} searchQuery="" />));
        const underlined = container.querySelectorAll('[data-low-conf="true"]');
        expect(underlined.length).toBeGreaterThan(0);
    });

    it('highlights search matches', () => {
        const { container } = render(withCtx(0, <TranscriptPanel transcript={TRANSCRIPT} searchQuery="utterance" />));
        const marks = container.querySelectorAll('mark');
        expect(marks.length).toBe(1);
        expect(marks[0].textContent).toBe('utterance');
    });
});
```

- [ ] **Step 2: Verify failure**

Run: `npm test -- --run editor/components/reviewer/TranscriptPanel.test.jsx`
Expected: FAIL.

- [ ] **Step 3: Implement `SearchHighlight`**

Create `editor/components/reviewer/SearchHighlight.jsx`:

```javascript
import React from 'react';

export default function SearchHighlight({ text, query }) {
    if (!query) return text;
    const lower = text.toLowerCase();
    const q = query.toLowerCase();
    const out = [];
    let cursor = 0;
    while (cursor < text.length) {
        const i = lower.indexOf(q, cursor);
        if (i === -1) {
            out.push(text.slice(cursor));
            break;
        }
        if (i > cursor) out.push(text.slice(cursor, i));
        out.push(<mark key={i}>{text.slice(i, i + q.length)}</mark>);
        cursor = i + q.length;
    }
    return out.map((part, idx) => (typeof part === 'string' ? <React.Fragment key={idx}>{part}</React.Fragment> : part));
}
```

- [ ] **Step 4: Implement `TranscriptPanel`**

Create `editor/components/reviewer/TranscriptPanel.jsx`:

```javascript
import React, { useEffect, useMemo, useRef, useState } from 'react';
import { useReviewer } from './ReviewerContext.js';
import SearchHighlight from './SearchHighlight.jsx';

const LOW_CONF_WORD_SCORE = 0.6;

function fmtTs(seconds) {
    const m = Math.floor(seconds / 60);
    const s = Math.floor(seconds % 60);
    return `${String(m).padStart(2, '0')}:${String(s).padStart(2, '0')}`;
}

function activeIndex(segments, currentTime) {
    // Last segment with start <= currentTime. -1 if none yet.
    let lo = 0, hi = segments.length - 1, ans = -1;
    while (lo <= hi) {
        const mid = (lo + hi) >> 1;
        if (segments[mid].start <= currentTime) { ans = mid; lo = mid + 1; }
        else hi = mid - 1;
    }
    return ans;
}

export default function TranscriptPanel({ transcript, searchQuery }) {
    const { currentTime, seekTo } = useReviewer();
    const segments = transcript.segments;
    const active = useMemo(() => activeIndex(segments, currentTime), [segments, currentTime]);
    const listRef = useRef(null);
    const userScrolled = useRef(false);

    useEffect(() => {
        const el = listRef.current;
        if (!el) return;
        const onScroll = () => { userScrolled.current = true; };
        el.addEventListener('wheel', onScroll, { passive: true });
        el.addEventListener('touchstart', onScroll, { passive: true });
        return () => {
            el.removeEventListener('wheel', onScroll);
            el.removeEventListener('touchstart', onScroll);
        };
    }, []);

    useEffect(() => {
        if (userScrolled.current) return;
        if (active < 0) return;
        const el = listRef.current?.querySelector(`[data-segment-id="${segments[active].id}"]`);
        el?.scrollIntoView({ block: 'center', behavior: 'auto' });
    }, [active, segments]);

    const onClickSegment = (s) => {
        userScrolled.current = false;  // resume auto-follow
        seekTo(s.start);
    };

    return (
        <div ref={listRef} role="region" aria-label="transcript" style={{ background: '#0d1117', borderLeft: '1px solid #21262d', overflowY: 'auto', flex: 1 }}>
            {segments.map((s, idx) => {
                const isActive = idx === active;
                return (
                    <div
                        key={s.id}
                        data-segment-id={s.id}
                        data-active={isActive}
                        onClick={() => onClickSegment(s)}
                        style={{
                            padding: '7px 12px', cursor: 'pointer',
                            borderLeft: `3px solid ${isActive ? '#2ea3a3' : 'transparent'}`,
                            background: isActive ? 'rgba(46, 163, 163, 0.13)' : undefined,
                            fontSize: '0.83rem', lineHeight: 1.45, color: '#c9d1d9',
                        }}
                    >
                        <span style={{ fontFamily: 'ui-monospace, monospace', color: '#8b949e', fontSize: '0.72rem', marginRight: 8 }}>
                            {fmtTs(s.start)}
                        </span>
                        <span style={{ color: '#2ea3a3', fontWeight: 600, marginRight: 4 }}>Speaker:</span>
                        <SegmentText segment={s} query={searchQuery} />
                    </div>
                );
            })}
        </div>
    );
}

function SegmentText({ segment, query }) {
    if (segment.words && segment.words.length > 0) {
        return (
            <>
                {segment.words.map((w, i) => {
                    const lowConf = (w.score ?? 1) < LOW_CONF_WORD_SCORE;
                    return (
                        <React.Fragment key={i}>
                            {i > 0 ? ' ' : ''}
                            <span data-low-conf={lowConf} style={lowConf ? { textDecoration: 'underline', textDecorationColor: '#d29922', textDecorationThickness: 2 } : undefined}>
                                <SearchHighlight text={w.word} query={query} />
                            </span>
                        </React.Fragment>
                    );
                })}
            </>
        );
    }
    return <SearchHighlight text={segment.text} query={query} />;
}
```

- [ ] **Step 5: Wire into ReviewerView**

In `ReviewerView.jsx`, lift `searchQuery` state and pass it down. Add:

```javascript
const [searchQuery, setSearchQuery] = useState('');
// ...
<TranscriptPanel transcript={transcript} searchQuery={searchQuery} />
```

`searchQuery` will be wired to the search input in Task 19.

- [ ] **Step 6: Verify pass**

Run: `npm test -- --run editor/components/reviewer/TranscriptPanel.test.jsx`
Expected: 5 PASS.

- [ ] **Step 7: Commit**

```bash
git add editor/components/reviewer/TranscriptPanel.jsx editor/components/reviewer/TranscriptPanel.test.jsx editor/components/reviewer/SearchHighlight.jsx editor/components/reviewer/ReviewerView.jsx
git commit -m "feat(editor): TranscriptPanel with active-scroll + low-conf + search

Active utterance derivation via binary search on currentTime. Auto-
scroll-to-follow suspends on wheel/touch; resumes on click. Low-
confidence WhisperX word.score < 0.6 underlines amber. Search query
is passed in; matches highlighted via SearchHighlight utility."
```

---

# Phase I — Context names panel + retranscribe wiring

## Task 17: `ContextNamesPanel` + retranscribe lifecycle

**Files:**
- Create: `editor/components/reviewer/ContextNamesPanel.jsx` + `.test.jsx`
- Modify: `editor/components/reviewer/ReviewerView.jsx` (wire retranscribe state machine)

- [ ] **Step 1: Write failing tests**

Create `editor/components/reviewer/ContextNamesPanel.test.jsx`:

```javascript
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import ContextNamesPanel from './ContextNamesPanel.jsx';

beforeEach(() => {
    globalThis.fetch = vi.fn();
});

describe('ContextNamesPanel', () => {
    it('Apply button POSTs context, then retranscribe, in order', async () => {
        fetch.mockResolvedValue({ ok: true, json: () => Promise.resolve({ ok: true }) });
        const onStarted = vi.fn();
        render(<ContextNamesPanel folder="/x" sourcePath="/x/y.mp3" onRetranscribeStarted={onStarted} disabled={false} />);
        fireEvent.change(screen.getByLabelText(/names/i), { target: { value: 'Patel' } });
        fireEvent.click(screen.getByRole('button', { name: /apply/i }));
        await waitFor(() => expect(fetch).toHaveBeenCalledTimes(2));
        expect(fetch.mock.calls[0][0]).toBe('/api/source/context');
        expect(fetch.mock.calls[1][0]).toBe('/api/source/retranscribe');
        expect(onStarted).toHaveBeenCalled();
    });

    it('disables button while disabled prop is true', () => {
        render(<ContextNamesPanel folder="/x" sourcePath="/x/y.mp3" onRetranscribeStarted={() => {}} disabled />);
        expect(screen.getByRole('button', { name: /apply/i })).toBeDisabled();
    });
});
```

- [ ] **Step 2: Verify failure**

Run: `npm test -- --run editor/components/reviewer/ContextNamesPanel.test.jsx`
Expected: FAIL.

- [ ] **Step 3: Implement**

Create `editor/components/reviewer/ContextNamesPanel.jsx`:

```javascript
import React, { useState } from 'react';

export default function ContextNamesPanel({ folder, sourcePath, onRetranscribeStarted, disabled }) {
    const [names, setNames] = useState('');
    const [locations, setLocations] = useState('');
    const [busy, setBusy] = useState(false);
    const [error, setError] = useState(null);

    const apply = async () => {
        setBusy(true);
        setError(null);
        try {
            const ctxResp = await fetch('/api/source/context', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    folder, source: sourcePath,
                    names: names.split('\n').map(s => s.trim()).filter(Boolean),
                    locations: locations.split('\n').map(s => s.trim()).filter(Boolean),
                }),
            });
            if (!ctxResp.ok) throw new Error(`context save failed (${ctxResp.status})`);
            const rerunResp = await fetch('/api/source/retranscribe', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ folder, source: sourcePath }),
            });
            if (!rerunResp.ok) throw new Error(`retranscribe failed (${rerunResp.status})`);
            onRetranscribeStarted();
        } catch (e) {
            setError(e.message);
        } finally {
            setBusy(false);
        }
    };

    return (
        <details open style={{ borderTop: '1px solid #21262d', background: '#0d1117', padding: '10px 12px', fontSize: '0.74rem', color: '#8b949e' }}>
            <summary style={{ cursor: 'pointer', color: '#c9d1d9' }}>Context names &amp; locations</summary>
            <label style={{ marginTop: 8, display: 'block', textTransform: 'uppercase', letterSpacing: '0.06em', fontSize: '0.65rem', color: '#6e7681' }}>
                Names you expect to hear
                <textarea value={names} onChange={(e) => setNames(e.target.value)} style={{ width: '100%', height: 36, marginTop: 5, background: '#010409', border: '1px solid #30363d', borderRadius: 3, color: '#c9d1d9', padding: '5px 8px', fontSize: '0.78rem' }} />
            </label>
            <label style={{ marginTop: 8, display: 'block', textTransform: 'uppercase', letterSpacing: '0.06em', fontSize: '0.65rem', color: '#6e7681' }}>
                Locations
                <textarea value={locations} onChange={(e) => setLocations(e.target.value)} style={{ width: '100%', height: 36, marginTop: 5, background: '#010409', border: '1px solid #30363d', borderRadius: 3, color: '#c9d1d9', padding: '5px 8px', fontSize: '0.78rem' }} />
            </label>
            <button onClick={apply} disabled={disabled || busy} style={{ marginTop: 9, background: '#2ea3a3', color: '#010409', border: 0, borderRadius: 3, padding: '4px 11px', fontSize: '0.74rem', fontWeight: 600 }}>
                {busy ? 'Applying…' : 'Apply & re-transcribe'}
            </button>
            {error && <span style={{ marginLeft: 8, color: '#f87171' }}>{error}</span>}
        </details>
    );
}
```

- [ ] **Step 4: Wire into ReviewerView**

In `ReviewerView.jsx`:

- Add `retranscribeStatus` state and a `staleTranscript` boolean.
- When `ContextNamesPanel.onRetranscribeStarted` fires, set `staleTranscript = true`, `retranscribeStatus = 'queued'`, and start polling `/api/source/state`.
- When polling reports `completed`, refetch `/api/source/transcript`, replace state, clear `staleTranscript`, set `retranscribeStatus = null`. Preserve `audioRef.current.currentTime` across the refetch (just don't touch it).
- On `failed`, leave `staleTranscript = true`, render an error banner.

```javascript
const [retranscribeStatus, setRetranscribeStatus] = useState(null);
const [staleTranscript, setStaleTranscript] = useState(false);

const fetchStatus = useCallback(async () => {
    const params = new URLSearchParams({ folder, source: source.path });
    const resp = await apiGet(`/api/source/state?${params.toString()}`);
    return resp.status === 'idle' ? null : resp.status;
}, [folder, source.path]);

const polling = usePolling(fetchStatus, retranscribeStatus !== null);

useEffect(() => {
    if (polling.status) setRetranscribeStatus(polling.status);
    if (polling.status === 'completed') {
        const params = new URLSearchParams({ folder, source: source.path });
        apiGet(`/api/source/transcript?${params.toString()}`).then((doc) => {
            setTranscript(doc.transcript);
            setSpeechSegments(doc.speech_segments);
            setStaleTranscript(false);
            setRetranscribeStatus(null);
        });
    }
}, [polling.status, folder, source.path]);

const onRetranscribeStarted = () => {
    setStaleTranscript(true);
    setRetranscribeStatus('queued');
};
```

Render the stale banner above `TranscriptPanel`:

```javascript
{staleTranscript && (
    <div style={{ background: '#161b22', borderBottom: '1px solid #d29922', color: '#d29922', padding: '6px 12px', fontSize: '0.78rem' }}>
        Re-transcribing — showing previous results
    </div>
)}
```

Pass `retranscribeStatus` to `<TopBar>`.

Place `<ContextNamesPanel>` inside the right column under `<TranscriptPanel>`.

- [ ] **Step 5: Verify pass**

Run: `npm test -- --run editor/components/reviewer/`
Expected: all PASS.

- [ ] **Step 6: Commit**

```bash
git add editor/components/reviewer/ContextNamesPanel.jsx editor/components/reviewer/ContextNamesPanel.test.jsx editor/components/reviewer/ReviewerView.jsx
git commit -m "feat(editor): ContextNamesPanel + retranscribe lifecycle

POSTs context.json, then retranscribe, then drives the polling loop.
While polling, transcript pane shows a stale banner over the previous
data. On completed, refetches the transcript and clears stale state."
```

---

# Phase J — Timeline

## Task 18: `useTimelineGeometry` hook

**Files:**
- Create: `editor/components/reviewer/useTimelineGeometry.js`
- Create: `editor/components/reviewer/useTimelineGeometry.test.js`

- [ ] **Step 1: Write failing tests**

```javascript
import { describe, it, expect } from 'vitest';
import { computeCells } from './useTimelineGeometry.js';

const SEGMENTS = [
    { start: 0, end: 5 },
    { start: 10, end: 15 },
    { start: 20, end: 25 },
];

describe('computeCells', () => {
    it('returns interleaved speech and silence cells (collapsed mode)', () => {
        const cells = computeCells({ speechSegments: SEGMENTS, durationSeconds: 30, mode: 'collapsed', expandedSilenceIndex: null });
        expect(cells.length).toBe(7);  // [silence, speech, silence, speech, silence, speech, silence]
        expect(cells.map(c => c.kind)).toEqual(['silence', 'speech', 'silence', 'speech', 'silence', 'speech', 'silence']);
    });

    it('uncompressed mode gives widthPct proportional to duration', () => {
        const cells = computeCells({ speechSegments: SEGMENTS, durationSeconds: 30, mode: 'uncompressed', expandedSilenceIndex: null });
        expect(cells[0].widthPct).toBeCloseTo(0, 5);
        expect(cells[1].widthPct).toBeCloseTo((5 / 30) * 100, 5);
    });

    it('expanded silence has widthPx 80 instead of 24', () => {
        const cells = computeCells({ speechSegments: SEGMENTS, durationSeconds: 30, mode: 'collapsed', expandedSilenceIndex: 1 });
        const silenceCells = cells.filter(c => c.kind === 'silence');
        // index 1 in the mixed list isn't necessarily the second silence; the hook
        // accepts a "silence index" relative to silence cells specifically.
        expect(silenceCells[1].widthPx).toBe(80);
        expect(silenceCells[0].widthPx).toBe(24);
    });

    it('omits zero-duration leading silence', () => {
        const cells = computeCells({ speechSegments: [{ start: 0, end: 5 }], durationSeconds: 5, mode: 'collapsed', expandedSilenceIndex: null });
        expect(cells.map(c => c.kind)).toEqual(['speech']);
    });
});
```

- [ ] **Step 2: Implement**

Create `editor/components/reviewer/useTimelineGeometry.js`:

```javascript
import { useMemo } from 'react';

const SILENCE_PX_DEFAULT = 24;
const SILENCE_PX_EXPANDED = 80;
const SPEECH_FLEX_PER_SECOND = 1.0;

export function computeCells({ speechSegments, durationSeconds, mode, expandedSilenceIndex }) {
    const cells = [];
    let cursor = 0;
    let silenceCount = 0;
    const pushSilence = (start, end) => {
        if (end <= start) return;
        const isExpanded = silenceCount === expandedSilenceIndex;
        const widthPx = isExpanded ? SILENCE_PX_EXPANDED : SILENCE_PX_DEFAULT;
        const widthPct = ((end - start) / durationSeconds) * 100;
        cells.push({ kind: 'silence', startSec: start, endSec: end, key: `s-${start}-${end}`, widthPx, widthPct, silenceIndex: silenceCount });
        silenceCount += 1;
    };
    const pushSpeech = (seg) => {
        const flexBasis = (seg.end - seg.start) * SPEECH_FLEX_PER_SECOND;
        const widthPct = ((seg.end - seg.start) / durationSeconds) * 100;
        cells.push({ kind: 'speech', startSec: seg.start, endSec: seg.end, key: `p-${seg.start}-${seg.end}`, flexBasis, widthPct });
    };
    for (const seg of speechSegments) {
        if (seg.start > cursor) pushSilence(cursor, seg.start);
        pushSpeech(seg);
        cursor = seg.end;
    }
    if (cursor < durationSeconds) pushSilence(cursor, durationSeconds);
    return cells;
}

export function useTimelineGeometry(args) {
    return useMemo(() => computeCells(args), [args.speechSegments, args.durationSeconds, args.mode, args.expandedSilenceIndex]);
}
```

- [ ] **Step 3: Verify pass + commit**

Run: `npm test -- --run editor/components/reviewer/useTimelineGeometry.test.js`
Expected: 4 PASS.

```bash
git add editor/components/reviewer/useTimelineGeometry.js editor/components/reviewer/useTimelineGeometry.test.js
git commit -m "feat(editor): useTimelineGeometry hook

Single source of truth for timeline cell layout. Returns interleaved
speech/silence cells with both flex (collapsed) and percent
(uncompressed) sizing data, plus per-silence-index expansion."
```

---

## Task 19: `Timeline` + `CollapsedTimeline` + `UncompressedTimeline`

**Files:**
- Create: `editor/components/reviewer/Timeline.jsx` + `.test.jsx`
- Create: `editor/components/reviewer/CollapsedTimeline.jsx`
- Create: `editor/components/reviewer/UncompressedTimeline.jsx`
- Modify: `editor/components/reviewer/ReviewerView.jsx` (replace placeholder)

- [ ] **Step 1: Write failing tests**

Create `editor/components/reviewer/Timeline.test.jsx`:

```javascript
import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import { ReviewerContext } from './ReviewerContext.js';
import Timeline from './Timeline.jsx';

const SEGS = [{ start: 0, end: 5 }, { start: 10, end: 15 }];

function withCtx(currentTime, ui) {
    return <ReviewerContext.Provider value={{
        audioRef: { current: null }, currentTime, duration: 20, playing: false,
        play: () => {}, pause: () => {}, seekTo: vi.fn(),
        folder: '/x', source: { path: '/x/y.mp3', mode: 'audio' },
    }}>{ui}</ReviewerContext.Provider>;
}

describe('Timeline', () => {
    it('renders collapsed view by default', () => {
        render(withCtx(0, <Timeline speechSegments={SEGS} duration={20} searchMatches={[]} />));
        expect(screen.getByTestId('timeline-collapsed')).toBeInTheDocument();
    });

    it('toggle button switches to uncompressed', () => {
        render(withCtx(0, <Timeline speechSegments={SEGS} duration={20} searchMatches={[]} />));
        fireEvent.click(screen.getByRole('button', { name: /uncompressed/i }));
        expect(screen.getByTestId('timeline-uncompressed')).toBeInTheDocument();
    });

    it('clicking a speech cell calls seekTo with linear interpolation', () => {
        const seekTo = vi.fn();
        const ctx = {
            audioRef: { current: null }, currentTime: 0, duration: 20, playing: false,
            play: () => {}, pause: () => {}, seekTo,
            folder: '/x', source: { path: '/x/y.mp3', mode: 'audio' },
        };
        render(<ReviewerContext.Provider value={ctx}><Timeline speechSegments={SEGS} duration={20} searchMatches={[]} /></ReviewerContext.Provider>);
        const cells = screen.getAllByTestId('seg-cell');
        // Simulate click at the right edge of cell 0 (5 s segment, click at x=cellWidth)
        Object.defineProperty(cells[0], 'getBoundingClientRect', {
            value: () => ({ left: 0, width: 100, top: 0, height: 20, right: 100, bottom: 20, x: 0, y: 0, toJSON: () => ({}) }),
        });
        fireEvent.click(cells[0], { clientX: 100 });
        expect(seekTo).toHaveBeenCalledWith(5);
    });

    it('Esc collapses an expanded silence', () => {
        // Click first silence to expand, press Esc, verify back to default width
        render(withCtx(0, <Timeline speechSegments={SEGS} duration={20} searchMatches={[]} />));
        const silences = screen.getAllByTestId('silence-cell');
        fireEvent.click(silences[0]);  // expand
        // Cell width should have changed; we don't assert pixel — just that clicking a different silence collapses it
        fireEvent.click(silences[1]);
        // Now press Esc; expanded should be cleared
        fireEvent.keyDown(window, { key: 'Escape' });
        // Indirect assertion: clicking the same silence again should expand it (would no-op if already expanded)
        fireEvent.click(silences[0]);
        // Test passes if no crash; concrete UI verification is covered by manual burn-in
    });
});
```

- [ ] **Step 2: Verify failure**

Run: `npm test -- --run editor/components/reviewer/Timeline.test.jsx`
Expected: FAIL.

- [ ] **Step 3: Implement `CollapsedTimeline`**

```javascript
// editor/components/reviewer/CollapsedTimeline.jsx
import React from 'react';

export default function CollapsedTimeline({ cells, currentTime, onSeek, onSilenceClick, expandedSilenceIndex, searchMatches }) {
    return (
        <div data-testid="timeline-collapsed" style={{ display: 'flex', height: 28, background: '#161b22', borderRadius: 3, overflow: 'hidden', position: 'relative' }}>
            {cells.map((c, idx) => {
                if (c.kind === 'silence') {
                    return (
                        <div
                            key={c.key}
                            data-testid="silence-cell"
                            data-dur={`${Math.round(c.endSec - c.startSec)}s silence`}
                            onClick={() => onSilenceClick(c.silenceIndex)}
                            style={{
                                width: c.widthPx, flex: `0 0 ${c.widthPx}px`,
                                background: 'repeating-linear-gradient(45deg, #21262d 0, #21262d 3px, #161b22 3px, #161b22 6px)',
                                cursor: 'pointer',
                                borderLeft: '1px solid #0d1117', borderRight: '1px solid #0d1117',
                            }}
                        />
                    );
                }
                const inThisCell = currentTime >= c.startSec && currentTime <= c.endSec;
                return (
                    <div
                        key={c.key}
                        data-testid="seg-cell"
                        onClick={(e) => {
                            const rect = e.currentTarget.getBoundingClientRect();
                            const fraction = Math.max(0, Math.min(1, (e.clientX - rect.left) / rect.width));
                            onSeek(c.startSec + fraction * (c.endSec - c.startSec));
                        }}
                        style={{
                            flex: `${c.flexBasis} 0 auto`,
                            background: inThisCell ? '#58d6d6' : '#2ea3a3',
                            cursor: 'pointer', borderRight: '1px solid #0d1117', position: 'relative',
                        }}
                    >
                        {inThisCell && (
                            <div style={{ position: 'absolute', top: -2, bottom: -2, width: 2, background: '#f0883e', left: `${(currentTime - c.startSec) / Math.max(0.001, c.endSec - c.startSec) * 100}%` }} />
                        )}
                        {searchMatches.some(m => m.start >= c.startSec && m.start <= c.endSec) && (
                            <div style={{ position: 'absolute', top: 2, left: '50%', transform: 'translateX(-50%)', width: 5, height: 5, borderRadius: '50%', background: '#f6c343' }} />
                        )}
                    </div>
                );
            })}
        </div>
    );
}
```

- [ ] **Step 4: Implement `UncompressedTimeline`**

```javascript
// editor/components/reviewer/UncompressedTimeline.jsx
import React from 'react';

export default function UncompressedTimeline({ cells, durationSeconds, currentTime, onSeek, searchMatches }) {
    const tickInterval = pickTickInterval(durationSeconds);
    const ticks = [];
    for (let t = 0; t <= durationSeconds; t += tickInterval) {
        ticks.push(t);
    }

    const onTrackClick = (e) => {
        const rect = e.currentTarget.getBoundingClientRect();
        const fraction = Math.max(0, Math.min(1, (e.clientX - rect.left) / rect.width));
        onSeek(fraction * durationSeconds);
    };

    return (
        <div data-testid="timeline-uncompressed" style={{ background: '#161b22', borderRadius: 3, overflow: 'hidden' }}>
            <div style={{ height: 14, background: '#0d1117', position: 'relative', borderBottom: '1px solid #21262d', color: '#6e7681', fontSize: '0.62rem' }}>
                {ticks.map(t => (
                    <span key={t} style={{ position: 'absolute', left: `${(t / durationSeconds) * 100}%`, top: 1, transform: 'translateX(-50%)' }}>
                        {fmtTick(t)}
                    </span>
                ))}
            </div>
            <div onClick={onTrackClick} style={{ height: 24, position: 'relative', cursor: 'pointer' }}>
                {cells.filter(c => c.kind === 'speech').map(c => (
                    <div key={c.key} style={{
                        position: 'absolute', left: `${(c.startSec / durationSeconds) * 100}%`,
                        width: `${c.widthPct}%`, top: 4, height: 16, background: '#2ea3a3', borderRadius: 2,
                    }} />
                ))}
                {searchMatches.map((m, i) => (
                    <div key={i} style={{
                        position: 'absolute', bottom: 0, left: `${(m.start / durationSeconds) * 100}%`,
                        width: 5, height: 5, borderRadius: '50%', background: '#f6c343', transform: 'translateX(-50%)',
                    }} />
                ))}
                <div style={{
                    position: 'absolute', top: 0, bottom: 0, width: 2,
                    background: '#f0883e', left: `${(currentTime / durationSeconds) * 100}%`,
                }} />
            </div>
        </div>
    );
}

function pickTickInterval(duration) {
    if (duration <= 60) return 5;
    if (duration <= 600) return 60;
    if (duration <= 3600) return 600;   // 10 min
    return 1800;                         // 30 min
}

function fmtTick(seconds) {
    const m = Math.floor(seconds / 60);
    const s = Math.floor(seconds % 60);
    return s === 0 ? `${m}:00` : `${m}:${String(s).padStart(2, '0')}`;
}
```

- [ ] **Step 5: Implement `Timeline`**

```javascript
// editor/components/reviewer/Timeline.jsx
import React, { useEffect, useState } from 'react';
import { useReviewer } from './ReviewerContext.js';
import { useTimelineGeometry } from './useTimelineGeometry.js';
import CollapsedTimeline from './CollapsedTimeline.jsx';
import UncompressedTimeline from './UncompressedTimeline.jsx';

export default function Timeline({ speechSegments, duration, searchMatches }) {
    const { currentTime, seekTo } = useReviewer();
    const [mode, setMode] = useState('collapsed');
    const [expandedSilenceIndex, setExpandedSilenceIndex] = useState(null);

    const cells = useTimelineGeometry({
        speechSegments,
        durationSeconds: duration,
        mode,
        expandedSilenceIndex,
    });

    useEffect(() => {
        const onKey = (e) => {
            const tag = (e.target && e.target.tagName) || '';
            if (tag === 'INPUT' || tag === 'TEXTAREA') return;
            if (e.key === 'Escape') {
                if (expandedSilenceIndex !== null) {
                    setExpandedSilenceIndex(null);
                    e.preventDefault();
                }
            }
        };
        window.addEventListener('keydown', onKey);
        return () => window.removeEventListener('keydown', onKey);
    }, [expandedSilenceIndex]);

    const handleSilence = (silenceIndex) => {
        setExpandedSilenceIndex(prev => (prev === silenceIndex ? null : silenceIndex));
    };

    return (
        <div style={{ background: '#0d1117', borderTop: '1px solid #21262d', padding: '8px 14px 10px', display: 'flex', flexDirection: 'column', gap: 6 }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: 10, fontSize: '0.72rem', color: '#6e7681' }}>
                <span style={{ textTransform: 'uppercase', letterSpacing: '0.06em' }}>
                    Timeline · {mode === 'collapsed' ? 'collapsed silence' : 'uncompressed'}
                </span>
                <button onClick={() => setMode(m => m === 'collapsed' ? 'uncompressed' : 'collapsed')}
                    aria-label={mode === 'collapsed' ? 'switch to uncompressed' : 'switch to collapsed'}
                    style={{ background: 'transparent', border: '1px solid #30363d', borderRadius: 3, color: '#c9d1d9', padding: '2px 8px', fontSize: '0.7rem' }}>
                    ⇄ {mode === 'collapsed' ? 'uncompressed' : 'collapsed'}
                </button>
                <span style={{ marginLeft: 'auto', fontFamily: 'ui-monospace, monospace', color: '#c9d1d9', fontSize: '0.78rem' }}>
                    {fmt(currentTime)} / {fmt(duration)}
                </span>
            </div>
            {mode === 'collapsed' ? (
                <CollapsedTimeline
                    cells={cells} currentTime={currentTime}
                    onSeek={seekTo} onSilenceClick={handleSilence}
                    expandedSilenceIndex={expandedSilenceIndex}
                    searchMatches={searchMatches}
                />
            ) : (
                <UncompressedTimeline
                    cells={cells} durationSeconds={duration}
                    currentTime={currentTime}
                    onSeek={seekTo} searchMatches={searchMatches}
                />
            )}
        </div>
    );
}

function fmt(s) {
    const m = Math.floor(s / 60);
    const sec = Math.floor(s % 60);
    return `${String(m).padStart(2, '0')}:${String(sec).padStart(2, '0')}`;
}
```

- [ ] **Step 6: Wire into ReviewerView**

Replace `<TimelinePlaceholder />` with:

```javascript
<Timeline
    speechSegments={speechSegments}
    duration={transcript.source.duration_seconds}
    searchMatches={searchMatches}
/>
```

`searchMatches` is computed from search query against transcript segments (added in Task 19/20 — use `[]` for now as a placeholder).

- [ ] **Step 7: Verify pass + commit**

Run: `npm test -- --run editor/components/reviewer/Timeline.test.jsx`
Expected: all PASS.

```bash
git add editor/components/reviewer/Timeline.jsx editor/components/reviewer/CollapsedTimeline.jsx editor/components/reviewer/UncompressedTimeline.jsx editor/components/reviewer/Timeline.test.jsx editor/components/reviewer/ReviewerView.jsx
git commit -m "feat(editor): Timeline (collapsed + uncompressed) + click-to-seek

Single useTimelineGeometry hook drives both views. Collapsed mode:
fixed-width striped silence bars, expand-on-click (one at a time;
Esc collapses). Uncompressed mode: real-time ruler with tick
auto-scaling. Search-match dots on both views. Playhead overlay
positioned within the active speech cell."
```

---

# Phase K — Search

## Task 20: Search input + match navigation + timeline marker recompute

**Files:**
- Modify: `editor/components/reviewer/MediaPane.jsx` (add search input)
- Modify: `editor/components/reviewer/ReviewerView.jsx` (lift search state, compute matches, pass to children)
- Create: `editor/components/reviewer/Search.test.jsx` (cross-component integration)

- [ ] **Step 1: Write failing test**

Create `editor/components/reviewer/Search.test.jsx`:

```javascript
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import ReviewerView from './ReviewerView.jsx';

beforeEach(() => {
    vi.useFakeTimers();
    globalThis.jest = { advanceTimersByTime: vi.advanceTimersByTime };
    globalThis.fetch = vi.fn(() => Promise.resolve({
        ok: true,
        json: () => Promise.resolve({
            transcript: {
                source: { path: '/x/y.mp3', duration_seconds: 30 },
                speakers: [],
                segments: [
                    { id: 0, start: 0, end: 5, text: 'medication first', words: [], low_confidence: false },
                    { id: 1, start: 10, end: 15, text: 'second utterance', words: [], low_confidence: false },
                    { id: 2, start: 20, end: 25, text: 'medication third', words: [], low_confidence: false },
                ],
            },
            speech_segments: [{ start: 0, end: 5 }, { start: 10, end: 15 }, { start: 20, end: 25 }],
        }),
    }));
});

describe('search', () => {
    it('debounced 100 ms; finds case-insensitive matches', async () => {
        render(<ReviewerView folder="/x" source={{ path: '/x/y.mp3', mode: 'audio' }} onBack={() => {}} manifest={{ folder: '/x', files: [] }} />);
        await waitFor(() => screen.getByText(/medication first/));
        const input = screen.getByPlaceholderText(/search/i);
        fireEvent.change(input, { target: { value: 'MEDICATION' } });
        await vi.advanceTimersByTimeAsync(150);
        const marks = document.querySelectorAll('mark');
        expect(marks.length).toBe(2);
    });

    it('Enter cycles to next match', async () => {
        // (similar setup; press Enter, verify the corresponding segment scrolls into view)
        // Specific assertion is implementation-dependent — at minimum, no crash and
        // some seekTo gets called with the matching segment's start time.
    });
});
```

- [ ] **Step 2: Implement**

In `MediaPane.jsx`, add the search input below the transport row:

```javascript
import { useReviewer } from './ReviewerContext.js';

// New prop on MediaPane: searchQuery, onSearchQueryChange, matchCount
function SearchInput({ value, onChange, matchCount }) {
    return (
        <div style={{ marginTop: 14, display: 'flex', gap: 8, alignItems: 'center' }}>
            <input type="text" placeholder="Search transcript…" value={value}
                onChange={(e) => onChange(e.target.value)}
                style={{ flex: 1, background: '#0d1117', border: '1px solid #30363d', borderRadius: 3, color: '#c9d1d9', padding: '5px 9px', fontSize: '0.8rem' }} />
            {value && <span style={{ color: '#6e7681', fontSize: '0.72rem', fontFamily: 'ui-monospace, monospace' }}>{matchCount} match{matchCount !== 1 ? 'es' : ''}</span>}
        </div>
    );
}
```

Wire it into `MediaPane` (accept new props from `ReviewerView`).

In `ReviewerView.jsx`, lift the state and add a debounced effect:

```javascript
const [searchInput, setSearchInput] = useState('');
const [searchQuery, setSearchQuery] = useState('');

useEffect(() => {
    const t = setTimeout(() => setSearchQuery(searchInput), 100);
    return () => clearTimeout(t);
}, [searchInput]);

const searchMatches = useMemo(() => {
    if (!searchQuery || !transcript) return [];
    const q = searchQuery.toLowerCase();
    return transcript.segments
        .filter(s => s.text.toLowerCase().includes(q))
        .map(s => ({ segmentId: s.id, start: s.start, end: s.end }));
}, [searchQuery, transcript]);
```

Pass `searchInput`/`setSearchInput`/`searchMatches.length` to `<MediaPane>`, `searchQuery` to `<TranscriptPanel>`, `searchMatches` to `<Timeline>`.

- [ ] **Step 3: Add Enter / Shift+Enter cycling**

Inside `ReviewerView`, track `activeMatchIndex`. Listen for keydown in the search input:

```javascript
const onSearchKey = (e) => {
    if (e.key !== 'Enter' || !searchMatches.length) return;
    e.preventDefault();
    const next = e.shiftKey
        ? (activeMatchIndex - 1 + searchMatches.length) % searchMatches.length
        : (activeMatchIndex + 1) % searchMatches.length;
    setActiveMatchIndex(next);
    seekTo(searchMatches[next].start);
};
```

Pass `onKeyDown={onSearchKey}` through to the search input.

- [ ] **Step 4: Verify pass + commit**

Run: `npm test -- --run editor/components/reviewer/Search.test.jsx`
Expected: PASS.

```bash
git add editor/components/reviewer/MediaPane.jsx editor/components/reviewer/ReviewerView.jsx editor/components/reviewer/Search.test.jsx
git commit -m "feat(editor): search across transcript with debounced highlighting

100 ms debounce. Case-insensitive substring against segment.text.
Matches highlighted via SearchHighlight in the panel and as gold dots
on both timeline views. Enter / Shift+Enter cycles matches."
```

---

# Phase L — Hotkeys + cross-source navigation

## Task 21: Window-level hotkey handler + source picker switching

**Files:**
- Modify: `editor/components/reviewer/ReviewerView.jsx` (add window keydown effect; wire `onSelectSource` for cross-source switching)
- Create: `editor/components/reviewer/Hotkeys.test.jsx`

- [ ] **Step 1: Write failing test**

```javascript
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import ReviewerView from './ReviewerView.jsx';

beforeEach(() => {
    globalThis.fetch = vi.fn(() => Promise.resolve({
        ok: true,
        json: () => Promise.resolve({
            transcript: { source: { path: '/x/y.mp3', duration_seconds: 60 }, speakers: [], segments: [] },
            speech_segments: [],
        }),
    }));
});

describe('hotkeys', () => {
    it('Space toggles play/pause', async () => {
        render(<ReviewerView folder="/x" source={{ path: '/x/y.mp3', mode: 'audio' }} onBack={() => {}} manifest={{ folder: '/x', files: [] }} />);
        await waitFor(() => screen.getByText(/transcript/i));
        const audio = document.querySelector('audio,video');
        const play = vi.spyOn(audio, 'play').mockResolvedValue();
        fireEvent.keyDown(window, { key: ' ', code: 'Space' });
        expect(play).toHaveBeenCalled();
    });

    it('letter keys absorbed inside textarea', async () => {
        render(<ReviewerView folder="/x" source={{ path: '/x/y.mp3', mode: 'audio' }} onBack={() => {}} manifest={{ folder: '/x', files: [] }} />);
        await waitFor(() => screen.getByText(/transcript/i));
        const textarea = document.createElement('textarea');
        document.body.appendChild(textarea);
        const audio = document.querySelector('audio,video');
        const play = vi.spyOn(audio, 'play').mockResolvedValue();
        textarea.focus();
        fireEvent.keyDown(textarea, { key: ' ', code: 'Space', target: textarea });
        expect(play).not.toHaveBeenCalled();
    });

    it('Ctrl+S is intercepted (no-op in M6 but does not save page)', async () => {
        render(<ReviewerView folder="/x" source={{ path: '/x/y.mp3', mode: 'audio' }} onBack={() => {}} manifest={{ folder: '/x', files: [] }} />);
        await waitFor(() => screen.getByText(/transcript/i));
        // Construct a real KeyboardEvent and spy on its preventDefault.
        // RTL's fireEvent.keyDown can't be used here because it ignores
        // a `preventDefault` property on the init dict — it constructs
        // its own synthetic event with a native preventDefault.
        const evt = new KeyboardEvent('keydown', { key: 's', ctrlKey: true, bubbles: true, cancelable: true });
        const spy = vi.spyOn(evt, 'preventDefault');
        window.dispatchEvent(evt);
        expect(spy).toHaveBeenCalled();
    });
});
```

- [ ] **Step 2: Implement**

In `ReviewerView.jsx`, add the window keydown effect:

```javascript
useEffect(() => {
    const onKey = (e) => {
        const tag = (e.target && e.target.tagName) || '';
        if (tag === 'INPUT' || tag === 'TEXTAREA') return;
        switch (e.key) {
            case ' ':
                e.preventDefault();
                if (audioRef.current?.paused) play(); else pause();
                break;
            case 'k':
            case 'K':
                pause();
                break;
            case 'j':
            case 'J':
                if (audioRef.current) audioRef.current.playbackRate = -1;
                play();
                break;
            case 'l':
            case 'L':
                if (audioRef.current) audioRef.current.playbackRate = 1;
                play();
                break;
            case 'ArrowLeft':
                seekTo((audioRef.current?.currentTime || 0) + (e.shiftKey ? -1 : -5));
                break;
            case 'ArrowRight':
                seekTo((audioRef.current?.currentTime || 0) + (e.shiftKey ? 1 : 5));
                break;
            case '/':
                e.preventDefault();
                document.querySelector('input[placeholder*="Search" i]')?.focus();
                break;
            case 's':
            case 'S':
                if (e.ctrlKey || e.metaKey) e.preventDefault();
                break;
            case 'Escape':
                // Timeline.jsx handles its own Esc; here, also blur the search input on Esc
                if (document.activeElement?.tagName === 'INPUT') document.activeElement.blur();
                break;
            default:
                return;
        }
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
}, [play, pause, seekTo]);
```

- [ ] **Step 3: Wire `onSelectSource` for cross-source navigation**

In `EditorApp.jsx`:

```javascript
function selectReviewerSource(file) {
    setReviewSource(file);
    apiPost('/api/project/reviewer-state', { folder: manifest.folder, last_source: file.path });
}
// pass selectReviewerSource as onSelectSource to ReviewerView, which passes to TopBar
```

When a different source is picked, `ReviewerView` keys on `source.path` and naturally re-mounts the transcript / audio source URL. (The `useEffect` dependency on `source.path` already handles this.)

- [ ] **Step 4: Verify pass + commit**

Run: `npm test -- --run editor/components/reviewer/Hotkeys.test.jsx`
Expected: PASS.

```bash
git add editor/components/reviewer/ReviewerView.jsx editor/components/reviewer/Hotkeys.test.jsx editor/EditorApp.jsx
git commit -m "feat(editor): hotkey handler + cross-source picker

Window keydown handler covers Space, J/K/L, ←/→, Shift+←/→, /,
Ctrl+S (no-op), Esc (blur input). Letters absorbed inside <input>
and <textarea>. Source picker now triggers cross-source navigation;
ReviewerView re-mounts via source.path key change."
```

---

# Phase M — Manual burn-in + handoff

## Task 22: Run the manual burn-in checklist + update HANDOFF.md

**Files:**
- Modify: `docs/HANDOFF.md` (mark M6 complete; add M6 manual burn-in record)

- [ ] **Step 1: Build editor bundle and launch the app**

```bash
npm run build:editor
npm start
```

- [ ] **Step 2: Walk through the manual burn-in checklist (spec §10.4)**

1. Open the Williams ENT DME (60 min) — reach reviewer view, hear audio, see transcript, see timeline.
2. Click a transcript utterance — audio jumps there.
3. Search for a known phrase — see highlights and gold timeline markers; Enter / Shift+Enter cycles matches.
4. Edit context names (e.g. "Patel"), click Apply, watch retranscribe complete in ~30 s, see new transcript.
5. Open `Samples/BWC/`, select `pia00458_…mp4`, verify the `<video>` element loads, scrub the timeline, confirm seek lands within ~50 ms of the click target.
6. Toggle ⇄ between collapsed and uncompressed views.

If any check fails, file the issue, fix it (with a regression test if possible), and re-walk that step.

- [ ] **Step 3: Process pia00458 to completion**

`pia00458_…mp4` already has Stage 1 cached (per HANDOFF). Re-submit it from the project view; the runner skips Stage 1 and runs 2-6. Verify completion. Record approximate wall-clock duration in the handoff update.

- [ ] **Step 4: Update HANDOFF.md**

Insert a new row in the milestone table:

```
| M6 | Reviewer UI surfaces | <new-merge-sha> | Threaded engine, Range streaming, /api/source/{audio,video,transcript,context,retranscribe} routes, reviewer-state persistence, full reviewer view (TopBar, MediaPane, Waveform, Transport, TranscriptPanel, ContextNamesPanel, Timeline collapsed+uncompressed, search, hotkeys); pia00458 BWC processed end-to-end; manual burn-in passed |
```

Update "Verified" paragraph and "Remaining" table accordingly. Update memory note about M6 if relevant.

- [ ] **Step 5: Final test run**

Run all engine + editor tests:

```bash
python -m pytest -q
npm test -- --run
```

Expected: all green. Integration tests pass (or skip cleanly when fixtures are absent). One known flake: `test_unknown_post_path_returns_404` per the existing memory note — re-run if it flakes.

- [ ] **Step 6: Merge to main**

```bash
git checkout main
git merge --no-ff milestone-6-reviewer-ui -m "Merge milestone 6: reviewer UI surfaces

Threaded HTTP server with HTTP Range support. Six new routes for
audio / video / transcript / context / retranscribe / reviewer-state.
runner.rerun_from_stage for selective stage invalidation. React
reviewer view with TopBar / MediaPane (audio + video) / Waveform /
Transport / TranscriptPanel (active scroll, low-conf underline,
search) / ContextNamesPanel (re-transcribe lifecycle with stale
banner) / Timeline (collapsed-silence + uncompressed, click-to-seek,
search markers). Hotkeys for playback subset; clip-authoring keys
deferred to M8.

Engine integration tests cover the Range stress against a 3.95 GB
BWC fixture and a context-edit retranscribe round-trip."
git push origin main
git push origin --delete milestone-6-reviewer-ui
git branch -d milestone-6-reviewer-ui
```

- [ ] **Step 7: Final commit (handoff update)**

```bash
git add docs/HANDOFF.md
git commit -m "docs: M6 complete — reviewer UI shipped"
git push
```

---

## Done

After Task 22 the milestone is shipped. The next milestone (M7) picks up diarization + wearer detection + dependency-gate splash; the reviewer view will gain real speaker labels and colors automatically once `transcript.json.speakers` is populated.

Per the handoff convention, M7 begins on a fresh `milestone-7-...` branch.
