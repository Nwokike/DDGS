"""ResultsScreen — search results display with loading, error, and result cards.

Converted from views/results/view_builder.py to declarative @ft.component.
During migration, card builders and empty states are imported from the old
views/ directory.  Phase 5 will move these to components/.
"""

from __future__ import annotations

import flet as ft
from flet import Control

from components.results.empty_states import (
    build_empty_results_box,
    build_error_box,
    build_loading_box,
    build_video_rate_limit_box,
)
from contexts.app_state_ctx import AppStateCtx
from contexts.controller_ctx import ControllerMethodsCtx
from core import theme, tokens
from core.styles import build_banner_ad


@ft.component
def ResultsScreen() -> Control:
    """Search results with loading, error, and result card rendering.

    Reads search_progress and extract_result from observable state.
    Card builders are imported from old views/ during migration.
    """
    state = ft.use_context(AppStateCtx)
    controller = ft.use_context(ControllerMethodsCtx)

    from flet import context as flet_context

    page = flet_context.page

    def _get_page():
        return page

    progress = state.search_progress
    extract_result = state.extract_result

    if progress is None:
        return build_empty_results_box()

    search_type = progress.search_type
    is_running = progress.is_running
    error = progress.error
    results = progress.results
    query = progress.query

    is_video_rate_limit = (search_type == "videos") and progress.is_rate_limited

    def _on_retry(q: str, st: str | None = None):
        _get_page().run_task(controller.start_search, q, st or search_type)

    # ── AppBar ──
    appbar = ft.AppBar(
        leading=ft.IconButton(
            icon=ft.Icons.ARROW_BACK_ROUNDED,
            icon_size=tokens.ICON_MD,
            on_click=lambda _: _get_page().run_task(controller.go_home),
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
                on_click=(
                    lambda _: (
                        controller.cancel_search()
                        if is_running
                        else _get_page().run_task(controller.go_home)
                    )
                ),
                tooltip="Cancel Search" if is_running else "Close",
            ),
            ft.Container(width=8),
        ],
        bgcolor=ft.Colors.TRANSPARENT,
        elevation=0,
    )

    # ── Loading box ──
    loading_box = build_loading_box(is_running)

    # ── Error box ──
    error_box = build_error_box(
        error, query, is_running, is_video_rate_limit, _on_retry
    )

    # ── Results content ──
    if is_video_rate_limit:
        results_content = build_video_rate_limit_box(query, _on_retry)
    elif search_type == "extract":
        # Import extract card from old views/ during migration
        from components.results.cards import _extract_card

        results_content = _extract_card(extract_result, page)
    elif results:
        # Import card builders from old views/ during migration
        from components.results.cards import CARD_BUILDERS, _text_card

        builder = CARD_BUILDERS.get(search_type, _text_card)

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

    return ft.Container(
        content=ft.Column(
            [
                appbar,
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
    )
