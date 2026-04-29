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
