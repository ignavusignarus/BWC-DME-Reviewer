"""HTTP handler tests for the M6 GET routes (audio, video, transcript).

Exercises the route table by faking BaseHTTPRequestHandler — same pattern
as the existing test_server_routes.py.
"""
from __future__ import annotations

import io
import json
from pathlib import Path
from unittest.mock import MagicMock
from urllib.parse import urlencode

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


def test_audio_route_415_when_extension_unknown(tmp_path: Path):
    folder = tmp_path / "case"
    folder.mkdir()
    source = folder / "exam.txt"  # not audio, not video
    source.write_bytes(b"x")
    qs = urlencode({"folder": str(folder), "source": str(source)})
    handler = _make_handler("GET", f"/api/source/audio?{qs}")
    handler.do_GET()
    assert _last_status(handler) == 415


# ── /api/source/transcript ────────────────────────────────────────────────

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
