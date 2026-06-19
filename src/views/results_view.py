from __future__ import annotations

from typing import Callable

import flet as ft

from core import theme, tokens
from core.constants import EXTRACT_FORMATS
from core.state import SearchProgress, SearchResult, state
from core.theme import AppColors
from services.search_service import SearchService
from services.storage_service import StorageService

LOG_TAG = "ResultsView"

_search_service = SearchService()


async def launch_url(url: str, page: ft.Page | None = None):
    """Open a URL in the system browser. Works on mobile + desktop."""
    if not url:
        return
    try:
        await ft.UrlLauncher().launch_url(url)
    except Exception:
        import webbrowser

        webbrowser.open(url)


def _on_link_tap(page: ft.Page, url: str):
    """Show a choice dialog when a link is tapped in fetched content:
    Fetch Page (primary) or Open in Browser."""

    def _fetch(_):
        page.pop_dialog()
        page.run_task(_fetch_and_show, page, url)

    def _open_browser(_):
        page.pop_dialog()
        page.run_task(launch_url, url, page)

    dlg = ft.AlertDialog(
        title=ft.Row(
            [
                ft.Icon(
                    ft.Icons.LINK_ROUNDED,
                    size=20,
                    color=AppColors.PRIMARY,
                ),
                ft.Text(
                    "Link Tapped",
                    size=tokens.FONT_MD,
                    weight=ft.FontWeight.BOLD,
                    font_family="Outfit",
                ),
            ],
            spacing=8,
        ),
        content=ft.Container(
            content=ft.Column(
                [
                    ft.Text(
                        url,
                        size=tokens.FONT_XS,
                        color=AppColors.PRIMARY,
                        max_lines=3,
                        overflow="ellipsis",
                        selectable=True,
                        font_family="Outfit",
                    ),
                    ft.Container(height=tokens.SPACE_SM),
                    ft.FilledButton(
                        content=ft.Row(
                            [
                                ft.Icon(
                                    ft.Icons.LANGUAGE_ROUNDED,
                                    size=16,
                                    color=ft.Colors.WHITE,
                                ),
                                ft.Text(
                                    "Fetch Page Content",
                                    size=tokens.FONT_SM,
                                    weight=ft.FontWeight.W_600,
                                    color=ft.Colors.WHITE,
                                    font_family="Outfit",
                                ),
                            ],
                            spacing=8,
                            tight=True,
                        ),
                        on_click=_fetch,
                        style=ft.ButtonStyle(
                            bgcolor=AppColors.PRIMARY,
                            shape=ft.RoundedRectangleBorder(radius=tokens.RADIUS_PILL),
                            padding=ft.Padding(20, 12, 20, 12),
                        ),
                    ),
                    ft.OutlinedButton(
                        content=ft.Row(
                            [
                                ft.Icon(
                                    ft.Icons.OPEN_IN_BROWSER_ROUNDED,
                                    size=16,
                                ),
                                ft.Text(
                                    "Open in Browser",
                                    size=tokens.FONT_SM,
                                    weight=ft.FontWeight.W_600,
                                    font_family="Outfit",
                                ),
                            ],
                            spacing=8,
                            tight=True,
                        ),
                        on_click=_open_browser,
                        style=ft.ButtonStyle(
                            shape=ft.RoundedRectangleBorder(radius=tokens.RADIUS_PILL),
                            padding=ft.Padding(20, 12, 20, 12),
                        ),
                    ),
                ],
                spacing=tokens.SPACE_SM,
                horizontal_alignment=ft.CrossAxisAlignment.STRETCH,
            ),
            width=300,
        ),
        actions=[
            ft.TextButton("Cancel", on_click=lambda _: page.pop_dialog()),
        ],
        actions_alignment=ft.MainAxisAlignment.END,
    )
    page.show_dialog(dlg)


async def _download_media(page: ft.Page, url: str, default_name: str):
    file_picker = getattr(page, "file_picker", None)
    if not file_picker:
        file_picker = ft.FilePicker()
        page.services.append(file_picker)
        page.update()

    path = await file_picker.save_file(file_name=default_name)
    if path:
        page.snack_bar = ft.SnackBar(ft.Text("Downloading file..."))
        page.snack_bar.open = True
        page.update()

        try:
            import httpx

            async with httpx.AsyncClient() as client:
                resp = await client.get(url, follow_redirects=True, timeout=30.0)
                resp.raise_for_status()
                with open(path, "wb") as f:
                    f.write(resp.content)
            page.snack_bar = ft.SnackBar(
                ft.Text(f"File successfully saved to {path}"), bgcolor=AppColors.SUCCESS
            )
        except Exception as ex:
            page.snack_bar = ft.SnackBar(
                ft.Text(f"Download failed: {ex}"), bgcolor=AppColors.ERROR
            )
        page.snack_bar.open = True
        page.update()


