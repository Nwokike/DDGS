"""Assistant summary sheet - streams a page summary from reader/preview/detail.

Lives outside the reactive component tree (BottomSheet via show_dialog), so it
drives its Text control manually with >=0.2s page.update() throttling - the
same discipline as the downloader progress bar.
"""

from __future__ import annotations

import time

import flet as ft

from core import tokens, ui
from core.state import state
from core.theme import AppColors


def show_ai_summary(page: ft.Page, title: str, content: str, url: str = "") -> None:
    """Open the summary sheet and stream an AI summary of `content`."""
    from core.constants import COST_SUMMARY
    from services import ai_service

    body = ft.Text(
        "Analyzing page…",
        size=tokens.FONT_SM,
        color=ft.Colors.ON_SURFACE_VARIANT,
        selectable=True,
    )

    def _close(e=None):
        try:
            page.pop_dialog()
        except Exception:
            pass

    def _ask_ai(e=None):
        """Hand this page to the agentic chat, preloaded to describe it."""
        _close()
        ctrl = getattr(page, "_ddgs_controller", None)
        if ctrl:
            page_url = url or (title if str(title).startswith("http") else "")
            ctrl.open_chat({"url": page_url, "title": title, "auto": True})

    def _open_wallet(e=None):
        """Credits route: close this sheet, open the credits dialog."""
        from components.wallet import show_wallet_dialog

        _close()
        show_wallet_dialog(page)

    column = ft.Column(
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
                    ft.IconButton(
                        icon=ft.Icons.CLOSE_ROUNDED,
                        icon_size=tokens.ICON_SM,
                        on_click=lambda e: _close(),
                    ),
                ],
                spacing=6,
                vertical_alignment=ft.CrossAxisAlignment.CENTER,
            ),
            ft.Text(
                (title or "")[:120],
                size=tokens.FONT_XS,
                color=ft.Colors.ON_SURFACE_VARIANT,
                max_lines=1,
                overflow=ft.TextOverflow.ELLIPSIS,
            ),
            ft.Divider(height=8, thickness=1),
            # No fixed height and no inner scroller: the summary is capped
            # at five bullets, so the sheet sizes to its content instead of
            # nesting a scroll inside a scroll.
            body,
            ft.Row(
                [
                    ft.TextButton(
                        "Ask Assistant about this page",
                        icon=ft.Icons.CHAT_BUBBLE_OUTLINE_ROUNDED,
                        on_click=_ask_ai,
                        style=ui.ZERO_PAD,
                    ),
                ],
                spacing=6,
                vertical_alignment=ft.CrossAxisAlignment.CENTER,
            ),
        ],
        spacing=8,
        tight=True,
    )
    sheet = ft.BottomSheet(
        content=ft.Container(
            content=column,
            width=min(480, (getattr(page, "width", None) or 420) - 24),
            padding=ft.Padding(16, 12, 16, 16),
        ),
        open=True,
        elevation=8,
    )

    page.show_dialog(sheet)

    async def _run() -> None:
        buffer = {"text": "", "last": 0.0}

        def on_token(token: str) -> None:
            buffer["text"] += token
            now = time.monotonic()
            if now - buffer["last"] >= 0.2:
                buffer["last"] = now
                body.value = buffer["text"]
                try:
                    page.update()
                except Exception:
                    pass

        messages = ai_service.build_summary_messages(title, content)
        try:
            await ai_service.stream_chat(
                messages,
                COST_SUMMARY,
                on_token,
                model=getattr(state, "ai_model", "auto"),
            )
            body.value = buffer["text"] or "(empty summary)"
        except ai_service.NotEnoughCredits as exc:
            body.value = f"Out of Assistant credits ({exc.balance} left)."
            body.color = AppColors.WARNING
            column.controls.append(
                ft.TextButton(
                    "Get credits",
                    style=ui.ZERO_PAD,
                    on_click=lambda e: (_close(), _open_wallet()),
                )
            )
        except ai_service.AIMidStream:
            body.value = (buffer["text"] + "\n\nConnection lost mid-summary.").strip()
            body.color = AppColors.WARNING
        except Exception:
            # AIUnavailable and anything unexpected share one honest line.
            body.value = "Assistant unavailable. The full page text is untouched."
            body.color = ft.Colors.ON_SURFACE_VARIANT
        try:
            page.update()
        except Exception:
            pass

    page.run_task(_run)
