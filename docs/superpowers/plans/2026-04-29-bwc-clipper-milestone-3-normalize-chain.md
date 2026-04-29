# BWC Clipper — Milestone 3: Stage 2 Normalize + Pipeline Chaining + Per-Stage UI — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add Stage 2 of the transcription pipeline (loudness normalization + dynamic-range compression + band-limit per brief §4.2) and the scaffolding to chain stages serially. After this milestone, selecting a source in the UI extracts its audio (Stage 1, M2) and then normalizes it (Stage 2, M3) in a single chained pipeline run, with the file's status indicator showing which stage is active.

**Architecture:** New `engine/pipeline/normalize.py` mirrors the shape of `engine/pipeline/extract.py` — same Stage protocol (load state → mark running → do work → mark completed → save state). Two-pass loudnorm: a measurement pass parses the JSON the loudnorm filter prints to stderr, then a single second-pass invocation chains `loudnorm` (with measured values) → `acompressor` → `highpass`/`lowpass` and writes the normalized WAV. The pipeline runner gains a `submit_pipeline` method that chains stages serially in a single worker job; per-stage idempotency checks let already-completed stages be skipped on resume. The status string returned by the runner becomes stage-aware: `running:extract`, `running:normalize`, `completed`, etc. — the UI parses the prefix.

**Tech Stack:** Continuing — Python stdlib subprocess + concurrent.futures, ffmpeg (already bundled by M2), React 19. **No new pip or npm dependencies in this milestone.** Stages 3 (DeepFilterNet) and 4 (Silero VAD) introduce model-based dependencies and live in Milestone 4.

**Scope of this milestone:**
- New ffmpeg helper `run_loudnorm_measure` — runs loudnorm in measurement mode and parses the JSON it emits to stderr.
- New stage `engine/pipeline/normalize.py` — two-pass loudnorm + compressor + bandpass per brief §4.2.
- Pipeline chaining: rename `submit_extract` → `submit_pipeline` (chains extract → normalize); per-stage skip-when-completed idempotency; `get_status` returns stage-aware status string.
- Server endpoints accept the new return shape; `/api/source/process` calls `submit_pipeline`; `/api/source/state` returns the same stage-aware string.
- UI: `FileListItem` parses the stage suffix and shows `extracting…` / `normalizing…` / `✓` / `✗`. `EditorApp` polls until the overall pipeline reaches `completed` or `failed`.

**Out of scope for this milestone (deliberately deferred):**
- Stage 3 (DeepFilterNet enhance), Stage 4 (Silero VAD), and all later stages. These are Milestone 4+.
- Foreground priority preemption / queue jumping when the user switches sources mid-pipeline. M2's "first-come, first-served" behavior continues; the current job runs to completion before the next is started. Real foreground prioritization arrives in Milestone 6.
- Per-stage timing reporting in the UI ("normalize took 12 s") — `pipeline-state.json` has the timestamps but the UI doesn't surface them yet.
- Multi-track normalization heuristics — every track found by Stage 1 is normalized identically; per-track parameter tuning is out of scope.

---

## File Structure

```
bwc-clipper/
├── engine/
│   ├── ffmpeg.py                   MODIFY — add run_loudnorm_measure helper
│   ├── pipeline/
│   │   ├── normalize.py            NEW — Stage 2 implementation
│   │   └── runner.py               MODIFY — submit_extract → submit_pipeline; chain stages;
│   │                                stage-aware get_status
│   └── server.py                   MODIFY — _handle_source_process calls submit_pipeline
├── editor/
│   ├── components/
│   │   ├── FileListItem.jsx        MODIFY — parse stage prefix in status string
│   │   └── FileListItem.test.jsx   MODIFY — add per-stage label tests
│   ├── EditorApp.jsx               MODIFY — ACTIVE_PREFIXES check + polling continues
│   │                                until terminal status (any stage)
│   └── EditorApp.test.jsx          MODIFY — extend tests for chained pipeline
└── tests/
    ├── test_ffmpeg.py              MODIFY — add run_loudnorm_measure tests
    ├── test_pipeline_normalize.py  NEW — Stage 2 unit tests
    ├── test_pipeline_runner.py     MODIFY — replace submit_extract tests with submit_pipeline
    └── test_server_source.py       MODIFY — assertions check stage-aware status strings
```

**Why no new package files:** This milestone reuses the M2 stage protocol exactly. `normalize.py` is structurally identical to `extract.py` — same `load_state` → `update_stage(RUNNING)` → work → `update_stage(COMPLETED)` flow. The runner refactor is minor.

---

## Reference patterns

| New code in M3 | Reference (read for pattern) |
|---|---|
| `engine/pipeline/normalize.py` | `engine/pipeline/extract.py` — same shape exactly, swap the work block |
| `engine/ffmpeg.py` `run_loudnorm_measure` | the existing `run_ffmpeg`/`run_ffprobe` helpers — same subprocess.run pattern, capture stderr instead of stdout |
| Pipeline chaining in `runner.py` | the existing `submit_extract` — generalize to a list of stages, skip per-stage if already completed |
| Stage-aware status string format | `running:extract` / `running:normalize` / `completed` / `failed` / `idle` / `queued` — colon-prefixed when in a specific stage; bare strings for terminal/idle states |

**Brief reference for ffmpeg parameters (§4.2):**

```
First pass (measurement):
ffmpeg -i input.wav -af loudnorm=I=-16:LRA=11:TP=-1.5:print_format=json -f null -
# Parse JSON from stderr: input_i, input_tp, input_lra, input_thresh, target_offset

Second pass (apply):
ffmpeg -y -i input.wav \
  -af "loudnorm=I=-16:LRA=11:TP=-1.5:measured_I=...:measured_TP=...:measured_LRA=...:measured_thresh=...:offset=...:linear=true,acompressor=threshold=-24dB:ratio=4:attack=20:release=250:makeup=6,highpass=f=80,lowpass=f=8000" \
  -ar 16000 -ac 1 -c:a pcm_s16le \
  output.wav
```

