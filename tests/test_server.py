"""Tests for engine.server.

These tests bind to a free port, start the server, hit it, and shut down.
They use threading.Thread + requests; no subprocess.
"""
import threading
from http.server import HTTPServer

import pytest
import requests

from engine.server import BWCRequestHandler


@pytest.fixture
def running_server():
    """Start engine.server on a random local port. Yield (port, shutdown)."""
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


def test_health_endpoint_returns_200(running_server):
    port = running_server
    response = requests.get(f"http://127.0.0.1:{port}/api/health", timeout=2)
    assert response.status_code == 200


def test_health_endpoint_returns_json_with_status_ok(running_server):
    port = running_server
    response = requests.get(f"http://127.0.0.1:{port}/api/health", timeout=2)
    body = response.json()
    assert body == {"status": "ok"}


def test_unknown_path_returns_404(running_server):
    port = running_server
    response = requests.get(f"http://127.0.0.1:{port}/api/nope", timeout=2)
    assert response.status_code == 404


def test_version_endpoint_returns_engine_version(running_server):
    """Confirms the /api/version handler exposes engine.version.get_version."""
    from engine.version import get_version

    port = running_server
    response = requests.get(f"http://127.0.0.1:{port}/api/version", timeout=2)
    assert response.status_code == 200
    body = response.json()
    assert body == {"version": get_version()}
