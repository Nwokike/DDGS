from __future__ import annotations

import flet as ft

from components.results.cards_media import (
    _books_card,
    _image_card,
    _news_card,
    _video_card,
)
from components.results.content_fetcher import _fetch_and_show, _on_link_tap
from components.results.detail_sheet import _show_result_sheet
from components.results.downloader import (
    _save_bytes_content,
    _save_text_content,
    launch_url,
)
from core import theme, tokens
from core.constants import EXTRACT_FORMATS
from core.state import SearchResult, state
from core.styles import build_banner_ad
from core.theme import AppColors
from services.storage_service import StorageService


def _text_card(r: SearchResult, i: int, page: ft.Page) -> ft.Container:
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
                    max_lines=3,
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
        on_click=lambda _: _show_result_sheet(page, r, "text"),
    )


def _extract_card(result: dict | None, page: ft.Page) -> ft.Container:
    if not result:
        return ft.Container(
            content=ft.Column(
                [
                    ft.Icon(
                        ft.Icons.ERROR_OUTLINE_ROUNDED,
                        size=tokens.ICON_LG,
                        color=ft.Colors.ON_SURFACE_VARIANT,
                    ),
                    ft.Text(
                        "No content extracted.",
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
            alignment=ft.Alignment.CENTER,
        )

    content = result.get("content", "")
    url = result.get("url", "")
    is_bytes = isinstance(content, bytes)

    async def save_extract(e=None):
        if is_bytes:
            await _save_bytes_content(page, content, "extracted_file.bin")
        else:
            await _save_text_content(page, str(content), "extracted_page.md")

    if is_bytes:
        display = ft.Text(
            f"[Binary content — {len(content)} bytes]",
            size=tokens.FONT_SM,
            color=ft.Colors.ON_SURFACE_VARIANT,
            font_family="Outfit",
        )
    else:
        display = ft.Markdown(
            value=str(content),
            selectable=True,
            extension_set="gitHubWeb",
            on_tap_link=lambda e: _on_link_tap(page, e.data, url),
        )

    async def _change_format(new_fmt: str):
        state.extract_format = new_fmt
        try:
            storage_svc = StorageService()
            await storage_svc.set_extract_format(new_fmt)
        except (
            ValueError,
            TypeError,
            OSError,
            RuntimeError,
            ConnectionError,
            ImportError,
        ) as _ex:
            __import__("logging").getLogger("app").debug(f"Ignored: {_ex}")
        await _fetch_and_show(page, url)

    format_row = ft.Row(
        [
            ft.Icon(
                ft.Icons.CODE_ROUNDED,
                size=14,
                color=ft.Colors.ON_SURFACE_VARIANT,
            ),
            ft.Text(
                "Format:",
                size=tokens.FONT_XS,
                color=ft.Colors.ON_SURFACE_VARIANT,
                font_family="Outfit",
                weight=ft.FontWeight.W_500,
            ),
            ft.Dropdown(
                value=state.extract_format,
                options=[
                    ft.dropdown.Option(f["key"], f["label"]) for f in EXTRACT_FORMATS
                ],
                on_select=lambda e: page.run_task(_change_format, e.control.value),
                filled=True,
                text_size=tokens.FONT_XS,
                content_padding=ft.Padding(left=10, top=4, right=10, bottom=4),
                border_radius=tokens.RADIUS_MD,
                width=150,
                height=36,
            ),
        ],
        spacing=6,
        vertical_alignment=ft.CrossAxisAlignment.CENTER,
    )

    return ft.Container(
        content=ft.Column(
            [
                ft.Row(
                    [
                        ft.Icon(
                            ft.Icons.LINK_ROUNDED,
                            size=tokens.ICON_SM,
                            color=AppColors.PRIMARY,
                        ),
                        ft.Text(
                            "Source URL:",
                            size=tokens.FONT_XS,
                            color=ft.Colors.ON_SURFACE_VARIANT,
                            font_family="Outfit",
                        ),
                        ft.Text(
                            url,
                            size=tokens.FONT_SM,
                            color=AppColors.PRIMARY,
                            selectable=True,
                            max_lines=2,
                            expand=True,
                            font_family="Outfit",
                        ),
                        ft.IconButton(
                            icon=ft.Icons.OPEN_IN_BROWSER_ROUNDED,
                            icon_size=tokens.ICON_SM,
                            tooltip="Open in browser",
                            on_click=lambda e: page.run_task(launch_url, url),
                        ),
                        ft.IconButton(
                            icon=ft.Icons.SAVE_ALT_ROUNDED,
                            icon_size=tokens.ICON_SM,
                            tooltip="Save content to file",
                            on_click=lambda e: page.run_task(save_extract),
                        ),
                    ],
                    spacing=6,
                ),
                format_row,
                ft.Divider(
                    height=1, color=ft.Colors.with_opacity(0.08, ft.Colors.ON_SURFACE)
                ),
                display,
                build_banner_ad(page),
            ],
            spacing=tokens.SPACE_SM,
            scroll=ft.ScrollMode.AUTO,
        ),
        padding=16,
        border_radius=tokens.RADIUS_LG,
        bgcolor=theme.adaptive_glass_bg(page),
        border=ft.Border.all(1, theme.adaptive_glass_border(page)),
        expand=True,
    )


CARD_BUILDERS = {
    "text": _text_card,
    "images": _image_card,
    "videos": _video_card,
    "news": _news_card,
    "books": _books_card,
}
