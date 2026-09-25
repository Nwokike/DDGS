"""Regression tests for the assistant defects found in the reference audit.

Each test here corresponds to a real user-visible bug, so a future change
that reintroduces the behaviour fails here rather than in someone's chat:

  - Settings hardcoded its price copy instead of reading COST_STEP, so the
    number on screen and the number charged could disagree
  - every completed turn truncated the stored transcript to 16 messages,
    making the 400-message cap dead code
  - deleting the active chat left its turns on screen, because the
    replacement id was assigned before switch_conversation's same-id guard
  - a rate limit surfaced as a generic "unavailable" with no next step
  - an answer-less turn was charged, and it was reported as unavailable
  - "Start router" was a no-op against a stale port
  - every "no results" hid the real tool failure
"""

from __future__ import annotations

import asyncio
import re
import sys
from pathlib import Path

SRC = Path(__file__).resolve().parents[1] / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))


# ── pricing copy must never drift from the constant ──────────────────────
def test_settings_price_copy_matches_cost_step():
    from core.constants import COST_STEP
    from core.state import state

    state.is_premium = False
    state.credits_remaining = 10
    state.ai_router_status = "ready"
    state.ai_model = "auto"
    state.scheduled_scrapes = []
    state.license_recovery_id = ""

    import flet as ft

    from components.settings.sections_ai import build_ai_section

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
        width = 390
        theme_mode = ft.ThemeMode.LIGHT
        _ddgs_controller = Controller()

        def run_task(self, handler, *a, **k):
            pass

        def show_dialog(self, dlg):
            pass

        def update(self):
            pass

    async def _save(key, value):
        pass

    card = build_ai_section(Page(), _save)
    texts: list[str] = []

    def walk(control):
        if isinstance(control, ft.Text) and control.value:
            texts.append(str(control.value))
        for attr in ("controls",):
            for child in getattr(control, attr, None) or []:
                walk(child)
        content = getattr(control, "content", None)
        if content is not None:
            walk(content)

    walk(card)
    blob = " ".join(texts)
    # Every credit figure on the page must be a number the code actually
    # charges. Asserted as a set of figures rather than one literal, so the
    # test holds at any value of COST_STEP instead of pinning the copy to
    # today's price.
    from core.constants import (
        DAILY_FREE_CREDITS,
        PREMIUM_DAILY_CREDITS,
        credit_word,
    )

    figures = set(re.findall(r"\b\d+\s+credits?\b", blob))
    assert credit_word(COST_STEP) in figures, (
        "the cost row must state the real per-step price from COST_STEP"
    )
    allowed = {
        credit_word(COST_STEP),
        credit_word(DAILY_FREE_CREDITS),
        credit_word(PREMIUM_DAILY_CREDITS),
    }
    drifted = sorted(figures - allowed)
    assert not drifted, f"price copy drifted from the constants: {drifted}"


def test_wallet_price_row_uses_cost_step():
    from core.constants import COST_STEP

    source = (SRC / "components" / "wallet.py").read_text(encoding="utf-8")
    assert "COST_STEP" in source
    assert "credit_word(COST_STEP)" in source, (
        "the wallet must pluralise from the constant, not from a literal"
    )
    assert COST_STEP >= 1


def test_credit_word_is_singular_only_at_one():
    """The old copy said "2 credit" at one price and would say
    "1 credits" at the other; both are now impossible."""
    from core.constants import credit_word

    assert credit_word(1) == "1 credit"
    assert credit_word(2) == "2 credits"
    assert credit_word(50) == "50 credits"


# ── transcript retention ─────────────────────────────────────────────────
def test_completed_turn_does_not_truncate_to_sixteen_messages():
    """The [-16:] slice silently deleted the user's own history."""
    source = (SRC / "screens" / "chat_screen.py").read_text(encoding="utf-8")
    assert ")[-16:]" not in source, (
        "a completed turn must not slice the stored transcript down to 16 messages"
    )
    from services.conversation_service import CONVERSATION_MESSAGE_CAP

    assert CONVERSATION_MESSAGE_CAP >= 100, "the stored transcript cap is too small"


def test_model_context_window_is_separate_from_storage():
    """The model sees a small window; the file keeps everything."""
    from core.constants import AGENT_HISTORY_MESSAGES
    from services.conversation_service import CONVERSATION_MESSAGE_CAP

    assert AGENT_HISTORY_MESSAGES < CONVERSATION_MESSAGE_CAP, (
        "the context window and the stored transcript are different limits"
    )


