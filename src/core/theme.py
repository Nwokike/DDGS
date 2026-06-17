"""Application theme."""

from __future__ import annotations

import flet as ft
from core.tokens import (
    FONT_XS,
    FONT_SM,
    FONT_MD,
    FONT_LG,
    FONT_XL,
    FONT_XXL,
    FONT_XXXL,
    SPACING_SM,
    SPACING_MD,
    SPACING_LG,
    BORDER_RADIUS_MD,
    BORDER_RADIUS_LG,
    BORDER_RADIUS_FULL,
)


class AppColors:
    """Color palette."""

    PRIMARY = "#1A73E8"
    PRIMARY_DARK = "#1557B0"
    PRIMARY_LIGHT = "#E8F0FE"
    SECONDARY = "#34A853"
    ACCENT = "#EA4335"
    WARNING = "#FBBC04"
    ERROR = "#EA4335"
    SUCCESS = "#34A853"

    SURFACE = ft.Colors.SURFACE
    BACKGROUND = ft.Colors.SURFACE_CONTAINER_LOWEST
    ON_SURFACE = ft.Colors.ON_SURFACE
    ON_BACKGROUND = ft.Colors.ON_SURFACE
    OUTLINE = ft.Colors.OUTLINE
    OUTLINE_VARIANT = ft.Colors.OUTLINE_VARIANT

    @classmethod
    def with_opacity(cls, opacity: float, color: str) -> str:
        """Create color with opacity."""
        return ft.Colors.with_opacity(opacity, color)


