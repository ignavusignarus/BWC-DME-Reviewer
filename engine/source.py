"""Per-source cache helpers for BWC Clipper.

A "source" is one media file inside the project folder. Each source gets a
cache subdirectory at ``<project>/.bwcclipper/<source-stem>/`` for transcripts,
extracted audio, waveforms, and other derived artifacts.
"""

from __future__ import annotations

import hashlib
from pathlib import Path

from engine.project import ensure_cache_dir


def source_cache_dir(project_folder: Path, source_path: Path) -> Path:
    """Ensure the per-source cache subdirectory exists; return its path.

    Cache subdir name is the source file's basename stem (no extension).
    Two sources with the same stem (e.g., ``video.mp4`` and ``video.MP3``)
    would collide; we don't guard against that today — the project's media
    file enumeration in M1 doesn't surface that case for any real folder
    we've seen, and stems are stable across runs.
    """
    project_cache = ensure_cache_dir(project_folder)
    sub = project_cache / source_path.stem
    sub.mkdir(exist_ok=True)
    return sub


def compute_source_sha256(source_path: Path, cache_dir: Path) -> str:
    """Compute (or read cached) SHA-256 hex digest of ``source_path``.

    The digest is cached as plain text in ``<cache_dir>/source.sha256``. If
    that file exists, it's returned verbatim — the caller is responsible for
    deciding when the cache is stale (e.g., on source-file mtime change).
    """
    cache_file = cache_dir / "source.sha256"
    if cache_file.is_file():
        return cache_file.read_text(encoding="utf-8").strip()

    h = hashlib.sha256()
    with source_path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    digest = h.hexdigest()
    cache_file.write_text(digest, encoding="utf-8")
    return digest
