"""Single-worker pipeline job runner.

Holds a ``concurrent.futures.ThreadPoolExecutor(max_workers=1)`` and an
in-memory registry of in-flight jobs keyed by source path. Submissions
return a Future immediately; the worker runs jobs serially.

For Milestone 2 the only stage is ``extract``. Later milestones add a
``submit_full_pipeline`` that chains extract → normalize → enhance → ...
"""

from __future__ import annotations

import threading
from concurrent.futures import Future, ThreadPoolExecutor
from pathlib import Path

from engine.pipeline.extract import run_extract_stage
from engine.pipeline.state import StageStatus, load_state
from engine.source import source_cache_dir


class PipelineRunner:
    def __init__(self):
        self._executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="bwc-pipeline")
        self._jobs: dict[str, Future] = {}
        self._lock = threading.Lock()

    def submit_extract(self, project_folder: Path, source_path: Path) -> Future:
        """Queue an extract job. If the source already has extract=completed,
        return a pre-resolved Future without queueing.
        """
        cache_dir = source_cache_dir(project_folder, source_path)
        state = load_state(cache_dir)
        if state.stages.get("extract", {}).get("status") == StageStatus.COMPLETED.value:
            f: Future = Future()
            f.set_result(None)
            return f

        key = str(source_path)
        with self._lock:
            existing = self._jobs.get(key)
            if existing and not existing.done():
                return existing
            future = self._executor.submit(run_extract_stage, source_path, cache_dir)
            self._jobs[key] = future
            return future

    def get_status(self, project_folder: Path, source_path: Path) -> str:
        """Return one of: idle, queued, running, completed, failed.

        Combines the persisted pipeline-state.json with the in-memory job
        registry so transient "queued" state is visible before the worker
        picks up the job.
        """
        cache_dir = source_cache_dir(project_folder, source_path)
        state = load_state(cache_dir)
        extract = state.stages.get("extract", {})
        persisted = extract.get("status")
        if persisted in (StageStatus.COMPLETED.value, StageStatus.FAILED.value):
            return persisted

        key = str(source_path)
        with self._lock:
            job = self._jobs.get(key)
        if job is None:
            return "idle"
        if job.done():
            # Race: the job finished but state.json hasn't been re-read yet.
            # Re-read.
            state = load_state(cache_dir)
            extract = state.stages.get("extract", {})
            return extract.get("status", "idle")
        if job.running():
            return "running"
        return "queued"

    def shutdown(self):
        self._executor.shutdown(wait=False, cancel_futures=True)
