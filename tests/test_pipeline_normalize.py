"""Tests for engine.pipeline.normalize — Stage 2 (loudnorm + compress + bandpass)."""
import json
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

from engine.pipeline.normalize import run_normalize_stage
from engine.pipeline.state import load_state


def _touch(p: Path, content: bytes = b""):
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_bytes(content)


def _write_source_metadata(cache_dir: Path, n_tracks: int):
    """Set up the ffprobe metadata that Stage 1 would have written."""
    cache_dir.mkdir(parents=True, exist_ok=True)
    tracks = [
        {"index": i + 1, "codec_name": "aac", "sample_rate": 48000, "channels": 1, "duration_seconds": 12.0}
        for i in range(n_tracks)
    ]
    (cache_dir / "source.json").write_text(json.dumps({"audio_tracks": tracks}))
    extracted = cache_dir / "extracted"
    extracted.mkdir(exist_ok=True)
    for i in range(n_tracks):
        _touch(extracted / f"track{i}.wav", b"fake-wav")


def test_run_normalize_stage_creates_normalized_wavs(tmp_path: Path):
    cache_dir = tmp_path / ".bwcclipper" / "officer"
    _write_source_metadata(cache_dir, n_tracks=2)

    measured = {
        "input_i": "-12", "input_tp": "-1", "input_lra": "5",
        "input_thresh": "-20", "target_offset": "0",
    }
    with patch("engine.pipeline.normalize.run_loudnorm_measure", return_value=measured), \
         patch("engine.pipeline.normalize.run_ffmpeg") as ffmpeg_mock:
        outputs = run_normalize_stage(cache_dir)

    assert len(outputs) == 2
    assert outputs[0] == cache_dir / "normalized" / "track0.wav"
    assert outputs[1] == cache_dir / "normalized" / "track1.wav"
    assert (cache_dir / "normalized").is_dir()

    # Two ffmpeg apply-pass calls (measurement is mocked separately).
    assert ffmpeg_mock.call_count == 2

    # First call: confirm filter chain composition for track 0
    args0 = ffmpeg_mock.call_args_list[0][0][0]
    af_idx = args0.index("-af")
    chain = args0[af_idx + 1]
    assert "loudnorm=I=-16" in chain
    assert "measured_I=-12" in chain
    assert "measured_TP=-1" in chain
    assert "measured_LRA=5" in chain
    assert "measured_thresh=-20" in chain
    assert "offset=0" in chain
    assert "acompressor=threshold=-24dB:ratio=4:attack=20:release=250:makeup=6" in chain
    assert "highpass=f=80" in chain
    assert "lowpass=f=8000" in chain

    # Output args
    assert "-ar" in args0 and "16000" in args0
    assert "-ac" in args0 and "1" in args0
    assert "-c:a" in args0 and "pcm_s16le" in args0
    assert str(cache_dir / "normalized" / "track0.wav") in args0


def test_run_normalize_stage_writes_pipeline_state(tmp_path: Path):
    cache_dir = tmp_path / ".bwcclipper" / "officer"
    _write_source_metadata(cache_dir, n_tracks=1)

    with patch("engine.pipeline.normalize.run_loudnorm_measure",
               return_value={"input_i": "-12", "input_tp": "-1", "input_lra": "5",
                             "input_thresh": "-20", "target_offset": "0"}), \
         patch("engine.pipeline.normalize.run_ffmpeg"):
        run_normalize_stage(cache_dir)

    state = load_state(cache_dir)
    norm = state.stages["normalize"]
    assert norm["status"] == "completed"
    assert "started_at" in norm and "completed_at" in norm
    assert len(norm["outputs"]) == 1


def test_run_normalize_stage_marks_failed_on_ffmpeg_error(tmp_path: Path):
    cache_dir = tmp_path / ".bwcclipper" / "officer"
    _write_source_metadata(cache_dir, n_tracks=1)

    with patch("engine.pipeline.normalize.run_loudnorm_measure",
               return_value={"input_i": "-12", "input_tp": "-1", "input_lra": "5",
                             "input_thresh": "-20", "target_offset": "0"}), \
         patch("engine.pipeline.normalize.run_ffmpeg", side_effect=RuntimeError("boom")):
        with pytest.raises(RuntimeError, match="boom"):
            run_normalize_stage(cache_dir)

    state = load_state(cache_dir)
    norm = state.stages["normalize"]
    assert norm["status"] == "failed"
    assert "boom" in norm.get("error", "")


def test_run_normalize_stage_raises_if_source_metadata_missing(tmp_path: Path):
    cache_dir = tmp_path / ".bwcclipper" / "officer"
    cache_dir.mkdir(parents=True)
    # Note: no source.json, no extracted/

    with pytest.raises(FileNotFoundError):
        run_normalize_stage(cache_dir)


def test_run_normalize_stage_raises_if_extracted_track_missing(tmp_path: Path):
    """source.json says 2 tracks exist, but extracted/ only has 1."""
    cache_dir = tmp_path / ".bwcclipper" / "officer"
    _write_source_metadata(cache_dir, n_tracks=2)
    # Remove track1.wav to simulate a partial / corrupted Stage 1 cache
    (cache_dir / "extracted" / "track1.wav").unlink()

    with pytest.raises(FileNotFoundError):
        run_normalize_stage(cache_dir)
