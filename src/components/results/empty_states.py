from __future__ import annotations

from collections.abc import Callable

import flet as ft

from core import tokens
from core.theme import AppColors
from core.utils import classify_error


def build_loading_box(is_running: bool) -> ft.Container:
    return ft.Container(
        content=ft.Column(
            [
                ft.ProgressBar(
                    color=AppColors.PRIMARY,
                    bgcolor=ft.Colors.with_opacity(0.12, AppColors.PRIMARY),
                ),
                ft.Text(
                    "Searching global servers...",
                    size=tokens.FONT_SM,
                    color=ft.Colors.ON_SURFACE_VARIANT,
                    font_family="Outfit",
                    text_align=ft.TextAlign.CENTER,
                ),
            ],
            spacing=tokens.SPACE_SM,
            horizontal_alignment=ft.CrossAxisAlignment.CENTER,
        ),
        padding=ft.Padding(
            tokens.SPACE_LG, tokens.SPACE_LG, tokens.SPACE_LG, tokens.SPACE_LG
        ),
        visible=is_running,
    )


def build_error_box(
    error: str | None,
    query: str,
    is_running: bool,
    is_video_rate_limit: bool,
    on_restart: Callable,
) -> ft.Container:
    category = classify_error(error)

    if category == "offline":
        err_icon = ft.Icons.WIFI_OFF_ROUNDED
        err_title = "No Internet Connection"
        err_desc = (
            "Unable to reach search servers. Please check your Wi-Fi or mobile data "
            "connection and try again."
        )
    elif category == "server":
        err_icon = ft.Icons.CLOUD_OFF_ROUNDED
        err_title = "Server Unavailable"
        err_desc = (
            f"The search server returned a non-200 error ({error}). "
            "Please try again in a few moments."
        )
    else:
        err_icon = ft.Icons.ERROR_OUTLINE_ROUNDED
        err_title = "Connection Failed"
        err_desc = error or "Unknown protocol error. Check settings and proxies."

    return ft.Container(
        content=ft.Column(
            [
                ft.Icon(
                    err_icon,
                    size=tokens.ICON_LG,
                    color=AppColors.ERROR,
                ),
                ft.Text(
                    err_title,
                    size=tokens.FONT_LG,
                    weight=ft.FontWeight.BOLD,
                    color=AppColors.ERROR,
                    font_family="Outfit",
                ),
                ft.Text(
                    err_desc,
                    size=tokens.FONT_SM,
                    text_align=ft.TextAlign.CENTER,
                    style=ft.TextStyle(height=1.4),
                ),
                ft.Container(height=12),
                ft.FilledButton(
                    content=ft.Row(
                        [
                            ft.Icon(
                                ft.Icons.REFRESH_ROUNDED,
                                size=tokens.ICON_SM,
                                color=ft.Colors.WHITE,
                            ),
                            ft.Text(
                                "Retry Search",
                                size=tokens.FONT_SM,
                                weight=ft.FontWeight.W_600,
                                color=ft.Colors.WHITE,
                                font_family="Outfit",
                            ),
                        ],
                        spacing=6,
                        tight=True,
                    ),
                    on_click=lambda _: on_restart(query),
                    style=ft.ButtonStyle(
                        shape=ft.RoundedRectangleBorder(radius=tokens.RADIUS_MD),
                        bgcolor=AppColors.PRIMARY,
                        padding=ft.Padding(20, 12, 20, 12),
                    ),
                ),
            ],
            spacing=tokens.SPACE_MD,
            horizontal_alignment=ft.CrossAxisAlignment.CENTER,
        ),
        padding=ft.Padding(32, 48, 32, 48),
        visible=bool(error) and not is_running and not is_video_rate_limit,
    )


def build_video_rate_limit_box(query: str, on_restart: Callable) -> ft.Container:
    return ft.Container(
        content=ft.Column(
            [
                ft.Icon(
                    ft.Icons.SCHEDULE_ROUNDED,
                    size=tokens.ICON_LG,
                    color=AppColors.WARNING,
                ),
                ft.Text(
                    "Video Search Rate-Limited",
                    size=tokens.FONT_LG,
                    weight=ft.FontWeight.BOLD,
                    color=AppColors.WARNING,
                    font_family="Outfit",
                ),
                ft.Text(
                    "DuckDuckGo strictly rate-limits automated video search queries. "
                    "When rate-limited, zero video results are returned.\n\n"
                    "Please try again later or switch to Web search.",
                    size=tokens.FONT_SM,
                    text_align=ft.TextAlign.CENTER,
                    style=ft.TextStyle(height=1.4),
                ),
                ft.Container(height=12),
                ft.Row(
                    [
                        ft.FilledButton(
                            content=ft.Row(
                                [
                                    ft.Icon(
                                        ft.Icons.SEARCH_ROUNDED,
                                        size=tokens.ICON_SM,
                                        color=ft.Colors.WHITE,
                                    ),
                                    ft.Text(
                                        "Try Web Search",
                                        size=tokens.FONT_SM,
                                        weight=ft.FontWeight.W_600,
                                        color=ft.Colors.WHITE,
                                        font_family="Outfit",
                                    ),
                                ],
                                spacing=6,
                                tight=True,
                            ),
                            on_click=lambda _: on_restart(query, "text"),
                            style=ft.ButtonStyle(
                                shape=ft.RoundedRectangleBorder(
                                    radius=tokens.RADIUS_MD
                                ),
                                bgcolor=AppColors.PRIMARY,
                                padding=ft.Padding(16, 12, 16, 12),
                            ),
                        ),
                        ft.OutlinedButton(
                            content=ft.Row(
                                [
                                    ft.Icon(
                                        ft.Icons.REFRESH_ROUNDED,
                                        size=tokens.ICON_SM,
                                    ),
                                    ft.Text(
                                        "Retry Video",
                                        size=tokens.FONT_SM,
                                        weight=ft.FontWeight.W_600,
                                        font_family="Outfit",
                                    ),
                                ],
                                spacing=6,
                                tight=True,
                            ),
                            on_click=lambda _: on_restart(query, "videos"),
                            style=ft.ButtonStyle(
                                shape=ft.RoundedRectangleBorder(
                                    radius=tokens.RADIUS_MD
                                ),
                                padding=ft.Padding(16, 12, 16, 12),
                            ),
                        ),
                    ],
                    alignment=ft.MainAxisAlignment.CENTER,
                    spacing=tokens.SPACE_SM,
                ),
            ],
            spacing=tokens.SPACE_MD,
            horizontal_alignment=ft.CrossAxisAlignment.CENTER,
        ),
        padding=ft.Padding(32, 48, 32, 48),
        expand=True,
        alignment=ft.Alignment.CENTER,
    )


def build_empty_results_box() -> ft.Container:
    return ft.Container(
        content=ft.Column(
            [
                ft.Icon(
                    ft.Icons.SEARCH_OFF_ROUNDED,
                    size=tokens.ICON_LG,
                    color=ft.Colors.ON_SURFACE_VARIANT,
                ),
                ft.Text(
                    "No matches found.",
                    size=tokens.FONT_MD,
                    color=ft.Colors.ON_SURFACE_VARIANT,
                    text_align=ft.TextAlign.CENTER,
                    font_family="Outfit",
                ),
            ],
            horizontal_alignment=ft.CrossAxisAlignment.CENTER,
            spacing=tokens.SPACE_SM,
        ),
        padding=ft.Padding(32, 48, 32, 48),
        expand=True,
        alignment=ft.Alignment.CENTER,
    )
