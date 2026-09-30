"""Assistant auto-summary card - the search-overview pattern for one page.

Search results get a passive AI overview at the top: no button, no modal,
it just starts. This is the same treatment for a single page. The Reader,
the fetch preview sheet, and the result detail sheet each embed the card
built here and auto-start it; the card streams the summary inline and
collapses via its chevron. Follow-up actions (Ask Assistant, Get credits)
appear only as terminal states - there is deliberately no button that
begins a summary.
"""

from __future__ import annotations

import time
from collections.abc import Awaitable, Callable

import flet as ft

from core import tokens
from core.constants import COST_SUMMARY
from core.state import state
from core.theme import AppColors


def build_auto_summary(
    page: ft.Page,
    *,
    get_title: Callable[[], str],
    get_content: Callable[[], str | None] | None = None,
    load_content: Callable[[], Awaitable[str | None]] | None = None,
    get_url: Callable[[], str] | None = None,
) -> tuple[ft.Container, Callable[..., None]]:
    """Build a passive summary card; return (card, start).

    The card starts hidden. Call `start()` once the host is visible and
    the page text is ready - it resolves the text (sync `get_content`
    first, then async `load_content`), shows the card, and streams the
    summary into it. Call `start(force=True)` when the host navigates to
    a new page. While a stream runs, `start()` is a no-op. When there is
    no readable text (binary, empty extract) the card stays hidden
    instead of summarizing nothing.
    """
    summary_state = {"expanded": True, "running": False, "gen": 0}
    summary_body = ft.Text(
        "Analyzing page…",
        size=tokens.FONT_SM,
        color=ft.Colors.ON_SURFACE_VARIANT,
        selectable=True,
    )
    summary_sub = ft.Text(
        "",
        size=tokens.FONT_XS,
        color=ft.Colors.ON_SURFACE_VARIANT,
        max_lines=1,
        overflow=ft.TextOverflow.ELLIPSIS,
    )
    summary_actions = ft.Row([], spacing=4, tight=True)

    def _sync_summary():
        summary_chevron.icon = (
            ft.Icons.EXPAND_MORE_ROUNDED
            if not summary_state["expanded"]
            else ft.Icons.EXPAND_LESS_ROUNDED
        )
        summary_chevron.tooltip = (
            "Show more" if not summary_state["expanded"] else "Show less"
        )
        try:
            summary_details.visible = summary_state["expanded"]
            page.update()
        except Exception:
            pass

    def _toggle_summary(e=None):
        summary_state["expanded"] = not summary_state["expanded"]
        _sync_summary()

    def _page_url() -> str:
        try:
            if get_url is not None:
                return get_url() or ""
            return get_title() or ""
        except Exception:
            return ""

    def _ask_summary_page(e=None):
        """Hand this page to the agentic chat, preloaded to describe it."""
        ctrl = getattr(page, "_ddgs_controller", None)
        if ctrl:
            ctrl.open_chat(
                {
                    "url": _page_url(),
                    "title": (get_title() or "Page"),
                    "auto": True,
                }
            )

    def _open_wallet(e=None):
        from components.wallet import show_wallet_dialog

        show_wallet_dialog(page)

    summary_chevron = ft.IconButton(
        icon=ft.Icons.EXPAND_LESS_ROUNDED,
        icon_size=tokens.ICON_SM,
        tooltip="Show less",
        on_click=lambda e: _toggle_summary(),
    )
    summary_details = ft.Column(
        [summary_body, summary_actions],
        spacing=6,
        tight=True,
        visible=True,
    )
    summary_card = ft.Container(
        content=ft.Column(
            [
                ft.Row(
                    [
                        ft.Icon(
                            ft.Icons.CHAT_BUBBLE_OUTLINE_ROUNDED,
                            size=tokens.ICON_SM,
                            color=AppColors.ACCENT,
                        ),
                        ft.Text(
                            "Assistant summary",
                            size=tokens.FONT_SM,
                            weight=ft.FontWeight.W_700,
                            font_family="Outfit",
                        ),
                        ft.Container(expand=True),
                        summary_chevron,
                    ],
                    spacing=6,
                    vertical_alignment=ft.CrossAxisAlignment.CENTER,
                ),
                summary_sub,
                summary_details,
            ],
            spacing=6,
            tight=True,
        ),
        padding=ft.Padding(16, 10, 16, 10),
        border_radius=tokens.RADIUS_LG,
        border=ft.Border.all(1, ft.Colors.with_opacity(0.25, AppColors.ACCENT)),
        bgcolor=ft.Colors.with_opacity(0.06, AppColors.ACCENT),
        visible=False,
    )

    async def _run(text: str, gen: int) -> None:
        from services import ai_service

        buffer = {"text": "", "last": 0.0}

        def on_token(token: str) -> None:
            if gen != summary_state["gen"]:
                return
            buffer["text"] += token
            now = time.monotonic()
            if now - buffer["last"] >= 0.2:
                buffer["last"] = now
                summary_body.value = buffer["text"]
                try:
                    page.update()
                except Exception:
                    pass

        messages = ai_service.build_summary_messages(get_title() or "Page", text)
        try:
            await ai_service.stream_chat(
                messages,
                COST_SUMMARY,
                on_token,
                model=getattr(state, "ai_model", "auto"),
            )
            if gen != summary_state["gen"]:
                return
            summary_body.value = buffer["text"] or "(empty summary)"
            summary_body.color = ft.Colors.ON_SURFACE
            summary_state["expanded"] = True
            summary_actions.controls = [
                ft.TextButton(
                    "Ask Assistant about this page",
                    icon=ft.Icons.CHAT_BUBBLE_OUTLINE_ROUNDED,
                    on_click=_ask_summary_page,
                    style=ft.ButtonStyle(padding=ft.Padding(4, 2, 4, 2)),
                )
            ]
        except ai_service.NotEnoughCredits as exc:
            summary_body.value = f"Out of Assistant credits ({exc.balance} left)."
            summary_body.color = AppColors.WARNING
            summary_actions.controls = [
                ft.TextButton(
                    "Get credits",
                    on_click=_open_wallet,
                    style=ft.ButtonStyle(padding=ft.Padding(4, 2, 4, 2)),
                )
            ]
        except ai_service.AIMidStream:
            summary_body.value = (
                buffer["text"] + " " + "Connection lost mid-summary."
            ).strip()
            summary_body.color = AppColors.WARNING
        except Exception:
            # AIUnavailable and anything unexpected share one honest line -
            # and a walking candidate list already retried every model.
            summary_body.value = "Assistant unavailable. The full page text is untouched."
            summary_body.color = ft.Colors.ON_SURFACE_VARIANT
        summary_state["running"] = False
        _sync_summary()
        try:
            page.update()
        except Exception:
            pass

    async def _start(force: bool = False) -> None:
        if summary_state["running"] and not force:
            return
        summary_state["gen"] += 1
        summary_state["running"] = True
        gen = summary_state["gen"]
        text = ""
        try:
            if get_content is not None:
                text = (get_content() or "")
        except Exception:
            text = ""
        if not text.strip() and load_content is not None:
            try:
                text = (await load_content()) or ""
            except Exception:
                text = ""
        if not text.strip():
            summary_state["running"] = False
            return
        summary_sub.value = (get_title() or "Page")[:120]
        summary_card.visible = True
        summary_state["expanded"] = True
        summary_body.value = "Analyzing page…"
        summary_body.color = ft.Colors.ON_SURFACE_VARIANT
        summary_actions.controls = []
        _sync_summary()
        await _run(text, gen)

    def start(force: bool = False) -> None:
        """Show the card and stream (no-op while a stream runs)."""
        if summary_state["running"] and not force:
            return
        page.run_task(_start, force)

    return summary_card, start
