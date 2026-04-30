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
