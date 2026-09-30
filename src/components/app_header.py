"""AppHeader - unified header component across all screens with a live version chip.

Follows the Sherlock (Sherlock/src/components/app_header.py) and KTV Player
(ktv-player/src/components/header.py) pattern:
- A prominent branding row on the left (or back arrow when navigated in)
- Action buttons, theme toggle, settings gear, and the version chip on the right
- The version chip normally displays v{APP_VERSION} (with "What's New" tooltip)
  and dynamically morphs into "Update: {version} Available!" (with a primary
  coloured border and notification dot) when state.update_available is True.
- Clicking the version chip always opens the update dialog.
- The entire row scrolls horizontally on narrow screens (Sherlock rule:
  header must scroll horizontally instead of clipping controls).
"""

from __future__ import annotations

from collections.abc import Callable

import flet as ft

from components.settings.version import _APP_VERSION
from core import tokens
from core.state import state
from core.theme import AppColors


def _build_version_chip(page: ft.Page | None) -> ft.Control:
    """KTV/Sherlock-style live version chip.

    Normally shows v{APP_VERSION} with a subtle pill. When state.update_available
    is True, morphs into an accented 'Update: {version} Available!' pill with
    a primary colored indicator dot. Clicking always opens the update dialog.
    """

    def _open_dialog(e=None):
        resolved_page = page
        if resolved_page is None:
            try:
                from flet import context as flet_context

                resolved_page = flet_context.page
            except Exception:
                resolved_page = None
        if resolved_page is not None:
            from components.update_dialog import show_update_dialog

            show_update_dialog(resolved_page)

    update_available = getattr(state, "update_available", False)
    if update_available:
        update_data = getattr(state, "update_data", None) or {}
        label = (
            update_data.get("version", "Update")
            if update_data.get("type") != "announcement"
            else "News"
        )
        content = ft.Row(
            controls=[
                ft.Text(
                    f"Update: {label} Available!"
                    if update_data.get("type") != "announcement"
                    else "News",
                    size=11,
                    weight=ft.FontWeight.BOLD,
                    color=AppColors.PRIMARY,
                    no_wrap=True,
                    font_family="Outfit",
                ),
                ft.Container(
                    width=6,
                    height=6,
                    border_radius=3,
                    bgcolor=AppColors.PRIMARY,
                ),
            ],
            spacing=6,
            vertical_alignment=ft.CrossAxisAlignment.CENTER,
            tight=True,
        )
        return ft.Container(
            content=content,
            padding=ft.Padding(10, 4, 10, 4),
            border_radius=10,
            bgcolor=ft.Colors.with_opacity(0.15, AppColors.PRIMARY),
            border=ft.Border.all(1.5, AppColors.PRIMARY),
            ink=True,
            tooltip="New update available - tap to view",
            on_click=_open_dialog,
        )

    return ft.Container(
        content=ft.Text(
            f"v{_APP_VERSION}",
            size=11,
            weight=ft.FontWeight.BOLD,
            color=ft.Colors.ON_SURFACE_VARIANT,
            no_wrap=True,
            font_family="Outfit",
        ),
        padding=ft.Padding(10, 4, 10, 4),
        border_radius=10,
        bgcolor=ft.Colors.with_opacity(0.08, ft.Colors.ON_SURFACE_VARIANT),
        ink=True,
        tooltip="What's New - version & changelog",
        on_click=_open_dialog,
    )


def _theme_icon(page: ft.Page | None) -> ft.IconData:
    if page is None:
        return ft.Icons.DARK_MODE_ROUNDED
    if page.theme_mode == ft.ThemeMode.DARK:
        return ft.Icons.DARK_MODE_ROUNDED
    if page.theme_mode == ft.ThemeMode.LIGHT:
        return ft.Icons.LIGHT_MODE_ROUNDED
    return ft.Icons.SETTINGS_SYSTEM_DAYDREAM_ROUNDED