async def _save_text_content(page: ft.Page, text: str, default_name: str):
    file_picker = getattr(page, "file_picker", None)
    if not file_picker:
        file_picker = ft.FilePicker()
        page.services.append(file_picker)
        page.update()

    path = await file_picker.save_file(file_name=default_name)
    if path:
        try:
            with open(path, "w", encoding="utf-8") as f:
                f.write(text)
            page.snack_bar = ft.SnackBar(
                ft.Text(f"File successfully saved to {path}"), bgcolor=AppColors.SUCCESS
            )
        except Exception as ex:
            page.snack_bar = ft.SnackBar(
                ft.Text(f"Failed to save file: {ex}"), bgcolor=AppColors.ERROR
            )
        page.snack_bar.open = True
        page.update()


async def _save_bytes_content(page: ft.Page, data: bytes, default_name: str):
    file_picker = getattr(page, "file_picker", None)
    if not file_picker:
        file_picker = ft.FilePicker()
        page.services.append(file_picker)
        page.update()

    path = await file_picker.save_file(file_name=default_name)
    if path:
        try:
            with open(path, "wb") as f:
                f.write(data)
            page.snack_bar = ft.SnackBar(
                ft.Text(f"File successfully saved to {path}"), bgcolor=AppColors.SUCCESS
            )
        except Exception as ex:
            page.snack_bar = ft.SnackBar(
                ft.Text(f"Failed to save file: {ex}"), bgcolor=AppColors.ERROR
            )
        page.snack_bar.open = True
        page.update()
    page.update()


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
    default_name = "image.jpg" if search_type == "images" else "video.mp4"
    media_url = r.image_url if search_type == "images" and r.image_url else r.url

    if is_media:

        def action_callback(_):
            page.run_task(_download_media, page, media_url, default_name)
    else:

        def action_callback(_):
            page.run_task(_fetch_and_show, page, r.url)

    def _close_details(_):
        page.pop_dialog()

    def _open_in_browser(_):
        page.pop_dialog()
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


