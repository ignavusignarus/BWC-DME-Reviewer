"""Per-project last-opened-source persistence for the reviewer view."""
from __future__ import annotations

import json
from pathlib import Path

REVIEWER_STATE_FILENAME = "reviewer-state.json"
_SUBDIR = ".bwcclipper"


def _state_path(folder: Path) -> Path:
    return folder / _SUBDIR / REVIEWER_STATE_FILENAME


def load_reviewer_state(folder: Path) -> dict:
    """Returns {'last_source': <str|None>}; missing-file returns the default."""
    path = _state_path(folder)
    if not path.is_file():
        return {"last_source": None}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            return {"last_source": None}
        return {"last_source": data.get("last_source")}
    except (OSError, json.JSONDecodeError):
        return {"last_source": None}


def save_reviewer_state(folder: Path, state: dict) -> None:
    """Writes {'last_source': ...}. Creates the .bwcclipper/ subdir if needed."""
    path = _state_path(folder)
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {"last_source": state.get("last_source")}
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
