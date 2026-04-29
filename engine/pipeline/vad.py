"""Stage 4: voice activity detection (Silero VAD).

Reads each ``enhanced/track{N}.wav`` (from Stage 3), runs Silero VAD with
brief §4.4 parameters (threshold=0.5, min_speech_duration_ms=250,
min_silence_duration_ms=300, speech_pad_ms=200), and writes a single
``speech-segments.json`` at the cache root containing one inner list per
track:

    {"tracks": [[{"start": 1.5, "end": 4.2}, ...], [{"start": 0.8, ...}, ...]]}

The model loads once per engine process via a module-level cache.

Tests mock ``vad_audio_file`` at the boundary; the underlying torch +
silero-vad calls are not exercised in unit tests.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from engine.pipeline.state import (
    StageStatus,
    load_state,
    save_state,
    update_stage,
)

STAGE_NAME = "vad"
SAMPLING_RATE = 16000

# Brief §4.4 parameters
VAD_PARAMS = {
    "threshold": 0.5,
    "min_speech_duration_ms": 250,
    "min_silence_duration_ms": 300,
    "speech_pad_ms": 200,
}

_silero_model = None


def _get_silero_model():
    """Lazy-load and cache the Silero VAD model."""
    global _silero_model
    if _silero_model is None:
        from silero_vad import load_silero_vad
        _silero_model = load_silero_vad()
    return _silero_model


def vad_audio_file(in_path: Path) -> list[dict]:
    """Run Silero VAD over a WAV, return list of {start, end} dicts (seconds).

    Tests mock this function — the underlying silero_vad + torch calls are
    not exercised in unit tests.
    """
    from silero_vad import get_speech_timestamps, read_audio

    model = _get_silero_model()
    audio = read_audio(str(in_path), sampling_rate=SAMPLING_RATE)
    raw_segments = get_speech_timestamps(
        audio,
        model,
        sampling_rate=SAMPLING_RATE,
        return_seconds=True,
        **VAD_PARAMS,
    )
    return [{"start": float(s["start"]), "end": float(s["end"])} for s in raw_segments]


def run_vad_stage(cache_dir: Path) -> Path:
    """VAD over each enhanced track. Writes speech-segments.json at the cache
    root. Returns the JSON path.

    Raises:
        FileNotFoundError: source.json or any enhanced/track{N}.wav missing.
        RuntimeError: VAD inference failed.
    """
    state = load_state(cache_dir)
    state = update_stage(
        state,
        STAGE_NAME,
        status=StageStatus.RUNNING,
        started_at=datetime.now(timezone.utc),
    )
    save_state(cache_dir, state)

    try:
        metadata_path = cache_dir / "source.json"
        if not metadata_path.is_file():
            raise FileNotFoundError(f"source.json missing in {cache_dir}")
        metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
        tracks = metadata.get("audio_tracks", [])

        # Validate all input tracks exist before processing any (fail fast).
        in_paths: list[Path] = []
        for n in range(len(tracks)):
            in_path = cache_dir / "enhanced" / f"track{n}.wav"
            if not in_path.is_file():
                raise FileNotFoundError(f"expected enhanced track missing: {in_path}")
            in_paths.append(in_path)

        per_track_segments: list[list[dict]] = []
        for in_path in in_paths:
            per_track_segments.append(vad_audio_file(in_path))

        out_path = cache_dir / "speech-segments.json"
        out_path.write_text(
            json.dumps({"tracks": per_track_segments}, indent=2),
            encoding="utf-8",
        )

        state = load_state(cache_dir)
        state = update_stage(
            state,
            STAGE_NAME,
            status=StageStatus.COMPLETED,
            completed_at=datetime.now(timezone.utc),
            outputs=[str(out_path)],
        )
        save_state(cache_dir, state)
        return out_path

    except Exception as exc:
        state = load_state(cache_dir)
        state = update_stage(
            state,
            STAGE_NAME,
            status=StageStatus.FAILED,
            completed_at=datetime.now(timezone.utc),
            error=str(exc),
        )
        save_state(cache_dir, state)
        raise
