"""BWC Clipper pipeline package — per-stage transcription orchestration."""

# Install compatibility shims before any stage module is imported. This
# ensures that ``from df.enhance import ...`` (which imports torchaudio
# internals) works against torchaudio >= 2.6 even though deepfilternet
# 0.5.6 references the removed ``torchaudio.backend.common`` path.
from engine import df_compat  # noqa: F401
