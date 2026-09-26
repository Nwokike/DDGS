"""Assistant chat - the agentic surface (FAB entry).

Imperative View (reader pattern): built once, refreshed from session state
with >=0.2s throttled streaming inside a ListView that flet auto-scrolls
(suspended while the user scrolls up). Agent loop lives in
services/chat_agent; this file owns presentation:
  - one meta line per finished turn: steps, credits, model, step expander
  - live tool steps collapse when the turn ends; thinking starts collapsed
  - flat result rows with one "Open N results" action
  - approve/deny card before any file-writing tool (auto-denies in 2m)
  - long-press a message for copy/edit/regenerate/delete; Clear chat in
    the app bar
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
from core import tokens, ui
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

_SUGGESTION_ROWS = [
    (ft.Icons.NEWSPAPER_ROUNDED, "What happened in tech this week?"),
    (ft.Icons.SHIELD_ROUNDED, "Find me the best free privacy tools"),
    (
        ft.Icons.CODE_ROUNDED,
        "Scrape the BBC News homepage and save it as HTML",
    ),
    (
        ft.Icons.SAVE_ROUNDED,
        "Find the best page about solar power and save it as Markdown",
    ),
    (ft.Icons.LIGHTBULB_ROUNDED, "Explain a topic like I'm 12"),
    (ft.Icons.DOWNLOAD_ROUNDED, "Download a video or image from a link"),
]


def _describe_prompt(url: str) -> str:
    """The one describe-this-page prompt; it used to be written three times."""
    return f"Describe this page for me: {url}"


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

    The session is bound to a conversation id and keeps ONE transcript:
    `turns`, the list the user sees. The flat `{"role", "content"}` pairs
    that get written to disk and handed to the model are projected from it
    by `conversation_service.flat_from_turns`, never held beside it. A
    second list in memory is how a deleted message used to survive: the
    view dropped it, the other list did not, and disk wrote it back.
    """

    def __init__(self, page: ft.Page, ctx: dict | None = None):
        from services import conversation_service as conversations

        self.page = page
        self.ctx = ctx or {}
        self.conversation_id: str = conversations.ensure_active()
        saved = conversations.load_conversation(self.conversation_id) or {}
        self.turns: list[dict] = _turns_from_messages(saved.get("messages") or [])
        self.busy = False
        self.cancel = asyncio.Event()
        # Two independent clocks. Sharing one meant a text flush reset the
        # thought throttle and vice versa, so thinking could silently starve
        # for 500ms every time a text token landed.
        self._last_text_flush = 0.0
        self._last_thought_flush = 0.0
        self._current: dict | None = None
        # Set once teardown starts; every UI touch afterwards is a no-op.
        self._closing = False
        self._confirm: tuple[asyncio.Event, dict] | None = None

        # ── Controls ────────────────────────────────────────────────
        # ListView with auto_scroll: flet suspends pinning while the user
        # scrolls up and resumes at the end. The old hand-rolled pin detector
        # read attributes flet 1.0.1 does not have, so it never yielded and
        # yanked the list to the bottom mid-read.
        self._list = ft.ListView(
            controls=[],
            spacing=tokens.SPACE_LG,
            expand=True,
            auto_scroll=True,
            padding=ft.Padding.symmetric(horizontal=12),
        )
        self.field = ft.TextField(
            hint_text="Ask anything",
            expand=True,
            dense=True,
            min_lines=1,
            max_lines=5,
            shift_enter=True,
            fill_color=ft.Colors.with_opacity(0.06, ft.Colors.ON_SURFACE),
            content_padding=ft.Padding(12, 8, 12, 8),
            border=ft.OutlineInputBorder(border_radius=tokens.RADIUS_LG),
        )
        # One circular button, two faces: send when idle, stop when busy.
        # The transcript's "Working" ring covers first-token liveness.
        self.send_btn = ft.IconButton(
            icon=ft.Icons.SEND_ROUNDED,
            icon_color=ft.Colors.WHITE,
            tooltip="Send",
            style=ft.ButtonStyle(
                shape=ft.CircleBorder(),
                bgcolor=AppColors.PRIMARY,
            ),
            on_click=lambda e: self._on_composer_button(e),
        )
        self.field.on_submit = lambda e: self._send_from_field()

        credits_color = _credits_color(state.credits_remaining)
        self.credits_chip = ft.Container(
            content=ft.Row(
                [
                    ft.Icon(_CHAT, size=tokens.ICON_SM, color=credits_color),
                    ft.Text(
                        str(state.credits_remaining),
                        size=tokens.FONT_XS,
                        weight=ft.FontWeight.W_600,
                        color=credits_color,
                    ),
                ],
                spacing=2,
                tight=True,
            ),
            # Same geometry as the model pill so the two read as one family;
            # the colour stays because it carries the balance signal.
            padding=ft.Padding(7, 3, 7, 3),
            border_radius=tokens.RADIUS_PILL,
            bgcolor=ft.Colors.with_opacity(0.1, credits_color),
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
                # Creation first, history next, then the readouts, and the
                # model selector last (owner's call: it is the pill people
                # reach for most).
                ft.IconButton(
                    icon=ft.Icons.ADD_ROUNDED,
                    icon_size=18,
                    icon_color=AppColors.PRIMARY,
                    tooltip="New chat",
                    on_click=lambda e: self.new_conversation(),
                ),
                self._history_button_control(),
                self.credits_chip,
                self.model_chip,
                ft.Container(width=6),
            ],
            bgcolor=ft.Colors.TRANSPARENT,
            elevation=0,
        )

        composer = ft.Container(
            content=ft.Row(
                [self.field, self.send_btn],
                vertical_alignment=ft.CrossAxisAlignment.END,
                spacing=2,
            ),
            padding=ft.Padding(10, 6, 10, 10),
        )

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
                self._model_history(),
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

    async def ask_confirm(self, label: str, detail: str = "") -> bool:
        """Inline approve/deny gate for file-writing tools. Times out to deny.

        `detail` carries the arguments the label hides: the full URL, the
        crawl interval, the page count, the quality. Without it the card
        asks the user to bless a recurring background job they cannot see.

        The gate is cleared in a finally block. Leaving it populated after
        a timeout or a cancellation kept the Allow/No controls on screen for
        an operation that was already resolved as denied, and clicking
        Allow then did nothing, which made a real safety gate look broken.
        """
        event = asyncio.Event()
        self._confirm = (event, {"label": label, "detail": detail, "decision": None})
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

    def _clear_chat(self) -> None:
        if not self.turns:
            return
        self.turns = []
        self._persist_history()
        self._render(force=True)
        self._snack("Chat cleared")

    def _model_history(self) -> list[dict]:
        """The flat transcript the agent consumes, projected on demand.

        Same function, same order, same trimming as the save path: what the
        model is told the user said is what the file says the user said.
        """
        from services import conversation_service as conversations

        return conversations.flat_from_turns(self.turns)

    def _delete_turn(self, index: int) -> None:
        """Delete an exchange from the transcript.

        `turns` is the only transcript, so this is the whole operation - the
        screen and the file are both derived from it. The previous version
        had to translate a view index into an `agent_history` index first;
        when that translation was wrong the message vanished on screen and
        came straight back from disk on the next switch.
        """
        if not (0 <= index < len(self.turns)):
            return
        role = self.turns[index].get("role")
        if role not in ("user", "assistant"):
            # Error/empty rows carry no text: a view-only row.
            del self.turns[index]
            self._render(force=True)
            return

        # Drop the whole exchange, not one side of it: a question with no
        # answer, or an answer with no question, reads as a glitch.
        start, end = index, index + 1
        if role == "user":
            if end < len(self.turns) and self.turns[end].get("role") == "assistant":
                end += 1
        elif start > 0 and self.turns[start - 1].get("role") == "user":
            # Include the question that asked for this answer, otherwise
            # regenerate leaves the old question in the transcript and the
            # resent one is appended alongside it.
            start -= 1

        del self.turns[start:end]
        self._persist_history()
        self._render(force=True)

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
        messages = conversations.flat_from_turns(self.turns)[
            -conversations.CONVERSATION_MESSAGE_CAP :
        ]

        # Schedule the disk write directly. There is no observable mirror
        # to update first: writing one used to mean a dead session could
        # stop the file write before it was ever scheduled.
        try:
            self.page.run_task(self._save_history, conversation_id, messages)
        except Exception:
            logger.debug("could not schedule the conversation save")

    async def _save_history(self, conversation_id: str, messages: list) -> None:
        """Persist one conversation. Never raises into the caller.

        Async because `page.run_task` refuses a plain function, and a throw
        here would surface as an unretrieved task exception during
        teardown - exactly the crash this replaced.
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
        self._remember_active()
        self._render(force=True)

    def _toggle_thought(self, turn: dict) -> None:
        turn["thought_open"] = not bool(turn.get("thought_open", False))

    def _toggle_steps(self, turn: dict) -> None:
        turn["steps_open"] = not bool(turn.get("steps_open"))
        self._render(force=True)

    def _retry_last(self) -> None:
        """Re-send the last user message of the active chat."""
        for turn in reversed(self.turns):
            if turn.get("role") == "user" and str(turn.get("text") or "").strip():
                self.send(turn["text"])
                return
        self._snack("There is nothing to retry")

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
        self._remember_active()
        self._render(force=True)

    @property
    def conversation_id(self) -> str:
        """The live chat id. One owner: `state.active_conversation`.

        The session used to keep its own copy, so `self.conversation_id`
        and `state.active_conversation` could disagree - the prune guard
        protected one while a save wrote the other. Delegating removes the
        second owner rather than trying to keep them in sync.
        """
        return state.active_conversation

    @conversation_id.setter
    def conversation_id(self, value: str) -> None:
        state.active_conversation = value

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
        """Past conversations get a history icon, not a hamburger: the
        hamburger implies navigation or settings, and this sheet is only
        the chat log (LM Router's header pair, history + plus).

        It stays a modal rebuilt from disk every time: a popup menu froze
        its items when the session was created, so a deleted chat kept
        showing until the whole screen refreshed. A modal is also the right
        surface: 50 chats do not fit a dropdown, and a truncated list means
        the older files you can still open are invisible.
        """
        return ft.IconButton(
            icon=ft.Icons.HISTORY_ROUNDED,
            icon_size=18,
            icon_color=AppColors.PRIMARY,
            tooltip="Chat history",
            on_click=lambda e: self._open_history_dialog(),
        )

    @staticmethod
    def _history_row(
        icon: ft.IconData,
        title: str,
        subtitle: str,
        trailing: ft.Control | None,
        *,
        accent: bool = False,
        on_click=None,
    ) -> ft.Container:
        """One line of the history modal; the shape lives in core.ui.

        The active chat is marked by colour and weight, not a filled block.
        """
        return ui.setting_row(
            icon,
            title,
            subtitle,
            trailing,
            accent=accent,
            on_click=on_click,
            subtitle_lines=1,
        )

    def _open_history_dialog(self) -> None:
        """Build and show the chat list as a modal, newest first, all of them.

        Rebuilt from disk on every open, and shaped like the credits
        dialog so the app's modals look like one family.
        """
        from services import conversation_service as conversations

        rows = conversations.list_conversations()
        page_height = getattr(self.page, "height", None) or 700

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

        items: list[ft.Control] = [
            self._history_row(
                ft.Icons.ADD_ROUNDED,
                "New chat",
                "Start a fresh conversation",
                ft.Icon(
                    ft.Icons.CHEVRON_RIGHT_ROUNDED,
                    size=tokens.ICON_SM,
                    color=ft.Colors.with_opacity(0.4, ft.Colors.ON_SURFACE_VARIANT),
                ),
                on_click=_new_chat,
            ),
            ft.Divider(
                height=1,
                thickness=1,
                color=ft.Colors.with_opacity(0.18, ft.Colors.OUTLINE),
            ),
        ]

        if not rows:
            items.append(
                ft.Container(
                    content=ft.Text(
                        "No saved chats yet.",
                        size=tokens.FONT_SM,
                        color=ft.Colors.ON_SURFACE_VARIANT,
                    ),
                    padding=ft.Padding(4, tokens.SPACE_MD, 4, tokens.SPACE_MD),
                )
            )

        for row in rows:
            conversation_id = str(row.get("id") or "")
            is_active = conversation_id == self.conversation_id
            title = str(row.get("title") or "New chat")
            items.append(
                self._history_row(
                    ft.Icons.CHAT_BUBBLE_OUTLINE_ROUNDED,
                    title,
                    conversations.summarize(row),
                    ft.Row(
                        [
                            ft.Icon(
                                ft.Icons.CHECK_CIRCLE_ROUNDED,
                                size=tokens.ICON_SM,
                                color=ft.Colors.PRIMARY,
                            )
                            if is_active
                            else ft.IconButton(
                                icon=ft.Icons.DELETE_OUTLINE_ROUNDED,
                                icon_size=tokens.ICON_SM,
                                icon_color=AppColors.ERROR,
                                tooltip="Delete this chat",
                                on_click=_delete_chat(conversation_id),
                            )
                        ],
                        spacing=0,
                        tight=True,
                    ),
                    accent=is_active,
                    on_click=_open_chat(conversation_id),
                )
            )

        # Scrollable with a bounded height: 50 rows must not push the
        # modal off the screen on a phone.
        self.page.show_dialog(
            ft.AlertDialog(
                title=ft.Text("Chat history", font_family="Outfit"),
                content=ft.Container(
                    content=ft.Column(
                        controls=items,
                        spacing=0,
                        tight=True,
                        scroll=ft.ScrollMode.AUTO,
                    ),
                    width=400,
                    height=min(len(items) * 64 + 16, page_height * 0.6),
                    padding=ft.Padding(4, 4, 4, 4),
                ),
                actions=[
                    ft.TextButton(
                        "Delete all chats",
                        icon=ft.Icons.DELETE_SWEEP_OUTLINED,
                        icon_color=AppColors.ERROR,
                        style=ft.ButtonStyle(color=AppColors.ERROR),
                        on_click=lambda e: (_close(), self._confirm_delete_all()),
                    ),
                    ft.TextButton("Close", on_click=_close),
                ],
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
        """One button, two faces: send when idle, stop when busy."""
        self.send_btn.icon = ft.Icons.STOP_ROUNDED if busy else ft.Icons.SEND_ROUNDED
        self.send_btn.tooltip = "Stop" if busy else "Send"
        self.send_btn.style = ft.ButtonStyle(
            shape=ft.CircleBorder(),
            bgcolor=AppColors.ERROR if busy else AppColors.PRIMARY,
        )
        try:
            self.send_btn.update()
        except Exception:
            pass

    def _on_composer_button(self, e=None) -> None:
        if self.busy:
            self.stop()
        else:
            self._send_from_field()

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
                # ai_service failures carry consumer-facing copy; show it
                # instead of flattening everything into a generic message.
                error_message=str(data.get("message") or ""),
                steps=data.get("steps", self._current.get("steps", 0)),
                cost=data.get("cost", self._current.get("cost", 0)),
            )
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
                else self._render_assistant(turn, idx)
            )
        if state.scheduled_scrapes:
            controls.append(self._render_schedules())
        self._list.controls = controls
        # Cheap, and keeps the pill honest as the router comes up.
        self.refresh_model_chip()
        try:
            # Patch the transcript only: a 5Hz whole-page push redrew the
            # app bar and composer for every streamed token.
            self._list.update()
        except Exception:
            # The session may already be gone; that is teardown, not a bug.
            pass

    def _welcome(self) -> ft.Container:
        # Four tappable starter rows, not a paragraph over pills: options
        # are prepopulated (NN/G), so the empty state teaches capability by
        # offering actions the user can fire immediately.
        kids: list[ft.Control] = [
            ft.Container(
                content=ft.Icon(_CHAT, size=44, color=AppColors.PRIMARY),
                alignment=ft.Alignment.CENTER,
                margin=ft.Margin(0, 40, 0, 8),
            ),
            ft.Text(
                "What I can do",
                size=tokens.FONT_LG,
                weight=ft.FontWeight.W_700,
                font_family="Outfit",
                text_align=ft.TextAlign.CENTER,
            ),
        ]
        starters: list[tuple[ft.IconData, str, str]] = []
        if self.ctx.get("url"):
            url = str(self.ctx.get("url") or "")
            starters.append(
                (
                    ft.Icons.LANGUAGE_ROUNDED,
                    f"Describe this page: {_domain(url)}",
                    _describe_prompt(url),
                )
            )
        for icon, prompt in _SUGGESTION_ROWS[: 5 - len(starters)]:
            starters.append((icon, prompt, prompt))
        kids.append(
            ft.Column(
                [
                    ui.setting_row(
                        icon,
                        label,
                        trailing=ft.Icon(
                            ft.Icons.CHEVRON_RIGHT_ROUNDED,
                            size=tokens.ICON_SM,
                            color=ft.Colors.ON_SURFACE_VARIANT,
                        ),
                        on_click=lambda e, q=prompt: self.send(q),
                    )
                    for icon, label, prompt in starters
                ],
                spacing=0,
                tight=True,
            )
        )
        return ft.Container(
            content=ft.Column(
                kids, horizontal_alignment=ft.CrossAxisAlignment.STRETCH
            ),
            expand=True,
        )

    # ── Message actions ─────────────────────────────────────────────────
    # Deliberately a visible row of small buttons. Long press alone is not
    # discoverable and has no keyboard equivalent, so it stays as a shortcut
    # rather than the only way in.

    async def _copy_text(self, text: str) -> None:
        try:
            clipboard = ft.Clipboard()
            if clipboard not in self.page.services:
                self.page.services.append(clipboard)
            await clipboard.set(text)
            self._snack("Copied to clipboard")
        except Exception:
            self._snack("Could not copy that", "error")

    def _copy_turn(self, index: int) -> None:
        if not (0 <= index < len(self.turns)):
            return
        self.page.run_task(
            self._copy_text, str(self.turns[index].get("text") or "")
        )

    def _edit_turn(self, index: int) -> None:
        """Prefill the composer with a sent message so it can be changed.

        The message leaves the transcript with it: editing in place would
        silently rewrite what the assistant answered to, and the model
        would carry on from a question that no longer exists.
        """
        if self.busy or not (0 <= index < len(self.turns)):
            return
        turn = self.turns[index]
        if turn.get("role") != "user":
            return
        text = str(turn.get("text") or "")
        self._delete_turn(index)
        self.field.value = text
        try:
            self.field.update()
            self.field.focus()
        except Exception:
            pass

    def _regenerate(self, index: int) -> None:
        """Re-ask the question this answer responded to."""
        if self.busy or not (0 <= index < len(self.turns)):
            return
        turn = self.turns[index]
        if turn.get("role") != "assistant":
            return
        question = ""
        for previous in reversed(self.turns[:index]):
            if previous.get("role") == "user":
                question = str(previous.get("text") or "")
                break
        if not question:
            self._snack("There is no question to re-ask")
            return
        # Drop the old answer first: it would otherwise sit above the new
        # one and read as two answers to the same question.
        self._delete_turn(index)
        self.send(question)

    def _confirm_delete_turn(self, index: int) -> None:
        if not (0 <= index < len(self.turns)):
            return

        def _do_delete(e=None):
            self.page.pop_dialog()
            self._delete_turn(index)

        self.page.show_dialog(
            ft.AlertDialog(
                title=ft.Text("Delete message?", font_family="Outfit"),
                content=ft.Text(
                    "This message and its exchange leave this chat. "
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

    def _message_actions(self, turn: dict, index: int) -> None:
        """Long-press sheet with the actions a message offers.

        Research pattern: actions are revealed, not parked under every
        message. The always-visible icon rows are gone; this is their only
        entry point now.
        """
        if index < 0 or self._closing:
            return
        entries = [
            ("Copy", lambda: self._copy_turn(index)),
        ]
        if turn.get("role") == "user":
            entries.append(("Edit and resend", lambda: self._edit_turn(index)))
        else:
            entries.append(("Regenerate", lambda: self._regenerate(index)))
        entries.append(("Delete", lambda: self._confirm_delete_turn(index)))

        def _run(action):
            def _handler(e):
                try:
                    self.page.pop_dialog()
                except Exception:
                    pass
                action()

            return _handler

        button_style = ft.ButtonStyle(alignment=ft.Alignment.CENTER_LEFT)
        self.page.show_dialog(
            ft.AlertDialog(
                title=ft.Text("Message", font_family="Outfit"),
                content=ft.Column(
                    [
                        ft.TextButton(label, style=button_style, on_click=_run(action))
                        for label, action in entries
                    ],
                    spacing=0,
                    tight=True,
                ),
                actions=[
                    ft.TextButton(
                        "Close", on_click=lambda e: self._close_dialog_quietly()
                    )
                ],
            )
        )

    def _close_dialog_quietly(self) -> None:
        try:
            self.page.pop_dialog()
        except Exception:
            pass

    def _meta_row(self, turn: dict) -> ft.Control | None:
        """One 12px meta line: steps, cost, model - and the step expander."""
        steps = int(turn.get("steps") or 0)
        cost = int(turn.get("cost") or 0)
        parts: list[str] = []
        if steps:
            parts.append(f"{steps} step{'' if steps == 1 else 's'}")
        if cost:
            parts.append(f"{cost} credit{'' if cost == 1 else 's'}")
        if turn.get("model"):
            parts.append(str(turn["model"]))
        if not parts:
            return None
        if turn.get("served_by") == "gateway":
            parts[-1] = f"{parts[-1]} (gateway)"
        if turn.get("stopped"):
            parts.append("stopped early")
        meta = ft.Text(
            " · ".join(parts),
            size=tokens.FONT_SM,
            color=ft.Colors.with_opacity(0.6, ft.Colors.ON_SURFACE),
        )
        steps_rows = turn.get("steps_rows") or []
        if not steps_rows:
            return ft.Container(content=meta, padding=ft.Padding(4, 2, 4, 0))
        expanded = bool(turn.get("steps_open"))
        return ft.Container(
            content=ft.Row(
                [
                    meta,
                    ft.Container(expand=True),
                    ft.Icon(
                        ft.Icons.EXPAND_LESS_ROUNDED
                        if expanded
                        else ft.Icons.EXPAND_MORE_ROUNDED,
                        size=tokens.ICON_SM,
                        color=ft.Colors.ON_SURFACE_VARIANT,
                    ),
                ],
                spacing=4,
                vertical_alignment=ft.CrossAxisAlignment.CENTER,
            ),
            padding=ft.Padding(4, 2, 4, 0),
            ink=True,
            tooltip="Hide steps" if expanded else "Show steps",
            on_click=lambda e, t=turn: self._toggle_steps(t),
        )

    def _render_user(self, turn: dict, index: int) -> ft.Container:
        bubble_width = min(300, (getattr(self.page, "width", None) or 400) * 0.78)
        return ft.Column(
            [
                ft.GestureDetector(
                    on_long_press=lambda e, t=turn, i=index: self._message_actions(
                        t, i
                    ),
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
                ),
            ],
            spacing=0,
            horizontal_alignment=ft.CrossAxisAlignment.END,
        )

    def _render_assistant(self, turn: dict, index: int = -1) -> ft.Container:
        kids: list[ft.Control] = []

        if (turn.get("thought") or "").strip():
            # Collapsed by default: reasoning is metadata, not the answer
            # (Claude/ChatGPT show it as a one-line chevron).
            thinking_open = bool(turn.get("thought_open", False))
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
                            else ft.Colors.ON_SURFACE_VARIANT,
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
                        color=ft.Colors.with_opacity(0.7, ft.Colors.ON_SURFACE),
                        selectable=True,
                    )
                )
            kids.append(
                ft.Container(
                    content=ft.Column(block, spacing=4, tight=True),
                    padding=ft.Padding(4, 4, 4, 4),
                    ink=True,
                    tooltip="Tap to expand or collapse",
                    on_click=lambda e, t=turn: self._toggle_thought(t),
                )
            )
        steps_rows = turn.get("steps_rows", [])
        running = bool(turn.get("partial"))
        if steps_rows and (running or turn.get("steps_open")):
            # Live or expanded: indented, muted, one line per step. The
            # finished turn folds them into the meta line below.
            for row in steps_rows:
                if row["state"] == "running":
                    icon = ft.Row(
                        [ft.ProgressRing(width=12, height=12, stroke_width=2)],
                        tight=True,
                    )
                elif row["state"] == "error":
                    icon = ft.Icon(
                        ft.Icons.ERROR_OUTLINE_ROUNDED,
                        size=tokens.ICON_SM,
                        color=AppColors.ERROR,
                    )
                else:
                    icon = ft.Icon(
                        ft.Icons.CHECK_CIRCLE_ROUNDED,
                        size=tokens.ICON_SM,
                        color=AppColors.SUCCESS,
                    )
                label = row["label"]
                outcome = str(row.get("outcome") or "").strip()
                if row["state"] == "done" and outcome:
                    # The consequence of a write tool: the saved filename,
                    # the page count, how many schedules were cancelled.
                    label = f"{label}: {outcome}"
                elif row["state"] == "done" and row.get("count"):
                    label = f"{label}: {row['count']} results"
                elif row["state"] == "error":
                    # Show what actually went wrong: "no results" for a
                    # denied write told the user nothing actionable.
                    detail = str(row.get("error") or "").strip() or "no results"
                    if len(detail) > 90:
                        detail = detail[:90].rstrip() + "…"
                    label = f"{label}: {detail}"
                kids.append(
                    ft.Container(
                        content=ft.Row(
                            [
                                icon,
                                ft.Text(
                                    label,
                                    size=tokens.FONT_SM,
                                    color=ft.Colors.ON_SURFACE_VARIANT,
                                ),
                            ],
                            spacing=6,
                            vertical_alignment=ft.CrossAxisAlignment.CENTER,
                        ),
                        padding=ft.Padding(12, 0, 0, 0),
                    )
                )

        # approval gate card
        if self._confirm and self._confirm[1].get("decision") is None:
            label = self._confirm[1]["label"]
            detail = str(self._confirm[1].get("detail") or "").strip()
            kids.append(
                ft.Container(
                    content=ft.Column(
                        [
                            ft.Text(
                                label,
                                size=tokens.FONT_SM,
                                weight=ft.FontWeight.W_600,
                            ),
                            *(
                                [
                                    ft.Text(
                                        detail,
                                        size=tokens.FONT_XS,
                                        color=ft.Colors.ON_SURFACE_VARIANT,
                                        selectable=True,
                                    ),
                                ]
                                if detail
                                else []
                            ),
                            ft.Row(
                                [
                                    ft.OutlinedButton(
                                        "Allow",
                                        on_click=lambda e: self._confirm_decision(
                                            "allow"
                                        ),
                                    ),
                                    ft.OutlinedButton(
                                        "Deny",
                                        on_click=lambda e: self._confirm_decision(
                                            "deny"
                                        ),
                                    ),
                                ],
                                spacing=8,
                            ),
                            ft.Text(
                                "Auto-denies in 2m",
                                size=tokens.FONT_XS,
                                color=ft.Colors.ON_SURFACE_VARIANT,
                            ),
                        ],
                        spacing=6,
                        tight=True,
                    ),
                    padding=ft.Padding(10, 8, 10, 8),
                    border_radius=tokens.RADIUS_MD,
                    border=ft.Border.all(
                        1, ft.Colors.with_opacity(0.5, AppColors.WARNING)
                    ),
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
                ui.notice(
                    "Out of assistant credits.",
                    level="warning",
                    action_label="Get credits",
                    on_action=lambda e: show_wallet_dialog(self.page),
                )
            )
        elif turn.get("error") == "midstream":
            kids.append(
                ui.notice(
                    "Connection lost mid-answer. What arrived was still charged.",
                    level="warning",
                    action_label="Try again",
                    action_icon=ft.Icons.REFRESH_ROUNDED,
                    on_action=lambda e: self._retry_last(),
                )
            )
        elif turn.get("error") == "empty":
            kids.append(
                ui.notice(
                    "That model replied with nothing. You were not charged for it.",
                    action_label="Try again",
                    action_icon=ft.Icons.REFRESH_ROUNDED,
                    on_action=lambda e: self._retry_last(),
                )
            )
        elif turn.get("error") == "unavailable":
            kids.append(
                ui.notice(
                    str(turn.get("error_message") or "")
                    or "Assistant unavailable. Classic search, scraping "
                    "and downloads still work.",
                    action_label="Try again",
                    action_icon=ft.Icons.REFRESH_ROUNDED,
                    on_action=lambda e: self._retry_last(),
                )
            )
        if turn.get("stopped"):
            kids.append(ui.notice("Stopped."))

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

        # Meta line: what it cost, who answered, plus the step expander.
        # Actions moved to a long-press sheet (see _message_actions).
        if index >= 0 and turn.get("cost"):
            meta = self._meta_row(turn)
            if meta is not None:
                kids.append(meta)
        elif turn.get("receipt"):
            kids.append(
                ui.notice(str(turn["receipt"]), level="warning")
            )

        return ft.Container(
            content=ft.Column(kids, spacing=6, tight=True),
            padding=ft.Padding(4, 2, 4, 2),
            on_long_press=lambda e, t=turn, i=index: self._message_actions(t, i),
        )

    def _render_cards(self, block: dict) -> ft.Control:
        results: list[SearchResult] = block.get("results") or []
        kind = block.get("kind", "web")
        rows: list[ft.Control] = []
        for i, r in enumerate(results[:8]):
            if i:
                rows.append(
                    ft.Divider(
                        height=1,
                        thickness=1,
                        color=ft.Colors.with_opacity(0.18, ft.Colors.OUTLINE),
                    )
                )
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
                                            size=tokens.ICON_SM,
                                            color=ft.Colors.ON_SURFACE_VARIANT,
                                        ),
                                    ),
                                    clip_behavior=ft.ClipBehavior.HARD_EDGE,
                                )
                                if thumb
                                else ft.Icon(
                                    _KIND_ICONS.get(kind, ft.Icons.LANGUAGE_ROUNDED),
                                    size=tokens.ICON_SM,
                                    color=ft.Colors.ON_SURFACE_VARIANT,
                                )
                            ),
                            ft.Text(
                                r.title or r.url,
                                size=tokens.FONT_SM,
                                max_lines=1,
                                overflow=ft.TextOverflow.ELLIPSIS,
                                expand=True,
                                weight=ft.FontWeight.W_500,
                            ),
                            ft.Text(
                                _domain(r.url or ""),
                                size=tokens.FONT_XS,
                                color=ft.Colors.ON_SURFACE_VARIANT,
                                max_lines=1,
                            ),
                        ],
                        spacing=6,
                        vertical_alignment=ft.CrossAxisAlignment.CENTER,
                    ),
                )
            )
        return ft.Column(
            [
                ft.Text(
                    f"Found {len(results)} {kind} result"
                    f"{'' if len(results) == 1 else 's'}",
                    size=tokens.FONT_XS,
                    weight=ft.FontWeight.W_600,
                    color=ft.Colors.ON_SURFACE_VARIANT,
                ),
                *rows,
                *(
                    [
                        ft.TextButton(
                            f"Open {len(results)} results",
                            icon=ft.Icons.LIST_ROUNDED,
                            on_click=lambda e, rs=results, k=kind: self._open_results(
                                rs, k
                            ),
                            style=ui.ZERO_PAD,
                        )
                    ]
                    if results
                    else []
                ),
            ],
            spacing=4,
            tight=True,
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
                existing.send(_describe_prompt(ctx['url']))
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
            session.send(_describe_prompt(ctx['url']))
        elif ctx.get("question"):
            session.send(ctx["question"])