---

## Tasks

### Task 1: Create milestone-3 branch

- [ ] **Step 1: Verify clean working tree on main**

```bash
cd "C:/Claude Code Projects/BWC Reviewer"
git status
git rev-parse --abbrev-ref HEAD
git log -1 --oneline
```

Expected: clean, on `main`, last commit `3830948` (M2 merge).

- [ ] **Step 2: Branch**

```bash
git checkout -b milestone-3-normalize-chain
```

---

### Task 2: `engine/ffmpeg.py` — `run_loudnorm_measure` helper (TDD)

**Files:**
- Modify: `tests/test_ffmpeg.py` (append)
- Modify: `engine/ffmpeg.py` (append)

`run_loudnorm_measure(input_path)` runs ffmpeg's loudnorm filter in measurement mode and parses the JSON object that ffmpeg writes to stderr. Returns a dict with the measured values (`input_i`, `input_tp`, `input_lra`, `input_thresh`, `target_offset`).

The existing `run_ffmpeg` helper captures stderr but discards it; we add a sibling helper that captures stderr explicitly and parses the JSON tail.

- [ ] **Step 1: Append tests**

```python
from engine.ffmpeg import run_loudnorm_measure


def test_run_loudnorm_measure_parses_json_from_stderr(tmp_path: Path, monkeypatch):
    fake = tmp_path / ("ffmpeg.exe" if os.name == "nt" else "ffmpeg")
    fake.write_bytes(b"")
    monkeypatch.setenv("BWC_CLIPPER_FFMPEG_DIR", str(tmp_path))

    # ffmpeg's loudnorm filter writes a JSON object to stderr after the audio
    # processing summary. Real-world output looks like this:
    fake_stderr = """\
ffmpeg version ... Copyright (c) ...
  built with gcc ...
[Parsed_loudnorm_0 @ 0x...] Loudnorm completed
[Parsed_loudnorm_0 @ 0x...]
{
        "input_i" : "-12.36",
        "input_tp" : "-0.31",
        "input_lra" : "8.20",
        "input_thresh" : "-22.36",
        "output_i" : "-15.12",
        "output_tp" : "-1.50",
        "output_lra" : "9.80",
        "output_thresh" : "-25.12",
        "normalization_type" : "linear",
        "target_offset" : "-1.20"
}
"""
    fake_completed = MagicMock(returncode=0, stdout="", stderr=fake_stderr)
    with patch("engine.ffmpeg.subprocess.run", return_value=fake_completed):
        measured = run_loudnorm_measure(Path("input.wav"))

    assert measured == {
        "input_i": "-12.36",
        "input_tp": "-0.31",
        "input_lra": "8.20",
        "input_thresh": "-22.36",
        "target_offset": "-1.20",
    }


def test_run_loudnorm_measure_raises_on_missing_json(tmp_path: Path, monkeypatch):
    fake = tmp_path / ("ffmpeg.exe" if os.name == "nt" else "ffmpeg")
    fake.write_bytes(b"")
    monkeypatch.setenv("BWC_CLIPPER_FFMPEG_DIR", str(tmp_path))

    fake_completed = MagicMock(returncode=0, stdout="", stderr="ffmpeg version ...\nno json here\n")
    with patch("engine.ffmpeg.subprocess.run", return_value=fake_completed):
        with pytest.raises(RuntimeError, match="loudnorm.*JSON"):
            run_loudnorm_measure(Path("input.wav"))


def test_run_loudnorm_measure_invokes_ffmpeg_with_correct_filter(tmp_path: Path, monkeypatch):
    fake = tmp_path / ("ffmpeg.exe" if os.name == "nt" else "ffmpeg")
    fake.write_bytes(b"")
    monkeypatch.setenv("BWC_CLIPPER_FFMPEG_DIR", str(tmp_path))

    valid_stderr = '{"input_i":"-12","input_tp":"-1","input_lra":"5","input_thresh":"-20","target_offset":"0"}'
    fake_completed = MagicMock(returncode=0, stdout="", stderr=valid_stderr)
    with patch("engine.ffmpeg.subprocess.run", return_value=fake_completed) as run_mock:
        run_loudnorm_measure(Path("input.wav"))

    cmd = run_mock.call_args[0][0]
    af_idx = cmd.index("-af")
    assert "loudnorm=I=-16" in cmd[af_idx + 1]
    assert "LRA=11" in cmd[af_idx + 1]
    assert "TP=-1.5" in cmd[af_idx + 1]
    assert "print_format=json" in cmd[af_idx + 1]
    # measurement pass writes to null sink
    assert "-f" in cmd
    assert "null" in cmd
```

- [ ] **Step 2: Run, confirm FAIL**

```bash
.venv/Scripts/python.exe -m pytest tests/test_ffmpeg.py -v -k loudnorm
```

Expected: `ImportError: cannot import name 'run_loudnorm_measure'`.

- [ ] **Step 3: Append to `engine/ffmpeg.py`**

