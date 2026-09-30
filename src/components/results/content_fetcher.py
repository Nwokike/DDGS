from __future__ import annotations

import flet as ft

from components.results.downloader import (
    _save_bytes_content,
    _save_text_content,
    launch_url,
)
from core import theme, tokens
from core.constants import EXTRACT_FORMATS
from core.state import state
from core.styles import build_banner_ad
from core.theme import AppColors
from core.utils import classify_error, is_web_url
from services.search_service import SearchService
from core.snack import show_snack

_search_service = SearchService()
_url_history: list[str] = []


def _resolve_url(link: str, base_url: str = "") -> str:
    """Resolve a potentially relative URL against a base URL."""
    import urllib.parse

    if not link:
        return ""
    if link.startswith(("http://", "https://")):
        return link
    if base_url:
        return urllib.parse.urljoin(base_url, link)
    return link


def _on_link_tap(
    page: ft.Page, url: str, base_url: str = "", from_dialog: bool = False
):
    """Directly fetch the tapped link and update the current view - like browser navigation."""
    if not url or url.startswith(("#", "mailto:")):
        return
    resolved = _resolve_url(url, base_url)
    if not is_web_url(resolved):
        # urljoin keeps foreign schemes (javascript:alert(1) survives it),
        # so the http(s) guard has to run AFTER resolution.
        return
    page.run_task(_fetch_and_show_link, page, resolved, from_dialog)


async def _fetch_and_show_link(page: ft.Page, url: str, from_dialog: bool = False):
    """Wrapper that safely fetches a link tapped inside fetched content."""
    try:
        await _fetch_and_show(page, url, pop_current=from_dialog)
    except (
        ValueError,
        TypeError,
        OSError,
        RuntimeError,
        ConnectionError,
        ImportError,
        KeyError,
        IndexError,
        AttributeError,
        TimeoutError,
    ):
        snack_tmp = ft.SnackBar(
            ft.Text(f"Could not fetch: {url}"),
            bgcolor=AppColors.ERROR,
        )
        show_snack(page, snack_tmp)
        page.update()


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
        page.pop_dialog()

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
                        f"Fetching {url[:50]}...",
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
        result, error_msg = await _search_service.extract_url(
            url, fmt=state.extract_format
        )
    except (
        ValueError,
        TypeError,
        OSError,
        RuntimeError,
        ConnectionError,
        ImportError,
        KeyError,
        IndexError,
        AttributeError,
        TimeoutError,
    ) as ex:
        result, error_msg = None, str(ex)

    page.pop_dialog()

    if not result:
        if classify_error(error_msg) == "offline":
            snack_tmp = ft.SnackBar(
                ft.Text("No internet connection. Check your network and try again."),
                action=ft.SnackBarAction(
                    "Retry",
                    on_click=lambda e: page.run_task(_fetch_and_show, page, url, False),
                ),
                bgcolor=AppColors.ERROR,
            )
        else:
            snack_tmp = ft.SnackBar(
                ft.Text(
                    f"Could not extract page content ({error_msg or 'Unavailable'})"
                ),
                action=ft.SnackBarAction(
                    "Open Browser",
                    on_click=lambda e: page.run_task(launch_url, url),
                ),
                bgcolor=AppColors.ERROR,
            )
        show_snack(page, snack_tmp)
        page.update()
        return

    # One mutable view for the whole sheet: format switches and link taps
    # re-extract INTO this sheet. A subsequent page from a fetch continues
    # right here - it never pops this sheet to open a second modal over
    # the results (owner's call).
    view = {
        "url": url,
        "content": result.get("content", ""),
        "raw": result.get("content", b""),
        "is_bytes": isinstance(result.get("content", ""), bytes),
    }
    if view["is_bytes"]:
        view["content"] = f"[Binary data extracted: {len(view['raw'])} bytes]"

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
        _url_history.clear()
        page.pop_dialog()
        ctrl = getattr(page, "_ddgs_controller", None)
        if ctrl:
            ctrl.open_content_reader(
                view["url"],
                None if view["is_bytes"] else str(view["content"] or ""),
            )

    def _close_preview(_):
        _url_history.clear()
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
            body_col.controls = [_body_control()]
            show_snack(
                page,
                ft.SnackBar(
                    ft.Text(
                        f"Could not load {new_url[:60]} ({err or 'Unavailable'})"
                    ),
                    bgcolor=AppColors.ERROR,
                ),
            )
            try:
                page.update()
            except Exception:
                pass
            return
        if push_history and view["url"] != new_url:
            _url_history.append(view["url"])
        raw = fresh.get("content", "")
        view["url"] = new_url
        view["raw"] = raw
        view["is_bytes"] = isinstance(raw, bytes)
        view["content"] = (
            f"[Binary data extracted: {len(raw)} bytes]" if view["is_bytes"] else raw
        )
        header_text.value = new_url[:60] + ("..." if len(new_url) > 60 else "")
        back_btn.visible = bool(_url_history)
        open_btn.action = ft.OpenUrl(new_url)
        body_col.controls = [_body_control()]
        if summary_card is not None:
            if view["is_bytes"]:
                summary_card.visible = False
            else:
                summary_card.visible = True
                start_summary(force=True)
        try:
            page.update()
        except Exception:
            pass

    def _nav_to(link: str) -> None:
        if not link or link.startswith(("#", "mailto:")):
            return
        resolved = _resolve_url(link, view["url"])
        if not is_web_url(resolved):
            # urljoin keeps foreign schemes (javascript:alert(1) survives
            # it), so the http(s) guard runs AFTER resolution.
            return
        page.run_task(_load, resolved, True)

    def _go_back(_):
        if _url_history:
            prev_url = _url_history.pop()
            page.run_task(_load, prev_url, False)

    back_btn = ft.IconButton(
        icon=ft.Icons.ARROW_BACK_ROUNDED,
        icon_size=tokens.ICON_MD,
        tooltip="Back to previous page",
        on_click=_go_back,
        visible=bool(_url_history),
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
        state.extract_format = new_fmt
        # Persist through the controller; never let a persistence failure
        # block the in-place re-extract below (page._ddgs_controller
        # exposes save_setting, not save_async).
        ctrl = getattr(page, "_ddgs_controller", None)
        try:
            if ctrl and ctrl.storage:
                await ctrl.save_setting("extract_format", new_fmt)
        except Exception:
            pass
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
                border=ft.OutlineInputBorder(border_radius=tokens.RADIUS_MD),
                width=150,
                height=36,
            ),
        ],
        spacing=6,
        vertical_alignment=ft.CrossAxisAlignment.CENTER,
    )

    is_dark = theme.is_dark_mode(page)
    # Fetch sheet gets the same passive top card as search overviews: it
    # starts itself once the sheet is up, no button, no modal - and a
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
    body_col = ft.Column(
        [_body_control()],
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
    if not view["is_bytes"]:
        start_summary()
