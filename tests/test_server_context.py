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
