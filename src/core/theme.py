from __future__ import annotations

import flet as ft


class AppColors:
    # Brand Orange Palette
    PRIMARY = "#B33A1D"  # Premium Dark Orange/Terracotta
    PRIMARY_LIGHT = "#DE5833"  # Standard Brand Orange
    PRIMARY_DARK = "#8E250F"  # Deep Pressed Orange
    ACCENT = "#B33A1D"  # Neutral accent (avoid color mixing)

    SUCCESS = "#2E7D32"  # Clean Material Green
    WARNING = "#F9A825"  # Amber Gold
    ERROR = "#D32F2F"  # Red

    # Premium Neutral Slate Dark Mode Palette
    DARK_BG_1 = "#0F1114"  # Deep Slate-Black Background
    DARK_BG_2 = "#121518"  # Slate Surface
    DARK_SURFACE = "#1A1D22"  # Card Background
    DARK_SURFACE_2 = "#252A30"  # Dialog Background
    DARK_BORDER = "#2E3339"  # Outline / Divider Border
    DARK_TEXT = "#ECEFF1"  # Primary Text
    DARK_TEXT_DIM = "#90A4AE"  # Secondary text

    # Premium Neutral Slate Light Mode Palette
    LIGHT_BG = "#FAFAFA"  # Pure clean warm background
    LIGHT_SURFACE = "#FFFFFF"  # Pure White Cards
    LIGHT_SURFACE_2 = "#F5F5F5"  # Soft divider focus surface
    LIGHT_BORDER = "#E0E0E0"  # Soft divider border
    LIGHT_TEXT = "#1A1A2E"  # Deep Charcoal slate body text
    LIGHT_TEXT_DIM = "#757575"  # Secondary gray text

    @staticmethod
    def _resolve_page(page: ft.Page | None) -> ft.Page | None:
        """Return the active page, falling back to ``flet.context.page``."""
        if page is not None:
            return page
        try:
            from flet import context as flet_context

            return flet_context.page
        except Exception:
            return None

    @staticmethod
    def get_bg(page: ft.Page | None = None) -> str:
        resolved = AppColors._resolve_page(page)
        is_dark = is_dark_mode(resolved)
        return AppColors.DARK_BG_1 if is_dark else AppColors.LIGHT_BG

    @staticmethod
    def get_surface(page: ft.Page | None = None) -> str:
        resolved = AppColors._resolve_page(page)
        is_dark = is_dark_mode(resolved)
        return AppColors.DARK_SURFACE if is_dark else AppColors.LIGHT_SURFACE

    @staticmethod
    def get_surface_2(page: ft.Page | None = None) -> str:
        resolved = AppColors._resolve_page(page)
        is_dark = is_dark_mode(resolved)
        return AppColors.DARK_SURFACE_2 if is_dark else AppColors.LIGHT_SURFACE_2

    @staticmethod
    def get_border(page: ft.Page | None = None) -> str:
        resolved = AppColors._resolve_page(page)
        is_dark = is_dark_mode(resolved)
        return AppColors.DARK_BORDER if is_dark else AppColors.LIGHT_BORDER

    @staticmethod
    def get_text(page: ft.Page | None = None) -> str:
        resolved = AppColors._resolve_page(page)
        is_dark = is_dark_mode(resolved)
        return AppColors.DARK_TEXT if is_dark else AppColors.LIGHT_TEXT

    @staticmethod
    def get_text_dim(page: ft.Page | None = None) -> str:
        resolved = AppColors._resolve_page(page)
        is_dark = is_dark_mode(resolved)
        return AppColors.DARK_TEXT_DIM if is_dark else AppColors.LIGHT_TEXT_DIM


def is_dark_mode(page: ft.Page | None) -> bool:
    """Check if the page is currently in dark mode (explicit or system).

    When ``page`` is ``None``, attempts to resolve the active Flet page via
    ``flet.context.page``. If that fails, defaults to dark mode.
    """
    if page is None:
        try:
            from flet import context as flet_context

            page = flet_context.page
        except Exception:
            return True  # fallback to dark
    if page is None:
        return True
    return page.theme_mode == ft.ThemeMode.DARK or (
        page.theme_mode == ft.ThemeMode.SYSTEM
        and page.platform_brightness == ft.Brightness.DARK
    )


# ── Glassmorphism Settings (Matching SpanInsight) ─────────────────
GLASS_BG = ft.Colors.with_opacity(0.05, ft.Colors.WHITE)
GLASS_BORDER_COLOR = ft.Colors.with_opacity(0.10, ft.Colors.WHITE)

LIGHT_GLASS_BG = ft.Colors.with_opacity(0.04, ft.Colors.BLACK)
LIGHT_GLASS_BORDER = ft.Colors.with_opacity(0.08, ft.Colors.BLACK)


