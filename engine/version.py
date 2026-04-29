"""Engine version. Bump on changes that invalidate the .bwcclipper/ cache schema."""

BWC_CLIPPER_VERSION = "2026.04.29b"


def get_version() -> str:
    return BWC_CLIPPER_VERSION