```python
import re


# Required keys we expect in the loudnorm JSON output.
_LOUDNORM_KEYS = ("input_i", "input_tp", "input_lra", "input_thresh", "target_offset")


def run_loudnorm_measure(input_path: Path) -> dict[str, str]:
    """First pass of two-pass loudnorm. Returns measured values as a dict
    of strings (kept as strings because ffmpeg's second pass takes them
    through unchanged on the command line).

    Per brief §4.2: ``loudnorm=I=-16:LRA=11:TP=-1.5``.
    """
    binary = find_ffmpeg()
    cmd = [
        str(binary),
        "-hide_banner",
        "-i", str(input_path),
        "-af", "loudnorm=I=-16:LRA=11:TP=-1.5:print_format=json",
        "-f", "null",
        "-",
    ]
    try:
        result = subprocess.run(cmd, check=True, capture_output=True, text=True)
    except subprocess.CalledProcessError as exc:
        raise RuntimeError(f"ffmpeg loudnorm-measure failed: {exc.stderr}") from exc

    # ffmpeg writes the JSON object near the end of stderr. Find the last
    # balanced { ... } block and parse it.
    match = re.search(r"\{[^{}]*\}", result.stderr, re.DOTALL)
    if match is None:
        raise RuntimeError(
            "loudnorm did not emit a JSON measurement block. "
            f"Last stderr lines:\n{result.stderr[-500:]}"
        )
    try:
        data = json.loads(match.group(0))
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"loudnorm JSON parse failed: {exc}") from exc

    return {k: str(data[k]) for k in _LOUDNORM_KEYS if k in data}
```

(`re` and `json` are already imported earlier in the file.)

- [ ] **Step 4: Run, confirm 3 new tests pass; full ffmpeg test file: 13 tests pass**

```bash
.venv/Scripts/python.exe -m pytest tests/test_ffmpeg.py -v
```

- [ ] **Step 5: Commit**

```bash
git add engine/ffmpeg.py tests/test_ffmpeg.py
git commit -m "engine: add run_loudnorm_measure two-pass helper"
```

---

### Task 3: `engine/pipeline/normalize.py` — Stage 2 implementation (TDD)

**Files:**
- Create: `tests/test_pipeline_normalize.py`
- Create: `engine/pipeline/normalize.py`

The Normalize stage reads each `extracted/track{N}.wav`, runs the loudnorm measurement pass, then runs a single ffmpeg invocation that chains `loudnorm` (with measured values) + `acompressor` + `highpass`/`lowpass`. Outputs go to `normalized/track{N}.wav`. Updates pipeline-state.json with running/completed/failed.

- [ ] **Step 1: Write failing tests**

`tests/test_pipeline_normalize.py`:

```python
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
```

- [ ] **Step 2: Run, confirm FAIL**

```bash
.venv/Scripts/python.exe -m pytest tests/test_pipeline_normalize.py -v
```

- [ ] **Step 3: Create `engine/pipeline/normalize.py`**

```python
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
```

- [ ] **Step 4: Run, confirm 5 passed**

```bash
.venv/Scripts/python.exe -m pytest tests/test_pipeline_normalize.py -v
```

- [ ] **Step 5: Commit**

```bash
git add engine/pipeline/normalize.py tests/test_pipeline_normalize.py
git commit -m "engine: add Stage 2 normalize — two-pass loudnorm + compress + bandpass"
```

---

### Task 4: `engine/pipeline/runner.py` — chain stages in `submit_pipeline` (TDD)

**Files:**
- Modify: `tests/test_pipeline_runner.py` (rewrite test cases for chained pipeline)
- Modify: `engine/pipeline/runner.py`

Replace `submit_extract` with `submit_pipeline`. The chained job runs `run_extract_stage` then `run_normalize_stage` serially in the executor thread. Each stage is skipped if already completed (idempotent). `get_status` returns:

- `idle` when no stage has started
- `queued` when a job is registered but not yet running
- `running:extract` while extract is the active stage
- `running:normalize` while normalize is the active stage
- `completed` when all stages have completed
- `failed` if any stage failed

- [ ] **Step 1: Replace `tests/test_pipeline_runner.py` (full rewrite)**

