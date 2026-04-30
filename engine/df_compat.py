"""Compatibility shim for deepfilternet 0.5.6 + torchaudio >= 2.6.

deepfilternet 0.5.6 imports ``from torchaudio.backend.common import AudioMetaData``,
but ``torchaudio.backend.common`` was removed in torchaudio 2.6+ (``AudioMetaData``
moved to ``torchaudio.AudioMetaData`` and is now considered private).

This module synthesizes the missing ``torchaudio.backend.common`` submodule and
re-exports ``AudioMetaData`` from the new location so deepfilternet's import
chain succeeds. Must be imported BEFORE any ``from df.* import`` statement.

When deepfilternet ships a release that uses the new import path, this shim
becomes a no-op (``torchaudio.backend.common`` will exist natively) and can be
removed.
"""

from __future__ import annotations

import sys
import types


def _install_torchaudio_backend_shim() -> None:
    try:
        import torchaudio
    except ImportError:
        return

    # If the backend module already exists, the shim isn't needed.
    try:
        from torchaudio.backend import common  # noqa: F401
        return
    except ImportError:
        pass

    if not hasattr(torchaudio, "AudioMetaData"):
        # Nothing to forward — let deepfilternet's import fail with the
        # original ImportError so the user sees a clear signal.
        return

    backend_module = types.ModuleType("torchaudio.backend")
    common_module = types.ModuleType("torchaudio.backend.common")
    common_module.AudioMetaData = torchaudio.AudioMetaData
    backend_module.common = common_module

    sys.modules["torchaudio.backend"] = backend_module
    sys.modules["torchaudio.backend.common"] = common_module
    # Also bind on the torchaudio package object so ``import
    # torchaudio.backend`` resolves via attribute lookup.
    torchaudio.backend = backend_module


_install_torchaudio_backend_shim()
