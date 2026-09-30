"""Every AI tool, tested offline (utilization-plan tool audit).

All 11 tools through `_dispatch` with stubbed services: no network, no
real disk writes. Pins the arguments that flow, the outputs the model
sees, the approval gate around the five write tools, the tool cap, and
the thinking-depth passthrough. The live twin is scripts/ai_probe.py,
which exercises these same paths against the real router and network.
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

SRC = Path(__file__).resolve().parents[1] / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from core.constants import TOOL_OUTPUT_CAP
from core.state import SearchResult


def _result(i: int = 0, **kw) -> SearchResult:
    base = dict(
        title=f"Result {i}",
        url=f"https://example.com/{i}",
        snippet=f"s{i} " * 60,
        search_type="text",
    )
    base.update(kw)
    return SearchResult(**base)


class _Progress:
    def __init__(self, results=None, error=None):
        self.results = results if results is not None else []
        self.error = error


class _Svc:
    """Stand-in SearchService: records calls, replays canned answers."""

    calls: list[tuple[str, dict]] = []
    answer: _Progress = _Progress()

    async def search(self, kind, query, ui=False):
        type(self).calls.append((kind, {"query": query, "ui": ui}))
        return type(self).answer

    async def extract_url(self, url, fmt="text_markdown", force=False):
        type(self).calls.append(("extract", {"url": url, "fmt": fmt}))
        return type(self).extract_answer, None


def _install(monkeypatch, progress: _Progress):
    from services import chat_agent

    _Svc.calls = []
    _Svc.answer = progress
    monkeypatch.setattr(chat_agent, "_svc", lambda: _Svc())
    return _Svc.calls


def test_search_web_flows_query_and_caps(monkeypatch):
    from services import chat_agent

    calls = _install(monkeypatch, _Progress([_result(i) for i in range(12)]))
    out, results = asyncio.run(
        chat_agent._dispatch("search_web", {"query": "rust news", "count": 99})
    )
    assert calls[0] == ("text", {"query": "rust news", "ui": False})
    # count clamps to the schema's ceiling of 8
    assert len(results) == 8 and len(out) == 8
    assert out[0]["title"] == "Result 0"
    # snippets are capped for the model (display-only slice)
    assert all(len(item["snippet"]) <= 300 for item in out)


def test_every_search_kind_routes_to_the_right_service(monkeypatch):
    from services import chat_agent

    for tool, kind in (
        ("search_web", "text"),
        ("search_images", "images"),
        ("search_videos", "videos"),
        ("search_news", "news"),
        ("search_books", "books"),
    ):
        calls = _install(monkeypatch, _Progress([_result(1)]))
        asyncio.run(chat_agent._dispatch(tool, {"query": "q"}))
        assert calls == [(kind, {"query": "q", "ui": False})], tool


def test_search_images_hands_the_model_a_direct_file(monkeypatch):
    from services import chat_agent

    _install(
        monkeypatch,
        _Progress(
            [
                _result(
                    1,
                    search_type="images",
                    image_url="https://cdn.example.com/full.jpg",
                    thumbnail="https://cdn.example.com/t.jpg",
                )
            ]
        ),
    )
    out, results = asyncio.run(chat_agent._dispatch("search_images", {"query": "cat"}))
    assert out[0]["image_url"] == "https://cdn.example.com/full.jpg"
    assert out[0]["url"] == "https://example.com/1"
    assert all(len(i["snippet"]) <= 80 for i in out)
    assert results, "the UI cards still need the SearchResult list"


def test_search_error_surfaces_to_the_model(monkeypatch):
    from services import chat_agent

    _install(monkeypatch, _Progress([], error="rate limited by engine"))
    try:
        asyncio.run(chat_agent._dispatch("search_news", {"query": "x"}))
        raise AssertionError("expected the error to raise")
    except RuntimeError as exc:
        assert "rate limited by engine" in str(exc)


def test_fetch_page_flows_url_fmt_and_cap(monkeypatch):
    from services import chat_agent

    calls = _install(monkeypatch, _Progress())
    _Svc.extract_answer = {"content": "x" * 9000, "url": "https://a.example/p"}
    out, results = asyncio.run(
        chat_agent._dispatch("fetch_page", {"url": "https://a.example/p"})
    )
    assert calls == [
        ("extract", {"url": "https://a.example/p", "fmt": "text_markdown"})
    ]
    assert results == []
    assert len(out["content"]) == TOOL_OUTPUT_CAP, "capped at the tool cap, not 3000"

    try:
        asyncio.run(chat_agent._dispatch("fetch_page", {"url": "ftp://x"}))
        raise AssertionError("non-http must be rejected")
    except ValueError:
        pass


def test_save_page_format_mapping_and_result(monkeypatch):
    from services import chat_agent

    seen: dict = {}

    async def fake_save(url, fmt="text_markdown"):
        seen["url"], seen["fmt"] = url, fmt
        return "/dl/DDGS/page.md"

    monkeypatch.setattr(chat_agent.agent_files, "save_page", fake_save)
    out, _ = asyncio.run(chat_agent._dispatch("save_page", {"url": "https://a.example"}))
    assert seen == {"url": "https://a.example", "fmt": "text_markdown"}
    assert out["saved_to"] == "/dl/DDGS/page.md"

    # format argument maps onto the extract fmt names the file layer knows
    asyncio.run(
        chat_agent._dispatch(
            "save_page", {"url": "https://a.example", "format": "html"}
        )
    )
    assert seen["fmt"] == "text"


def test_download_media_flows_quality(monkeypatch):
    from services import chat_agent

    seen: dict = {}

    async def fake_dl(url, quality="best"):
        seen["url"], seen["quality"] = url, quality
        return "/dl/DDGS/clip.mp4"

    monkeypatch.setattr(chat_agent.agent_files, "download_media", fake_dl)
    out, _ = asyncio.run(
        chat_agent._dispatch("download_media", {"url": "https://v.example/x", "quality": "720p"})
    )
    assert seen == {"url": "https://v.example/x", "quality": "720p"}
    assert out["saved_to"] == "/dl/DDGS/clip.mp4"


def test_scrape_site_flows_max_pages_and_format(monkeypatch):
    from services import chat_agent

    seen: dict = {}

    async def fake_scrape(url, max_pages=5, fmt="text_markdown", svc=None):
        seen.update(url=url, max_pages=max_pages, fmt=fmt)
        return {"saved": ["a.md"], "failed": []}

    monkeypatch.setattr(chat_agent.agent_files, "scrape_site", fake_scrape)
    out, _ = asyncio.run(
        chat_agent._dispatch("scrape_site", {"url": "https://a.example", "max_pages": 3})
    )
    assert seen == {
        "url": "https://a.example",
        "max_pages": 3,
        "fmt": "text_markdown",
    }
    assert out == {"saved": ["a.md"], "failed": []}

    # default when the model omits max_pages
    asyncio.run(chat_agent._dispatch("scrape_site", {"url": "https://a.example"}))
    assert seen["max_pages"] == 5


def test_schedule_scrape_clamps_and_replaces(monkeypatch):
    from core.state import state
    from services import chat_agent

    monkeypatch.setattr(chat_agent, "_persist_schedule", _noop_async)
    monkeypatch.setattr(state, "scheduled_scrapes", [])

    out, _ = asyncio.run(
        chat_agent._dispatch("schedule_scrape", {"url": "https://a.example/feed", "interval_minutes": 5})
    )
    entry = out["scheduled"]
    assert entry["interval_minutes"] == 15, "clamped to the schema floor"
    assert len(state.scheduled_scrapes) == 1

    # a huge interval clamps down, and the same URL replaces, not stacks
    out, _ = asyncio.run(
        chat_agent._dispatch(
            "schedule_scrape", {"url": "https://a.example/feed", "interval_minutes": 99999}
        )
    )
    assert out["scheduled"]["interval_minutes"] == 1440
    assert len(state.scheduled_scrapes) == 1, "same URL replaces its entry"

    # non-http is refused before any state change
    try:
        asyncio.run(chat_agent._dispatch("schedule_scrape", {"url": "javascript:alert(1)", "interval_minutes": 60}))
        raise AssertionError("non-http must be rejected")
    except ValueError:
        pass


def test_cancel_scrape_removes_and_reports(monkeypatch):
    from core.state import state
    from services import chat_agent

    monkeypatch.setattr(chat_agent, "_persist_schedule", _noop_async)
    monkeypatch.setattr(
        state,
        "scheduled_scrapes",
        [{"url": "https://a.example/feed", "interval_minutes": 60}],
    )

    out, _ = asyncio.run(chat_agent._dispatch("cancel_scrape", {"url": "https://a.example/feed"}))
    assert out["removed"] == 1
    assert state.scheduled_scrapes == []

    out, _ = asyncio.run(chat_agent._dispatch("cancel_scrape", {"url": "https://a.example/nope"}))
    assert out["removed"] == 0, "cancelling nothing says so"


def test_unknown_tool_raises_honestly():
    from services import chat_agent

    try:
        asyncio.run(chat_agent._dispatch("drop_database", {}))
        raise AssertionError("unknown tool must raise")
    except ValueError as exc:
        assert "unknown tool" in str(exc)


def _noop_async(*_a, **_k):
    return asyncio.sleep(0)


def test_thinking_depth_passthrough():
    from core.state import state
    from services.chat_agent import _thinking_depth

    old = state.reasoning_effort
    try:
        state.reasoning_effort = "auto"
        assert _thinking_depth() is None, "auto omits the parameter entirely"
        state.reasoning_effort = "low"
        assert _thinking_depth() == "low"
        state.reasoning_effort = "high"
        assert _thinking_depth() == "high"
        state.reasoning_effort = ""
        assert _thinking_depth() is None, "empty degrades to auto"
    finally:
        state.reasoning_effort = old


def test_build_tools_covers_all_eleven():
    from services.chat_agent import _WRITE_TOOLS, build_tools

    tools = {t["function"]["name"] for t in build_tools()}
    assert tools == {
        "search_web",
        "search_images",
        "search_videos",
        "search_news",
        "search_books",
        "fetch_page",
        "save_page",
        "download_media",
        "scrape_site",
        "schedule_scrape",
        "cancel_scrape",
    }
    # exactly the five mutating tools need approval
    assert _WRITE_TOOLS == {
        "save_page",
        "download_media",
        "scrape_site",
        "schedule_scrape",
        "cancel_scrape",
    }
    for t in build_tools():
        fn = t["function"]
        assert fn["parameters"]["type"] == "object"
        assert fn["parameters"]["additionalProperties"] is False
        assert fn["description"], f"{fn['name']} needs a description"
