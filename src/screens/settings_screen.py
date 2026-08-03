"""SettingsScreen — all app settings with theme, search rules, backends, etc.

Converted from views/settings/view_builder.py to declarative @ft.component.
During migration, section builders are imported from old views/settings/.
Phase 5 will move these to components/.
"""

from __future__ import annotations

import flet as ft
from flet import Control

from contexts.controller_ctx import ControllerMethodsCtx
from core import theme
from core.state import state
from core.styles import build_banner_ad
from core.theme import AppColors
from core.tokens import (
    FONT_LG,
    FONT_XS,
    ICON_MD,
)
from core.utils import in_memory_log_handler, logger


async def _launch_url(url: str):
    """Launch a URL with fallback to webbrowser."""
    try:
        await ft.UrlLauncher().launch_url(url)
    except Exception:
        import webbrowser

        webbrowser.open(url)


def _build_logs_dialog():
    """Build the live activity logs dialog."""
    from flet import context as flet_context

    logs = (
        "\n".join(in_memory_log_handler.records)
        if in_memory_log_handler.records
        else "No activity recorded yet. Perform a search to see live output."
    )

    log_text_control = ft.Text(
        logs,
        font_family="Courier New",
        size=11,
        color="#A6E22E",
        selectable=True,
    )

    async def copy_logs(e=None):
        try:
            page = flet_context.page
            await page.clipboard.set(logs)
            snack = ft.SnackBar(ft.Text("Activity log copied to clipboard!"))
            snack.open = True
            page.show_dialog(snack)
            page.update()
        except Exception as ex:
            logger.error(f"Copy logs failed: {ex}")

    def close_dialog(e=None):
        flet_context.page.pop_dialog()

    return ft.AlertDialog(
        title=ft.Row(
            [
                ft.Icon(ft.Icons.TERMINAL_ROUNDED, size=22, color=AppColors.PRIMARY),
                ft.Text(
                    "Live Activity",
                    font_family="Outfit",
                    size=FONT_LG,
                    weight=ft.FontWeight.BOLD,
                ),
            ],
            spacing=8,
        ),
        content=ft.Container(
            content=ft.Column(
                [
                    ft.Text(
                        "Real-time log of every search, connection, and response. "
                        "Copy and share if you encounter errors.",
                        size=FONT_XS,
                        color=ft.Colors.ON_SURFACE_VARIANT,
                    ),
                    ft.Container(
                        content=ft.Column(
                            [log_text_control], scroll=ft.ScrollMode.AUTO
                        ),
                        padding=12,
                        bgcolor="#0D0D0D",
                        border=ft.Border.all(
                            1, ft.Colors.with_opacity(0.15, ft.Colors.WHITE)
                        ),
                        border_radius=8,
                        expand=True,
                    ),
                ],
                spacing=8,
            ),
            width=450,
            height=500,
        ),
        actions=[
            ft.IconButton(
                icon=ft.Icons.COPY_ROUNDED,
                tooltip="Copy to Clipboard",
                on_click=lambda e: copy_logs(),
            ),
            ft.TextButton(
                "Close",
                on_click=close_dialog,
            ),
        ],
        actions_alignment=ft.MainAxisAlignment.END,
    )


@ft.component
def SettingsScreen() -> Control:
    """All app settings: theme, search rules, backends, connection, about."""
    controller = ft.use_context(ControllerMethodsCtx)

    from flet import context as flet_context

    def _get_page():
        return flet_context.page

    def _set(key: str, val):
        controller.save(key, val)

    def _current_theme():
        page = _get_page()
        if page.theme_mode == ft.ThemeMode.DARK:
            return "dark"
        elif page.theme_mode == ft.ThemeMode.LIGHT:
            return "light"
        return "system"

    async def _change_theme(mode_str: str):
        _set("theme", mode_str)

    def _show_clear_dialog(e):
        async def _do_clear():
            page = _get_page()
            page.pop_dialog()
            state.search_history.clear()
            await controller.save_async("history", [])

        page = _get_page()
        dlg = ft.AlertDialog(
            modal=True,
            title=ft.Text(
                "Clear Search History?",
                font_family="Outfit",
                size=FONT_LG,
                weight=ft.FontWeight.BOLD,
            ),
            content=ft.Text(
                "This will delete all saved search entries. This action is irreversible.",
                style=ft.TextStyle(height=1.4),
            ),
            actions=[
                ft.TextButton("Cancel", on_click=lambda _: page.pop_dialog()),
                ft.FilledButton(
                    "Clear All",
                    on_click=lambda _: page.run_task(_do_clear),
                    style=ft.ButtonStyle(
                        bgcolor=AppColors.ERROR, color=ft.Colors.WHITE
                    ),
                ),
            ],
            actions_alignment=ft.MainAxisAlignment.END,
        )
        page.show_dialog(dlg)

    # ── Import old section builders during migration ──
    from components.settings.sections_about import (
        build_about_section,
        build_logs_section,
        build_storage_section,
    )
    from components.settings.sections_advanced import (
        build_backends_section,
        build_connection_section,
        build_downloads_section,
        build_extraction_section,
        build_performance_section,
    )
    from components.settings.sections_general import (
        build_search_rules_section,
        build_theme_section,
    )

    page = _get_page()

    # ── Header ──
    header = ft.Container(
        content=ft.Row(
            [
                ft.IconButton(
                    icon=ft.Icons.ARROW_BACK_ROUNDED,
                    icon_size=ICON_MD,
                    on_click=lambda e: controller.navigate_tab(0),
                ),
                ft.Text(
                    "Settings",
                    size=FONT_LG,
                    weight=ft.FontWeight.BOLD,
                    font_family="Outfit",
                ),
            ],
            spacing=4,
        ),
        padding=ft.Padding(4, 8, 16, 8),
    )

    # ── Sections ──
    # Old section builders use page.run_task() internally, so all callbacks
    # passed to them must be async (coroutine functions).
    async def _set_safe_search(v):
        await controller.save_async("safe_search", v)

    sections = ft.Column(
        [
            build_theme_section(page, _current_theme(), _change_theme),
            build_search_rules_section(
                page,
                controller.save_async,
                _set_safe_search,
            ),
            build_banner_ad(page),
            build_backends_section(page, controller.save_async),
            build_extraction_section(page, controller.save_async),
            build_downloads_section(page, controller.save_async),
            build_connection_section(page, controller.save_async),
            build_performance_section(page, controller.save_async),
            build_logs_section(page),
            build_storage_section(page, _show_clear_dialog),
            build_about_section(
                page,
                lambda e: _launch_url("https://kiri.ng/privacy"),
                lambda e: _launch_url("https://kiri.ng/terms"),
            ),
            ft.Container(
                content=ft.Text(
                    "Dux Distributed Global Search (DDGS)",
                    size=10,
                    text_align=ft.TextAlign.CENTER,
                    color=ft.Colors.ON_SURFACE_VARIANT,
                ),
                alignment=ft.Alignment.CENTER,
                padding=ft.Padding(0, 12, 0, 24),
            ),
            build_banner_ad(page),
        ],
        spacing=16,
        scroll=ft.ScrollMode.AUTO,
        expand=True,
    )

    return ft.Container(
        content=ft.Column(
            [header, ft.Container(content=sections, padding=16, expand=True)],
            spacing=0,
            expand=True,
        ),
        gradient=theme.AppStyles.brand_gradient(page),
        expand=True,
    )
