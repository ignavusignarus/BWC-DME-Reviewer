# BWC Clipper — Milestone 5: Stage 5 Transcribe + Stage 6 Align + transcript.json — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add Stages 5 and 6 of the transcription pipeline — speech-to-text via faster-whisper large-v3 (Stage 5) and word-level forced alignment via WhisperX (Stage 6) — and produce the canonical `transcript.json` artifact at the per-source cache root. After this milestone, the six-stage pipeline runs end-to-end on a source: extract → normalize → enhance → VAD → transcribe → align, with `transcript.json` enriched with per-segment + per-word timestamps that downstream features (M6 transcript panel, click-to-seek, the collapsed-silence timeline) read from.

**Architecture:** Two new stage modules `engine/pipeline/transcribe.py` and `engine/pipeline/align.py`, each following the M2/M3/M4 stage protocol exactly. Stage 5 produces an intermediate `transcribe-raw.json` (segment list in a WhisperX-compatible dict format); Stage 6 reads it, aligns words, and writes the final `transcript.json` with the brief §4.8 top-level schema. Heavy ML calls are wrapped in helper functions (`transcribe_audio_file`, `align_segments`) that tests mock at the boundary — no real Whisper or wav2vec2 inference in unit tests. Module-level model singletons for the faster-whisper model and the WhisperX align model so each loads once per engine process.

