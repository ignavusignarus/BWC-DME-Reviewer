"""Stage 2: loudness normalization + dynamic-range compression + bandpass.

Two-pass loudnorm (per brief §4.2):
  1. Measure with ``loudnorm=I=-16:LRA=11:TP=-1.5:print_format=json``.
  2. Apply with measured values + acompressor + highpass/lowpass in a single
     ffmpeg invocation.

Reads each ``extracted/track{N}.wav`` (from Stage 1), writes
``normalized/track{N}.wav`` at the same sample rate / channel layout.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from engine.ffmpeg import run_ffmpeg, run_loudnorm_measure
from engine.pipeline.state import (
    StageStatus,
    load_state,
    save_state,
    update_stage,
)

STAGE_NAME = "normalize"

# Brief §4.2 — chained after loudnorm in the same ffmpeg invocation.
_COMPRESSOR = "acompressor=threshold=-24dB:ratio=4:attack=20:release=250:makeup=6"
_HIGHPASS = "highpass=f=80"
_LOWPASS = "lowpass=f=8000"


def _build_filter_chain(measured: dict[str, str]) -> str:
    loudnorm = (
        "loudnorm=I=-16:LRA=11:TP=-1.5"
        f":measured_I={measured['input_i']}"
        f":measured_TP={measured['input_tp']}"
        f":measured_LRA={measured['input_lra']}"
        f":measured_thresh={measured['input_thresh']}"
        f":offset={measured['target_offset']}"
        ":linear=true"
    )
    return ",".join([loudnorm, _COMPRESSOR, _HIGHPASS, _LOWPASS])


def run_normalize_stage(cache_dir: Path) -> list[Path]:
    """Normalize each extracted track. Returns list of output WAV paths.

    Updates pipeline-state.json with running/completed/failed.

    Raises:
        FileNotFoundError: source.json or any extracted/track{N}.wav missing.
        RuntimeError: ffmpeg subprocess failed.
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

        out_dir = cache_dir / "normalized"
        out_dir.mkdir(parents=True, exist_ok=True)
        outputs: list[Path] = []

        for n in range(len(tracks)):
            in_path = cache_dir / "extracted" / f"track{n}.wav"
            if not in_path.is_file():
                raise FileNotFoundError(f"expected extracted track missing: {in_path}")

            measured = run_loudnorm_measure(in_path)
            out_path = out_dir / f"track{n}.wav"
            run_ffmpeg([
                "-y",
                "-i", str(in_path),
                "-af", _build_filter_chain(measured),
                "-ar", "16000",
                "-ac", "1",
                "-c:a", "pcm_s16le",
                str(out_path),
            ])
            outputs.append(out_path)

        state = load_state(cache_dir)
        state = update_stage(
            state,
            STAGE_NAME,
            status=StageStatus.COMPLETED,
            completed_at=datetime.now(timezone.utc),
            outputs=[str(p) for p in outputs],
        )
        save_state(cache_dir, state)
        return outputs

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
