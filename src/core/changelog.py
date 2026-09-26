"""Bundled changelog shown by the version dialog when the app is up to
date - works fully offline. One entry per release; keep the entry for the
current APP_VERSION in sync when bumping (guarded by tests)."""

CHANGELOG: dict[str, str] = {
    "2.0.0": (
        "- Assistant: agentic chat that searches, reads and saves pages for you\n"
        "- Assistant credits: 50 a day free, 200 with Premium\n"
        "- Premium unlocks itself after payment; the recovery ID is on "
        "your receipt\n"
        "- The Play Store build stays free-only with no purchase UI\n"
        "- Up to date dialog tells the truth, with this changelog\n"
        "- Video search fallback fixed"
    ),
    "1.2.1": ("- Maintenance release: build and CI updates"),
}


def notes_for(version: str) -> str:
    """Changelog entry for a version, falling back to the latest entry."""
    return CHANGELOG.get(version) or next(reversed(CHANGELOG.values()), "")
