"""Tests for engine.version."""
from engine.version import BWC_CLIPPER_VERSION, get_version


def test_version_constant_is_string():
    assert isinstance(BWC_CLIPPER_VERSION, str)
    assert len(BWC_CLIPPER_VERSION) > 0


def test_version_constant_has_year_dot_format():
    """Version is a calver-ish string starting with the year (e.g., 2026.04.29a)."""
    parts = BWC_CLIPPER_VERSION.split(".")
    assert len(parts) >= 2
    assert parts[0].isdigit()
    assert int(parts[0]) >= 2026


def test_get_version_returns_constant():
    assert get_version() == BWC_CLIPPER_VERSION
