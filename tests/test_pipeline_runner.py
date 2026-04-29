"""Tests for engine.pipeline.runner — single-worker job dispatch."""
import time
from pathlib import Path
from unittest.mock import patch

import pytest


def _touch(p: Path, content: bytes = b""):
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_bytes(content)


def test_runner_get_status_idle_for_unprocessed_source(tmp_path: Path):
    from engine.pipeline.runner import PipelineRunner

    source = tmp_path / "x.mp4"
    _touch(source, b"x")

    runner = PipelineRunner()
    try:
        status = runner.get_status(tmp_path, source)
        assert status == "idle"
    finally:
        runner.shutdown()


def test_runner_submit_extract_runs_then_marks_completed(tmp_path: Path):
    from engine.pipeline.runner import PipelineRunner

    source = tmp_path / "x.mp4"
    _touch(source, b"x")

    runner = PipelineRunner()
    try:
        with patch("engine.pipeline.extract.probe_audio_tracks") as probe_mock, \
             patch("engine.pipeline.extract.run_ffmpeg", return_value=""):
            probe_mock.return_value = [
                {"index": 0, "codec_name": "aac", "sample_rate": 48000, "channels": 1, "duration_seconds": 1.0},
            ]
            future = runner.submit_extract(tmp_path, source)
            future.result(timeout=5)
        status = runner.get_status(tmp_path, source)
        assert status == "completed"
    finally:
        runner.shutdown()


def test_runner_get_status_failed_after_extract_error(tmp_path: Path):
    from engine.pipeline.runner import PipelineRunner

    source = tmp_path / "x.mp4"
    _touch(source, b"x")

    runner = PipelineRunner()
    try:
        with patch("engine.pipeline.extract.probe_audio_tracks") as probe_mock, \
             patch("engine.pipeline.extract.run_ffmpeg", side_effect=RuntimeError("boom")):
            probe_mock.return_value = [{"index": 0, "codec_name": "aac", "sample_rate": 48000, "channels": 1, "duration_seconds": 1.0}]
            future = runner.submit_extract(tmp_path, source)
            with pytest.raises(RuntimeError):
                future.result(timeout=5)
        assert runner.get_status(tmp_path, source) == "failed"
    finally:
        runner.shutdown()


def test_runner_submit_idempotent_when_already_completed(tmp_path: Path):
    """Submitting a source whose pipeline-state.json shows extract=completed
    returns a completed Future immediately without re-running ffmpeg."""
    from engine.pipeline.runner import PipelineRunner

    source = tmp_path / "x.mp4"
    _touch(source, b"x")

    runner = PipelineRunner()
    try:
        with patch("engine.pipeline.extract.probe_audio_tracks") as probe_mock, \
             patch("engine.pipeline.extract.run_ffmpeg", return_value="") as ffmpeg_mock:
            probe_mock.return_value = [
                {"index": 0, "codec_name": "aac", "sample_rate": 48000, "channels": 1, "duration_seconds": 1.0},
            ]
            runner.submit_extract(tmp_path, source).result(timeout=5)
            initial_call_count = ffmpeg_mock.call_count
            # Second submit should not invoke ffmpeg again.
            runner.submit_extract(tmp_path, source).result(timeout=5)
            assert ffmpeg_mock.call_count == initial_call_count
    finally:
        runner.shutdown()
