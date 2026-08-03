from __future__ import annotations

from collections.abc import Callable

import flet as ft

from core.constants import REGIONS, SAFE_SEARCH_OPTIONS, TIMELIMIT_OPTIONS
from core.state import state
from core.theme import AppColors, AppStyles
from core.tokens import BORDER_RADIUS_MD, FONT_MD, FONT_SM, ICON_MD, SPACING_SM


def build_theme_section(
    page: ft.Page, current_theme: str, change_theme_fn: Callable
) -> ft.Container:
    def create_theme_card(mode: str, label: str, icon: str):
        is_sel = current_theme == mode
        return ft.Container(
            content=ft.Row(
                [
                    ft.Icon(
                        icon,
                        color=AppColors.PRIMARY
                        if is_sel
                        else ft.Colors.ON_SURFACE_VARIANT,
                        size=ICON_MD,
                    ),
                    ft.Text(
                        label,
                        size=12,
                        weight=ft.FontWeight.W_600 if is_sel else ft.FontWeight.NORMAL,
                        color=AppColors.PRIMARY if is_sel else ft.Colors.ON_SURFACE,
                        font_family="Outfit",
                    ),
                ],
                alignment=ft.MainAxisAlignment.CENTER,
                spacing=6,
            ),
            padding=ft.Padding(12, 10, 12, 10),
            border_radius=BORDER_RADIUS_MD,
            border=ft.Border.all(2, AppColors.PRIMARY)
            if is_sel
            else ft.Border.all(1, ft.Colors.with_opacity(0.1, ft.Colors.ON_SURFACE)),
            bgcolor=ft.Colors.with_opacity(0.1, AppColors.PRIMARY)
            if is_sel
            else ft.Colors.SURFACE_CONTAINER_HIGHEST,
            expand=True,
            animate=ft.Animation(150, ft.AnimationCurve.EASE_OUT),
            on_click=lambda e: page.run_task(change_theme_fn, mode),
        )

    light_btn = create_theme_card("light", "Light", ft.Icons.LIGHT_MODE_ROUNDED)
    dark_btn = create_theme_card("dark", "Dark", ft.Icons.DARK_MODE_ROUNDED)
    system_btn = create_theme_card(
        "system", "System", ft.Icons.SETTINGS_SYSTEM_DAYDREAM_ROUNDED
    )

    return AppStyles.section_card(
        "Display Theme",
        ft.Icons.COLOR_LENS_ROUNDED,
        ft.Row(
            [light_btn, dark_btn, system_btn],
            spacing=8,
            alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
        ),
        page=page,
    )


def build_search_rules_section(
    page: ft.Page, set_fn: Callable, set_rebuild_fn: Callable
) -> ft.Container:
    safe_chips = []
    for opt in SAFE_SEARCH_OPTIONS:
        is_active = opt["key"] == state.safe_search
        safe_chips.append(
            ft.Chip(
                label=ft.Text(opt["label"], size=FONT_SM, font_family="Outfit"),
                selected=is_active,
                on_click=lambda _, k=opt["key"]: page.run_task(set_rebuild_fn, k),
                bgcolor=ft.Colors.with_opacity(0.12, AppColors.PRIMARY)
                if is_active
                else None,
            )
        )

    return AppStyles.section_card(
        "Search Rules",
        ft.Icons.SEARCH_ROUNDED,
        ft.Column(
            [
                ft.Text(
                    "Safe Search",
                    size=FONT_MD,
                    weight=ft.FontWeight.W_600,
                    font_family="Outfit",
                ),
                ft.Row(safe_chips, spacing=SPACING_SM),
                ft.Divider(
                    height=1,
                    color=ft.Colors.with_opacity(0.04, ft.Colors.ON_SURFACE),
                ),
                ft.Text(
                    "Region Filter",
                    size=FONT_MD,
                    weight=ft.FontWeight.W_600,
                    font_family="Outfit",
                ),
                ft.Dropdown(
                    value=state.region,
                    options=[ft.dropdown.Option(r["key"], r["label"]) for r in REGIONS],
                    on_select=lambda e: page.run_task(
                        set_fn, "region", e.control.value
                    ),
                    filled=True,
                    border_radius=BORDER_RADIUS_MD,
                ),
                ft.Divider(
                    height=1,
                    color=ft.Colors.with_opacity(0.04, ft.Colors.ON_SURFACE),
                ),
                ft.Text(
                    "Max Results",
                    size=FONT_MD,
                    weight=ft.FontWeight.W_600,
                    font_family="Outfit",
                ),
                ft.Row(
                    [
                        ft.Slider(
                            value=float(state.max_results),
                            min=5,
                            max=100,
                            divisions=19,
                            label="{value}",
                            expand=True,
                            active_color=AppColors.PRIMARY,
                            on_change_end=lambda e: page.run_task(
                                set_fn, "max_results", int(e.control.value)
                            ),
                        ),
                        ft.Text(
                            f"{state.max_results}",
                            size=FONT_SM,
                            weight=ft.FontWeight.BOLD,
                            color=AppColors.PRIMARY,
                            font_family="Outfit",
                            width=24,
                        ),
                    ],
                    spacing=SPACING_SM,
                    vertical_alignment=ft.CrossAxisAlignment.CENTER,
                ),
                ft.Divider(
                    height=1,
                    color=ft.Colors.with_opacity(0.04, ft.Colors.ON_SURFACE),
                ),
                ft.Text(
                    "Default Time Limit",
                    size=FONT_MD,
                    weight=ft.FontWeight.W_600,
                    font_family="Outfit",
                ),
                ft.Dropdown(
                    value=state.timelimit or "",
                    options=[
                        ft.dropdown.Option(o["key"], o["label"])
                        for o in TIMELIMIT_OPTIONS
                    ],
                    on_select=lambda e: page.run_task(
                        set_fn, "timelimit", e.control.value
                    ),
                    filled=True,
                    border_radius=BORDER_RADIUS_MD,
                ),
            ],
            spacing=12,
        ),
        page=page,
    )
