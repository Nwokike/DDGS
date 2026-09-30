"""Detail sheet for search results - enriched with metadata and actions."""

from __future__ import annotations

import flet as ft

from components.results.content_fetcher import _fetch_and_show
from components.results.downloader import _download_media
from core import theme, tokens
from core.state import SearchResult
from core.theme import AppColors
from core.utils import display_url
from core.snack import show_snack


def _result_actions_sheet(page: ft.Page, r: SearchResult) -> None:
    """Quick actions for a result row - long-press (mobile) or right-click
    (desktop) - the same three verbs the detail sheet offers, one gesture
    away (plan C3)."""
    display = display_url(r.url)

    def _close(e=None):
        try:
            page.pop_dialog()
        except Exception:
            pass

    async def _open_browser(e=None):
        _close()
        from components.results.downloader import launch_url

        await launch_url(r.url, page)

    def _copied(e=None):
        _close()
        snack = ft.SnackBar(ft.Text("Link copied"))
        show_snack(page, snack)

    def _shared(e=None):
        _close()

    def _button(icon, label, handler, action=None):
        return ft.OutlinedButton(
            content=ft.Row(
                [
                    ft.Icon(icon, size=tokens.ICON_SM),
                    ft.Text(label, size=tokens.FONT_MD, font_family="Outfit"),
                ],
                spacing=8,
                tight=True,
            ),
            action=action,
            on_click=handler,
            style=ft.ButtonStyle(
                shape=ft.RoundedRectangleBorder(radius=tokens.RADIUS_MD),
                padding=ft.Padding(12, 10, 12, 10),
            ),
            expand=True,
        )

    page.show_dialog(
        ft.BottomSheet(
            content=ft.Container(
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
                                    display,
                                    size=tokens.FONT_SM,
                                    color=ft.Colors.ON_SURFACE_VARIANT,
                                    max_lines=1,
                                    overflow=ft.TextOverflow.ELLIPSIS,
                                    expand=True,
                                    font_family="Outfit",
                                ),
                            ],
                            spacing=6,
                        ),
                        _button(
                            ft.Icons.OPEN_IN_BROWSER_ROUNDED,
                            "Open in browser",
                            _open_browser,
                        ),
                        _button(
                            ft.Icons.CONTENT_COPY_ROUNDED,
                            "Copy link",
                            _copied,
                            action=ft.CopyToClipboard(r.url),
                        ),
                        _button(
                            ft.Icons.SHARE_ROUNDED,
                            "Share",
                            _shared,
                            action=ft.ShareText(
                                f"{r.title}{chr(10)}{r.url}", title=r.title
                            ),
                        ),
                    ],
                    spacing=tokens.SPACE_SM,
                    tight=True,
                ),
                padding=ft.Padding(
                    tokens.SPACE_LG, tokens.SPACE_MD, tokens.SPACE_LG, tokens.SPACE_LG
                ),
            ),
        )
    )


