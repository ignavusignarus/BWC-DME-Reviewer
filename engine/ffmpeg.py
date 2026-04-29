"""ffmpeg / ffprobe binary discovery and subprocess wrappers.

The Electron main process downloads ffmpeg.exe and ffprobe.exe to a per-user
directory and passes the path to the engine via the BWC_CLIPPER_FFMPEG_DIR
environment variable. If that variable is not set (e.g., when running tests
or when the user has system ffmpeg installed), fall back to searching PATH.
"""

from __future__ import annotations

import os
import shutil
from pathlib import Path

FFMPEG_BINARY = "ffmpeg.exe" if os.name == "nt" else "ffmpeg"
FFPROBE_BINARY = "ffprobe.exe" if os.name == "nt" else "ffprobe"


def _find_binary(name: str) -> Path:
    bundled_dir = os.environ.get("BWC_CLIPPER_FFMPEG_DIR")
    if bundled_dir:
        candidate = Path(bundled_dir) / name
        if candidate.is_file():
            return candidate
    on_path = shutil.which(name)
    if on_path:
        return Path(on_path)
    raise FileNotFoundError(
        f"{name} not found — checked BWC_CLIPPER_FFMPEG_DIR={bundled_dir!r} and system PATH"
    )


def find_ffmpeg() -> Path:
    return _find_binary(FFMPEG_BINARY)


def find_ffprobe() -> Path:
    return _find_binary(FFPROBE_BINARY)


import subprocess


def run_ffmpeg(args: list[str], *, timeout: float | None = None) -> str:
    """Run ffmpeg with the given arguments. Returns captured stdout.

    Raises:
        RuntimeError: ffmpeg exited non-zero. The exception message includes
            the captured stderr.
    """
    binary = find_ffmpeg()
    try:
        result = subprocess.run(
            [str(binary), *args],
            check=True,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        return result.stdout
    except subprocess.CalledProcessError as exc:
        raise RuntimeError(f"ffmpeg failed (exit {exc.returncode}): {exc.stderr}") from exc


def run_ffprobe(args: list[str], *, timeout: float | None = None) -> str:
    """Run ffprobe with the given arguments. Returns captured stdout."""
    binary = find_ffprobe()
    try:
        result = subprocess.run(
            [str(binary), *args],
            check=True,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        return result.stdout
    except subprocess.CalledProcessError as exc:
        raise RuntimeError(f"ffprobe failed (exit {exc.returncode}): {exc.stderr}") from exc
