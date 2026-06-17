"""Results view — renders per-type result cards + extract output."""

from __future__ import annotations

from typing import Callable

import flet as ft

from core.state import SearchProgress, SearchResult
from core.theme import AppColors
from core.tokens import (
    FONT_XS,
    FONT_SM,
    FONT_MD,
    FONT_LG,
    SPACING_XS,
    SPACING_SM,
    SPACING_MD,
    SPACING_LG,
    SPACING_XL,
    BORDER_RADIUS_MD,
    ICON_MD,
    ICON_LG,
)
from core.utils import logger

LOG_TAG = "ResultsView"


def launch_url(url: str):
    if url:
        import webbrowser

        webbrowser.open(url)


def _text_card(r: SearchResult, i: int) -> ft.Container:
    return ft.Container(
        content=ft.Column(
            controls=[
                ft.Text(
                    r.title,
                    size=FONT_MD,
                    weight=ft.FontWeight.W_600,
                    color=AppColors.PRIMARY,
                    max_lines=2,
                ),
                ft.Text(
                    r.url,
                    size=FONT_XS,
                    color=ft.Colors.ON_SURFACE_VARIANT,
                    no_wrap=False,
                    max_lines=1,
                ),
                ft.Text(
                    r.snippet, size=FONT_SM, color=ft.Colors.ON_SURFACE, max_lines=3
                ),
            ],
            spacing=SPACING_XS,
            tight=True,
        ),
        padding=ft.padding.all(SPACING_MD),
        border_radius=BORDER_RADIUS_MD,
        ink=True,
        on_click=lambda _: launch_url(r.url),
    )


def _image_card(r: SearchResult, i: int) -> ft.Container:
    return ft.Container(
        content=ft.Column(
            controls=[
                ft.Container(
                    content=ft.Image(
                        src=r.thumbnail or r.image_url,
                        fit=ft.ImageFit.COVER,
                        border_radius=BORDER_RADIUS_MD,
                        error_content=ft.Container(
                            content=ft.Icon(
                                ft.Icons.BROKEN_IMAGE_ROUNDED,
                                size=ICON_LG,
                                color=AppColors.OUTLINE,
                            ),
                            height=150,
                            alignment=ft.alignment.center,
                            bgcolor=ft.Colors.SURFACE_CONTAINER,
                            border_radius=BORDER_RADIUS_MD,
                        ),
                    ),
                    height=150,
                    border_radius=BORDER_RADIUS_MD,
                    clip_behavior=ft.ClipBehavior.ANTI_ALIAS,
                ),
                ft.Text(r.title, size=FONT_XS, max_lines=2),
                ft.Text(
                    f"{r.width}x{r.height}" if r.width else "",
                    size=FONT_XS,
                    color=ft.Colors.ON_SURFACE_VARIANT,
                ),
            ],
            spacing=SPACING_XS,
            tight=True,
        ),
        width=180,
        padding=ft.padding.all(SPACING_SM),
        border_radius=BORDER_RADIUS_MD,
        ink=True,
        on_click=lambda _: launch_url(r.url),
    )


def _video_card(r: SearchResult, i: int) -> ft.Container:
    return ft.Container(
        content=ft.Row(
            controls=[
                ft.Container(
                    content=ft.Stack(
                        controls=[
                            ft.Image(
                                src=r.thumbnail or "",
                                fit=ft.ImageFit.COVER,
                                width=160,
                                height=90,
                                border_radius=BORDER_RADIUS_MD,
                                error_content=ft.Container(
                                    ft.Icon(
                                        ft.Icons.VIDEO_LIBRARY_ROUNDED,
                                        size=ICON_LG,
                                        color=AppColors.OUTLINE,
                                    ),
                                    width=160,
                                    height=90,
                                    alignment=ft.alignment.center,
                                    bgcolor=ft.Colors.SURFACE_CONTAINER,
                                    border_radius=BORDER_RADIUS_MD,
                                ),
                            ),
                            ft.Container(
                                content=ft.Text(
                                    r.duration or "",
                                    size=FONT_XS,
                                    color=ft.Colors.WHITE,
                                    weight=ft.FontWeight.W_600,
                                ),
                                padding=ft.padding.all(SPACING_XS),
                                bgcolor=ft.Colors.BLACK54,
                                border_radius=BORDER_RADIUS_MD,
                                right=SPACING_XS,
                                bottom=SPACING_XS,
                            ),
                        ]
                    ),
                ),
                ft.Column(
                    controls=[
                        ft.Text(
                            r.title,
                            size=FONT_MD,
                            weight=ft.FontWeight.W_600,
                            max_lines=2,
                        ),
                        ft.Text(
                            r.publisher or r.source or "",
                            size=FONT_XS,
                            color=ft.Colors.ON_SURFACE_VARIANT,
                        ),
                        ft.Text(r.snippet, size=FONT_SM, max_lines=2),
                        ft.Row(
                            controls=[
                                ft.Icon(
                                    ft.Icons.VISIBILITY_ROUNDED,
                                    size=12,
                                    color=AppColors.OUTLINE,
                                ),
                                ft.Text(
                                    f"{r.views:,}" if r.views else "",
                                    size=FONT_XS,
                                    color=AppColors.OUTLINE,
                                ),
                            ],
                            spacing=SPACING_XS,
                        ),
                    ],
                    spacing=SPACING_XS,
                    expand=True,
                ),
            ],
            spacing=SPACING_MD,
        ),
        padding=ft.padding.all(SPACING_MD),
        border_radius=BORDER_RADIUS_MD,
        ink=True,
        on_click=lambda _: launch_url(r.url),
    )


