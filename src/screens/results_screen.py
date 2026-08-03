"""ResultsScreen — search results display with loading, error, and result cards.

Converted from views/results/view_builder.py to declarative @ft.component.
During migration, card builders and empty states are imported from the old
views/ directory.  Phase 5 will move these to components/.
"""

from __future__ import annotations

import flet as ft
from flet import Control

from contexts.app_state_ctx import AppStateCtx
from contexts.controller_ctx import ControllerMethodsCtx
from core import theme, tokens
from core.styles import build_banner_ad
from core.theme import AppColors


def _build_loading_box(is_running: bool) -> ft.Container:
    return ft.Container(
        content=ft.Column(
            [
                ft.ProgressBar(
                    color=AppColors.PRIMARY,
                    bgcolor=ft.Colors.with_opacity(0.12, AppColors.PRIMARY),
                ),
                ft.Text(
                    "Searching global servers...",
                    size=tokens.FONT_SM,
                    color=ft.Colors.ON_SURFACE_VARIANT,
                    font_family="Outfit",
                    text_align=ft.TextAlign.CENTER,
                ),
            ],
            spacing=tokens.SPACE_SM,
            horizontal_alignment=ft.CrossAxisAlignment.CENTER,
        ),
        padding=ft.Padding(
            tokens.SPACE_LG, tokens.SPACE_LG, tokens.SPACE_LG, tokens.SPACE_LG
        ),
        visible=is_running,
    )


def _build_error_box(
    error: str | None,
    query: str,
    is_running: bool,
    is_video_rate_limit: bool,
    on_retry,
) -> ft.Container:
    err_str = str(error or "").lower()
    is_offline = any(
        kw in err_str
        for kw in ("dns", "connect", "network", "offline", "unreachable", "timed out", "timeout")
    )
    is_server_err = any(kw in err_str for kw in ("500", "502", "503", "504", "server error"))

    if is_offline:
        err_icon = ft.Icons.WIFI_OFF_ROUNDED
        err_title = "No Internet Connection"
        err_desc = (
            "Unable to reach search servers. Please check your Wi-Fi or mobile data "
            "connection and try again."
        )
    elif is_server_err:
        err_icon = ft.Icons.CLOUD_OFF_ROUNDED
        err_title = "Server Unavailable"
        err_desc = (
            f"The search server returned a non-200 error ({error}). "
            "Please try again in a few moments."
        )
    else:
        err_icon = ft.Icons.ERROR_OUTLINE_ROUNDED
        err_title = "Connection Failed"
        err_desc = error or "Unknown protocol error. Check settings and proxies."

    return ft.Container(
        content=ft.Column(
            [
                ft.Icon(err_icon, size=tokens.ICON_LG, color=AppColors.ERROR),
                ft.Text(
                    err_title,
                    size=tokens.FONT_LG,
                    weight=ft.FontWeight.BOLD,
                    color=AppColors.ERROR,
                    font_family="Outfit",
                ),
                ft.Text(
                    err_desc,
                    size=tokens.FONT_SM,
                    text_align=ft.TextAlign.CENTER,
                    style=ft.TextStyle(height=1.4),
                ),
                ft.Container(height=12),
                ft.FilledButton(
                    content=ft.Row(
                        [
                            ft.Icon(
                                ft.Icons.REFRESH_ROUNDED,
                                size=tokens.ICON_SM,
                                color=ft.Colors.WHITE,
                            ),
                            ft.Text(
                                "Retry Search",
                                size=tokens.FONT_SM,
                                weight=ft.FontWeight.W_600,
                                color=ft.Colors.WHITE,
                                font_family="Outfit",
                            ),
                        ],
                        spacing=6,
                        tight=True,
                    ),
                    on_click=lambda _: on_retry(query),
                    style=ft.ButtonStyle(
                        shape=ft.RoundedRectangleBorder(radius=tokens.RADIUS_MD),
                        bgcolor=AppColors.PRIMARY,
                        padding=ft.Padding(20, 12, 20, 12),
                    ),
                ),
            ],
            spacing=tokens.SPACE_MD,
            horizontal_alignment=ft.CrossAxisAlignment.CENTER,
        ),
        padding=ft.Padding(32, 48, 32, 48),
        visible=bool(error) and not is_running and not is_video_rate_limit,
    )