**Tech Stack:** New runtime deps `faster-whisper>=1.0` and `whisperx>=3.1`. WhisperX brings transformers, ctranslate2, pyannote.audio (transitively, used in M7), and friends. Continuing the M4 torchaudio<2.6 pin. Models download on first invocation: faster-whisper large-v3 ≈ 3 GB, wav2vec2 alignment ≈ 300 MB, cached under `%LOCALAPPDATA%\faster_whisper\` and the HuggingFace hub default cache.

**Scope of this milestone:**
- Add `faster-whisper>=1.0` and `whisperx>=3.1` to `pyproject.toml` `dependencies`.
- New `engine/pipeline/transcribe.py` — Stage 5 reads `enhanced/track0.wav`, runs faster-whisper large-v3 with brief §4.5 anti-hallucination decoder params, writes `transcribe-raw.json` (intermediate cache file). Track 0 only — multi-track transcription is a future refinement.
- New `engine/pipeline/align.py` — Stage 6 reads `transcribe-raw.json` + `enhanced/track0.wav`, runs WhisperX wav2vec2 forced alignment to add per-word timestamps, assembles the final `transcript.json` with brief §4.8 top-level schema.
- Append `transcribe` and `align` to `_PIPELINE_STAGES`. M3's chaining handles the rest.
- UI: `STAGE_LABELS` adds `transcribe`: "transcribing…" and `align`: "aligning words…".

**Out of scope for this milestone (deliberately deferred):**
- Stages 7 (diarize) and 8 (wearer-detect). M6+.
- Reviewer UI surfaces — transcript panel, audio player, click-to-seek. M6.
- Initial-prompt / context-names per-source UI. M6 (engine accepts an `initial_prompt` parameter from a per-source `context.json` if present, but no UI to edit it).
- VTT / TXT / DOCX exports. Not in V1.
- Multi-track transcription. M5 transcribes track 0 only; multi-track waits for the wearer-detection feature in M7.
- `low_confidence` thresholding logic — flagged but values stay in the schema; the UI's amber-underline rendering arrives in M6.

---

## File Structure

```
bwc-clipper/
├── pyproject.toml                            MODIFY — add 2 runtime deps
├── engine/
│   ├── pipeline/
│   │   ├── transcribe.py                     NEW — Stage 5, faster-whisper large-v3
│   │   ├── align.py                          NEW — Stage 6, WhisperX align + transcript.json
│   │   └── runner.py                         MODIFY — append transcribe + align to _PIPELINE_STAGES
│   └── version.py                            MODIFY — bump BWC_CLIPPER_VERSION (transcript schema is sensitive to it)
├── editor/
│   └── components/
│       ├── FileListItem.jsx                  MODIFY — add 2 STAGE_LABELS entries
│       └── FileListItem.test.jsx             MODIFY — add 2 stage-label tests
├── tests/
│   ├── test_pipeline_transcribe.py           NEW
│   ├── test_pipeline_align.py                NEW
│   └── test_pipeline_runner.py               MODIFY — extend chained-runner test for 6 stages
└── README.md                                 MODIFY — update status to M5
```

**Why split transcribe.py and align.py:** They're separate stages with separate models and separate cache files. Keeping them in distinct files mirrors the M2–M4 decomposition (`extract.py` / `normalize.py` / `enhance.py` / `vad.py`). Combining them would couple the model lifecycle in confusing ways.

**Why bump `BWC_CLIPPER_VERSION` in `engine/version.py`:** transcript.json embeds `processing.pipeline_version` so consumers know the schema/model version they're reading. Adding the transcript artifact is a meaningful schema-affecting change.

---

## Reference patterns

| New code in M5 | Reference (read for pattern) |
|---|---|
| `engine/pipeline/transcribe.py` | `engine/pipeline/enhance.py` — module-level model singleton + helper-boundary mock + stage protocol |
| `engine/pipeline/align.py` | `engine/pipeline/vad.py` — JSON-output-at-cache-root pattern + helper-boundary mock |
| transcript.json top-level assembly | brief §4.8 schema verbatim |
| Per-segment dict shape | brief §4.5 — `{id, start, end, text, words[], avg_logprob, no_speech_prob, compression_ratio, low_confidence}` |
| `_PIPELINE_STAGES` extension | runner.py from M4 — append two more entries with the `(_source, cache)` signature lambda |

**Brief reference:**
- §4.5 (Transcription): faster-whisper / WhisperX with `large-v3`. Decoder params for anti-hallucination: `condition_on_previous_text=False`, `no_speech_threshold=0.6`, `compression_ratio_threshold=2.4`, `logprob_threshold=-1.0`, `temperature=[0.0, 0.2, 0.4]`, `beam_size=5`, `patience=1.0`, `suppress_tokens=[-1]`. Word-level alignment via WhisperX wav2vec2 is non-negotiable.
- §4.8 (Output Assembly): top-level `transcript.json` schema. `speakers` is an array (empty in M5, populated by M7 diarization). `processing.timestamp_utc` is the wall-clock time of the run. `low_confidence` per segment is derived from the thresholds.

---

## Testing strategy

- **No real model inference in tests.** Both stages have helpers (`transcribe_audio_file(in_path)` returning a list of segment dicts, `align_segments(segments, audio_path)` returning the same list with `words` added). Tests mock these helpers and verify the orchestration logic — file paths, JSON schema, state transitions, cache layout. Real model loading is verified at the manual launch step.
- **No new pytest deps.** Continuing with `unittest.mock`.
- **Mock segment shape:** WhisperX expects segments shaped like `{"start": float, "end": float, "text": str}`. After `align()`, each gains a `words` list. Faster-whisper Segment objects are converted to dicts at the Stage 5 boundary.

---

## Pip install caveats (read before Task 2)

Adding `faster-whisper` and `whisperx` brings substantial deps. Install size estimate on top of M4:

- `faster-whisper`: ~5 MB package + ~500 MB ctranslate2 wheel transitively
- `whisperx`: ~10 MB + transformers (~150 MB) + a couple smaller packages
- Plus large-v3 model and wav2vec2 model downloads on first inference (~3 GB total)

**Expected pip install time:** 3–10 minutes, dominated by ctranslate2 + transformers wheels.

**The torchaudio<2.6 pin is in place from M4.** WhisperX's torch dep is loose — `torch>=1.9` per its setup.py — so the pin should hold. If pip complains about an unsatisfiable constraint during install, surface the conflict; do NOT remove the pin (it's protecting deepfilternet 0.5.6).

**On manual launch (Task 8):** the engine downloads ~3 GB of model files the first time it transcribes anything. This is unavoidable for V1; the M7/M8 packaging milestone will handle installer-time model bundling.

---

## Tasks

### Task 1: Create milestone-5 branch

- [ ] **Step 1: Verify clean working tree on main**

```bash
cd "C:/Claude Code Projects/BWC Reviewer"
git status
git rev-parse --abbrev-ref HEAD
git log -1 --oneline
```

Expected: clean, on `main`, last commit `4bbc057` (M4 merge).

- [ ] **Step 2: Branch**

```bash
git checkout -b milestone-5-transcribe-align
```

---

### Task 2: Add `faster-whisper` and `whisperx` to `pyproject.toml`; install

**Files:**
- Modify: `pyproject.toml`

- [ ] **Step 1: Edit `pyproject.toml`**

Find the existing dependencies block (added in M4):

```toml
dependencies = [
    "torch>=1.12,<2.6",
    "torchaudio>=0.12,<2.6",
    "deepfilternet>=0.5",
    "silero-vad>=5.0",
    "soundfile>=0.12",
]
```

Replace with:

```toml
dependencies = [
    "torch>=1.12,<2.6",
    "torchaudio>=0.12,<2.6",
    "deepfilternet>=0.5",
    "silero-vad>=5.0",
    "soundfile>=0.12",
    "faster-whisper>=1.0",
    "whisperx>=3.1",
]
```

- [ ] **Step 2: Reinstall the project to pull new deps**

```bash
.venv/Scripts/python.exe -m pip install -e ".[dev]"
```

**Expected: 3–10 minute wait** for ctranslate2 + transformers wheels. If pip fails with a torchaudio constraint conflict, STOP and surface the error — do not remove the `<2.6` pin (it's protecting deepfilternet).

- [ ] **Step 3: Verify the deps import cleanly**

```bash
.venv/Scripts/python.exe -c "import faster_whisper; import whisperx; print('OK')"
```

Expected: `OK`. If WhisperX emits a `UserWarning` from its own modules, that's fine — only fail-on-error.

- [ ] **Step 4: Run the existing test suite to confirm zero regressions**

```bash
.venv/Scripts/python.exe -m pytest -v
```

Expected: 93 tests pass (same as M4 final).

- [ ] **Step 5: Commit**

```bash
git add pyproject.toml
git commit -m "engine: add faster-whisper and whisperx as runtime deps"
```

---

### Task 3: `engine/pipeline/transcribe.py` — Stage 5 (TDD)

**Files:**
- Create: `tests/test_pipeline_transcribe.py`
- Create: `engine/pipeline/transcribe.py`

Reads `enhanced/track0.wav` and runs faster-whisper large-v3 with brief §4.5 decoder params. Writes `transcribe-raw.json` (intermediate cache) at the source cache root containing the segment list as a WhisperX-compatible dict array. Module-level singleton caches the WhisperModel.

- [ ] **Step 1: Create `tests/test_pipeline_transcribe.py`**

```python
"""Tests for engine.pipeline.transcribe — Stage 5 (faster-whisper large-v3)."""
import json
from pathlib import Path
from unittest.mock import patch