class AppTheme:
    """Application theme builder."""

    @staticmethod
    def get_light_theme() -> ft.Theme:
        return ft.Theme(
            color_scheme=ft.ColorScheme(
                primary=AppColors.PRIMARY,
                on_primary=ft.Colors.WHITE,
                primary_container=AppColors.PRIMARY_LIGHT,
                on_primary_container=AppColors.PRIMARY_DARK,
                secondary=AppColors.SECONDARY,
                on_secondary=ft.Colors.WHITE,
                surface=AppColors.SURFACE,
                on_surface=AppColors.ON_SURFACE,
                error=AppColors.ERROR,
                on_error=ft.Colors.WHITE,
                outline=AppColors.OUTLINE,
                outline_variant=AppColors.OUTLINE_VARIANT,
            ),
            text_theme=ft.TextTheme(
                display_large=ft.TextStyle(size=FONT_XXXL, weight=ft.FontWeight.BOLD),
                display_medium=ft.TextStyle(size=FONT_XXL, weight=ft.FontWeight.BOLD),
                display_small=ft.TextStyle(size=FONT_XL, weight=ft.FontWeight.W_600),
                headline_large=ft.TextStyle(size=FONT_XXL, weight=ft.FontWeight.W_600),
                headline_medium=ft.TextStyle(size=FONT_XL, weight=ft.FontWeight.W_600),
                headline_small=ft.TextStyle(size=FONT_LG, weight=ft.FontWeight.W_600),
                title_large=ft.TextStyle(size=FONT_LG, weight=ft.FontWeight.W_600),
                title_medium=ft.TextStyle(size=FONT_MD, weight=ft.FontWeight.W_500),
                title_small=ft.TextStyle(size=FONT_SM, weight=ft.FontWeight.W_500),
                body_large=ft.TextStyle(size=FONT_MD),
                body_medium=ft.TextStyle(size=FONT_MD),
                body_small=ft.TextStyle(size=FONT_SM),
                label_large=ft.TextStyle(size=FONT_MD, weight=ft.FontWeight.W_500),
                label_medium=ft.TextStyle(size=FONT_SM, weight=ft.FontWeight.W_500),
                label_small=ft.TextStyle(size=FONT_XS, weight=ft.FontWeight.W_500),
            ),
            filled_button_theme=ft.ButtonStyle(
                shape=ft.RoundedRectangleBorder(radius=BORDER_RADIUS_FULL),
                padding=ft.Padding(
                    left=SPACING_LG, top=SPACING_MD, right=SPACING_LG, bottom=SPACING_MD
                ),
                text_style=ft.TextStyle(size=FONT_MD, weight=ft.FontWeight.W_600),
                bgcolor=AppColors.PRIMARY,
                color=ft.Colors.WHITE,
            ),
            outlined_button_theme=ft.ButtonStyle(
                shape=ft.RoundedRectangleBorder(radius=BORDER_RADIUS_FULL),
                padding=ft.Padding(
                    left=SPACING_LG, top=SPACING_MD, right=SPACING_LG, bottom=SPACING_MD
                ),
                text_style=ft.TextStyle(size=FONT_MD, weight=ft.FontWeight.W_500),
                side=ft.BorderSide(1, AppColors.OUTLINE),
            ),
            text_button_theme=ft.ButtonStyle(
                shape=ft.RoundedRectangleBorder(radius=BORDER_RADIUS_MD),
                padding=ft.Padding(
                    left=SPACING_MD, top=SPACING_SM, right=SPACING_MD, bottom=SPACING_SM
                ),
                text_style=ft.TextStyle(size=FONT_SM, weight=ft.FontWeight.W_500),
            ),
            card_theme=ft.CardTheme(
                elevation=1,
                shape=ft.RoundedRectangleBorder(radius=BORDER_RADIUS_LG),
                color=AppColors.SURFACE,
            ),
        )

    @staticmethod
    def get_dark_theme() -> ft.Theme:
        return ft.Theme(
            color_scheme=ft.ColorScheme(
                primary="#8AB4F8",
                on_primary=ft.Colors.BLACK,
                primary_container="#1A73E8",
                on_primary_container=ft.Colors.WHITE,
                secondary="#81C995",
                on_secondary=ft.Colors.BLACK,
                surface=ft.Colors.SURFACE_CONTAINER,
                on_surface=ft.Colors.ON_SURFACE,
                error="#F28B82",
                on_error=ft.Colors.BLACK,
                outline=ft.Colors.OUTLINE,
                outline_variant=ft.Colors.OUTLINE_VARIANT,
            ),
            text_theme=ft.TextTheme(
                display_large=ft.TextStyle(size=FONT_XXXL, weight=ft.FontWeight.BOLD),
                display_medium=ft.TextStyle(size=FONT_XXL, weight=ft.FontWeight.BOLD),
                display_small=ft.TextStyle(size=FONT_XL, weight=ft.FontWeight.W_600),
                headline_large=ft.TextStyle(size=FONT_XXL, weight=ft.FontWeight.W_600),
                headline_medium=ft.TextStyle(size=FONT_XL, weight=ft.FontWeight.W_600),
                headline_small=ft.TextStyle(size=FONT_LG, weight=ft.FontWeight.W_600),
                title_large=ft.TextStyle(size=FONT_LG, weight=ft.FontWeight.W_600),
                title_medium=ft.TextStyle(size=FONT_MD, weight=ft.FontWeight.W_500),
                title_small=ft.TextStyle(size=FONT_SM, weight=ft.FontWeight.W_500),
                body_large=ft.TextStyle(size=FONT_MD),
                body_medium=ft.TextStyle(size=FONT_MD),
                body_small=ft.TextStyle(size=FONT_SM),
                label_large=ft.TextStyle(size=FONT_MD, weight=ft.FontWeight.W_600),
                label_medium=ft.TextStyle(size=FONT_SM, weight=ft.FontWeight.W_500),
                label_small=ft.TextStyle(size=FONT_XS, weight=ft.FontWeight.W_500),
            ),
            filled_button_theme=ft.ButtonStyle(
                shape=ft.RoundedRectangleBorder(radius=BORDER_RADIUS_FULL),
                padding=ft.Padding(
                    left=SPACING_LG, top=SPACING_MD, right=SPACING_LG, bottom=SPACING_MD
                ),
                text_style=ft.TextStyle(size=FONT_MD, weight=ft.FontWeight.W_600),
                bgcolor="#8AB4F8",
                color=ft.Colors.BLACK,
            ),
            outlined_button_theme=ft.ButtonStyle(
                shape=ft.RoundedRectangleBorder(radius=BORDER_RADIUS_FULL),
                padding=ft.Padding(
                    left=SPACING_LG, top=SPACING_MD, right=SPACING_LG, bottom=SPACING_MD
                ),
                text_style=ft.TextStyle(size=FONT_MD, weight=ft.FontWeight.W_500),
                side=ft.BorderSide(1, ft.Colors.OUTLINE),
            ),
            text_button_theme=ft.ButtonStyle(
                shape=ft.RoundedRectangleBorder(radius=BORDER_RADIUS_MD),
                padding=ft.Padding(
                    left=SPACING_MD, top=SPACING_SM, right=SPACING_MD, bottom=SPACING_SM
                ),
                text_style=ft.TextStyle(size=FONT_SM, weight=ft.FontWeight.W_500),
            ),
            card_theme=ft.CardTheme(
                elevation=1,
                shape=ft.RoundedRectangleBorder(radius=BORDER_RADIUS_LG),
                color=ft.Colors.SURFACE_CONTAINER,
            ),
        )
