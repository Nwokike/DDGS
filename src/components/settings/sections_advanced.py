from __future__ import annotations

from collections.abc import Callable

import flet as ft

from core.constants import (
    BACKEND_OPTIONS_TEXT,
    EXTRACT_FORMATS,
    VIDEO_QUALITY_OPTIONS,
)
from core.state import state
from core.theme import AppColors, AppStyles
from core.tokens import BORDER_RADIUS_MD, FONT_MD, FONT_SM, FONT_XS, SPACING_SM


def build_backends_section(page: ft.Page, set_fn: Callable) -> ft.Container:
    return AppStyles.section_card(
        "Search Backends",
        ft.Icons.TRAVEL_EXPLORE_ROUNDED,
        ft.Column(
            [
                ft.Text(
                    "Fallback Search Backend",
                    size=FONT_MD,
                    weight=ft.FontWeight.W_600,
                    font_family="Outfit",
                ),
                ft.Dropdown(
                    value=state.backend or "auto",
                    options=[
                        ft.dropdown.Option(b["key"], b["label"])
                        for b in BACKEND_OPTIONS_TEXT
                    ],
                    on_select=lambda e: page.run_task(
                        set_fn, "backend", e.control.value
                    ),
                    filled=True,
                    border_radius=BORDER_RADIUS_MD,
                ),
            ],
            spacing=10,
        ),
        page=page,
    )


def build_extraction_section(page: ft.Page, set_fn: Callable) -> ft.Container:
    return AppStyles.section_card(
        "Content Extraction",
        ft.Icons.DOWNLOAD_ROUNDED,
        ft.Column(
            [
                ft.Text(
                    "URL Extraction Format",
                    size=FONT_MD,
                    weight=ft.FontWeight.W_600,
                    font_family="Outfit",
                ),
                ft.Dropdown(
                    value=state.extract_format,
                    options=[
                        ft.dropdown.Option(f["key"], f["label"])
                        for f in EXTRACT_FORMATS
                    ],
                    on_select=lambda e: page.run_task(
                        set_fn, "extract_format", e.control.value
                    ),
                    filled=True,
                    border_radius=BORDER_RADIUS_MD,
                ),
            ],
            spacing=10,
        ),
        page=page,
    )


def build_downloads_section(page: ft.Page, set_fn: Callable) -> ft.Container:
    return AppStyles.section_card(
        "Downloads",
        ft.Icons.DOWNLOAD_ROUNDED,
        ft.Column(
            [
                ft.Text(
                    "Video Quality",
                    size=FONT_MD,
                    weight=ft.FontWeight.W_600,
                    font_family="Outfit",
                ),
                ft.Dropdown(
                    value=state.video_quality,
                    options=[
                        ft.dropdown.Option(q["key"], q["label"])
                        for q in VIDEO_QUALITY_OPTIONS
                    ],
                    on_select=lambda e: page.run_task(
                        set_fn, "video_quality", e.control.value
                    ),
                    filled=True,
                    border_radius=BORDER_RADIUS_MD,
                ),
                ft.Text(
                    "Preferred quality when downloading videos. "
                    "YouTube is resolved to a direct file; other sources are fetched as-is.",
                    size=FONT_XS,
                    color=ft.Colors.ON_SURFACE_VARIANT,
                ),
            ],
            spacing=10,
        ),
        page=page,
    )


def build_connection_section(page: ft.Page, set_fn: Callable) -> ft.Container:
    return AppStyles.section_card(
        "Connection & Proxy",
        ft.Icons.WIFI_ROUNDED,
        ft.Column(
            [
                ft.Text(
                    "HTTP/SOCKS5 Proxy",
                    size=FONT_MD,
                    weight=ft.FontWeight.W_600,
                    font_family="Outfit",
                ),
                ft.TextField(
                    value=state.proxy,
                    hint_text="e.g. socks5://127.0.0.1:9050",
                    on_change=lambda e: page.run_task(set_fn, "proxy", e.control.value),
                    border_radius=BORDER_RADIUS_MD,
                    filled=True,
                ),
                ft.Row(
                    [
                        ft.Text(
                            "Verify TLS/SSL Certificates",
                            size=FONT_MD,
                            weight=ft.FontWeight.W_500,
                            expand=True,
                        ),
                        ft.Switch(
                            value=state.verify_ssl,
                            active_color=AppColors.PRIMARY,
                            on_change=lambda e: page.run_task(
                                set_fn, "verify_ssl", e.control.value
                            ),
                        ),
                    ],
                    alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                ),
            ],
            spacing=12,
        ),
        page=page,
    )


def build_performance_section(page: ft.Page, set_fn: Callable) -> ft.Container:
    return AppStyles.section_card(
        "Performance",
        ft.Icons.SPEED_ROUNDED,
        ft.Column(
            [
                ft.Text(
                    "Maximum Worker Threads",
                    size=FONT_MD,
                    weight=ft.FontWeight.W_600,
                    font_family="Outfit",
                ),
                ft.Text(
                    "0 = automatic defaults",
                    size=FONT_XS,
                    color=ft.Colors.ON_SURFACE_VARIANT,
                ),
                ft.Row(
                    [
                        ft.Slider(
                            value=float(state.threads),
                            min=0,
                            max=20,
                            divisions=20,
                            label="{value}",
                            expand=True,
                            active_color=AppColors.PRIMARY,
                            on_change_end=lambda e: page.run_task(
                                set_fn, "threads", int(e.control.value)
                            ),
                        ),
                        ft.Text(
                            f"{state.threads}",
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
            ],
            spacing=12,
        ),
        page=page,
    )
