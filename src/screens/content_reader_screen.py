"""ContentReaderScreen - full-screen reader for extracted web content.

Pushed as a ft.View when the user taps "Open in Reader" from the
extract card.  Uses imperative state (not hooks) since it's rendered
outside the component tree.
"""

from __future__ import annotations

import flet as ft

from components.app_header import _build_version_chip
from core import theme, tokens
from core.state import state
from core.styles import build_banner_ad
from core.theme import AppColors
from core.utils import FetchNav, resolve_url, set_extract_format
from core.snack import show_snack


def build_content_reader(
    page: ft.Page, url: str, content: str | None = None
) -> ft.View:
    """Build a full-screen content reader View with back stack."""
    # Imperative state (since this runs outside the component tree). The
    # nav is this view's own: no other surface can bleed history into it,
    # and rapid link taps are debounced instead of stacking fetches.
    _nav = FetchNav()
    _current_url = url
    _current_content = content
    _is_loading = content is None
    _error = None

    # UI references
    content_text = ft.Ref[ft.Markdown]()
    loading_col = ft.Ref[ft.Container]()
    error_col = ft.Ref[ft.Container]()
    url_text = ft.Ref[ft.Text]()
    format_dropdown = ft.Ref[ft.Dropdown]()
    copy_btn = ft.Ref[ft.IconButton]()
    open_btn = ft.Ref[ft.IconButton]()

    async def _fetch(target_url: str, force: bool = False):
        nonlocal _current_url, _current_content, _is_loading, _error
        _is_loading = True
        _error = None
        _update_ui()

        try:
            from services.search_service import SearchService

            svc = SearchService()
            # force bypasses the 24h page cache: Refresh and Retry must
            # show what the server serves now, or Retry after a failed
            # extract re-renders the same failure from cache.
            result, err = await svc.extract_url(
                target_url, fmt=state.extract_format, force=force
            )
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
            if not _error and _current_content:
                start_summary(force=True)

    def _update_ui():
        """Rebuild the content area based on current state."""
        if url_text.current:
            url_text.current.value = _current_url
        # Client actions must carry the URL that is current right now.
        if copy_btn.current:
            copy_btn.current.action = ft.CopyToClipboard(_current_url or "")
        if open_btn.current:
            open_btn.current.action = ft.OpenUrl(_current_url or "")

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

    # Register keyboard handler - chained, not replacing (plan C9): the
    # global Esc/Ctrl+K handler must survive a Reader round-trip.
    _prev_key_handler = page.on_keyboard_event

    def _handle_keyboard(e):
        """Handle hardware back button on Android; delegate the rest."""
        if _prev_key_handler is not None:
            try:
                _prev_key_handler(e)
            except Exception:
                pass
        if e.key in ("Back", "Escape", "BrowserBack"):
            _go_back()

    page.on_keyboard_event = _handle_keyboard

    def _on_link_tap(e):
        # One resolver for every surface (extract card, preview sheet,
        # reader): urljoin for relative links, scheme guard after - so
        # `../`, `?q` and `./path` work while `javascript:` never fetches.
        resolved = resolve_url(_current_url, e.data)
        if resolved is None or not _nav.allow_tap():
            return
        _nav.push(_current_url)
        page.run_task(_fetch, resolved)

    def _go_back():
        prev = _nav.pop()
        if prev:
            page.run_task(_fetch, prev)
        else:
            _exit_reader()

    def _exit_reader():
        """Always exit the reader - pop back to whatever was underneath."""
        try:
            page.on_keyboard_event = _prev_key_handler
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
            snack = ft.SnackBar(ft.Text(f"Save failed: {ex}"))
            show_snack(page, snack)
            page.update()

    def _on_format_change(e):
        # The reader drives the SAME global setting as the extract card
        # and the preview sheet: one switch, persisted, reflected
        # everywhere - it used to keep a private copy that never saved.

        async def _apply():
            await set_extract_format(page, e.control.value)
            await _fetch(_current_url)

        page.run_task(_apply)

    def _copy_feedback(_=None):
        snack = ft.SnackBar(ft.Text("URL copied"))
        show_snack(page, snack)
        page.update()

    # ── Assistant summary card (top of reader, expandable - NOT a modal)
    # The search overview pattern for one page: no button, no modal. The
    # card starts hidden and auto-starts after the fetch, collapsing via
    # its chevron. Follow-ups appear only as terminal states.
    from components.ai_summary import build_auto_summary

    summary_card, start_summary = build_auto_summary(
        page,
        get_title=lambda: _current_url or "Page",
        get_content=lambda: (
            None
            if isinstance(_current_content, bytes)
            else (str(_current_content) if _current_content else None)
        ),
        get_url=lambda: _current_url or "",
    )

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
                value=state.extract_format,
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
                icon=ft.Icons.REFRESH_ROUNDED,
                icon_size=tokens.ICON_SM,
                tooltip="Refresh content",
                on_click=lambda _: page.run_task(_fetch, _current_url, True),
            ),
            ft.IconButton(
                ref=copy_btn,
                icon=ft.Icons.CONTENT_COPY_ROUNDED,
                icon_size=tokens.ICON_SM,
                tooltip="Copy URL",
                action=ft.CopyToClipboard(url or ""),
                on_click=_copy_feedback,
            ),
            ft.IconButton(
                ref=open_btn,
                icon=ft.Icons.OPEN_IN_BROWSER_ROUNDED,
                icon_size=tokens.ICON_SM,
                tooltip="Open in Browser",
                action=ft.OpenUrl(url or ""),
            ),
            _build_version_chip(page),
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
                    on_click=lambda _: page.run_task(_fetch, _current_url, True),
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
            # Plan D7: code fences in scraped pages now carry a real
            # pygments theme (Dart-side, zero cost) - dark reads DRACULA,
            # light keeps the default.
            code_theme=(
                ft.MarkdownCodeTheme.DRACULA
                if theme.is_dark_mode(page)
                else ft.MarkdownCodeTheme.DEFAULT
            ),
            on_tap_link=_on_link_tap,
            visible=bool(_current_content),
        ),
        padding=ft.Padding(
            tokens.SPACE_LG, tokens.SPACE_SM, tokens.SPACE_LG, tokens.SPACE_LG
        ),
        expand=True,
    )

    body = ft.Column(
        [loading_indicator, error_box, markdown_view, build_banner_ad(page)],
        spacing=0,
        expand=True,
    )

    # Pre-loaded content (extract card / preview sheet path) never goes
    # through _fetch, so kick the auto-summary here; the streamed tokens
    # land after the view mounts. Opened with NO content (a tapped link
    # from the extract card), the fetch never starts by itself - kick it
    # or the spinner runs forever.
    if _current_content and not _is_loading:
        start_summary()
    elif _is_loading:
        page.run_task(_fetch, _current_url)

    return ft.View(
        route="/reader",
        controls=[
            ft.Container(
                content=ft.Column(
                    [appbar, summary_card, body],
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
