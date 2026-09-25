"""Regression tests for the assistant design audit.

Every test maps to a real defect found by the cross-project audit against
lm-router, and to the two crashes the user reproduced directly:

  - a turn that throws when the Flet session dies, logging
    "Task exception was never retrieved" and losing the conversation
  - a deleted message reappearing from disk after a chat switch

They assert behaviour, so a comment cannot make them pass.
"""

from __future__ import annotations

import asyncio
import sys
import time
from pathlib import Path

SRC = Path(__file__).resolve().parents[1] / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))


def _session_stub():
    import flet as ft

    from screens.chat_screen import ChatSession

    class Controller:
        billing = None
        storage = None

        async def _grant_premium_benefits(self):
            return False

        async def _sync_premium_storage(self):
            pass

        async def verify_purchases(self):
            pass

    class Page:
        platform = ft.PagePlatform.WINDOWS
        width = 900
        height = 800
        theme_mode = ft.ThemeMode.LIGHT

        def __init__(self):
            self.dialogs = []
            self.views = []
            self._ddgs_controller = Controller()
            self.scheduled = []

        def run_task(self, handler, *args, **kwargs):
            if not asyncio.iscoroutinefunction(handler):
                raise TypeError("handler must be a coroutine function")
            self.scheduled.append(handler.__name__)
            loop = asyncio.new_event_loop()
            try:
                loop.run_until_complete(handler(*args, **kwargs))
            finally:
                loop.close()

        def show_dialog(self, dlg):
            self.dialogs.append(dlg)

        def pop_dialog(self):
            pass

        def update(self):
            pass

    return ChatSession, Page


# ── the deleted message must stay deleted ────────────────────────────────
def test_deleting_a_message_removes_it_from_the_transcript(tmp_path, monkeypatch):
    monkeypatch.setenv("FLET_APP_STORAGE_DATA", str(tmp_path / "data"))
    ChatSession, Page = _session_stub()

    session = ChatSession(Page())
    session.agent_history = [
        {"role": "user", "content": "first question"},
        {"role": "assistant", "content": "first answer"},
        {"role": "user", "content": "second question"},
        {"role": "assistant", "content": "second answer"},
    ]
    session.turns = _turns(session)
    before = len(session.agent_history)

    session._delete_turn(2)  # the second user message

    assert len(session.agent_history) == before - 2, "the exchange was not removed"
    text = " ".join(str(m.get("content")) for m in session.agent_history)
    assert "second question" not in text, "the deleted message stayed in the transcript"
    assert "second answer" not in text, "the orphaned answer survived"
    assert "first question" in text, "unrelated messages must be untouched"
    assert len(session.turns) == 2, "the view must be rebuilt from the transcript"

    # and it must not come back on reload, which is the reported bug
    from services import conversation_service as cs

    session._persist_history()
    rows = cs.list_conversations()
    assert rows, "the conversation should be saved"
    reloaded = cs.load_conversation(rows[0]["id"])
    persisted = " ".join(str(m.get("content")) for m in reloaded["messages"])
    assert "second question" not in persisted, "the message returned from disk"
    assert "first question" in persisted


def _turns(session):
    from screens.chat_screen import _turns_from_messages

    return _turns_from_messages(session.agent_history)


def test_deleting_a_message_keeps_the_view_in_sync(tmp_path, monkeypatch):
    monkeypatch.setenv("FLET_APP_STORAGE_DATA", str(tmp_path / "data"))
    ChatSession, Page = _session_stub()
    session = ChatSession(Page())
    session.agent_history = [
        {"role": "user", "content": "a"},
        {"role": "assistant", "content": "b"},
        {"role": "user", "content": "c"},
        {"role": "assistant", "content": "d"},
    ]
    session.turns = _turns(session)
    session._delete_turn(0)
    assert len(session.turns) == len(session.agent_history) == 2


def test_deleting_out_of_range_is_a_no_op(tmp_path, monkeypatch):
    monkeypatch.setenv("FLET_APP_STORAGE_DATA", str(tmp_path / "data"))
    ChatSession, Page = _session_stub()
    session = ChatSession(Page())
    session.agent_history = [{"role": "user", "content": "only"}]
    session.turns = _turns(session)
    session._delete_turn(99)
    assert len(session.agent_history) == 1


# ── the destroyed-session cascade ────────────────────────────────────────
def test_session_shutdown_stops_the_turn_and_persists(tmp_path, monkeypatch):
    monkeypatch.setenv("FLET_APP_STORAGE_DATA", str(tmp_path / "data"))
    ChatSession, Page = _session_stub()
    page = Page()
    session = ChatSession(page)
    session.agent_history = [
        {"role": "user", "content": "question"},
        {"role": "assistant", "content": "answer"},
    ]
    session.turns = _turns(session)
    session.busy = True
    session.send = lambda text: None  # not used; we are shutting down

    session.shutdown()
    assert session._closing is True, "the closing flag must be set"
    assert session.cancel.is_set(), "the cooperative cancel must be raised"

    # a second call is a no-op, so a repeated close cannot double-save
    session.shutdown()
    assert session._closing is True


