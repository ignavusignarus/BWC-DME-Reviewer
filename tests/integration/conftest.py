"""Shared fixtures for ML pipeline integration tests.

These tests run real models on real audio and require:
- The ML runtime deps installed (deepfilternet, silero-vad, faster-whisper, whisperx)
- A short sample WAV at ``tests/fixtures/integration/sample_short.wav``
  (16 kHz mono PCM, ~10-30 seconds of speech). Sliced from the user's
  Samples/DME Audio/ folder via ffmpeg; NOT committed (case-audio
  privacy). Regenerate via:

      ffmpeg -y -ss 60 -t 15 \\
          -i "Samples/DME Audio/<some>.MP3" \\
          -ac 1 -ar 16000 -c:a pcm_s16le \\
          tests/fixtures/integration/sample_short.wav

Tests skip with a clear message if the fixture is missing.
"""
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
FIXTURE_PATH = REPO_ROOT / "tests" / "fixtures" / "integration" / "sample_short.wav"


@pytest.fixture(scope="session")
def sample_short_wav() -> Path:
    if not FIXTURE_PATH.is_file():
        pytest.skip(
            f"Integration fixture missing: {FIXTURE_PATH}. "
            f"See tests/integration/conftest.py for regeneration instructions."
        )
    return FIXTURE_PATH