import pytest

from engine.pipeline.transcribe import run_transcribe_stage
from engine.pipeline.state import load_state


def _touch(p: Path, content: bytes = b""):
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_bytes(content)


def _write_source_metadata_with_enhanced(cache_dir: Path, n_tracks: int):
    """Set up the cache as if Stages 1-4 have completed."""
    cache_dir.mkdir(parents=True, exist_ok=True)
    tracks = [
        {"index": i + 1, "codec_name": "aac", "sample_rate": 48000, "channels": 1, "duration_seconds": 12.0}
        for i in range(n_tracks)
    ]
    (cache_dir / "source.json").write_text(json.dumps({"audio_tracks": tracks}))
    enhanced = cache_dir / "enhanced"
    enhanced.mkdir(exist_ok=True)
    for i in range(n_tracks):
        _touch(enhanced / f"track{i}.wav", b"fake-enhanced-wav")


def test_run_transcribe_stage_writes_transcribe_raw_json(tmp_path: Path):
    cache_dir = tmp_path / ".bwcclipper" / "officer"
    _write_source_metadata_with_enhanced(cache_dir, n_tracks=1)

    fake_segments = [
        {"id": 0, "start": 0.5, "end": 3.2, "text": "hello world",
         "avg_logprob": -0.4, "no_speech_prob": 0.1, "compression_ratio": 1.8},
        {"id": 1, "start": 3.5, "end": 5.0, "text": "second segment",
         "avg_logprob": -0.5, "no_speech_prob": 0.2, "compression_ratio": 1.9},
    ]

    with patch("engine.pipeline.transcribe.transcribe_audio_file",
               return_value=fake_segments) as mock:
        result = run_transcribe_stage(cache_dir)

    assert result == cache_dir / "transcribe-raw.json"
    assert result.is_file()
    data = json.loads(result.read_text(encoding="utf-8"))
    assert data["segments"] == fake_segments

    # Helper called once with the track 0 enhanced path
    assert mock.call_count == 1
    args, _ = mock.call_args
    assert args[0] == cache_dir / "enhanced" / "track0.wav"


def test_run_transcribe_stage_writes_pipeline_state(tmp_path: Path):
    cache_dir = tmp_path / ".bwcclipper" / "officer"
    _write_source_metadata_with_enhanced(cache_dir, n_tracks=1)

    with patch("engine.pipeline.transcribe.transcribe_audio_file", return_value=[]):
        run_transcribe_stage(cache_dir)

    state = load_state(cache_dir)
    transcribe = state.stages["transcribe"]
    assert transcribe["status"] == "completed"
    assert "started_at" in transcribe and "completed_at" in transcribe
    assert transcribe["outputs"] == [str(cache_dir / "transcribe-raw.json")]


def test_run_transcribe_stage_marks_failed_on_helper_error(tmp_path: Path):
    cache_dir = tmp_path / ".bwcclipper" / "officer"
    _write_source_metadata_with_enhanced(cache_dir, n_tracks=1)

    with patch("engine.pipeline.transcribe.transcribe_audio_file",
               side_effect=RuntimeError("boom")):
        with pytest.raises(RuntimeError, match="boom"):
            run_transcribe_stage(cache_dir)

    state = load_state(cache_dir)
    transcribe = state.stages["transcribe"]
    assert transcribe["status"] == "failed"
    assert "boom" in transcribe.get("error", "")


def test_run_transcribe_stage_raises_if_source_metadata_missing(tmp_path: Path):
    cache_dir = tmp_path / ".bwcclipper" / "officer"
    cache_dir.mkdir(parents=True)

    with pytest.raises(FileNotFoundError):
        run_transcribe_stage(cache_dir)


def test_run_transcribe_stage_raises_if_enhanced_track0_missing(tmp_path: Path):
    cache_dir = tmp_path / ".bwcclipper" / "officer"
    _write_source_metadata_with_enhanced(cache_dir, n_tracks=1)
    (cache_dir / "enhanced" / "track0.wav").unlink()

    with pytest.raises(FileNotFoundError):
        run_transcribe_stage(cache_dir)


