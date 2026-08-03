from __future__ import annotations

import flet as ft

from components.results.content_fetcher import _fetch_and_show, _url_history
from components.results.downloader import _download_media, launch_url
from core import theme, tokens
from core.state import SearchResult
from core.theme import AppColors


def _show_result_sheet(page: ft.Page, r: SearchResult, search_type: str):
    """Show a premium bottom sheet with result info, launch link, and raw extraction triggers."""
    is_dark = theme.is_dark_mode(page)
    bg_color = AppColors.DARK_SURFACE if is_dark else AppColors.LIGHT_SURFACE
    is_media = search_type in ("images", "videos")
    action_text = (
        "Download Image"
        if search_type == "images"
        else ("Download Video" if search_type == "videos" else "View Page Content")
    )

    if is_media:

        def action_callback(_):
            page.run_task(_download_media, page, r, search_type)

    else:

        def action_callback(_):
            _url_history.clear()
            page.run_task(_fetch_and_show, page, r.url, pop_current=True)

    def _close_details(_):
        try:
            page.pop_dialog()
        except (
            ValueError,
            TypeError,
            OSError,
            RuntimeError,
            ConnectionError,
            ImportError,
        ) as _ex:
            __import__("logging").getLogger("app").debug(f"Ignored: {_ex}")

    def _open_in_browser(_):
        try:
            page.pop_dialog()
        except (
            ValueError,
            TypeError,
            OSError,
            RuntimeError,
            ConnectionError,
            ImportError,
        ) as _ex:
            __import__("logging").getLogger("app").debug(f"Ignored: {_ex}")
        page.run_task(launch_url, r.url)

    sheet_content = ft.Container(
        content=ft.Column(
            [
                ft.Row(
                    [
                        ft.Icon(
                            ft.Icons.ARTICLE_ROUNDED
                            if search_type != "extract"
                            else ft.Icons.DOWNLOAD_ROUNDED,
                            size=tokens.ICON_MD,
                            color=AppColors.PRIMARY,
                        ),
                        ft.Text(
                            "Result Details",
                            size=tokens.FONT_LG,
                            weight=ft.FontWeight.BOLD,
                            font_family="Outfit",
                            expand=True,
                        ),
                        ft.IconButton(
                            icon=ft.Icons.CLOSE_ROUNDED,
                            icon_size=tokens.ICON_MD,
                            on_click=_close_details,
                        ),
                    ],
                    spacing=tokens.SPACE_SM,
                ),
                ft.Divider(
                    height=1, color=ft.Colors.with_opacity(0.08, ft.Colors.ON_SURFACE)
                ),
                ft.Container(height=8),
                ft.Text(
                    r.title,
                    size=tokens.FONT_MD,
                    weight=ft.FontWeight.W_600,
                    max_lines=3,
                    font_family="Outfit",
                ),
                ft.Text(
                    r.url,
                    size=tokens.FONT_XS,
                    color=AppColors.PRIMARY,
                    selectable=True,
                    max_lines=2,
                ),
                ft.Row(
                    [
                        ft.FilledButton(
                            content=ft.Row(
                                [
                                    ft.Icon(
                                        ft.Icons.DOWNLOAD_ROUNDED,
                                        size=tokens.ICON_SM,
                                        color=ft.Colors.WHITE,
                                    ),
                                    ft.Text(
                                        action_text,
                                        size=tokens.FONT_SM,
                                        weight=ft.FontWeight.W_600,
                                        color=ft.Colors.WHITE,
                                        font_family="Outfit",
                                    ),
                                ],
                                spacing=6,
                                tight=True,
                            ),
                            on_click=action_callback,
                            style=ft.ButtonStyle(
                                bgcolor=AppColors.PRIMARY,
                                shape=ft.RoundedRectangleBorder(
                                    radius=tokens.RADIUS_MD
                                ),
                                padding=ft.Padding(16, 12, 16, 12),
                            ),
                            expand=True,
                        ),
                    ],
                    spacing=tokens.SPACE_SM,
                ),
                ft.Container(height=8),
                ft.OutlinedButton(
                    content=ft.Row(
                        [
                            ft.Icon(
                                ft.Icons.OPEN_IN_BROWSER_ROUNDED,
                                size=tokens.ICON_SM,
                            ),
                            ft.Text(
                                "Open in Browser",
                                size=tokens.FONT_SM,
                                weight=ft.FontWeight.W_600,
                                font_family="Outfit",
                            ),
                        ],
                        spacing=6,
                        tight=True,
                    ),
                    on_click=_open_in_browser,
                    style=ft.ButtonStyle(
                        shape=ft.RoundedRectangleBorder(radius=tokens.RADIUS_MD),
                        side=ft.BorderSide(1, AppColors.PRIMARY),
                        padding=ft.Padding(16, 12, 16, 12),
                    ),
                    expand=True,
                ),
            ],
            spacing=tokens.SPACE_SM,
            scroll=ft.ScrollMode.AUTO,
            tight=True,
        ),
        padding=ft.Padding(20, 16, 20, 20),
        bgcolor=bg_color,
        border_radius=ft.BorderRadius(tokens.RADIUS_LG, tokens.RADIUS_LG, 0, 0),
    )

    sheet = ft.BottomSheet(
        content=sheet_content,
        open=True,
        elevation=8,
    )
    page.show_dialog(sheet)
