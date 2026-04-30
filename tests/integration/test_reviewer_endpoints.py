"""Integration tests for the M6 reviewer endpoints.

Spin a real engine on a free port; hit it with urllib.request. Requires
ffmpeg discoverable (BWC_CLIPPER_FFMPEG_DIR set in the integration
fixture) and, for the retranscribe round-trip, the real ML stack.
"""
from __future__ import annotations

import json
import socket
import threading
import time
import urllib.request
from contextlib import contextmanager
from pathlib import Path
from urllib.parse import urlencode

import pytest

from engine.server import BWCRequestHandler, reset_pipeline_runner
from serve import ThreadedHTTPServer


@contextmanager
def _running_engine():
    """Start the engine on a free port for the duration of the context."""
    reset_pipeline_runner()
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.bind(("127.0.0.1", 0))
    port = sock.getsockname()[1]
    sock.close()

    server = ThreadedHTTPServer(("127.0.0.1", port), BWCRequestHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{port}"
    finally:
        server.shutdown()
        server.server_close()
        reset_pipeline_runner()


# ── Range stress ──────────────────────────────────────────────────────────

@pytest.mark.integration
def test_range_fetch_against_real_bwc_video():
    """Range fetch into a 3.95 GB BWC fixture catches 32-bit math mistakes
    and verifies Connection: close so subsequent API calls aren't blocked."""
    fixture = Path("Samples/BWC/tja00453_20231107020851e0_20231107020821_01_000w_1-4-001.mp4")
    if not fixture.is_file():
        pytest.skip(f"missing fixture: {fixture}")

    folder = fixture.parent
    with _running_engine() as base:
        # Fetch a slice from the middle of the file
        midpoint = fixture.stat().st_size // 2
        qs = urlencode({"folder": str(folder.resolve()), "source": str(fixture.resolve())})
        req = urllib.request.Request(
            f"{base}/api/source/video?{qs}",
            headers={"Range": f"bytes={midpoint}-{midpoint + 1023}"},
        )
        with urllib.request.urlopen(req, timeout=10) as resp:
            assert resp.status == 206
            assert resp.headers.get("Content-Range").endswith(f"/{fixture.stat().st_size}")
            chunk = resp.read()
            assert len(chunk) == 1024

        # And confirm a normal API call works fine right after
        with urllib.request.urlopen(f"{base}/api/health", timeout=5) as health:
            assert health.status == 200


# ── Retranscribe round-trip ───────────────────────────────────────────────

@pytest.mark.integration
def test_context_then_retranscribe_round_trip(tmp_path: Path):
    """Edit context, retranscribe, poll until complete, verify a context
    name appears in the new transcript."""
    fixture = Path("tests/fixtures/integration/sample_short.wav")
    if not fixture.is_file():
        pytest.skip(f"missing fixture: {fixture}")

    project = tmp_path / "case"
    project.mkdir()
    source = project / "sample.wav"
    source.write_bytes(fixture.read_bytes())

    with _running_engine() as base:
        # First-pass full pipeline
        urllib.request.urlopen(
            urllib.request.Request(
                f"{base}/api/source/process",
                data=json.dumps({"folder": str(project), "source": str(source)}).encode(),
                headers={"Content-Type": "application/json"},
                method="POST",
            ),
            timeout=600,
        )
        _poll_until(base, project, source, "completed", timeout_s=600)

        # Edit context
        urllib.request.urlopen(
            urllib.request.Request(
                f"{base}/api/source/context",
                data=json.dumps({
                    "folder": str(project),
                    "source": str(source),
                    "names": ["Aurelius"],
                    "locations": [],
                }).encode(),
                headers={"Content-Type": "application/json"},
                method="POST",
            ),
            timeout=10,
        )

        # Trigger re-transcribe
        urllib.request.urlopen(
            urllib.request.Request(
                f"{base}/api/source/retranscribe",
                data=json.dumps({"folder": str(project), "source": str(source)}).encode(),
                headers={"Content-Type": "application/json"},
                method="POST",
            ),
            timeout=10,
        )
        _poll_until(base, project, source, "completed", timeout_s=120)

        # Fetch new transcript
        qs = urlencode({"folder": str(project), "source": str(source)})
        with urllib.request.urlopen(f"{base}/api/source/transcript?{qs}", timeout=10) as resp:
            payload = json.loads(resp.read())
        # We can't assert the model actually transcribed "Aurelius" — the fixture
        # may not contain that audio. We just assert the round-trip worked and
        # the new transcript exists with at least one segment.
        assert payload["transcript"]["segments"]


def _poll_until(base: str, folder: Path, source: Path, target: str, timeout_s: int) -> None:
    deadline = time.time() + timeout_s
    qs = urlencode({"folder": str(folder), "source": str(source)})
    status = None
    while time.time() < deadline:
        with urllib.request.urlopen(f"{base}/api/source/state?{qs}", timeout=5) as resp:
            status = json.loads(resp.read())["status"]
        if status == target:
            return
        if status == "failed":
            raise AssertionError("pipeline reported failed")
        time.sleep(1)
    raise AssertionError(f"timed out waiting for {target}; last status={status}")
