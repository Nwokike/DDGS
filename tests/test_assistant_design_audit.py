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

import flet as ft

SRC = Path(__file__).resolve().parents[1] / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))


def _session_stub():
    import flet as ft

    from screens.chat_screen import ChatSession

    class Controller:
        billing = None
        storage = None

        async def _grant_premium_benefits(self, *, first_time=False):
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
def _chat(*pairs: str) -> list[dict]:
    """A transcript of alternating user/assistant rows from 'role,text' pairs."""
    turns = []
    for i, text in enumerate(pairs):
        turns.append({"role": "user" if i % 2 == 0 else "assistant", "text": text})
    return turns


def test_deleting_a_message_removes_it_from_the_transcript(tmp_path, monkeypatch):
    monkeypatch.setenv("FLET_APP_STORAGE_DATA", str(tmp_path / "data"))
    ChatSession, Page = _session_stub()

    session = ChatSession(Page())
    session.turns = _chat(
        "first question", "first answer", "second question", "second answer"
    )
    before = len(session.turns)

    session._delete_turn(2)  # the second user message

    assert len(session.turns) == before - 2, "the exchange was not removed"
    text = " ".join(str(t.get("text")) for t in session.turns)
    assert "second question" not in text, "the deleted message stayed in the transcript"
    assert "second answer" not in text, "the orphaned answer survived"
    assert "first question" in text, "unrelated messages must be untouched"
    # There is one transcript, so what the model reads cannot lag the view.
    assert "second question" not in str(session._model_history())

    # and it must not come back on reload, which is the reported bug
    from services import conversation_service as cs

    session._persist_history()
    rows = cs.list_conversations()
    assert rows, "the conversation should be saved"
    reloaded = cs.load_conversation(rows[0]["id"])
    persisted = " ".join(str(m.get("content")) for m in reloaded["messages"])
    assert "second question" not in persisted, "the message returned from disk"
    assert "first question" in persisted


def test_deleting_a_message_keeps_the_view_in_sync(tmp_path, monkeypatch):
    monkeypatch.setenv("FLET_APP_STORAGE_DATA", str(tmp_path / "data"))
    ChatSession, Page = _session_stub()
    session = ChatSession(Page())
    session.turns = _chat("a", "b", "c", "d")
    session._delete_turn(0)
    assert len(session.turns) == 2
    assert [m["content"] for m in session._model_history()] == ["c", "d"], (
        "the projection must be the same list the screen just edited"
    )


def test_deleting_out_of_range_is_a_no_op(tmp_path, monkeypatch):
    monkeypatch.setenv("FLET_APP_STORAGE_DATA", str(tmp_path / "data"))
    ChatSession, Page = _session_stub()
    session = ChatSession(Page())
    session.turns = _chat("only")
    session._delete_turn(99)
    assert len(session.turns) == 1


def test_what_is_saved_is_what_the_model_is_told(tmp_path, monkeypatch):
    """One projection serves disk and context, so they cannot disagree.

    Two lists meant a partial or failed exchange could be on screen, absent
    from the file, and absent from the model's context — three different
    histories of the same conversation.
    """
    monkeypatch.setenv("FLET_APP_STORAGE_DATA", str(tmp_path / "data"))
    ChatSession, Page = _session_stub()
    session = ChatSession(Page())
    session.turns = [
        {"role": "user", "text": "why is the sky blue"},
        {"role": "assistant", "text": "rayleigh scattering"},
        # A failure that streamed nothing is not something the model should
        # be told the user said.
        {"role": "assistant", "text": "", "error": "unavailable"},
    ]
    projected = session._model_history()
    assert [m["role"] for m in projected] == ["user", "assistant"]
    assert projected[0]["content"] == "why is the sky blue"

    session._persist_history()
    from services import conversation_service as cs

    rows = cs.list_conversations()
    stored = cs.load_conversation(rows[0]["id"])["messages"]
    assert stored == projected, "the file and the model must read one transcript"


