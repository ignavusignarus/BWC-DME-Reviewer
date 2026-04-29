"""Tests for engine.source per-source cache helpers."""
import hashlib
from pathlib import Path

import pytest


def _touch(p: Path, content: bytes = b""):
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_bytes(content)


def test_source_cache_dir_creates_per_source_subdir(tmp_path: Path):
    from engine.source import source_cache_dir

    project = tmp_path
    source = project / "officer-garcia.mp4"
    _touch(source)

    cache = source_cache_dir(project, source)
    assert cache == project / ".bwcclipper" / "officer-garcia"
    assert cache.is_dir()


def test_source_cache_dir_idempotent(tmp_path: Path):
    from engine.source import source_cache_dir

    source = tmp_path / "x.mp4"
    _touch(source)
    a = source_cache_dir(tmp_path, source)
    b = source_cache_dir(tmp_path, source)
    assert a == b


def test_source_cache_dir_uses_basename_stem(tmp_path: Path):
    """Cache subdir is keyed by basename without extension."""
    from engine.source import source_cache_dir

    source = tmp_path / "subdir" / "doctor.MP3"
    _touch(source)
    cache = source_cache_dir(tmp_path, source)
    assert cache.name == "doctor"


def test_compute_source_sha256_returns_hex(tmp_path: Path):
    from engine.source import compute_source_sha256, source_cache_dir

    source = tmp_path / "x.mp4"
    _touch(source, b"hello world")
    cache = source_cache_dir(tmp_path, source)

    digest = compute_source_sha256(source, cache)
    expected = hashlib.sha256(b"hello world").hexdigest()
    assert digest == expected


def test_compute_source_sha256_caches_to_disk(tmp_path: Path):
    from engine.source import compute_source_sha256, source_cache_dir

    source = tmp_path / "x.mp4"
    _touch(source, b"abc")
    cache = source_cache_dir(tmp_path, source)
    digest = compute_source_sha256(source, cache)
    cached_file = cache / "source.sha256"
    assert cached_file.is_file()
    assert cached_file.read_text(encoding="utf-8").strip() == digest


def test_compute_source_sha256_uses_cache_if_present(tmp_path: Path):
    """If the cached hash matches the file's content, the cached value is returned
    without re-hashing. Trick: write the wrong digest and confirm it's returned."""
    from engine.source import compute_source_sha256, source_cache_dir

    source = tmp_path / "x.mp4"
    _touch(source, b"real-content")
    cache = source_cache_dir(tmp_path, source)
    # Inject a wrong-but-valid-looking cached digest
    (cache / "source.sha256").write_text("a" * 64, encoding="utf-8")

    # First call: returns cached "wrong" value because we don't verify
    # contents — caller is responsible for invalidating cache when source
    # changes (handled at a higher level, e.g., by file mtime check at the
    # project layer in a future milestone).
    assert compute_source_sha256(source, cache) == "a" * 64