def _qr_dialog(page: ft.Page, url: str) -> None:
    """Open-on-phone: a QR of the link (plan D6). Scan, keep browsing."""
    import io

    import qrcode

    buffer = io.BytesIO()
    qrcode.make(url, box_size=8, border=2).save(buffer, format="PNG")
    png_bytes = buffer.getvalue()

    page.show_dialog(
        ft.AlertDialog(
            title=ft.Text("Open on your phone", font_family="Outfit"),
            content=ft.Column(
                [
                    ft.Image(src=png_bytes, width=240, height=240),
                    ft.Text(
                        "Scan to open this link on your device",
                        size=tokens.FONT_SM,
                        color=ft.Colors.ON_SURFACE_VARIANT,
                        text_align=ft.TextAlign.CENTER,
                        font_family="Outfit",
                    ),
                ],
                tight=True,
                horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                spacing=tokens.SPACE_SM,
            ),
            actions=[
                ft.FilledButton(
                    "Done",
                    on_click=lambda e: page.pop_dialog(),
                    style=ft.ButtonStyle(
                        bgcolor=AppColors.PRIMARY, color=ft.Colors.WHITE
                    ),
                )
            ],
            actions_alignment=ft.MainAxisAlignment.END,
        )
    )


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
            # The preview owns its navigation now; no shared history to
            # clear before it opens.
            page.run_task(_fetch_and_show, page, r.url, pop_current=True)

    def _close(_):
        try:
            page.pop_dialog()
        except Exception:
            pass

    def _open_browser(_):
        # The Open button's client-side action opens the URL; this just
        # closes the sheet so the browser window is visible underneath.
        try:
            page.pop_dialog()
        except Exception:
            pass

    def _copy_url(_):
        # Copying happens client-side via action=ft.CopyToClipboard.
        snack = ft.SnackBar(ft.Text("URL copied"))
        show_snack(page, snack)
        page.update()

    # ── Passive summary card (non-media only): same pattern as search
    # overviews - it starts itself once the sheet is up. The getter pulls
    # the full page text; when the extract is empty it falls back to the
    # title + snippet so there is always something to summarize.
    async def _load_result_text() -> str | None:
        try:
            from services.search_service import SearchService

            svc = SearchService()
            res, _err = await svc.extract_url(r.url, fmt="text_plain")
            text = str((res or {}).get("content") or "")
            if not text.strip():
                text = f"{r.title}\n\n{r.snippet}"
            return text or None
        except Exception:
            return f"{r.title}\n\n{r.snippet}"

    summary_card, start_summary = (None, None)
    if not is_media:
        from components.ai_summary import build_auto_summary

        summary_card, start_summary = build_auto_summary(
            page,
            get_title=lambda: r.title,
            load_content=_load_result_text,
            get_url=lambda: r.url,
        )

    # ── Build preview based on type ──
    preview = None
    if search_type == "images" and (r.thumbnail or r.image_url):
        # Plan C10: the preview pinch-zooms (mouse-wheel zooms on desktop),
        # so a photo is inspectable without leaving the sheet.
        preview = ft.Container(
            content=ft.InteractiveViewer(
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
                min_scale=1.0,
                max_scale=5.0,
                trackpad_scroll_causes_scale=True,
            ),
            height=220,
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
        # Header: right-click (desktop) and long-press (mobile) open the
        # quick actions sheet: same verbs as the card row, per plan.
        ft.GestureDetector(
            on_secondary_tap=lambda _: _result_actions_sheet(page, r),
            content=ft.Row(
                [
                    ft.Container(
                        content=ft.Text(
                            r.title,
                            size=tokens.FONT_MD,
                            weight=ft.FontWeight.W_600,
                            max_lines=2,
                            overflow=ft.TextOverflow.ELLIPSIS,
                            font_family="Outfit",
                        ),
                        expand=True,
                        on_long_press=lambda _: _result_actions_sheet(page, r),
                    ),
                    ft.IconButton(
                        icon=ft.Icons.QR_CODE_ROUNDED,
                        icon_size=tokens.ICON_MD,
                        tooltip="Open on your phone",
                        on_click=lambda e: _qr_dialog(page, r.url),
                    ),
                    ft.IconButton(
                        icon=ft.Icons.CLOSE_ROUNDED,
                        icon_size=tokens.ICON_MD,
                        on_click=_close,
                    ),
                ],
                spacing=tokens.SPACE_SM,
            ),
        ),
        # URL
        ft.Text(
            display_url(r.url),
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

    # Passive summary sits above the actions so the stream is visible
    # without scrolling; collapsible any time - never a button, never
    # a modal.
    if summary_card is not None:
        controls.append(summary_card)

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
                    action=ft.OpenUrl(r.url),
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
                    action=ft.CopyToClipboard(r.url),
                    on_click=_copy_url,
                    style=ft.ButtonStyle(
                        shape=ft.RoundedRectangleBorder(radius=tokens.RADIUS_MD),
                        side=ft.BorderSide(1, ft.Colors.OUTLINE),
                        padding=ft.Padding(12, 8, 12, 8),
                    ),
                    expand=True,
                ),
                ft.OutlinedButton(
                    content=ft.Row(
                        [
                            ft.Icon(ft.Icons.SHARE_ROUNDED, size=tokens.ICON_SM),
                            ft.Text("Share", size=tokens.FONT_SM, font_family="Outfit"),
                        ],
                        spacing=4,
                        tight=True,
                    ),
                    action=ft.ShareText(f"{r.title}\n{r.url}", title=r.title),
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
    if start_summary is not None:
        start_summary()
