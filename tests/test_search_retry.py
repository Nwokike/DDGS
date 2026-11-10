"""Few-result provider retry + registry-derived picker pins.

Root cause these lock in: providers answer per request - challenged pages
and 429s make a whole pass come back with a single result when only one
engine parsed. ddgs aggregates whatever parsed and has no retry, so the
app re-issues the SAME ddgs call once with every provider (a second
chance for the challenged engines), then merges deduped.
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

SRC = Path(__file__).resolve().parents[1] / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))


def _fresh_state():
    from core.state import state

    state.search_retry_enabled = True
    state.search_retry_min = 4
    state.backend = "auto"
    state.region = "wt-wt"
    state.safe_search = "moderate"
    state.max_results = 20
    state.page = 1
    state.timelimit = ""
    state.proxy = ""
    state.verify_ssl = True
    state.threads = 0
    for field in (
        "image_size",
        "image_color",
        "image_type",
        "image_layout",
        "image_license",
        "search_resolution",
        "search_duration",
        "search_license",
    ):
        setattr(state, field, "")
    return state


class _FakeDDGS:
    """Scripted raw-result pages; records every backend param it gets."""

    def __init__(self, pages: list[list[dict]]):
        self.pages = pages
        self.calls: list[dict] = []

    def text(self, query, **params):
        self.calls.append(dict(params))
        index = min(len(self.calls), len(self.pages)) - 1
        return self.pages[index]

    # search() builds the whole method map eagerly; unused categories no-op.
    def images(self, query, **params):
        return []

    def videos(self, query, **params):
        return []

    def news(self, query, **params):
        return []

    def books(self, query, **params):
        return []


def _service(fake) -> object:
    from services.search_service import SearchService

    svc = SearchService.__new__(SearchService)
    svc._ddgs = fake
    svc._ddgs_config_at_build = svc._ddgs_config()
    svc._generation = 0
    return svc


def test_few_results_retry_with_every_provider_and_merge_deduped():
    _fresh_state()
    fake = _FakeDDGS(
        [
            [{"title": "One", "href": "https://a.example", "body": "x"}],
            [
                {"title": "One", "href": "https://a.example", "body": "x"},
                {"title": "Two", "href": "https://b.example", "body": "y"},
            ],
        ]
    )
    progress = asyncio.run(_service(fake).search("text", "kiri labs", ui=False))

    assert len(fake.calls) == 2, "a 1-result pass must trigger exactly one retry"
    from ddgs.engines import ENGINES

    expected = ",".join(sorted(ENGINES["text"]))
    assert fake.calls[1]["backend"] == expected, (
        "the retry re-issues the same call with every registry provider"
    )
    urls = [r.url for r in progress.results]
    assert urls == ["https://a.example", "https://b.example"], (
        "the retry merges new results and drops the duplicate"
    )


def test_explicit_backend_outranks_the_retry():
    _fresh_state()
    from core.state import state

    state.backend = "duckduckgo"
    fake = _FakeDDGS(
        [[{"title": "One", "href": "https://a.example", "body": "x"}]]
    )
    progress = asyncio.run(_service(fake).search("text", "kiri labs", ui=False))

    assert len(fake.calls) == 1, "the user's explicit source choice is honored"
    assert fake.calls[0]["backend"] == "duckduckgo"
    assert len(progress.results) == 1


def test_retry_disabled_by_setting():
    _fresh_state()
    from core.state import state

    state.search_retry_enabled = False
    fake = _FakeDDGS(
        [[{"title": "One", "href": "https://a.example", "body": "x"}]]
    )
    asyncio.run(_service(fake).search("text", "kiri labs", ui=False))
    assert len(fake.calls) == 1, "the exposed switch must be able to stop the retry"


def test_backend_picker_is_derived_from_the_ddgs_registry():
    """No hand-mirrored provider list: whatever ddgs ships is what the
    picker offers, so registry churn (google's removal in 9.16.1) can
    never leave a stale option in the UI."""
    from core.constants import backend_options

    from ddgs.engines import ENGINES

    for category in ("text", "images", "news", "videos", "books"):
        keys = [o["key"] for o in backend_options(category)]
        assert keys[0] == "auto", "auto is ddgs's native default, always first"
        assert sorted(keys[1:]) == sorted(ENGINES.get(category, {})), (
            f"{category} picker must mirror the live registry exactly"
        )


def test_reader_header_names_the_page_not_a_hardcoded_label():
    """Owner ruling: the reader header shows the page's own name (seeded
    title, then <title> from the HTML, then the URL) and carries no app
    version chip."""
    reader = (SRC / "screens" / "content_reader_screen.py").read_text(
        encoding="utf-8"
    )
    assert "Content Reader" not in reader
    assert "_build_version_chip" not in reader
    assert "def _page_title(" in reader
    assert "title: str | None = None" in reader

    from screens.content_reader_screen import _page_title

    assert (
        _page_title("<html><head><title>Kiri Labs</title></head></html>", "https://x")
        == "Kiri Labs"
    )
    assert _page_title("# Markdown only", "https://x") == "https://x"
    assert _page_title(None, "https://x") == "https://x"


def test_load_more_flag_renders_a_spinner_and_keeps_results():
    state_src = (SRC / "core" / "state.py").read_text(encoding="utf-8")
    assert "load_more_running" in state_src
    controller_src = (SRC / "app_controller.py").read_text(encoding="utf-8")
    assert "state.load_more_running = True" in controller_src
    assert "state.load_more_running = False" in controller_src
    screen_src = (SRC / "screens" / "results_screen.py").read_text(encoding="utf-8")
    assert "load_more_running" in screen_src
    assert "ProgressRing" in screen_src
