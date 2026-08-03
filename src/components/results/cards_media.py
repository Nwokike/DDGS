from __future__ import annotations

import flet as ft

from components.results.detail_sheet import _show_result_sheet
from core import theme, tokens
from core.state import SearchResult
from core.theme import AppColors


def _image_card(r: SearchResult, i: int, page: ft.Page) -> ft.Container:
    is_dark = theme.is_dark_mode(page)
    return ft.Container(
        content=ft.Column(
            [
                ft.Container(
                    content=ft.Image(
                        src=r.thumbnail or r.image_url or "",
                        fit=ft.BoxFit.COVER,
                        border_radius=tokens.RADIUS_MD,
                        error_content=ft.Container(
                            content=ft.Icon(
                                ft.Icons.BROKEN_IMAGE_ROUNDED,
                                size=tokens.ICON_LG,
                                color=ft.Colors.ON_SURFACE_VARIANT,
                            ),
                            height=120,
                            alignment=ft.Alignment.CENTER,
                            bgcolor=ft.Colors.with_opacity(0.04, ft.Colors.ON_SURFACE),
                            border_radius=tokens.RADIUS_MD,
                        ),
                    ),
                    height=120,
                    border_radius=tokens.RADIUS_MD,
                    clip_behavior=ft.ClipBehavior.ANTI_ALIAS,
                ),
                ft.Container(height=4),
                ft.Text(
                    r.title,
                    size=tokens.FONT_XS,
                    max_lines=2,
                    weight=ft.FontWeight.W_500,
                ),
                ft.Text(
                    f"{r.width}x{r.height}" if r.width else "",
                    size=10,
                    color=AppColors.PRIMARY if is_dark else AppColors.PRIMARY_DARK,
                    weight=ft.FontWeight.BOLD,
                ),
            ],
            spacing=tokens.SPACE_XS,
            tight=True,
        ),
        width=165,
        padding=10,
        border_radius=tokens.RADIUS_LG,
        bgcolor=theme.adaptive_glass_bg(page),
        border=ft.Border.all(1, theme.adaptive_glass_border(page)),
        ink=True,
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
                                width=130,
                                height=76,
                                border_radius=tokens.RADIUS_MD,
                                error_content=ft.Container(
                                    ft.Icon(
                                        ft.Icons.VIDEO_LIBRARY_ROUNDED,
                                        size=tokens.ICON_LG,
                                        color=ft.Colors.ON_SURFACE_VARIANT,
                                    ),
                                    width=130,
                                    height=76,
                                    alignment=ft.Alignment.CENTER,
                                    bgcolor=ft.Colors.with_opacity(
                                        0.04, ft.Colors.ON_SURFACE
                                    ),
                                    border_radius=tokens.RADIUS_MD,
                                ),
                            ),
                            ft.Container(
                                content=ft.Text(
                                    r.duration or "",
                                    size=10,
                                    color=ft.Colors.WHITE,
                                    weight=ft.FontWeight.BOLD,
                                ),
                                padding=ft.Padding(6, 3, 6, 3),
                                bgcolor=ft.Colors.BLACK_87,
                                border_radius=tokens.RADIUS_MD,
                                right=6,
                                bottom=6,
                            ),
                        ]
                    ),
                    border_radius=tokens.RADIUS_MD,
                ),
                ft.Column(
                    [
                        ft.Text(
                            r.title,
                            size=tokens.FONT_SM,
                            weight=ft.FontWeight.W_600,
                            max_lines=2,
                            font_family="Outfit",
                        ),
                        ft.Text(
                            r.publisher or r.source or "",
                            size=tokens.FONT_XS,
                            color=ft.Colors.ON_SURFACE_VARIANT,
                        ),
                        ft.Row(
                            [
                                ft.Icon(
                                    ft.Icons.VISIBILITY_ROUNDED,
                                    size=11,
                                    color=ft.Colors.ON_SURFACE_VARIANT,
                                ),
                                ft.Text(
                                    f"{r.views:,} views" if r.views else "Video result",
                                    size=tokens.FONT_XS,
                                    color=ft.Colors.ON_SURFACE_VARIANT,
                                ),
                            ],
                            spacing=4,
                        ),
                    ],
                    spacing=tokens.SPACE_XS,
                    expand=True,
                ),
            ],
            spacing=tokens.SPACE_MD,
        ),
        padding=12,
        border_radius=tokens.RADIUS_LG,
        bgcolor=theme.adaptive_glass_bg(page),
        border=ft.Border.all(1, theme.adaptive_glass_border(page)),
        ink=True,
        on_click=lambda _: _show_result_sheet(page, r, "videos"),
    )


