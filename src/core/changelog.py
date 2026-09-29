"""Bundled changelog shown by the version dialog when the app is up to
date - works fully offline. One entry per release; keep the entry for the
current app version (components.settings.version._APP_VERSION) in sync
when bumping (guarded by tests)."""

CHANGELOG: dict[str, str] = {
    "2.0.2": (
        "- Settings carries KTV's live version header: the status line "
        "reads “Update available · tap to view” the moment "
        "the feed has a newer build\n"
        "- Update notes bullet every change, like KTV Player and LM Router"
    ),
    "2.0.1": (
        "- Fix: the Assistant screen would not scroll and the composer "
        "slipped off the bottom on phones; the chat view fills the screen "
        "again\n"
        "- Fix: the header stays clear of the status bar and oversized "
        "pills scroll instead of clipping"
    ),
    "2.0.0": (
        "- Assistant: agentic chat that searches, reads and saves pages for you\n"
        "- Assistant credits: 50 a day free, 500 with Premium\n"
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