```python
"""Tests for engine.pipeline.runner — chained pipeline dispatch."""
from pathlib import Path
from unittest.mock import patch

import pytest


def _touch(p: Path, content: bytes = b""):
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_bytes(content)


def test_runner_get_status_idle_for_unprocessed_source(tmp_path: Path):
    from engine.pipeline.runner import PipelineRunner

    source = tmp_path / "x.mp4"
    _touch(source, b"x")

    runner = PipelineRunner()
    try:
        assert runner.get_status(tmp_path, source) == "idle"
    finally:
        runner.shutdown()


def test_runner_submit_pipeline_runs_extract_then_normalize(tmp_path: Path):
    from engine.pipeline.runner import PipelineRunner

    source = tmp_path / "x.mp4"
    _touch(source, b"x")

    runner = PipelineRunner()
    try:
        with patch("engine.pipeline.extract.probe_audio_tracks") as probe_mock, \
             patch("engine.pipeline.extract.run_ffmpeg", return_value=""), \
             patch("engine.pipeline.normalize.run_loudnorm_measure",
                   return_value={"input_i": "-12", "input_tp": "-1", "input_lra": "5",
                                 "input_thresh": "-20", "target_offset": "0"}), \
             patch("engine.pipeline.normalize.run_ffmpeg", return_value=""):
            probe_mock.return_value = [
                {"index": 0, "codec_name": "aac", "sample_rate": 48000, "channels": 1, "duration_seconds": 1.0},
            ]
            future = runner.submit_pipeline(tmp_path, source)
            future.result(timeout=5)
        assert runner.get_status(tmp_path, source) == "completed"
    finally:
        runner.shutdown()


def test_runner_get_status_failed_after_normalize_error(tmp_path: Path):
    from engine.pipeline.runner import PipelineRunner

    source = tmp_path / "x.mp4"
    _touch(source, b"x")

    runner = PipelineRunner()
    try:
        with patch("engine.pipeline.extract.probe_audio_tracks") as probe_mock, \
             patch("engine.pipeline.extract.run_ffmpeg", return_value=""), \
             patch("engine.pipeline.normalize.run_loudnorm_measure",
                   side_effect=RuntimeError("boom-norm")):
            probe_mock.return_value = [
                {"index": 0, "codec_name": "aac", "sample_rate": 48000, "channels": 1, "duration_seconds": 1.0},
            ]
            future = runner.submit_pipeline(tmp_path, source)
            with pytest.raises(RuntimeError):
                future.result(timeout=5)
        assert runner.get_status(tmp_path, source) == "failed"
    finally:
        runner.shutdown()


def test_runner_get_status_failed_after_extract_error(tmp_path: Path):
    from engine.pipeline.runner import PipelineRunner

    source = tmp_path / "x.mp4"
    _touch(source, b"x")

    runner = PipelineRunner()
    try:
        with patch("engine.pipeline.extract.probe_audio_tracks") as probe_mock, \
             patch("engine.pipeline.extract.run_ffmpeg", side_effect=RuntimeError("boom-extract")):
            probe_mock.return_value = [
                {"index": 0, "codec_name": "aac", "sample_rate": 48000, "channels": 1, "duration_seconds": 1.0},
            ]
            future = runner.submit_pipeline(tmp_path, source)
            with pytest.raises(RuntimeError):
                future.result(timeout=5)
        assert runner.get_status(tmp_path, source) == "failed"
    finally:
        runner.shutdown()


def test_runner_skips_extract_if_already_completed(tmp_path: Path):
    """If extract was previously completed, submit_pipeline only runs normalize."""
    from engine.pipeline.runner import PipelineRunner
    from engine.pipeline.extract import run_extract_stage
    from engine.source import source_cache_dir

    source = tmp_path / "x.mp4"
    _touch(source, b"x")

    # Pre-run extract so its state.json says completed
    cache_dir = source_cache_dir(tmp_path, source)
    with patch("engine.pipeline.extract.probe_audio_tracks") as probe_mock, \
         patch("engine.pipeline.extract.run_ffmpeg", return_value=""):
        probe_mock.return_value = [
            {"index": 0, "codec_name": "aac", "sample_rate": 48000, "channels": 1, "duration_seconds": 1.0},
        ]
        run_extract_stage(source, cache_dir)

    runner = PipelineRunner()
    try:
        with patch("engine.pipeline.extract.run_ffmpeg") as extract_mock, \
             patch("engine.pipeline.normalize.run_loudnorm_measure",
                   return_value={"input_i": "-12", "input_tp": "-1", "input_lra": "5",
                                 "input_thresh": "-20", "target_offset": "0"}), \
             patch("engine.pipeline.normalize.run_ffmpeg", return_value="") as norm_mock:
            # Need an extracted/track0.wav for normalize to read
            extracted = cache_dir / "extracted" / "track0.wav"
            extracted.parent.mkdir(parents=True, exist_ok=True)
            extracted.write_bytes(b"fake")

            future = runner.submit_pipeline(tmp_path, source)
            future.result(timeout=5)

            # Extract's run_ffmpeg should NOT have been called this time
            assert extract_mock.call_count == 0
            # Normalize's run_ffmpeg should have been called once (one track)
            assert norm_mock.call_count == 1
        assert runner.get_status(tmp_path, source) == "completed"
    finally:
        runner.shutdown()


def test_runner_get_status_returns_running_with_stage_name(tmp_path: Path):
    """While extract is running, status is 'running:extract'."""
    import threading
    import time
    from engine.pipeline.runner import PipelineRunner

    source = tmp_path / "x.mp4"
    _touch(source, b"x")

    extract_started = threading.Event()
    block_extract = threading.Event()

    def slow_run_ffmpeg(*args, **kwargs):
        extract_started.set()
        # Block until the test releases us
        block_extract.wait(timeout=5)
        return ""

    runner = PipelineRunner()
    try:
        with patch("engine.pipeline.extract.probe_audio_tracks") as probe_mock, \
             patch("engine.pipeline.extract.run_ffmpeg", side_effect=slow_run_ffmpeg), \
             patch("engine.pipeline.normalize.run_loudnorm_measure",
                   return_value={"input_i": "-12", "input_tp": "-1", "input_lra": "5",
                                 "input_thresh": "-20", "target_offset": "0"}), \
             patch("engine.pipeline.normalize.run_ffmpeg", return_value=""):
            probe_mock.return_value = [
                {"index": 0, "codec_name": "aac", "sample_rate": 48000, "channels": 1, "duration_seconds": 1.0},
            ]

            future = runner.submit_pipeline(tmp_path, source)
            assert extract_started.wait(timeout=2)
            # extract is now hanging on the event
            assert runner.get_status(tmp_path, source) == "running:extract"
            block_extract.set()
            future.result(timeout=5)
        assert runner.get_status(tmp_path, source) == "completed"
    finally:
        block_extract.set()
        runner.shutdown()
```

- [ ] **Step 2: Run, confirm FAIL**

```bash
.venv/Scripts/python.exe -m pytest tests/test_pipeline_runner.py -v
```

Expected: most tests fail with `AttributeError: 'PipelineRunner' object has no attribute 'submit_pipeline'`.

- [ ] **Step 3: Replace `engine/pipeline/runner.py`**