def _news_card(r: SearchResult, i: int) -> ft.Container:
    return ft.Container(
        content=ft.Row(
            controls=[
                ft.Container(
                    content=ft.Image(
                        src=r.thumbnail or "",
                        fit=ft.ImageFit.COVER,
                        width=80,
                        height=80,
                        border_radius=BORDER_RADIUS_MD,
                        error_content=ft.Container(
                            ft.Icon(
                                ft.Icons.ARTICLE_ROUNDED,
                                size=ICON_LG,
                                color=AppColors.OUTLINE,
                            ),
                            width=80,
                            height=80,
                            alignment=ft.alignment.center,
                            bgcolor=ft.Colors.SURFACE_CONTAINER,
                            border_radius=BORDER_RADIUS_MD,
                        ),
                    ),
                    border_radius=BORDER_RADIUS_MD,
                    clip_behavior=ft.ClipBehavior.ANTI_ALIAS,
                ),
                ft.Column(
                    controls=[
                        ft.Text(
                            r.title,
                            size=FONT_MD,
                            weight=ft.FontWeight.W_600,
                            max_lines=2,
                        ),
                        ft.Text(r.snippet, size=FONT_SM, max_lines=3),
                        ft.Row(
                            controls=[
                                ft.Text(
                                    r.source or "",
                                    size=FONT_XS,
                                    weight=ft.FontWeight.W_500,
                                    color=AppColors.PRIMARY,
                                ),
                                ft.Text(
                                    r.date or "",
                                    size=FONT_XS,
                                    color=ft.Colors.ON_SURFACE_VARIANT,
                                ),
                            ],
                            spacing=SPACING_SM,
                        ),
                    ],
                    spacing=SPACING_XS,
                    expand=True,
                ),
            ],
            spacing=SPACING_MD,
        ),
        padding=ft.padding.all(SPACING_MD),
        border_radius=BORDER_RADIUS_MD,
        ink=True,
        on_click=lambda _: launch_url(r.url),
    )


def _books_card(r: SearchResult, i: int) -> ft.Container:
    return ft.Container(
        content=ft.Column(
            controls=[
                ft.Text(
                    r.title,
                    size=FONT_MD,
                    weight=ft.FontWeight.W_600,
                    color=AppColors.PRIMARY,
                    max_lines=2,
                ),
                ft.Text(
                    r.url, size=FONT_XS, color=ft.Colors.ON_SURFACE_VARIANT, max_lines=1
                ),
                ft.Text(r.snippet, size=FONT_SM, max_lines=3),
            ],
            spacing=SPACING_XS,
            tight=True,
        ),
        padding=ft.padding.all(SPACING_MD),
        border_radius=BORDER_RADIUS_MD,
        ink=True,
        on_click=lambda _: launch_url(r.url),
    )


def _extract_card(result: dict | None) -> ft.Container:
    """Render extract result — shows the content."""
    if not result:
        return ft.Container(
            content=ft.Text(
                "No content extracted", size=FONT_MD, color=ft.Colors.ON_SURFACE_VARIANT
            ),
            padding=ft.padding.all(SPACING_XL),
        )
    content = result.get("content", "")
    url = result.get("url", "")

    if isinstance(content, bytes):
        display = ft.Text(
            f"[Binary content — {len(content)} bytes]",
            size=FONT_SM,
            color=ft.Colors.ON_SURFACE_VARIANT,
        )
    else:
        display = ft.Text(str(content), size=FONT_SM, selectable=True, max_lines=200)

    return ft.Container(
        content=ft.Column(
            controls=[
                ft.Text(
                    "Extracted from:", size=FONT_XS, color=ft.Colors.ON_SURFACE_VARIANT
                ),
                ft.Text(
                    url,
                    size=FONT_SM,
                    color=AppColors.PRIMARY,
                    selectable=True,
                    max_lines=2,
                ),
                ft.Divider(height=SPACING_SM),
                display,
            ],
            spacing=SPACING_XS,
            scroll=ft.ScrollMode.AUTO,
        ),
        padding=ft.padding.all(SPACING_MD),
        border_radius=BORDER_RADIUS_MD,
        bgcolor=ft.Colors.SURFACE_CONTAINER,
    )