# ── conversation switching and deletion ───────────────────────────────────
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
        width = 390
        theme_mode = ft.ThemeMode.LIGHT

        def __init__(self):
            self.dialogs = []
            self.views = []
            self._ddgs_controller = Controller()

        def run_task(self, handler, *a, **k):
            loop = asyncio.new_event_loop()
            try:
                loop.run_until_complete(handler(*a, **k))
            finally:
                loop.close()

        def show_dialog(self, dlg):
            self.dialogs.append(dlg)

        def pop_dialog(self):
            pass

        def update(self):
            pass

    return ChatSession, Page


def test_deleting_the_active_chat_loads_its_replacement(tmp_path, monkeypatch):
    """The deleted chat's turns must not stay on screen."""
    monkeypatch.setenv("FLET_APP_STORAGE_DATA", str(tmp_path / "data"))
    ChatSession, Page = _session_stub()
    from services import conversation_service as cs

    page = Page()
    session = ChatSession(page)

    keep = cs.new_conversation_id()
    cs.save_conversation(
        keep,
        [
            {"role": "user", "content": "survivor question"},
            {"role": "assistant", "content": "survivor answer"},
        ],
    )
    doomed = cs.new_conversation_id()
    cs.save_conversation(
        doomed,
        [
            {"role": "user", "content": "doomed question"},
            {"role": "assistant", "content": "doomed answer"},
        ],
    )
    session.switch_conversation(doomed)
    assert any("doomed question" in str(t.get("text")) for t in session.turns)

    session.delete_conversation(doomed)

    rendered = " ".join(str(t.get("text") or "") for t in session.turns)
    assert "doomed question" not in rendered, (
        "the deleted conversation is still on screen"
    )
    assert session.conversation_id != doomed


def test_history_sheet_lists_every_saved_chat(tmp_path, monkeypatch):
    """A truncated list means stored chats are unreachable."""
    monkeypatch.setenv("FLET_APP_STORAGE_DATA", str(tmp_path / "data"))
    from services import conversation_service as cs

    for i in range(15):
        cs.save_conversation(
            cs.new_conversation_id(), [{"role": "user", "content": f"q{i}"}]
        )
    assert len(cs.list_conversations()) == 15
    source = (SRC / "screens" / "chat_screen.py").read_text(encoding="utf-8")
    assert "rows[:12]" not in source, "the history sheet must not cap the list at 12"


# ── rate limiting ────────────────────────────────────────────────────────
def test_rate_limit_advice_names_an_uncapped_model():
    from services import ai_service

    catalog = [
        {
            "id": "auto",
            "status": "active",
            "latency_ms": None,
            "rate_hint": {"tier": "variable", "label": "Free tier, rotates"},
        },
        {
            "id": "capped-model",
            "status": "active",
            "latency_ms": 400,
            "rate_hint": {"tier": "light", "approx_per_hour": 10, "label": "10/hour"},
        },
        {
            "id": "open-model",
            "status": "active",
            "latency_ms": 300,
            "rate_hint": {"tier": "wide", "approx_per_hour": 500, "label": "500/hour"},
        },
    ]
    original = ai_service._catalog
    ai_service._catalog = catalog
    try:
        message, suggestion = ai_service.rate_limit_advice("capped-model")
        assert suggestion == "open-model", "should point at the uncapped model"
        assert "open-model" in message
        # auto must not suggest a model that is itself capped
        ai_service._catalog = [
            {**c, "status": "rate limited"} if c["id"] != "open-model" else c
            for c in catalog
        ]
        _auto_message, auto_suggestion = ai_service.rate_limit_advice("auto")
        assert auto_suggestion == "open-model", (
            "auto must skip models the catalog reports as rate limited"
        )
        # When literally nothing is healthy there is no next step to offer,
        # and the caller must not render a button for an empty suggestion.
        ai_service._catalog = [
            {**c, "status": "rate limited"} for c in catalog if c["id"] == "auto"
        ]
        message, none_left = ai_service.rate_limit_advice("auto")
        assert none_left == "", "a fully capped catalog has nothing to offer"
        assert "Try again shortly" in message
    finally:
        ai_service._catalog = original


def test_rate_limit_advice_without_a_catalog_still_answers():
    from services import ai_service

    original = ai_service._catalog
    ai_service._catalog = []
    try:
        message, suggestion = ai_service.rate_limit_advice("anything")
        assert message
        assert suggestion == ""
    finally:
        ai_service._catalog = original


def test_rate_limited_is_a_distinct_outcome():
    from services import ai_service

    assert issubclass(ai_service.AIRateLimited, Exception)
    assert not issubclass(ai_service.AIRateLimited, ai_service.AIUnavailable), (
        "a capped tier must not be reported as a broken backend"
    )