def test_run_transcribe_stage_only_processes_track0_for_now(tmp_path: Path):
    """V1 transcribes track 0 only; track 1+ are ignored. Multi-track is M7+."""
    cache_dir = tmp_path / ".bwcclipper" / "officer"
    _write_source_metadata_with_enhanced(cache_dir, n_tracks=3)

    with patch("engine.pipeline.transcribe.transcribe_audio_file", return_value=[]) as mock:
        run_transcribe_stage(cache_dir)

    assert mock.call_count == 1
    args, _ = mock.call_args
    assert args[0].name == "track0.wav"
```

- [ ] **Step 2: Run, confirm FAIL**

```bash
.venv/Scripts/python.exe -m pytest tests/test_pipeline_transcribe.py -v
```

- [ ] **Step 3: Create `engine/pipeline/transcribe.py`**

```python
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
    "logprob_threshold": -1.0,
    "temperature": [0.0, 0.2, 0.4],
    "suppress_tokens": [-1],
    "without_timestamps": False,
    "word_timestamps": False,  # WhisperX align in Stage 6 produces these
}

WHISPER_MODEL_NAME = "large-v3"

_whisper_model = None


def _get_whisper_model():
    """Lazy-load and cache the faster-whisper large-v3 model."""
    global _whisper_model
    if _whisper_model is None:
        from faster_whisper import WhisperModel
        # device="cpu", compute_type="float32" is the safe default. Users with
        # a CUDA-enabled torch install will get auto-detection in a future
        # milestone; for V1 we pin to CPU for reproducibility.
        _whisper_model = WhisperModel(
            WHISPER_MODEL_NAME,
            device="cpu",
            compute_type="float32",
        )
    return _whisper_model


