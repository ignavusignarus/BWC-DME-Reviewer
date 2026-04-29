# BWC Clipper — Milestone 4: Stage 3 Enhance + Stage 4 VAD + speech-segments.json — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add Stages 3 and 4 of the transcription pipeline — speech enhancement (DeepFilterNet 3) and voice activity detection (Silero VAD) — and produce the `speech-segments.json` artifact that the collapsed-silence timeline (M5+) will read from. After this milestone, the four-stage pipeline runs end-to-end on a source: extract → normalize → enhance → VAD, with each stage's output cached and live status reported in the UI.

**Architecture:** Two new stage modules `engine/pipeline/enhance.py` and `engine/pipeline/vad.py`, each following the M2/M3 stage protocol exactly. Heavy ML model loading is wrapped in module-level cached singletons (`_get_df_model`, `_get_silero_model`) so each model loads once per engine process, not once per source. Each model is invoked through a small helper function (`enhance_audio_file`, `vad_audio_file`) that the tests mock at the boundary — no model inference runs during tests. The runner gains two more entries in `_PIPELINE_STAGES`; M3's chaining infrastructure handles the rest. The UI's `STAGE_LABELS` dict gains two entries (`enhance` → "enhancing…", `vad` → "detecting speech…").

**Tech Stack:** New runtime dependencies — `deepfilternet>=0.5` (pulls torch, torchaudio transitively, ~250 MB total install), `silero-vad>=5.0` (~5 MB), `soundfile>=0.12` (numpy-based WAV I/O, ~10 MB). Production code uses CPU torch by default; GPU acceleration is a manual reinstall step documented in the README, not part of this milestone's code.