```python
"""Single-worker pipeline job runner.

Holds a ``concurrent.futures.ThreadPoolExecutor(max_workers=1)`` and an
in-memory registry of in-flight jobs keyed by source path. Submissions
return a Future immediately; the worker runs jobs serially.

The pipeline currently has two stages: extract (M2) and normalize (M3).
Each stage is skipped if pipeline-state.json says it's already completed,
so resubmitting a partially-processed source picks up where it left off.
Later milestones (M4+) extend ``_PIPELINE_STAGES`` with enhance, vad, etc.
"""

from __future__ import annotations

import threading
from concurrent.futures import Future, ThreadPoolExecutor
from pathlib import Path
from typing import Callable

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


def _run_pipeline(source_path: Path, cache_dir: Path) -> None:
    """Execute each stage in order, skipping stages already marked completed."""
    for name, fn in _PIPELINE_STAGES:
        state = load_state(cache_dir)
        if state.stages.get(name, {}).get("status") == StageStatus.COMPLETED.value:
            continue
        fn(source_path, cache_dir)


class PipelineRunner:
    def __init__(self):
        self._executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="bwc-pipeline")
        self._jobs: dict[str, Future] = {}
        self._lock = threading.Lock()

    def submit_pipeline(self, project_folder: Path, source_path: Path) -> Future:
        """Queue the full pipeline for a source. Idempotent: stages already
        marked completed in pipeline-state.json are skipped. If every stage
        is already completed, returns a pre-resolved Future without queueing.
        """
        cache_dir = source_cache_dir(project_folder, source_path)
        state = load_state(cache_dir)
        all_completed = all(
            state.stages.get(name, {}).get("status") == StageStatus.COMPLETED.value
            for name, _ in _PIPELINE_STAGES
        )
        if all_completed:
            f: Future = Future()
            f.set_result(None)
            return f

        key = str(source_path)
        with self._lock:
            existing = self._jobs.get(key)
            if existing and not existing.done():
                return existing
            future = self._executor.submit(_run_pipeline, source_path, cache_dir)
            self._jobs[key] = future
            return future

    def get_status(self, project_folder: Path, source_path: Path) -> str:
        """Return one of: idle, queued, running:<stage>, completed, failed.

        Combines the persisted pipeline-state.json with the in-memory job
        registry. If any stage failed, returns 'failed'. If all stages are
        completed, returns 'completed'. Otherwise the active stage is the
        first non-completed stage in the pipeline.
        """
        cache_dir = source_cache_dir(project_folder, source_path)
        state = load_state(cache_dir)

        # Check for any failed stage first.
        for name, _ in _PIPELINE_STAGES:
            if state.stages.get(name, {}).get("status") == StageStatus.FAILED.value:
                return "failed"

        # All stages completed?
        all_completed = all(
            state.stages.get(name, {}).get("status") == StageStatus.COMPLETED.value
            for name, _ in _PIPELINE_STAGES
        )
        if all_completed:
            return "completed"

        # Find the first non-completed stage.
        active_stage = None
        for name, _ in _PIPELINE_STAGES:
            if state.stages.get(name, {}).get("status") != StageStatus.COMPLETED.value:
                active_stage = name
                break

        key = str(source_path)
        with self._lock:
            job = self._jobs.get(key)
        if job is None:
            # No state, no job → idle. Some state but no job → idle (cache from
            # a previous run that wasn't completed; user will need to re-submit).
            if not state.stages:
                return "idle"
            # Some stage is in flight from a prior run that crashed mid-stage.
            # Treat as idle so the next submit picks it up.
            return "idle"
        if job.done():
            # Job finished but get_status is called before persisted state catches up.
            # Re-read state.
            state = load_state(cache_dir)
            for name, _ in _PIPELINE_STAGES:
                if state.stages.get(name, {}).get("status") == StageStatus.FAILED.value:
                    return "failed"
            all_done = all(
                state.stages.get(name, {}).get("status") == StageStatus.COMPLETED.value
                for name, _ in _PIPELINE_STAGES
            )
            return "completed" if all_done else "idle"
        if job.running():
            return f"running:{active_stage}"
        return "queued"

    def shutdown(self):
        self._executor.shutdown(wait=False, cancel_futures=True)
```

- [ ] **Step 4: Run, confirm 6 passed**

```bash
.venv/Scripts/python.exe -m pytest tests/test_pipeline_runner.py -v
```

- [ ] **Step 5: Commit**

```bash
git add engine/pipeline/runner.py tests/test_pipeline_runner.py
git commit -m "engine: chain extract → normalize in submit_pipeline; stage-aware get_status"
```

---

### Task 5: `engine/server.py` — point endpoints at `submit_pipeline` (TDD)

**Files:**
- Modify: `tests/test_server_source.py` (update assertions for stage-aware status)
- Modify: `engine/server.py` (rename submit_extract → submit_pipeline)

- [ ] **Step 1: Update the test assertions**

In `tests/test_server_source.py`:

Find:

```python
def test_process_endpoint_submits_extract_and_returns_status(running_server, tmp_path: Path):
    source = tmp_path / "officer.mp4"
    _touch(source, b"x")

    with patch("engine.pipeline.extract.probe_audio_tracks") as probe_mock, \
         patch("engine.pipeline.extract.run_ffmpeg", return_value=""):
        probe_mock.return_value = [{"index": 0, "codec_name": "aac", "sample_rate": 48000, "channels": 1, "duration_seconds": 1.0}]
        response = requests.post(
            f"http://127.0.0.1:{running_server}/api/source/process",
            json={"folder": str(tmp_path), "source": str(source)},
            timeout=5,
        )
    assert response.status_code == 200
    body = response.json()
    assert body["status"] in ("queued", "running", "completed")
```

Replace with (now that the pipeline is chained, the immediate post-submit status may be `queued`, `running:extract`, `running:normalize`, or `completed`):