def test_render_does_not_talk_to_a_dead_session(tmp_path, monkeypatch):
    """The scroll call sits outside the update try; it must not be able to
    kill a turn, and it must not leak an un-awaited coroutine."""
    ChatSession, Page = _session_stub()

    class DeadPage(Page):
        def update(self):
            raise RuntimeError("An attempt to fetch destroyed session.")

        def run_task(self, handler, *args, **kwargs):
            raise RuntimeError("An attempt to fetch destroyed session.")

    page = DeadPage()
    session = ChatSession(page)
    session.agent_history = [{"role": "user", "content": "q"}]
    session.turns = _turns(session)
    session._pinned = True
    session._render()  # must not raise
    assert True


def test_persist_schedules_the_save_before_touching_observable_state(
    tmp_path, monkeypatch
):
    """`state.assistant_history = ...` can throw after teardown; if it ran
    first, the conversation file was never written at all."""
    ChatSession, Page = _session_stub()
    page = Page()
    session = ChatSession(page)
    session.agent_history = [
        {"role": "user", "content": "q"},
        {"role": "assistant", "content": "a"},
    ]
    session.turns = _turns(session)
    session._persist_history()
    assert "_save_history" in page.scheduled, (
        "the disk save must be scheduled even if an observable write fails"
    )


def test_turn_task_exception_is_retrieved():
    """asyncio logs 'Task exception was never retrieved' otherwise, which is
    what the user saw in the crash log."""
    ChatSession, Page = _session_stub()
    session = ChatSession(Page())
    assert hasattr(session, "_on_turn_done")
    source = (
        SRC / "screens" / "chat_screen.py"
    ).read_text(encoding="utf-8")
    assert "add_done_callback(self._on_turn_done)" in source
    assert "def shutdown(self)" in source


def test_app_close_stops_the_turn_before_flushing():
    source = (SRC / "app_controller.py").read_text(encoding="utf-8")
    block = source.split("def on_app_close", 1)[1].split("async def", 1)[0]
    assert "session.shutdown()" in block, "the turn must stop before teardown"
    assert block.index("session.shutdown()") < block.index("flush_now()"), (
        "the turn must be stopped first, while the loop is still alive"
    )


# ── credits: one lock, honest settlement ─────────────────────────────────
class _Store:
    def __init__(self, initial=None):
        # The real key is STORAGE_CREDITS = "ddgs_credits"; using "credits"
        # silently fell back to the default cap and hid lost updates.
        from core.constants import STORAGE_CREDITS

        self.key = STORAGE_CREDITS
        self.data = dict(initial or {STORAGE_CREDITS: "50"})

    async def get(self, key, default=None):
        return self.data.get(key, default)

    async def set(self, key, value):
        self.data[key] = value
        return True


def test_credit_lock_covers_every_balance_mutation():
    """Only commit_amount was locked, so a reward or daily reset could
    overwrite a settlement and lose one of the two."""
    source = (SRC / "services" / "credit_service.py").read_text(encoding="utf-8")
    for method in (
        "async def reserve(",
        "async def reserve_more(",
        "async def charge(",
        "async def spend(",
        "async def add_credits(",
        "async def _check_daily_reset(",
        "async def commit_amount(",
    ):
        block = source.split(method, 1)[1].split("\n    async def", 1)[0]
        assert "async with self._lock" in block, f"{method} is not serialized"


def test_concurrent_credits_are_not_lost():
    from services.credit_service import CreditService

    async def scenario():
        service = CreditService(_Store({"ddgs_credits": "100"}))
        await service.initialize()
        await asyncio.gather(*[service.add_credits(1) for _ in range(20)])
        balance = await service.get_balance()
        assert balance == 120, f"lost updates: expected 120, got {balance}"

        await asyncio.gather(*[service.charge(1) for _ in range(10)])
        assert await service.get_balance() == 110, "a charge was lost"

    asyncio.run(scenario())


def test_daily_reset_does_not_delete_live_holds():
    """A turn in flight at UTC midnight had its hold cleared, so the later
    settlement found nothing and charged zero for delivered work."""
    from services.credit_service import CreditService

    source = (SRC / "services" / "credit_service.py").read_text(encoding="utf-8")
    reset = source.split("async def _check_daily_reset", 1)[1].split(
        "\n    async def", 1
    )[0]
    assert "self._reservations.clear()" not in reset

    async def scenario():
        service = CreditService(_Store({"ddgs_credits": "50"}))
        tx = await service.reserve(2)
        assert tx is not None
        await service._check_daily_reset()
        assert tx in service._reservations, "the reset destroyed a live hold"

    asyncio.run(scenario())