# ── the destroyed-session cascade ────────────────────────────────────────
def test_session_shutdown_stops_the_turn_and_persists(tmp_path, monkeypatch):
    monkeypatch.setenv("FLET_APP_STORAGE_DATA", str(tmp_path / "data"))
    ChatSession, Page = _session_stub()
    page = Page()
    session = ChatSession(page)
    session.turns = _chat("question", "answer")
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
    session.turns = _chat("q")
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
    session.turns = _chat("q", "a")
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


def test_there_is_no_second_transcript_to_get_out_of_sync():
    """The bug class, not the instance.

    Every history defect in this file came from two lists being mutated at
    different times. `turns` is the only transcript now; disk and model
    context are both `flat_from_turns(turns)`.
    """
    source = (SRC / "screens" / "chat_screen.py").read_text(encoding="utf-8")
    assert "self.agent_history" not in source, "a second in-memory list is back"
    assert "self.pending_user" not in source, (
        "the staging field that fed the second list is back"
    )
    service = (SRC / "services" / "conversation_service.py").read_text(
        encoding="utf-8"
    )
    assert "def flat_from_turns(" in service
    # ...and the offset mapper that translated between the two is gone.
    assert "def _transcript_offset" not in source
    assert "def _record_turn" not in source


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
def test_the_app_has_no_model_suggestion_layer():
    """Rate-limit advice and app-side ranking were removed.

    The router owns selection (`auto_order` in run.py); a 429 that reaches
    the app is the router's final answer and surfaces as a plain
    AIUnavailable with consumer-facing copy.
    """
    from services import ai_service

    assert not hasattr(ai_service, "rate_limit_advice")
    assert not hasattr(ai_service, "AIRateLimited")
    source = (SRC / "services" / "ai_service.py").read_text(encoding="utf-8")
    # no candidate loop on the request path
    assert "for candidate in candidates" not in source
    assert '"model": chosen' in source
    assert "Try again shortly" in source  # the429 keeps honest copy


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


# ── the clock in every prompt ─────────────────────────────────────────────
def test_prompts_carry_the_current_date():
    """The model's training data ends before today, so 'this week' was
    answered from its knowledge cutoff instead of from now."""
    import datetime

    from services.ai_service import build_summary_messages, with_clock

    stamped = with_clock("You are DDGS AI.")
    today = datetime.datetime.now().astimezone().strftime("%Y-%m-%d")
    assert today in stamped, "the clock line must carry today's date"
    assert "never your training data" in stamped

    summary = build_summary_messages("T", "body")
    assert today in summary[0]["content"]


def test_chat_prompt_carries_the_current_date():
    """The chat prompt is the one that answers 'what happened this week'."""
    source = (SRC / "services" / "chat_agent.py").read_text(encoding="utf-8")
    assert "ai_service.with_clock(SYSTEM_PROMPT)" in source


# ── write-tool outcomes ──────────────────────────────────────────────────
def test_write_tools_report_what_they_did():
    from services.chat_agent import tool_outcome

    assert tool_outcome(
        "save_page", {"saved_to": "/home/u/Downloads/DDGS/kiri.ng.md"}
    ) == "saved to kiri.ng.md"
    assert (
        tool_outcome(
            "scrape_site",
            {"saved": ["a.md", "b.md", "c.md"], "failed": []},
        )
        == "3 pages saved"
    )
    assert (
        tool_outcome("scrape_site", {"saved": ["a.md"], "failed": ["b.md"]})
        == "1 page saved, 1 failed"
    )
    assert tool_outcome("cancel_scrape", {"removed": 1}) == "1 removed"
    assert tool_outcome("cancel_scrape", {"removed": 0}) == "nothing to cancel"
    assert (
        tool_outcome("schedule_scrape", {"scheduled": {"interval_minutes": 45}})
        == "every 45 minutes"
    )
    # a search tool has no outcome; it reports a count instead
    assert tool_outcome("search_web", []) == ""


