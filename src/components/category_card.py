from __future__ import annotations

import flet as ft

from core import theme, tokens
from core.theme import AppColors


def _action_card(
    icon: str,
    title: str,
    subtitle: str,
    color: str,
    is_active: bool,
    on_click=None,
    page: ft.Page | None = None,
) -> ft.Container:
    """Build a quick action card matching SpanInsight's layout."""
    border_color = AppColors.PRIMARY if is_active else theme.adaptive_glass_border(page)
    bg_color = (
        ft.Colors.with_opacity(0.12, AppColors.PRIMARY)
        if is_active
        else theme.adaptive_glass_bg(page)
    )

    return ft.Container(
        content=ft.Column(
            controls=[
                ft.Container(
                    content=ft.Icon(icon, size=24, color=color),
                    width=44,
                    height=44,
                    border_radius=12,
                    bgcolor=ft.Colors.with_opacity(0.1, color),
                    alignment=ft.Alignment.CENTER,
                ),
                ft.Text(
                    title,
                    size=12,
                    weight=ft.FontWeight.W_600,
                    font_family="Outfit",
                    max_lines=1,
                    overflow="ellipsis",
                ),
                ft.Text(
                    subtitle,
                    size=9,
                    color=ft.Colors.ON_SURFACE_VARIANT,
                    font_family="Outfit",
                    max_lines=1,
                    overflow="ellipsis",
                ),
            ],
            spacing=4,
            horizontal_alignment=ft.CrossAxisAlignment.CENTER,
        ),
        expand=True,
        padding=12,
        border_radius=16,
        bgcolor=bg_color,
        border=ft.Border.all(1.5 if is_active else 1, border_color),
        on_click=on_click,
        ink=True,
    )


def _feature_card(
    icon: str,
    title: str,
    desc: str,
    color: str,
    on_click=None,
    page: ft.Page | None = None,
) -> ft.Container:
    """Build a feature card row matching SpanInsight's layout."""
    return ft.Container(
        content=ft.Row(
            controls=[
                ft.Container(
                    content=ft.Icon(icon, size=20, color=color),
                    width=38,
                    height=38,
                    border_radius=10,
                    bgcolor=ft.Colors.with_opacity(0.1, color),
                    alignment=ft.Alignment.CENTER,
                ),
                ft.Column(
                    controls=[
                        ft.Text(
                            title,
                            size=tokens.FONT_SM,
                            weight=ft.FontWeight.W_600,
                            font_family="Outfit",
                            max_lines=1,
                            overflow="ellipsis",
                        ),
                        ft.Text(
                            desc,
                            size=tokens.FONT_XS,
                            color=ft.Colors.ON_SURFACE_VARIANT,
                            max_lines=2,
                            overflow="ellipsis",
                            font_family="Outfit",
                        ),
                    ],
                    spacing=2,
                    expand=True,
                ),
            ],
            spacing=tokens.SPACE_MD,
            vertical_alignment="center",
        ),
        padding=12,
        border_radius=12,
        bgcolor=theme.adaptive_glass_bg(page),
        border=ft.Border.all(1, theme.adaptive_glass_border(page)),
        on_click=on_click,
        ink=on_click is not None,
    )


def _step_row(number: str, title: str, desc: str) -> ft.Row:
    """Build a numbered step row matching SpanInsight's layout."""
    return ft.Row(
        controls=[
            ft.Container(
                content=ft.Text(
                    number,
                    size=tokens.FONT_SM,
                    weight=ft.FontWeight.W_700,
                    color=ft.Colors.WHITE,
                    text_align=ft.TextAlign.CENTER,
                    font_family="Outfit",
                ),
                width=26,
                height=26,
                border_radius=13,
                bgcolor=AppColors.PRIMARY,
                alignment=ft.Alignment.CENTER,
            ),
            ft.Column(
                controls=[
                    ft.Text(
                        title,
                        size=tokens.FONT_SM,
                        weight=ft.FontWeight.W_600,
                        font_family="Outfit",
                    ),
                    ft.Text(
                        desc,
                        size=tokens.FONT_XS,
                        color=ft.Colors.ON_SURFACE_VARIANT,
                        font_family="Outfit",
                    ),
                ],
                spacing=tokens.SPACE_XXS,
                expand=True,
            ),
        ],
        spacing=tokens.SPACE_MD,
        vertical_alignment=ft.CrossAxisAlignment.CENTER,
    )
