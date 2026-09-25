"""Assistant chat — the agentic surface (FAB entry).

Imperative View (reader pattern): built once, refreshed from session state
with >=0.2s throttled streaming, pinned-to-bottom auto-scroll. Agent loop
lives in services/chat_agent; this file owns presentation:
  - "Assistant used N steps · 2N credits" receipts
  - collapsible tool steps + thinking
  - result blocks with "View N results in Results" (minimizes the Assistant)
  - approve/deny gates before any file-writing tool
  - long-press a message to delete; Clear chat in the app bar
  - scheduled crawls listed with cancel
"""

from __future__ import annotations

import asyncio
import logging
import time

import flet as ft

from components.model_picker import build_model_pill
from components.results.downloader import launch_url
from components.wallet import show_wallet_dialog
from core import tokens
from core.state import SearchResult, state
from core.theme import AppColors

logger = logging.getLogger(__name__)

_CHAT = ft.Icons.CHAT_BUBBLE_OUTLINE_ROUNDED

_KIND_ICONS = {
    "web": ft.Icons.LANGUAGE_ROUNDED,
    "images": ft.Icons.IMAGE_ROUNDED,
    "videos": ft.Icons.VIDEO_LIBRARY_ROUNDED,
    "news": ft.Icons.NEWSPAPER_ROUNDED,
    "books": ft.Icons.BOOK_ROUNDED,
}
# Generous now that the body is expandable and collapsible: truncating at
# 900 characters used to hide the reasoning the user asked to see.
_THROUGHT_CAP = 8000

_SUGGESTIONS = [
    "What happened in tech this week?",
    "Explain a topic like I'm 12",
    "Find me the best free privacy tools",
]


def _thought_seconds(turn: dict) -> int:
    """How long the model spent reasoning, frozen when the thought ended.

    Measured from the first reasoning delta, so it excludes the wait
    before the model started thinking.
    """
    started = turn.get("thought_started_at")
    if not started:
        return 0
    end = turn.get("thought_ended_at") or started
    try:
        return int(max(end - started, 0))
    except TypeError:
        return 0


def _domain(url: str) -> str:
    if "//" in url:
        return url.split("/")[2].removeprefix("www.")
    return url[:40]


def conversations_load(conversation_id: str) -> dict | None:
    """Read a saved conversation. Thin wrapper so callers need one import."""
    from services import conversation_service as conversations

    return conversations.load_conversation(conversation_id)


def _turns_from_messages(messages: list[dict]) -> list[dict]:
    """Rebuild renderable turns from a saved conversation.

    Saved messages are the flat role/content pairs the agent consumes, so
    the visual extras (steps, cards, receipt) are not in them. Reopened
    chats therefore show the conversation itself, which is the honest
    rendering: we do not have the tool-step detail for an old turn.
    """
    turns: list[dict] = []
    for message in messages or []:
        if not isinstance(message, dict):
            continue
        role = str(message.get("role") or "")
        text = message.get("content")
        if not isinstance(text, str) or not text.strip():
            continue
        if role == "user":
            turns.append({"role": "user", "text": text})
        elif role == "assistant":
            turns.append(
                {
                    "role": "assistant",
                    "text": text,
                    "thought": "",
                    "steps": 0,
                    "cost": 0,
                    "partial": False,
                    "steps_rows": [],
                    "cards": [],
                    "related": [],
                    "served_by": "",
                    "model": "",
                    "error": None,
                    "stopped": False,
                    "receipt": "",
                }
            )
    return turns


