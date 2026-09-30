from __future__ import annotations

import flet as ft

from components.results.cards_media import (
    _books_card,
    _image_card,
    _news_card,
    _video_card,
)
from components.results.detail_sheet import (
    _result_actions_sheet,
    _show_result_sheet,
)
from components.results.downloader import (
    _save_bytes_content,
    _save_text_content,
)
from core import theme, tokens
from core.constants import EXTRACT_FORMATS, EXTRACT_FORMAT_SHORT
from core.snack import show_snack
from core.state import SearchResult, state
from core.styles import build_banner_ad
from core.theme import AppColors
from core.utils import FetchNav, display_url, resolve_url, set_extract_format

# Tap pacing for extract-card link opens: a double-tap must not stack
# two Reader views.
_link_nav = FetchNav()


def _open_link_in_reader(page: ft.Page, base_url: str, link: str) -> None:
    """Open a tapped content link in the full-screen Reader.

    Direct fetches already show their content full-width on the results
    screen; a subsequent page must continue in the same full-screen
    surface (the Reader), not drop a preview modal over the results.
    """
    resolved = resolve_url(base_url, link)
    if resolved is None or not _link_nav.allow_tap():
        return
    ctrl = getattr(page, "_ddgs_controller", None)
    if ctrl:
        ctrl.open_content_reader(resolved)


def _text_card(r: SearchResult, i: int, page: ft.Page) -> ft.GestureDetector:
    # Long-press (mobile) / right-click (desktop) opens the quick actions
    # sheet (plan C3); primary taps keep opening the detail sheet.
    return ft.GestureDetector(
        on_secondary_tap=lambda e: _result_actions_sheet(page, r),
        content=ft.Container(
            on_long_press=lambda e: _result_actions_sheet(page, r),
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
                        display_url(r.url),
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
        ),
    )


# Compact segment labels for the extract formats live in
# core.constants.EXTRACT_FORMAT_SHORT, shared with the preview sheet and
# the reader so every switcher reads the same words.


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
            f"[Binary content: {len(content)} bytes]",
            size=tokens.FONT_SM,
            color=ft.Colors.ON_SURFACE_VARIANT,
            font_family="Outfit",
        )
    else:
        display = ft.Markdown(
            value=str(content),
            selectable=True,
            extension_set="gitHubWeb",
            code_theme=(
                ft.MarkdownCodeTheme.DRACULA
                if theme.is_dark_mode(page)
                else ft.MarkdownCodeTheme.DEFAULT
            ),
            # Links continue in the full-screen Reader - direct fetches
            # are already a full-screen surface, so a second page must
            # not open a modal over the results (owner's call).
            on_tap_link=lambda e: _open_link_in_reader(page, url, e.data),
        )

    async def _change_format(new_fmt: str):
        # One writer for observable state + persistence, shared with the
        # preview sheet and the reader.
        await set_extract_format(page, new_fmt)
        # Re-extract in place: the same card re-renders with the new
        # format. This used to pop the preview modal over the results,
        # which read as "the switch opens something else" instead of
        # "the content changed".
        from services.search_service import SearchService

        result, err = await SearchService().extract_url(url, fmt=new_fmt)
        if result:
            state.extract_result = result
        else:
            show_snack(
                page,
                ft.SnackBar(
                    ft.Text(f"Could not re-extract ({err or 'Unavailable'})")
                ),
            )

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
            # Plan C4: all five formats visible at once beats a dropdown
            # that hid four of them behind a tap.
            ft.SegmentedButton(
                segments=[
                    ft.Segment(
                        value=f["key"],
                        label=ft.Text(
                            EXTRACT_FORMAT_SHORT.get(f["key"], f["label"]),
                            size=tokens.FONT_XS,
                            font_family="Outfit",
                            tooltip=f["label"],
                        ),
                    )
                    for f in EXTRACT_FORMATS
                ],
                selected=[state.extract_format],
                allow_multiple_selection=False,
                on_change=lambda e: page.run_task(
                    _change_format, (e.control.selected or [state.extract_format])[0]
                ),
            ),
        ],
        spacing=6,
        vertical_alignment=ft.CrossAxisAlignment.CENTER,
    )

    def _open_reader():
        from flet import context as flet_context

        page = flet_context.page
        ctrl = getattr(page, "_ddgs_controller", None)
        if ctrl:
            ctrl.open_content_reader(url, str(content) if not is_bytes else None)

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
                            icon=ft.Icons.OPEN_IN_NEW_ROUNDED,
                            icon_size=tokens.ICON_SM,
                            tooltip="Open in full reader",
                            on_click=lambda e: _open_reader(),
                        ),
                        ft.IconButton(
                            icon=ft.Icons.OPEN_IN_BROWSER_ROUNDED,
                            icon_size=tokens.ICON_SM,
                            tooltip="Open in browser",
                            action=ft.OpenUrl(url),
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
