from __future__ import annotations

from collections.abc import Callable

import flet as ft

from components.settings.version import _APP_VERSION
from core import ui
from core.constants import CONTACT_EMAIL, GITHUB_PROFILE_URL, GITHUB_REPO_URL
from core.state import state
from core.theme import AppColors, AppStyles
from core.tokens import BORDER_RADIUS_MD, FONT_LG, FONT_MD, FONT_SM, FONT_XS, SPACING_SM
from core.utils import in_memory_log_handler
from services.update_service import PLAY_STORE_URL

# Kiri Research Labs on Play (both listings resolve to the same developer
# id; verified live, the name-based URL 404s).
PLAY_DEV_URL = "https://play.google.com/store/apps/dev?id=5797833969564243342"


def _launch(page, url: str) -> None:
    async def _run():
        await ft.UrlLauncher().launch_url(url)

    page.run_task(_run)


def _external_trailing() -> ft.Icon:
    return ft.Icon(
        ft.Icons.OPEN_IN_NEW_ROUNDED,
        size=15,
        color=ft.Colors.ON_SURFACE_VARIANT,
    )


def _more_apps_url(page) -> str:
    # Same KTV split as the rate row: store devices get the Play developer
    # page, desktop gets GitHub where everything else lives.
    return PLAY_DEV_URL if _is_store_device(page) else GITHUB_PROFILE_URL


def _is_store_device(page) -> bool:
    """Phones and TV are the Play audience; desktop has no listing (KTV)."""
    try:
        return page.platform in (
            ft.PagePlatform.ANDROID,
            ft.PagePlatform.IOS,
            ft.PagePlatform.ANDROID_TV,
        )
    except Exception:
        return False


def _rate_url(page) -> str:
    return PLAY_STORE_URL if _is_store_device(page) else GITHUB_REPO_URL


def _rate_subtitle(page) -> str:
    return "Rate us on Google Play" if _is_store_device(page) else "Star us on GitHub"


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
        snack = ft.SnackBar(ft.Text("Activity log copied to clipboard!"))
        snack.open = True
        page.show_dialog(snack)
        page.update()

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
                action=ft.CopyToClipboard(logs),
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


def _open_version_dialog(page: ft.Page):
    from components.update_dialog import show_update_dialog
    from core.state import state as _st

    if getattr(_st, "update_available", False) and getattr(_st, "update_data", None):
        show_update_dialog(page, _st.update_data)
    else:
        # Up-to-date mode (KTV Player's shape): the installed version and a
        # live re-check. Never fabricate an update the feed never announced.
        show_update_dialog(page, None)


def build_about_section(
    page: ft.Page, privacy_url: str, terms_url: str
) -> ft.Container:
    from core.build_channel import CHANNEL

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
                ft.Container(
                    content=ft.Row(
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
                    ink=True,
                    tooltip="Tap to view changelog",
                    on_click=lambda e: _open_version_dialog(page),
                ),
                *(
                    [
                        ft.Row(
                            [
                                ft.Text(
                                    "Edition", size=FONT_SM, font_family="Outfit"
                                ),
                                ft.TextButton(
                                    content=ft.Text(
                                        "Google Play Edition · Full edition on GitHub",
                                        size=FONT_SM,
                                        weight=ft.FontWeight.W_600,
                                        color=AppColors.PRIMARY,
                                    ),
                                    on_click=lambda e: _launch(
                                        page, GITHUB_REPO_URL
                                    ),
                                    style=ft.ButtonStyle(
                                        padding=ft.Padding(0, 0, 0, 0)
                                    ),
                                ),
                            ],
                            alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                        )
                    ]
                    if CHANNEL == "play"
                    else []
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
                # KTV Player's About shape: icon rows with a real subtitle,
                # whole row tappable (Contact / Rate / More apps).
                ui.setting_row(
                    ft.Icons.MAIL_OUTLINE_ROUNDED,
                    "Contact developer",
                    CONTACT_EMAIL,
                    _external_trailing(),
                    on_click=lambda e: _launch(page, f"mailto:{CONTACT_EMAIL}"),
                ),
                ui.setting_row(
                    ft.Icons.STAR_ROUNDED,
                    "Rate 5 stars",
                    _rate_subtitle(page),
                    _external_trailing(),
                    on_click=lambda e: _launch(page, _rate_url(page)),
                ),
                ui.setting_row(
                    ft.Icons.APPS_ROUNDED,
                    "More apps",
                    "More apps from Kiri Research Labs",
                    _external_trailing(),
                    on_click=lambda e: _launch(page, _more_apps_url(page)),
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
                            on_click=lambda e: _launch(page, privacy_url),
                        ),
                        ft.TextButton(
                            "Terms of Service",
                            icon=ft.Icons.GAVEL_ROUNDED,
                            style=ft.ButtonStyle(color=AppColors.PRIMARY),
                            on_click=lambda e: _launch(page, terms_url),
                        ),
                    ],
                    alignment=ft.MainAxisAlignment.SPACE_EVENLY,
                ),
            ],
            spacing=8,
        ),
        page=page,
    )
