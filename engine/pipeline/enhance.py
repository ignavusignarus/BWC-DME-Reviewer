"""Stage 3: speech enhancement (DeepFilterNet 3).

Reads each ``normalized/track{N}.wav`` (from Stage 2), runs DeepFilterNet 3
over it, writes ``enhanced/track{N}.wav`` at the same sample rate (16 kHz
mono). Per brief §4.3, DF3 is the primary path; no fallback to RNNoise or
no-op. The model loads once per engine process via a module-level cache.

The orchestration in ``run_enhance_stage`` is small. The actual model load
+ inference runs inside ``enhance_audio_file``, which tests mock at that
boundary so unit tests don't need to load DeepFilterNet.
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

STAGE_NAME = "enhance"

# Cache the result of ``init_df()`` (loads model weights — expensive). The
# return is a tuple whose first two elements are ``(model, df_state)``;
# additional elements vary across deepfilternet versions (``suffix``,
# ``epoch``), so we destructure only the first two and use ``*_`` for the
# rest.
_df_init = None


def _get_df_model():
    """Lazy-load and cache the DeepFilterNet 3 model + state."""
    global _df_init
    if _df_init is None:
        from df.enhance import init_df
        # DeepFilterNet 0.5.x does NOT accept a ``default_device`` kwarg in
        # ``init_df()``. Device selection is handled internally via
        # ``df.utils.get_device()``, which already calls
        # ``torch.cuda.is_available()`` and picks ``cuda:0`` automatically when
        # CUDA is present. No explicit device argument is needed here — DF3
        # self-selects GPU whenever a CUDA-enabled torch is installed.
        _df_init = init_df()
    return _df_init


# Chunk size for DF3 enhancement (in seconds at the model's native rate).
# Long audio (60+ minute files) passed as a single tensor triggers
# ``CUDNN_STATUS_NOT_SUPPORTED`` errors deep inside cuDNN's RNN ops — the
# tensor's sequence length exceeds an internal limit. 60-second chunks at
# 48 kHz (~2.9M samples each) run cleanly on a 16 GB VRAM GPU; the
# concatenated output is bit-identical to one-shot processing for shorter
# audio (DF3 is a feed-forward + CRN model with a small temporal context;
# chunk boundaries don't propagate context across, but with 60-second
# chunks the artifact is negligible vs. the per-frame DF3 processing).
_CHUNK_SECONDS = 60


def enhance_audio_file(in_path: Path, out_path: Path) -> None:
    """Read a WAV, run DeepFilterNet 3 over it, write the enhanced WAV.

    DF3 operates internally at 48 kHz. Long inputs are chunked to avoid
    cuDNN's CUDNN_STATUS_NOT_SUPPORTED error on very long sequences; each
    chunk is processed independently and the outputs are concatenated.
    The 48 kHz output is resampled to 16 kHz before writing so the cache
    layout stays consistent for Stage 4 (Silero VAD wants 16 kHz) and
    downstream stages — ``df.enhance.save_audio`` does NOT resample (it
    just writes the tensor's samples at the claimed sample rate), so
    passing 48 kHz audio with sr=16000 would produce a 3x-too-long WAV.

    Tests mock this function — the underlying df calls are not exercised
    in unit tests.
    """
    import torch
    import torchaudio.functional as F
    from df.enhance import enhance, load_audio, save_audio

    model, df_state, *_ = _get_df_model()
    sr_model = df_state.sr()  # 48000 for DF3
    audio, _in_sr = load_audio(str(in_path), sr=sr_model)

    chunk_samples = _CHUNK_SECONDS * sr_model
    total_samples = audio.shape[-1]

    if total_samples <= chunk_samples:
        # Short audio — process whole thing in one pass.
        enhanced = enhance(model, df_state, audio)
    else:
        # Process in fixed-size chunks; concatenate results on CPU so VRAM
        # doesn't accumulate across chunks.
        out_chunks = []
        for start in range(0, total_samples, chunk_samples):
            end = min(start + chunk_samples, total_samples)
            chunk = audio[..., start:end].contiguous()
            chunk_out = enhance(model, df_state, chunk)
            out_chunks.append(chunk_out.cpu())
        enhanced = torch.cat(out_chunks, dim=-1)

    enhanced_16k = F.resample(enhanced, sr_model, 16000)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    save_audio(str(out_path), enhanced_16k, 16000)


def run_enhance_stage(cache_dir: Path) -> list[Path]:
    """Enhance each normalized track. Returns list of output WAV paths.

    Updates pipeline-state.json with running/completed/failed.

    Raises:
        FileNotFoundError: source.json or any normalized/track{N}.wav missing.
        RuntimeError: DF3 inference failed.
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
            in_path = cache_dir / "normalized" / f"track{n}.wav"
            if not in_path.is_file():
                raise FileNotFoundError(f"expected normalized track missing: {in_path}")
            in_paths.append(in_path)

        out_dir = cache_dir / "enhanced"
        out_dir.mkdir(parents=True, exist_ok=True)
        outputs: list[Path] = []

        for n, in_path in enumerate(in_paths):
            out_path = out_dir / f"track{n}.wav"
            enhance_audio_file(in_path, out_path)
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
