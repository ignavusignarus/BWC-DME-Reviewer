"""Tests for engine.pipeline.vad — Stage 4 (Silero VAD)."""
import json
from pathlib import Path
from unittest.mock import patch

import pytest

from engine.pipeline.vad import run_vad_stage
from engine.pipeline.state import load_state


def _touch(p: Path, content: bytes = b""):
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_bytes(content)


def _write_source_metadata_with_enhanced(cache_dir: Path, n_tracks: int):
    """Set up the cache as if Stages 1 + 2 + 3 have completed."""
    cache_dir.mkdir(parents=True, exist_ok=True)
    tracks = [
        {"index": i + 1, "codec_name": "aac", "sample_rate": 48000, "channels": 1, "duration_seconds": 12.0}
        for i in range(n_tracks)
    ]
    (cache_dir / "source.json").write_text(json.dumps({"audio_tracks": tracks}))
    enhanced = cache_dir / "enhanced"
    enhanced.mkdir(exist_ok=True)
    for i in range(n_tracks):
        _touch(enhanced / f"track{i}.wav", b"fake-enhanced-wav")


def test_run_vad_stage_writes_speech_segments_json(tmp_path: Path):
    cache_dir = tmp_path / ".bwcclipper" / "officer"
    _write_source_metadata_with_enhanced(cache_dir, n_tracks=2)

    def _per_track_segments(in_path: Path) -> list[dict]:
        if "track0" in str(in_path):
            return [{"start": 0.5, "end": 2.0}, {"start": 3.5, "end": 6.0}]
        return [{"start": 1.0, "end": 4.0}]

    with patch("engine.pipeline.vad.vad_audio_file", side_effect=_per_track_segments) as mock:
        result = run_vad_stage(cache_dir)

    out_path = cache_dir / "speech-segments.json"
    assert out_path.is_file()
    data = json.loads(out_path.read_text(encoding="utf-8"))
    assert "tracks" in data
    assert len(data["tracks"]) == 2
    assert data["tracks"][0] == [{"start": 0.5, "end": 2.0}, {"start": 3.5, "end": 6.0}]
    assert data["tracks"][1] == [{"start": 1.0, "end": 4.0}]

    assert result == out_path
    assert mock.call_count == 2


def test_run_vad_stage_writes_pipeline_state(tmp_path: Path):
    cache_dir = tmp_path / ".bwcclipper" / "officer"
    _write_source_metadata_with_enhanced(cache_dir, n_tracks=1)

    with patch("engine.pipeline.vad.vad_audio_file", return_value=[]):
        run_vad_stage(cache_dir)

    state = load_state(cache_dir)
    vad = state.stages["vad"]
    assert vad["status"] == "completed"
    assert "started_at" in vad and "completed_at" in vad
    assert vad["outputs"] == [str(cache_dir / "speech-segments.json")]


def test_run_vad_stage_marks_failed_on_helper_error(tmp_path: Path):
    cache_dir = tmp_path / ".bwcclipper" / "officer"
    _write_source_metadata_with_enhanced(cache_dir, n_tracks=1)

    with patch("engine.pipeline.vad.vad_audio_file", side_effect=RuntimeError("boom")):
        with pytest.raises(RuntimeError, match="boom"):
            run_vad_stage(cache_dir)

    state = load_state(cache_dir)
    vad = state.stages["vad"]
    assert vad["status"] == "failed"
    assert "boom" in vad.get("error", "")


def test_run_vad_stage_raises_if_source_metadata_missing(tmp_path: Path):
    cache_dir = tmp_path / ".bwcclipper" / "officer"
    cache_dir.mkdir(parents=True)

    with pytest.raises(FileNotFoundError):
        run_vad_stage(cache_dir)


def test_run_vad_stage_raises_if_enhanced_track_missing(tmp_path: Path):
    cache_dir = tmp_path / ".bwcclipper" / "officer"
    _write_source_metadata_with_enhanced(cache_dir, n_tracks=2)
    (cache_dir / "enhanced" / "track1.wav").unlink()

    with pytest.raises(FileNotFoundError):
        run_vad_stage(cache_dir)


def test_run_vad_stage_handles_empty_speech(tmp_path: Path):
    """A silent track → empty segments list, but VAD still runs and writes JSON."""
    cache_dir = tmp_path / ".bwcclipper" / "officer"
    _write_source_metadata_with_enhanced(cache_dir, n_tracks=1)

    with patch("engine.pipeline.vad.vad_audio_file", return_value=[]):
        run_vad_stage(cache_dir)

    out_path = cache_dir / "speech-segments.json"
    data = json.loads(out_path.read_text(encoding="utf-8"))
    assert data == {"tracks": [[]]}
