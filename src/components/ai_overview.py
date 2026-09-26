"""Assistant overview card - Google-style summary above normal text/news results.

Companion to the agentic chat: the chat is where the AI *acts* (searches,
fetches, iterates); this card is the passive glanceable answer for the
search you just ran. Free - COST_OVERVIEW is 0, auto-triggered when AI mode is
on; the router serves it free of upstream cost.

Collapsed by default with a clamped body + "Read full report"; expanded shows
the entire markdown, source rows with thumbnails, and related pills.
"""

from __future__ import annotations

import flet as ft

from components.results.downloader import launch_url
from components.wallet import show_wallet_dialog
from core import theme, tokens, ui
from core.state import state
from core.theme import AppColors


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
                ft.Icons.CHAT_BUBBLE_OUTLINE_ROUNDED,
                size=tokens.ICON_SM,
                color=AppColors.ACCENT,
            ),
            ft.Text(
                "Assistant overview",
                size=tokens.FONT_SM,
                weight=ft.FontWeight.W_700,
                font_family="Outfit",
            ),
            ft.Container(expand=True),
            ft.TextButton(
                "Ask Assistant",
                on_click=lambda e: ctrl
                and ctrl.open_chat(
                    {
                        "question": f"Give me a deeper, well-sourced answer about: {ov.query}",
                        "auto": True,
                    }
                ),
            ),
            ft.IconButton(
                icon=ft.Icons.CLOSE_ROUNDED,
                icon_size=tokens.ICON_SM,
                tooltip="Hide Assistant overviews",
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
        body.append(
            ui.notice(
                "Out of free Assistant overviews. Results below are unaffected.",
                level="warning",
                action_label="Get credits",
                on_action=lambda e: show_wallet_dialog(page),
            )
        )
    elif ov.error == "midstream":
        body.append(
            ui.notice(
                "Connection lost mid-overview. Tap Ask Assistant to retry.",
                level="warning",
            )
        )
    elif ov.error == "unavailable":
        body.append(
            ui.notice(
                "Assistant unavailable. Showing classic results.",
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
        else:
            chips = [
                ft.Container(
                    content=ft.Text(
                        str(i + 1),
                        size=tokens.FONT_XS,
                        weight=ft.FontWeight.W_700,
                        color=AppColors.PRIMARY,
                    ),
                    padding=ft.Padding(10, 6, 10, 6),
                    border_radius=6,
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
            ],
            spacing=tokens.SPACE_XS,
            tight=True,
        ),
        padding=ft.Padding(14, 12, 14, 12),
        border_radius=tokens.RADIUS_LG,
        bgcolor=theme.adaptive_glass_bg(page),
        border=ft.Border.all(1, theme.adaptive_glass_border(page)),
    )
