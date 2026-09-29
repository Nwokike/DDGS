"""Load-more pins (plan D2): next page appended, deduped, page-aware."""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

SRC = Path(__file__).resolve().parents[1] / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))


def _result(url: str):
    from core.state import SearchResult

    return SearchResult(url=url, title=url, snippet="")


def test_load_more_appends_deduped_page():
    from app_controller import AppController
    from core.state import state

    class _Svc:
        calls: list = []

        async def search(self, search_type, query, ui=False):
            _Svc.calls.append((search_type, query, state.page))
            from core.state import SearchProgress

            return SearchProgress(
                query=query,
                search_type=search_type,
                results=[_result("https://b.example"), _result("https://c.example")],
                is_running=False,
            )

    state.current_query = "trains"
    state.page = 1
    state.last_results = {"text": [_result("https://a.example"), _result("https://b.example")]}
    from core.state import SearchProgress

    state.search_progress = SearchProgress(
        query="trains", search_type="text", results=list(state.last_results["text"])
    )
    ctrl = AppController.__new__(AppController)
    ctrl.search_service = _Svc()
    ctrl.page = None  # never used: no progress callbacks on the append path

    asyncio.run(ctrl.load_more_results())

    urls = [r.url for r in state.last_results["text"]]
    assert urls == ["https://a.example", "https://b.example", "https://c.example"]
    assert state.page == 2, "the tap bumps the page the service sends"
    assert _Svc.calls == [("text", "trains", 2)]
    assert state.search_progress.total_results == 3
    # untouched keys survive
    state.last_results = {}
    state.search_progress = None