**Scope of this milestone:**
- Add `deepfilternet`, `silero-vad`, `soundfile` to `pyproject.toml` `dependencies` (becoming the engine's first real runtime deps).
- New `engine/pipeline/enhance.py` — Stage 3 reads `normalized/track{N}.wav`, writes `enhanced/track{N}.wav` per brief §4.3.
- New `engine/pipeline/vad.py` — Stage 4 reads `enhanced/track{N}.wav`, writes `speech-segments.json` at the source cache root with shape `{"tracks": [[{start, end}, ...], ...]}` per brief §4.4 (threshold=0.5, min_speech_duration_ms=250, min_silence_duration_ms=300, speech_pad_ms=200).
- Append `enhance` and `vad` to the runner's `_PIPELINE_STAGES`.
- UI `STAGE_LABELS` adds the two new entries.

**Out of scope for this milestone:**
- Stages 5–8 (transcribe, align, diarize, wearer-detect, output assembly). Those are M5+.
- The reviewer UI surfaces (transcript panel, timeline visualization, video pane). M5+.
- GPU/CUDA configuration. CPU-only is shipped; CUDA is a manual `pip install --index-url` upgrade documented in README.
- Multi-track speaker-aware VAD. We run VAD per track and write per-track segments lists; cross-track union is M6+.
- `speech-segments.json` schema versioning. We're at v1; if it grows we add a `schema_version` field later.
- The full dependency gate (M7).

---

## File Structure

```
bwc-clipper/
├── pyproject.toml                            MODIFY — add 3 runtime deps
├── README.md                                 MODIFY — document GPU acceleration upgrade path,
│                                              update status to M4
├── engine/
│   ├── pipeline/
│   │   ├── enhance.py                        NEW — Stage 3, DeepFilterNet 3
│   │   ├── vad.py                            NEW — Stage 4, Silero VAD
│   │   └── runner.py                         MODIFY — append enhance + vad to _PIPELINE_STAGES
├── editor/
│   └── components/
│       ├── FileListItem.jsx                  MODIFY — add STAGE_LABELS for enhance + vad
│       └── FileListItem.test.jsx             MODIFY — add 2 stage-label tests
└── tests/
    ├── test_pipeline_enhance.py              NEW
    ├── test_pipeline_vad.py                  NEW
    └── test_pipeline_runner.py               MODIFY — extend chained-runner tests for 4 stages
```

**Why two separate stage files (enhance.py, vad.py) instead of one:** They are different responsibilities — different models, different inputs, different output formats. Enhance writes a WAV per track; VAD writes a single JSON file across tracks. Splitting matches the existing `extract.py` / `normalize.py` decomposition and keeps each file ~80 lines.

**Why a new `tests/test_pipeline_enhance.py` and `tests/test_pipeline_vad.py`:** Same rationale — separate test files for separate stages, mirroring the existing `test_pipeline_extract.py` and `test_pipeline_normalize.py`.

---

## Reference patterns

| New code in M4 | Reference (read for pattern) |
|---|---|
| `engine/pipeline/enhance.py` | `engine/pipeline/normalize.py` — same shape, different work block |
| `engine/pipeline/vad.py` | `engine/pipeline/extract.py` for the orchestration; the work writes JSON instead of WAVs |
| Module-level model cache (`_get_df_model`, `_get_silero_model`) | `engine/server.py`'s `_RUNNER` singleton + `get_pipeline_runner()` accessor |
| Tests mock at the helper boundary | `tests/test_pipeline_normalize.py` mocks `engine.pipeline.normalize.run_loudnorm_measure` and `run_ffmpeg` — same approach |
| `pyproject.toml` runtime deps | `Depo-Clipper/pyproject.toml` for the relative shape of a Python project with ML deps |

**Brief reference:**
- §4.3 (Speech Enhancement): DeepFilterNet 3 chosen over alternatives (faster than Resemble Enhance, less artifacting than VoiceFixer, Apache 2.0 license). Run on the **normalized** audio (not original).
- §4.4 (VAD): Silero VAD chosen as the lightweight default. Parameters: threshold=0.5, min_speech_duration_ms=250, min_silence_duration_ms=300, speech_pad_ms=200. Output is `(start_seconds, end_seconds)` tuples.
- The brief calls VAD's input "input WAV" without specifying — pipeline diagram §3 places it after enhancement, so VAD reads `enhanced/track{N}.wav`.

---

## Testing strategy

- **No real model inference in tests.** Both stages have a small helper function (`enhance_audio_file(in_path, out_path)` in enhance.py and `vad_audio_file(in_path)` in vad.py) that wraps the heavy ML call. Tests mock these helpers and verify the orchestration logic — file paths, state transitions, output schema. Real model loading is verified at the manual launch step.
- **Imports are top-level**, not lazy. The engine refuses to start if deps are missing — that's the dependency gate's job in M7, but we get a free crude version of it now via Python's import machinery. Acceptable for V1.
- **No new pytest deps.** `unittest.mock.patch` already in stdlib.

---

## Pip install caveats (read before starting Task 2)

Adding `deepfilternet` will pull `torch` and `torchaudio` transitively. Total install size for the Windows CPU wheel:

- `torch` CPU: ~190 MB
- `torchaudio` CPU: ~5 MB (wheel) plus ~50 MB DLLs
- `deepfilternet`: ~10 MB package + ~50 MB ONNX models bundled
- `silero-vad`: ~3 MB + ~2 MB ONNX bundled
- `soundfile`: ~10 MB

**Expected install time:** 2–6 minutes on a typical Windows machine, dominated by the torch download.

**If torch install fails:** the most common cause is a Python version mismatch. Confirm `.venv/Scripts/python.exe --version` reports `Python 3.11.x` — the venv must be 3.11, not 3.14 (the system default on this machine). If the venv is wrong, recreate it: `py -3.11 -m venv .venv` (use the Windows `py` launcher, not bare `python`). See `MEMORY.md` reference `Windows Python toolchain` for context.

**No manual GPU configuration in this milestone.** CPU torch is what we ship. If the user later wants CUDA, they reinstall with `pip install --index-url https://download.pytorch.org/whl/cu121 torch torchaudio` — this is documented in the README in Task 8 but no code paths require it.

---

## Tasks

### Task 1: Create milestone-4 branch

- [ ] **Step 1: Verify clean working tree on main, last commit is M3 merge**

```bash
cd "C:/Claude Code Projects/BWC Reviewer"
git status
git rev-parse --abbrev-ref HEAD
git log -1 --oneline
```

Expected: clean, on `main`, last commit `4a298ca` (M3 merge).

- [ ] **Step 2: Branch**

```bash
git checkout -b milestone-4-enhance-vad
```

---

### Task 2: Add runtime deps to `pyproject.toml`; install

**Files:**
- Modify: `pyproject.toml`

- [ ] **Step 1: Edit `pyproject.toml`**

Find:

```toml
# Milestone 0 has zero runtime deps — pipeline deps land in later milestones.
dependencies = []
```

Replace with:

```toml
# Stage 3 (DeepFilterNet) and Stage 4 (Silero VAD) bring the engine's first
# real runtime deps. torch is a transitive of deepfilternet (CPU wheel by
# default; GPU acceleration is a manual reinstall — see README).
dependencies = [
    "deepfilternet>=0.5",
    "silero-vad>=5.0",
    "soundfile>=0.12",
]
```

- [ ] **Step 2: Reinstall the project to pull new deps**

```bash
.venv/Scripts/python.exe -m pip install -e ".[dev]"
```

Expected: pip resolves and downloads `torch`, `torchaudio`, `deepfilternet`, `silero-vad`, `soundfile`, plus their transitives. **2–6 minute wait.** If it fails with a "no matching distribution" error, re-check `.venv/Scripts/python.exe --version` is 3.11.x (per the install caveats section above).

- [ ] **Step 3: Verify the deps import cleanly**

```bash
.venv/Scripts/python.exe -c "import torch; import df.enhance; import silero_vad; import soundfile; print('OK')"
```

Expected: prints `OK`. If any import fails, stop and surface the error — Task 3 cannot proceed without these deps.

- [ ] **Step 4: Run the existing test suite to confirm zero regressions**

```bash
.venv/Scripts/python.exe -m pytest -v
```

Expected: 81 tests pass (same as M3 final).

- [ ] **Step 5: Commit**

```bash
git add pyproject.toml
git commit -m "engine: add deepfilternet, silero-vad, soundfile as runtime deps"
```

---

### Task 3: `engine/pipeline/enhance.py` — Stage 3 (TDD)

**Files:**
- Create: `tests/test_pipeline_enhance.py`
- Create: `engine/pipeline/enhance.py`

The Enhance stage reads each `normalized/track{N}.wav` and runs DeepFilterNet 3 over it, writing `enhanced/track{N}.wav` at the same sample rate / channel layout. Updates `pipeline-state.json` with running/completed/failed.

The orchestration is small. The heavy lifting (loading the model, running inference) is in a helper function `enhance_audio_file(in_path, out_path)` that tests mock at that boundary.

- [ ] **Step 1: Create `tests/test_pipeline_enhance.py`**

```python
"""Tests for engine.pipeline.enhance — Stage 3 (DeepFilterNet 3 enhancement)."""
import json
from pathlib import Path
from unittest.mock import patch

import pytest

from engine.pipeline.enhance import run_enhance_stage
from engine.pipeline.state import load_state


def _touch(p: Path, content: bytes = b""):
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_bytes(content)


def _write_source_metadata_with_normalized(cache_dir: Path, n_tracks: int):
    """Set up the cache as if Stages 1 + 2 have completed."""
    cache_dir.mkdir(parents=True, exist_ok=True)
    tracks = [
        {"index": i + 1, "codec_name": "aac", "sample_rate": 48000, "channels": 1, "duration_seconds": 12.0}
        for i in range(n_tracks)
    ]
    (cache_dir / "source.json").write_text(json.dumps({"audio_tracks": tracks}))
    normalized = cache_dir / "normalized"
    normalized.mkdir(exist_ok=True)
    for i in range(n_tracks):
        _touch(normalized / f"track{i}.wav", b"fake-normalized-wav")


def test_run_enhance_stage_creates_enhanced_wavs(tmp_path: Path):
    cache_dir = tmp_path / ".bwcclipper" / "officer"
    _write_source_metadata_with_normalized(cache_dir, n_tracks=2)

    def _writes_output(in_path, out_path):
        Path(out_path).parent.mkdir(parents=True, exist_ok=True)
        Path(out_path).touch()

    with patch("engine.pipeline.enhance.enhance_audio_file", side_effect=_writes_output) as mock:
        outputs = run_enhance_stage(cache_dir)

    assert len(outputs) == 2
    assert outputs[0] == cache_dir / "enhanced" / "track0.wav"
    assert outputs[1] == cache_dir / "enhanced" / "track1.wav"
    assert (cache_dir / "enhanced").is_dir()

    # Enhance helper was called once per track with the right paths
    assert mock.call_count == 2
    args0, _ = mock.call_args_list[0]
    assert args0[0] == cache_dir / "normalized" / "track0.wav"
    assert args0[1] == cache_dir / "enhanced" / "track0.wav"


def test_run_enhance_stage_writes_pipeline_state(tmp_path: Path):
    cache_dir = tmp_path / ".bwcclipper" / "officer"
    _write_source_metadata_with_normalized(cache_dir, n_tracks=1)

    def _writes_output(in_path, out_path):
        Path(out_path).parent.mkdir(parents=True, exist_ok=True)
        Path(out_path).touch()

    with patch("engine.pipeline.enhance.enhance_audio_file", side_effect=_writes_output):
        run_enhance_stage(cache_dir)

    state = load_state(cache_dir)
    enhance = state.stages["enhance"]
    assert enhance["status"] == "completed"
    assert "started_at" in enhance and "completed_at" in enhance
    assert len(enhance["outputs"]) == 1


def test_run_enhance_stage_marks_failed_on_helper_error(tmp_path: Path):
    cache_dir = tmp_path / ".bwcclipper" / "officer"
    _write_source_metadata_with_normalized(cache_dir, n_tracks=1)

    with patch("engine.pipeline.enhance.enhance_audio_file", side_effect=RuntimeError("boom")):
        with pytest.raises(RuntimeError, match="boom"):
            run_enhance_stage(cache_dir)

    state = load_state(cache_dir)
    enhance = state.stages["enhance"]
    assert enhance["status"] == "failed"
    assert "boom" in enhance.get("error", "")


def test_run_enhance_stage_raises_if_source_metadata_missing(tmp_path: Path):
    cache_dir = tmp_path / ".bwcclipper" / "officer"
    cache_dir.mkdir(parents=True)

    with pytest.raises(FileNotFoundError):
        run_enhance_stage(cache_dir)


def test_run_enhance_stage_raises_if_normalized_track_missing(tmp_path: Path):
    cache_dir = tmp_path / ".bwcclipper" / "officer"
    _write_source_metadata_with_normalized(cache_dir, n_tracks=2)
    (cache_dir / "normalized" / "track1.wav").unlink()

    with pytest.raises(FileNotFoundError):
        run_enhance_stage(cache_dir)
```

- [ ] **Step 2: Run, confirm FAIL**

```bash
.venv/Scripts/python.exe -m pytest tests/test_pipeline_enhance.py -v
```

- [ ] **Step 3: Create `engine/pipeline/enhance.py`**

```python
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
        _df_init = init_df()
    return _df_init


def enhance_audio_file(in_path: Path, out_path: Path) -> None:
    """Read a WAV, run DeepFilterNet 3 over it, write the enhanced WAV.

    DF3 operates internally at 48 kHz; we use df.enhance.load_audio + save_audio
    which handle resampling so input/output stay at the source's native rate
    (16 kHz from Stage 2). Tests mock this function — the underlying df calls
    are not exercised in unit tests.
    """
    from df.enhance import enhance, load_audio, save_audio

    model, df_state, *_ = _get_df_model()
    # Resample input to the model's native rate (48 kHz for DF3).
    audio, _in_sr = load_audio(str(in_path), sr=df_state.sr())
    enhanced = enhance(model, df_state, audio)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    # Save at 16 kHz to keep cache layout consistent for Stage 4 (Silero VAD,
    # which expects 16 kHz). save_audio resamples internally.
    save_audio(str(out_path), enhanced, 16000)


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

        out_dir = cache_dir / "enhanced"
        out_dir.mkdir(parents=True, exist_ok=True)
        outputs: list[Path] = []

        for n in range(len(tracks)):
            in_path = cache_dir / "normalized" / f"track{n}.wav"
            if not in_path.is_file():
                raise FileNotFoundError(f"expected normalized track missing: {in_path}")
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
```

- [ ] **Step 4: Run, confirm 5 passed**

```bash
.venv/Scripts/python.exe -m pytest tests/test_pipeline_enhance.py -v
```

- [ ] **Step 5: Commit**

```bash
git add engine/pipeline/enhance.py tests/test_pipeline_enhance.py
git commit -m "engine: add Stage 3 enhance — DeepFilterNet 3 speech enhancement"
```

---

### Task 4: `engine/pipeline/vad.py` — Stage 4 (TDD)

**Files:**
- Create: `tests/test_pipeline_vad.py`
- Create: `engine/pipeline/vad.py`

The VAD stage reads each `enhanced/track{N}.wav` and runs Silero VAD with the brief's parameters. Outputs `speech-segments.json` at the cache root with shape:

```json
{
    "tracks": [
        [{"start": 1.5, "end": 4.2}, {"start": 6.0, "end": 9.5}, ...],
        [{"start": 0.8, "end": 3.1}, ...]
    ]
}
```

One inner array per audio track. Each segment is `{start, end}` in seconds (floats).

- [ ] **Step 1: Create `tests/test_pipeline_vad.py`**

```python
"""Tests for engine.pipeline.vad — Stage 4 (Silero VAD)."""
import json
from pathlib import Path
from unittest.mock import patch

import pytest

from engine.pipeline.vad import run_vad_stage
from engine.pipeline.state import load_state


def _touch(p: Path, content: bytes = b""):
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_bytes(content)


def _write_source_metadata_with_enhanced(cache_dir: Path, n_tracks: int):
    """Set up the cache as if Stages 1 + 2 + 3 have completed."""
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


def test_run_vad_stage_writes_speech_segments_json(tmp_path: Path):
    cache_dir = tmp_path / ".bwcclipper" / "officer"
    _write_source_metadata_with_enhanced(cache_dir, n_tracks=2)

    def _per_track_segments(in_path: Path) -> list[dict]:
        # Distinct fake segments per track to confirm ordering
        if "track0" in str(in_path):
            return [{"start": 0.5, "end": 2.0}, {"start": 3.5, "end": 6.0}]
        return [{"start": 1.0, "end": 4.0}]

    with patch("engine.pipeline.vad.vad_audio_file", side_effect=_per_track_segments) as mock:
        result = run_vad_stage(cache_dir)

    out_path = cache_dir / "speech-segments.json"
    assert out_path.is_file()
    data = json.loads(out_path.read_text(encoding="utf-8"))
    assert "tracks" in data
    assert len(data["tracks"]) == 2
    assert data["tracks"][0] == [{"start": 0.5, "end": 2.0}, {"start": 3.5, "end": 6.0}]
    assert data["tracks"][1] == [{"start": 1.0, "end": 4.0}]

    # Returned path is the JSON file path
    assert result == out_path

    # vad_audio_file was called once per track
    assert mock.call_count == 2


def test_run_vad_stage_writes_pipeline_state(tmp_path: Path):
    cache_dir = tmp_path / ".bwcclipper" / "officer"
    _write_source_metadata_with_enhanced(cache_dir, n_tracks=1)

    with patch("engine.pipeline.vad.vad_audio_file", return_value=[]):
        run_vad_stage(cache_dir)

    state = load_state(cache_dir)
    vad = state.stages["vad"]
    assert vad["status"] == "completed"
    assert "started_at" in vad and "completed_at" in vad
    assert vad["outputs"] == [str(cache_dir / "speech-segments.json")]


def test_run_vad_stage_marks_failed_on_helper_error(tmp_path: Path):
    cache_dir = tmp_path / ".bwcclipper" / "officer"
    _write_source_metadata_with_enhanced(cache_dir, n_tracks=1)

    with patch("engine.pipeline.vad.vad_audio_file", side_effect=RuntimeError("boom")):
        with pytest.raises(RuntimeError, match="boom"):
            run_vad_stage(cache_dir)

    state = load_state(cache_dir)
    vad = state.stages["vad"]
    assert vad["status"] == "failed"
    assert "boom" in vad.get("error", "")


def test_run_vad_stage_raises_if_source_metadata_missing(tmp_path: Path):
    cache_dir = tmp_path / ".bwcclipper" / "officer"
    cache_dir.mkdir(parents=True)

    with pytest.raises(FileNotFoundError):
        run_vad_stage(cache_dir)


def test_run_vad_stage_raises_if_enhanced_track_missing(tmp_path: Path):
    cache_dir = tmp_path / ".bwcclipper" / "officer"
    _write_source_metadata_with_enhanced(cache_dir, n_tracks=2)
    (cache_dir / "enhanced" / "track1.wav").unlink()

    with pytest.raises(FileNotFoundError):
        run_vad_stage(cache_dir)


def test_run_vad_stage_handles_empty_speech(tmp_path: Path):
    """A silent track → empty segments list, but VAD still runs and writes JSON."""
    cache_dir = tmp_path / ".bwcclipper" / "officer"
    _write_source_metadata_with_enhanced(cache_dir, n_tracks=1)

    with patch("engine.pipeline.vad.vad_audio_file", return_value=[]):
        run_vad_stage(cache_dir)

    out_path = cache_dir / "speech-segments.json"
    data = json.loads(out_path.read_text(encoding="utf-8"))
    assert data == {"tracks": [[]]}
```

- [ ] **Step 2: Run, confirm FAIL**

```bash
.venv/Scripts/python.exe -m pytest tests/test_pipeline_vad.py -v
```

- [ ] **Step 3: Create `engine/pipeline/vad.py`**

```python
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
    # Silero returns dicts with 'start' / 'end' keys (in seconds when return_seconds=True).
    # Strip any extra keys for a clean schema.
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

        per_track_segments: list[list[dict]] = []
        for n in range(len(tracks)):
            in_path = cache_dir / "enhanced" / f"track{n}.wav"
            if not in_path.is_file():
                raise FileNotFoundError(f"expected enhanced track missing: {in_path}")
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
```

- [ ] **Step 4: Run, confirm 6 passed**

```bash
.venv/Scripts/python.exe -m pytest tests/test_pipeline_vad.py -v
```

- [ ] **Step 5: Commit**

```bash
git add engine/pipeline/vad.py tests/test_pipeline_vad.py
git commit -m "engine: add Stage 4 vad — Silero VAD producing speech-segments.json"
```

---

### Task 5: Append enhance + vad to `_PIPELINE_STAGES`; extend chained-runner tests (TDD)

**Files:**
- Modify: `engine/pipeline/runner.py`
- Modify: `tests/test_pipeline_runner.py`

The runner already chains stages serially and reports stage-aware status (M3). M4 just adds two more entries to `_PIPELINE_STAGES` plus tests confirming the four-stage chain works end-to-end.

- [ ] **Step 1: Append a new test to `tests/test_pipeline_runner.py`**

Append at the end (don't modify existing tests):

```python
def test_runner_runs_all_four_stages_in_order(tmp_path: Path):
    """Full pipeline: extract → normalize → enhance → vad → completed."""
    from engine.pipeline.runner import PipelineRunner

    source = tmp_path / "x.mp4"
    _touch(source, b"x")

    def _writes_output(args, **kwargs):
        Path(args[-1]).touch()
        return ""

    def _enhance_writes(in_path, out_path):
        Path(out_path).parent.mkdir(parents=True, exist_ok=True)
        Path(out_path).touch()

    runner = PipelineRunner()
    try:
        with patch("engine.pipeline.extract.probe_audio_tracks") as probe_mock, \
             patch("engine.pipeline.extract.run_ffmpeg", side_effect=_writes_output), \
             patch("engine.pipeline.normalize.run_loudnorm_measure",
                   return_value={"input_i": "-12", "input_tp": "-1", "input_lra": "5",
                                 "input_thresh": "-20", "target_offset": "0"}), \
             patch("engine.pipeline.normalize.run_ffmpeg", side_effect=_writes_output), \
             patch("engine.pipeline.enhance.enhance_audio_file", side_effect=_enhance_writes), \
             patch("engine.pipeline.vad.vad_audio_file", return_value=[{"start": 0.0, "end": 1.0}]):
            probe_mock.return_value = [
                {"index": 0, "codec_name": "aac", "sample_rate": 48000, "channels": 1, "duration_seconds": 1.0},
            ]
            future = runner.submit_pipeline(tmp_path, source)
            future.result(timeout=10)
        assert runner.get_status(tmp_path, source) == "completed"

        # Verify all four stages are completed in pipeline-state.json
        from engine.pipeline.state import load_state
        from engine.source import source_cache_dir
        cache_dir = source_cache_dir(tmp_path, source)
        state = load_state(cache_dir)
        for stage_name in ("extract", "normalize", "enhance", "vad"):
            assert state.stages.get(stage_name, {}).get("status") == "completed", \
                f"stage {stage_name} not completed"

        # speech-segments.json was written
        assert (cache_dir / "speech-segments.json").is_file()
    finally:
        runner.shutdown()
```

- [ ] **Step 2: Run the new test — it will FAIL because enhance and vad aren't yet in `_PIPELINE_STAGES`**

```bash
.venv/Scripts/python.exe -m pytest tests/test_pipeline_runner.py::test_runner_runs_all_four_stages_in_order -v
```

Expected fail mode: the assertion on `enhance` stage status fails because the stage was never run. Or `speech-segments.json` is not present.

- [ ] **Step 3: Modify `engine/pipeline/runner.py` to append the two new stages**

Find:

```python
from engine.pipeline.extract import run_extract_stage
from engine.pipeline.normalize import run_normalize_stage
from engine.pipeline.state import StageStatus, load_state
from engine.source import source_cache_dir

# Each stage is (name, runner_callable). The runner_callable signature is
# ``fn(source_path, cache_dir) -> Any`` for extract; later stages take only
# ``cache_dir`` once the audio's been extracted. We adapt with a lambda.
_PIPELINE_STAGES: list[tuple[str, Callable]] = [
    ("extract", lambda source, cache: run_extract_stage(source, cache)),
    ("normalize", lambda _source, cache: run_normalize_stage(cache)),
]
```

Replace with:

```python
from engine.pipeline.enhance import run_enhance_stage
from engine.pipeline.extract import run_extract_stage
from engine.pipeline.normalize import run_normalize_stage
from engine.pipeline.state import StageStatus, load_state
from engine.pipeline.vad import run_vad_stage
from engine.source import source_cache_dir

# Each stage is (name, runner_callable). The runner_callable signature is
# ``fn(source_path, cache_dir) -> Any`` — extract is the only stage that
# reads the source media directly; later stages all read the per-source
# cache from earlier stages.
_PIPELINE_STAGES: list[tuple[str, Callable]] = [
    ("extract", lambda source, cache: run_extract_stage(source, cache)),
    ("normalize", lambda _source, cache: run_normalize_stage(cache)),
    ("enhance", lambda _source, cache: run_enhance_stage(cache)),
    ("vad", lambda _source, cache: run_vad_stage(cache)),
]
```

- [ ] **Step 4: Run the new test — confirm pass**

```bash
.venv/Scripts/python.exe -m pytest tests/test_pipeline_runner.py::test_runner_runs_all_four_stages_in_order -v
```

- [ ] **Step 5: Run the FULL pytest suite to confirm zero regressions**

```bash
.venv/Scripts/python.exe -m pytest -v
```

Expected: 81 (existing) + 5 enhance + 6 vad + 1 chained = 93 tests. All pass.

- [ ] **Step 6: Commit**

```bash
git add engine/pipeline/runner.py tests/test_pipeline_runner.py
git commit -m "engine: append enhance + vad to pipeline; chained-runner test"
```

---

### Task 6: UI — `STAGE_LABELS` for enhance + vad (TDD)

**Files:**
- Modify: `editor/components/FileListItem.test.jsx`
- Modify: `editor/components/FileListItem.jsx`

- [ ] **Step 1: Append two tests to the existing `'FileListItem stage-aware status'` describe block in `editor/components/FileListItem.test.jsx`**

```jsx
    it('renders "enhancing…" for running:enhance', () => {
        render(
            <FileListItem
                file={sampleFile}
                selected={false}
                onSelect={() => {}}
                status="running:enhance"
            />,
        );
        expect(screen.getByText(/enhancing/i)).toBeDefined();
    });

    it('renders "detecting speech…" for running:vad', () => {
        render(
            <FileListItem
                file={sampleFile}
                selected={false}
                onSelect={() => {}}
                status="running:vad"
            />,
        );
        expect(screen.getByText(/detecting speech/i)).toBeDefined();
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
    // Future stages (M4+): enhance, vad, transcribe, etc.
};
```

Replace with:

```jsx
const STAGE_LABELS = {
    extract: 'extracting…',
    normalize: 'normalizing…',
    enhance: 'enhancing…',
    vad: 'detecting speech…',
    // Future stages (M5+): transcribe, align, diarize, etc.
};
```

- [ ] **Step 4: Run, confirm 16 FileListItem tests pass (14 + 2 new)**

```bash
npx vitest run editor/components/FileListItem.test.jsx
```

- [ ] **Step 5: Run the full vitest suite**

```bash
npm test
```

Expected: 31 tests pass (29 + 2 new).

- [ ] **Step 6: Build production bundle (sanity check)**

```bash
NODE_ENV=production npm run build:editor
```

- [ ] **Step 7: Commit**

```bash
git add editor/components/FileListItem.jsx editor/components/FileListItem.test.jsx
git commit -m "editor: add stage labels for enhance and vad"
```

---

### Task 7: Manual launch verification

**Files:** none (verification, no commit)

This task verifies the full four-stage pipeline runs end-to-end on real audio with real models. **Expect the full pipeline to take several minutes the first time** — DeepFilterNet and Silero models download/load on first invocation, and DF3 inference on a long file is roughly 0.5x real-time on CPU.

- [ ] **Step 1: Build editor + run the test suites once more**

```bash
npm run build:editor
.venv/Scripts/python.exe -m pytest -v
npm test
```

- [ ] **Step 2: (Optional) Clear the cache for a fresh run**

```bash
# Optional — only if you want to re-exercise stages 1+2 from scratch:
# rm -rf "Samples/.bwcclipper" "Samples/BWC/.bwcclipper"
```

If you skip this, M3's already-completed extract+normalize for the previously-tested DME source will be reused, and only enhance + VAD will run on it. That's a cleaner test of stage-skip-when-completed and is faster overall.

- [ ] **Step 3: Launch the app**

```bash
npm start
```

Expected manual verification:
- Splash → main window opens (ffmpeg already cached).
- Open the folder containing the previously-processed DME source (`Samples/`).
- Click the previously-completed source. Status indicator should:
  1. Briefly pass through `● enhancing…` (yellow). DF3 takes 0.5x real-time on CPU, so a 60-min source ≈ 30 min CPU time. Patience is required.
  2. Then `● detecting speech…` (yellow) — Silero is much faster, ~real-time-or-better.
  3. Finally `✓` (green).
- Inspect `Samples/.bwcclipper/<source-stem>/`:
  - `enhanced/track0.wav` — **new in M4**
  - `speech-segments.json` — **new in M4**, valid JSON with shape `{tracks: [[{start, end}, ...]]}`
  - `pipeline-state.json` — all four stages now show `completed` with timestamps
- Pretty-print `speech-segments.json` and skim the segments. Should be plausible: a typical 60-min ENT exam has dozens to hundreds of speech segments.

If DF3 enhancement takes implausibly long (>2x real-time), or VAD finds zero segments on audio you know contains speech, that's a real problem — surface it before merging.

- [ ] **Step 4: If anything fails, debug — do NOT commit until manual flow works**

---

### Task 8: README — update with M4 status + GPU acceleration note

**Files:**
- Modify: `README.md`

- [ ] **Step 1: Replace the M3 status line**

Find:

```
> **Status:** Milestone 3 of 8 complete — Stage 2 normalize + pipeline chaining. After extracting audio (Stage 1), the engine now runs two-pass loudness normalization plus dynamic-range compression and bandpass filtering (per the brief's §4.2 ffmpeg chain). The UI status indicator reflects the active stage — `extracting…` → `normalizing…` → `✓`.
```

Replace with:

```
> **Status:** Milestone 4 of 8 complete — full pre-AI pipeline (Stages 1–4). After extracting audio (Stage 1) and normalizing it (Stage 2), the engine now runs DeepFilterNet 3 speech enhancement (Stage 3) and Silero voice activity detection (Stage 4). VAD output is persisted as `speech-segments.json` per source. The UI status indicator cycles through `extracting…` → `normalizing…` → `enhancing…` → `detecting speech…` → `✓`.
```

- [ ] **Step 2: Add a new "GPU acceleration (optional)" section to the Development section**

Find the existing block (in the Development section):

```bash
# Python engine
python -m venv .venv
.venv/Scripts/python.exe -m pip install --upgrade pip      # Windows
# .venv/bin/python -m pip install --upgrade pip            # macOS/Linux
.venv/Scripts/python.exe -m pip install -e ".[dev]"
```

Append immediately after that code fence:

```markdown

#### GPU acceleration (optional)

The default install pulls the CPU build of PyTorch. DeepFilterNet 3 enhancement
and (in later milestones) Whisper transcription run several times faster on
NVIDIA GPUs. To upgrade an existing venv to CUDA-enabled torch:

\`\`\`bash
.venv/Scripts/python.exe -m pip install --index-url https://download.pytorch.org/whl/cu121 --upgrade torch torchaudio
\`\`\`

Verify CUDA is detected:

\`\`\`bash
.venv/Scripts/python.exe -c "import torch; print('CUDA available:', torch.cuda.is_available())"
\`\`\`

Auto-detection of CUDA at runtime is handled by torch / DeepFilterNet directly
once the CUDA wheels are installed; no engine code changes are required.
```

(In the actual README, the inner triple backticks should be real triple backticks, not the escaped `\`\`\`` shown above.)

- [ ] **Step 3: Commit**

```bash
git add README.md
git commit -m "docs: update status to M4 complete; document GPU acceleration upgrade"
```

---

### Task 9: Push, merge to main, clean up

- [ ] **Step 1: Push the branch**

```bash
git push -u origin milestone-4-enhance-vad
```

- [ ] **Step 2: Switch to main and merge**

```bash
git checkout main
git merge --no-ff milestone-4-enhance-vad -m "$(cat <<'EOF'
Merge milestone 4: Stage 3 enhance + Stage 4 VAD + speech-segments.json

Adds Stages 3 (DeepFilterNet 3 speech enhancement) and 4 (Silero VAD)
of the transcription pipeline. New runtime deps: deepfilternet,
silero-vad, soundfile (torch comes transitively via deepfilternet).
New engine/pipeline/enhance.py reads normalized/track{N}.wav and
writes enhanced/track{N}.wav via DF3. New engine/pipeline/vad.py
reads enhanced/track{N}.wav and writes speech-segments.json at the
source cache root, schema {tracks: [[{start, end}, ...]]} with
times in seconds. Brief §4.4 VAD parameters applied verbatim.
Both stages plug into _PIPELINE_STAGES; M3's chaining infrastructure
needed no changes. UI: STAGE_LABELS adds 'enhancing…' and
'detecting speech…'.

CPU-only by default; GPU acceleration via manual reinstall with
CUDA wheels documented in README.

Test coverage: 12 new pytest tests (5 enhance, 6 vad, 1 four-stage
chained-runner integration); 2 new vitest tests on FileListItem
labels. Manual launch verified end-to-end on a real DME source —
all four stages completed, speech-segments.json contains plausible
segment count.

Out of scope (deferred to M5): transcription (Whisper), word
alignment (wav2vec2), diarization (pyannote), wearer detection,
output assembly. The reviewer UI surfaces (transcript panel,
collapsed-silence timeline, video pane) start landing in M5.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

- [ ] **Step 3: Push main and clean up**

```bash
git push origin main
git push origin --delete milestone-4-enhance-vad
git branch -d milestone-4-enhance-vad
```

- [ ] **Step 4: Verify final state**

```bash
git log --oneline --graph -10
```

---

## What this milestone leaves you with

- The full pre-AI pipeline running end-to-end on real audio: extract → normalize → enhance → VAD.
- The first artifact (`speech-segments.json`) that downstream UI features will read from. The collapsed-silence timeline in M5+ literally renders this file.
- The first runtime ML model dependencies cleanly installed and used. Subsequent milestones (M5 transcribe, M6 diarize) extend this pattern.
- The dependency-gate problem is now real: the engine refuses to start if torch / DF / Silero are missing. M7 turns this implicit gate into an explicit splash-screen check.

## Next milestone (preview, not part of this plan)

**Milestone 5: Stage 5 transcribe (faster-whisper / WhisperX) + Stage 6 align (wav2vec2) + transcript.json.** New deps: `faster-whisper`, `whisperx`. Two more stages plug into `_PIPELINE_STAGES`. The first user-visible reviewer UI surfaces — the **transcript panel** showing the raw transcribed text with timestamps, click-to-seek into the cached enhanced audio. Stage 6's word-level alignment is what makes click-to-seek usable. Big milestone — likely to be larger than M4.
