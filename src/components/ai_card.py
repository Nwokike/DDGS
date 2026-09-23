"""AI answer card — rendered above text/news results.

States: running skeleton · done (citations, sources, related, follow-up) ·
zero-credits · unavailable (one quiet line — classic results unaffected).
A pure function of AppState: the controller swaps whole AiAnswer objects to
stream tokens (>=0.2s), which re-renders this component.
"""

from __future__ import annotations

import flet as ft

from components.results.downloader import launch_url
from components.wallet import show_wallet_dialog
from core import theme, tokens
from core.state import state
from core.theme import AppColors

_DISCLOSURE = (
    "Sends your query + short result snippets to Kiri AI "
    "(your in-app router first). No history, no identity, no training."
)


def build_ai_answer_card(page: ft.Page, search_type: str) -> ft.Control:
    """Empty container unless AI mode is on for a text/news result set."""
    empty = ft.Container(height=0)
    if not state.ai_mode_enabled or search_type not in ("text", "news"):
        return empty
    answer = state.current_ai_answer
    if answer is None:
        return empty

    ctrl = getattr(page, "_ddgs_controller", None)

    def _open_url(url: str) -> None:
        if url:
            page.run_task(launch_url, url)

    header = ft.Row(
        [
            ft.Icon(
                ft.Icons.AUTO_AWESOME_ROUNDED,
                size=tokens.ICON_SM,
                color=AppColors.ACCENT,
            ),
            ft.Text(
                "DDGS AI",
                size=tokens.FONT_SM,
                weight=ft.FontWeight.W_700,
                font_family="Outfit",
            ),
            ft.Container(
                content=ft.Text(
                    answer.mode.upper(),
                    size=9,
                    color=ft.Colors.ON_SURFACE_VARIANT,
                    weight=ft.FontWeight.W_600,
                ),
                padding=ft.Padding(5, 1, 5, 1),
                border_radius=4,
                bgcolor=ft.Colors.with_opacity(0.08, ft.Colors.ON_SURFACE),
            ),
            ft.Container(expand=True),
            ft.IconButton(
                icon=ft.Icons.CLOSE_ROUNDED,
                icon_size=16,
                tooltip="Hide AI answers",
                on_click=lambda e: ctrl and ctrl.save("ai_mode", False),
            ),
        ],
        spacing=6,
        vertical_alignment=ft.CrossAxisAlignment.CENTER,
    )

    body: list[ft.Control] = []

    if answer.error == "credits":
        # Zero-state: degrade, never dead-end.
        body = [
            ft.Text(
                "Out of free AI answers — results below are unaffected.",
                size=tokens.FONT_SM,
                color=ft.Colors.ON_SURFACE_VARIANT,
            ),
            ft.Row(
                [
                    ft.FilledButton(
                        "Get credits",
                        icon=ft.Icons.ADD_CIRCLE_ROUNDED,
                        on_click=lambda e: show_wallet_dialog(page),
                        style=ft.ButtonStyle(bgcolor=AppColors.PRIMARY),
                    ),
                    ft.TextButton(
                        "Premium: 200/day",
                        on_click=lambda e: ctrl and ctrl.navigate_tab(2),
                    ),
                ],
                spacing=8,
            ),
            ft.Text(
                "Free refill arrives at 00:00 UTC.",
                size=tokens.FONT_XS,
                color=ft.Colors.ON_SURFACE_VARIANT,
            ),
        ]
    elif answer.error == "unavailable":
        body = [
            ft.Text(
                "AI unavailable — showing classic results.",
                size=tokens.FONT_SM,
                color=ft.Colors.ON_SURFACE_VARIANT,
                italic=True,
            )
        ]
    else:
        if answer.is_running:
            body.append(
                ft.Row(
                    [
                        ft.ProgressRing(width=14, height=14, stroke_width=2),
                        ft.Text(
                            f"Analyzing {len(answer.sources)} sources…",
                            size=tokens.FONT_SM,
                            color=ft.Colors.ON_SURFACE_VARIANT,
                        ),
                    ],
                    spacing=8,
                )
            )
        if answer.followup and (answer.is_running or answer.is_done):
            body.append(
                ft.Text(
                    f"You asked: {answer.followup}",
                    size=tokens.FONT_XS,
                    color=AppColors.PRIMARY,
                    italic=True,
                )
            )
        if answer.text:
            # Citations were rewritten to [n](url) by the controller.
            body.append(
                ft.Markdown(
                    answer.text,
                    selectable=True,
                    extension_set="gitHubWeb",
                    on_tap_link=lambda e: _open_url(e.data),
                )
            )
        if answer.error == "midstream":
            body.append(
                ft.Text(
                    "⚠ Connection lost mid-answer — ask a follow-up to retry.",
                    size=tokens.FONT_XS,
                    color=AppColors.WARNING,
                )
            )

        if answer.is_done and answer.sources:

            def _chip_click(url: str):
                return lambda e: _open_url(url)

            chips = [
                ft.Container(
                    content=ft.Text(
                        str(i + 1),
                        size=10,
                        weight=ft.FontWeight.W_700,
                        color=AppColors.PRIMARY,
                    ),
                    padding=ft.Padding(6, 2, 6, 2),
                    border_radius=4,
                    bgcolor=ft.Colors.with_opacity(0.1, AppColors.PRIMARY),
                    ink=True,
                    tooltip=(src.get("title") or "")[:80],
                    on_click=_chip_click(src.get("url", "")),
                )
                for i, src in enumerate(answer.sources)
            ]
            body.append(
                ft.Row(
                    [
                        ft.Text(
                            "Sources:",
                            size=tokens.FONT_XS,
                            color=ft.Colors.ON_SURFACE_VARIANT,
                        ),
                        *chips,
                    ],
                    spacing=4,
                    wrap=True,
                )
            )

        if answer.is_done and answer.related:
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
                    on_click=lambda e, qq=q: ctrl
                    and page.run_task(ctrl.start_search, qq, "text"),
                )
                for q in answer.related
            ]
            body.append(
                ft.Row(
                    [
                        ft.Text(
                            "Related:",
                            size=tokens.FONT_XS,
                            color=ft.Colors.ON_SURFACE_VARIANT,
                        ),
                        *pills,
                    ],
                    spacing=6,
                    wrap=True,
                )
            )

        can_ask = (
            not answer.is_running
            and bool(answer.sources)
            and answer.error in (None, "midstream")
        )
        if can_ask:
            field_ref = ft.Ref[ft.TextField]()

            def _submit_field(field) -> None:
                value = (field.value or "").strip()
                field.value = ""
                try:
                    field.update()
                except Exception:
                    pass
                if value and ctrl:
                    page.run_task(ctrl.ask_followup, value)

            body.append(
                ft.Row(
                    [
                        ft.TextField(
                            ref=field_ref,
                            hint_text="Ask a follow-up…",
                            expand=True,
                            dense=True,
                            text_size=tokens.FONT_XS,
                            content_padding=ft.Padding(10, 6, 10, 6),
                            border_radius=tokens.RADIUS_MD,
                            on_submit=lambda e: _submit_field(e.control),
                        ),
                        ft.IconButton(
                            icon=ft.Icons.SEND_ROUNDED,
                            icon_size=18,
                            tooltip="Send follow-up",
                            on_click=lambda e: field_ref.current
                            and _submit_field(field_ref.current),
                        ),
                    ],
                    spacing=4,
                    vertical_alignment=ft.CrossAxisAlignment.CENTER,
                )
            )
            if answer.is_done and answer.mode == "standard":
                body.append(
                    ft.Row(
                        [
                            ft.TextButton(
                                "Deep synthesis (5 credits)"
                                if not state.is_premium
                                else "Deep synthesis",
                                icon=ft.Icons.AUTO_AWESOME_ROUNDED,
                                on_click=lambda e: ctrl
                                and page.run_task(
                                    ctrl.run_ai_answer,
                                    answer.query,
                                    answer.sources,
                                    "deep",
                                ),
                            ),
                        ],
                        alignment=ft.MainAxisAlignment.END,
                    )
                )

    return ft.Container(
        content=ft.Column(
            [
                header,
                *body,
                ft.Text(
                    _DISCLOSURE,
                    size=9,
                    color=ft.Colors.with_opacity(0.5, ft.Colors.ON_SURFACE),
                ),
            ],
            spacing=tokens.SPACE_SM,
            tight=True,
        ),
        padding=ft.Padding(14, 12, 14, 12),
        border_radius=tokens.RADIUS_LG,
        bgcolor=theme.adaptive_glass_bg(page),
        border=ft.Border.all(1, theme.adaptive_glass_border(page)),
    )
