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
