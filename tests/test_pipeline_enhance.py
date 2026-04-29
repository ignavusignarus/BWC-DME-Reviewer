"""Tests for engine.pipeline.enhance — Stage 3 (DeepFilterNet 3 enhancement)."""
import json
from pathlib import Path
from unittest.mock import patch

import pytest

from engine.pipeline.enhance import run_enhance_stage
from engine.pipeline.state import load_state


def _touch(p: Path, content: bytes = b""):
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_bytes(content)


def _write_source_metadata_with_normalized(cache_dir: Path, n_tracks: int):
    """Set up the cache as if Stages 1 + 2 have completed."""
    cache_dir.mkdir(parents=True, exist_ok=True)
    tracks = [
        {"index": i + 1, "codec_name": "aac", "sample_rate": 48000, "channels": 1, "duration_seconds": 12.0}
        for i in range(n_tracks)
    ]
    (cache_dir / "source.json").write_text(json.dumps({"audio_tracks": tracks}))
    normalized = cache_dir / "normalized"
    normalized.mkdir(exist_ok=True)
    for i in range(n_tracks):
        _touch(normalized / f"track{i}.wav", b"fake-normalized-wav")


def test_run_enhance_stage_creates_enhanced_wavs(tmp_path: Path):
    cache_dir = tmp_path / ".bwcclipper" / "officer"
    _write_source_metadata_with_normalized(cache_dir, n_tracks=2)

    def _writes_output(in_path, out_path):
        Path(out_path).parent.mkdir(parents=True, exist_ok=True)
        Path(out_path).touch()

    with patch("engine.pipeline.enhance.enhance_audio_file", side_effect=_writes_output) as mock:
        outputs = run_enhance_stage(cache_dir)

    assert len(outputs) == 2
    assert outputs[0] == cache_dir / "enhanced" / "track0.wav"
    assert outputs[1] == cache_dir / "enhanced" / "track1.wav"
    assert (cache_dir / "enhanced").is_dir()

    assert mock.call_count == 2
    args0, _ = mock.call_args_list[0]
    assert args0[0] == cache_dir / "normalized" / "track0.wav"
    assert args0[1] == cache_dir / "enhanced" / "track0.wav"


def test_run_enhance_stage_writes_pipeline_state(tmp_path: Path):
    cache_dir = tmp_path / ".bwcclipper" / "officer"
    _write_source_metadata_with_normalized(cache_dir, n_tracks=1)

    def _writes_output(in_path, out_path):
        Path(out_path).parent.mkdir(parents=True, exist_ok=True)
        Path(out_path).touch()

    with patch("engine.pipeline.enhance.enhance_audio_file", side_effect=_writes_output):
        run_enhance_stage(cache_dir)

    state = load_state(cache_dir)
    enhance = state.stages["enhance"]
    assert enhance["status"] == "completed"
    assert "started_at" in enhance and "completed_at" in enhance
    assert len(enhance["outputs"]) == 1


def test_run_enhance_stage_marks_failed_on_helper_error(tmp_path: Path):
    cache_dir = tmp_path / ".bwcclipper" / "officer"
    _write_source_metadata_with_normalized(cache_dir, n_tracks=1)

    with patch("engine.pipeline.enhance.enhance_audio_file", side_effect=RuntimeError("boom")):
        with pytest.raises(RuntimeError, match="boom"):
            run_enhance_stage(cache_dir)

    state = load_state(cache_dir)
    enhance = state.stages["enhance"]
    assert enhance["status"] == "failed"
    assert "boom" in enhance.get("error", "")


def test_run_enhance_stage_raises_if_source_metadata_missing(tmp_path: Path):
    cache_dir = tmp_path / ".bwcclipper" / "officer"
    cache_dir.mkdir(parents=True)

    with pytest.raises(FileNotFoundError):
        run_enhance_stage(cache_dir)


def test_run_enhance_stage_raises_if_normalized_track_missing(tmp_path: Path):
    cache_dir = tmp_path / ".bwcclipper" / "officer"
    _write_source_metadata_with_normalized(cache_dir, n_tracks=2)
    (cache_dir / "normalized" / "track1.wav").unlink()

    with pytest.raises(FileNotFoundError):
        run_enhance_stage(cache_dir)
