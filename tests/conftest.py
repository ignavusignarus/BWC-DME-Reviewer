"""Shared pytest fixtures.

For Milestone 0 this is mostly empty — placeholder for the test suite to grow.
The running_server fixture lives in test_server.py because it's specific to
the server test module; if more tests need it, lift it here.
"""
import pytest


@pytest.fixture
def repo_root():
    """Absolute path to the repository root."""
    from pathlib import Path
    return Path(__file__).resolve().parent.parent
