"""ContentReaderScreen — full-screen reader for extracted web content.

Pushed as a ft.View when the user taps "Open in Reader" from the
extract card.  Uses imperative state (not hooks) since it's rendered
outside the component tree.
"""

from __future__ import annotations

import flet as ft

from core import theme, tokens
from core.state import state
from core.theme import AppColors


def build_content_reader(
    page: ft.Page, url: str, content: str | None = None
) -> ft.View:
    """Build a full-screen content reader View with back stack."""
    # Imperative state (since this runs outside the component tree)
    _url_stack: list[str] = []
    _current_url = url
    _current_content = content
    _is_loading = content is None
    _error = None
    # Map extract_format to valid dropdown options
    _VALID_FORMATS = {"text_markdown", "text_plain", "text_rich", "text", "content"}
    _format = (
        state.extract_format
        if state.extract_format in _VALID_FORMATS
        else "text_markdown"
    )

    # UI references
    content_text = ft.Ref[ft.Markdown]()
    loading_col = ft.Ref[ft.Container]()
    error_col = ft.Ref[ft.Container]()
    url_text = ft.Ref[ft.Text]()
    format_dropdown = ft.Ref[ft.Dropdown]()

    async def _fetch(target_url: str):
        nonlocal _current_url, _current_content, _is_loading, _error
        _is_loading = True
        _error = None
        _update_ui()

        try:
            from services.search_service import SearchService

            svc = SearchService()
            result, err = await svc.extract_url(target_url, fmt=_format)
            if err:
                _error = err
                _current_content = None
            elif result:
                _current_content = result.get("content", "")
                _current_url = target_url
            else:
                _current_content = "No content extracted."
        except Exception as ex:
            _error = str(ex)
            _current_content = None
        finally:
            _is_loading = False
            _update_ui()

    def _update_ui():
        """Rebuild the content area based on current state."""
        if url_text.current:
            url_text.current.value = _current_url

        if _is_loading:
            if loading_col.current:
                loading_col.current.visible = True
            if error_col.current:
                error_col.current.visible = False
            if content_text.current:
                content_text.current.visible = False
        elif _error:
            if loading_col.current:
                loading_col.current.visible = False
            if error_col.current:
                error_col.current.visible = True
            if content_text.current:
                content_text.current.visible = False
        elif _current_content:
            if loading_col.current:
                loading_col.current.visible = False
            if error_col.current:
                error_col.current.visible = False
            if content_text.current:
                content_text.current.value = str(_current_content)
                content_text.current.visible = True

        try:
            page.update()
        except Exception:
            pass

    def _handle_keyboard(e):
        """Handle hardware back button on Android."""
        if e.key in ("Back", "Escape", "BrowserBack"):
            _go_back()

    # Register keyboard handler
    page.on_keyboard_event = _handle_keyboard

    def _on_link_tap(e):
        import urllib.parse

        link = e.data
        if not link or link.startswith(("#", "mailto:")):
            return
        if not link.startswith("http"):
            parsed = urllib.parse.urlparse(_current_url)
            link = f"{parsed.scheme}://{parsed.netloc}/{link.lstrip('/')}"
        _url_stack.append(_current_url)
        page.run_task(_fetch, link)

    def _go_back():
        if _url_stack:
            prev = _url_stack.pop()
            page.run_task(_fetch, prev)
        else:
            _exit_reader()

    def _exit_reader():
        """Always exit the reader — pop back to whatever was underneath."""
        try:
            page.on_keyboard_event = None
            if len(page.views) > 1:
                page.views.pop()
                page.update()
        except Exception:
            pass

    async def _save_content():
        """Save the current content to a file."""
        if not _current_content:
            return
        try:
            from components.results.downloader import (
                _save_bytes_content,
                _save_text_content,
            )

            if isinstance(_current_content, bytes):
                await _save_bytes_content(page, _current_content, "extracted_file.bin")
            else:
                await _save_text_content(
                    page, str(_current_content), "extracted_page.md"
                )
        except Exception as ex:
            page.snack_bar = ft.SnackBar(ft.Text(f"Save failed: {ex}"))
            page.snack_bar.open = True
            page.update()

    def _on_format_change(e):
        nonlocal _format
        _format = e.control.value
        page.run_task(_fetch, _current_url)

    async def _copy_url():
        try:
            await page.clipboard.set(_current_url or "")
            page.snack_bar = ft.SnackBar(ft.Text("URL copied"))
            page.snack_bar.open = True
            page.update()
        except Exception:
            pass

    async def _open_browser():
        try:
            await ft.UrlLauncher().launch_url(_current_url or "")
        except Exception:
            import webbrowser

            webbrowser.open(_current_url or "")

    # ── Build UI ──

    appbar = ft.AppBar(
        leading=ft.IconButton(
            icon=ft.Icons.ARROW_BACK_ROUNDED,
            icon_size=tokens.ICON_MD,
            on_click=lambda _: _go_back(),
            tooltip="Back",
        ),
        title=ft.Column(
            [
                ft.Text(
                    "Content Reader",
                    size=tokens.FONT_MD,
                    weight=ft.FontWeight.W_600,
                    font_family="Outfit",
                ),
                ft.Text(
                    ref=url_text,
                    value=_current_url or "",
                    size=tokens.FONT_XS,
                    color=ft.Colors.ON_SURFACE_VARIANT,
                    max_lines=1,
                    overflow=ft.TextOverflow.ELLIPSIS,
                ),
            ],
            spacing=2,
        ),
        actions=[
            ft.Dropdown(
                ref=format_dropdown,
                value=_format,
                options=[
                    ft.dropdown.Option("text_markdown", "Markdown"),
                    ft.dropdown.Option("text_plain", "Plain Text"),
                    ft.dropdown.Option("text_rich", "Rich Text"),
                    ft.dropdown.Option("text", "Raw HTML"),
                    ft.dropdown.Option("content", "Raw Bytes"),
                ],
                on_select=_on_format_change,
                dense=True,
                text_size=tokens.FONT_XS,
                content_padding=ft.Padding(8, 2, 8, 2),
                width=130,
                height=36,
            ),
            ft.IconButton(
                icon=ft.Icons.SAVE_ALT_ROUNDED,
                icon_size=tokens.ICON_SM,
                tooltip="Save content to file",
                on_click=lambda _: page.run_task(_save_content),
            ),
            ft.IconButton(
                icon=ft.Icons.CONTENT_COPY_ROUNDED,
                icon_size=tokens.ICON_SM,
                tooltip="Copy URL",
                on_click=lambda _: page.run_task(_copy_url),
            ),
            ft.IconButton(
                icon=ft.Icons.OPEN_IN_BROWSER_ROUNDED,
                icon_size=tokens.ICON_SM,
                tooltip="Open in Browser",
                on_click=lambda _: page.run_task(_open_browser),
            ),
            ft.IconButton(
                icon=ft.Icons.CLOSE_ROUNDED,
                icon_size=tokens.ICON_MD,
                tooltip="Exit Reader",
                on_click=lambda _: _exit_reader(),
            ),
        ],
        bgcolor=ft.Colors.TRANSPARENT,
        elevation=0,
    )

    # Loading state
    loading_indicator = ft.Container(
        ref=loading_col,
        content=ft.Column(
            [
                ft.ProgressRing(color=AppColors.PRIMARY, width=32, height=32),
                ft.Container(height=8),
                ft.Text(
                    "Extracting content...",
                    size=tokens.FONT_SM,
                    color=ft.Colors.ON_SURFACE_VARIANT,
                    font_family="Outfit",
                ),
            ],
            horizontal_alignment=ft.CrossAxisAlignment.CENTER,
            spacing=0,
        ),
        alignment=ft.Alignment.CENTER,
        expand=True,
        visible=_is_loading,
    )

    # Error state
    error_box = ft.Container(
        ref=error_col,
        content=ft.Column(
            [
                ft.Icon(
                    ft.Icons.ERROR_OUTLINE_ROUNDED,
                    size=48,
                    color=AppColors.ERROR,
                ),
                ft.Container(height=8),
                ft.Text(
                    "Extraction Failed",
                    size=tokens.FONT_MD,
                    weight=ft.FontWeight.W_600,
                    color=AppColors.ERROR,
                    font_family="Outfit",
                ),
                ft.Container(height=4),
                ft.Text(
                    _error or "",
                    size=tokens.FONT_SM,
                    color=ft.Colors.ON_SURFACE_VARIANT,
                    text_align=ft.TextAlign.CENTER,
                ),
                ft.Container(height=16),
                ft.FilledButton(
                    "Retry",
                    icon=ft.Icons.REFRESH_ROUNDED,
                    on_click=lambda _: page.run_task(_fetch, _current_url),
                    style=ft.ButtonStyle(
                        bgcolor=AppColors.PRIMARY,
                        color=ft.Colors.WHITE,
                        shape=ft.RoundedRectangleBorder(radius=tokens.RADIUS_MD),
                    ),
                ),
            ],
            horizontal_alignment=ft.CrossAxisAlignment.CENTER,
            spacing=0,
        ),
        alignment=ft.Alignment.CENTER,
        expand=True,
        padding=32,
        visible=bool(_error),
    )

    # Content
    markdown_view = ft.Container(
        content=ft.Markdown(
            ref=content_text,
            value=str(_current_content) if _current_content else "",
            selectable=True,
            extension_set="gitHubWeb",
            on_tap_link=_on_link_tap,
            visible=bool(_current_content),
        ),
        padding=ft.Padding(
            tokens.SPACE_LG, tokens.SPACE_SM, tokens.SPACE_LG, tokens.SPACE_LG
        ),
        expand=True,
    )

    body = ft.Column(
        [loading_indicator, error_box, markdown_view],
        spacing=0,
        expand=True,
    )

    return ft.View(
        route="/reader",
        controls=[
            ft.Container(
                content=ft.Column(
                    [appbar, body],
                    spacing=0,
                    expand=True,
                ),
                gradient=theme.AppStyles.brand_gradient(page),
                expand=True,
            )
        ],
        padding=0,
        spacing=0,
    )