def _cycle_theme(page: ft.Page | None) -> None:
    if page is None:
        return
    if page.theme_mode == ft.ThemeMode.DARK:
        new_mode = ft.ThemeMode.LIGHT
    elif page.theme_mode == ft.ThemeMode.LIGHT:
        new_mode = ft.ThemeMode.SYSTEM
    else:
        new_mode = ft.ThemeMode.DARK

    page.theme_mode = new_mode
    state.theme_mode = new_mode
    ctrl = getattr(page, "_ddgs_controller", None)
    if ctrl is not None and hasattr(ctrl, "save"):
        ctrl.save("theme", new_mode.value)
    try:
        page.update()
    except Exception:
        pass


def AppHeader(
    page: ft.Page | None,
    *,
    title: str | None = None,
    subtitle: str | None = None,
    show_back: bool = False,
    on_back: Callable | None = None,
    show_settings: bool = True,
    on_settings: Callable | None = None,
    show_theme: bool = True,
    extra_actions: list[ft.Control] | None = None,
    leading_control: ft.Control | None = None,
) -> ft.Container:
    """Unified header across DDGS screens.

    Renders branding / navigation on the left, action controls and the
    KTV-style live version/update chip on the right.
    """
    left_controls: list[ft.Control] = []

    if leading_control is not None:
        left_controls.append(leading_control)
    elif show_back and on_back is not None:
        left_controls.append(
            ft.IconButton(
                icon=ft.Icons.ARROW_BACK_ROUNDED,
                icon_size=tokens.ICON_MD,
                on_click=on_back,
                tooltip="Back",
            )
        )
    else:
        left_controls.append(
            ft.Image(
                src="icon.png",
                width=28,
                height=28,
                color=AppColors.PRIMARY,
                fit=ft.BoxFit.CONTAIN,
            )
        )

    if title:
        title_controls: list[ft.Control] = [
            ft.Text(
                title,
                size=tokens.FONT_LG,
                weight=ft.FontWeight.BOLD,
                font_family="Outfit",
            )
        ]
        if subtitle:
            title_controls.append(
                ft.Text(
                    subtitle,
                    size=tokens.FONT_XS,
                    color=ft.Colors.ON_SURFACE_VARIANT,
                    font_family="Outfit",
                )
            )
        left_controls.append(
            ft.Column(
                controls=title_controls,
                spacing=tokens.SPACE_XXS,
                tight=True,
            )
        )

    right_controls: list[ft.Control] = []
    if extra_actions:
        right_controls.extend(extra_actions)

    # The version chip is always visible on every screen
    right_controls.append(_build_version_chip(page))

    if show_theme:
        right_controls.append(
            ft.IconButton(
                icon=_theme_icon(page),
                icon_size=20,
                on_click=lambda e: _cycle_theme(page),
                tooltip="Toggle Theme",
            )
        )

    if show_settings and on_settings is not None:
        right_controls.append(
            ft.IconButton(
                icon=ft.Icons.SETTINGS_ROUNDED,
                icon_size=20,
                on_click=on_settings,
                tooltip="Settings",
            )
        )

    return ft.Container(
        content=ft.Row(
            controls=[
                ft.Row(
                    left_controls,
                    spacing=tokens.SPACE_XS,
                    vertical_alignment=ft.CrossAxisAlignment.CENTER,
                    tight=True,
                ),
                ft.Row(
                    right_controls,
                    spacing=tokens.SPACE_XS,
                    vertical_alignment=ft.CrossAxisAlignment.CENTER,
                    tight=True,
                ),
            ],
            alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
            vertical_alignment=ft.CrossAxisAlignment.CENTER,
            scroll=ft.ScrollMode.AUTO,
        ),
        padding=ft.Padding(
            tokens.SPACE_LG, tokens.SPACE_SM, tokens.SPACE_LG, tokens.SPACE_SM
        ),
    )
