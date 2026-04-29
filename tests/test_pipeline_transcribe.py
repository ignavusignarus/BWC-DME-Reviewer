"""Tests for engine.pipeline.transcribe — Stage 5 (faster-whisper large-v3)."""
import json
from pathlib import Path
from unittest.mock import patch

import pytest

from engine.pipeline.transcribe import run_transcribe_stage
from engine.pipeline.state import load_state


def _touch(p: Path, content: bytes = b""):
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_bytes(content)


def _write_source_metadata_with_enhanced(cache_dir: Path, n_tracks: int):
    """Set up the cache as if Stages 1-4 have completed."""
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


def test_run_transcribe_stage_writes_transcribe_raw_json(tmp_path: Path):
    cache_dir = tmp_path / ".bwcclipper" / "officer"
    _write_source_metadata_with_enhanced(cache_dir, n_tracks=1)

    fake_segments = [
        {"id": 0, "start": 0.5, "end": 3.2, "text": "hello world",
         "avg_logprob": -0.4, "no_speech_prob": 0.1, "compression_ratio": 1.8},
        {"id": 1, "start": 3.5, "end": 5.0, "text": "second segment",
         "avg_logprob": -0.5, "no_speech_prob": 0.2, "compression_ratio": 1.9},
    ]

    with patch("engine.pipeline.transcribe.transcribe_audio_file",
               return_value=fake_segments) as mock:
        result = run_transcribe_stage(cache_dir)

    assert result == cache_dir / "transcribe-raw.json"
    assert result.is_file()
    data = json.loads(result.read_text(encoding="utf-8"))
    assert data["segments"] == fake_segments

    # Helper called once with the track 0 enhanced path
    assert mock.call_count == 1
    args, _ = mock.call_args
    assert args[0] == cache_dir / "enhanced" / "track0.wav"


def test_run_transcribe_stage_writes_pipeline_state(tmp_path: Path):
    cache_dir = tmp_path / ".bwcclipper" / "officer"
    _write_source_metadata_with_enhanced(cache_dir, n_tracks=1)

    with patch("engine.pipeline.transcribe.transcribe_audio_file", return_value=[]):
        run_transcribe_stage(cache_dir)

    state = load_state(cache_dir)
    transcribe = state.stages["transcribe"]
    assert transcribe["status"] == "completed"
    assert "started_at" in transcribe and "completed_at" in transcribe
    assert transcribe["outputs"] == [str(cache_dir / "transcribe-raw.json")]


def test_run_transcribe_stage_marks_failed_on_helper_error(tmp_path: Path):
    cache_dir = tmp_path / ".bwcclipper" / "officer"
    _write_source_metadata_with_enhanced(cache_dir, n_tracks=1)

    with patch("engine.pipeline.transcribe.transcribe_audio_file",
               side_effect=RuntimeError("boom")):
        with pytest.raises(RuntimeError, match="boom"):
            run_transcribe_stage(cache_dir)

    state = load_state(cache_dir)
    transcribe = state.stages["transcribe"]
    assert transcribe["status"] == "failed"
    assert "boom" in transcribe.get("error", "")


def test_run_transcribe_stage_raises_if_source_metadata_missing(tmp_path: Path):
    cache_dir = tmp_path / ".bwcclipper" / "officer"
    cache_dir.mkdir(parents=True)

    with pytest.raises(FileNotFoundError):
        run_transcribe_stage(cache_dir)


def test_run_transcribe_stage_raises_if_enhanced_track0_missing(tmp_path: Path):
    cache_dir = tmp_path / ".bwcclipper" / "officer"
    _write_source_metadata_with_enhanced(cache_dir, n_tracks=1)
    (cache_dir / "enhanced" / "track0.wav").unlink()

    with pytest.raises(FileNotFoundError):
        run_transcribe_stage(cache_dir)


def test_run_transcribe_stage_only_processes_track0_for_now(tmp_path: Path):
    """V1 transcribes track 0 only; track 1+ are ignored. Multi-track is M7+."""
    cache_dir = tmp_path / ".bwcclipper" / "officer"
    _write_source_metadata_with_enhanced(cache_dir, n_tracks=3)

    with patch("engine.pipeline.transcribe.transcribe_audio_file", return_value=[]) as mock:
        run_transcribe_stage(cache_dir)

    assert mock.call_count == 1
    args, _ = mock.call_args
    assert args[0].name == "track0.wav"
