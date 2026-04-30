"""rerun_from_stage tests — clears stage state and resubmits."""
from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

import pytest

from engine.pipeline.runner import PipelineRunner, _PIPELINE_STAGES
from engine.pipeline.state import StageStatus, save_state, load_state, PipelineState


def _completed_state() -> PipelineState:
    """All M0–M5 stages marked completed."""
    stages = {
        name: {"status": StageStatus.COMPLETED.value, "outputs": []}
        for name, _ in _PIPELINE_STAGES
    }
    return PipelineState(stages=stages)


def test_rerun_from_transcribe_clears_transcribe_and_align(tmp_path: Path):
    folder = tmp_path / "case"
    folder.mkdir()
    source = folder / "exam.mp3"
    source.write_bytes(b"x")
    from engine.source import source_cache_dir
    cache_dir = source_cache_dir(folder, source)
    cache_dir.mkdir(parents=True, exist_ok=True)
    save_state(cache_dir, _completed_state())

    runner = PipelineRunner()
    try:
        with patch.object(runner, "submit_pipeline") as submit:
            runner.rerun_from_stage("transcribe", folder, source)
            submit.assert_called_once_with(folder, source)

        # transcribe and align should now be missing / non-completed
        state = load_state(cache_dir)
        assert "transcribe" not in state.stages or \
            state.stages["transcribe"].get("status") != StageStatus.COMPLETED.value
        assert "align" not in state.stages or \
            state.stages["align"].get("status") != StageStatus.COMPLETED.value
        # earlier stages preserved
        assert state.stages["extract"]["status"] == StageStatus.COMPLETED.value
        assert state.stages["normalize"]["status"] == StageStatus.COMPLETED.value
        assert state.stages["enhance"]["status"] == StageStatus.COMPLETED.value
        assert state.stages["vad"]["status"] == StageStatus.COMPLETED.value
    finally:
        runner.shutdown()


def test_rerun_from_invalid_stage_raises(tmp_path: Path):
    runner = PipelineRunner()
    try:
        with pytest.raises(ValueError, match="unknown stage"):
            runner.rerun_from_stage("nonexistent", tmp_path, tmp_path / "x")
    finally:
        runner.shutdown()


def test_rerun_idempotent_when_already_queued(tmp_path: Path):
    """Calling rerun_from_stage twice in quick succession is harmless;
    submit_pipeline's existing idempotency handles the queue."""
    folder = tmp_path / "case"
    folder.mkdir()
    source = folder / "exam.mp3"
    source.write_bytes(b"x")
    from engine.source import source_cache_dir
    cache_dir = source_cache_dir(folder, source)
    cache_dir.mkdir(parents=True, exist_ok=True)
    save_state(cache_dir, _completed_state())

    runner = PipelineRunner()
    try:
        with patch.object(runner, "submit_pipeline") as submit:
            runner.rerun_from_stage("transcribe", folder, source)
            runner.rerun_from_stage("transcribe", folder, source)
            assert submit.call_count == 2  # method itself isn't deduping; submit_pipeline does
    finally:
        runner.shutdown()
