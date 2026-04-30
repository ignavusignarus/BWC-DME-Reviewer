"""Device selection for ML pipeline stages.

Auto-detects CUDA availability at runtime. Can be overridden via the
``BWC_CLIPPER_FORCE_DEVICE`` environment variable (``cpu`` or ``cuda``)
for testing or troubleshooting.
"""

from __future__ import annotations

import os


def select_device() -> str:
    """Return ``"cuda"`` if CUDA is available, else ``"cpu"``.

    Honors the ``BWC_CLIPPER_FORCE_DEVICE`` env var if set.
    """
    forced = os.environ.get("BWC_CLIPPER_FORCE_DEVICE")
    if forced:
        return forced.strip().lower()
    try:
        import torch
        if torch.cuda.is_available():
            return "cuda"
    except ImportError:
        pass
    return "cpu"
