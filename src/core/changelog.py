"""Bundled changelog shown by the version dialog when the app is up to
date - works fully offline. One entry per release; keep the entry for the
current app version (components.settings.version._APP_VERSION) in sync
when bumping (guarded by tests)."""

CHANGELOG: dict[str, str] = {
    "2.2.1": (
        "- Searches that come back with zero or few results now "
        "automatically retry once with every provider: rate-limited and "
        "challenge-blocked sources get a second chance instead of showing "
        "you an empty page\n"
        "- The content reader header is back to its original shape and no "
        "longer slides under the status bar, with the page's real name and "
        "URL in it, the action buttons on their own row and the format "
        "chips on the next\n"
        "- Search filters are tiny pills, always visible under the search "
        "bar and centered, in Settings too - no rectangle dropdowns "
        "anywhere\n"
        "- Safe search defaults to off\n"
        "- Load more shows a spinner while the next page loads and keeps "
        "your results on screen\n"
        "- Opening a site goes straight to the full reader: the detail "
        "sheet stays the one half screen, and AI summaries are cached per "
        "page so reopening never re-runs them\n"
        "- The model picker is a real dropdown with hints and Refresh, and "
        "the Assistant resolves its model the moment you open it\n"
        "- The source picker reads the search library's live registry, so "
        "it can never offer a provider that no longer exists"
    ),
    "2.2.0": (
        "- The Assistant keeps working: the 6-call and 10-tool caps that "
        "cut deep research mid-task are gone (30 model rounds, 100 tool "
        "calls, 15 minutes per turn)\n"
        "- When every high and medium model is busy or failing, the "
        "Assistant now falls back to the lighter models instead of giving "
        "up, and it answers honestly when a search truly returns nothing\n"
        "- The model picker is a real dropdown with per-model hints and a "
        "Refresh row; opening the Assistant resolves the model by itself "
        "instead of waiting on a spinner\n"
        "- AI page summaries and search overviews are cached per page and "
        "per query: reopening the same page or rerunning the same search "
        "reuses the answer instead of paying for it again\n"
        "- The Assistant corrects its own malformed tool calls instead of "
        "burning every model on one bad JSON escape\n"
        "- Every format surface reads the same: the extract card, the "
        "fetch preview and the full reader share one swipeable chip bar, "
        "and the full reader finally scrolls\n"
        "- Search filters are tiny pills (the proot-distro design) on one "
        "scrollable track, not big rectangle dropdowns\n"
        "- Ads match CollabShell: an interstitial after every third "
        "Assistant reply and when opening the reader, always behind the "
        "60 second gap; a licence status refusal can no longer revoke a "
        "valid cached Premium\n"
        "- One branch: the Play edition is built from main by stamping the "
        "channel, which also blocks YouTube downloads there while the "
        "Assistant's own downloader stays unrestricted\n"
        "- Built on flet 1.1.2; the Google scraper engine "
        "(upstream removed it) is gone from the source picker; broken "
        "text searches no longer blame a DNS failure twice"
    ),
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
