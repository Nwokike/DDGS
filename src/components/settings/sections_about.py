from __future__ import annotations

from collections.abc import Callable

import flet as ft

from components.settings.version import _APP_VERSION
from core.state import state
from core.theme import AppColors, AppStyles
from core.tokens import BORDER_RADIUS_MD, FONT_LG, FONT_MD, FONT_SM, FONT_XS, SPACING_SM
from core.utils import in_memory_log_handler, logger


def build_logs_dialog(page: ft.Page):
    logs = (
        "\n".join(in_memory_log_handler.records)
        if in_memory_log_handler.records
        else "No activity recorded yet. Perform a search to see live output."
    )

    log_text_control = ft.Text(
        logs,
        font_family="Courier New",
        size=11,
        color="#A6E22E",
        selectable=True,
    )

    async def copy_logs(e=None):
        try:
            await page.clipboard.set(logs)
            snack = ft.SnackBar(ft.Text("Activity log copied to clipboard!"))
            snack.open = True
            page.show_dialog(snack)
            page.update()
        except (
            ValueError,
            TypeError,
            AttributeError,
            OSError,
            RuntimeError,
        ) as ex:
            logger.error(f"Copy logs failed: {ex}")

    return ft.AlertDialog(
        title=ft.Row(
            [
                ft.Icon(
                    ft.Icons.TERMINAL_ROUNDED,
                    size=22,
                    color=AppColors.PRIMARY,
                ),
                ft.Text(
                    "Live Activity",
                    font_family="Outfit",
                    size=FONT_LG,
                    weight=ft.FontWeight.BOLD,
                ),
            ],
            spacing=8,
        ),
        content=ft.Container(
            content=ft.Column(
                [
                    ft.Text(
                        "Real-time log of every search, connection, and response. "
                        "Copy and share if you encounter errors.",
                        size=FONT_XS,
                        color=ft.Colors.ON_SURFACE_VARIANT,
                    ),
                    ft.Container(
                        content=ft.Column(
                            [log_text_control], scroll=ft.ScrollMode.AUTO
                        ),
                        padding=12,
                        bgcolor="#0D0D0D",
                        border=ft.Border.all(
                            1, ft.Colors.with_opacity(0.15, ft.Colors.WHITE)
                        ),
                        border_radius=8,
                        expand=True,
                    ),
                ],
                spacing=8,
            ),
            width=page.window.width * 0.9 if page.window.width else 450,
            height=500,
        ),
        actions=[
            ft.IconButton(
                icon=ft.Icons.COPY_ROUNDED,
                tooltip="Copy to Clipboard",
                on_click=lambda e: page.run_task(copy_logs),
            ),
            ft.TextButton("Close", on_click=lambda e: page.pop_dialog()),
        ],
        actions_alignment=ft.MainAxisAlignment.END,
    )


def build_logs_section(page: ft.Page) -> ft.Container:
    return AppStyles.section_card(
        "Activity Terminal",
        ft.Icons.TERMINAL_ROUNDED,
        ft.Column(
            [
                ft.Text(
                    "Live Activity Terminal",
                    size=FONT_MD,
                    weight=ft.FontWeight.W_600,
                    font_family="Outfit",
                ),
                ft.Text(
                    "View real-time search activity, connection logs, and errors. "
                    "Useful for troubleshooting on mobile.",
                    size=FONT_XS,
                    color=ft.Colors.ON_SURFACE_VARIANT,
                ),
                ft.FilledButton(
                    "Open Terminal",
                    icon=ft.Icons.TERMINAL_ROUNDED,
                    on_click=lambda e: page.show_dialog(build_logs_dialog(page)),
                    style=ft.ButtonStyle(
                        bgcolor=AppColors.PRIMARY,
                        color=ft.Colors.WHITE,
                        shape=ft.RoundedRectangleBorder(radius=BORDER_RADIUS_MD),
                    ),
                ),
            ],
            spacing=10,
        ),
        page=page,
    )


def build_storage_section(
    page: ft.Page, show_clear_dialog_fn: Callable
) -> ft.Container:
    return AppStyles.section_card(
        "Local Storage Data",
        ft.Icons.STORAGE_ROUNDED,
        ft.Column(
            [
                ft.Text(
                    f"{len(state.search_history)} local history queries stored",
                    size=FONT_SM,
                    color=ft.Colors.ON_SURFACE_VARIANT,
                ),
                ft.OutlinedButton(
                    "Clear Cache History",
                    icon=ft.Icons.DELETE_SWEEP_ROUNDED,
                    on_click=show_clear_dialog_fn,
                    style=ft.ButtonStyle(
                        color=AppColors.ERROR,
                        side=ft.BorderSide(1, AppColors.ERROR),
                        shape=ft.RoundedRectangleBorder(radius=BORDER_RADIUS_MD),
                    ),
                ),
            ],
            spacing=12,
        ),
        page=page,
    )


def build_about_section(
    page: ft.Page, launch_privacy_fn: Callable, launch_terms_fn: Callable
) -> ft.Container:
    return AppStyles.section_card(
        "About Info",
        ft.Icons.INFO_ROUNDED,
        ft.Column(
            [
                ft.Container(
                    content=ft.Image(
                        src="icon.png",
                        width=96,
                        height=96,
                        fit=ft.BoxFit.CONTAIN,
                    ),
                    alignment=ft.Alignment.CENTER,
                    margin=ft.Margin(0, 0, 0, SPACING_SM),
                ),
                ft.Row(
                    [
                        ft.Text("Version", size=FONT_SM, font_family="Outfit"),
                        ft.Text(
                            _APP_VERSION,
                            size=FONT_SM,
                            color=ft.Colors.ON_SURFACE_VARIANT,
                        ),
                    ],
                    alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                ),
                ft.Row(
                    [
                        ft.Text("Built with", size=FONT_SM, font_family="Outfit"),
                        ft.Text(
                            "ddgs (MIT) + primp",
                            size=FONT_SM,
                            color=ft.Colors.ON_SURFACE_VARIANT,
                        ),
                    ],
                    alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                ),
                ft.Divider(
                    height=1,
                    color=ft.Colors.with_opacity(0.04, ft.Colors.ON_SURFACE),
                ),
                ft.Row(
                    [
                        ft.TextButton(
                            "Privacy Policy",
                            icon=ft.Icons.PRIVACY_TIP_ROUNDED,
                            style=ft.ButtonStyle(color=AppColors.PRIMARY),
                            on_click=lambda e: page.run_task(launch_privacy_fn),
                        ),
                        ft.TextButton(
                            "Terms of Service",
                            icon=ft.Icons.GAVEL_ROUNDED,
                            style=ft.ButtonStyle(color=AppColors.PRIMARY),
                            on_click=lambda e: page.run_task(launch_terms_fn),
                        ),
                    ],
                    alignment=ft.MainAxisAlignment.SPACE_EVENLY,
                ),
            ],
            spacing=8,
        ),
        page=page,
    )
