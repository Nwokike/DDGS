from __future__ import annotations

from typing import Callable

import flet as ft

from core.state import SearchProgress, SearchResult, state
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
    BORDER_RADIUS_LG,
    ICON_SM,
    ICON_MD,
    ICON_LG,
    ANIMATION_FAST,
)
from services.search_service import SearchService

LOG_TAG = "ResultsView"

_search_service = SearchService()


def launch_url(url: str):
    if url:
        import webbrowser

        webbrowser.open(url)


def _show_result_sheet(page: ft.Page, r: SearchResult, search_type: str):
    """Show a bottom sheet with result info, open link, and fetch preview."""
    sheet_content = ft.Container(
        content=ft.Column(
            [
                ft.Row(
                    [
                        ft.Icon(
                            ft.Icons.CAPTION_ROUNDED
                            if search_type != "extract"
                            else ft.Icons.DOWNLOAD_ROUNDED,
                            size=ICON_MD,
                            color=AppColors.PRIMARY,
                        ),
                        ft.Text(
                            "Result Details",
                            size=FONT_LG,
                            weight=ft.FontWeight.BOLD,
                            expand=True,
                        ),
                        ft.IconButton(
                            icon=ft.Icons.CLOSE_ROUNDED,
                            icon_size=ICON_MD,
                            on_click=lambda _: _close_sheet(page),
                        ),
                    ],
                    spacing=SPACING_SM,
                ),
                ft.Divider(
                    height=1, color=ft.Colors.with_opacity(0.1, ft.Colors.ON_SURFACE)
                ),
                ft.Container(height=8),
                ft.Text(r.title, size=FONT_MD, weight=ft.FontWeight.W_600, max_lines=3),
                ft.Text(
                    r.url,
                    size=FONT_XS,
                    color=AppColors.PRIMARY,
                    selectable=True,
                    max_lines=2,
                ),
                ft.Container(height=8),
                ft.Row(
                    [
                        ft.FilledButton(
                            content=ft.Row(
                                [
                                    ft.Icon(
                                        ft.Icons.OPEN_IN_BROWSER_ROUNDED,
                                        size=ICON_SM,
                                        color=ft.Colors.WHITE,
                                    ),
                                    ft.Text(
                                        "Open in Browser",
                                        size=FONT_SM,
                                        weight=ft.FontWeight.W_600,
                                        color=ft.Colors.WHITE,
                                    ),
                                ],
                                spacing=6,
                                tight=True,
                            ),
                            on_click=lambda _: (_close_sheet(page), launch_url(r.url)),
                            style=ft.ButtonStyle(
                                shape=ft.RoundedRectangleBorder(
                                    radius=BORDER_RADIUS_MD
                                ),
                                padding=ft.Padding(16, 10, 16, 10),
                            ),
                            expand=True,
                        ),
                    ],
                    spacing=SPACING_SM,
                ),
                ft.Container(height=4),
                ft.OutlinedButton(
                    content=ft.Row(
                        [
                            ft.Icon(ft.Icons.DOWNLOAD_ROUNDED, size=ICON_SM),
                            ft.Text(
                                "Fetch Page Content",
                                size=FONT_SM,
                                weight=ft.FontWeight.W_500,
                            ),
                        ],
                        spacing=6,
                        tight=True,
                    ),
                    on_click=lambda _: page.run_task(_fetch_and_show, page, r.url),
                    style=ft.ButtonStyle(
                        shape=ft.RoundedRectangleBorder(radius=BORDER_RADIUS_MD),
                        side=ft.BorderSide(1, AppColors.PRIMARY),
                        padding=ft.Padding(16, 10, 16, 10),
                    ),
                    expand=True,
                ),
            ],
            spacing=SPACING_SM,
            scroll=ft.ScrollMode.AUTO,
        ),
        padding=ft.Padding(20, 16, 20, 20),
    )

    sheet = ft.BottomSheet(
        content=sheet_content,
        open=True,
        elevation=8,
    )
    page.overlay.append(sheet)
    page.update()


