from __future__ import annotations

from collections.abc import Callable

import flet as ft

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
from core.state import state
from core.styles import build_banner_ad
from core.theme import AppColors, AppStyles
from core.tokens import FONT_LG, ICON_MD
from core.utils import logger
from services.storage_service import StorageService

LOG_TAG = "SettingsView"


def build_settings_view(
    page: ft.Page, on_navigate: Callable, storage: StorageService
) -> ft.View:
    logger.info(f"[{LOG_TAG}] Building settings view")

    async def _set(key: str, val):
        setattr(state, key, val)
        save = getattr(storage, f"set_{key}", None)
        if save:
            await save(val)

    def _rebuild():
        on_navigate(page.route)

    async def _launch_privacy(e=None):
        try:
            await ft.UrlLauncher().launch_url("https://kiri.ng/privacy")
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
            import webbrowser

            webbrowser.open("https://kiri.ng/privacy")

    async def _launch_terms(e=None):
        try:
            await ft.UrlLauncher().launch_url("https://kiri.ng/terms")
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
            import webbrowser

            webbrowser.open("https://kiri.ng/terms")

    current_theme = "system"
    if page.theme_mode == ft.ThemeMode.DARK:
        current_theme = "dark"
    elif page.theme_mode == ft.ThemeMode.LIGHT:
        current_theme = "light"

    async def _change_theme(mode_str: str):
        nonlocal current_theme
        current_theme = mode_str
        if mode_str == "dark":
            page.theme_mode = ft.ThemeMode.DARK
        elif mode_str == "light":
            page.theme_mode = ft.ThemeMode.LIGHT
        else:
            page.theme_mode = ft.ThemeMode.SYSTEM
        state.theme_mode = page.theme_mode
        await storage.set_theme(mode_str)
        _rebuild()

    async def _set_and_rebuild(key: str):
        await _set("safe_search", key)
        _rebuild()

    def _close_dialog(e=None):
        page.pop_dialog()

    async def _do_clear():
        page.pop_dialog()
        state.search_history.clear()
        await storage.set_history([])
        _rebuild()

    def _show_clear_dialog(e):
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
                ft.TextButton("Cancel", on_click=_close_dialog),
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

    async def _go_home():
        on_navigate("/home")

    header = ft.Container(
        content=ft.Row(
            [
                ft.IconButton(
                    icon=ft.Icons.ARROW_BACK_ROUNDED,
                    icon_size=ICON_MD,
                    on_click=lambda e: page.run_task(_go_home),
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

    sections = ft.Column(
        [
            build_theme_section(page, current_theme, _change_theme),
            build_search_rules_section(page, _set, _set_and_rebuild),
            build_banner_ad(page),
            build_backends_section(page, _set),
            build_extraction_section(page, _set),
            build_downloads_section(page, _set),
            build_connection_section(page, _set),
            build_performance_section(page, _set),
            build_logs_section(page),
            build_storage_section(page, _show_clear_dialog),
            build_about_section(page, _launch_privacy, _launch_terms),
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

    settings_body = ft.Container(
        content=sections,
        padding=16,
        expand=True,
    )

    return ft.View(
        route="/settings",
        controls=[
            ft.SafeArea(
                ft.Container(
                    content=ft.Column([header, settings_body], spacing=0, expand=True),
                    gradient=AppStyles.brand_gradient(page),
                    expand=True,
                ),
                expand=True,
            )
        ],
        padding=0,
        spacing=0,
    )
