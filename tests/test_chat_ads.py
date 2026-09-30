"""Assistant chat ads: the owner's rule, ported from LM Router.

One ad after every AI reply, derived positionally from the transcript (so
streaming re-renders cannot stack duplicates); the thread never ends on an
ad; premium and desktop insert nothing; and the chat view carries no
banner other than the in-transcript ones.
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

import flet as ft

SRC = Path(__file__).resolve().parents[1] / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))


def _session_stub(platform=ft.PagePlatform.ANDROID):
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
        width = 900
        height = 800
        theme_mode = ft.ThemeMode.DARK

        def __init__(self):
            self.dialogs = []
            self.views = []
            self._ddgs_controller = Controller()
            self.scheduled = []

        def run_task(self, handler, *args, **kwargs):
            if not asyncio.iscoroutinefunction(handler):
                raise TypeError("handler must be a coroutine function")
            self.scheduled.append(handler.__name__)

        def run_thread(self, handler, *args, **kwargs):
            self.scheduled.append(getattr(handler, "__name__", "thread"))

        def show_dialog(self, dlg):
            self.dialogs.append(dlg)

        def pop_dialog(self):
            pass

        def update(self):
            pass

    Page.platform = platform
    return ChatSession, Page


def _chat(pairs: int) -> list[dict]:
    """Alternating user/assistant rows: N questions with N answers."""
    turns = []
    for i in range(pairs * 2):
        turns.append(
            {"role": "user" if i % 2 == 0 else "assistant", "text": f"row {i}"}
        )
    return turns


def _ads(session) -> list:
    """Top-level ad rows: the renderer returns Containers, ads are rows."""
    return [c for c in session._list.controls if isinstance(c, ft.Row)]


def test_ad_after_every_reply_but_never_the_last(tmp_path, monkeypatch):
    monkeypatch.setenv("FLET_APP_STORAGE_DATA", str(tmp_path / "data"))
    ChatSession, Page = _session_stub()
    session = ChatSession(Page())
    session.turns = _chat(3)
    session._render()

    controls = session._list.controls
    # u a AD u a AD u a  (the final reply never carries the ad)
    assert len(_ads(session)) == 2
    assert isinstance(controls[2], ft.Row)
    assert isinstance(controls[5], ft.Row)
    assert not isinstance(controls[-1], ft.Row)


def test_single_exchange_ends_on_the_message(tmp_path, monkeypatch):
    monkeypatch.setenv("FLET_APP_STORAGE_DATA", str(tmp_path / "data"))
    ChatSession, Page = _session_stub()
    session = ChatSession(Page())
    session.turns = _chat(1)
    session._render()
    assert _ads(session) == [], "a one-shot conversation must not end on an ad"


def test_empty_conversation_has_no_ad(tmp_path, monkeypatch):
    monkeypatch.setenv("FLET_APP_STORAGE_DATA", str(tmp_path / "data"))
    ChatSession, Page = _session_stub()
    session = ChatSession(Page())
    session.turns = []
    session._render()
    assert _ads(session) == []


def test_failed_reply_still_counts_and_banners_follow_the_rule(tmp_path, monkeypatch):
    monkeypatch.setenv("FLET_APP_STORAGE_DATA", str(tmp_path / "data"))
    ChatSession, Page = _session_stub()
    session = ChatSession(Page())
    session.turns = [
        {"role": "user", "text": "q"},
        {"role": "assistant", "text": "", "error": "unavailable"},
        {"role": "user", "text": "q2"},
        {"role": "assistant", "text": "a2"},
    ]
    session._render()
    controls = session._list.controls
    # The failed reply is mid-thread, so it earns its ad; the newest does not.
    assert isinstance(controls[2], ft.Row)
    assert len(_ads(session)) == 1


def test_premium_gets_no_ad_rows(tmp_path, monkeypatch):
    monkeypatch.setenv("FLET_APP_STORAGE_DATA", str(tmp_path / "data"))
    from core.state import state

    monkeypatch.setattr(state, "is_premium", True)
    monkeypatch.setattr(state, "scheduled_scrapes", [])
    ChatSession, Page = _session_stub()
    session = ChatSession(Page())
    session.turns = _chat(3)
    session._render()
    assert _ads(session) == [], "a paid conversation must have no ad rows"


def test_desktop_gets_no_ad_rows(tmp_path, monkeypatch):
    monkeypatch.setenv("FLET_APP_STORAGE_DATA", str(tmp_path / "data"))
    ChatSession, Page = _session_stub(platform=ft.PagePlatform.WINDOWS)
    session = ChatSession(Page())
    session.turns = _chat(3)
    session._render()
    assert _ads(session) == []


def test_ad_slot_keeps_its_identity_across_renders(tmp_path, monkeypatch):
    """The pool stops native ad churn: emit() re-renders ~5x per second
    while streaming, and a fresh BannerAd per render would rebuild the
    native view per token."""
    monkeypatch.setenv("FLET_APP_STORAGE_DATA", str(tmp_path / "data"))
    ChatSession, Page = _session_stub()
    session = ChatSession(Page())
    session.turns = _chat(3)
    session._render()
    first = session._list.controls[2]
    session._render()
    assert session._list.controls[2] is first, "the ad slot was rebuilt"
    session._render()
    assert session._list.controls[5] is not first, "slots must not alias"


def test_chat_view_has_no_other_banner(tmp_path, monkeypatch):
    """The chat view stays [appbar, list, composer]: the only banners in
    assistant mode are the in-transcript reply ads."""
    monkeypatch.setenv("FLET_APP_STORAGE_DATA", str(tmp_path / "data"))
    ChatSession, Page = _session_stub()
    session = ChatSession(Page())
    session.turns = _chat(2)
    session._render()

    # view = [SafeArea > Container > Column(header, list, composer)]:
    # SafeArea carries the status-bar inset the old AppBar provided.
    host = session.view.controls[0]
    column = host.content.content
    assert len(column.controls) == 3, "a banner sibling crept into the view"
    # and the transcript banners are the only ad controls anywhere
    assert isinstance(column.controls[1].content, ft.ListView)
    assert len(_ads(session)) == 1  # 2 pairs: only the first reply's ad
