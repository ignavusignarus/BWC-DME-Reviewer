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

from engine.pipeline.align import run_align_stage
from engine.pipeline.enhance import run_enhance_stage
from engine.pipeline.extract import run_extract_stage
from engine.pipeline.normalize import run_normalize_stage
from engine.pipeline.state import PipelineState, StageStatus, load_state, save_state
from engine.pipeline.transcribe import run_transcribe_stage
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
    ("transcribe", lambda _source, cache: run_transcribe_stage(cache)),
    ("align", lambda source, cache: run_align_stage(source, cache)),
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

    def rerun_from_stage(
        self, stage_name: str, project_folder: Path, source_path: Path
    ) -> Future:
        """Clear `stage_name` and every subsequent stage's persisted state, then
        submit the pipeline. The existing skip-when-COMPLETED logic causes
        stages before `stage_name` to be skipped and the cleared stages to run.

        Forward-compatible with M7+: any stage added after `align` in
        _PIPELINE_STAGES will be cleared by rerun_from_stage("transcribe", ...).

        Raises ValueError if `stage_name` is not in _PIPELINE_STAGES.
        """
        stage_names = [name for name, _ in _PIPELINE_STAGES]
        if stage_name not in stage_names:
            raise ValueError(f"unknown stage: {stage_name!r}")
        cache_dir = source_cache_dir(project_folder, source_path)
        state = load_state(cache_dir)
        start_index = stage_names.index(stage_name)
        new_stages = dict(state.stages)
        for name in stage_names[start_index:]:
            new_stages.pop(name, None)
        save_state(cache_dir, PipelineState(schema_version=state.schema_version, stages=new_stages))
        return self.submit_pipeline(project_folder, source_path)

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
