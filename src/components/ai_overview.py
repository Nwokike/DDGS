"""AI overview card — Google-style summary above normal text/news results.

Companion to the agentic chat: the chat is where the AI *acts* (searches,
fetches, iterates); this card is the passive glanceable answer for the
search you just ran. One credit per overview, auto-triggered when AI mode is
on; the router serves it free of upstream cost.

Collapsed by default with a clamped body + "Read full report"; expanded shows
the entire markdown, source rows with thumbnails, and related pills.
"""

from __future__ import annotations

import flet as ft

from components.results.downloader import launch_url
from components.wallet import show_wallet_dialog
from core import theme, tokens
from core.state import state
from core.theme import AppColors

_DISCLOSURE = "Sends your query + short result snippets to Kiri AI (router first). No history, no training."


def _domain(url: str) -> str:
    if "//" in url:
        return url.split("/")[2].removeprefix("www.")
    return url[:40]


def _open_in_app(page: ft.Page, url: str) -> None:
    async def _go() -> None:
        if not url:
            return
        from components.results.content_fetcher import _fetch_and_show

        try:
            await _fetch_and_show(page, url)
        except Exception:
            await launch_url(url)

    page.run_task(_go)


def _source_click(page: ft.Page, source: dict):
    """Factory for source handlers (avoids calls in lambda defaults)."""
    return lambda e: _open_in_app(page, source.get("url", ""))


def build_ai_overview(page: ft.Page) -> ft.Control:
    """Empty container unless an overview exists for the current results."""
    empty = ft.Container(height=0)
    if not state.ai_mode_enabled:
        return empty
    ov = state.ai_overview
    if ov is None:
        return empty
    ctrl = getattr(page, "_ddgs_controller", None)
    expanded = state.ai_overview_expanded

    header = ft.Row(
        [
            ft.Icon(
                ft.Icons.AUTO_AWESOME_ROUNDED,
                size=tokens.ICON_SM,
                color=AppColors.ACCENT,
            ),
            ft.Text(
                "AI overview",
                size=tokens.FONT_SM,
                weight=ft.FontWeight.W_700,
                font_family="Outfit",
            ),
            ft.Container(expand=True),
            ft.TextButton(
                "Ask AI",
                icon=ft.Icons.CHAT_BUBBLE_OUTLINE_ROUNDED,
                on_click=lambda e: ctrl
                and ctrl.open_chat(
                    {
                        "question": f"Give me a deeper, well-sourced answer about: {ov.query}",
                        "auto": True,
                    }
                ),
            ),
            *(
                [
                    ft.IconButton(
                        icon=ft.Icons.EXPAND_LESS_ROUNDED
                        if expanded
                        else ft.Icons.EXPAND_MORE_ROUNDED,
                        icon_size=18,
                        tooltip="Show less" if expanded else "Read full report",
                        on_click=lambda e: setattr(
                            state, "ai_overview_expanded", not expanded
                        ),
                    )
                ]
                if ov.text
                else []
            ),
            ft.IconButton(
                icon=ft.Icons.CLOSE_ROUNDED,
                icon_size=16,
                tooltip="Hide AI overviews",
                on_click=lambda e: ctrl and ctrl.save("ai_mode", False),
            ),
        ],
        spacing=4,
        vertical_alignment=ft.CrossAxisAlignment.CENTER,
    )

    body: list[ft.Control] = []
    if ov.is_running:
        body.append(
            ft.Row(
                [
                    ft.ProgressRing(width=13, height=13, stroke_width=2),
                    ft.Text(
                        f"Reading {len(ov.sources)} sources…",
                        size=tokens.FONT_XS,
                        color=ft.Colors.ON_SURFACE_VARIANT,
                    ),
                ],
                spacing=7,
            )
        )
    if ov.text:
        markdown = ft.Markdown(
            ov.text,
            selectable=True,
            extension_set="gitHubWeb",
            on_tap_link=lambda e: _open_in_app(page, e.data),
        )
        if expanded:
            body.append(markdown)
        else:
            body.append(
                ft.Container(
                    content=markdown,
                    height=150,  # clamped preview
                    clip_behavior=ft.ClipBehavior.HARD_EDGE,
                )
            )
            body.append(
                ft.TextButton(
                    "Read full report",
                    icon=ft.Icons.EXPAND_MORE_ROUNDED,
                    on_click=lambda e: setattr(state, "ai_overview_expanded", True),
                    style=ft.ButtonStyle(padding=ft.Padding(0, 0, 0, 0)),
                )
            )
    if ov.error == "credits":
        body.extend(
            [
                ft.Text(
                    "Out of free AI overviews — results below are unaffected.",
                    size=tokens.FONT_XS,
                    color=AppColors.WARNING,
                ),
                ft.TextButton(
                    "Get credits",
                    on_click=lambda e: show_wallet_dialog(page),
                    style=ft.ButtonStyle(padding=ft.Padding(0, 0, 0, 0)),
                ),
            ]
        )
    elif ov.error == "midstream":
        body.append(
            ft.Text(
                "⚠ Connection lost mid-overview — tap Ask AI to retry.",
                size=tokens.FONT_XS,
                color=AppColors.WARNING,
            )
        )
    elif ov.error == "unavailable":
        body.append(
            ft.Text(
                "AI unavailable — showing classic results.",
                size=tokens.FONT_XS,
                color=ft.Colors.ON_SURFACE_VARIANT,
                italic=True,
            )
        )
    elif ov.is_done and ov.sources:
        if expanded:
            # full source list with thumbnails
            for i, s in enumerate(ov.sources):
                thumb = s.get("thumb") or ""
                body.append(
                    ft.GestureDetector(
                        on_tap=_source_click(page, s),
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
                                                ft.Icons.LANGUAGE_ROUNDED,
                                                size=13,
                                                color=AppColors.PRIMARY,
                                            ),
                                        ),
                                        clip_behavior=ft.ClipBehavior.HARD_EDGE,
                                    )
                                    if thumb
                                    else ft.Icon(
                                        ft.Icons.LANGUAGE_ROUNDED,
                                        size=13,
                                        color=AppColors.PRIMARY,
                                    )
                                ),
                                ft.Text(
                                    f"[{i + 1}] {s.get('title') or s.get('url', '')}",
                                    size=tokens.FONT_XS,
                                    max_lines=1,
                                    overflow=ft.TextOverflow.ELLIPSIS,
                                    expand=True,
                                ),
                                ft.Text(
                                    _domain(s.get("url", "")),
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
        else:
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
                    tooltip=(s.get("title") or "")[:80],
                    on_click=_source_click(page, s),
                )
                for i, s in enumerate(ov.sources)
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
    if ov.is_done and ov.related:
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
                border=ft.Border.all(1, ft.Colors.with_opacity(0.3, AppColors.PRIMARY)),
                ink=True,
                tooltip=f"Search: {q}",
                on_click=lambda e, qq=q: ctrl
                and page.run_task(ctrl.start_search, qq, "text"),
            )
            for q in ov.related
        ]
        body.append(ft.Row(pills, spacing=6, wrap=True, run_spacing=4))

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
            spacing=tokens.SPACE_XS,
            tight=True,
        ),
        padding=ft.Padding(14, 12, 14, 12),
        border_radius=tokens.RADIUS_LG,
        bgcolor=theme.adaptive_glass_bg(page),
        border=ft.Border.all(1, theme.adaptive_glass_border(page)),
    )
