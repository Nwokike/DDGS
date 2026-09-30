from __future__ import annotations

import flet as ft

from components.results.downloader import (
    _save_bytes_content,
    _save_text_content,
    launch_url,
)
from core import theme, tokens
from core.constants import EXTRACT_FORMATS, EXTRACT_FORMAT_SHORT
from core.state import state
from core.styles import build_banner_ad
from core.theme import AppColors
from core.utils import FetchNav, classify_error, resolve_url, set_extract_format
from services.search_service import SearchService
from core.snack import show_snack

_search_service = SearchService()


async def _fetch_and_show(page: ft.Page, url: str, pop_current: bool = True):
    from core.utils import sanitize_url

    sanitized = sanitize_url(url)
    if not sanitized:
        snack_tmp = ft.SnackBar(
            ft.Text("Invalid URL. Paste a full web link."),
            bgcolor=AppColors.ERROR,
        )
        show_snack(page, snack_tmp)
        page.update()
        return
    url = sanitized

    if pop_current:
        # Close the sheet this fetch came from (detail sheet, overview).
        # A no-op when nothing is open; the loading state below is inline,
        # so there is no second dialog to interleave on fast taps.
        try:
            page.pop_dialog()
        except Exception:
            pass

    # One mutable view for the whole sheet: format switches and link taps
    # re-extract INTO this sheet. A subsequent page from a fetch continues
    # right here - it never pops this sheet to open a second modal over
    # the results (owner's call). History and tap pacing live on this
    # call's own nav, never in module state.
    nav = FetchNav()
    view = {
        "url": url,
        "content": "",
        "raw": b"",
        "is_bytes": False,
        "loaded": False,
    }

    async def save_extract(e=None):
        if view["is_bytes"]:
            await _save_bytes_content(page, view["raw"], "extracted_file.bin")
        else:
            fmt_map = {
                "text_markdown": ".md",
                "text_plain": ".txt",
                "text_rich": ".html",
                "text": ".html",
                "content": ".bin",
            }
            ext = fmt_map.get(state.extract_format, ".md")
            import urllib.parse

            parsed_url = urllib.parse.urlparse(view["url"])
            domain_name = (
                (parsed_url.netloc or parsed_url.path or "extracted_page")
                .replace("www.", "")
                .replace(".", "_")
            )
            clean_name = (
                "".join(c for c in domain_name if c.isalnum() or c in ("_", "-")).strip(
                    "_"
                )
                or "extracted_page"
            )
            file_name = f"{clean_name}{ext}"
            await _save_text_content(page, str(view["content"]), file_name)

    def _expand_to_reader():
        """Close this preview and open the full-screen content reader."""
        nav.clear()
        page.pop_dialog()
        ctrl = getattr(page, "_ddgs_controller", None)
        if ctrl:
            ctrl.open_content_reader(
                view["url"],
                None if view["is_bytes"] else str(view["content"] or ""),
            )

    def _close_preview(_):
        nav.clear()
        page.pop_dialog()

    def _body_control():
        if view["is_bytes"]:
            return ft.Text(
                str(view["content"]), size=tokens.FONT_SM, selectable=True
            )
        return ft.Markdown(
            value=str(view["content"]),
            selectable=True,
            extension_set="gitHubWeb",
            on_tap_link=lambda e: _nav_to(e.data),
        )

    def _loading_control():
        return ft.Row(
            [
                ft.ProgressRing(
                    width=20,
                    height=20,
                    stroke_width=2,
                    color=AppColors.PRIMARY,
                ),
                ft.Text(
                    "Loading…",
                    size=tokens.FONT_SM,
                    color=ft.Colors.ON_SURFACE_VARIANT,
                ),
            ],
            spacing=8,
            vertical_alignment=ft.CrossAxisAlignment.CENTER,
        )

    def _error_control(message: str):
        return ft.Column(
            [
                ft.Icon(
                    ft.Icons.ERROR_OUTLINE_ROUNDED,
                    size=32,
                    color=AppColors.ERROR,
                ),
                ft.Text(
                    message,
                    size=tokens.FONT_SM,
                    color=ft.Colors.ON_SURFACE_VARIANT,
                    text_align=ft.TextAlign.CENTER,
                ),
                ft.Row(
                    [
                        ft.OutlinedButton(
                            "Retry",
                            icon=ft.Icons.REFRESH_ROUNDED,
                            on_click=lambda _: page.run_task(
                                _load, view["url"], False
                            ),
                        ),
                        ft.OutlinedButton(
                            "Open in browser",
                            icon=ft.Icons.OPEN_IN_BROWSER_ROUNDED,
                            on_click=lambda _: page.run_task(
                                launch_url, view["url"]
                            ),
                        ),
                    ],
                    spacing=tokens.SPACE_SM,
                    alignment=ft.MainAxisAlignment.CENTER,
                ),
            ],
            spacing=tokens.SPACE_SM,
            horizontal_alignment=ft.CrossAxisAlignment.CENTER,
            tight=True,
        )

    def _paint_error(err: str | None) -> None:
        """Failure inline: the sheet stays up and says why (with Retry).

        A page that already has content keeps it on screen; the entry
        fetch shows the error body instead of an empty sheet.
        """
        if view["loaded"]:
            body_col.controls = [_body_control()]
        else:
            message = (
                "No internet connection. Check your network and try again."
                if classify_error(err) == "offline"
                else f"Could not load this page ({err or 'Unavailable'})"
            )
            body_col.controls = [_error_control(message)]
        try:
            page.update()
        except Exception:
            pass

    def _apply(fresh: dict, new_url: str | None = None) -> None:
        """Fill the sheet from an extract result (entry and navigation)."""
        raw = fresh.get("content", "")
        if new_url:
            view["url"] = new_url
        view["raw"] = raw
        view["is_bytes"] = isinstance(raw, bytes)
        view["content"] = (
            f"[Binary data extracted: {len(raw)} bytes]"
            if view["is_bytes"]
            else raw
        )
        view["loaded"] = True
        shown = view["url"]
        header_text.value = shown[:60] + ("..." if len(shown) > 60 else "")
        back_btn.visible = nav.can_back
        open_btn.action = ft.OpenUrl(shown)
        body_col.controls = [_body_control()]
        if view["is_bytes"]:
            summary_card.visible = False
        else:
            summary_card.visible = True
            start_summary(force=True)
        try:
            page.update()
        except Exception:
            pass

    async def _load(new_url: str, push_history: bool = False) -> None:
        """Re-extract into THIS sheet: no pop, no second modal."""
        body_col.controls = [_loading_control()]
        try:
            page.update()
        except Exception:
            pass
        try:
            fresh, err = await _search_service.extract_url(
                new_url, fmt=state.extract_format
            )
        except Exception as ex:
            fresh, err = None, str(ex)
        if not fresh:
            _paint_error(err)
            return
        if push_history and view["loaded"] and view["url"] != new_url:
            nav.push(view["url"])
        _apply(fresh, new_url)

    def _nav_to(link: str) -> None:
        resolved = resolve_url(view["url"], link)
        if resolved is None or not nav.allow_tap():
            return
        page.run_task(_load, resolved, True)

    def _go_back(_):
        prev_url = nav.pop()
        if prev_url:
            page.run_task(_load, prev_url, False)

    back_btn = ft.IconButton(
        icon=ft.Icons.ARROW_BACK_ROUNDED,
        icon_size=tokens.ICON_MD,
        tooltip="Back to previous page",
        on_click=_go_back,
        visible=False,
    )
    header_text = ft.Text(
        view["url"][:60] + ("..." if len(view["url"]) > 60 else ""),
        size=tokens.FONT_SM,
        weight=ft.FontWeight.W_600,
        font_family="Outfit",
        expand=True,
        max_lines=1,
        overflow=ft.TextOverflow.ELLIPSIS,
    )
    open_btn = ft.IconButton(
        icon=ft.Icons.OPEN_IN_BROWSER_ROUNDED,
        icon_size=tokens.ICON_MD,
        tooltip="Open in browser",
        action=ft.OpenUrl(view["url"]),
    )

    header_row = ft.Row(
        [
            back_btn,
            ft.Icon(
                ft.Icons.LANGUAGE_ROUNDED,
                size=tokens.ICON_MD,
                color=AppColors.PRIMARY,
            ),
            header_text,
            open_btn,
            ft.IconButton(
                icon=ft.Icons.SAVE_ALT_ROUNDED,
                icon_size=tokens.ICON_MD,
                tooltip="Save content to file",
                on_click=lambda _: page.run_task(save_extract),
            ),
            ft.IconButton(
                icon=ft.Icons.FULLSCREEN_ROUNDED,
                icon_size=tokens.ICON_MD,
                tooltip="Open in full reader",
                on_click=lambda _: _expand_to_reader(),
            ),
            ft.IconButton(
                icon=ft.Icons.CLOSE_ROUNDED,
                icon_size=tokens.ICON_MD,
                on_click=_close_preview,
            ),
        ],
        spacing=2,
        vertical_alignment=ft.CrossAxisAlignment.CENTER,
    )

    async def _change_preview_format(new_fmt: str):
        # One writer for observable state + persistence, shared with the
        # extract card and the reader, so the surfaces cannot diverge.
        await set_extract_format(page, new_fmt)
        # In place: the sheet stays up and its content re-renders in the
        # newly chosen format. The old pop-and-reopen read as "the switch
        # opens something else" instead of "the content changed".
        await _load(view["url"], push_history=False)

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
            # All five formats visible at once (same as the extract card)
            # beats a dropdown that hid four of them behind a tap.
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
                    _change_preview_format,
                    (e.control.selected or [state.extract_format])[0],
                ),
            ),
        ],
        spacing=6,
        vertical_alignment=ft.CrossAxisAlignment.CENTER,
    )

    is_dark = theme.is_dark_mode(page)
    # Fetch sheet gets the same passive top card as search overviews: it
    # starts itself once content lands, no button, no modal - and a
    # navigation inside the sheet restarts it for the new page.
    from components.ai_summary import build_auto_summary

    summary_card, start_summary = build_auto_summary(
        page,
        get_title=lambda: view["url"],
        get_content=lambda: (
            None
            if view["is_bytes"]
            else (str(view["content"]) if view["content"] else None)
        ),
        get_url=lambda: view["url"],
    )
    # The sheet opens immediately with an inline loading body: no
    # modal loading dialog, no flicker, nothing to interleave.
    body_col = ft.Column(
        [_loading_control()],
        expand=True,
        scroll=ft.ScrollMode.AUTO,
    )
    preview_sheet = ft.BottomSheet(
        content=ft.Container(
            content=ft.Column(
                [
                    header_row,
                    preview_format_row,
                    ft.Divider(
                        height=1,
                        color=ft.Colors.with_opacity(0.08, ft.Colors.ON_SURFACE),
                    ),
                    summary_card,
                    body_col,
                    build_banner_ad(page),
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

    try:
        fresh, err = await _search_service.extract_url(
            url, fmt=state.extract_format
        )
    except Exception as ex:
        fresh, err = None, str(ex)
    if not fresh:
        _paint_error(err)
        return
    _apply(fresh, url)
