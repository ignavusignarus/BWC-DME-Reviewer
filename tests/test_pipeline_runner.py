"""Tests for engine.pipeline.runner — chained pipeline dispatch."""
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
        assert runner.get_status(tmp_path, source) == "idle"
    finally:
        runner.shutdown()


def test_runner_submit_pipeline_runs_extract_then_normalize(tmp_path: Path):
    from engine.pipeline.runner import PipelineRunner

    source = tmp_path / "x.mp4"
    _touch(source, b"x")

    runner = PipelineRunner()
    try:
        with patch("engine.pipeline.extract.probe_audio_tracks") as probe_mock, \
             patch("engine.pipeline.extract.run_ffmpeg", return_value=""), \
             patch("engine.pipeline.normalize.run_loudnorm_measure",
                   return_value={"input_i": "-12", "input_tp": "-1", "input_lra": "5",
                                 "input_thresh": "-20", "target_offset": "0"}), \
             patch("engine.pipeline.normalize.run_ffmpeg", return_value=""):
            probe_mock.return_value = [
                {"index": 0, "codec_name": "aac", "sample_rate": 48000, "channels": 1, "duration_seconds": 1.0},
            ]
            future = runner.submit_pipeline(tmp_path, source)
            future.result(timeout=5)
        assert runner.get_status(tmp_path, source) == "completed"
    finally:
        runner.shutdown()


def test_runner_get_status_failed_after_normalize_error(tmp_path: Path):
    from engine.pipeline.runner import PipelineRunner

    source = tmp_path / "x.mp4"
    _touch(source, b"x")

    runner = PipelineRunner()
    try:
        with patch("engine.pipeline.extract.probe_audio_tracks") as probe_mock, \
             patch("engine.pipeline.extract.run_ffmpeg", return_value=""), \
             patch("engine.pipeline.normalize.run_loudnorm_measure",
                   side_effect=RuntimeError("boom-norm")):
            probe_mock.return_value = [
                {"index": 0, "codec_name": "aac", "sample_rate": 48000, "channels": 1, "duration_seconds": 1.0},
            ]
            future = runner.submit_pipeline(tmp_path, source)
            with pytest.raises(RuntimeError):
                future.result(timeout=5)
        assert runner.get_status(tmp_path, source) == "failed"
    finally:
        runner.shutdown()


def test_runner_get_status_failed_after_extract_error(tmp_path: Path):
    from engine.pipeline.runner import PipelineRunner

    source = tmp_path / "x.mp4"
    _touch(source, b"x")

    runner = PipelineRunner()
    try:
        with patch("engine.pipeline.extract.probe_audio_tracks") as probe_mock, \
             patch("engine.pipeline.extract.run_ffmpeg", side_effect=RuntimeError("boom-extract")):
            probe_mock.return_value = [
                {"index": 0, "codec_name": "aac", "sample_rate": 48000, "channels": 1, "duration_seconds": 1.0},
            ]
            future = runner.submit_pipeline(tmp_path, source)
            with pytest.raises(RuntimeError):
                future.result(timeout=5)
        assert runner.get_status(tmp_path, source) == "failed"
    finally:
        runner.shutdown()


def test_runner_skips_extract_if_already_completed(tmp_path: Path):
    """If extract was previously completed, submit_pipeline only runs normalize."""
    from engine.pipeline.runner import PipelineRunner
    from engine.pipeline.extract import run_extract_stage
    from engine.source import source_cache_dir

    source = tmp_path / "x.mp4"
    _touch(source, b"x")

    # Pre-run extract so its state.json says completed
    cache_dir = source_cache_dir(tmp_path, source)
    with patch("engine.pipeline.extract.probe_audio_tracks") as probe_mock, \
         patch("engine.pipeline.extract.run_ffmpeg", return_value=""):
        probe_mock.return_value = [
            {"index": 0, "codec_name": "aac", "sample_rate": 48000, "channels": 1, "duration_seconds": 1.0},
        ]
        run_extract_stage(source, cache_dir)

    runner = PipelineRunner()
    try:
        with patch("engine.pipeline.extract.run_ffmpeg") as extract_mock, \
             patch("engine.pipeline.normalize.run_loudnorm_measure",
                   return_value={"input_i": "-12", "input_tp": "-1", "input_lra": "5",
                                 "input_thresh": "-20", "target_offset": "0"}), \
             patch("engine.pipeline.normalize.run_ffmpeg", return_value="") as norm_mock:
            # Need an extracted/track0.wav for normalize to read
            extracted = cache_dir / "extracted" / "track0.wav"
            extracted.parent.mkdir(parents=True, exist_ok=True)
            extracted.write_bytes(b"fake")

            future = runner.submit_pipeline(tmp_path, source)
            future.result(timeout=5)

            # Extract's run_ffmpeg should NOT have been called this time
            assert extract_mock.call_count == 0
            # Normalize's run_ffmpeg should have been called once (one track)
            assert norm_mock.call_count == 1
        assert runner.get_status(tmp_path, source) == "completed"
    finally:
        runner.shutdown()


def test_runner_get_status_returns_running_with_stage_name(tmp_path: Path):
    """While extract is running, status is 'running:extract'."""
    import threading
    from engine.pipeline.runner import PipelineRunner

    source = tmp_path / "x.mp4"
    _touch(source, b"x")

    extract_started = threading.Event()
    block_extract = threading.Event()

    def slow_run_ffmpeg(*args, **kwargs):
        extract_started.set()
        # Block until the test releases us
        block_extract.wait(timeout=5)
        return ""

    runner = PipelineRunner()
    try:
        with patch("engine.pipeline.extract.probe_audio_tracks") as probe_mock, \
             patch("engine.pipeline.extract.run_ffmpeg", side_effect=slow_run_ffmpeg), \
             patch("engine.pipeline.normalize.run_loudnorm_measure",
                   return_value={"input_i": "-12", "input_tp": "-1", "input_lra": "5",
                                 "input_thresh": "-20", "target_offset": "0"}), \
             patch("engine.pipeline.normalize.run_ffmpeg", return_value=""):
            probe_mock.return_value = [
                {"index": 0, "codec_name": "aac", "sample_rate": 48000, "channels": 1, "duration_seconds": 1.0},
            ]

            future = runner.submit_pipeline(tmp_path, source)
            assert extract_started.wait(timeout=2)
            # extract is now hanging on the event
            assert runner.get_status(tmp_path, source) == "running:extract"
            block_extract.set()
            future.result(timeout=5)
        assert runner.get_status(tmp_path, source) == "completed"
    finally:
        block_extract.set()
        runner.shutdown()