# ── an answer-less turn must not be charged ──────────────────────────────
def test_empty_answer_emits_an_unpaid_empty_state():
    source = (SRC / "services" / "chat_agent.py").read_text(encoding="utf-8")
    assert '"kind": "empty"' in source
    assert "empty model response" not in source, (
        "an empty answer must be its own state, not a generic failure"
    )
    # and it settles zero so the hold is released
    empty_block = source.split('"kind": "empty"')[0].rsplit("if not final_text.strip()", 1)
    assert "settle_turn(credits, tx, 0)" in empty_block[-1]


def test_settle_turn_zero_releases_the_hold():
    """Zero steps must roll the reservation back, not charge for it."""

    class FakeCredits:
        def __init__(self):
            self.calls = []

        async def get_balance(self):
            return 42

        async def rollback(self, tx):
            self.calls.append(("rollback", tx))

        async def commit_amount(self, tx, amount):
            self.calls.append(("commit", tx, amount))

        async def charge(self, amount):
            self.calls.append(("charge", amount))

    from services.chat_agent import settle_turn

    credits = FakeCredits()
    assert asyncio.run(settle_turn(credits, "tx-1", 0)) == 42
    assert credits.calls == [("rollback", "tx-1")]


def test_settle_turn_charges_two_per_step():
    from core.constants import COST_STEP
    from services.chat_agent import settle_turn

    class FakeCredits:
        def __init__(self):
            self.calls = []

        async def get_balance(self):
            return 10

        async def rollback(self, tx):
            self.calls.append(("rollback", tx))

        async def commit_amount(self, tx, amount):
            self.calls.append(("commit", tx, amount))

        async def charge(self, amount):
            self.calls.append(("charge", amount))

    credits = FakeCredits()
    asyncio.run(settle_turn(credits, "tx-2", 3))
    assert credits.calls == [("commit", "tx-2", 3 * COST_STEP)]


# ── router recovery ──────────────────────────────────────────────────────
def test_ensure_router_can_verify_a_stale_port():
    source = (SRC / "services" / "ai_service.py").read_text(encoding="utf-8")
    assert "def ensure_router(*, verify: bool = False)" in source
    picker = (SRC / "components" / "model_picker.py").read_text(encoding="utf-8")
    assert "ensure_router(verify=True)" in picker, (
        "Start router must verify, or a dead port is trusted forever"
    )


# ── tool failure detail ──────────────────────────────────────────────────
def test_tool_errors_are_not_flattened_to_no_results():
    source = (SRC / "screens" / "chat_screen.py").read_text(encoding="utf-8")
    # Strip comments so a mention in prose cannot fail this, but any
    # real use in code would still be caught.
    code = "".join(line.split("#", 1)[0] for line in source.splitlines())
    # "no results" is allowed only as the fallback when the tool gave no
    # detail; what must not happen is a real error being replaced by it.
    assert 'detail = "no results"' in code, "keep the empty-result fallback"
    assert 'if not detail' in code, "the fallback must be conditional"
    assert "row.get(\"error\") or \"\").strip()" in code, (
        "the tool's actual error must be read and shown"
    )


# ── minimising must not cancel work ──────────────────────────────────────
def test_minimize_does_not_cancel_the_turn():
    ChatSession, Page = _session_stub()
    source = (SRC / "screens" / "chat_screen.py").read_text(encoding="utf-8")
    close_block = source.split("    def close(self) -> None:")[1].split("    def restore")[0]
    assert "self.cancel.set()" not in close_block, (
        "minimising must not stop a turn the user is watching"
    )
    stop_block = source.split("    def stop(self) -> None:")[1].split("    async def")[0]
    assert "self.cancel.set()" in stop_block, "Stop must still signal the agent"
    assert "task.cancel()" in stop_block, "Stop must also cancel the task"
    assert ChatSession and Page  # import guard


def test_cancellation_settles_credits():
    """CancelledError is a BaseException; it must still settle the hold."""
    source = (SRC / "services" / "chat_agent.py").read_text(encoding="utf-8")
    assert "except asyncio.CancelledError:" in source
    tail = source.split("except asyncio.CancelledError:")[1]
    # The handler body ends where the next top-level except starts, not
    # where the word "except" appears inside its own comment.
    block = tail.split(chr(10) + "    except ")[0]
    assert "settle_turn(" in block, "a hard cancel must still settle the hold"
    assert "raise" in block, "the cancellation must still propagate"
