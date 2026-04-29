"""Stage 1: audio extraction.

Probes the source media for audio tracks, then runs ffmpeg once per track
to produce a 16 kHz mono PCM WAV at ``<cache_dir>/extracted/track{N}.wav``.
Writes per-stage status to pipeline-state.json. Persists the ffprobe track
list as ``source.json`` so later milestones can consume the metadata
without re-probing.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from engine.ffmpeg import probe_audio_tracks, run_ffmpeg
from engine.pipeline.state import (
    StageStatus,
    load_state,
    save_state,
    update_stage,
)

STAGE_NAME = "extract"


def run_extract_stage(source_path: Path, cache_dir: Path) -> list[Path]:
    """Run audio extraction on ``source_path``, writing outputs into
    ``cache_dir/extracted/``. Returns the list of output WAV paths.

    Updates pipeline-state.json with running/completed/failed status.
    Persists ffprobe track list as ``source.json``.

    Raises:
        ValueError: source has no audio tracks.
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
        tracks = probe_audio_tracks(source_path)
        if not tracks:
            raise ValueError(f"no audio tracks found in {source_path}")

        # Persist ffprobe output as source.json so later milestones can consume
        # it without re-probing.
        (cache_dir / "source.json").write_text(
            json.dumps({"audio_tracks": tracks}, indent=2),
            encoding="utf-8",
        )

        out_dir = cache_dir / "extracted"
        out_dir.mkdir(parents=True, exist_ok=True)
        outputs: list[Path] = []

        for n, track in enumerate(tracks):
            out = out_dir / f"track{n}.wav"
            run_ffmpeg([
                "-y",
                "-i", str(source_path),
                "-map", f"0:{track['index']}",
                "-ac", "1",
                "-ar", "16000",
                "-c:a", "pcm_s16le",
                str(out),
            ])
            outputs.append(out)

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