```python
def test_process_endpoint_submits_pipeline_and_returns_status(running_server, tmp_path: Path):
    source = tmp_path / "officer.mp4"
    _touch(source, b"x")

    with patch("engine.pipeline.extract.probe_audio_tracks") as probe_mock, \
         patch("engine.pipeline.extract.run_ffmpeg", return_value=""), \
         patch("engine.pipeline.normalize.run_loudnorm_measure",
               return_value={"input_i": "-12", "input_tp": "-1", "input_lra": "5",
                             "input_thresh": "-20", "target_offset": "0"}), \
         patch("engine.pipeline.normalize.run_ffmpeg", return_value=""):
        probe_mock.return_value = [{"index": 0, "codec_name": "aac", "sample_rate": 48000, "channels": 1, "duration_seconds": 1.0}]
        response = requests.post(
            f"http://127.0.0.1:{running_server}/api/source/process",
            json={"folder": str(tmp_path), "source": str(source)},
            timeout=5,
        )
    assert response.status_code == 200
    body = response.json()
    assert (
        body["status"] == "queued"
        or body["status"].startswith("running:")
        or body["status"] == "completed"
    )
```

Find and update the completed-after-extract test similarly. Replace:

```python
def test_state_endpoint_completed_after_extract(running_server, tmp_path: Path):
```

With:

```python
def test_state_endpoint_completed_after_pipeline(running_server, tmp_path: Path):
    source = tmp_path / "officer.mp4"
    _touch(source, b"x")

    with patch("engine.pipeline.extract.probe_audio_tracks") as probe_mock, \
         patch("engine.pipeline.extract.run_ffmpeg", return_value=""), \
         patch("engine.pipeline.normalize.run_loudnorm_measure",
               return_value={"input_i": "-12", "input_tp": "-1", "input_lra": "5",
                             "input_thresh": "-20", "target_offset": "0"}), \
         patch("engine.pipeline.normalize.run_ffmpeg", return_value=""):
        probe_mock.return_value = [{"index": 0, "codec_name": "aac", "sample_rate": 48000, "channels": 1, "duration_seconds": 1.0}]
        requests.post(
            f"http://127.0.0.1:{running_server}/api/source/process",
            json={"folder": str(tmp_path), "source": str(source)},
            timeout=5,
        )
        # Poll until completed (max 5s)
        import time
        deadline = time.time() + 5
        status = None
        while time.time() < deadline:
            r = requests.get(
                f"http://127.0.0.1:{running_server}/api/source/state",
                params={"folder": str(tmp_path), "source": str(source)},
                timeout=5,
            )
            status = r.json()["status"]
            if status == "completed":
                break
            time.sleep(0.05)
        assert status == "completed"
```

- [ ] **Step 2: Run, confirm tests fail because runner has no `submit_extract`**

```bash
.venv/Scripts/python.exe -m pytest tests/test_server_source.py -v
```

- [ ] **Step 3: Update `engine/server.py` to call `submit_pipeline`**

Find inside `_handle_source_process`:

```python
        runner = get_pipeline_runner()
        runner.submit_extract(Path(folder), Path(source))
        status = runner.get_status(Path(folder), Path(source))
```

Replace with:

```python
        runner = get_pipeline_runner()
        runner.submit_pipeline(Path(folder), Path(source))
        status = runner.get_status(Path(folder), Path(source))
```

- [ ] **Step 4: Run, confirm 5 passed**

```bash
.venv/Scripts/python.exe -m pytest tests/test_server_source.py -v
```

- [ ] **Step 5: Run the full pytest suite** (regression check — total test count grows by ~14 from this milestone)

```bash
.venv/Scripts/python.exe -m pytest -v
```

Expected: all tests pass.

- [ ] **Step 6: Commit**

```bash
git add engine/server.py tests/test_server_source.py
git commit -m "engine: route /api/source/process to submit_pipeline"
```

---

### Task 6: `editor/components/FileListItem.jsx` — stage-aware status indicator (TDD)

**Files:**
- Modify: `editor/components/FileListItem.test.jsx` (append)
- Modify: `editor/components/FileListItem.jsx`

The status string from the engine now includes a stage suffix (`running:extract`, `running:normalize`). FileListItem parses the prefix and renders the right label.

- [ ] **Step 1: Append tests**

```jsx
describe('FileListItem stage-aware status', () => {
    it('renders "extracting…" for running:extract', () => {
        render(
            <FileListItem
                file={sampleFile}
                selected={false}
                onSelect={() => {}}
                status="running:extract"
            />,
        );
        expect(screen.getByText(/extracting/i)).toBeDefined();
    });

    it('renders "normalizing…" for running:normalize', () => {
        render(
            <FileListItem
                file={sampleFile}
                selected={false}
                onSelect={() => {}}
                status="running:normalize"
            />,
        );
        expect(screen.getByText(/normalizing/i)).toBeDefined();
    });

    it('falls back to "running" for an unknown stage suffix', () => {
        render(
            <FileListItem
                file={sampleFile}
                selected={false}
                onSelect={() => {}}
                status="running:something-new"
            />,
        );
        expect(screen.getByText(/running/i)).toBeDefined();
    });
});
```

- [ ] **Step 2: Run, confirm new tests FAIL**

```bash
npx vitest run editor/components/FileListItem.test.jsx
```

- [ ] **Step 3: Modify `editor/components/FileListItem.jsx`**

Find the existing constants block:

```jsx
const STATUS_LABELS = {
    queued: 'queued',
    running: 'extracting…',
    completed: '',
    failed: 'failed',
};

const STATUS_COLORS = {
    queued: '#6e7681',
    running: '#fbbf24',
    completed: '#22c55e',
    failed: '#f87171',
};
```

Replace with:

```jsx
const STAGE_LABELS = {
    extract: 'extracting…',
    normalize: 'normalizing…',
    // Future stages (M4+): enhance: 'enhancing…', vad: 'detecting speech…', etc.
};

const TERMINAL_LABELS = {
    queued: 'queued',
    completed: '',
    failed: 'failed',
};

const STATUS_COLORS = {
    queued: '#6e7681',
    running: '#fbbf24',
    completed: '#22c55e',
    failed: '#f87171',
};

function statusKey(status) {
    // 'running:extract' → 'running'; 'completed' → 'completed'.
    const colon = status.indexOf(':');
    return colon >= 0 ? status.slice(0, colon) : status;
}

function statusLabel(status) {
    if (status.startsWith('running:')) {
        const stage = status.slice('running:'.length);
        return STAGE_LABELS[stage] ?? 'running';
    }
    return TERMINAL_LABELS[status] ?? status;
}
```

