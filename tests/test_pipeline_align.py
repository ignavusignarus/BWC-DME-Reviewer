"""Tests for engine.pipeline.align — Stage 6 (WhisperX wav2vec2 alignment + transcript.json)."""
import json
from pathlib import Path
from unittest.mock import patch

import pytest

from engine.pipeline.align import run_align_stage
from engine.pipeline.state import load_state


def _touch(p: Path, content: bytes = b""):
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_bytes(content)


def _write_full_cache(cache_dir: Path, source_basename: str = "officer.mp4"):
    """Set up the cache as if Stages 1-5 have completed."""
    cache_dir.mkdir(parents=True, exist_ok=True)
    (cache_dir / "source.json").write_text(json.dumps({
        "audio_tracks": [
            {"index": 1, "codec_name": "aac", "sample_rate": 48000, "channels": 1, "duration_seconds": 60.0},
        ],
    }))
    (cache_dir / "source.sha256").write_text("a" * 64)
    enhanced = cache_dir / "enhanced"
    enhanced.mkdir(exist_ok=True)
    _touch(enhanced / "track0.wav", b"fake-enhanced-wav")
    (cache_dir / "transcribe-raw.json").write_text(json.dumps({
        "segments": [
            {"id": 0, "start": 0.5, "end": 3.2, "text": "hello world",
             "avg_logprob": -0.4, "no_speech_prob": 0.1, "compression_ratio": 1.8},
            {"id": 1, "start": 3.5, "end": 5.0, "text": "second segment",
             "avg_logprob": -0.5, "no_speech_prob": 0.2, "compression_ratio": 1.9},
        ],
    }))


def test_run_align_stage_writes_transcript_json(tmp_path: Path):
    cache_dir = tmp_path / ".bwcclipper" / "officer"
    _write_full_cache(cache_dir)
    source_path = tmp_path / "officer.mp4"
    _touch(source_path, b"x")

    def _fake_align(segments, audio_path):
        # Add a fake 'words' list to each segment
        return [
            {**s, "words": [
                {"word": "hello", "start": 0.5, "end": 0.9, "score": 0.95},
                {"word": "world", "start": 1.0, "end": 1.5, "score": 0.93},
            ]}
            for s in segments
        ]

    with patch("engine.pipeline.align.align_segments", side_effect=_fake_align) as mock:
        result = run_align_stage(source_path, cache_dir)

    assert result == cache_dir / "transcript.json"
    assert result.is_file()
    data = json.loads(result.read_text(encoding="utf-8"))

    # Top-level schema
    assert data["schema_version"] == "1.0"
    # Source path is stored in forward-slash form for cross-platform JSON.
    assert data["source"]["path"] == str(source_path).replace("\\", "/")
    assert data["source"]["sha256"] == "a" * 64
    assert data["source"]["duration_seconds"] == 60.0
    assert data["source"]["tracks"][0]["index"] == 1
    assert data["processing"]["whisper_model"] == "large-v3"
    assert data["processing"]["enhanced"] is True
    assert data["processing"]["vad"] == "silero"
    assert "timestamp_utc" in data["processing"]
    assert data["speakers"] == []  # M5 doesn't populate; M7 does

    # Segments (each has 'words' from align)
    assert len(data["segments"]) == 2
    assert data["segments"][0]["text"] == "hello world"
    assert len(data["segments"][0]["words"]) == 2
    assert data["segments"][0]["words"][0]["word"] == "hello"
    # low_confidence flag is derived
    assert data["segments"][0]["low_confidence"] is False

    # align_segments was called once with the segments + audio path
    assert mock.call_count == 1
    args, _ = mock.call_args
    assert len(args[0]) == 2  # 2 segments passed
    assert args[1] == cache_dir / "enhanced" / "track0.wav"