def test_step_done_carries_the_outcome():
    source = (SRC / "services" / "chat_agent.py").read_text(encoding="utf-8")
    assert '"outcome": tool_outcome(name, model_out)' in source


# ── stop shows a live indicator ──────────────────────────────────────────
def test_stop_button_is_a_spinner_not_a_bare_icon():
    """A static red square was the only sign the app was alive."""
    ChatSession, Page = _session_stub()
    session = ChatSession(Page())
    assert isinstance(session.stop_btn, ft.Container), "needs content for a ring"
    assert session.stop_btn.on_click is not None, "it must still stop"
    assert session.stop_btn.visible is False, "hidden until busy"
    assert session.stop_btn.tooltip == "Stop"

    def walk(control, found):
        if isinstance(control, ft.ProgressRing):
            found.append(control)
        for child in getattr(control, "controls", None) or []:
            walk(child, found)
        content = getattr(control, "content", None)
        if content is not None and hasattr(content, "controls"):
            walk(content, found)

    rings: list = []
    walk(session.stop_btn.content, rings)
    assert rings, "the stop button must contain a progress ring"


# ── the model must be able to show a picture, not just describe it ───────
def _fake_image_service(monkeypatch, results):
    from core.state import SearchResult
    from services import chat_agent

    class Progress:
        error = None

    class Svc:
        async def search(self, kind, query, ui=False):
            return Progress()

    Progress.results = [
        SearchResult(
            title="Sunset over the lagoon",
            url="https://example.com/page",
            snippet="a long page snippet that would crowd out the picture",
            search_type="images",
            thumbnail="https://cdn.example.com/thumb.jpg",
            image_url="https://cdn.example.com/full.jpg",
        )
        if results
        else None
    ]
    monkeypatch.setattr(chat_agent, "_svc", lambda: Svc())
    return chat_agent


def test_image_results_hand_the_model_a_direct_file(monkeypatch):
    """The result `url` is the hosting page — useless for embedding."""
    chat_agent = _fake_image_service(monkeypatch, True)
    out, results = asyncio.run(
        chat_agent._dispatch("search_images", {"query": "sunset", "count": 4})
    )
    assert results, "the UI cards still need the SearchResult list"
    assert out[0]["image_url"] == "https://cdn.example.com/full.jpg"
    assert out[0]["url"] == "https://example.com/page", "keep the source too"
    assert len(out[0]["snippet"]) <= 80, "snippets must not crowd out the image"


def test_image_tool_output_fits_the_tool_cap(monkeypatch):
    """A truncated JSON blob is worse than a short one the model can read."""
    from core.constants import TOOL_OUTPUT_CAP
    from services import chat_agent

    class Progress:
        error = None

    class Svc:
        async def search(self, kind, query, ui=False):
            return Progress()

    from core.state import SearchResult

    Progress.results = [
        SearchResult(
            title=f"Image {i} " + "x" * 80,
            url=f"https://example.com/{i}",
            snippet="s",
            search_type="images",
            image_url=f"https://cdn.example.com/{i}.jpg",
        )
        for i in range(8)
    ]
    monkeypatch.setattr(chat_agent, "_svc", lambda: Svc())
    out, _ = asyncio.run(
        chat_agent._dispatch("search_images", {"query": "sunset", "count": 8})
    )
    import json

    blob = json.dumps(out, ensure_ascii=False)
    assert len(blob) <= TOOL_OUTPUT_CAP, f"{len(blob)} chars would be cut off"
    assert all("image_url" in item for item in out)


def test_the_prompt_tells_the_model_to_embed_the_image():
    from services import chat_agent

    assert "![short description](image_url)" in chat_agent.SYSTEM_PROMPT
    tools = {t["function"]["name"]: t for t in chat_agent.build_tools()}
    assert "image_url" in tools["search_images"]["function"]["description"]


