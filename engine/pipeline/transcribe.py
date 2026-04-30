"""Stage 5: speech-to-text transcription (faster-whisper large-v3).

Reads ``enhanced/track0.wav`` (from Stage 3), runs faster-whisper large-v3
with the anti-hallucination decoder parameters from brief §4.5, and writes
``transcribe-raw.json`` at the source cache root containing the segment
list in a WhisperX-compatible dict format. Stage 6 reads this intermediate
file and produces the final ``transcript.json``.

V1 transcribes track 0 only. Multi-track transcription waits for the
wearer-detection feature in M7+.

The model loads once per engine process via a module-level cache. Tests
mock ``transcribe_audio_file`` at the boundary; the underlying
faster-whisper calls are not exercised in unit tests.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from engine.device import select_device
from engine.pipeline.state import (
    StageStatus,
    load_state,
    save_state,
    update_stage,
)

STAGE_NAME = "transcribe"

# Brief §4.5 decoder parameters — anti-hallucination on noisy BWC audio.
WHISPER_DECODER_PARAMS = {
    "beam_size": 5,
    "patience": 1.0,
    "condition_on_previous_text": False,
    "no_speech_threshold": 0.6,
    "compression_ratio_threshold": 2.4,
    "log_prob_threshold": -1.0,
    "temperature": [0.0, 0.2, 0.4],
    "suppress_tokens": [-1],
    "without_timestamps": False,
    "word_timestamps": False,  # WhisperX align in Stage 6 produces these
    # Skip non-speech regions before Whisper inference. faster-whisper runs
    # Silero VAD internally on the audio, then transcribes only the speech
    # segments. Without this, long stretches of silence (typical in DME
    # audio between exam questions) waste compute AND trigger hallucinations
    # like "Thanks for watching" / "Please subscribe". Stage 4's separate
    # Silero pass writes speech-segments.json for the UI's collapsed-silence
    # timeline; the VAD here is a separate (parameter-matched) Silero
    # invocation internal to faster-whisper. Brief §4.4 parameters applied.
    "vad_filter": True,
    "vad_parameters": {
        "threshold": 0.5,
        "min_speech_duration_ms": 250,
        "min_silence_duration_ms": 300,
        "speech_pad_ms": 200,
    },
}

WHISPER_MODEL_NAME = "large-v3"

_whisper_model = None


def _get_whisper_model():
    """Lazy-load and cache the faster-whisper large-v3 model."""
    global _whisper_model
    if _whisper_model is None:
        from faster_whisper import WhisperModel
        device = select_device()
        # On GPU we use float16 for memory headroom (large-v3 weights ~6 GB at
        # float32 vs ~3 GB at float16). On CPU we stay at int8 to fit in
        # system RAM alongside DF3 + Silero + Electron.
        compute_type = "float16" if device == "cuda" else "int8"
        _whisper_model = WhisperModel(
            WHISPER_MODEL_NAME,
            device=device,
            compute_type=compute_type,
        )
    return _whisper_model


def transcribe_audio_file(in_path: Path) -> list[dict]:
    """Run faster-whisper over a 16 kHz mono WAV. Returns list of segment
    dicts in WhisperX-compatible format: ``{id, start, end, text,
    avg_logprob, no_speech_prob, compression_ratio}``.

    Segment IDs are assigned sequentially (0, 1, 2, ...) — faster-whisper's
    own ``Segment.id`` is always 0 when ``vad_filter=True``, which would
    break the renderer's auto-scroll lookup if forwarded as-is.

    Tests mock this function — the underlying faster-whisper calls are not
    exercised in unit tests.
    """
    model = _get_whisper_model()
    segments_iter, _info = model.transcribe(
        str(in_path),
        **WHISPER_DECODER_PARAMS,
    )
    out = []
    for i, s in enumerate(segments_iter):
        out.append({
            "id": i,
            "start": float(s.start),
            "end": float(s.end),
            "text": s.text,
            "avg_logprob": float(s.avg_logprob),
            "no_speech_prob": float(s.no_speech_prob),
            "compression_ratio": float(s.compression_ratio),
        })
    return out


def run_transcribe_stage(cache_dir: Path) -> Path:
    """Transcribe enhanced/track0.wav. Writes transcribe-raw.json at the
    cache root. Returns the JSON path.

    Raises:
        FileNotFoundError: source.json or enhanced/track0.wav missing.
        RuntimeError: faster-whisper inference failed.
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

        in_path = cache_dir / "enhanced" / "track0.wav"
        if not in_path.is_file():
            raise FileNotFoundError(f"expected enhanced track missing: {in_path}")

        segments = transcribe_audio_file(in_path)

        out_path = cache_dir / "transcribe-raw.json"
        out_path.write_text(
            json.dumps({"segments": segments}, indent=2),
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
