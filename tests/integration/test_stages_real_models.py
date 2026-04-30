"""Real-model integration tests for the ML pipeline stages.

These tests load the actual models and run them on a short sample WAV. They
are slow (model loading dominates) and require GPU for reasonable runtime.
Marked ``integration`` so the fast unit suite excludes them. Run explicitly:

    .venv/Scripts/python.exe -m pytest -m integration -v
"""

import json
from pathlib import Path

import pytest

pytestmark = pytest.mark.integration


def _build_basic_cache(tmp_path: Path, sample_wav: Path, stage_dir: str = "enhanced") -> Path:
    """Set up a per-source cache with the sample placed under the given stage
    dir as track0.wav, and a minimal source.json + source.sha256.
    """
    cache_dir = tmp_path / ".bwcclipper" / "officer"
    cache_dir.mkdir(parents=True, exist_ok=True)
    (cache_dir / "source.json").write_text(json.dumps({
        "audio_tracks": [
            {"index": 0, "codec_name": "pcm_s16le", "sample_rate": 16000,
             "channels": 1, "duration_seconds": 15.0},
        ],
    }))
    (cache_dir / "source.sha256").write_text("0" * 64)
    stage = cache_dir / stage_dir
    stage.mkdir(exist_ok=True)
    # Copy (don't symlink — Windows symlinks need admin) the fixture in.
    import shutil
    shutil.copy(sample_wav, stage / "track0.wav")
    return cache_dir


# ── Stage 3: DeepFilterNet enhance ────────────────────────────────────────

def test_real_enhance_runs_on_sample(tmp_path: Path, sample_short_wav: Path):
    """DF3 actually runs on real audio, produces a real-bytes WAV out
    at the SAME duration as the input (not 3x longer due to the
    save_audio sample-rate mismatch bug)."""
    import soundfile as sf

    from engine.pipeline.enhance import run_enhance_stage
    cache_dir = _build_basic_cache(tmp_path, sample_short_wav, stage_dir="normalized")

    outputs = run_enhance_stage(cache_dir)

    assert len(outputs) == 1
    out_wav = outputs[0]
    assert out_wav.is_file()
    assert out_wav.stat().st_size > 1000  # real audio data, not just a header

    # Critical: output duration must match input. The fixture is 15s; the
    # enhanced output must also be ~15s. The save_audio sample-rate-mismatch
    # bug produces 45s output (48k data labeled as 16k = 3x longer).
    in_info = sf.info(str(sample_short_wav))
    out_info = sf.info(str(out_wav))
    assert out_info.samplerate == 16000, \
        f"Enhanced WAV not at 16 kHz: {out_info.samplerate}"
    duration_ratio = out_info.duration / in_info.duration
    assert 0.95 < duration_ratio < 1.05, \
        (f"Enhanced output duration {out_info.duration:.2f}s vs input "
         f"{in_info.duration:.2f}s (ratio={duration_ratio:.2f}). "
         f"Likely the save_audio sample-rate-mismatch bug.")


# ── Stage 4: Silero VAD ────────────────────────────────────────────────────

def test_real_vad_runs_on_sample(tmp_path: Path, sample_short_wav: Path):
    """Silero VAD actually runs on real audio, produces speech-segments.json
    with at least one segment (the sample is known to contain speech)."""
    from engine.pipeline.vad import run_vad_stage
    cache_dir = _build_basic_cache(tmp_path, sample_short_wav, stage_dir="enhanced")

    out_path = run_vad_stage(cache_dir)
    assert out_path.is_file()
    data = json.loads(out_path.read_text(encoding="utf-8"))
    assert "tracks" in data
    assert len(data["tracks"]) == 1
    # The sample is 15 seconds of medical-exam speech — VAD should find
    # at least a couple of segments.
    assert len(data["tracks"][0]) >= 1, \
        f"VAD found no speech in fixture; segments: {data['tracks'][0]}"


# ── Stage 5: faster-whisper transcribe ────────────────────────────────────