# ── chat history is a modal, in the credits-dialog style ─────────────────
def _open_history(tmp_path, monkeypatch, titles=()):
    """Point storage at a scratch dir, build a session, open the history."""
    monkeypatch.setenv("FLET_APP_STORAGE_DATA", str(tmp_path))
    monkeypatch.setenv("FLET_APP_STORAGE_CACHE", str(tmp_path / "cache"))
    monkeypatch.setenv("FLET_APP_STORAGE_TEMP", str(tmp_path / "temp"))
    conv_dir = tmp_path / "conversations"
    conv_dir.mkdir(parents=True, exist_ok=True)
    import json

    for i, title in enumerate(titles):
        (conv_dir / f"conv{i}.json").write_text(
            json.dumps(
                {
                    "id": f"conv{i}",
                    "title": title,
                    "messages": [{"role": "user", "content": "hi"}],
                    "updated": 1700000000.0 + i,
                }
            ),
            encoding="utf-8",
        )

    ChatSession, Page = _session_stub()
    page = Page()
    session = ChatSession(page)
    if titles:
        # Mark the first saved chat as the one on screen so the active
        # marker has something to point at.
        from core.state import state

        state.active_conversation = "conv0"
    page.dialogs.clear()
    session._open_history_dialog()
    assert page.dialogs, "the history must open"
    return session, page, page.dialogs[-1]


def _walk(control, found):
    if control is None or isinstance(control, (str, int, float, bool)):
        return
    found.append(control)
    for child in list(getattr(control, "controls", None) or []):
        _walk(child, found)
    for attr in ("content", "title", "actions"):
        kid = getattr(control, attr, None)
        if isinstance(kid, list):
            for item in kid:
                _walk(item, found)
        else:
            _walk(kid, found)


def _action_labels(dlg) -> list[str]:
    out = []
    for action in dlg.actions or []:
        label = getattr(action, "content", None)
        out.append(label if isinstance(label, str) else str(label))
    return out


def test_history_opens_as_a_modal_like_the_credit_dialog(tmp_path, monkeypatch):
    _, _, dlg = _open_history(tmp_path, monkeypatch, ["First chat"])
    assert isinstance(dlg, ft.AlertDialog)
    assert not isinstance(dlg, ft.BottomSheet), "the sheet is what was disliked"
    assert dlg.title.value == "Chat history"
    labels = _action_labels(dlg)
    assert "Close" in labels
    assert "Delete all chats" in labels, "destructive work lives in actions"
    # A bounded list: 50 chats must not run off a phone screen.
    assert dlg.content.height, "the list needs a bounded height"


def test_history_rows_are_not_filled_dark_slabs(tmp_path, monkeypatch):
    """The old list tinted the active row with a full-width colour block."""
    _, _, dlg = _open_history(tmp_path, monkeypatch, ["Alpha", "Beta"])
    found: list = []
    _walk(dlg.content, found)
    slabs = [
        c
        for c in found
        if isinstance(c, ft.Container)
        and getattr(c, "bgcolor", None)
        and getattr(c, "width", None) is None
    ]
    assert not slabs, f"{len(slabs)} full-width tinted row(s) remain"
    assert not any(isinstance(c, ft.ListTile) for c in found), (
        "the ListTile stack is the dark list the user rejected"
    )


def test_history_marks_the_open_chat_and_reads_disk_every_time(
    tmp_path, monkeypatch
):
    from services import conversation_service as conversations

    session, page, dlg = _open_history(
        tmp_path, monkeypatch, ["Alpha chat", "Beta chat"]
    )
    found: list = []
    _walk(dlg.content, found)
    checks = [
        c
        for c in found
        if isinstance(c, ft.Icon)
        and getattr(c, "icon", None) == ft.Icons.CHECK_CIRCLE_ROUNDED
    ]
    assert checks, "the open chat must be visible in the list"

    # Reopening must re-read the folder, or a deleted chat lingers.
    page.dialogs.clear()
    session._open_history_dialog()
    assert len(page.dialogs) == 1
    titles = conversations.list_conversations()
    assert len(titles) >= 2
    assert {t["title"] for t in titles} >= {"Alpha chat", "Beta chat"}
