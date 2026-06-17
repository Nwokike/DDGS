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
)


class AppColors:
    PRIMARY = "#4F46E5"
    SECONDARY = "#4338CA"
    TERTIARY = "#7C3AED"
    ACCENT = "#F59E0B"
    SUCCESS = "#10B981"
    WARNING = "#F59E0B"
    ERROR = "#EF4444"

    DARK_BG = "#000000"
    DARK_SURFACE = "#0A0A0A"
    DARK_CARD = "#121212"
    DARK_TEXT = "#FFFFFF"
    DARK_TEXT_DIM = "#A0A0A0"

    LIGHT_BG = "#FFFFFF"
    LIGHT_SURFACE = "#F8F8F8"
    LIGHT_CARD = "#FFFFFF"
    LIGHT_TEXT = "#000000"
    LIGHT_TEXT_DIM = "#666666"


class AppStyles:
    RADIUS_SMALL = 8
    RADIUS = 12
    RADIUS_LARGE = 20

    PADDING_SMALL = 8
    PADDING = 16
    PADDING_LARGE = 24

    @staticmethod
    def section_card(title: str, icon: str, content: ft.Control) -> ft.Container:
        return ft.Container(
            content=ft.Column(
                [
                    ft.Row(
                        [
                            ft.Icon(icon, color=AppColors.PRIMARY, size=20),
                            ft.Text(title, size=15, weight=ft.FontWeight.W_600),
                        ],
                        spacing=8,
                    ),
                    ft.Divider(
                        height=1,
                        color=ft.Colors.with_opacity(0.1, ft.Colors.ON_SURFACE),
                    ),
                    content,
                ],
                spacing=12,
            ),
            padding=16,
            border_radius=AppStyles.RADIUS,
            bgcolor=ft.Colors.SURFACE_CONTAINER_HIGHEST,
            border=ft.Border.all(1, ft.Colors.with_opacity(0.05, ft.Colors.ON_SURFACE)),
        )

    @staticmethod
    def glass_card(content: ft.Control, blur_sigma: int = 10):
        return ft.Container(
            content=content,
            bgcolor=ft.Colors.with_opacity(0.02, ft.Colors.WHITE),
            blur=ft.Blur(blur_sigma, blur_sigma, ft.BlurTileMode.MIRROR),
            border=ft.Border.all(1, ft.Colors.with_opacity(0.05, ft.Colors.WHITE)),
            border_radius=AppStyles.RADIUS,
        )

    @staticmethod
    def brand_gradient():
        return ft.LinearGradient(
            begin=ft.Alignment.TOP_CENTER,
            end=ft.Alignment.BOTTOM_CENTER,
            colors=[
                ft.Colors.with_opacity(0.05, AppColors.PRIMARY),
                ft.Colors.TRANSPARENT,
            ],
        )


class AppTheme:
    @staticmethod
    def get_light_theme() -> ft.Theme:
        return ft.Theme(
            color_scheme=ft.ColorScheme(
                primary=AppColors.PRIMARY,
                on_primary=ft.Colors.WHITE,
                primary_container=ft.Colors.with_opacity(0.12, AppColors.PRIMARY),
                on_primary_container=AppColors.PRIMARY,
                secondary=AppColors.SECONDARY,
                on_secondary=ft.Colors.WHITE,
                surface=AppColors.LIGHT_BG,
                on_surface=AppColors.LIGHT_TEXT,
                surface_container=AppColors.LIGHT_SURFACE,
                surface_container_highest=AppColors.LIGHT_CARD,
                on_surface_variant=AppColors.LIGHT_TEXT_DIM,
                error=AppColors.ERROR,
                on_error=ft.Colors.WHITE,
                outline=ft.Colors.with_opacity(0.2, AppColors.LIGHT_TEXT),
                outline_variant=ft.Colors.with_opacity(0.1, AppColors.LIGHT_TEXT),
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
        )

    @staticmethod
    def get_dark_theme() -> ft.Theme:
        return ft.Theme(
            color_scheme=ft.ColorScheme(
                primary=ft.Colors.with_opacity(0.9, "#8AB4F8"),
                on_primary=ft.Colors.BLACK,
                primary_container=ft.Colors.with_opacity(0.15, "#8AB4F8"),
                on_primary_container="#8AB4F8",
                secondary="#81C995",
                on_secondary=ft.Colors.BLACK,
                surface=AppColors.DARK_BG,
                on_surface=AppColors.DARK_TEXT,
                surface_container=AppColors.DARK_SURFACE,
                surface_container_highest=AppColors.DARK_CARD,
                on_surface_variant=AppColors.DARK_TEXT_DIM,
                error="#F28B82",
                on_error=ft.Colors.BLACK,
                outline=ft.Colors.with_opacity(0.3, AppColors.DARK_TEXT),
                outline_variant=ft.Colors.with_opacity(0.15, AppColors.DARK_TEXT),
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
        )
