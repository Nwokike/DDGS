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
    state.last_results = {
        "text": [_result("https://a.example"), _result("https://b.example")]
    }
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


def test_load_more_button_reaches_a_real_method_through_the_facade():
    """The 2.1.0 runtime bug: the button called controller.load_more_results
    but the ControllerMethods facade never exposed it, so every click was a
    guaranteed AttributeError. Source inspection missed it because the name
    exists on AppController - the wire between facade field, mount and
    caller must be asserted, not assumed."""
    facade_src = (SRC / "contexts" / "controller_ctx.py").read_text(encoding="utf-8")
    assert "load_more_results" in facade_src, "the facade must expose the method"

    from contexts.controller_ctx import ControllerMethods

    instance = ControllerMethods()
    assert callable(instance.load_more_results), (
        "the facade must carry the field with a callable default"
    )

    from app_controller import AppController

    assert callable(getattr(AppController, "load_more_results", None))

    mount_src = (SRC / "app_controller.py").read_text(encoding="utf-8")
    assert "load_more_results=self.load_more_results" in mount_src, (
        "the mount must hand the real method to the facade"
    )
    screen_src = (SRC / "screens" / "results_screen.py").read_text(encoding="utf-8")
    assert "controller.load_more_results" in screen_src, (
        "the button must call the facade attribute the mount actually wires"
    )