def _build_video_rate_limit_box(query: str, on_retry) -> ft.Container:
    return ft.Container(
        content=ft.Column(
            [
                ft.Icon(
                    ft.Icons.SCHEDULE_ROUNDED,
                    size=tokens.ICON_LG,
                    color=AppColors.WARNING,
                ),
                ft.Text(
                    "Video Search Rate-Limited",
                    size=tokens.FONT_LG,
                    weight=ft.FontWeight.BOLD,
                    color=AppColors.WARNING,
                    font_family="Outfit",
                ),
                ft.Text(
                    "DuckDuckGo strictly rate-limits automated video search queries. "
                    "When rate-limited, zero video results are returned.\n\n"
                    "Please try again later or switch to Web search.",
                    size=tokens.FONT_SM,
                    text_align=ft.TextAlign.CENTER,
                    style=ft.TextStyle(height=1.4),
                ),
                ft.Container(height=12),
                ft.Row(
                    [
                        ft.FilledButton(
                            content=ft.Row(
                                [
                                    ft.Icon(
                                        ft.Icons.SEARCH_ROUNDED,
                                        size=tokens.ICON_SM,
                                        color=ft.Colors.WHITE,
                                    ),
                                    ft.Text(
                                        "Try Web Search",
                                        size=tokens.FONT_SM,
                                        weight=ft.FontWeight.W_600,
                                        color=ft.Colors.WHITE,
                                        font_family="Outfit",
                                    ),
                                ],
                                spacing=6,
                                tight=True,
                            ),
                            on_click=lambda _: on_retry(query, "text"),
                            style=ft.ButtonStyle(
                                shape=ft.RoundedRectangleBorder(radius=tokens.RADIUS_MD),
                                bgcolor=AppColors.PRIMARY,
                                padding=ft.Padding(16, 12, 16, 12),
                            ),
                        ),
                        ft.OutlinedButton(
                            content=ft.Row(
                                [
                                    ft.Icon(
                                        ft.Icons.REFRESH_ROUNDED,
                                        size=tokens.ICON_SM,
                                    ),
                                    ft.Text(
                                        "Retry Video",
                                        size=tokens.FONT_SM,
                                        weight=ft.FontWeight.W_600,
                                        font_family="Outfit",
                                    ),
                                ],
                                spacing=6,
                                tight=True,
                            ),
                            on_click=lambda _: on_retry(query, "videos"),
                            style=ft.ButtonStyle(
                                shape=ft.RoundedRectangleBorder(radius=tokens.RADIUS_MD),
                                padding=ft.Padding(16, 12, 16, 12),
                            ),
                        ),
                    ],
                    alignment=ft.MainAxisAlignment.CENTER,
                    spacing=tokens.SPACE_SM,
                ),
            ],
            spacing=tokens.SPACE_MD,
            horizontal_alignment=ft.CrossAxisAlignment.CENTER,
        ),
        padding=ft.Padding(32, 48, 32, 48),
        expand=True,
        alignment=ft.Alignment.CENTER,
    )


def _build_empty_results_box() -> ft.Container:
    return ft.Container(
        content=ft.Column(
            [
                ft.Icon(
                    ft.Icons.SEARCH_OFF_ROUNDED,
                    size=tokens.ICON_LG,
                    color=ft.Colors.ON_SURFACE_VARIANT,
                ),
                ft.Text(
                    "No matches found.",
                    size=tokens.FONT_MD,
                    color=ft.Colors.ON_SURFACE_VARIANT,
                    text_align=ft.TextAlign.CENTER,
                    font_family="Outfit",
                ),
            ],
            horizontal_alignment=ft.CrossAxisAlignment.CENTER,
            spacing=tokens.SPACE_SM,
        ),
        padding=ft.Padding(32, 48, 32, 48),
        expand=True,
        alignment=ft.Alignment.CENTER,
    )


@ft.component
def ResultsScreen() -> Control:
    """Search results with loading, error, and result card rendering.

    Reads search_progress and extract_result from observable state.
    Card builders are imported from old views/ during migration.
    """
    state = ft.use_context(AppStateCtx)
    controller = ft.use_context(ControllerMethodsCtx)

    progress = state.search_progress
    extract_result = state.extract_result

    if progress is None:
        return _build_empty_results_box()

    search_type = progress.search_type
    is_running = progress.is_running
    error = progress.error
    results = progress.results
    query = progress.query

    is_video_rate_limit = (search_type == "videos") and bool(error)

    def _on_retry(q: str, st: str | None = None):
        controller.start_search(q, st or search_type)

    def _on_back():
        controller.go_home()

    def _on_close():
        if is_running:
            controller.cancel_search()
        else:
            controller.go_home()

    # ── Loading box ──
    loading_box = _build_loading_box(is_running)

    # ── Error box ──
    error_box = _build_error_box(error, query, is_running, is_video_rate_limit, _on_retry)

    # ── Results content ──
    if is_video_rate_limit:
        results_content = _build_video_rate_limit_box(query, _on_retry)
    elif search_type == "extract":
        # Import extract card from old views/ during migration
        from flet import context as flet_context

        from components.results.cards import _extract_card

        results_content = _extract_card(extract_result, flet_context.page)
    elif results:
        # Import card builders from old views/ during migration
        from components.results.cards import CARD_BUILDERS, _text_card

        builder = CARD_BUILDERS.get(search_type, _text_card)

        from flet import context as flet_context

        page = flet_context.page

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
        results_content = _build_empty_results_box()

    results_container = ft.Container(
        content=results_content,
        padding=ft.Padding(
            tokens.SPACE_MD, tokens.SPACE_SM, tokens.SPACE_MD, tokens.SPACE_SM
        ),
        expand=True,
        visible=not is_running and (not bool(error) or is_video_rate_limit),
    )

    from flet import context as flet_context

    return ft.Container(
        content=ft.Column(
            [
                loading_box,
                error_box,
                results_container,
                build_banner_ad(flet_context.page),
            ],
            spacing=0,
            expand=True,
        ),
        gradient=theme.AppStyles.brand_gradient(flet_context.page),
        expand=True,
    )