def _close_sheet(page: ft.Page):
    for o in list(page.overlay):
        if isinstance(o, ft.BottomSheet):
            o.open = False
            page.overlay.remove(o)
    page.update()


async def _fetch_and_show(page: ft.Page, url: str):
    _close_sheet(page)
    loading = ft.AlertDialog(
        modal=True,
        title=ft.Text("Fetching page content..."),
        content=ft.ProgressBar(color=AppColors.PRIMARY),
    )
    page.overlay.append(loading)
    loading.open = True
    page.update()

    result = await _search_service.extract_url(url, fmt=state.extract_format)

    loading.open = False
    page.overlay.remove(loading)

    if not result:
        snack = ft.SnackBar(
            ft.Text("Could not fetch content from this URL"), bgcolor=AppColors.ERROR
        )
        page.overlay.append(snack)
        snack.open = True
        page.update()
        return

    content = result.get("content", "")
    if isinstance(content, bytes):
        content = f"[Binary content \u2014 {len(content)} bytes]"

    preview_sheet = ft.BottomSheet(
        content=ft.Container(
            content=ft.Column(
                [
                    ft.Row(
                        [
                            ft.Icon(
                                ft.Icons.DOWNLOAD_ROUNDED,
                                size=ICON_MD,
                                color=AppColors.PRIMARY,
                            ),
                            ft.Text(
                                "Fetched Content",
                                size=FONT_LG,
                                weight=ft.FontWeight.BOLD,
                                expand=True,
                            ),
                            ft.IconButton(
                                icon=ft.Icons.CLOSE_ROUNDED,
                                icon_size=ICON_MD,
                                on_click=lambda _: _close_sheet(page),
                            ),
                        ],
                        spacing=SPACING_SM,
                    ),
                    ft.Divider(
                        height=1,
                        color=ft.Colors.with_opacity(0.1, ft.Colors.ON_SURFACE),
                    ),
                    ft.Container(
                        content=ft.Text(str(content), size=FONT_SM, selectable=True),
                        expand=True,
                        scroll=ft.ScrollMode.AUTO,
                    ),
                ],
                spacing=SPACING_SM,
            ),
            padding=ft.Padding(20, 16, 20, 20),
            height=page.window.height * 0.7 if page.window.height else 500,
        ),
        open=True,
        elevation=8,
    )
    page.overlay.append(preview_sheet)
    page.update()


