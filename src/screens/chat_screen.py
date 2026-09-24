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
import time

import flet as ft

from components.model_picker import show_model_picker
from components.results.downloader import launch_url
from components.wallet import show_wallet_dialog
from core import tokens
from core.state import SearchResult, state
from core.theme import AppColors

_CHAT = ft.Icons.CHAT_BUBBLE_OUTLINE_ROUNDED

_DISCLOSURE = (
    "Runs on your in-app Kiri router first; if it's down, requests fall back to "
    "Kiri's gateway. We instruct no training; page text is sent only for "
    "features you tap."
)

_KIND_ICONS = {
    "web": ft.Icons.LANGUAGE_ROUNDED,
    "images": ft.Icons.IMAGE_ROUNDED,
    "videos": ft.Icons.VIDEO_LIBRARY_ROUNDED,
    "news": ft.Icons.NEWSPAPER_ROUNDED,
    "books": ft.Icons.BOOK_ROUNDED,
}
_THROUGHT_CAP = 900

_SUGGESTIONS = [
    "What happened in tech this week?",
    "Explain a topic like I'm 12",
    "Find me the best free privacy tools",
]


def _domain(url: str) -> str:
    if "//" in url:
        return url.split("/")[2].removeprefix("www.")
    return url[:40]


class ChatSession:
    """Owns one conversation: local model, rendering, agent turn, approvals."""

    def __init__(self, page: ft.Page, ctx: dict | None = None):
        self.page = page
        self.ctx = ctx or {}
        self.turns: list[dict] = []
        self.agent_history: list[dict] = list(
            getattr(state, "assistant_history", []) or []
        )
        self.pending_user = ""
        self.busy = False
        self.cancel = asyncio.Event()
        self._last_partial_flush = 0.0
        self._pinned = True  # auto-scroll only while the user sits at the bottom
        self._current: dict | None = None
        self._confirm: tuple[asyncio.Event, dict] | None = None

        # ── Controls ────────────────────────────────────────────────
        self._list = ft.Column(
            [], spacing=tokens.SPACE_SM, expand=True, scroll=ft.ScrollMode.AUTO
        )
        self.field = ft.TextField(
            hint_text="Ask the assistant — it can search and fetch for you…",
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
            tooltip="Assistant credits — tap for details",
            on_click=lambda e: show_wallet_dialog(page),
        )
        self.model_chip = ft.Container(
            content=ft.Row(
                [
                    ft.Text(
                        state.ai_model,
                        size=tokens.FONT_XS,
                        color=AppColors.PRIMARY,
                    ),
                    ft.Icon(
                        ft.Icons.EXPAND_MORE_ROUNDED,
                        size=12,
                        color=AppColors.PRIMARY,
                    ),
                ],
                spacing=2,
                tight=True,
            ),
            padding=ft.Padding(7, 3, 7, 3),
            border_radius=tokens.RADIUS_PILL,
            bgcolor=ft.Colors.with_opacity(0.1, AppColors.PRIMARY),
            ink=True,
            tooltip="Assistant model",
            on_click=lambda e: show_model_picker(page),
        )

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
                ft.IconButton(
                    icon=ft.Icons.DELETE_SWEEP_OUTLINED,
                    icon_size=18,
                    tooltip="Clear chat",
                    on_click=lambda e: self._clear_chat(),
                ),
                ft.Container(width=6),
            ],
            bgcolor=ft.Colors.TRANSPARENT,
            elevation=0,
        )

        composer = ft.Container(
            content=ft.Column(
                [
                    ft.Row(
                        [self.field, self.send_btn, self.stop_btn],
                        vertical_alignment=ft.CrossAxisAlignment.END,
                        spacing=2,
                    ),
                    ft.Text(
                        _DISCLOSURE,
                        size=9,
                        color=ft.Colors.with_opacity(0.5, ft.Colors.ON_SURFACE),
                    ),
                ],
                spacing=4,
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
        self.page.run_task(self._run_turn, text)

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
        finally:
            self.busy = False
            self._set_busy_ui(False)
            self._render(force=True)

    def stop(self) -> None:
        self.cancel.set()

    async def ask_confirm(self, label: str) -> bool:
        """Inline approve/deny gate for file-writing tools. Times out to deny."""
        event = asyncio.Event()
        self._confirm = (event, {"label": label, "decision": None})
        self._render(force=True)
        try:
            await asyncio.wait_for(event.wait(), timeout=120)
        except TimeoutError:
            return False
        decision = self._confirm[1]["decision"] if self._confirm else None
        return decision == "allow"

    def _confirm_decision(self, decision: str) -> None:
        if self._confirm and self._confirm[1].get("decision") is None:
            self._confirm[1]["decision"] = decision
            self._confirm[0].set()

    def close(self) -> None:
        self.cancel.set()
        self._persist_history()
        try:
            if self.page.views and self.page.views[-1] is self.view:
                self.page.views.pop()
                state.chat_open = False
                self.page.update()
        except Exception:
            state.chat_open = False

    def _clear_chat(self) -> None:
        if not self.turns:
            return
        self.turns = []
        self.agent_history = []
        state.assistant_history = []
        self._persist_history()
        self._render(force=True)
        snack = ft.SnackBar(ft.Text("Chat cleared"))
        snack.open = True
        self.page.show_dialog(snack)
        try:
            self.page.update()
        except Exception:
            pass

    def _delete_turn(self, index: int) -> None:
        if 0 <= index < len(self.turns):
            del self.turns[index]
            self._persist_history()
            self._render(force=True)

    def _persist_history(self) -> None:
        text = self.agent_history[-16:]
        state.assistant_history = text
        storage = _storage()
        if storage:
            try:
                import json

                self.page.run_task(storage.set_assistant_history, json.dumps(text))
            except Exception:
                pass

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
            if now - self._last_partial_flush < 0.2:
                return
            self._last_partial_flush = now
        elif event == "thought" and self._current is not None:
            buf = (self._current.get("thought") or "") + data.get("text", "")
            self._current["thought"] = buf[:_THROUGHT_CAP]
            force = False
            if now - self._last_partial_flush < 0.5:
                return
            self._last_partial_flush = now
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
            self._current.update(
                text=data.get("text", ""),
                related=data.get("related", []),
                served_by=data.get("served_by", ""),
                steps=data.get("steps", 0),
                cost=data.get("cost", 0),
                partial=False,
                receipt="",
            )
            self.agent_history = (
                self.agent_history
                + [
                    {"role": "user", "content": self.pending_user},
                    {"role": "assistant", "content": self._current["text"]},
                ]
            )[-16:]
            self._persist_history()
            self._refresh_credits_chip()
        elif event == "stopped" and self._current is not None:
            self._current.update(
                partial=False,
                stopped=True,
                steps=data.get("steps", self._current.get("steps", 0)),
                cost=data.get("cost", self._current.get("cost", 0)),
            )
        elif event == "error" and self._current is not None:
            self._current.update(
                partial=False,
                error=data.get("kind", "unavailable"),
                steps=data.get("steps", self._current.get("steps", 0)),
                cost=data.get("cost", self._current.get("cost", 0)),
            )
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
                    "error": data.get("kind", "unavailable"),
                    "stopped": False,
                    "receipt": "",
                }
            )
            if data.get("kind") == "credits":
                self.busy = False
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

    # ── Rendering ──────────────────────────────────────────────────────────

    def _render(self, force: bool = True) -> None:
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
        if force:
            try:
                self.page.update()
            except Exception:
                pass
            if self._pinned:
                self.page.run_task(self._scroll_to_bottom)

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
                "download media — myself, and show you what I find.",
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
                        f"📄 Describe this page — {_domain(str(self.ctx['url']))}",
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
            kids.append(
                ft.Container(
                    content=ft.Text(
                        "💭 " + turn["thought"].strip().replace("\n", " "),
                        size=tokens.FONT_XS,
                        italic=True,
                        color=ft.Colors.ON_SURFACE_VARIANT,
                        max_lines=2,
                        overflow=ft.TextOverflow.ELLIPSIS,
                    ),
                    padding=ft.Padding(8, 4, 8, 4),
                    border_radius=tokens.RADIUS_SM,
                    bgcolor=ft.Colors.with_opacity(0.04, ft.Colors.ON_SURFACE),
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
                label += f" — {row['count']} results"
            if row["state"] == "error" and row.get("error"):
                label = f"{label.rstrip('…')} — didn't return results"
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

        if turn.get("partial") and not turn.get("text"):
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
                            "Out of free assistant messages — assistant replies need credits.",
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
                    "⚠ Connection lost mid-answer — what arrived was still charged.",
                    size=tokens.FONT_XS,
                    color=AppColors.WARNING,
                )
            )
        elif turn.get("error") == "unavailable":
            kids.append(
                ft.Text(
                    "Assistant unavailable — classic search, scraping and "
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

        # receipt — every assistant turn shows what it cost
        if turn.get("cost"):
            receipt = (
                f"Assistant used {turn.get('steps', 0)} steps · {turn['cost']} credits"
            )
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


def _storage():
    credits = getattr(state, "credit_service", None)
    return getattr(credits, "_storage", None) if credits else None


def open_chat_view(page: ft.Page, ctx: dict | None = None) -> None:
    """Open (or re-expand) the assistant. Reuses the retained session."""
    if state.chat_open:
        return
    existing = getattr(page, "_chat_session", None)
    if isinstance(existing, ChatSession):
        state.chat_open = True
        page.views.append(existing.view)
        try:
            page.update()
        except Exception:
            pass
        if ctx and ctx.get("auto"):
            if ctx.get("url"):
                existing.send(f"Describe this page for me: {ctx['url']}")
            elif ctx.get("question"):
                existing.send(ctx["question"])
        return
    session = ChatSession(page, ctx)
    page._chat_session = session
    state.chat_open = True
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
