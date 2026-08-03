"""ContentReaderScreen — full-screen reader for extracted web content.

Pushed as a ft.View when the user taps "Fetch Page" or clicks a link
inside extracted content.  Has its own AppBar, back stack for in-reader
link navigation, and format switching.
"""

from __future__ import annotations

import flet as ft
from flet import Control

from contexts.app_state_ctx import AppStateCtx
from core import theme, tokens
from core.theme import AppColors


@ft.component
def ContentReaderScreen(url: str, content: str | None = None) -> Control:
    """Full-screen content reader with back stack for link navigation."""
    state = ft.use_context(AppStateCtx)

    from flet import context as flet_context

    def _get_page():
        return flet_context.page

    # State
    url_stack, set_url_stack = ft.use_state([])
    current_url, set_current_url = ft.use_state(url)
    current_content, set_current_content = ft.use_state(content)
    is_loading, set_is_loading = ft.use_state(content is None)
    error, set_error = ft.use_state(None)
    format_val, set_format_val = ft.use_state(state.extract_format)

    # Fetch content
    async def _fetch(target_url: str):
        set_is_loading(True)
        set_error(None)
        try:
            from services.search_service import SearchService

            svc = SearchService()
            result, err = await svc.extract_url(target_url, fmt=format_val)
            if err:
                set_error(err)
                set_current_content(None)
            elif result:
                set_current_content(result.get("content", ""))
                set_current_url(target_url)
            else:
                set_current_content("No content extracted.")
        except Exception as ex:
            set_error(str(ex))
            set_current_content(None)
        finally:
            set_is_loading(False)

    # Initial fetch
    def _on_mount(_):
        if current_content is None and not is_loading:
            _get_page().run_task(_fetch, current_url)

    ft.use_effect(_on_mount, [current_url])

    # Link tap inside content
    def _on_link_tap(e):
        import urllib.parse

        link = e.data
        if not link or link.startswith(("#", "mailto:")):
            return
        # Resolve relative URLs
        if not link.startswith("http"):
            parsed = urllib.parse.urlparse(current_url)
            link = f"{parsed.scheme}://{parsed.netloc}/{link.lstrip('/')}"
        # Push current to stack, fetch new
        new_stack = list(url_stack)
        new_stack.append(current_url)
        set_url_stack(new_stack)
        _get_page().run_task(_fetch, link)

    # Go back in reader
    def _go_back():
        if url_stack:
            new_stack = list(url_stack)
            prev = new_stack.pop()
            set_url_stack(new_stack)
            _get_page().run_task(_fetch, prev)
        else:
            # Exit reader
            _get_page().views.pop()
            _get_page().update()

    # Format change
    def _on_format_change(e):
        new_fmt = e.control.value
        set_format_val(new_fmt)
        _get_page().run_task(_fetch, current_url)

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
                    current_url or "",
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
                value=format_val,
                options=[
                    ft.dropdown.Option("text_markdown", "Markdown"),
                    ft.dropdown.Option("text_plain", "Plain"),
                    ft.dropdown.Option("text_rich", "Rich"),
                ],
                on_select=_on_format_change,
                dense=True,
                text_size=tokens.FONT_XS,
                content_padding=ft.Padding(8, 2, 8, 2),
                width=110,
                height=36,
            ),
            ft.IconButton(
                icon=ft.Icons.CONTENT_COPY_ROUNDED,
                icon_size=tokens.ICON_SM,
                tooltip="Copy URL",
                on_click=lambda _: _copy_url(),
            ),
            ft.IconButton(
                icon=ft.Icons.OPEN_IN_BROWSER_ROUNDED,
                icon_size=tokens.ICON_SM,
                tooltip="Open in Browser",
                on_click=lambda _: _get_page().run_task(_open_browser),
            ),
            ft.Container(width=4),
        ],
        bgcolor=ft.Colors.TRANSPARENT,
        elevation=0,
    )

    async def _copy_url():
        try:
            await _get_page().clipboard.set(current_url or "")
            _get_page().snack_bar = ft.SnackBar(ft.Text("URL copied"))
            _get_page().snack_bar.open = True
            _get_page().update()
        except Exception:
            pass

    async def _open_browser():
        try:
            await ft.UrlLauncher().launch_url(current_url or "")
        except Exception:
            import webbrowser
            webbrowser.open(current_url or "")

    # Content body
    if is_loading:
        body = ft.Container(
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
        )
    elif error:
        body = ft.Container(
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
                        error,
                        size=tokens.FONT_SM,
                        color=ft.Colors.ON_SURFACE_VARIANT,
                        text_align=ft.TextAlign.CENTER,
                    ),
                    ft.Container(height=16),
                    ft.FilledButton(
                        "Retry",
                        icon=ft.Icons.REFRESH_ROUNDED,
                        on_click=lambda _: _get_page().run_task(_fetch, current_url),
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
        )
    elif current_content:
        body = ft.Container(
            content=ft.Markdown(
                value=str(current_content),
                selectable=True,
                extension_set="gitHubWeb",
                on_tap_link=_on_link_tap,
            ),
            padding=ft.Padding(
                tokens.SPACE_LG, tokens.SPACE_SM, tokens.SPACE_LG, tokens.SPACE_LG
            ),
            expand=True,
        )
    else:
        body = ft.Container(
            content=ft.Text(
                "No content to display.",
                size=tokens.FONT_SM,
                color=ft.Colors.ON_SURFACE_VARIANT,
            ),
            alignment=ft.Alignment.CENTER,
            expand=True,
        )

    return ft.Container(
        content=ft.Column(
            [appbar, body],
            spacing=0,
            expand=True,
        ),
        gradient=theme.AppStyles.brand_gradient(_get_page()),
        expand=True,
    )