def _text_card(r: SearchResult, i: int, page: ft.Page) -> ft.Container:
    return ft.Container(
        content=ft.Column(
            [
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
        padding=ft.Padding(SPACING_MD, SPACING_MD, SPACING_MD, SPACING_MD),
        border_radius=BORDER_RADIUS_LG,
        bgcolor=ft.Colors.SURFACE_CONTAINER_HIGHEST,
        ink=True,
        animate=ft.Animation(ANIMATION_FAST, ft.AnimationCurve.EASE_OUT),
        on_click=lambda _: _show_result_sheet(page, r, "text"),
    )


def _image_card(r: SearchResult, i: int, page: ft.Page) -> ft.Container:
    return ft.Container(
        content=ft.Column(
            [
                ft.Container(
                    content=ft.Image(
                        src=r.thumbnail or r.image_url or "",
                        fit=ft.BoxFit.COVER,
                        border_radius=BORDER_RADIUS_MD,
                        error_content=ft.Container(
                            content=ft.Icon(
                                ft.Icons.BROKEN_IMAGE_ROUNDED,
                                size=ICON_LG,
                                color=ft.Colors.ON_SURFACE_VARIANT,
                            ),
                            height=140,
                            alignment=ft.alignment.Alignment(0, 0),
                            bgcolor=ft.Colors.SURFACE_CONTAINER,
                            border_radius=BORDER_RADIUS_MD,
                        ),
                    ),
                    height=140,
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
        width=170,
        padding=ft.Padding(SPACING_SM, SPACING_SM, SPACING_SM, SPACING_SM),
        border_radius=BORDER_RADIUS_LG,
        bgcolor=ft.Colors.SURFACE_CONTAINER_HIGHEST,
        ink=True,
        animate=ft.Animation(ANIMATION_FAST, ft.AnimationCurve.EASE_OUT),
        on_click=lambda _: _show_result_sheet(page, r, "images"),
    )


def _video_card(r: SearchResult, i: int, page: ft.Page) -> ft.Container:
    return ft.Container(
        content=ft.Row(
            [
                ft.Container(
                    content=ft.Stack(
                        [
                            ft.Image(
                                src=r.thumbnail or "",
                                fit=ft.BoxFit.COVER,
                                width=140,
                                height=80,
                                border_radius=BORDER_RADIUS_MD,
                                error_content=ft.Container(
                                    ft.Icon(
                                        ft.Icons.VIDEO_LIBRARY_ROUNDED,
                                        size=ICON_LG,
                                        color=ft.Colors.ON_SURFACE_VARIANT,
                                    ),
                                    width=140,
                                    height=80,
                                    alignment=ft.alignment.Alignment(0, 0),
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
                                padding=ft.Padding(
                                    SPACING_XS, SPACING_XS, SPACING_XS, SPACING_XS
                                ),
                                bgcolor=ft.Colors.BLACK54,
                                border_radius=BORDER_RADIUS_MD,
                                right=SPACING_XS,
                                bottom=SPACING_XS,
                            ),
                        ]
                    ),
                ),
                ft.Column(
                    [
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
                            [
                                ft.Icon(
                                    ft.Icons.VISIBILITY_ROUNDED,
                                    size=12,
                                    color=ft.Colors.ON_SURFACE_VARIANT,
                                ),
                                ft.Text(
                                    f"{r.views:,}" if r.views else "",
                                    size=FONT_XS,
                                    color=ft.Colors.ON_SURFACE_VARIANT,
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
        padding=ft.Padding(SPACING_MD, SPACING_MD, SPACING_MD, SPACING_MD),
        border_radius=BORDER_RADIUS_LG,
        bgcolor=ft.Colors.SURFACE_CONTAINER_HIGHEST,
        ink=True,
        animate=ft.Animation(ANIMATION_FAST, ft.AnimationCurve.EASE_OUT),
        on_click=lambda _: _show_result_sheet(page, r, "videos"),
    )


def _news_card(r: SearchResult, i: int, page: ft.Page) -> ft.Container:
    return ft.Container(
        content=ft.Row(
            [
                ft.Container(
                    content=ft.Image(
                        src=r.thumbnail or "",
                        fit=ft.BoxFit.COVER,
                        width=72,
                        height=72,
                        border_radius=BORDER_RADIUS_MD,
                        error_content=ft.Container(
                            ft.Icon(
                                ft.Icons.ARTICLE_ROUNDED,
                                size=ICON_LG,
                                color=ft.Colors.ON_SURFACE_VARIANT,
                            ),
                            width=72,
                            height=72,
                            alignment=ft.alignment.Alignment(0, 0),
                            bgcolor=ft.Colors.SURFACE_CONTAINER,
                            border_radius=BORDER_RADIUS_MD,
                        ),
                    ),
                    border_radius=BORDER_RADIUS_MD,
                    clip_behavior=ft.ClipBehavior.ANTI_ALIAS,
                ),
                ft.Column(
                    [
                        ft.Text(
                            r.title,
                            size=FONT_MD,
                            weight=ft.FontWeight.W_600,
                            max_lines=2,
                        ),
                        ft.Text(r.snippet, size=FONT_SM, max_lines=3),
                        ft.Row(
                            [
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
        padding=ft.Padding(SPACING_MD, SPACING_MD, SPACING_MD, SPACING_MD),
        border_radius=BORDER_RADIUS_LG,
        bgcolor=ft.Colors.SURFACE_CONTAINER_HIGHEST,
        ink=True,
        animate=ft.Animation(ANIMATION_FAST, ft.AnimationCurve.EASE_OUT),
        on_click=lambda _: _show_result_sheet(page, r, "news"),
    )


def _books_card(r: SearchResult, i: int, page: ft.Page) -> ft.Container:
    return ft.Container(
        content=ft.Column(
            [
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
        padding=ft.Padding(SPACING_MD, SPACING_MD, SPACING_MD, SPACING_MD),
        border_radius=BORDER_RADIUS_LG,
        bgcolor=ft.Colors.SURFACE_CONTAINER_HIGHEST,
        ink=True,
        animate=ft.Animation(ANIMATION_FAST, ft.AnimationCurve.EASE_OUT),
        on_click=lambda _: _show_result_sheet(page, r, "books"),
    )


def _extract_card(result: dict | None, page: ft.Page) -> ft.Container:
    if not result:
        return ft.Container(
            content=ft.Column(
                [
                    ft.Icon(
                        ft.Icons.ERROR_OUTLINE_ROUNDED,
                        size=ICON_LG,
                        color=ft.Colors.ON_SURFACE_VARIANT,
                    ),
                    ft.Text(
                        "No content extracted",
                        size=FONT_MD,
                        color=ft.Colors.ON_SURFACE_VARIANT,
                        text_align=ft.TextAlign.CENTER,
                    ),
                ],
                horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                spacing=SPACING_SM,
            ),
            padding=ft.Padding(SPACING_XL, SPACING_XL, SPACING_XL, SPACING_XL),
            expand=True,
            alignment=ft.alignment.Alignment(0, 0),
        )

    content = result.get("content", "")
    url = result.get("url", "")

    if isinstance(content, bytes):
        display = ft.Text(
            f"[Binary content \u2014 {len(content)} bytes]",
            size=FONT_SM,
            color=ft.Colors.ON_SURFACE_VARIANT,
        )
    else:
        display = ft.Text(str(content), size=FONT_SM, selectable=True, max_lines=200)

    return ft.Container(
        content=ft.Column(
            [
                ft.Row(
                    [
                        ft.Icon(
                            ft.Icons.LINK_ROUNDED, size=ICON_SM, color=AppColors.PRIMARY
                        ),
                        ft.Text(
                            "Source:", size=FONT_XS, color=ft.Colors.ON_SURFACE_VARIANT
                        ),
                        ft.Text(
                            url,
                            size=FONT_SM,
                            color=AppColors.PRIMARY,
                            selectable=True,
                            max_lines=2,
                            expand=True,
                        ),
                    ],
                    spacing=6,
                ),
                ft.Divider(
                    height=1, color=ft.Colors.with_opacity(0.1, ft.Colors.ON_SURFACE)
                ),
                display,
            ],
            spacing=SPACING_SM,
            scroll=ft.ScrollMode.AUTO,
        ),
        padding=ft.Padding(SPACING_MD, SPACING_MD, SPACING_MD, SPACING_MD),
        border_radius=BORDER_RADIUS_LG,
        bgcolor=ft.Colors.SURFACE_CONTAINER_HIGHEST,
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

    # ── Header ──
    header = ft.Container(
        content=ft.Row(
            [
                ft.IconButton(
                    icon=ft.Icons.ARROW_BACK_ROUNDED,
                    icon_size=ICON_MD,
                    on_click=lambda _: on_navigate("/home"),
                ),
                ft.Column(
                    [
                        ft.Text(
                            query or "Result",
                            size=FONT_LG,
                            weight=ft.FontWeight.W_600,
                            max_lines=1,
                        ),
                        ft.Text(
                            f"{search_type.capitalize()} \u00b7 {len(results)} results"
                            if not is_running
                            else "Searching...",
                            size=FONT_XS,
                            color=ft.Colors.ON_SURFACE_VARIANT,
                        ),
                    ],
                    spacing=2,
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
        padding=ft.Padding(SPACING_MD, SPACING_SM, SPACING_MD, SPACING_SM),
        border=ft.Border(
            top=ft.BorderSide(0, ft.Colors.TRANSPARENT),
            right=ft.BorderSide(0, ft.Colors.TRANSPARENT),
            bottom=ft.BorderSide(1, ft.Colors.with_opacity(0.1, ft.Colors.ON_SURFACE)),
            left=ft.BorderSide(0, ft.Colors.TRANSPARENT),
        ),
    )

    # ── Loading ──
    loading = ft.Container(
        content=ft.Column(
            [
                ft.ProgressBar(
                    color=AppColors.PRIMARY,
                    bgcolor=ft.Colors.with_opacity(0.1, AppColors.PRIMARY),
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
        padding=ft.Padding(SPACING_LG, SPACING_LG, SPACING_LG, SPACING_LG),
        visible=is_running,
    )

    # ── Error ──
    error_banner = ft.Container(
        content=ft.Column(
            [
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
                ft.Container(height=8),
                ft.FilledButton(
                    content=ft.Row(
                        [
                            ft.Icon(
                                ft.Icons.REFRESH_ROUNDED,
                                size=ICON_SM,
                                color=ft.Colors.WHITE,
                            ),
                            ft.Text(
                                "Try Again",
                                size=FONT_SM,
                                weight=ft.FontWeight.W_600,
                                color=ft.Colors.WHITE,
                            ),
                        ],
                        spacing=6,
                        tight=True,
                    ),
                    on_click=lambda _: on_restart(query),
                    style=ft.ButtonStyle(
                        shape=ft.RoundedRectangleBorder(radius=BORDER_RADIUS_MD)
                    ),
                ),
            ],
            spacing=SPACING_MD,
            horizontal_alignment=ft.CrossAxisAlignment.CENTER,
        ),
        padding=ft.Padding(SPACING_XL, SPACING_XL, SPACING_XL, SPACING_XL),
        visible=bool(error) and not is_running,
    )

    # ── Results ──
    if search_type == "extract":
        results_content = _extract_card(extract_result, page)
    elif results:
        builder = CARD_BUILDERS.get(search_type, _text_card)
        cards = [builder(r, i, page) for i, r in enumerate(results)]
        results_content = ft.Column(
            [
                ft.Row(
                    [
                        ft.Icon(
                            ft.Icons.SEARCH_ROUNDED
                            if search_type == "text"
                            else ft.Icons.IMAGE_ROUNDED,
                            size=ICON_SM,
                            color=ft.Colors.ON_SURFACE_VARIANT,
                        ),
                        ft.Text(
                            f"{len(results)} results",
                            size=FONT_SM,
                            color=ft.Colors.ON_SURFACE_VARIANT,
                            weight=ft.FontWeight.W_500,
                        ),
                    ],
                    spacing=6,
                ),
                *cards,
            ],
            spacing=SPACING_SM,
            scroll=ft.ScrollMode.AUTO,
            expand=True,
        )
    else:
        results_content = ft.Container(
            content=ft.Column(
                [
                    ft.Icon(
                        ft.Icons.SEARCH_OFF_ROUNDED,
                        size=ICON_LG,
                        color=ft.Colors.ON_SURFACE_VARIANT,
                    ),
                    ft.Text(
                        "No results found" if not is_running else "",
                        size=FONT_MD,
                        color=ft.Colors.ON_SURFACE_VARIANT,
                        text_align=ft.TextAlign.CENTER,
                    ),
                ],
                horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                spacing=SPACING_SM,
            ),
            padding=ft.Padding(SPACING_XL, SPACING_XL, SPACING_XL, SPACING_XL),
            expand=True,
            alignment=ft.alignment.Alignment(0, 0),
        )

    results_container = ft.Container(
        content=results_content,
        padding=ft.Padding(SPACING_MD, SPACING_SM, SPACING_MD, SPACING_SM),
        expand=True,
    )

    return ft.View(
        route="/results",
        controls=[
            ft.SafeArea(
                content=ft.Column(
                    [header, loading, error_banner, results_container],
                    spacing=0,
                    expand=True,
                )
            )
        ],
        padding=0,
        spacing=0,
        bgcolor=ft.Colors.SURFACE,
    )