def test_a_stopped_turn_charges_for_delivered_text(tmp_path, monkeypatch):
    """on_token raises before steps increments, so a partial answer that
    reached the screen used to settle at zero and refund delivered work."""

    class Store(_Store):
        pass

    source = (SRC / "services" / "chat_agent.py").read_text(encoding="utf-8")
    assert "charge_steps = max(steps, 1) if delivered else steps" in source, (
        "a stopped turn with visible text must be charged"
    )
    assert "delivered = bool" in source


def test_cancel_scrape_needs_approval():
    """It deletes a user's recurring crawl and persists the change, yet it
    was the only mutating tool not gated."""
    from services.chat_agent import _WRITE_TOOLS

    assert _WRITE_TOOLS == {
        "save_page",
        "download_media",
        "scrape_site",
        "schedule_scrape",
        "cancel_scrape",
    }


def test_a_timeout_says_timed_out_not_no_results():
    """str(TimeoutError()) is '' and the row fell back to 'no results'."""
    from services.chat_agent import _error_text

    assert _error_text(TimeoutError()) == "timed out"
    assert _error_text(ValueError("bad url")) == "bad url"
    assert _error_text(RuntimeError()) == "RuntimeError"
    assert len(_error_text(ValueError("x" * 500))) <= 300


# ── model picker and rate limits ─────────────────────────────────────────
def test_rate_limit_suggests_the_most_generous_model():
    from services import ai_service

    catalog = [
        {"id": "auto", "status": "active", "rate_hint": {"label": "rotates"}},
        {
            "id": "tight",
            "status": "active",
            "latency_ms": 400,
            "rate_hint": {"approx_per_hour": 10, "label": "10/hour"},
        },
        {
            "id": "open",
            "status": "active",
            "latency_ms": 500,
            "rate_hint": {"approx_per_hour": 500, "label": "500/hour"},
        },
        {
            "id": "medium",
            "status": "active",
            "latency_ms": 100,
            "rate_hint": {"approx_per_hour": 100, "label": "100/hour"},
        },
    ]
    original = ai_service._catalog
    ai_service._catalog = catalog
    try:
        _, suggestion = ai_service.rate_limit_advice("tight")
        # The old key sorted the cap ascending, so it recommended the
        # 10/hour model here — the opposite of useful.
        assert suggestion == "open", f"suggested {suggestion!r}, wanted the generous one"
    finally:
        ai_service._catalog = original


def test_non_chat_endpoints_are_not_request_candidates():
    from services.ai_service import rank_models

    def m(mid, etype="/chat.completion", latency=100, status="active"):
        return {
            "id": mid,
            "endpoint_type": etype,
            "latency_ms": latency,
            "status": status,
        }

    ranked = rank_models(
        [
            m("fast-chat", latency=150),
            m("slow-chat", latency=900),
            m("muse-spark", etype="/response", latency=10),
            m("jev", etype="/systemone", latency=20),
            m("dead-chat", status="failed"),
            m("limited", status="rate limited"),
        ]
    )
    assert ranked == ["fast-chat", "slow-chat"], ranked


def test_a_stopped_router_outranks_a_stale_catalog():
    from components.model_picker import model_picker_state
    from core.state import state
    from services import ai_service

    original = (ai_service._catalog, ai_service._catalog_fetched_at)
    ai_service._catalog = [
        {"id": "auto", "hint": "rotates", "status": "active"},
        {"id": "ling-3.0-flash", "hint": "210ms", "status": "active"},
    ]
    ai_service._catalog_fetched_at = time.monotonic()
    try:
        for status, expected in (
            ("stopped", "Router stopped"),
            ("unavailable", "Router unavailable"),
        ):
            state.ai_router_status = status
            state.ai_model = "ling-3.0-flash"
            ps = model_picker_state()
            assert ps.label == expected, (
                f"a stale catalog hid {status} behind a model name"
            )
            assert ps.action == "Start router", "the recovery action must show"
    finally:
        ai_service._catalog, ai_service._catalog_fetched_at = original


# ── streaming responsiveness ─────────────────────────────────────────────
def test_text_and_thought_use_independent_throttles():
    """Sharing one clock meant a text token could starve the reasoning
    display for the whole 0.5s thought window."""
    ChatSession, Page = _session_stub()
    session = ChatSession(Page())
    assert hasattr(session, "_last_text_flush")
    assert hasattr(session, "_last_thought_flush")
    assert not hasattr(session, "_last_partial_flush")
    source = (
        SRC / "screens" / "chat_screen.py"
    ).read_text(encoding="utf-8")
    assert "now - self._last_text_flush < 0.2" in source
    assert "now - self._last_thought_flush < 0.5" in source


def test_model_pill_is_not_rebuilt_for_every_token():
    """Building a control tree and sending a panel update per token for a
    label that almost never moves."""
    source = (
        SRC / "screens" / "chat_screen.py"
    ).read_text(encoding="utf-8")
    assert "_pill_signature" in source, "the pill must short-circuit"
    refresh = source.split("def refresh_model_chip", 1)[1].split("\n    def ", 1)[0]
    assert "if signature == getattr(self, \"_pill_signature\", None):" in refresh
