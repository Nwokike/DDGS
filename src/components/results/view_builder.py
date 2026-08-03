from __future__ import annotations

from collections.abc import Callable

import flet as ft

from components.results.cards import CARD_BUILDERS, _extract_card, _text_card
from components.results.empty_states import (
    build_empty_results_box,
    build_error_box,
    build_loading_box,
    build_video_rate_limit_box,
)
from core import theme, tokens
from core.state import SearchProgress
from core.styles import build_banner_ad


def build_results_view(
    page: ft.Page,
    progress: SearchProgress,
    on_navigate: Callable,
    on_restart: Callable,
    on_cancel: Callable,
    extract_result: dict | None = None,
) -> ft.View:
    search_type = progress.search_type
    is_running = progress.is_running
    error = progress.error
    results = progress.results
    query = progress.query

    # ── AppBar ──
    appbar = ft.AppBar(
        leading=ft.IconButton(
            icon=ft.Icons.ARROW_BACK_ROUNDED,
            icon_size=tokens.ICON_MD,
            on_click=lambda _: on_navigate("/home"),
            tooltip="Back to Home",
        ),
        title=ft.Column(
            [
                ft.Text(
                    query or "Search Results",
                    size=tokens.FONT_LG,
                    weight=ft.FontWeight.W_600,
                    max_lines=1,
                    overflow=ft.TextOverflow.ELLIPSIS,
                    font_family="Outfit",
                ),
                ft.Text(
                    f"{search_type.capitalize()} \u00b7 {len(results)} results"
                    if not is_running
                    else f"Loading {search_type.capitalize()}...",
                    size=tokens.FONT_XS,
                    color=ft.Colors.ON_SURFACE_VARIANT,
                ),
            ],
            spacing=2,
        ),
        actions=[
            ft.IconButton(
                icon=ft.Icons.CLOSE_ROUNDED,
                icon_size=tokens.ICON_MD,
                on_click=lambda _: on_cancel() if is_running else on_navigate("/home"),
                tooltip="Cancel Search" if is_running else "Close",
            ),
            ft.Container(width=8),
        ],
        bgcolor=ft.Colors.TRANSPARENT,
        elevation=0,
    )

    loading_box = build_loading_box(is_running)

    is_video_rate_limit = (search_type == "videos") and bool(error)

    error_box = build_error_box(
        error, query, is_running, is_video_rate_limit, on_restart
    )

    # ── Render Search results ──
    if is_video_rate_limit:
        results_content = build_video_rate_limit_box(query, on_restart)
    elif search_type == "extract":
        results_content = _extract_card(extract_result, page)
    elif results:
        builder = CARD_BUILDERS.get(search_type, _text_card)

        # Grid layout for images, list layout for others
        if search_type == "images":
            cards = [builder(r, i, page) for i, r in enumerate(results)]
            results_content = ft.Column(
                [
                    ft.Text(
                        f"Found {len(results)} images in index",
                        size=tokens.FONT_XS,
                        color=ft.Colors.ON_SURFACE_VARIANT,
                        weight=ft.FontWeight.W_500,
                        font_family="Outfit",
                    ),
                    ft.Row(
                        cards,
                        wrap=True,
                        spacing=10,
                        run_spacing=10,
                        alignment=ft.MainAxisAlignment.START,
                    ),
                ],
                spacing=tokens.SPACE_SM,
                scroll=ft.ScrollMode.AUTO,
                expand=True,
            )
        else:
            cards = []
            for idx, r in enumerate(results):
                if idx > 0 and idx % 4 == 0:
                    cards.append(build_banner_ad(page))
                cards.append(builder(r, idx, page))
            results_content = ft.Column(
                [
                    ft.Row(
                        [
                            ft.Icon(
                                ft.Icons.TRAVEL_EXPLORE_ROUNDED,
                                size=14,
                                color=ft.Colors.ON_SURFACE_VARIANT,
                            ),
                            ft.Text(
                                f"{len(results)} listings retrieved",
                                size=tokens.FONT_XS,
                                color=ft.Colors.ON_SURFACE_VARIANT,
                                weight=ft.FontWeight.W_500,
                                font_family="Outfit",
                            ),
                        ],
                        spacing=6,
                    ),
                    *cards,
                ],
                spacing=tokens.SPACE_SM,
                scroll=ft.ScrollMode.AUTO,
                expand=True,
            )
    else:
        results_content = build_empty_results_box()

    results_container = ft.Container(
        content=results_content,
        padding=ft.Padding(
            tokens.SPACE_MD, tokens.SPACE_SM, tokens.SPACE_MD, tokens.SPACE_SM
        ),
        expand=True,
        visible=not is_running and (not bool(error) or is_video_rate_limit),
    )

    return ft.View(
        route="/results",
        controls=[
            ft.SafeArea(
                content=ft.Container(
                    content=ft.Column(
                        [
                            loading_box,
                            error_box,
                            results_container,
                            build_banner_ad(page),
                        ],
                        spacing=0,
                        expand=True,
                    ),
                    gradient=theme.AppStyles.brand_gradient(page),
                    expand=True,
                ),
                expand=True,
            )
        ],
        appbar=appbar,
        padding=0,
        spacing=0,
    )
