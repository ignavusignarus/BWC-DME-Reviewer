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


def test_process_endpoint_submits_pipeline_and_returns_status(running_server, tmp_path: Path):
    source = tmp_path / "officer.mp4"
    _touch(source, b"x")

    def _ffmpeg_writes_output(args, **kwargs):
        Path(args[-1]).touch()
        return ""

    with patch("engine.pipeline.extract.probe_audio_tracks") as probe_mock, \
         patch("engine.pipeline.extract.run_ffmpeg", side_effect=_ffmpeg_writes_output), \
         patch("engine.pipeline.normalize.run_loudnorm_measure",
               return_value={"input_i": "-12", "input_tp": "-1", "input_lra": "5",
                             "input_thresh": "-20", "target_offset": "0"}), \
         patch("engine.pipeline.normalize.run_ffmpeg", side_effect=_ffmpeg_writes_output):
        probe_mock.return_value = [{"index": 0, "codec_name": "aac", "sample_rate": 48000, "channels": 1, "duration_seconds": 1.0}]
        response = requests.post(
            f"http://127.0.0.1:{running_server}/api/source/process",
            json={"folder": str(tmp_path), "source": str(source)},
            timeout=5,
        )
    assert response.status_code == 200
    body = response.json()
    assert (
        body["status"] == "queued"
        or body["status"].startswith("running:")
        or body["status"] == "completed"
    )


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


def test_state_endpoint_completed_after_pipeline(running_server, tmp_path: Path):
    source = tmp_path / "officer.mp4"
    _touch(source, b"x")

    def _ffmpeg_writes_output(args, **kwargs):
        Path(args[-1]).touch()
        return ""

    with patch("engine.pipeline.extract.probe_audio_tracks") as probe_mock, \
         patch("engine.pipeline.extract.run_ffmpeg", side_effect=_ffmpeg_writes_output), \
         patch("engine.pipeline.normalize.run_loudnorm_measure",
               return_value={"input_i": "-12", "input_tp": "-1", "input_lra": "5",
                             "input_thresh": "-20", "target_offset": "0"}), \
         patch("engine.pipeline.normalize.run_ffmpeg", side_effect=_ffmpeg_writes_output):
        probe_mock.return_value = [{"index": 0, "codec_name": "aac", "sample_rate": 48000, "channels": 1, "duration_seconds": 1.0}]
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