def transcribe_audio_file(in_path: Path, initial_prompt: str | None = None) -> list[dict]:
    """Run faster-whisper over a 16 kHz mono WAV. Returns list of segment
    dicts in WhisperX-compatible format: ``{id, start, end, text,
    avg_logprob, no_speech_prob, compression_ratio}``.

    Tests mock this function — the underlying faster-whisper calls are not
    exercised in unit tests.
    """
    model = _get_whisper_model()
    segments_iter, _info = model.transcribe(
        str(in_path),
        initial_prompt=initial_prompt,
        **WHISPER_DECODER_PARAMS,
    )
    # faster-whisper returns an iterator of Segment objects. Convert to dicts
    # in the format WhisperX align() expects.
    out = []
    for s in segments_iter:
        out.append({
            "id": int(s.id),
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

        # Optional initial prompt (per-source context names panel — populated
        # by future milestones). Stored in cache_dir/context.json if present.
        initial_prompt = _read_initial_prompt(cache_dir)

        segments = transcribe_audio_file(in_path, initial_prompt=initial_prompt)

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


def _read_initial_prompt(cache_dir: Path) -> str | None:
    """Read context.json if present and assemble an initial_prompt string.

    Schema (V1, additive — UI to write this lands in M6):
        {"names": ["Officer Garcia", ...], "locations": ["Crenshaw Blvd", ...]}

    Returns None if the file is missing or empty.
    """
    context_path = cache_dir / "context.json"
    if not context_path.is_file():
        return None
    try:
        ctx = json.loads(context_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return None
    names = ctx.get("names") or []
    locations = ctx.get("locations") or []
    if not names and not locations:
        return None
    parts = ["This is audio from a recorded interaction."]
    if names:
        parts.append(f"Names mentioned may include: {', '.join(names)}.")
    if locations:
        parts.append(f"Locations include: {', '.join(locations)}.")
    return " ".join(parts)
```

- [ ] **Step 4: Run, confirm 6 passed**

```bash
.venv/Scripts/python.exe -m pytest tests/test_pipeline_transcribe.py -v
```

- [ ] **Step 5: Commit**

```bash
git add engine/pipeline/transcribe.py tests/test_pipeline_transcribe.py
git commit -m "engine: add Stage 5 transcribe — faster-whisper large-v3"
```

---

### Task 4: `engine/pipeline/align.py` — Stage 6 + transcript.json (TDD)

**Files:**
- Create: `tests/test_pipeline_align.py`
- Create: `engine/pipeline/align.py`

Stage 6 reads `transcribe-raw.json` + `enhanced/track0.wav`, runs WhisperX wav2vec2 forced alignment to add per-word `{word, start, end, score}` arrays to each segment, and assembles the final `transcript.json` with the brief §4.8 top-level schema.

`transcript.json` top-level structure:

```json
{
    "schema_version": "1.0",
    "source": {
        "path": "<source media path>",
        "sha256": "<hex>",
        "duration_seconds": 1234.5,
        "tracks": [{"index": 0, ...}]
    },
    "processing": {
        "pipeline_version": "<engine version>",
        "whisper_model": "large-v3",
        "vad": "silero",
        "diarization": null,
        "enhanced": true,
        "timestamp_utc": "2026-04-29T..."
    },
    "speakers": [],
    "segments": [...]
}
```

Per-segment shape (brief §4.5):

```json
{
    "id": 0,
    "start": 0.5,
    "end": 3.2,
    "text": "hello world",
    "words": [{"word": "hello", "start": 0.5, "end": 0.9, "score": 0.95}, ...],
    "avg_logprob": -0.4,
    "no_speech_prob": 0.1,
    "compression_ratio": 1.8,
    "low_confidence": false
}
```

`low_confidence` is derived: `(no_speech_prob > 0.6) OR (avg_logprob < -1.0) OR (compression_ratio > 2.4)`.

- [ ] **Step 1: Create `tests/test_pipeline_align.py`**

```python
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

    with patch("engine.pipeline.align.align_segments", side_effect=lambda segs, path: [{**s, "words": []} for s in segs]):
        run_align_stage(cache_dir)

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
```

- [ ] **Step 2: Run, confirm FAIL**

```bash
.venv/Scripts/python.exe -m pytest tests/test_pipeline_align.py -v
```

- [ ] **Step 3: Create `engine/pipeline/align.py`**

```python
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
        # device="cpu" matches the M5 transcribe stage. CUDA enablement is M7+.
        model, metadata = whisperx.load_align_model(language_code=language_code, device="cpu")
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
        device="cpu",
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
```

- [ ] **Step 4: Run, confirm 7 passed**

```bash
.venv/Scripts/python.exe -m pytest tests/test_pipeline_align.py -v
```

- [ ] **Step 5: Commit**

```bash
git add engine/pipeline/align.py tests/test_pipeline_align.py
git commit -m "engine: add Stage 6 align — WhisperX word alignment + transcript.json"
```

---

### Task 5: Append transcribe + align to `_PIPELINE_STAGES`; extend chained-runner test (TDD)

**Files:**
- Modify: `engine/pipeline/runner.py`
- Modify: `tests/test_pipeline_runner.py`

The runner already chains stages serially (M3 + M4). M5 just adds two more entries to `_PIPELINE_STAGES` plus a six-stage integration test.

- [ ] **Step 1: Append a new test to `tests/test_pipeline_runner.py`**

Append at the end (don't modify existing tests):

```python
def test_runner_runs_all_six_stages_in_order(tmp_path: Path):
    """Full pipeline through M5: extract → normalize → enhance → vad →
    transcribe → align → completed."""
    from engine.pipeline.runner import PipelineRunner

    source = tmp_path / "x.mp4"
    _touch(source, b"x")

    def _writes_output(args, **kwargs):
        Path(args[-1]).touch()
        return ""

    def _enhance_writes(in_path, out_path):
        Path(out_path).parent.mkdir(parents=True, exist_ok=True)
        Path(out_path).touch()

    fake_segments = [
        {"id": 0, "start": 0.5, "end": 3.2, "text": "hello world",
         "avg_logprob": -0.4, "no_speech_prob": 0.1, "compression_ratio": 1.8},
    ]

    runner = PipelineRunner()
    try:
        with patch("engine.pipeline.extract.probe_audio_tracks") as probe_mock, \
             patch("engine.pipeline.extract.run_ffmpeg", side_effect=_writes_output), \
             patch("engine.pipeline.normalize.run_loudnorm_measure",
                   return_value={"input_i": "-12", "input_tp": "-1", "input_lra": "5",
                                 "input_thresh": "-20", "target_offset": "0"}), \
             patch("engine.pipeline.normalize.run_ffmpeg", side_effect=_writes_output), \
             patch("engine.pipeline.enhance.enhance_audio_file", side_effect=_enhance_writes), \
             patch("engine.pipeline.vad.vad_audio_file", return_value=[{"start": 0.0, "end": 1.0}]), \
             patch("engine.pipeline.transcribe.transcribe_audio_file", return_value=fake_segments), \
             patch("engine.pipeline.align.align_segments",
                   side_effect=lambda segs, path: [{**s, "words": [{"word": "hello", "start": 0.5, "end": 0.9, "score": 0.95}]} for s in segs]):
            probe_mock.return_value = [
                {"index": 0, "codec_name": "aac", "sample_rate": 48000, "channels": 1, "duration_seconds": 1.0},
            ]
            future = runner.submit_pipeline(tmp_path, source)
            future.result(timeout=15)
        assert runner.get_status(tmp_path, source) == "completed"

        # Verify all six stages completed in pipeline-state.json
        from engine.pipeline.state import load_state
        from engine.source import source_cache_dir
        cache_dir = source_cache_dir(tmp_path, source)
        state = load_state(cache_dir)
        for stage_name in ("extract", "normalize", "enhance", "vad", "transcribe", "align"):
            assert state.stages.get(stage_name, {}).get("status") == "completed", \
                f"stage {stage_name} not completed"

        # transcript.json was written with correct top-level schema
        import json as _json
        transcript = _json.loads((cache_dir / "transcript.json").read_text(encoding="utf-8"))
        assert transcript["schema_version"] == "1.0"
        assert transcript["processing"]["whisper_model"] == "large-v3"
        assert len(transcript["segments"]) == 1
        assert transcript["segments"][0]["text"] == "hello world"
        assert transcript["segments"][0]["low_confidence"] is False
    finally:
        runner.shutdown()
```

- [ ] **Step 2: Run the new test — fail because transcribe + align aren't in _PIPELINE_STAGES**

```bash
.venv/Scripts/python.exe -m pytest tests/test_pipeline_runner.py::test_runner_runs_all_six_stages_in_order -v
```

- [ ] **Step 3: Modify `engine/pipeline/runner.py`**

Find:

```python
from engine.pipeline.enhance import run_enhance_stage
from engine.pipeline.extract import run_extract_stage
from engine.pipeline.normalize import run_normalize_stage
from engine.pipeline.state import StageStatus, load_state
from engine.pipeline.vad import run_vad_stage
from engine.source import source_cache_dir
```

Replace with (alphabetical order):

```python
from engine.pipeline.align import run_align_stage
from engine.pipeline.enhance import run_enhance_stage
from engine.pipeline.extract import run_extract_stage
from engine.pipeline.normalize import run_normalize_stage
from engine.pipeline.state import StageStatus, load_state
from engine.pipeline.transcribe import run_transcribe_stage
from engine.pipeline.vad import run_vad_stage
from engine.source import source_cache_dir
```

Then find:

```python
_PIPELINE_STAGES: list[tuple[str, Callable]] = [
    ("extract", lambda source, cache: run_extract_stage(source, cache)),
    ("normalize", lambda _source, cache: run_normalize_stage(cache)),
    ("enhance", lambda _source, cache: run_enhance_stage(cache)),
    ("vad", lambda _source, cache: run_vad_stage(cache)),
]
```

Replace with:

```python
_PIPELINE_STAGES: list[tuple[str, Callable]] = [
    ("extract", lambda source, cache: run_extract_stage(source, cache)),
    ("normalize", lambda _source, cache: run_normalize_stage(cache)),
    ("enhance", lambda _source, cache: run_enhance_stage(cache)),
    ("vad", lambda _source, cache: run_vad_stage(cache)),
    ("transcribe", lambda _source, cache: run_transcribe_stage(cache)),
    ("align", lambda source, cache: run_align_stage(source, cache)),
]
```

- [ ] **Step 4: Run the new test — confirm pass**

```bash
.venv/Scripts/python.exe -m pytest tests/test_pipeline_runner.py::test_runner_runs_all_six_stages_in_order -v
```

- [ ] **Step 5: Run the full pytest suite**

Pre-existing chained-pipeline tests (`test_runner_submit_pipeline_runs_extract_then_normalize`,
`test_runner_skips_extract_if_already_completed`, `test_runner_get_status_failed_after_normalize_error`,
`test_runner_get_status_returns_running_with_stage_name`, `test_runner_runs_all_four_stages_in_order`,
`test_state_endpoint_completed_after_pipeline`) will fail because they don't mock the new transcribe/align
stages. M4 hit the same issue when adding enhance + vad — the fix is identical: add the new mocks to
each affected test.

For each failing test, add these to the existing `with patch(...)` block:

```python
             patch("engine.pipeline.transcribe.transcribe_audio_file", return_value=[]), \
             patch("engine.pipeline.align.align_segments", return_value=[]), \
```

The specific tests that need the new mocks (i.e., they trigger `submit_pipeline` → run-to-completion or directly assert pipeline-state transitions):

In `tests/test_pipeline_runner.py`:
- `test_runner_submit_pipeline_runs_extract_then_normalize`
- `test_runner_skips_extract_if_already_completed`
- `test_runner_get_status_returns_running_with_stage_name`
- `test_runner_runs_all_four_stages_in_order`

In `tests/test_server_source.py`:
- `test_process_endpoint_submits_pipeline_and_returns_status`
- `test_state_endpoint_completed_after_pipeline`

Tests that don't need updates (they fail before reaching the new stages):
- `test_runner_get_status_idle_for_unprocessed_source` — never submits anything
- `test_runner_get_status_failed_after_extract_error` — fails at extract; pipeline halts before transcribe
- `test_runner_get_status_failed_after_normalize_error` — fails at normalize; pipeline halts before transcribe
- `test_state_endpoint_idle_for_unprocessed_source` — no submit
- `test_process_endpoint_400_for_missing_fields` — 400 short-circuit
- `test_state_endpoint_400_for_missing_query_params` — 400 short-circuit

Sanity-check by grepping the test files for `submit_pipeline` and `state_endpoint_completed` after applying the fix — every match site should have the new mocks. Then:

```bash
.venv/Scripts/python.exe -m pytest -v
```

Expected: 93 (M4 final) + 6 (transcribe) + 7 (align) + 1 (chained 6-stage) = 107 tests passing.

- [ ] **Step 6: Commit**

```bash
git add engine/pipeline/runner.py tests/test_pipeline_runner.py tests/test_server_source.py
git commit -m "engine: append transcribe + align to pipeline; chained-runner test"
```

---

### Task 6: UI — `STAGE_LABELS` for transcribe + align (TDD)

**Files:**
- Modify: `editor/components/FileListItem.test.jsx`
- Modify: `editor/components/FileListItem.jsx`

- [ ] **Step 1: Append two tests inside the existing `'FileListItem stage-aware status'` describe block**

```jsx
    it('renders "transcribing…" for running:transcribe', () => {
        render(
            <FileListItem
                file={sampleFile}
                selected={false}
                onSelect={() => {}}
                status="running:transcribe"
            />,
        );
        expect(screen.getByText(/transcribing/i)).toBeDefined();
    });

    it('renders "aligning words…" for running:align', () => {
        render(
            <FileListItem
                file={sampleFile}
                selected={false}
                onSelect={() => {}}
                status="running:align"
            />,
        );
        expect(screen.getByText(/aligning words/i)).toBeDefined();
    });
```

- [ ] **Step 2: Run, confirm new tests FAIL**

```bash
npx vitest run editor/components/FileListItem.test.jsx
```

- [ ] **Step 3: Modify `editor/components/FileListItem.jsx`**

Find:

```jsx
const STAGE_LABELS = {
    extract: 'extracting…',
    normalize: 'normalizing…',
    enhance: 'enhancing…',
    vad: 'detecting speech…',
    // Future stages (M5+): transcribe, align, diarize, etc.
};
```

Replace with:

```jsx
const STAGE_LABELS = {
    extract: 'extracting…',
    normalize: 'normalizing…',
    enhance: 'enhancing…',
    vad: 'detecting speech…',
    transcribe: 'transcribing…',
    align: 'aligning words…',
    // Future stages (M6+): diarize, wearer-detect.
};
```

- [ ] **Step 4: Run, confirm 18 FileListItem tests pass (16 + 2 new)**

```bash
npx vitest run editor/components/FileListItem.test.jsx
```

- [ ] **Step 5: Run the full vitest suite**

```bash
npm test
```

Expected: 33 tests pass (31 + 2 new).

- [ ] **Step 6: Build production bundle (sanity check)**

```bash
NODE_ENV=production npm run build:editor
```

- [ ] **Step 7: Commit**

```bash
git add editor/components/FileListItem.jsx editor/components/FileListItem.test.jsx
git commit -m "editor: add stage labels for transcribe and align"
```

---

### Task 7: Bump `engine/version.py`

**Files:**
- Modify: `engine/version.py`

`transcript.json` embeds `processing.pipeline_version`. Bumping the version makes it discoverable that the schema-producing-process changed, even though the on-disk schema_version stays at `1.0`.

- [ ] **Step 1: Bump the version**

Find:

```python
BWC_CLIPPER_VERSION = "2026.04.29a"
```

Replace with:

```python
BWC_CLIPPER_VERSION = "2026.04.29b"
```

- [ ] **Step 2: Run pytest to verify the version test still passes**

```bash
.venv/Scripts/python.exe -m pytest tests/test_version.py -v
```

The existing test asserts the version starts with year ≥ 2026 and is a non-empty string — bumping the suffix doesn't affect that.

- [ ] **Step 3: Commit**

```bash
git add engine/version.py
git commit -m "engine: bump version for M5 transcript.json artifact"
```

---

### Task 8: Manual launch verification

**Files:** none (verification, no commit)

This is the long one. The first transcribe run downloads ~3 GB of model files (faster-whisper large-v3 + wav2vec2 alignment). Subsequent runs reuse the cache.

- [ ] **Step 1: Build editor + run all tests one more time**

```bash
npm run build:editor
.venv/Scripts/python.exe -m pytest -v
npm test
```

- [ ] **Step 2: Launch the app**

```bash
npm start
```

Expected manual verification (long wait — be patient):
- Splash → main window opens.
- Open the folder containing the previously-processed source (e.g., `Samples/`).
- Click the previously-processed source. Status indicator should:
  1. Briefly pass through `enhanced` and `VAD` if needed (cached from M4 if you tested then).
  2. **First transcribe run**: model download visible in engine logs (`[engine stdout] ... downloading large-v3 ...`). Splash and UI may sit at `transcribing…` for **5-15 minutes** of download + same again for inference on a 60-min source. **Be patient.**
  3. Then `aligning words…` for ~1-2 minutes (wav2vec2 download + alignment).
  4. Finally `✓` (green).
- Inspect `Samples/.bwcclipper/<source-stem>/`:
  - `transcribe-raw.json` — new (intermediate)
  - `transcript.json` — new, with brief §4.8 schema
- Pretty-print `transcript.json` and skim:
  - `processing.whisper_model` is `"large-v3"`
  - `speakers` is `[]` (M5; M6+ fills)
  - `segments[0]` has `text`, `words[]`, `avg_logprob`, etc.
  - Words have `start` / `end` / `score` floats
- Sanity-check segment count vs. file duration. A 60-min ENT exam with normal turn-taking should yield dozens to hundreds of segments. If segment count is implausibly low, surface it.

If transcription fails (model download error, OOM, etc.), debug — do NOT commit until manual flow works.

If transcription works but produces obvious garbage (every segment is "Thanks for watching"), the anti-hallucination params may not be applied correctly — re-check `transcribe_audio_file`'s `WHISPER_DECODER_PARAMS`.

- [ ] **Step 3: Optionally tail engine stderr for warnings**

When the model first loads, faster-whisper / WhisperX will emit warnings about CTranslate2 / CUDA detection. CPU-only is expected; warnings about CUDA not being available are NOT errors — they're informational.

---

### Task 9: README — update with M5 status

**Files:**
- Modify: `README.md`

- [ ] **Step 1: Replace the M4 status line**

Find:

```
> **Status:** Milestone 4 of 8 complete — full pre-AI pipeline (Stages 1–4). After extracting audio (Stage 1) and normalizing it (Stage 2), the engine runs DeepFilterNet 3 speech enhancement (Stage 3) and Silero voice activity detection (Stage 4). VAD output is persisted as `speech-segments.json` per source. The UI status indicator cycles through `extracting…` → `normalizing…` → `enhancing…` → `detecting speech…` → `✓`.
```

Replace with:

```
> **Status:** Milestone 5 of 8 complete — six-stage transcription pipeline. After audio prep (Stages 1-4) the engine now runs faster-whisper large-v3 transcription (Stage 5) and WhisperX wav2vec2 word-level alignment (Stage 6). The canonical `transcript.json` artifact (per the brief's §4.8 schema) lands in the per-source cache, ready for the reviewer UI surfaces in M6. Status indicator cycles: `extracting…` → `normalizing…` → `enhancing…` → `detecting speech…` → `transcribing…` → `aligning words…` → `✓`.
```

- [ ] **Step 2: Commit**

```bash
git add README.md
git commit -m "docs: update status to M5 complete"
```

---

### Task 10: Push, merge to main, clean up

- [ ] **Step 1: Push the branch**

```bash
git push -u origin milestone-5-transcribe-align
```

- [ ] **Step 2: Switch to main and merge**

```bash
git checkout main
git merge --no-ff milestone-5-transcribe-align -m "$(cat <<'EOF'
Merge milestone 5: Stage 5 transcribe + Stage 6 align + transcript.json

Adds Stages 5 (faster-whisper large-v3 transcription) and 6 (WhisperX
wav2vec2 word-level forced alignment) of the transcription pipeline.
New runtime deps: faster-whisper, whisperx (transitively pulls
ctranslate2, transformers, friends). Continuing the M4 torchaudio<2.6
pin from deepfilternet compatibility.

engine/pipeline/transcribe.py reads enhanced/track0.wav (track 0 only
for V1; multi-track waits for wearer-detect in M7+) and runs
faster-whisper with brief §4.5 anti-hallucination decoder params.
Outputs an intermediate transcribe-raw.json with WhisperX-compatible
segment dicts. Per-source context.json (names + locations) is
optionally consumed as the initial_prompt to improve proper-noun
recall.

engine/pipeline/align.py reads transcribe-raw.json + enhanced audio,
runs WhisperX align to add per-word {word, start, end, score} arrays,
and assembles the final transcript.json at the cache root with brief
§4.8 top-level schema. low_confidence per segment is derived from
the no_speech_prob / avg_logprob / compression_ratio thresholds.
speakers is empty in M5; M7 diarization populates it.

UI: STAGE_LABELS adds 'transcribing…' and 'aligning words…'. No
reviewer panels yet — the transcript panel + audio player +
click-to-seek surfaces are M6.

engine.version bumped to 2026.04.29b — transcript.json embeds it as
processing.pipeline_version.

Test coverage: 13 new pytest tests (6 transcribe, 7 align). 6 pre-existing
chained-pipeline tests updated to mock the new stages. 1 new six-stage
integration test. 2 new vitest tests for the new stage labels. Full
suite: 107 pytest + 33 vitest passing. Manual launch verified: real
faster-whisper + WhisperX run end-to-end on a real source, transcript.json
produced with valid schema.

Out of scope (deferred to M6): reviewer UI surfaces (transcript panel,
audio player, click-to-seek), context.json edit panel, multi-track
transcription, diarization (M7), wearer detection (M7).

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

- [ ] **Step 3: Push main and clean up**

```bash
git push origin main
git push origin --delete milestone-5-transcribe-align
git branch -d milestone-5-transcribe-align
```

- [ ] **Step 4: Verify final state**

```bash
git log --oneline --graph -10
```

---

## What this milestone leaves you with

- The full transcription pipeline from raw media to word-timestamped text — the foundation for every reviewer UI feature ahead.
- `transcript.json` at the source cache root with the brief §4.8 schema, ready to be consumed by the M6 transcript panel.
- The first cache file with semantic data (text, not just bytes / timestamps) — opens the door to search, summarization, and clip-from-text features in later milestones.
- The pattern of an intermediate cache file (transcribe-raw.json) that a downstream stage consumes — useful for any future stage that needs to checkpoint heavy ML output before further processing.

## Next milestone (preview, not part of this plan)

**Milestone 6: Reviewer UI surfaces — transcript panel + audio player + click-to-seek + context.json edit panel.** First user-visible reviewer experience. New engine endpoint to serve cached audio (so the renderer's `<audio>` tag can play `enhanced/track0.wav` from a localhost URL). Transcript panel renders from `transcript.json`, click any segment to seek the player. Speaker colors driven by `speakers` field (empty for now until M7). Context-names panel writes `context.json` and triggers re-transcription. Big milestone — first end-to-end reviewer experience.
