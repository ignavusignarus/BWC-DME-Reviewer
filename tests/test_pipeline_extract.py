"""Tests for engine.pipeline.extract."""
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

from engine.pipeline.extract import run_extract_stage
from engine.pipeline.state import StageStatus, load_state


def _touch(p: Path, content: bytes = b""):
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_bytes(content)


def test_run_extract_stage_creates_extracted_subdir_and_wav_files(tmp_path: Path):
    project = tmp_path
    source = project / "officer.mp4"
    _touch(source, b"some-bytes")
    cache_dir = project / ".bwcclipper" / "officer"
    cache_dir.mkdir(parents=True)

    # Mock the ffmpeg/ffprobe wrappers — we're testing orchestration.
    with patch("engine.pipeline.extract.probe_audio_tracks") as probe_mock, \
         patch("engine.pipeline.extract.run_ffmpeg") as ffmpeg_mock:
        probe_mock.return_value = [
            {"index": 1, "codec_name": "aac", "sample_rate": 48000, "channels": 2, "duration_seconds": 12.0},
            {"index": 2, "codec_name": "aac", "sample_rate": 48000, "channels": 1, "duration_seconds": 12.0},
        ]
        ffmpeg_mock.return_value = ""  # ffmpeg succeeds
        outputs = run_extract_stage(source, cache_dir)

    # Two outputs, one per track
    assert len(outputs) == 2
    expected_track0 = cache_dir / "extracted" / "track0.wav"
    expected_track1 = cache_dir / "extracted" / "track1.wav"
    assert outputs[0] == expected_track0
    assert outputs[1] == expected_track1

    # extracted/ directory is created
    assert (cache_dir / "extracted").is_dir()

    # ffmpeg was called twice with the expected -map and resampling args
    assert ffmpeg_mock.call_count == 2
    # First call: track 0 (stream index 1 from probe)
    call0_args = ffmpeg_mock.call_args_list[0][0][0]
    assert "-map" in call0_args
    assert "0:1" in call0_args  # stream index 1
    assert "-ac" in call0_args and "1" in call0_args  # mono
    assert "-ar" in call0_args and "16000" in call0_args  # 16 kHz
    assert "-c:a" in call0_args and "pcm_s16le" in call0_args
    assert str(expected_track0) in call0_args


def test_run_extract_stage_writes_pipeline_state(tmp_path: Path):
    source = tmp_path / "officer.mp4"
    _touch(source, b"x")
    cache_dir = tmp_path / ".bwcclipper" / "officer"
    cache_dir.mkdir(parents=True)

    with patch("engine.pipeline.extract.probe_audio_tracks") as probe_mock, \
         patch("engine.pipeline.extract.run_ffmpeg") as _ffmpeg_mock:
        probe_mock.return_value = [
            {"index": 0, "codec_name": "aac", "sample_rate": 48000, "channels": 1, "duration_seconds": 5.0},
        ]
        run_extract_stage(source, cache_dir)

    state = load_state(cache_dir)
    extract = state.stages["extract"]
    assert extract["status"] == "completed"
    assert "started_at" in extract and "completed_at" in extract
    assert len(extract["outputs"]) == 1


def test_run_extract_stage_writes_source_metadata(tmp_path: Path):
    """source.json captures the ffprobe track list for later milestones to consume."""
    import json as _json

    source = tmp_path / "officer.mp4"
    _touch(source, b"x")
    cache_dir = tmp_path / ".bwcclipper" / "officer"
    cache_dir.mkdir(parents=True)

    with patch("engine.pipeline.extract.probe_audio_tracks") as probe_mock, \
         patch("engine.pipeline.extract.run_ffmpeg", return_value=""):
        probe_mock.return_value = [
            {"index": 1, "codec_name": "aac", "sample_rate": 48000, "channels": 2, "duration_seconds": 12.0},
        ]
        run_extract_stage(source, cache_dir)

    metadata_file = cache_dir / "source.json"
    assert metadata_file.is_file()
    metadata = _json.loads(metadata_file.read_text(encoding="utf-8"))
    assert metadata["audio_tracks"][0]["index"] == 1
    assert metadata["audio_tracks"][0]["channels"] == 2


def test_run_extract_stage_marks_failed_on_ffmpeg_error(tmp_path: Path):
    source = tmp_path / "officer.mp4"
    _touch(source, b"x")
    cache_dir = tmp_path / ".bwcclipper" / "officer"
    cache_dir.mkdir(parents=True)

    with patch("engine.pipeline.extract.probe_audio_tracks") as probe_mock, \
         patch("engine.pipeline.extract.run_ffmpeg", side_effect=RuntimeError("boom")):
        probe_mock.return_value = [{"index": 0, "codec_name": "aac", "sample_rate": 48000, "channels": 1, "duration_seconds": 5.0}]
        with pytest.raises(RuntimeError, match="boom"):
            run_extract_stage(source, cache_dir)

    state = load_state(cache_dir)
    extract = state.stages["extract"]
    assert extract["status"] == "failed"
    assert "boom" in extract.get("error", "")


def test_run_extract_stage_raises_for_no_audio_tracks(tmp_path: Path):
    source = tmp_path / "officer.mp4"
    _touch(source, b"x")
    cache_dir = tmp_path / ".bwcclipper" / "officer"
    cache_dir.mkdir(parents=True)

    with patch("engine.pipeline.extract.probe_audio_tracks", return_value=[]):
        with pytest.raises(ValueError, match="no audio"):
            run_extract_stage(source, cache_dir)