def adaptive_glass_bg(page: ft.Page | None = None) -> str:
    """Return card background color appropriate for current theme."""
    if page and not is_dark_mode(page):
        return LIGHT_GLASS_BG
    return GLASS_BG


def adaptive_glass_border(page: ft.Page | None = None) -> str:
    """Return card border color appropriate for current theme."""
    if page and not is_dark_mode(page):
        return LIGHT_GLASS_BORDER
    return GLASS_BORDER_COLOR


class AppStyles:
    RADIUS_SMALL = 8
    RADIUS = 12
    RADIUS_LARGE = 20

    PADDING_SMALL = 8
    PADDING = 16
    PADDING_LARGE = 24

    @staticmethod
    def section_card(
        title: str, icon: str, content: ft.Control, page: ft.Page | None = None
    ) -> ft.Container:
        """Frosted card section matching SpanInsight/Sherlock styles."""
        is_dark = is_dark_mode(page)
        border_color = AppColors.DARK_BORDER if is_dark else AppColors.LIGHT_BORDER
        bg_color = AppColors.DARK_SURFACE if is_dark else AppColors.LIGHT_SURFACE

        return ft.Container(
            content=ft.Column(
                [
                    ft.Row(
                        [
                            ft.Icon(icon, color=AppColors.PRIMARY, size=18),
                            ft.Text(
                                title,
                                size=14,
                                weight=ft.FontWeight.W_600,
                                font_family="Outfit",
                            ),
                        ],
                        spacing=10,
                    ),
                    ft.Divider(
                        height=1,
                        color=ft.Colors.with_opacity(0.08, ft.Colors.ON_SURFACE),
                    ),
                    content,
                ],
                spacing=12,
            ),
            padding=16,
            border_radius=AppStyles.RADIUS,
            bgcolor=bg_color,
            border=ft.Border.all(1, border_color),
        )

    @staticmethod
    def glass_card(content: ft.Control, page: ft.Page | None = None) -> ft.Container:
        """Frost glass effect for premium container layouts."""
        return ft.Container(
            content=content,
            bgcolor=adaptive_glass_bg(page),
            border=ft.Border.all(1, adaptive_glass_border(page)),
            border_radius=AppStyles.RADIUS,
        )

    @staticmethod
    def brand_gradient(page: ft.Page | None = None):
        """Clean neutral background gradient matching SpanInsight."""
        is_dark = is_dark_mode(page)
        if is_dark:
            return ft.LinearGradient(
                begin=ft.Alignment.TOP_CENTER,
                end=ft.Alignment.BOTTOM_CENTER,
                colors=[AppColors.DARK_BG_1, AppColors.DARK_BG_2],
            )
        else:
            return ft.LinearGradient(
                begin=ft.Alignment.TOP_CENTER,
                end=ft.Alignment.BOTTOM_CENTER,
                colors=["#F5F5F5", AppColors.LIGHT_BG],
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
                secondary=AppColors.ACCENT,
                on_secondary=ft.Colors.WHITE,
                surface=AppColors.LIGHT_BG,
                on_surface=AppColors.LIGHT_TEXT,
                surface_container=AppColors.LIGHT_SURFACE,
                surface_container_highest=AppColors.LIGHT_SURFACE,
                on_surface_variant=AppColors.LIGHT_TEXT_DIM,
                error=AppColors.ERROR,
                on_error=ft.Colors.WHITE,
                outline=AppColors.LIGHT_BORDER,
                outline_variant=AppColors.LIGHT_SURFACE_2,
            ),
            font_family="Outfit",
            visual_density=ft.VisualDensity.COMFORTABLE,
        )

    @staticmethod
    def get_dark_theme() -> ft.Theme:
        return ft.Theme(
            color_scheme=ft.ColorScheme(
                primary=AppColors.PRIMARY,
                on_primary=ft.Colors.WHITE,
                primary_container=ft.Colors.with_opacity(0.15, AppColors.PRIMARY_LIGHT),
                on_primary_container=AppColors.PRIMARY_LIGHT,
                secondary=AppColors.ACCENT,
                on_secondary=ft.Colors.BLACK,
                surface=AppColors.DARK_BG_1,
                on_surface=AppColors.DARK_TEXT,
                surface_container=AppColors.DARK_SURFACE,
                surface_container_highest=AppColors.DARK_SURFACE,
                on_surface_variant=AppColors.DARK_TEXT_DIM,
                error=AppColors.ERROR,
                on_error=ft.Colors.WHITE,
                outline=AppColors.DARK_BORDER,
                outline_variant=AppColors.DARK_SURFACE_2,
            ),
            font_family="Outfit",
            visual_density=ft.VisualDensity.COMFORTABLE,
        )