Find the `StatusIndicator` body:

```jsx
function StatusIndicator({ status }) {
    if (!status) return null;
    const color = STATUS_COLORS[status] ?? '#6e7681';
    const label = STATUS_LABELS[status] ?? status;
    const glyph = status === 'completed' ? '✓' : status === 'failed' ? '✗' : '●';
    return (
```

Replace with:

```jsx
function StatusIndicator({ status }) {
    if (!status) return null;
    const key = statusKey(status);
    const color = STATUS_COLORS[key] ?? '#6e7681';
    const label = statusLabel(status);
    const glyph = key === 'completed' ? '✓' : key === 'failed' ? '✗' : '●';
    return (
```

- [ ] **Step 4: Update one existing test that asserted `running` directly**

Find the existing test:

```jsx
    it('renders running status', () => {
        render(
            <FileListItem
                file={sampleFile}
                selected={false}
                onSelect={() => {}}
                status="running"
            />,
        );
        expect(screen.getByText(/extracting/i)).toBeDefined();
    });
```

Replace with (the engine no longer returns plain "running"; it returns "running:<stage>"):

```jsx
    it('renders generic running label when status is just "running"', () => {
        render(
            <FileListItem
                file={sampleFile}
                selected={false}
                onSelect={() => {}}
                status="running"
            />,
        );
        // Plain "running" without a stage suffix falls through to generic label.
        // Don't assert exact wording — implementation detail — but DO assert the
        // status-color dot is visible by aria-hidden glyph.
        expect(screen.getByText('●')).toBeDefined();
    });
```

- [ ] **Step 5: Run, confirm all FileListItem tests pass (was 11, now 14)**

```bash
npx vitest run editor/components/FileListItem.test.jsx
```

- [ ] **Step 6: Commit**

```bash
git add editor/components/FileListItem.jsx editor/components/FileListItem.test.jsx
git commit -m "editor: parse stage prefix in FileListItem status indicator"
```

---

### Task 7: `editor/EditorApp.jsx` — poll until terminal status across stages (TDD)

**Files:**
- Modify: `editor/EditorApp.test.jsx`
- Modify: `editor/EditorApp.jsx`

`ACTIVE_STATUSES` becomes a prefix check. The polling loop continues while status is `queued` or starts with `running:`; stops on `completed` or `failed`.

- [ ] **Step 1: Add a test for the chained-pipeline status flow**

In the existing `describe('EditorApp', ...)` block, REPLACE the test:

```jsx
    it('polls source state and updates UI to completed', async () => {
        global.fetch = setupFetchStub({ sequence: ['running', 'running', 'completed'] });
        render(<EditorApp />);
        fireEvent.click(screen.getByRole('button', { name: /open folder/i }));
        await waitFor(() => expect(screen.getByText('officer.mp4')).toBeDefined());
        fireEvent.click(screen.getByText('officer.mp4'));

        // First poll → running
        await act(async () => {
            await vi.advanceTimersByTimeAsync(1000);
        });
        // Second poll → completed
        await act(async () => {
            await vi.advanceTimersByTimeAsync(1000);
        });
        await act(async () => {
            await vi.advanceTimersByTimeAsync(1000);
        });

        await waitFor(() => {
            const row = document.querySelector('[data-status="completed"]');
            expect(row).not.toBeNull();
        });
    });
```

WITH:

```jsx
    it('polls source state across stages and updates UI to completed', async () => {
        global.fetch = setupFetchStub({
            sequence: ['running:extract', 'running:normalize', 'completed'],
        });
        render(<EditorApp />);
        fireEvent.click(screen.getByRole('button', { name: /open folder/i }));
        await waitFor(() => expect(screen.getByText('officer.mp4')).toBeDefined());
        fireEvent.click(screen.getByText('officer.mp4'));

        // First poll → running:extract
        await act(async () => { await vi.advanceTimersByTimeAsync(1000); });
        // Second poll → running:normalize
        await act(async () => { await vi.advanceTimersByTimeAsync(1000); });
        // Third poll → completed
        await act(async () => { await vi.advanceTimersByTimeAsync(1000); });
        // Fourth tick — polling should have stopped after seeing 'completed'.
        await act(async () => { await vi.advanceTimersByTimeAsync(1000); });

        await waitFor(() => {
            const row = document.querySelector('[data-status="completed"]');
            expect(row).not.toBeNull();
        });
    });
```