CARD_BUILDERS = {
    "text": _text_card,
    "images": _image_card,
    "videos": _video_card,
    "news": _news_card,
    "books": _books_card,
}


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

    logger.info(
        f"[{LOG_TAG}] Results view: type={search_type}, results={len(results)}, running={is_running}"
    )

    # ── Header ──
    header = ft.Container(
        content=ft.Row(
            controls=[
                ft.IconButton(
                    icon=ft.Icons.ARROW_BACK_ROUNDED,
                    icon_size=ICON_MD,
                    on_click=lambda _: on_navigate("/home"),
                ),
                ft.Column(
                    controls=[
                        ft.Text(
                            query or "Result",
                            size=FONT_LG,
                            weight=ft.FontWeight.W_600,
                            max_lines=1,
                        ),
                        ft.Text(
                            f"{search_type.capitalize()}",
                            size=FONT_XS,
                            color=ft.Colors.ON_SURFACE_VARIANT,
                        ),
                    ],
                    spacing=SPACING_XS,
                    expand=True,
                ),
                ft.IconButton(
                    icon=ft.Icons.CLOSE_ROUNDED,
                    icon_size=ICON_MD,
                    on_click=lambda _: (
                        on_cancel() if is_running else on_navigate("/home")
                    ),
                ),
            ],
            spacing=SPACING_SM,
        ),
        padding=ft.padding.symmetric(horizontal=SPACING_MD, vertical=SPACING_SM),
        border=ft.border.only(bottom=ft.BorderSide(1, ft.Colors.OUTLINE_VARIANT)),
    )

    # ── Loading ──
    loading = ft.Container(
        content=ft.Column(
            controls=[
                ft.ProgressBar(
                    color=AppColors.PRIMARY, bgcolor=AppColors.PRIMARY_LIGHT
                ),
                ft.Text(
                    "Searching...",
                    size=FONT_SM,
                    color=ft.Colors.ON_SURFACE_VARIANT,
                    text_align=ft.TextAlign.CENTER,
                ),
            ],
            spacing=SPACING_SM,
            horizontal_alignment=ft.CrossAxisAlignment.CENTER,
        ),
        padding=ft.padding.all(SPACING_LG),
        visible=is_running,
    )

    # ── Error ──
    error_banner = ft.Container(
        content=ft.Column(
            controls=[
                ft.Icon(
                    ft.Icons.ERROR_OUTLINE_ROUNDED, size=ICON_LG, color=AppColors.ERROR
                ),
                ft.Text(
                    "Search Failed",
                    size=FONT_LG,
                    weight=ft.FontWeight.W_600,
                    color=AppColors.ERROR,
                    text_align=ft.TextAlign.CENTER,
                ),
                ft.Text(
                    error or "Unknown error",
                    size=FONT_SM,
                    text_align=ft.TextAlign.CENTER,
                ),
                ft.ElevatedButton(
                    "Try Again",
                    icon=ft.Icons.REFRESH_ROUNDED,
                    on_click=lambda _: on_restart(query),
                ),
            ],
            spacing=SPACING_MD,
            horizontal_alignment=ft.CrossAxisAlignment.CENTER,
        ),
        padding=ft.padding.all(SPACING_XL),
        visible=bool(error) and not is_running,
    )

    # ── Results ──
    if search_type == "extract":
        results_content = _extract_card(extract_result)
    elif results:
        builder = CARD_BUILDERS.get(search_type, _text_card)
        cards = [builder(r, i) for i, r in enumerate(results)]
        results_content = ft.Column(
            controls=[
                ft.Row(
                    controls=[
                        ft.Text(
                            f"{len(results)} results",
                            size=FONT_SM,
                            color=ft.Colors.ON_SURFACE_VARIANT,
                            weight=ft.FontWeight.W_500,
                        )
                    ]
                ),
                *cards,
            ],
            spacing=SPACING_SM,
            scroll=ft.ScrollMode.AUTO,
            expand=True,
        )
    else:
        results_content = ft.Container(
            content=ft.Text(
                "No results found" if not is_running else "",
                size=FONT_MD,
                color=ft.Colors.ON_SURFACE_VARIANT,
                text_align=ft.TextAlign.CENTER,
            ),
            padding=ft.padding.all(SPACING_XL),
            expand=True,
        )

    results_container = ft.Container(
        content=results_content,
        padding=ft.padding.symmetric(horizontal=SPACING_MD, vertical=SPACING_SM),
        expand=True,
    )

    return ft.View(
        route="/results",
        controls=[
            ft.SafeArea(
                content=ft.Column(
                    controls=[header, loading, error_banner, results_container],
                    spacing=0,
                    expand=True,
                )
            )
        ],
        padding=0,
        spacing=0,
        bgcolor=AppColors.BACKGROUND,
    )
