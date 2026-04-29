"""Tests for engine.pipeline.state — pipeline-state.json read/write."""
from datetime import datetime, timezone
from pathlib import Path

from engine.pipeline.state import (
    PipelineState,
    StageStatus,
    load_state,
    save_state,
    update_stage,
)


def test_pipeline_state_default(tmp_path: Path):
    state = PipelineState.empty()
    assert state.stages == {}


def test_save_then_load_roundtrip(tmp_path: Path):
    state = PipelineState.empty()
    state = update_stage(
        state,
        "extract",
        status=StageStatus.RUNNING,
        started_at=datetime(2026, 4, 29, 12, 0, tzinfo=timezone.utc),
    )
    save_state(tmp_path, state)
    loaded = load_state(tmp_path)
    assert loaded.stages["extract"]["status"] == "running"
    assert loaded.stages["extract"]["started_at"] == "2026-04-29T12:00:00+00:00"


def test_load_state_returns_empty_when_file_missing(tmp_path: Path):
    state = load_state(tmp_path)
    assert state.stages == {}


def test_update_stage_overwrites_keys(tmp_path: Path):
    state = PipelineState.empty()
    state = update_stage(state, "extract", status=StageStatus.RUNNING)
    state = update_stage(
        state,
        "extract",
        status=StageStatus.COMPLETED,
        outputs=["a.wav", "b.wav"],
    )
    assert state.stages["extract"]["status"] == "completed"
    assert state.stages["extract"]["outputs"] == ["a.wav", "b.wav"]


def test_stage_status_values():
    assert StageStatus.QUEUED.value == "queued"
    assert StageStatus.RUNNING.value == "running"
    assert StageStatus.COMPLETED.value == "completed"
    assert StageStatus.FAILED.value == "failed"
