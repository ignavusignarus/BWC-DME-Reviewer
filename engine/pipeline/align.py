"""Stage 6: word-level forced alignment (WhisperX wav2vec2) + transcript.json.

Reads ``transcribe-raw.json`` (from Stage 5) and ``enhanced/track0.wav``,
runs WhisperX wav2vec2 forced alignment to add per-word
``{word, start, end, score}`` arrays to each segment, then assembles the
final ``transcript.json`` at the source cache root with the brief §4.8
top-level schema.

The alignment model loads once per engine process via a module-level cache.
Tests mock ``align_segments`` at the boundary; the underlying WhisperX +
transformers calls are not exercised in unit tests.
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
from engine.version import BWC_CLIPPER_VERSION

STAGE_NAME = "align"

# Confidence thresholds for the derived low_confidence flag (brief §4.5).
NO_SPEECH_PROB_THRESHOLD = 0.6
LOGPROB_THRESHOLD = -1.0
COMPRESSION_RATIO_THRESHOLD = 2.4

_align_init = None


def _get_align_model(language_code: str = "en"):
    """Lazy-load and cache the WhisperX align model + metadata."""
    global _align_init
    if _align_init is None:
        import whisperx
        device = select_device()
        model, metadata = whisperx.load_align_model(language_code=language_code, device=device)
        _align_init = (model, metadata)
    return _align_init


def align_segments(segments: list[dict], audio_path: Path) -> list[dict]:
    """Run WhisperX wav2vec2 forced alignment over the given segments.
    Returns the same segments with a ``words`` field added per segment.

    Tests mock this function — the underlying WhisperX calls are not
    exercised in unit tests.
    """
    import whisperx

    model, metadata = _get_align_model()
    audio = whisperx.load_audio(str(audio_path))
    aligned = whisperx.align(
        segments,
        model,
        metadata,
        audio,
        device=select_device(),
        return_char_alignments=False,
    )
    # WhisperX returns a dict with a "segments" key. Each segment has a "words"
    # list of {word, start, end, score} dicts. Strip any extra fields for
    # schema cleanliness.
    out = []
    for s in aligned.get("segments", []):
        words = [
            {
                "word": w.get("word", ""),
                "start": float(w.get("start", 0.0)),
                "end": float(w.get("end", 0.0)),
                "score": float(w.get("score", 0.0)),
            }
            for w in s.get("words", [])
        ]
        out.append({**s, "words": words})
    return out


def _is_low_confidence(segment: dict) -> bool:
    """Per brief §4.5: flag a segment as low_confidence when any of the
    decoder-derived metrics crosses the threshold."""
    if segment.get("no_speech_prob", 0.0) > NO_SPEECH_PROB_THRESHOLD:
        return True
    if segment.get("avg_logprob", 0.0) < LOGPROB_THRESHOLD:
        return True
    if segment.get("compression_ratio", 0.0) > COMPRESSION_RATIO_THRESHOLD:
        return True
    return False


def _read_source_metadata(cache_dir: Path) -> dict:
    metadata_path = cache_dir / "source.json"
    if not metadata_path.is_file():
        raise FileNotFoundError(f"source.json missing in {cache_dir}")
    return json.loads(metadata_path.read_text(encoding="utf-8"))


def _read_source_sha256(cache_dir: Path) -> str:
    sha_path = cache_dir / "source.sha256"
    if not sha_path.is_file():
        return ""
    return sha_path.read_text(encoding="utf-8").strip()


def _build_transcript(source_path: Path, cache_dir: Path, segments_with_words: list[dict]) -> dict:
    """Assemble the brief §4.8 top-level transcript.json schema."""
    source_metadata = _read_source_metadata(cache_dir)
    tracks = source_metadata.get("audio_tracks", [])
    duration_seconds = tracks[0]["duration_seconds"] if tracks else 0.0

    enriched_segments = []
    for s in segments_with_words:
        enriched = {
            "id": s.get("id", 0),
            "start": s.get("start", 0.0),
            "end": s.get("end", 0.0),
            "text": s.get("text", ""),
            "words": s.get("words", []),
            "avg_logprob": s.get("avg_logprob", 0.0),
            "no_speech_prob": s.get("no_speech_prob", 0.0),
            "compression_ratio": s.get("compression_ratio", 0.0),
            "low_confidence": _is_low_confidence(s),
        }
        enriched_segments.append(enriched)

    return {
        "schema_version": "1.0",
        "source": {
            "path": str(source_path).replace("\\", "/"),
            "sha256": _read_source_sha256(cache_dir),
            "duration_seconds": duration_seconds,
            "tracks": tracks,
        },
        "processing": {
            "pipeline_version": BWC_CLIPPER_VERSION,
            "whisper_model": "large-v3",
            "vad": "silero",
            "diarization": None,
            "enhanced": True,
            "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        },
        "speakers": [],
        "segments": enriched_segments,
    }


def run_align_stage(source_path: Path, cache_dir: Path) -> Path:
    """Align words and write transcript.json. Returns the JSON path.

    ``source_path`` is the original media file (used to populate
    ``source.path`` in transcript.json per brief §4.8); audio for alignment
    is read from ``cache_dir / enhanced / track0.wav``.

    Raises:
        FileNotFoundError: source.json, transcribe-raw.json, or enhanced
            track 0 missing.
        RuntimeError: WhisperX inference failed.
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
        raw_path = cache_dir / "transcribe-raw.json"
        if not raw_path.is_file():
            raise FileNotFoundError(f"transcribe-raw.json missing in {cache_dir}")

        audio_path = cache_dir / "enhanced" / "track0.wav"
        if not audio_path.is_file():
            raise FileNotFoundError(f"expected enhanced track missing: {audio_path}")

        raw = json.loads(raw_path.read_text(encoding="utf-8"))
        raw_segments = raw.get("segments", [])

        if raw_segments:
            aligned = align_segments(raw_segments, audio_path)
        else:
            aligned = []

        transcript = _build_transcript(source_path, cache_dir, aligned)
        out_path = cache_dir / "transcript.json"
        out_path.write_text(json.dumps(transcript, indent=2), encoding="utf-8")

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