def test_low_confidence_flag_derived_from_thresholds(tmp_path: Path):
    cache_dir = tmp_path / ".bwcclipper" / "officer"
    _write_full_cache(cache_dir)
    # Override transcribe-raw.json with thresholds that will trip each flag
    (cache_dir / "transcribe-raw.json").write_text(json.dumps({
        "segments": [
            # low_confidence: no_speech_prob > 0.6
            {"id": 0, "start": 0, "end": 1, "text": "a", "avg_logprob": -0.1,
             "no_speech_prob": 0.7, "compression_ratio": 1.5},
            # low_confidence: avg_logprob < -1.0
            {"id": 1, "start": 1, "end": 2, "text": "b", "avg_logprob": -1.5,
             "no_speech_prob": 0.1, "compression_ratio": 1.5},
            # low_confidence: compression_ratio > 2.4
            {"id": 2, "start": 2, "end": 3, "text": "c", "avg_logprob": -0.1,
             "no_speech_prob": 0.1, "compression_ratio": 2.5},
            # all clean → false
            {"id": 3, "start": 3, "end": 4, "text": "d", "avg_logprob": -0.1,
             "no_speech_prob": 0.1, "compression_ratio": 1.5},
        ],
    }))
    source_path = tmp_path / "officer.mp4"
    _touch(source_path, b"x")
    with patch("engine.pipeline.align.align_segments",
               side_effect=lambda segs, path: [{**s, "words": []} for s in segs]):
        run_align_stage(source_path, cache_dir)

    data = json.loads((cache_dir / "transcript.json").read_text(encoding="utf-8"))
    assert data["segments"][0]["low_confidence"] is True
    assert data["segments"][1]["low_confidence"] is True
    assert data["segments"][2]["low_confidence"] is True
    assert data["segments"][3]["low_confidence"] is False


def test_run_align_stage_writes_pipeline_state(tmp_path: Path):
    cache_dir = tmp_path / ".bwcclipper" / "officer"
    _write_full_cache(cache_dir)
    source_path = tmp_path / "officer.mp4"
    _touch(source_path, b"x")
    with patch("engine.pipeline.align.align_segments",
               side_effect=lambda segs, path: [{**s, "words": []} for s in segs]):
        run_align_stage(source_path, cache_dir)

    state = load_state(cache_dir)
    align = state.stages["align"]
    assert align["status"] == "completed"
    assert "started_at" in align and "completed_at" in align
    assert align["outputs"] == [str(cache_dir / "transcript.json")]


def test_run_align_stage_marks_failed_on_helper_error(tmp_path: Path):
    cache_dir = tmp_path / ".bwcclipper" / "officer"
    _write_full_cache(cache_dir)
    source_path = tmp_path / "officer.mp4"
    _touch(source_path, b"x")

    with patch("engine.pipeline.align.align_segments", side_effect=RuntimeError("boom")):
        with pytest.raises(RuntimeError, match="boom"):
            run_align_stage(source_path, cache_dir)

    state = load_state(cache_dir)
    align = state.stages["align"]
    assert align["status"] == "failed"
    assert "boom" in align.get("error", "")


def test_run_align_stage_raises_if_transcribe_raw_missing(tmp_path: Path):
    cache_dir = tmp_path / ".bwcclipper" / "officer"
    _write_full_cache(cache_dir)
    (cache_dir / "transcribe-raw.json").unlink()
    source_path = tmp_path / "officer.mp4"
    _touch(source_path, b"x")

    with pytest.raises(FileNotFoundError):
        run_align_stage(source_path, cache_dir)


def test_run_align_stage_raises_if_enhanced_track0_missing(tmp_path: Path):
    cache_dir = tmp_path / ".bwcclipper" / "officer"
    _write_full_cache(cache_dir)
    (cache_dir / "enhanced" / "track0.wav").unlink()
    source_path = tmp_path / "officer.mp4"
    _touch(source_path, b"x")

    with pytest.raises(FileNotFoundError):
        run_align_stage(source_path, cache_dir)


def test_run_align_stage_handles_empty_segments(tmp_path: Path):
    """A silent file → empty transcribe-raw.json → empty transcript.json."""
    cache_dir = tmp_path / ".bwcclipper" / "officer"
    _write_full_cache(cache_dir)
    (cache_dir / "transcribe-raw.json").write_text(json.dumps({"segments": []}))
    source_path = tmp_path / "officer.mp4"
    _touch(source_path, b"x")

    with patch("engine.pipeline.align.align_segments", return_value=[]):
        run_align_stage(source_path, cache_dir)

    data = json.loads((cache_dir / "transcript.json").read_text(encoding="utf-8"))
    assert data["segments"] == []
