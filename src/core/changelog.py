"""Bundled changelog shown by the version dialog when the app is up to
date - works fully offline. One entry per release; keep the entry for the
current app version (components.settings.version._APP_VERSION) in sync
when bumping (guarded by tests)."""

CHANGELOG: dict[str, str] = {
    "2.1.0": (
        "- The Assistant now runs on the kani agent engine: same tools, "
        "same approval gate, a real agent loop, and the Thinking block "
        "shows reasoning again\n"
        "- The Kiri router is the only AI source - the gateway fallback "
        "and the hand-rolled stream parsing are gone\n"
        "- Every paid reply reports its exact token count beside steps "
        "and credits\n"
        "- Thinking depth: Auto / Fast / Deep in Settings; Auto leaves it "
        "to the model, and the system prompt and tools ride a warm "
        "prompt cache\n"
        "- Chats export and import as .kani archives from the chat list\n"
        "- Undo on every delete: chats, messages and search history\n"
        "- Long-press or right-click any result for open, copy link and "
        "share; image previews pinch-zoom and carry a QR for your phone\n"
        "- Load more: results no longer stop at twenty\n"
        "- Your proxy now covers downloads, updates and license checks, "
        "not just search\n"
        "- Crawl schedules gain an interval editor; finished saves buzz "
        "and share on mobile\n"
        "- Desktop: Esc closes dialogs, Ctrl+K jumps to search; the "
        "Android splash matches the app's surfaces\n"
        "- Fixes: notification bars (with Undo) can no longer stay on "
        "screen and block every tap; foreign URL schemes blocked; "
        "punycode hosts read as real names; YouTube parsing can no longer "
        "hang on backtracking"
    ),
    "2.0.2": (
        "- Settings carries KTV's live version header: the status line "
        "reads “Update available · tap to view” the moment "
        "the feed has a newer build\n"
        "- Update notes bullet every change, like KTV Player"
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
