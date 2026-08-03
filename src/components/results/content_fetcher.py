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
from services.search_service import SearchService
from services.storage_service import StorageService

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
    """Directly fetch the tapped link and update the current view — like browser navigation."""
    if not url or url.startswith(("#", "mailto:")):
        return
    resolved = _resolve_url(url, base_url)
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
        snack_tmp.open = True
        page.show_dialog(snack_tmp)
        page.update()


async def _fetch_and_show(page: ft.Page, url: str, pop_current: bool = True):
    from core.utils import sanitize_url

    sanitized = sanitize_url(url)
    if not sanitized:
        snack_tmp = ft.SnackBar(
            ft.Text("Invalid URL format. Please provide a valid web link."),
            bgcolor=AppColors.ERROR,
        )
        snack_tmp.open = True
        page.show_dialog(snack_tmp)
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
        err_str = str(error_msg or "").lower()
        is_offline = any(
            kw in err_str
            for kw in (
                "dns",
                "connect",
                "network",
                "offline",
                "unreachable",
                "timed out",
                "timeout",
                "refused",
            )
        )
        if is_offline:
            snack_tmp = ft.SnackBar(
                ft.Text(
                    "No internet connection. Please check your network and try again."
                ),
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
        snack_tmp.open = True
        page.show_dialog(snack_tmp)
        page.update()
        return

    content = result.get("content", "")
    is_bytes = isinstance(result.get("content", ""), bytes)
    if is_bytes:
        content = f"[Binary data extracted: {len(content)} bytes]"

    async def save_extract(e=None):
        if is_bytes:
            await _save_bytes_content(
                page, result.get("content", b""), "extracted_file.bin"
            )
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

            parsed_url = urllib.parse.urlparse(url)
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
            await _save_text_content(page, str(content), file_name)

    def _expand_to_reader():
        """Close this preview and open the full-screen content reader."""
        _url_history.clear()
        page.pop_dialog()
        ctrl = getattr(page, "_ddgs_controller", None)
        if ctrl:
            ctrl.open_content_reader(url, str(content) if content else None)

    def _close_preview(_):
        _url_history.clear()
        page.pop_dialog()

    def _go_back(_):
        if _url_history:
            prev_url = _url_history.pop()
            page.pop_dialog()
            page.run_task(_fetch_and_show, page, prev_url, pop_current=False)

    has_history = len(_url_history) > 0

    header_row = ft.Row(
        [
            ft.IconButton(
                icon=ft.Icons.ARROW_BACK_ROUNDED,
                icon_size=tokens.ICON_MD,
                tooltip="Back to previous page",
                on_click=_go_back,
                visible=has_history,
            ),
            ft.Icon(
                ft.Icons.LANGUAGE_ROUNDED,
                size=tokens.ICON_MD,
                color=AppColors.PRIMARY,
            ),
            ft.Text(
                url[:60] + ("..." if len(url) > 60 else ""),
                size=tokens.FONT_SM,
                weight=ft.FontWeight.W_600,
                font_family="Outfit",
                expand=True,
                max_lines=1,
                overflow=ft.TextOverflow.ELLIPSIS,
            ),
            ft.IconButton(
                icon=ft.Icons.OPEN_IN_BROWSER_ROUNDED,
                icon_size=tokens.ICON_MD,
                tooltip="Open in browser",
                on_click=lambda _: page.run_task(launch_url, url),
            ),
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
        page.pop_dialog()
        await _fetch_and_show(page, url, pop_current=False)

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

    def _nav_link(page_ref, link_url, base):
        _url_history.append(url)
        _on_link_tap(page_ref, link_url, base, from_dialog=True)

    is_dark = theme.is_dark_mode(page)
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
                    ft.Column(
                        [
                            ft.Markdown(
                                value=str(content),
                                selectable=True,
                                extension_set="gitHubWeb",
                                on_tap_link=lambda e: _nav_link(page, e.data, url),
                            )
                            if not is_bytes
                            else ft.Text(
                                str(content), size=tokens.FONT_SM, selectable=True
                            )
                        ],
                        expand=True,
                        scroll=ft.ScrollMode.AUTO,
                    ),
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