def test_real_transcribe_runs_on_sample(tmp_path: Path, sample_short_wav: Path):
    """faster-whisper actually runs on real audio, produces transcribe-raw.json
    with at least one segment (the sample contains speech)."""
    from engine.pipeline.transcribe import run_transcribe_stage
    cache_dir = _build_basic_cache(tmp_path, sample_short_wav, stage_dir="enhanced")

    out_path = run_transcribe_stage(cache_dir)
    assert out_path.is_file()
    data = json.loads(out_path.read_text(encoding="utf-8"))
    segments = data.get("segments", [])
    assert len(segments) >= 1, f"Whisper produced no segments on speech fixture"

    # Each segment should have the M5 schema fields.
    s = segments[0]
    assert "start" in s and "end" in s and "text" in s
    assert "avg_logprob" in s and "no_speech_prob" in s and "compression_ratio" in s
    # Sanity: text is non-empty and starts/ends are floats in expected range.
    assert s["text"].strip(), f"Empty transcribed text: {s}"
    assert 0.0 <= s["start"] <= 15.0
    assert 0.0 < s["end"] <= 15.0


# ── Stage 6: WhisperX align ───────────────────────────────────────────────

def test_real_align_runs_on_sample(tmp_path: Path, sample_short_wav: Path):
    """WhisperX align adds per-word timestamps to real transcribe output."""
    from engine.pipeline.align import run_align_stage
    from engine.pipeline.transcribe import run_transcribe_stage

    cache_dir = _build_basic_cache(tmp_path, sample_short_wav, stage_dir="enhanced")
    # First run real transcribe to produce transcribe-raw.json
    run_transcribe_stage(cache_dir)

    # Now run real align
    source_path = sample_short_wav  # use the fixture as the "source" path
    transcript_path = run_align_stage(source_path, cache_dir)

    assert transcript_path.is_file()
    data = json.loads(transcript_path.read_text(encoding="utf-8"))
    assert data["schema_version"] == "1.0"
    assert data["source"]["path"] == str(source_path).replace("\\", "/")
    assert len(data["segments"]) >= 1
    # First segment should have word-level timestamps.
    s = data["segments"][0]
    assert "words" in s
    assert len(s["words"]) >= 1, f"WhisperX produced no words: {s}"
    w = s["words"][0]
    assert "word" in w and "start" in w and "end" in w and "score" in w


# ── Full pipeline (Stages 1-6 chained on the fixture as a synthetic source) ─

def test_real_full_pipeline_on_sample(tmp_path: Path, sample_short_wav: Path):
    """End-to-end: a fresh source media file goes through all 6 stages.

    We use the fixture as the source media (a 16 kHz mono WAV — ffmpeg can
    extract from it directly). All real models run.
    """
    from engine.pipeline.runner import PipelineRunner
    from engine.source import source_cache_dir
    from engine.pipeline.state import load_state

    project = tmp_path
    # Copy the fixture into a path that looks like a "source media" file.
    import shutil
    source = project / "sample.wav"
    shutil.copy(sample_short_wav, source)

    runner = PipelineRunner()
    try:
        future = runner.submit_pipeline(project, source)
        # Allow plenty of time — first run loads all 4 ML models (DF3, Silero,
        # Whisper, wav2vec2). On GPU this is ~30s; on CPU it's longer.
        future.result(timeout=300)
        assert runner.get_status(project, source) == "completed"
    finally:
        runner.shutdown()

    cache_dir = source_cache_dir(project, source)
    state = load_state(cache_dir)
    for stage_name in ("extract", "normalize", "enhance", "vad", "transcribe", "align"):
        assert state.stages.get(stage_name, {}).get("status") == "completed", \
            f"stage {stage_name} not completed in {state.stages}"

    transcript = json.loads((cache_dir / "transcript.json").read_text(encoding="utf-8"))
    assert transcript["segments"], "transcript.json has no segments"
    speech = json.loads((cache_dir / "speech-segments.json").read_text(encoding="utf-8"))
    assert speech["tracks"][0], "speech-segments.json has no segments"