- [ ] **Step 2: Run, confirm fail (the current `ACTIVE_STATUSES` set doesn't recognize `running:extract`)**

```bash
npx vitest run editor/EditorApp.test.jsx
```

- [ ] **Step 3: Modify `editor/EditorApp.jsx`**

Find:

```jsx
const ACTIVE_STATUSES = new Set(['queued', 'running']);
```

Replace with:

```jsx
function isActiveStatus(s) {
    return s === 'queued' || (typeof s === 'string' && s.startsWith('running'));
}
```

Then find ALL uses of `ACTIVE_STATUSES.has(...)` and replace with `isActiveStatus(...)`. There are exactly two locations:

```jsx
            if (ACTIVE_STATUSES.has(resp.status)) {
                startPolling(file.path);
            }
```

becomes:

```jsx
            if (isActiveStatus(resp.status)) {
                startPolling(file.path);
            }
```

And:

```jsx
                if (!ACTIVE_STATUSES.has(resp.status)) {
                    stopPolling();
                }
```

becomes:

```jsx
                if (!isActiveStatus(resp.status)) {
                    stopPolling();
                }
```

- [ ] **Step 4: Run, confirm all editor tests pass**

```bash
npm test
```

Expected: 4 EditorApp + 3 EmptyState + 14 FileListItem (11 + 3 new) + 8 ProjectView = 29 tests.

- [ ] **Step 5: Commit**

```bash
git add editor/EditorApp.jsx editor/EditorApp.test.jsx
git commit -m "editor: keep polling across stage transitions in chained pipeline"
```

---

### Task 8: Manual launch verification

**Files:** none (verification, no commit)

- [ ] **Step 1: Build and run the test suites once**

```bash
npm run build:editor
.venv/Scripts/python.exe -m pytest -v
npm test
```

- [ ] **Step 2: Launch the app**

```bash
npm start
```

Expected manual verification:
- Splash → main window opens (ffmpeg already cached from M2).
- Open `Samples/BWC/`. File list appears.
- Click a file you HAVEN'T processed before (or delete its `.bwcclipper/<source-stem>/` cache subdirectory first to re-test from scratch). Status indicator shows:
  1. `● extracting…` (yellow) for ~5–30 s
  2. `● normalizing…` (yellow) for another ~5–60 s (loudness measurement is roughly real-time, so a 30-min source might take a while)
  3. `✓` (green) when both stages complete
- Inspect `Samples/BWC/.bwcclipper/<stem>/`:
  - `extracted/track0.wav` (from M2)
  - `normalized/track0.wav` — **new in M3**, slightly different size from `extracted/track0.wav` (compression + normalization changes the data)
  - `pipeline-state.json` shows both `extract` and `normalize` stages with `completed` status
- Click a previously-completed file → indicator stays `✓` (skip-when-completed working).
- Close the app → no orphan processes.

- [ ] **Step 3: If anything fails, debug — do NOT commit until manual flow works**

---

### Task 9: README — update with M3 status

**Files:**
- Modify: `README.md`

- [ ] **Step 1: Edit `README.md`**

Replace:

```
> **Status:** Milestone 2 of 8 complete — ffmpeg integration + audio extraction. App downloads ffmpeg on first launch, extracts each media file's audio tracks to 16 kHz mono WAVs in the project's hidden cache, and shows live processing status on each file row.
```

With:

```
> **Status:** Milestone 3 of 8 complete — Stage 2 normalize + pipeline chaining. After extracting audio (Stage 1), the engine now runs two-pass loudness normalization plus dynamic-range compression and bandpass filtering (per the brief's §4.2 ffmpeg chain). The UI status indicator reflects the active stage — `extracting…` → `normalizing…` → `✓`.
```

- [ ] **Step 2: Commit**

```bash
git add README.md
git commit -m "docs: update status to M3 complete"
```

---

### Task 10: Push, merge to main, clean up

- [ ] **Step 1: Push the branch**

```bash
git push -u origin milestone-3-normalize-chain
```

- [ ] **Step 2: Switch to main and merge**

```bash
git checkout main
git merge --no-ff milestone-3-normalize-chain -m "$(cat <<'EOF'
Merge milestone 3: Stage 2 normalize + pipeline chaining

Adds Stage 2 of the transcription pipeline (loudness normalization +
dynamic-range compression + bandpass per brief §4.2) and the runner
scaffolding to chain stages serially. New engine/pipeline/normalize.py
mirrors the Stage 1 protocol. New engine.ffmpeg.run_loudnorm_measure
runs the first-pass measurement and parses ffmpeg's JSON output.
PipelineRunner.submit_extract is replaced with submit_pipeline that
runs extract → normalize, skipping any stage already completed in
pipeline-state.json. get_status returns stage-aware strings —
running:extract / running:normalize / completed / failed. UI's
FileListItem renders the right label per stage; EditorApp polls until
terminal status is reached regardless of which stage is active.

Test coverage: 11 new pytest tests (ffmpeg loudnorm-measure, pipeline
normalize, runner chained dispatch with new stage-status assertions);
3 new vitest tests on FileListItem stage labels. Manual launch
verified end-to-end on a Samples/BWC source — extracted/track0.wav
plus normalized/track0.wav both produced, pipeline-state.json shows
both stages completed.

Out of scope (deferred to M4): Stage 3 enhance (DeepFilterNet),
Stage 4 VAD (Silero), and the model-dependency story they bring.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

- [ ] **Step 3: Push main and clean up**

```bash
git push origin main
git push origin --delete milestone-3-normalize-chain
git branch -d milestone-3-normalize-chain
```

---

## What this milestone leaves you with

- A two-stage pipeline that runs end-to-end on real BWC video, with each stage's output cached separately and pipeline state persisted across runs.
- The chaining infrastructure that all subsequent stages plug into without any further refactoring — `_PIPELINE_STAGES` is the canonical extension point.
- A stage-aware UI status protocol (`running:<stage>`) that scales to the rest of the pipeline as new stages are added.
- The pattern for parsing ffmpeg filter output (loudnorm JSON in stderr) that other ffmpeg-driven measurement steps will reuse.

## Next milestone (preview, not part of this plan)

**Milestone 4: Stage 3 enhance (DeepFilterNet) + Stage 4 VAD (Silero) + speech-segments.json.** New pip dependencies (`deepfilternet`, `silero-vad`, `torch`, `soundfile`). Two new stages plug into `_PIPELINE_STAGES`. New artifact `speech-segments.json` at the source root, schema `{tracks: [{start, end}, ...]}`. UI status grows two more labels (`enhancing…`, `detecting speech…`). Adds the dependency-gate's first real check (do we have torch?), the foundation for the full gate in Milestone 7.