async def _fetch_and_show(page: ft.Page, url: str):
    from core.utils import sanitize_url

    sanitized = sanitize_url(url)
    if not sanitized:
        page.snack_bar = ft.SnackBar(
            ft.Text("Invalid URL format. Please provide a valid web link."),
            bgcolor=AppColors.ERROR,
        )
        page.snack_bar.open = True
        page.update()
        return
    url = sanitized

    # Close the result details sheet
    page.pop_dialog()

    # Show loading spinner dialog
    loading_dialog = ft.AlertDialog(
        modal=True,
        content=ft.Container(
            content=ft.Row(
                [
                    ft.ProgressRing(
                        width=24,
                        height=24,
                        stroke_width=3,
                        color=AppColors.PRIMARY,
                    ),
                    ft.Text(
                        "Extracting page content...",
                        size=tokens.FONT_SM,
                        weight=ft.FontWeight.W_500,
                        font_family="Outfit",
                    ),
                ],
                spacing=12,
                alignment=ft.MainAxisAlignment.CENTER,
            ),
            padding=ft.Padding(24, 20, 24, 20),
        ),
    )
    page.show_dialog(loading_dialog)

    try:
        result = await _search_service.extract_url(url, fmt=state.extract_format)
    except Exception:
        result = None

    # Dismiss loading spinner
    page.pop_dialog()

    if not result:
        page.snack_bar = ft.SnackBar(
            ft.Text("Failed to retrieve content from target URL"),
            bgcolor=AppColors.ERROR,
        )
        page.snack_bar.open = True
        page.update()
        return

    content = result.get("content", "")
    is_bytes = isinstance(result.get("content", ""), bytes)
    if is_bytes:
        content = f"[Binary data extracted: {len(content)} bytes]"

    # Save helper
    async def save_extract(e=None):
        if is_bytes:
            await _save_bytes_content(
                page, result.get("content", b""), "extracted_file.bin"
            )
        else:
            await _save_text_content(page, str(content), "extracted_page.md")

    def _close_preview(_):
        page.pop_dialog()

    # Title row actions
    actions_row = ft.Row(
        [
            ft.IconButton(
                icon=ft.Icons.SAVE_ALT_ROUNDED,
                icon_size=tokens.ICON_MD,
                tooltip="Save content to file",
                on_click=lambda _: page.run_task(save_extract),
            ),
            ft.IconButton(
                icon=ft.Icons.CLOSE_ROUNDED,
                icon_size=tokens.ICON_MD,
                on_click=_close_preview,
            ),
        ],
        spacing=4,
    )

    # Format switcher for preview sheet
    async def _change_preview_format(new_fmt: str):
        state.extract_format = new_fmt
        try:
            storage_svc = StorageService()
            await storage_svc.set_extract_format(new_fmt)
        except Exception:
            pass
        page.pop_dialog()
        await _fetch_and_show(page, url)

    preview_format_row = ft.Row(
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
                on_select=lambda e: page.run_task(
                    _change_preview_format, e.control.value
                ),
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

    is_dark = theme.is_dark_mode(page)
    preview_sheet = ft.BottomSheet(
        content=ft.Container(
            content=ft.Column(
                [
                    ft.Row(
                        [
                            ft.Icon(
                                ft.Icons.DOWNLOAD_ROUNDED,
                                size=tokens.ICON_MD,
                                color=AppColors.PRIMARY,
                            ),
                            ft.Text(
                                "Page Extract Preview",
                                size=tokens.FONT_LG,
                                weight=ft.FontWeight.BOLD,
                                font_family="Outfit",
                                expand=True,
                            ),
                            actions_row,
                        ],
                        spacing=tokens.SPACE_SM,
                    ),
                    preview_format_row,
                    ft.Divider(
                        height=1,
                        color=ft.Colors.with_opacity(0.08, ft.Colors.ON_SURFACE),
                    ),
                    ft.Column(
                        [
                            ft.Markdown(
                                value=str(content),
                                selectable=True,
                                extension_set="gitHubWeb",
                                on_tap_link=lambda e: _on_link_tap(page, e.data),
                            )
                            if not is_bytes
                            else ft.Text(
                                str(content), size=tokens.FONT_SM, selectable=True
                            )
                        ],
                        expand=True,
                        scroll=ft.ScrollMode.AUTO,
                    ),
                ],
                spacing=tokens.SPACE_SM,
            ),
            padding=ft.Padding(20, 16, 20, 20),
            height=page.window.height * 0.75 if page.window.height else 550,
            bgcolor=AppColors.DARK_SURFACE if is_dark else AppColors.LIGHT_SURFACE,
            border_radius=ft.BorderRadius(tokens.RADIUS_LG, tokens.RADIUS_LG, 0, 0),
        ),
        open=True,
        elevation=8,
    )
    page.show_dialog(preview_sheet)


# ── Card Builder Factories (Reusing SpanInsight's glassmorphism style) ──


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

    # Save helper
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
            on_tap_link=lambda e: _on_link_tap(page, e.data),
        )

    # Format switcher — re-fetch in different format
    async def _change_format(new_fmt: str):
        state.extract_format = new_fmt
        try:
            storage_svc = StorageService()
            await storage_svc.set_extract_format(new_fmt)
        except Exception:
            pass
        # Re-fetch the same URL with the new format
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

    # ── Progress loading section ──
    loading_box = ft.Container(
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

    # ── Error handler banner ──
    error_box = ft.Container(
        content=ft.Column(
            [
                ft.Icon(
                    ft.Icons.ERROR_OUTLINE_ROUNDED,
                    size=tokens.ICON_LG,
                    color=AppColors.ERROR,
                ),
                ft.Text(
                    "Connection Failed",
                    size=tokens.FONT_LG,
                    weight=ft.FontWeight.BOLD,
                    color=AppColors.ERROR,
                    font_family="Outfit",
                ),
                ft.Text(
                    error or "Unknown protocol error. Check settings and proxies.",
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
                    on_click=lambda _: on_restart(query),
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
        visible=bool(error) and not is_running,
    )

    # ── Render Search results ──
    if search_type == "extract":
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
            cards = [builder(r, i, page) for i, r in enumerate(results)]
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
        results_content = ft.Container(
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

    results_container = ft.Container(
        content=results_content,
        padding=ft.Padding(
            tokens.SPACE_MD, tokens.SPACE_SM, tokens.SPACE_MD, tokens.SPACE_SM
        ),
        expand=True,
        visible=not is_running and not bool(error),
    )

    return ft.View(
        route="/results",
        controls=[
            ft.SafeArea(
                content=ft.Container(
                    content=ft.Column(
                        [loading_box, error_box, results_container],
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