def _news_card(r: SearchResult, i: int, page: ft.Page) -> ft.Container:
    is_dark = theme.is_dark_mode(page)
    return ft.Container(
        content=ft.Row(
            [
                ft.Column(
                    [
                        ft.Text(
                            r.title,
                            size=tokens.FONT_SM,
                            weight=ft.FontWeight.W_600,
                            max_lines=2,
                            font_family="Outfit",
                            color=AppColors.PRIMARY,
                        ),
                        ft.Text(
                            r.snippet,
                            size=tokens.FONT_XS,
                            color=ft.Colors.ON_SURFACE,
                            max_lines=2,
                            style=ft.TextStyle(height=1.4),
                        ),
                        ft.Row(
                            [
                                ft.Text(
                                    r.source or "News Source",
                                    size=tokens.FONT_XS,
                                    weight=ft.FontWeight.BOLD,
                                    color=AppColors.PRIMARY_LIGHT
                                    if is_dark
                                    else AppColors.PRIMARY_DARK,
                                ),
                                ft.Text(
                                    r.date or "",
                                    size=tokens.FONT_XS,
                                    color=ft.Colors.ON_SURFACE_VARIANT,
                                ),
                            ],
                            spacing=tokens.SPACE_SM,
                        ),
                    ],
                    spacing=tokens.SPACE_XS,
                    expand=True,
                ),
                ft.Container(
                    content=ft.Image(
                        src=r.thumbnail or "",
                        fit=ft.BoxFit.COVER,
                        width=64,
                        height=64,
                        border_radius=tokens.RADIUS_MD,
                        error_content=ft.Container(
                            ft.Icon(
                                ft.Icons.ARTICLE_ROUNDED,
                                size=tokens.ICON_MD,
                                color=ft.Colors.ON_SURFACE_VARIANT,
                            ),
                            width=64,
                            height=64,
                            alignment=ft.Alignment.CENTER,
                            bgcolor=ft.Colors.with_opacity(0.04, ft.Colors.ON_SURFACE),
                            border_radius=tokens.RADIUS_MD,
                        ),
                    ),
                    border_radius=tokens.RADIUS_MD,
                    clip_behavior=ft.ClipBehavior.ANTI_ALIAS,
                )
                if r.thumbnail
                else ft.Container(),
            ],
            spacing=tokens.SPACE_MD,
        ),
        padding=12,
        border_radius=tokens.RADIUS_LG,
        bgcolor=theme.adaptive_glass_bg(page),
        border=ft.Border.all(1, theme.adaptive_glass_border(page)),
        ink=True,
        on_click=lambda _: _show_result_sheet(page, r, "news"),
    )


def _books_card(r: SearchResult, i: int, page: ft.Page) -> ft.Container:
    return ft.Container(
        content=ft.Column(
            [
                ft.Text(
                    r.title,
                    size=tokens.FONT_MD,
                    weight=ft.FontWeight.W_600,
                    color=AppColors.PRIMARY,
                    max_lines=2,
                    font_family="Outfit",
                ),
                ft.Text(
                    r.url,
                    size=tokens.FONT_XS,
                    color=ft.Colors.ON_SURFACE_VARIANT,
                    max_lines=1,
                    overflow=ft.TextOverflow.ELLIPSIS,
                ),
                ft.Text(
                    r.snippet,
                    size=tokens.FONT_SM,
                    color=ft.Colors.ON_SURFACE,
                    max_lines=4,
                    style=ft.TextStyle(height=1.4),
                ),
            ],
            spacing=tokens.SPACE_XS,
            tight=True,
        ),
        padding=16,
        border_radius=tokens.RADIUS_LG,
        bgcolor=theme.adaptive_glass_bg(page),
        border=ft.Border.all(1, theme.adaptive_glass_border(page)),
        ink=True,
        on_click=lambda _: _show_result_sheet(page, r, "books"),
    )
