"""Detail sheet for search results — enriched with metadata and actions."""

from __future__ import annotations

import flet as ft

from components.results.content_fetcher import _fetch_and_show, _url_history
from components.results.downloader import _download_media, launch_url
from core import theme, tokens
from core.state import SearchResult
from core.theme import AppColors


def _show_result_sheet(page: ft.Page, r: SearchResult, search_type: str):
    """Show an enriched bottom sheet with result info, preview, and actions."""
    is_dark = theme.is_dark_mode(page)
    bg_color = AppColors.DARK_SURFACE if is_dark else AppColors.LIGHT_SURFACE
    is_media = search_type in ("images", "videos")

    # ── Action button text ──
    action_text = {
        "images": "Download Image",
        "videos": "Download Video",
    }.get(search_type, "View Page Content")

    def action_callback(_):
        if is_media:
            page.run_task(_download_media, page, r, search_type)
        else:
            _url_history.clear()
            page.run_task(_fetch_and_show, page, r.url, pop_current=True)

    def _close(_):
        try:
            page.pop_dialog()
        except Exception:
            pass

    def _open_browser(_):
        try:
            page.pop_dialog()
        except Exception:
            pass
        page.run_task(launch_url, r.url)

    def _copy_url(_):
        async def _do():
            try:
                clipboard = ft.Clipboard()
                await clipboard.set(r.url)
                page.snack_bar = ft.SnackBar(ft.Text("URL copied"))
                page.snack_bar.open = True
                page.update()
            except Exception:
                pass

        page.run_task(_do)

    # ── Build preview based on type ──
    preview = None
    if search_type == "images" and (r.thumbnail or r.image_url):
        preview = ft.Container(
            content=ft.Image(
                src=r.thumbnail or r.image_url or "",
                fit=ft.BoxFit.CONTAIN,
                border_radius=tokens.RADIUS_MD,
                error_content=ft.Container(
                    ft.Icon(
                        ft.Icons.BROKEN_IMAGE_ROUNDED,
                        size=32,
                        color=ft.Colors.ON_SURFACE_VARIANT,
                    ),
                    height=120,
                    alignment=ft.Alignment.CENTER,
                ),
            ),
            height=180,
            border_radius=tokens.RADIUS_MD,
            clip_behavior=ft.ClipBehavior.ANTI_ALIAS,
            alignment=ft.Alignment.CENTER,
        )
    elif search_type == "videos" and r.thumbnail:
        preview = ft.Container(
            content=ft.Stack(
                [
                    ft.Image(
                        src=r.thumbnail,
                        fit=ft.BoxFit.COVER,
                        width=320,
                        height=180,
                        border_radius=tokens.RADIUS_MD,
                    ),
                    # Duration badge
                    ft.Container(
                        content=ft.Text(
                            r.duration or "",
                            size=11,
                            color=ft.Colors.WHITE,
                            weight=ft.FontWeight.BOLD,
                        ),
                        padding=ft.Padding(8, 4, 8, 4),
                        bgcolor=ft.Colors.BLACK_87,
                        border_radius=tokens.RADIUS_SM,
                        right=8,
                        bottom=8,
                    ),
                ],
            ),
            border_radius=tokens.RADIUS_MD,
            clip_behavior=ft.ClipBehavior.ANTI_ALIAS,
        )
    elif r.snippet and not is_media:
        preview = ft.Container(
            content=ft.Text(
                r.snippet,
                size=tokens.FONT_SM,
                color=ft.Colors.ON_SURFACE_VARIANT,
                max_lines=3,
                style=ft.TextStyle(height=1.4),
            ),
            padding=ft.Padding(12, 8, 12, 8),
            border_radius=tokens.RADIUS_SM,
            bgcolor=ft.Colors.with_opacity(0.04, ft.Colors.ON_SURFACE),
        )

    # ── Metadata row ──
    meta_parts = []
    if r.source or r.publisher:
        meta_parts.append(r.source or r.publisher)
    if r.date:
        meta_parts.append(r.date)
    if r.views:
        meta_parts.append(f"{r.views:,} views")
    if r.width and r.height:
        meta_parts.append(f"{r.width}×{r.height}")
    if r.duration:
        meta_parts.append(r.duration)

    meta_row = None
    if meta_parts:
        meta_row = ft.Row(
            [
                ft.Text(
                    " · ".join(meta_parts),
                    size=tokens.FONT_XS,
                    color=ft.Colors.ON_SURFACE_VARIANT,
                    font_family="Outfit",
                ),
            ],
            spacing=4,
        )

    # ── Drag handle ──
    drag_handle = ft.Container(
        width=40,
        height=4,
        border_radius=2,
        bgcolor=ft.Colors.with_opacity(0.3, ft.Colors.ON_SURFACE),
        alignment=ft.Alignment.CENTER,
        margin=ft.Margin(0, 0, 0, 8),
    )

    # ── Assemble sheet ──
    controls = [
        drag_handle,
        # Header
        ft.Row(
            [
                ft.Text(
                    r.title,
                    size=tokens.FONT_MD,
                    weight=ft.FontWeight.W_600,
                    max_lines=2,
                    overflow=ft.TextOverflow.ELLIPSIS,
                    expand=True,
                    font_family="Outfit",
                ),
                ft.IconButton(
                    icon=ft.Icons.CLOSE_ROUNDED,
                    icon_size=tokens.ICON_MD,
                    on_click=_close,
                ),
            ],
            spacing=tokens.SPACE_SM,
        ),
        # URL
        ft.Text(
            r.url,
            size=tokens.FONT_XS,
            color=AppColors.PRIMARY,
            selectable=True,
            max_lines=1,
            overflow=ft.TextOverflow.ELLIPSIS,
        ),
    ]

    # Preview
    if preview:
        controls.append(preview)

    # Metadata
    if meta_row:
        controls.append(meta_row)

    # Divider
    controls.append(
        ft.Divider(height=1, color=ft.Colors.with_opacity(0.08, ft.Colors.ON_SURFACE))
    )

    # Primary action
    controls.append(
        ft.FilledButton(
            content=ft.Row(
                [
                    ft.Icon(
                        ft.Icons.DOWNLOAD_ROUNDED
                        if is_media
                        else ft.Icons.LANGUAGE_ROUNDED,
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
                shape=ft.RoundedRectangleBorder(radius=tokens.RADIUS_MD),
                padding=ft.Padding(16, 12, 16, 12),
            ),
            expand=True,
        )
    )

    # Secondary actions row
    controls.append(
        ft.Row(
            [
                ft.OutlinedButton(
                    content=ft.Row(
                        [
                            ft.Icon(
                                ft.Icons.OPEN_IN_BROWSER_ROUNDED, size=tokens.ICON_SM
                            ),
                            ft.Text("Open", size=tokens.FONT_SM, font_family="Outfit"),
                        ],
                        spacing=4,
                        tight=True,
                    ),
                    on_click=_open_browser,
                    style=ft.ButtonStyle(
                        shape=ft.RoundedRectangleBorder(radius=tokens.RADIUS_MD),
                        side=ft.BorderSide(1, AppColors.PRIMARY),
                        padding=ft.Padding(12, 8, 12, 8),
                    ),
                    expand=True,
                ),
                ft.OutlinedButton(
                    content=ft.Row(
                        [
                            ft.Icon(ft.Icons.CONTENT_COPY_ROUNDED, size=tokens.ICON_SM),
                            ft.Text(
                                "Copy URL", size=tokens.FONT_SM, font_family="Outfit"
                            ),
                        ],
                        spacing=4,
                        tight=True,
                    ),
                    on_click=_copy_url,
                    style=ft.ButtonStyle(
                        shape=ft.RoundedRectangleBorder(radius=tokens.RADIUS_MD),
                        side=ft.BorderSide(1, ft.Colors.OUTLINE),
                        padding=ft.Padding(12, 8, 12, 8),
                    ),
                    expand=True,
                ),
            ],
            spacing=tokens.SPACE_SM,
        )
    )

    sheet_content = ft.Container(
        content=ft.Column(
            controls,
            spacing=tokens.SPACE_SM,
            scroll=ft.ScrollMode.AUTO,
            tight=True,
        ),
        padding=ft.Padding(20, 8, 20, 20),
        bgcolor=bg_color,
        border_radius=ft.BorderRadius(tokens.RADIUS_LG, tokens.RADIUS_LG, 0, 0),
    )

    sheet = ft.BottomSheet(
        content=sheet_content,
        open=True,
        elevation=8,
    )
    page.show_dialog(sheet)
