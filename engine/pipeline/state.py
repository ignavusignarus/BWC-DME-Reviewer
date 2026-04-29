"""Pipeline state persistence (pipeline-state.json).

One file per source cache subdirectory. Tracks per-stage status and
arbitrary per-stage metadata (timestamps, output paths, error message).
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any

SCHEMA_VERSION = "1.0"
STATE_FILENAME = "pipeline-state.json"


class StageStatus(str, Enum):
    QUEUED = "queued"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


@dataclass
class PipelineState:
    schema_version: str = SCHEMA_VERSION
    stages: dict[str, dict] = field(default_factory=dict)

    @classmethod
    def empty(cls) -> "PipelineState":
        return cls()


def load_state(cache_dir: Path) -> PipelineState:
    file = cache_dir / STATE_FILENAME
    if not file.is_file():
        return PipelineState.empty()
    raw = json.loads(file.read_text(encoding="utf-8"))
    return PipelineState(
        schema_version=raw.get("schema_version", SCHEMA_VERSION),
        stages=raw.get("stages", {}),
    )


def save_state(cache_dir: Path, state: PipelineState) -> None:
    cache_dir.mkdir(parents=True, exist_ok=True)
    file = cache_dir / STATE_FILENAME
    file.write_text(
        json.dumps(
            {"schema_version": state.schema_version, "stages": state.stages},
            indent=2,
            default=_serialize,
        ),
        encoding="utf-8",
    )


def update_stage(
    state: PipelineState,
    name: str,
    *,
    status: StageStatus | None = None,
    started_at: datetime | None = None,
    completed_at: datetime | None = None,
    outputs: list[str] | None = None,
    error: str | None = None,
) -> PipelineState:
    existing = state.stages.get(name, {})
    merged = dict(existing)
    if status is not None:
        merged["status"] = status.value
    if started_at is not None:
        merged["started_at"] = started_at.isoformat()
    if completed_at is not None:
        merged["completed_at"] = completed_at.isoformat()
    if outputs is not None:
        merged["outputs"] = list(outputs)
    if error is not None:
        merged["error"] = error
    new_stages = dict(state.stages)
    new_stages[name] = merged
    return PipelineState(schema_version=state.schema_version, stages=new_stages)


def _serialize(obj: Any):
    if isinstance(obj, datetime):
        return obj.isoformat()
    raise TypeError(f"unserializable: {type(obj)}")
