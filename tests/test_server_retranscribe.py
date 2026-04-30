"""POST /api/source/retranscribe tests — invokes runner.rerun_from_stage."""
from __future__ import annotations

import io
import json
from pathlib import Path
from unittest.mock import MagicMock, patch

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

    fake_runner.rerun_from_stage.assert_called_once_with("transcribe", Path(str(folder)).resolve(), Path(str(source)).resolve())
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


def test_retranscribe_400_when_source_outside_folder(tmp_path: Path):
    folder = tmp_path / "case"
    folder.mkdir()
    other = tmp_path / "elsewhere.mp3"
    other.write_bytes(b"x")

    handler = _post({"folder": str(folder), "source": str(other)})
    fake_runner = MagicMock()
    with patch("engine.server.get_pipeline_runner", return_value=fake_runner):
        handler.do_POST()
    assert _last_status(handler) == 400
    fake_runner.rerun_from_stage.assert_not_called()
