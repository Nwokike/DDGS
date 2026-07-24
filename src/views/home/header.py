from __future__ import annotations

from collections.abc import Callable

import flet as ft

from core import tokens
from core.state import state
from core.theme import AppColors


def build_appbar(
    page: ft.Page,
    on_navigate: Callable,
    storage,
    rebuild_fn: Callable,
) -> ft.AppBar:
    def _toggle_theme(e):
        if page.theme_mode == ft.ThemeMode.DARK:
            page.theme_mode = ft.ThemeMode.LIGHT
        elif page.theme_mode == ft.ThemeMode.LIGHT:
            page.theme_mode = ft.ThemeMode.SYSTEM
        else:
            page.theme_mode = ft.ThemeMode.DARK
        state.theme_mode = page.theme_mode
        page.run_task(storage.set_theme, page.theme_mode.value)
        rebuild_fn()

    def _get_theme_icon():
        if page.theme_mode == ft.ThemeMode.DARK:
            return ft.Icons.DARK_MODE_ROUNDED
        elif page.theme_mode == ft.ThemeMode.LIGHT:
            return ft.Icons.LIGHT_MODE_ROUNDED
        return ft.Icons.SETTINGS_SYSTEM_DAYDREAM_ROUNDED

    return ft.AppBar(
        leading=ft.Container(
            content=ft.Row(
                [
                    ft.Image(
                        src="icon.png", width=28, height=28, color=AppColors.PRIMARY
                    ),
                    ft.Text(
                        "DDGS",
                        size=tokens.FONT_LG,
                        weight=ft.FontWeight.BOLD,
                        font_family="Outfit",
                    ),
                ],
                spacing=8,
                tight=True,
            ),
            padding=ft.Padding(12, 0, 0, 0),
        ),
        leading_width=120,
        actions=[
            ft.IconButton(
                icon=_get_theme_icon(),
                icon_size=20,
                on_click=_toggle_theme,
                tooltip="Toggle Theme",
            ),
            ft.IconButton(
                icon=ft.Icons.SETTINGS_ROUNDED,
                icon_size=20,
                on_click=lambda e: on_navigate("/settings"),
                tooltip="Open Settings",
            ),
            ft.Container(width=8),
        ],
        bgcolor=ft.Colors.TRANSPARENT,
        elevation=0,
    )


def build_hero() -> ft.Container:
    return ft.Container(
        content=ft.Column(
            [
                ft.Container(height=tokens.SPACE_LG),
                ft.Image(
                    src="icon.png",
                    width=72,
                    height=72,
                    color=AppColors.PRIMARY,
                    fit=ft.BoxFit.CONTAIN,
                ),
                ft.Container(height=tokens.SPACE_SM),
                ft.Text(
                    "Search the web privately.\nFetch any webpage instantly.",
                    size=tokens.FONT_SM,
                    color=ft.Colors.ON_SURFACE_VARIANT,
                    text_align=ft.TextAlign.CENTER,
                    font_family="Outfit",
                    weight=ft.FontWeight.W_500,
                ),
                ft.Container(height=tokens.SPACE_XL),
            ],
            horizontal_alignment=ft.CrossAxisAlignment.CENTER,
            spacing=0,
        ),
    )
