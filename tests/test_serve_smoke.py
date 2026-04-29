"""End-to-end smoke test: launch serve.py as a subprocess, parse the port from
its stdout, hit /api/health over HTTP, then kill the process.

This exercises the same code path Electron will use to spawn the engine.
"""
import os
import subprocess
import sys
import time
from pathlib import Path

import pytest
import requests

REPO_ROOT = Path(__file__).resolve().parent.parent
SERVE_PY = REPO_ROOT / "serve.py"


@pytest.mark.smoke
def test_serve_py_starts_and_serves_health():
    env = os.environ.copy()
    env["PYTHONUNBUFFERED"] = "1"
    proc = subprocess.Popen(
        [sys.executable, str(SERVE_PY)],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        cwd=str(REPO_ROOT),
        env=env,
        text=True,
    )
    try:
        port = None
        deadline = time.time() + 10  # seconds
        while time.time() < deadline:
            line = proc.stdout.readline()
            if not line:
                time.sleep(0.05)
                continue
            line = line.strip()
            if line.startswith("BWC_CLIPPER_PORT="):
                port = int(line.split("=", 1)[1])
                break
        assert port is not None, "serve.py did not print BWC_CLIPPER_PORT= within 10s"

        # Hit /api/health
        response = requests.get(f"http://127.0.0.1:{port}/api/health", timeout=2)
        assert response.status_code == 200
        assert response.json() == {"status": "ok"}
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=3)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait()
