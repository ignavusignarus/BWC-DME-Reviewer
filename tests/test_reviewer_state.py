"""reviewer_state module + GET/POST /api/project/reviewer-state tests."""
from __future__ import annotations

import io
import json
from pathlib import Path
from unittest.mock import MagicMock

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
