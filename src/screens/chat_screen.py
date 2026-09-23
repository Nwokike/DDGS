"""ChatScreen — full-screen agentic AI chat (the Ask-AI FAB entry).

Imperative View (reader pattern): built once, refreshed from local session
state with >=0.2s throttling for token streams and immediate refreshes for
block additions (tool steps, result blocks). The agent loop lives in
services/chat_agent; this file owns presentation + the emit protocol.
"""

from __future__ import annotations

import asyncio
import time

import flet as ft

from components.results.downloader import launch_url
from components.wallet import show_wallet_dialog
from core import tokens
from core.state import SearchResult, state
from core.styles import build_banner_ad
from core.theme import AppColors

_KIND_ICONS = {
    "web": ft.Icons.LANGUAGE_ROUNDED,
    "images": ft.Icons.IMAGE_ROUNDED,
    "videos": ft.Icons.VIDEO_LIBRARY_ROUNDED,
    "news": ft.Icons.NEWSPAPER_ROUNDED,
    "books": ft.Icons.BOOK_ROUNDED,
}

_DISCLOSURE = (
    "1 credit per message · queries go to your in-app Kiri router first · "
    "no history, no identity, no training."
)

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
    """Owns one chat thread: local message model, rendering, agent turn."""

    def __init__(self, page: ft.Page, ctx: dict | None = None):
        self.page = page
        self.ctx = ctx or {}
        self.turns: list[dict] = []
        self.agent_history: list[dict] = []
        self.pending_user = ""
        self.busy = False
        self.cancel = asyncio.Event()
        self._last_partial_flush = 0.0
        self._current: dict | None = None

        # ── Controls ────────────────────────────────────────────────
        self._list = ft.Column([], spacing=tokens.SPACE_SM, expand=True)
        self.field = ft.TextField(
            hint_text="Ask AI anything — it can search and fetch for you…",
            expand=True,
            dense=True,
            min_lines=1,
            max_lines=4,
            content_padding=ft.Padding(12, 8, 12, 8),
            border=ft.OutlineInputBorder(border_radius=tokens.RADIUS_LG),
        )
        if self.ctx.get("url"):
            self.field.value = ""
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

        credits_color = (
            AppColors.SUCCESS
            if state.credits_remaining > 20
            else AppColors.WARNING
            if state.credits_remaining >= 5
            else AppColors.ERROR
        )
        self.credits_chip = ft.Container(
            content=ft.Row(
                [
                    ft.Icon(
                        ft.Icons.AUTO_AWESOME_ROUNDED, size=14, color=credits_color
                    ),
                    ft.Text(
                        str(state.credits_remaining),
                        size=tokens.FONT_XS,
                        weight=ft.FontWeight.W_700,
                        color=credits_color,
                    ),
                ],
                spacing=3,
                tight=True,
            ),
            padding=ft.Padding(7, 3, 9, 3),
            border_radius=tokens.RADIUS_PILL,
            bgcolor=ft.Colors.with_opacity(0.12, credits_color),
            ink=True,
            tooltip="AI credits — tap for details",
            on_click=lambda e: show_wallet_dialog(page),
        )

        appbar = ft.AppBar(
            leading=ft.IconButton(
                icon=ft.Icons.ARROW_BACK_ROUNDED,
                tooltip="Close chat",
                on_click=lambda e: self.close(),
            ),
            title=ft.Row(
                [
                    ft.Icon(
                        ft.Icons.AUTO_AWESOME_ROUNDED,
                        size=20,
                        color=AppColors.ACCENT,
                    ),
                    ft.Text(
                        "DDGS AI",
                        size=tokens.FONT_MD,
                        weight=ft.FontWeight.W_700,
                        font_family="Outfit",
                    ),
                ],
                spacing=6,
            ),
            actions=[self.credits_chip, ft.Container(width=8)],
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

        self.view = ft.View(
            route="/chat",
            controls=[
                ft.Container(
                    content=ft.Column(
                        [
                            appbar,
                            ft.Container(self._list, expand=True),
                            build_banner_ad(page),
                            composer,
                        ],
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
                text, list(self.agent_history), self.emit, self.cancel
            )
        finally:
            self.busy = False
            self._set_busy_ui(False)
            self._render(force=True)

    def stop(self) -> None:
        self.cancel.set()

    def close(self) -> None:
        self.cancel.set()
        try:
            if self.page.views and self.page.views[-1] is self.view:
                self.page.views.pop()
                state.chat_open = False
                self.page.update()
        except Exception:
            state.chat_open = False

    def _set_busy_ui(self, busy: bool) -> None:
        self.send_btn.visible = not busy
        self.stop_btn.visible = busy
        try:
            self.send_btn.update()
            self.stop_btn.update()
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
                "partial": True,
                "steps": [],
                "cards": [],
                "related": [],
                "served_by": "",
                "error": None,
                "stopped": False,
            }
            self.turns.append(self._current)
        elif event == "text_partial" and self._current is not None:
            self._current["text"] = data.get("text", "")
            force = False  # throttle partials
            if now - self._last_partial_flush < 0.2:
                return
            self._last_partial_flush = now
        elif event == "step_start" and self._current is not None:
            self._current["steps"].append(
                {
                    "id": data.get("id", ""),
                    "label": data.get("label", ""),
                    "state": "running",
                    "count": 0,
                    "error": None,
                }
            )
        elif event in ("step_done", "step_error") and self._current is not None:
            for step in self._current["steps"]:
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
                partial=False,
                related=data.get("related", []),
                served_by=data.get("served_by", ""),
            )
            clean = self._current["text"]
            if clean:
                self.agent_history = (
                    self.agent_history
                    + [
                        {"role": "user", "content": self.pending_user},
                        {"role": "assistant", "content": clean},
                    ]
                )[-16:]
        elif event == "stopped" and self._current is not None:
            self._current.update(partial=False, stopped=True)
            if data.get("partial") and not self._current["text"]:
                self._current["text"] = data["partial"]
        elif event == "error" and self._current is not None:
            self._current.update(
                partial=False,
                error=data.get("kind", "unavailable"),
            )
            if data.get("partial") and not self._current["text"]:
                self._current["text"] = data["partial"]
        elif event == "error" and self._current is None:
            # failed before assistant_start (e.g. no credits)
            self.turns.append(
                {
                    "role": "assistant",
                    "text": "",
                    "partial": False,
                    "steps": [],
                    "cards": [],
                    "related": [],
                    "served_by": "",
                    "error": data.get("kind", "unavailable"),
                    "stopped": False,
                }
            )
            if data.get("kind") == "credits":
                self.busy = False
        self._render(force=force)

    # ── Rendering ──────────────────────────────────────────────────────────

    def _render(self, force: bool = True) -> None:
        controls: list[ft.Control] = []
        if not self.turns:
            controls.append(self._welcome())
        for turn in self.turns:
            controls.append(
                self._render_user(turn)
                if turn.get("role") == "user"
                else self._render_assistant(turn)
            )
        self._list.controls = controls
        if force:
            try:
                self.page.update()
            except Exception:
                pass

    def _welcome(self) -> ft.Container:
        kids: list[ft.Control] = [
            ft.Container(
                content=ft.Icon(
                    ft.Icons.AUTO_AWESOME_ROUNDED, size=44, color=AppColors.ACCENT
                ),
                alignment=ft.Alignment.CENTER,
                margin=ft.Margin(0, 40, 0, 8),
            ),
            ft.Text(
                "Ask me anything",
                size=tokens.FONT_LG,
                weight=ft.FontWeight.W_700,
                font_family="Outfit",
                text_align=ft.TextAlign.CENTER,
            ),
            ft.Text(
                "I can search DDGS across web, images, videos, news and books — "
                "and fetch pages — myself, then show you what I find.",
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
        for s in _SUGGESTIONS:
            chips.append(
                ft.Container(
                    content=ft.Text(s, size=tokens.FONT_XS, color=AppColors.PRIMARY),
                    padding=ft.Padding(10, 6, 10, 6),
                    border_radius=tokens.RADIUS_PILL,
                    border=ft.Border.all(
                        1, ft.Colors.with_opacity(0.3, AppColors.PRIMARY)
                    ),
                    ink=True,
                    on_click=lambda e, q=s: self.send(q),
                )
            )
        kids.append(ft.Row(chips, spacing=6, wrap=True, run_spacing=6))
        return ft.Container(
            content=ft.Column(kids, horizontal_alignment=ft.CrossAxisAlignment.CENTER),
            expand=True,
        )

    def _render_user(self, turn: dict) -> ft.Container:
        bubble_width = min(300, (getattr(self.page, "width", None) or 400) * 0.72)
        return ft.Row(
            [
                ft.Container(
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
                )
            ],
            alignment=ft.MainAxisAlignment.END,
        )

    def _render_assistant(self, turn: dict) -> ft.Container:
        kids: list[ft.Control] = []

        for step in turn.get("steps", []):
            if step["state"] == "running":
                icon = ft.Row(
                    [
                        ft.ProgressRing(width=12, height=12, stroke_width=2),
                    ],
                    tight=True,
                )
            elif step["state"] == "error":
                icon = ft.Icon(
                    ft.Icons.ERROR_OUTLINE_ROUNDED, size=14, color=AppColors.ERROR
                )
            else:
                icon = ft.Icon(
                    ft.Icons.CHECK_CIRCLE_ROUNDED,
                    size=14,
                    color=AppColors.SUCCESS,
                )
            label = step["label"]
            if step["state"] == "done" and step.get("count"):
                label = label.removesuffix("…")
                label += f" — {step['count']} results"
            if step["state"] == "error" and step.get("error"):
                label = f"{label.rstrip('…')} — {step['error']}"
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

        for block in turn.get("cards", []):
            kids.append(self._render_cards(block))

        if turn.get("text"):
            kids.append(
                ft.Markdown(
                    turn["text"],
                    selectable=True,
                    extension_set="gitHubWeb",
                    on_tap_link=lambda e: (
                        e.data and self.page.run_task(launch_url, e.data)
                    ),
                )
            )

        if turn.get("partial") and not turn.get("text"):
            kids.append(
                ft.Row(
                    [
                        ft.ProgressRing(width=12, height=12, stroke_width=2),
                        ft.Text(
                            "Thinking…",
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
                            "Out of free AI messages — refill options:",
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
                    "⚠ Connection lost mid-answer.",
                    size=tokens.FONT_XS,
                    color=AppColors.WARNING,
                )
            )
        elif turn.get("error") == "unavailable":
            kids.append(
                ft.Text(
                    "AI unavailable right now — your searches still work normally.",
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

        return ft.Container(
            content=ft.Column(kids, spacing=tokens.SPACE_XS, tight=True),
            padding=ft.Padding(4, 2, 4, 2),
        )

    def _render_cards(self, block: dict) -> ft.Container:
        results: list[SearchResult] = block.get("results") or []
        kind = block.get("kind", "web")
        rows: list[ft.Control] = []
        for r in results[:5]:
            rows.append(
                ft.GestureDetector(
                    on_tap=lambda e, u=r.url: u and self.page.run_task(launch_url, u),
                    content=ft.Row(
                        [
                            ft.Icon(
                                _KIND_ICONS.get(kind, ft.Icons.LANGUAGE_ROUNDED),
                                size=14,
                                color=AppColors.PRIMARY,
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
        if len(results) > 5:
            rows.append(
                ft.Text(
                    f"…and {len(results) - 5} more",
                    size=9,
                    color=ft.Colors.ON_SURFACE_VARIANT,
                )
            )
        return ft.Container(
            content=ft.Column(
                [
                    ft.Text(
                        f"Found {len(results)} {kind} result{'' if len(results) == 1 else 's'}",
                        size=9,
                        weight=ft.FontWeight.W_700,
                        color=AppColors.PRIMARY,
                    ),
                    *rows,
                ],
                spacing=3,
                tight=True,
            ),
            padding=ft.Padding(10, 6, 10, 6),
            border_radius=tokens.RADIUS_MD,
            bgcolor=ft.Colors.with_opacity(0.05, AppColors.PRIMARY),
        )


def open_chat_view(page: ft.Page, ctx: dict | None = None) -> None:
    """Push the chat view (idempotent). Called by AppController.open_chat."""
    if state.chat_open:
        return
    ctx = ctx or {}
    session = ChatSession(page, ctx)
    page._chat_session = session
    state.chat_open = True
    page.views.append(session.view)
    try:
        page.update()
    except Exception:
        pass
    if not ctx.get("auto"):
        return
    if ctx.get("url"):
        session.send(f"Describe this page for me: {ctx['url']}")
    elif ctx.get("question"):
        session.send(ctx["question"])