class ChatSession:
    """Owns one conversation: local model, rendering, agent turn, approvals.

    The session is bound to a conversation id. Turns are rendered from
    `turns` for the live view, while `agent_history` (the flat role/content
    list the agent consumes) is what actually gets persisted, so a reopened
    chat continues with real context instead of starting cold.
    """

    def __init__(self, page: ft.Page, ctx: dict | None = None):
        from services import conversation_service as conversations

        self.page = page
        self.ctx = ctx or {}
        self.conversation_id: str = conversations.ensure_active()
        saved = conversations.load_conversation(self.conversation_id) or {}
        self.turns: list[dict] = _turns_from_messages(saved.get("messages") or [])
        self.agent_history: list[dict] = list(saved.get("messages") or [])
        self.pending_user = ""
        self.busy = False
        self.cancel = asyncio.Event()
        # Two independent clocks. Sharing one meant a text flush reset the
        # thought throttle and vice versa, so thinking could silently starve
        # for 500ms every time a text token landed.
        self._last_text_flush = 0.0
        self._last_thought_flush = 0.0
        self._pinned = True  # auto-scroll only while the user sits at the bottom
        self._current: dict | None = None
        # Set once teardown starts; every UI touch afterwards is a no-op.
        self._closing = False
        self._confirm: tuple[asyncio.Event, dict] | None = None

        # ── Controls ────────────────────────────────────────────────
        self._list = ft.Column(
            [], spacing=tokens.SPACE_SM, expand=True, scroll=ft.ScrollMode.AUTO
        )
        self.field = ft.TextField(
            hint_text="Ask the assistant. It can search and fetch for you.",
            expand=True,
            dense=True,
            min_lines=1,
            max_lines=4,
            content_padding=ft.Padding(12, 8, 12, 8),
            border=ft.OutlineInputBorder(border_radius=tokens.RADIUS_LG),
        )
        self.send_btn = ft.IconButton(
            icon=ft.Icons.SEND_ROUNDED,
            icon_color=AppColors.PRIMARY,
            tooltip="Send",
            on_click=lambda e: self._send_from_field(),
        )
        self.stop_btn = ft.IconButton(
            icon=ft.Icons.STOP_ROUNDED,
            icon_color=AppColors.ERROR,
            tooltip="Stop",
            visible=False,
            on_click=lambda e: self.stop(),
        )
        self.field.on_submit = lambda e: self._send_from_field()

        credits_color = _credits_color(state.credits_remaining)
        self.credits_chip = ft.Container(
            content=ft.Row(
                [
                    ft.Icon(_CHAT, size=tokens.ICON_SM, color=credits_color),
                    ft.Text(
                        str(state.credits_remaining),
                        size=tokens.FONT_SM,
                        weight=ft.FontWeight.W_700,
                        color=credits_color,
                    ),
                ],
                spacing=3,
                tight=True,
            ),
            padding=ft.Padding(8, 4, 10, 4),
            border_radius=tokens.RADIUS_PILL,
            bgcolor=ft.Colors.with_opacity(0.12, credits_color),
            border=ft.Border.all(1, ft.Colors.with_opacity(0.25, credits_color)),
            ink=True,
            tooltip="Assistant credits, tap for details",
            on_click=lambda e: show_wallet_dialog(page),
        )
        # Live pill: its label tracks the router lifecycle (starting /
        # ready / stopped) and the selected model, rebuilt on every render.
        self.model_chip = build_model_pill(page)

        appbar = ft.AppBar(
            leading=ft.IconButton(
                icon=ft.Icons.ARROW_BACK_ROUNDED,
                tooltip="Minimize assistant",
                on_click=lambda e: self.close(),
            ),
            title=ft.Row(
                [
                    ft.Icon(_CHAT, size=20, color=AppColors.PRIMARY),
                    ft.Text(
                        "Assistant",
                        size=tokens.FONT_MD,
                        weight=ft.FontWeight.W_700,
                        font_family="Outfit",
                    ),
                ],
                spacing=6,
            ),
            actions=[
                self.model_chip,
                self.credits_chip,
                self._history_button_control(),
                ft.Container(width=6),
            ],
            bgcolor=ft.Colors.TRANSPARENT,
            elevation=0,
        )

        composer = ft.Container(
            content=ft.Row(
                [self.field, self.send_btn, self.stop_btn],
                vertical_alignment=ft.CrossAxisAlignment.END,
                spacing=2,
            ),
            padding=ft.Padding(10, 6, 10, 10),
        )

        # Pinned detection: flip off when the user scrolls away from the end.
        try:
            self._list.on_scroll = self._on_scroll
        except Exception:
            pass

        self.view = ft.View(
            route="/chat",
            controls=[
                ft.Container(
                    content=ft.Column(
                        [appbar, ft.Container(self._list, expand=True), composer],
                        spacing=0,
                        expand=True,
                    ),
                    expand=True,
                    bgcolor=ft.Colors.SURFACE,
                )
            ],
            padding=0,
            spacing=0,
        )
        self._render()

    # ── Controller-ish API ────────────────────────────────────────────────

    def _send_from_field(self) -> None:
        text = (self.field.value or "").strip()
        if not text or self.busy:
            return
        self.field.value = ""
        try:
            self.field.update()
        except Exception:
            pass
        self.send(text)

    def send(self, text: str) -> None:
        if self.busy:
            return
        self.pending_user = text
        self.cancel = asyncio.Event()
        self.busy = True
        self._set_busy_ui(True)
        # Keep the handle so Stop can cancel the task. Setting the flag
        # alone is cooperative: a stalled socket or a long tool can leave
        # the UI spinning long after the user pressed Stop.
        task = asyncio.ensure_future(self._run_turn(text))
        # Retrieve the terminal exception ourselves. Without this, a turn
        # that fails logs "Task exception was never retrieved" and the
        # error disappears, which is what produced the cascade in the log.
        task.add_done_callback(self._on_turn_done)
        self._turn_task = task

    def shutdown(self) -> None:
        """Tear the session down before Flet releases the page.

        Called from the app close hook. Once the session is gone every
        `page.update()` and `page.run_task()` raises, so a turn still
        running would throw inside render, then again inside settlement,
        and the persistence that follows would never run. Stopping it here,
        while the loop is still alive, is the whole point.
        """
        if self._closing:
            return
        self._closing = True
        self.cancel.set()
        task = getattr(self, "_turn_task", None)
        if task is not None and not task.done():
            task.cancel()
        try:
            self._persist_history()
        except Exception:
            logger.debug("persist on shutdown failed")

    def _on_turn_done(self, task: asyncio.Task) -> None:
        """Own the turn's terminal exception instead of letting asyncio log it."""
        if self._turn_task is task:
            self._turn_task = None
        if task.cancelled():
            return
        exc = task.exception()
        if exc is None:
            return
        # Expected after teardown; anything else is a real failure worth
        # seeing once, loudly, rather than as a duplicate traceback.
        if "destroyed session" in str(exc):
            logger.debug("assistant turn ended with the session already closed")
        else:
            logger.exception("assistant turn failed", exc_info=exc)

    async def _run_turn(self, text: str) -> None:
        from services import chat_agent

        try:
            await chat_agent.run_turn(
                text,
                list(self.agent_history),
                self.emit,
                self.cancel,
                on_thought=lambda t: self.emit("thought", {"text": t}),
                ask_confirm=self.ask_confirm,
            )
        except asyncio.CancelledError:
            # Stop cancelled the task outright. run_turn settles its own
            # credits before re-raising, so nothing is left half-charged;
            # we just keep what the user already saw.
            logger.info("assistant turn cancelled by the user")
            raise
        finally:
            self.busy = False
            self._turn_task = None
            self._set_busy_ui(False)
            # Persist and refresh the balance even on stop or failure: the
            # credits moved whether or not the turn succeeded.
            self._persist_history()
            self._refresh_credits_chip()
            self._render(force=True)

    def stop(self) -> None:
        """Stop the turn now: raise the flag, then cancel the task itself."""
        self.cancel.set()
        task = getattr(self, "_turn_task", None)
        if task is not None and not task.done():
            task.cancel()

    async def ask_confirm(self, label: str) -> bool:
        """Inline approve/deny gate for file-writing tools. Times out to deny.

        The gate is cleared in a finally block. Leaving it populated after a
        timeout or a cancellation kept the Allow/No controls on screen for an
        operation that was already resolved as denied, and clicking Allow
        then did nothing, which made a real safety gate look broken.
        """
        event = asyncio.Event()
        self._confirm = (event, {"label": label, "decision": None})
        self._render(force=True)
        try:
            await asyncio.wait_for(event.wait(), timeout=120)
            decision = self._confirm[1]["decision"] if self._confirm else None
            return decision == "allow"
        except (TimeoutError, asyncio.CancelledError):
            return False
        finally:
            self._confirm = None
            self._render(force=True)

    def _confirm_decision(self, decision: str) -> None:
        if self._confirm and self._confirm[1].get("decision") is None:
            self._confirm[1]["decision"] = decision
            self._confirm[0].set()

    def close(self) -> None:
        """Minimize the Assistant. The session is retained, never destroyed.

        Popping the view is not the same as discarding the conversation:
        the ChatSession object stays on the page, so the FAB can bring back
        the exact same turns, scroll position and pending approval.

        This deliberately does not cancel a running turn. Minimizing means
        putting the conversation away, not discarding work in progress, and
        the FAB brings the user straight back to it.
        """
        self._persist_history()
        try:
            if self.page.views and self.page.views[-1] is self.view:
                self.page.views.pop()
            state.chat_open = False
            state.chat_minimized = True
            self.page.update()
        except Exception:
            state.chat_open = False
            state.chat_minimized = True

    def restore(self) -> None:
        """Re-attach this retained session to the view stack."""
        state.chat_open = True
        state.chat_minimized = False
        if self.view not in self.page.views:
            self.page.views.append(self.view)
        self.refresh_model_chip()
        if self._closing:
            return
        try:
            self.page.update()
        except Exception:
            # The session may already be gone; that is teardown, not a bug.
            pass
        if self._pinned:
            try:
                self.page.run_task(self._scroll_to_bottom)
            except Exception:
                # run_task evaluates page.session before scheduling, so a
                # destroyed session raises here and would otherwise leak an
                # un-awaited scroll coroutine and kill the whole turn.
                pass

    def _clear_chat(self) -> None:
        if not self.turns:
            return
        self.turns = []
        self.agent_history = []
        self._persist_history()
        self._render(force=True)
        self._snack("Chat cleared")

    def _delete_turn(self, index: int) -> None:
        """Delete a message from the transcript, then rebuild the view.

        The old code deleted only from `self.turns` — the render list — and
        then persisted `self.agent_history`, which was untouched. So the
        message vanished visually and came straight back from disk on the
        next switch or restart. A delete has to mutate the canonical
        transcript; the view is a projection of it, never the other way
        round.
        """
        if not (0 <= index < len(self.turns)):
            return
        turn = self.turns[index]
        role = turn.get("role")
        if role not in ("user", "assistant"):
            # Error/empty rows have no transcript entry: view-only.
            del self.turns[index]
            self._render(force=True)
            return
        offset = self._transcript_offset(index, role)
        if offset is None:
            del self.turns[index]
            self._render(force=True)
            return

        # Drop the whole exchange, not one side of it: a question with no
        # answer, or an answer with no question, reads as a glitch.
        start = offset
        end = offset + 1
        if role == "user":
            while (
                end < len(self.agent_history)
                and self.agent_history[end].get("role") != "assistant"
            ):
                end += 1
            if end < len(self.agent_history):
                end += 1
        else:
            while (
                start > 0
                and self.agent_history[start - 1].get("role") != "user"
            ):
                start -= 1

        del self.agent_history[start:end]
        self.turns = _turns_from_messages(self.agent_history)
        self._persist_history()
        self._render(force=True)

    def _transcript_offset(self, turn_index: int, role: str) -> int | None:
        """Find the transcript index of a rendered turn of the same role.

        `turns` and `agent_history` are both ordered, and `turns` is built
        from `agent_history`, so the Nth turn of a role maps to the Nth
        entry of that role. No text matching, so an edited or repeated
        message cannot be deleted by mistake.
        """
        position = sum(
            1 for t in self.turns[:turn_index] if t.get("role") == role
        )
        same_role = [
            i
            for i, entry in enumerate(self.agent_history)
            if entry.get("role") == role
        ]
        if position >= len(same_role):
            return None
        return same_role[position]

    def _persist_history(self) -> None:
        """Write this conversation to disk and refresh the history menu.

        The 16-message cap that used to live here was the *agent context*
        window, not a storage limit. A saved conversation keeps every
        message (up to CONVERSATION_MESSAGE_CAP, so one very long chat
        cannot grow without bound); `chat_agent` already slices what it
        sends to the model, so truncating on save was throwing away the
        user's own history.
        """
        from services import conversation_service as conversations

        conversation_id = self.conversation_id
        messages = list(self.agent_history)[-conversations.CONVERSATION_MESSAGE_CAP :]

        # Schedule the disk write BEFORE touching any observable field.
        # `state.assistant_history = ...` notifies subscribers and can raise
        # after teardown, and anything raised before these lines meant the
        # conversation was never written at all — history silently lost.
        try:
            self.page.run_task(self._save_history, conversation_id, messages)
        except Exception:
            logger.debug("could not schedule the conversation save")
        # The mirror is written second and guarded: it is only here so an
        # observer can see the transcript, and a dead session must never be
        # able to stop the file write that already happened above.
        try:
            state.assistant_history = list(self.agent_history)
        except Exception:
            pass

    async def _save_history(self, conversation_id: str, messages: list) -> None:
        """Persist one conversation. Never raises into the caller.

        Async because `page.run_task` refuses a plain function, and a throw
        here would surface as an unretrieved task exception during
        teardown — exactly the crash this replaced.
        """
        from services import conversation_service as conversations

        try:
            existed = await asyncio.to_thread(
                conversations.load_conversation, conversation_id
            )
            saved = await asyncio.to_thread(
                conversations.save_conversation, conversation_id, messages
            )
            if not saved:
                return
            rows = conversations.refresh_state()
            # Announce pruning only when the cap actually bit. Counting
            # "before + 1 - after" reported a deletion on every save of an
            # existing chat, telling users their history was being removed
            # when it was not.
            if existed is None and len(rows) >= conversations.MAX_CONVERSATIONS:
                self._snack(
                    f"Kept your {conversations.MAX_CONVERSATIONS} most recent "
                    "chats and removed the oldest one"
                )
        except Exception:
            logger.exception("conversation save failed")

    def _snack(self, message: str) -> None:
        snack = ft.SnackBar(ft.Text(message))
        snack.open = True
        self.page.show_dialog(snack)
        try:
            self.page.update()
        except Exception:
            pass

    # ── Conversation switching ──────────────────────────────────────────
    def _busy_refuse(self, what: str) -> bool:
        """Refuse a history change while a reply is still streaming.

        The running turn writes into `self.conversation_id` when it
        finishes, so switching, replacing or deleting the active chat
        mid-reply would file the answer under the wrong conversation, or
        recreate the one just deleted.
        """
        if not self.busy:
            return False
        self._snack(f"Wait for the current reply before {what}")
        return True

    def new_conversation(self, *, keep_current: bool = True) -> None:
        """Start an empty chat.

        `keep_current=False` is for the delete path: the chat we are in has
        just been removed, so persisting it again would write the deleted
        file straight back to disk.
        """
        from services import conversation_service as conversations

        if self._busy_refuse("starting a new chat"):
            return
        if keep_current:
            self._persist_history()
        self.conversation_id = conversations.new_conversation_id()
        state.active_conversation = self.conversation_id
        self.turns = []
        self.agent_history = []
        self._remember_active()
        self._render(force=True)

    def _toggle_thought(self, turn: dict) -> None:
        turn["thought_open"] = not bool(turn.get("thought_open", True))
        self._render(force=True)

    def _retry_last(self) -> None:
        """Re-send the last user message of the active chat."""
        for turn in reversed(self.turns):
            if turn.get("role") == "user" and str(turn.get("text") or "").strip():
                self.send(turn["text"])
                return
        self._snack("There is nothing to retry")

    def _switch_model_and_retry(self, model_id: str) -> None:
        """Apply the suggested model, then re-ask the last question.

        Both halves matter: a rate limit is only recovered from if the new
        model is actually the one the next request uses.
        """
        if not model_id:
            return
        from components.model_picker import _select

        _select(self.page, getattr(self.page, "_ddgs_controller", None), model_id)
        self.refresh_model_chip()
        self._retry_last()

    def _adopt(self, loaded: dict) -> None:
        """Make a loaded conversation the live one, with no same-id guard.

        Split out from switch_conversation so deleting the active chat can
        load its replacement: the caller sets the id itself, and the old
        guard would have seen the ids already matching and returned early,
        leaving the deleted chat's turns on screen.
        """
        self.conversation_id = str(loaded.get("id") or self.conversation_id)
        state.active_conversation = self.conversation_id
        self.turns = _turns_from_messages(loaded.get("messages") or [])
        self.agent_history = list(loaded.get("messages") or [])
        self._remember_active()
        self._render(force=True)

    def _remember_active(self) -> None:
        """Remember the open chat so the next launch returns to it."""
        ctrl = getattr(self.page, "_ddgs_controller", None)
        storage = getattr(ctrl, "storage", None) if ctrl else None
        if storage is None:
            return

        async def _save() -> None:
            try:
                await storage.set_active_conversation(self.conversation_id)
            except Exception:
                logger.debug("could not remember the active chat")

        try:
            self.page.run_task(_save)
        except Exception:
            pass

    def switch_conversation(self, conversation_id: str) -> None:
        """Open a saved chat in this session."""
        if conversation_id == self.conversation_id:
            return
        if self.busy:
            self._snack("Wait for the current reply to finish")
            return
        self._persist_history()
        loaded = conversations_load(conversation_id)
        if loaded is None:
            self._snack("That chat could not be opened")
            return
        self._adopt(loaded)

    def delete_conversation(self, conversation_id: str) -> None:
        from services import conversation_service as conversations

        was_active = conversation_id == self.conversation_id
        if was_active and self._busy_refuse("deleting this chat"):
            return
        if not conversations.delete_conversation(conversation_id):
            self._snack("That chat could not be deleted")
            return
        conversations.refresh_state()
        if was_active:
            rows = conversations.list_conversations()
            if rows:
                # Load the replacement directly. Going through
                # switch_conversation() would set the id first and then hit
                # its own same-id guard, leaving the deleted chat's turns
                # on screen. keep_current=False everywhere: this chat is
                # gone, so saving it again would recreate the deleted file.
                loaded = conversations.load_conversation(rows[0]["id"])
                if loaded is not None:
                    self._adopt(loaded)
            else:
                self.new_conversation(keep_current=False)
        self._snack("Chat deleted")

    def delete_all_conversations(self) -> None:
        from services import conversation_service as conversations

        if self._busy_refuse("deleting your chats"):
            return
        deleted, failed = conversations.delete_all()
        conversations.refresh_state()
        self.new_conversation(keep_current=False)
        if failed:
            self._snack(f"Deleted {deleted} chats, {failed} could not be removed")
        else:
            self._snack("All chats deleted")

    def _history_button_control(self) -> ft.IconButton:
        """The hamburger. It opens a sheet rebuilt from disk every time.

        A popup menu froze its items when the session was created, so a
        deleted chat kept showing until the whole screen refreshed. A sheet
        is also the right surface: 50 chats do not fit a dropdown, and a
        truncated list means the older files you can still open are
        invisible.
        """
        return ft.IconButton(
            icon=ft.Icons.MENU_ROUNDED,
            icon_size=18,
            icon_color=AppColors.PRIMARY,
            tooltip="Chat history",
            on_click=lambda e: self._open_history_sheet(),
        )

    def _open_history_sheet(self) -> None:
        """Build and show the chat list, newest first, all of them."""
        from services import conversation_service as conversations

        rows = conversations.list_conversations()

        def _close(e=None):
            try:
                self.page.pop_dialog()
            except Exception:
                pass

        def _new_chat(e=None):
            _close()
            self.new_conversation()

        def _open_chat(cid: str):
            def _handler(e=None):
                _close()
                self.switch_conversation(cid)

            return _handler

        def _delete_chat(cid: str):
            def _handler(e=None):
                _close()
                self._confirm_delete_one(cid)

            return _handler

        tiles: list[ft.Control] = [
            ft.ListTile(
                leading=ft.Icon(
                    ft.Icons.ADD_ROUNDED, color=ft.Colors.PRIMARY, size=tokens.ICON_MD
                ),
                title=ft.Text(
                    "New chat",
                    weight=ft.FontWeight.W_500,
                    font_family="Outfit",
                ),
                subtitle=ft.Text(
                    "Start a fresh conversation", size=tokens.FONT_XS
                ),
                on_click=_new_chat,
            )
        ]

        if not rows:
            tiles.append(
                ft.Container(
                    content=ft.Text(
                        "No saved chats yet.",
                        size=tokens.FONT_SM,
                        color=ft.Colors.ON_SURFACE_VARIANT,
                    ),
                    padding=ft.Padding(
                        tokens.SPACE_LG, tokens.SPACE_MD, tokens.SPACE_LG, tokens.SPACE_MD
                    ),
                )
            )

        for row in rows:
            conversation_id = str(row.get("id") or "")
            is_active = conversation_id == self.conversation_id
            title = str(row.get("title") or "New chat")
            tiles.append(
                ft.ListTile(
                    leading=ft.Icon(
                        ft.Icons.CHAT_BUBBLE_OUTLINE_ROUNDED,
                        size=tokens.ICON_MD,
                        color=ft.Colors.PRIMARY if is_active else None,
                    ),
                    title=ft.Text(
                        title,
                        weight=ft.FontWeight.W_600 if is_active else None,
                        font_family="Outfit",
                        max_lines=1,
                        overflow=ft.TextOverflow.ELLIPSIS,
                    ),
                    subtitle=ft.Text(
                        conversations.summarize(row),
                        size=tokens.FONT_XS,
                        color=ft.Colors.ON_SURFACE_VARIANT,
                    ),
                    bgcolor=(
                        ft.Colors.with_opacity(0.10, ft.Colors.PRIMARY)
                        if is_active
                        else None
                    ),
                    on_click=_open_chat(conversation_id),
                    trailing=ft.IconButton(
                        icon=ft.Icons.DELETE_OUTLINE_ROUNDED,
                        icon_size=tokens.ICON_SM,
                        icon_color=AppColors.ERROR,
                        tooltip="Delete this chat",
                        on_click=_delete_chat(conversation_id),
                    ),
                )
            )

        tiles.append(
            ft.Divider(height=1, color=ft.Colors.with_opacity(0.2, ft.Colors.OUTLINE))
        )
        tiles.append(
            ft.ListTile(
                leading=ft.Icon(
                    ft.Icons.DELETE_SWEEP_OUTLINED,
                    color=AppColors.ERROR,
                    size=tokens.ICON_MD,
                ),
                title=ft.Text(
                    "Delete all chats",
                    color=AppColors.ERROR,
                    font_family="Outfit",
                ),
                on_click=lambda e: (_close(), self._confirm_delete_all()),
            )
        )

        # Scrollable with a bounded height: 50 tiles must not push the
        # sheet off the screen on a phone.
        self.page.show_dialog(
            ft.BottomSheet(
                content=ft.Container(
                    content=ft.Column(
                        controls=tiles,
                        spacing=0,
                        tight=True,
                        scroll=ft.ScrollMode.AUTO,
                    ),
                    padding=ft.Padding(
                        tokens.SPACE_SM,
                        tokens.SPACE_MD,
                        tokens.SPACE_SM,
                        tokens.SPACE_MD,
                    ),
                    height=min(
                        len(tiles) * 72 + 40,
                        (getattr(self.page, "height", None) or 700) * 0.7,
                    ),
                ),
                show_drag_handle=True,
            )
        )
    def _on_delete_button(self, e, conversation_id: str) -> None:
        """Delete from a menu row without also opening that row's chat.

        The delete IconButton sits inside a clickable PopupMenuItem, so
        without stopping the event the tap both asked for a delete and
        switched conversations.
        """
        try:
            if hasattr(e, "control"):
                e.control.disabled = True
        except Exception:
            pass
        self._confirm_delete_one(conversation_id)

    def _confirm_delete_one(self, conversation_id: str) -> None:
        from services import conversation_service as conversations

        row = next(
            (
                r
                for r in conversations.list_conversations()
                if r["id"] == conversation_id
            ),
            None,
        )
        title = (row or {}).get("title") or "this chat"

        def _do_delete(e=None):
            self.page.pop_dialog()
            self.delete_conversation(conversation_id)

        self.page.show_dialog(
            ft.AlertDialog(
                title=ft.Text("Delete chat?", font_family="Outfit"),
                content=ft.Text(
                    f'"{title}" will be removed from this device. '
                    "This cannot be undone."
                ),
                actions=[
                    ft.TextButton("Cancel", on_click=lambda e: self.page.pop_dialog()),
                    ft.FilledButton(
                        "Delete",
                        on_click=_do_delete,
                        style=ft.ButtonStyle(
                            bgcolor=AppColors.ERROR, color=ft.Colors.WHITE
                        ),
                    ),
                ],
            )
        )

    def _confirm_delete_all(self) -> None:
        from services import conversation_service as conversations

        count = len(conversations.list_conversations())

        def _do_delete(e=None):
            self.page.pop_dialog()
            self.delete_all_conversations()

        self.page.show_dialog(
            ft.AlertDialog(
                title=ft.Text("Delete all chats?", font_family="Outfit"),
                content=ft.Text(
                    f"All {count} saved chats will be removed from this device. "
                    "This cannot be undone."
                ),
                actions=[
                    ft.TextButton("Cancel", on_click=lambda e: self.page.pop_dialog()),
                    ft.FilledButton(
                        "Delete all",
                        on_click=_do_delete,
                        style=ft.ButtonStyle(
                            bgcolor=AppColors.ERROR, color=ft.Colors.WHITE
                        ),
                    ),
                ],
            )
        )

    def _set_busy_ui(self, busy: bool) -> None:
        self.send_btn.visible = not busy
        self.stop_btn.visible = busy
        try:
            self.send_btn.update()
            self.stop_btn.update()
        except Exception:
            pass

    def _on_scroll(self, e) -> None:
        try:
            offset = getattr(self._list, "scroll_offset", None) or 0
            extent = getattr(self._list, "scroll_extent", None) or 0
            viewport = getattr(self._list, "viewport", None) or 0
            if isinstance(offset, (int, float)) and isinstance(extent, (int, float)):
                self._pinned = offset + viewport >= extent - 64
        except Exception:
            pass

    # ── Emit protocol ──────────────────────────────────────────────────────

    def emit(self, event: str, data: dict) -> None:
        now = time.monotonic()
        force = True
        if event == "user":
            self.turns.append({"role": "user", "text": data.get("text", "")})
        elif event == "assistant_start":
            self._current = {
                "role": "assistant",
                "text": "",
                "thought": "",
                "steps": 0,
                "cost": 0,
                "partial": True,
                "steps_rows": [],
                "cards": [],
                "related": [],
                "served_by": "",
                "model": "",
                "error": None,
                "stopped": False,
                "receipt": "",
            }
            self.turns.append(self._current)
        elif event == "nudge" and self._current is not None:
            self._current["receipt"] = data.get("text", "")
        elif event == "text_partial" and self._current is not None:
            self._current["text"] = data.get("text", "")
            force = False
            if now - self._last_text_flush < 0.2:
                return
            self._last_text_flush = now
        elif event == "thought" and self._current is not None:
            if not self._current.get("thought_started_at"):
                self._current["thought_started_at"] = now
            buf = (self._current.get("thought") or "") + data.get("text", "")
            self._current["thought"] = buf[:_THROUGHT_CAP]
            force = False
            if now - self._last_thought_flush < 0.5:
                return
            self._last_thought_flush = now
        elif event == "step_start" and self._current is not None:
            self._current["steps_rows"].append(
                {
                    "id": data.get("id", ""),
                    "label": data.get("label", ""),
                    "state": "running",
                    "count": 0,
                    "error": None,
                }
            )
        elif event in ("step_done", "step_error") and self._current is not None:
            for step in self._current["steps_rows"]:
                if step["id"] == data.get("id") or step["state"] == "running":
                    step["state"] = "done" if event == "step_done" else "error"
                    step["count"] = data.get("count", 0)
                    step["error"] = data.get("error")
                    step["label"] = data.get("label", step["label"])
                    break
        elif event == "results" and self._current is not None:
            self._current["cards"].append(
                {"kind": data.get("kind", "web"), "results": data.get("results", [])}
            )
        elif event == "text_final" and self._current is not None:
            # Reasoning is over once the answer starts, so freeze its
            # duration instead of letting the label keep counting.
            if self._current.get("thought_started_at") and not self._current.get(
                "thought_ended_at"
            ):
                self._current["thought_ended_at"] = now
            self._current.update(
                text=data.get("text", ""),
                related=data.get("related", []),
                served_by=data.get("served_by", ""),
                model=data.get("model", ""),
                steps=data.get("steps", 0),
                cost=data.get("cost", 0),
                partial=False,
                receipt="",
            )
            self._record_turn(self._current["text"])
            self._persist_history()
            self._refresh_credits_chip()
            self.refresh_model_chip()
        elif event == "stopped" and self._current is not None:
            if self._current.get("thought_started_at") and not self._current.get(
                "thought_ended_at"
            ):
                self._current["thought_ended_at"] = now
            self._current.update(
                partial=False,
                stopped=True,
                # Whatever streamed before Stop is a real partial answer and
                # must survive a chat switch or a restart.
                text=str(data.get("partial") or self._current.get("text") or ""),
                steps=data.get("steps", self._current.get("steps", 0)),
                cost=data.get("cost", self._current.get("cost", 0)),
            )
            self._record_turn(self._current.get("text"))
            self._persist_history()
        elif event == "error" and self._current is not None:
            if self._current.get("thought_started_at") and not self._current.get(
                "thought_ended_at"
            ):
                self._current["thought_ended_at"] = now
            self._current.update(
                partial=False,
                # Keep whatever streamed before the failure so the exchange
                # survives a switch or a restart.
                text=str(data.get("partial") or self._current.get("text") or ""),
                error=data.get("kind", "unavailable"),
                # Rate limits and empty answers carry their own copy and a
                # next step, so they are not flattened into a generic
                # "unavailable" the user can do nothing about.
                error_message=str(data.get("message") or ""),
                suggestion=str(data.get("suggestion") or ""),
                steps=data.get("steps", self._current.get("steps", 0)),
                cost=data.get("cost", self._current.get("cost", 0)),
            )
            self._record_turn(self._current.get("text"))
            self._persist_history()
        elif event == "error" and self._current is None:
            self.turns.append(
                {
                    "role": "assistant",
                    "text": "",
                    "thought": "",
                    "steps": 0,
                    "cost": 0,
                    "partial": False,
                    "steps_rows": [],
                    "cards": [],
                    "related": [],
                    "served_by": "",
                    "model": "",
                    "error": data.get("kind", "unavailable"),
                    "stopped": False,
                    "receipt": "",
                }
            )
            if data.get("kind") == "credits":
                self.busy = False
            self._refresh_credits_chip()
        # The balance moved for stops, failures and rate limits too, so the
        # chip is refreshed on every terminal event, not only on success.
        if event in ("text_final", "error", "stopped"):
            self._refresh_credits_chip()
        self._render(force=force)

    def _record_turn(self, text: str = "") -> None:
        """Append a question, and any answer the user actually saw.

        Called for success, stop and failure. A stopped or failed turn is
        still a real exchange: dropping it meant that switching chats or
        restarting the app lost the question, any partial answer, and the
        context the model needed to follow up.
        """
        if not self.pending_user:
            return
        question = self.pending_user
        answer = str(text or "").strip()
        if not answer and self._current is not None:
            answer = str(self._current.get("text") or "").strip()
        if not question and not answer:
            self.pending_user = ""
            return
        entry = []
        if question:
            entry.append({"role": "user", "content": question})
        if answer:
            entry.append({"role": "assistant", "content": answer})
        if entry:
            self.agent_history = self.agent_history + entry
        self.pending_user = ""

    def _refresh_credits_chip(self) -> None:
        try:
            color = _credits_color(state.credits_remaining)
            for control in self.credits_chip.content.controls:
                control.color = color
            self.credits_chip.content.controls[-1].value = str(state.credits_remaining)
            self.credits_chip.update()
        except Exception:
            pass

    def refresh_model_chip(self) -> None:
        """Rebuild the header pill, but only when it actually changed.

        The chip is a static control inside an imperative View, so nothing
        re-renders it when the observable router status changes. It used to
        be rebuilt on every accepted token, which meant constructing a whole
        control tree and sending a separate panel update per token for a
        label that almost never moved. Now it short-circuits unless the
        router status, model or availability changed.
        """
        from components.model_picker import model_picker_state

        try:
            snapshot = model_picker_state()
            signature = (
                snapshot.label,
                snapshot.active,
                snapshot.discovering,
                snapshot.selected,
                state.ai_router_status,
            )
            if signature == getattr(self, "_pill_signature", None):
                return
            self._pill_signature = signature
            new_chip = build_model_pill(self.page)
            self.model_chip.content = new_chip.content
            self.model_chip.bgcolor = new_chip.bgcolor
            self.model_chip.update()
        except Exception:
            pass

    # ── Rendering ──────────────────────────────────────────────────────────

    def _render(self, force: bool = True) -> None:
        """Rebuild the turn list and push it to the client.

        The update is unconditional. Streaming text and thinking arrive with
        force=False, and gating page.update() behind `force` rebuilt the tree
        in memory without painting it, so tokens only showed up at the next
        hard event and the reply looked stuck. emit() already throttles to
        0.2s, so the paint rate stays bounded.
        """
        if self._closing:
            # Teardown: no UI work at all. Anything here touches
            # page.session and raises "destroyed session".
            return
        controls: list[ft.Control] = []
        if not self.turns:
            controls.append(self._welcome())
        for idx, turn in enumerate(self.turns):
            controls.append(
                self._render_user(turn, idx)
                if turn.get("role") == "user"
                else self._render_assistant(turn)
            )
        if state.scheduled_scrapes:
            controls.append(self._render_schedules())
        self._list.controls = controls
        # Cheap, and keeps the pill honest as the router comes up.
        self.refresh_model_chip()
        try:
            self.page.update()
        except Exception:
            # The session may already be gone; that is teardown, not a bug.
            pass
        if self._pinned:
            try:
                self.page.run_task(self._scroll_to_bottom)
            except Exception:
                # run_task evaluates page.session while building the
                # coroutine, so a dead session raises here and would
                # otherwise leak an un-awaited coroutine into the turn.
                pass

    async def _scroll_to_bottom(self):
        # ScrollableControl.scroll_to is async in flet 1.0
        try:
            await self._list.scroll_to(offset=-1, duration=200)
        except Exception:
            pass

    def _welcome(self) -> ft.Container:
        kids: list[ft.Control] = [
            ft.Container(
                content=ft.Icon(_CHAT, size=44, color=AppColors.PRIMARY),
                alignment=ft.Alignment.CENTER,
                margin=ft.Margin(0, 40, 0, 8),
            ),
            ft.Text(
                "Ask me anything",
                size=tokens.FONT_LG,
                weight=ft.FontWeight.W_700,
                font_family="Outfit",
            ),
            ft.Text(
                "I can search across 10 engines, fetch and save pages, and "
                "download media myself, and show you what I find.",
                size=tokens.FONT_SM,
                color=ft.Colors.ON_SURFACE_VARIANT,
                text_align=ft.TextAlign.CENTER,
                style=ft.TextStyle(height=1.4),
            ),
            ft.Container(height=tokens.SPACE_SM),
        ]
        chips: list[ft.Control] = []
        if self.ctx.get("url"):
            chips.append(
                ft.Container(
                    content=ft.Text(
                        f"📄 Describe this page: {_domain(str(self.ctx['url']))}",
                        size=tokens.FONT_XS,
                        color=AppColors.PRIMARY,
                    ),
                    padding=ft.Padding(10, 6, 10, 6),
                    border_radius=tokens.RADIUS_PILL,
                    border=ft.Border.all(
                        1, ft.Colors.with_opacity(0.3, AppColors.PRIMARY)
                    ),
                    ink=True,
                    on_click=lambda e: self.send(
                        f"Describe this page for me: {self.ctx.get('url')}"
                    ),
                )
            )
        for suggestion in _SUGGESTIONS:
            chips.append(
                ft.Container(
                    content=ft.Text(
                        suggestion, size=tokens.FONT_XS, color=AppColors.PRIMARY
                    ),
                    padding=ft.Padding(10, 6, 10, 6),
                    border_radius=tokens.RADIUS_PILL,
                    border=ft.Border.all(
                        1, ft.Colors.with_opacity(0.3, AppColors.PRIMARY)
                    ),
                    ink=True,
                    on_click=lambda e, q=suggestion: self.send(q),
                )
            )
        kids.append(ft.Row(chips, spacing=6, wrap=True, run_spacing=6))
        return ft.Container(
            content=ft.Column(kids, horizontal_alignment=ft.CrossAxisAlignment.CENTER),
            expand=True,
        )

    def _render_user(self, turn: dict, index: int) -> ft.Container:
        bubble_width = min(300, (getattr(self.page, "width", None) or 400) * 0.72)
        return ft.Row(
            [
                ft.GestureDetector(
                    on_long_press=lambda e, i=index: self._delete_turn(i),
                    content=ft.Container(
                        content=ft.Text(
                            turn.get("text", ""),
                            size=tokens.FONT_SM,
                            color=ft.Colors.WHITE,
                            selectable=True,
                        ),
                        padding=ft.Padding(12, 8, 12, 8),
                        border_radius=ft.BorderRadius(16, 16, 4, 16),
                        bgcolor=AppColors.PRIMARY,
                        width=bubble_width,
                    ),
                )
            ],
            alignment=ft.MainAxisAlignment.END,
        )

    def _render_assistant(self, turn: dict) -> ft.Container:
        kids: list[ft.Control] = []

        if (turn.get("thought") or "").strip():
            thinking_open = bool(turn.get("thought_open", True))
            still_thinking = bool(turn.get("partial")) and not turn.get("text")
            elapsed = _thought_seconds(turn)
            label = (
                "Thinking…"
                if still_thinking
                else f"Thought for {elapsed}s"
                if elapsed
                else "Thought it through"
            )
            block: list[ft.Control] = [
                ft.Row(
                    [
                        ft.Icon(
                            ft.Icons.PSYCHOLOGY_ROUNDED,
                            size=tokens.ICON_SM,
                            color=AppColors.WARNING
                            if still_thinking
                            else AppColors.SUCCESS,
                        ),
                        ft.Text(
                            label,
                            size=tokens.FONT_XS,
                            color=ft.Colors.ON_SURFACE_VARIANT,
                            weight=ft.FontWeight.W_500,
                        ),
                        ft.Container(expand=True),
                        ft.Icon(
                            ft.Icons.EXPAND_LESS_ROUNDED
                            if thinking_open
                            else ft.Icons.EXPAND_MORE_ROUNDED,
                            size=tokens.ICON_SM,
                            color=ft.Colors.ON_SURFACE_VARIANT,
                        ),
                    ],
                    spacing=6,
                )
            ]
            if thinking_open:
                block.append(
                    ft.Text(
                        turn["thought"].strip(),
                        size=tokens.FONT_XS,
                        color=ft.Colors.ON_SURFACE_VARIANT,
                        selectable=True,
                    )
                )
            kids.append(
                ft.Container(
                    content=ft.Column(block, spacing=4, tight=True),
                    bgcolor=ft.Colors.with_opacity(0.06, ft.Colors.ON_SURFACE),
                    border_radius=tokens.RADIUS_SM,
                    padding=ft.Padding(8, 8, 8, 8),
                    ink=True,
                    tooltip="Tap to expand or collapse",
                    on_click=lambda e, t=turn: self._toggle_thought(t),
                )
            )
        for row in turn.get("steps_rows", []):
            if row["state"] == "running":
                icon = ft.Row(
                    [ft.ProgressRing(width=12, height=12, stroke_width=2)], tight=True
                )
            elif row["state"] == "error":
                icon = ft.Icon(
                    ft.Icons.ERROR_OUTLINE_ROUNDED, size=14, color=AppColors.ERROR
                )
            else:
                icon = ft.Icon(
                    ft.Icons.CHECK_CIRCLE_ROUNDED, size=14, color=AppColors.SUCCESS
                )
            label = row["label"]
            if row["state"] == "done" and row.get("count"):
                label = label.removesuffix("…")
                label += f": {row['count']} results"
            if row["state"] == "error":
                # Show what actually went wrong. "no results" for a denied
                # write, a network failure and an empty search told the user
                # nothing they could act on.
                detail = str(row.get("error") or "").strip()
                if not detail:
                    detail = "no results"
                elif len(detail) > 90:
                    detail = detail[:90].rstrip() + "…"
                label = f"{label.rstrip('…')}: {detail}"
            kids.append(
                ft.Row(
                    [
                        icon,
                        ft.Text(
                            label,
                            size=tokens.FONT_XS,
                            color=ft.Colors.ON_SURFACE_VARIANT,
                        ),
                    ],
                    spacing=6,
                    vertical_alignment=ft.CrossAxisAlignment.CENTER,
                )
            )

        # approval gate row
        if self._confirm and self._confirm[1].get("decision") is None:
            label = self._confirm[1]["label"]
            kids.append(
                ft.Container(
                    content=ft.Column(
                        [
                            ft.Text(
                                label,
                                size=tokens.FONT_XS,
                                color=AppColors.WARNING,
                                max_lines=2,
                                overflow=ft.TextOverflow.ELLIPSIS,
                            ),
                            ft.Row(
                                [
                                    ft.FilledButton(
                                        "Allow",
                                        icon=ft.Icons.CHECK_ROUNDED,
                                        on_click=lambda e: self._confirm_decision(
                                            "allow"
                                        ),
                                    ),
                                    ft.TextButton(
                                        "No",
                                        on_click=lambda e: self._confirm_decision(
                                            "deny"
                                        ),
                                    ),
                                ],
                                spacing=8,
                            ),
                        ],
                        spacing=4,
                        tight=True,
                    ),
                    padding=ft.Padding(10, 6, 10, 6),
                    border_radius=tokens.RADIUS_MD,
                    bgcolor=ft.Colors.with_opacity(0.08, AppColors.WARNING),
                )
            )

        for block in turn.get("cards", []):
            kids.append(self._render_cards(block))

        if turn.get("text"):
            kids.append(
                ft.Markdown(
                    turn["text"],
                    selectable=True,
                    extension_set="gitHubWeb",
                    on_tap_link=lambda e: self._open_in_app(e.data),
                )
            )

        if turn.get("partial") and not turn.get("text") and not turn.get("steps_rows"):
            kids.append(
                ft.Row(
                    [
                        ft.ProgressRing(width=12, height=12, stroke_width=2),
                        ft.Text(
                            "Working…",
                            size=tokens.FONT_XS,
                            color=ft.Colors.ON_SURFACE_VARIANT,
                        ),
                    ],
                    spacing=6,
                )
            )

        if turn.get("error") == "credits":
            kids.append(
                ft.Row(
                    [
                        ft.Text(
                            "Out of assistant credits. Assistant replies need credits.",
                            size=tokens.FONT_XS,
                            color=AppColors.WARNING,
                        ),
                        ft.TextButton(
                            "Get credits",
                            on_click=lambda e: show_wallet_dialog(self.page),
                            style=ft.ButtonStyle(padding=ft.Padding(0, 0, 0, 0)),
                        ),
                    ],
                    spacing=4,
                )
            )
        elif turn.get("error") == "midstream":
            kids.append(
                ft.Text(
                    "⚠ Connection lost mid-answer. What arrived was still charged.",
                    size=tokens.FONT_XS,
                    color=AppColors.WARNING,
                )
            )
        elif turn.get("error") == "rate_limited":
            suggestion = str(turn.get("suggestion") or "")
            kids.append(
                ft.Column(
                    [
                        ft.Text(
                            str(turn.get("error_message") or "")
                            or "Rate limited right now.",
                            size=tokens.FONT_XS,
                            color=AppColors.WARNING,
                        ),
                        *(
                            [
                                ft.TextButton(
                                    f"Use {suggestion} and retry",
                                    icon=ft.Icons.AUTO_AWESOME_ROUNDED,
                                    on_click=lambda e, mid=suggestion: (
                                        self._switch_model_and_retry(mid)
                                    ),
                                    style=ft.ButtonStyle(
                                        padding=ft.Padding(0, 0, 0, 0)
                                    ),
                                )
                            ]
                            if suggestion
                            else []
                        ),
                        ft.TextButton(
                            "Ask again",
                            icon=ft.Icons.REFRESH_ROUNDED,
                            on_click=lambda e: self._retry_last(),
                            style=ft.ButtonStyle(padding=ft.Padding(0, 0, 0, 0)),
                        ),
                    ],
                    spacing=2,
                    tight=True,
                    alignment=ft.MainAxisAlignment.START,
                )
            )
        elif turn.get("error") == "empty":
            kids.append(
                ft.Column(
                    [
                        ft.Text(
                            "That model replied with nothing. You were not "
                            "charged for it.",
                            size=tokens.FONT_XS,
                            color=ft.Colors.ON_SURFACE_VARIANT,
                        ),
                        ft.TextButton(
                            "Ask again",
                            icon=ft.Icons.REFRESH_ROUNDED,
                            on_click=lambda e: self._retry_last(),
                            style=ft.ButtonStyle(padding=ft.Padding(0, 0, 0, 0)),
                        ),
                    ],
                    spacing=2,
                    tight=True,
                    alignment=ft.MainAxisAlignment.START,
                )
            )
        elif turn.get("error") == "unavailable":
            kids.append(
                ft.Text(
                    "Assistant unavailable. Classic search, scraping and "
                    "downloads still work.",
                    size=tokens.FONT_XS,
                    color=ft.Colors.ON_SURFACE_VARIANT,
                    italic=True,
                )
            )
        if turn.get("stopped"):
            kids.append(
                ft.Text(
                    "⏹ Stopped.",
                    size=tokens.FONT_XS,
                    color=ft.Colors.ON_SURFACE_VARIANT,
                )
            )

        if turn.get("related"):
            pills = [
                ft.Container(
                    content=ft.Text(
                        q,
                        size=tokens.FONT_XS,
                        color=AppColors.PRIMARY,
                        max_lines=1,
                        overflow=ft.TextOverflow.ELLIPSIS,
                    ),
                    padding=ft.Padding(8, 4, 8, 4),
                    border_radius=tokens.RADIUS_PILL,
                    border=ft.Border.all(
                        1, ft.Colors.with_opacity(0.3, AppColors.PRIMARY)
                    ),
                    ink=True,
                    tooltip=f"Search: {q}",
                    on_click=lambda e, qq=q: self.send(qq),
                )
                for q in turn["related"]
            ]
            kids.append(ft.Row(pills, spacing=6, wrap=True, run_spacing=4))

        # receipt — every assistant turn shows what it cost and who answered
        if turn.get("cost"):
            receipt = (
                f"Assistant used {turn.get('steps', 0)} steps · {turn['cost']} credits"
            )
            if turn.get("model"):
                receipt += f" · {turn['model']}"
            if turn.get("served_by") == "gateway":
                receipt += " (gateway)"
            if turn.get("stopped"):
                receipt += " (stopped early)"
            kids.append(
                ft.Text(
                    receipt,
                    size=9,
                    color=ft.Colors.with_opacity(0.6, ft.Colors.ON_SURFACE),
                )
            )
        elif turn.get("receipt"):
            kids.append(ft.Text(turn["receipt"], size=9, color=AppColors.WARNING))

        return ft.Container(
            content=ft.Column(kids, spacing=tokens.SPACE_XS, tight=True),
            padding=ft.Padding(4, 2, 4, 2),
        )

    def _render_cards(self, block: dict) -> ft.Container:
        results: list[SearchResult] = block.get("results") or []
        kind = block.get("kind", "web")
        rows: list[ft.Control] = []
        for r in results[:8]:
            thumb = (r.thumbnail or r.image_url or "") if r else ""
            rows.append(
                ft.GestureDetector(
                    on_tap=lambda e, res=r: self._open_result(res, kind),
                    content=ft.Row(
                        [
                            (
                                ft.Container(
                                    content=ft.Image(
                                        src=thumb,
                                        width=30,
                                        height=30,
                                        fit=ft.BoxFit.COVER,
                                        border_radius=ft.BorderRadius(6, 6, 6, 6),
                                        error_content=ft.Icon(
                                            _KIND_ICONS.get(
                                                kind, ft.Icons.LANGUAGE_ROUNDED
                                            ),
                                            size=14,
                                            color=AppColors.PRIMARY,
                                        ),
                                    ),
                                    clip_behavior=ft.ClipBehavior.HARD_EDGE,
                                )
                                if thumb
                                else ft.Icon(
                                    _KIND_ICONS.get(kind, ft.Icons.LANGUAGE_ROUNDED),
                                    size=14,
                                    color=AppColors.PRIMARY,
                                )
                            ),
                            ft.Text(
                                r.title or r.url,
                                size=tokens.FONT_XS,
                                max_lines=1,
                                overflow=ft.TextOverflow.ELLIPSIS,
                                expand=True,
                                weight=ft.FontWeight.W_500,
                            ),
                            ft.Text(
                                _domain(r.url or ""),
                                size=9,
                                color=ft.Colors.ON_SURFACE_VARIANT,
                                max_lines=1,
                            ),
                        ],
                        spacing=6,
                        vertical_alignment=ft.CrossAxisAlignment.CENTER,
                    ),
                )
            )
        body = ft.Column(rows, spacing=4, tight=True, scroll=ft.ScrollMode.AUTO)
        return ft.Container(
            content=ft.Column(
                [
                    ft.Text(
                        f"Found {len(results)} {kind} result"
                        f"{'' if len(results) == 1 else 's'}",
                        size=tokens.FONT_XS,
                        weight=ft.FontWeight.W_700,
                        color=AppColors.PRIMARY,
                    ),
                    body,
                    *(
                        [
                            ft.TextButton(
                                f"View {len(results)} results in Results",
                                icon=ft.Icons.LIST_ROUNDED,
                                on_click=lambda e, rs=results, k=kind: self._open_results(
                                    rs, k
                                ),
                                style=ft.ButtonStyle(
                                    padding=ft.Padding(0, 0, 0, 0)
                                ),
                            )
                        ]
                        if results
                        else []
                    ),
                ],
                spacing=3,
                tight=True,
            ),
            padding=ft.Padding(10, 6, 10, 6),
            border_radius=tokens.RADIUS_MD,
            bgcolor=ft.Colors.with_opacity(0.05, AppColors.PRIMARY),
        )

    def _render_schedules(self) -> ft.Container:
        rows = []
        for task in state.scheduled_scrapes:
            rows.append(
                ft.Row(
                    [
                        ft.Text(
                            task.get("url", ""),
                            size=tokens.FONT_XS,
                            max_lines=1,
                            overflow=ft.TextOverflow.ELLIPSIS,
                            expand=True,
                        ),
                        ft.IconButton(
                            icon=ft.Icons.DELETE_OUTLINE_ROUNDED,
                            icon_size=15,
                            tooltip="Cancel scheduled crawl",
                            on_click=lambda e, task=task: self._cancel_schedule(
                                task.get("url") or ""
                            ),
                        ),
                    ],
                    vertical_alignment=ft.CrossAxisAlignment.CENTER,
                )
            )
        return ft.Container(
            content=ft.Column(
                [
                    ft.Text(
                        "Scheduled crawls (run while the app is open)",
                        size=tokens.FONT_XS,
                        weight=ft.FontWeight.W_600,
                    ),
                    *rows,
                ],
                spacing=2,
                tight=True,
            ),
            padding=ft.Padding(8, 6, 8, 6),
            border_radius=tokens.RADIUS_MD,
            bgcolor=ft.Colors.with_opacity(0.04, AppColors.PRIMARY),
        )

    def _cancel_schedule(self, url: str) -> None:
        ctrl = getattr(self.page, "_ddgs_controller", None)
        if ctrl:
            self.page.run_task(ctrl.cancel_scheduled_scrape, url)

    def _open_result(self, r, kind: str) -> None:
        """Open an assistant-found result exactly like a normal result card."""
        from components.results.detail_sheet import _show_result_sheet

        search_type = {
            "web": "text",
            "images": "images",
            "videos": "videos",
            "news": "news",
            "books": "books",
        }.get(kind, "text")
        _show_result_sheet(self.page, r, search_type)

    def _open_results(self, results: list, kind: str) -> None:
        """Send the assistant's results to the app Results screen and minimize."""
        ctrl = getattr(self.page, "_ddgs_controller", None)
        if ctrl:
            ctrl.open_assistant_results(results, kind)
            self.close()

    def _open_in_app(self, url: str) -> None:
        """Open a link the DDGS way: in-app extracted preview (browser inside)."""

        async def _go() -> None:
            if not url:
                return
            from components.results.content_fetcher import _fetch_and_show

            try:
                await _fetch_and_show(self.page, url)
            except Exception:
                await launch_url(url)

        self.page.run_task(_go)


def _credits_color(credits: int) -> str:
    if credits > 20:
        return AppColors.SUCCESS
    if credits >= 5:
        return AppColors.WARNING
    return AppColors.ERROR


def open_chat_view(page: ft.Page, ctx: dict | None = None) -> None:
    """Open or re-expand the Assistant, reusing the retained session.

    A minimized session is restored rather than rebuilt, so the user lands
    back on the exact conversation they left, not a fresh one.
    """
    if state.chat_open:
        return
    existing = getattr(page, "_chat_session", None)
    if isinstance(existing, ChatSession):
        existing.restore()
        if ctx and ctx.get("auto"):
            if ctx.get("url"):
                existing.send(f"Describe this page for me: {ctx['url']}")
            elif ctx.get("question"):
                existing.send(ctx["question"])
        return
    session = ChatSession(page, ctx)
    page._chat_session = session
    state.chat_open = True
    state.chat_minimized = False
    page.views.append(session.view)
    try:
        page.update()
    except Exception:
        pass
    if ctx and ctx.get("auto"):
        if ctx.get("url"):
            session.send(f"Describe this page for me: {ctx['url']}")
        elif ctx.get("question"):
            session.send(ctx["question"])
