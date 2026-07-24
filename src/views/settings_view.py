from __future__ import annotations

from collections.abc import Callable

import flet as ft

from core.constants import (
    BACKEND_OPTIONS_TEXT,
    EXTRACT_FORMATS,
    REGIONS,
    SAFE_SEARCH_OPTIONS,
    TIMELIMIT_OPTIONS,
    VIDEO_QUALITY_OPTIONS,
)
from core.state import state
from core.styles import build_banner_ad
from core.theme import AppColors, AppStyles
from core.tokens import (
    BORDER_RADIUS_MD,
    FONT_LG,
    FONT_MD,
    FONT_SM,
    FONT_XS,
    ICON_MD,
    SPACING_SM,
)
from core.utils import in_memory_log_handler, logger
from services.storage_service import StorageService

try:
    from importlib.metadata import version as _pkg_version

    _APP_VERSION: str = _pkg_version("ddgs-app")
except (ImportError, KeyError, OSError):
    import tomllib
    from pathlib import Path

    try:
        _pp = Path(__file__).resolve().parent.parent.parent / "pyproject.toml"
        with open(_pp, "rb") as f:
            _APP_VERSION = tomllib.load(f)["project"]["version"]
    except (ImportError, KeyError, OSError, tomllib.TOMLDecodeError):
        _APP_VERSION = "1.1.0"

LOG_TAG = "SettingsView"


def build_settings_view(
    page: ft.Page, on_navigate: Callable, storage: StorageService
) -> ft.View:
    logger.info(f"[{LOG_TAG}] Building settings view")

    async def _set(key: str, val):
        setattr(state, key, val)
        save = getattr(storage, f"set_{key}", None)
        if save:
            await save(val)

    def _rebuild():
        on_navigate(page.route)

    async def _launch_privacy(e=None):
        try:
            await ft.UrlLauncher().launch_url("https://kiri.ng/privacy")
        except (
            ValueError,
            TypeError,
            OSError,
            RuntimeError,
            ConnectionError,
            ImportError,
            KeyError,
            IndexError,
            AttributeError,
            TimeoutError,
        ):
            import webbrowser

            webbrowser.open("https://kiri.ng/privacy")

    async def _launch_terms(e=None):
        try:
            await ft.UrlLauncher().launch_url("https://kiri.ng/terms")
        except (
            ValueError,
            TypeError,
            OSError,
            RuntimeError,
            ConnectionError,
            ImportError,
            KeyError,
            IndexError,
            AttributeError,
            TimeoutError,
        ):
            import webbrowser

            webbrowser.open("https://kiri.ng/terms")

    # ── Theme toggle cards ──
    current_theme = "system"
    if page.theme_mode == ft.ThemeMode.DARK:
        current_theme = "dark"
    elif page.theme_mode == ft.ThemeMode.LIGHT:
        current_theme = "light"

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
            on_click=lambda e: page.run_task(_change_theme, mode),
        )

    light_btn = create_theme_card("light", "Light", ft.Icons.LIGHT_MODE_ROUNDED)
    dark_btn = create_theme_card("dark", "Dark", ft.Icons.DARK_MODE_ROUNDED)
    system_btn = create_theme_card(
        "system", "System", ft.Icons.SETTINGS_SYSTEM_DAYDREAM_ROUNDED
    )

    async def _change_theme(mode_str: str):
        nonlocal current_theme
        current_theme = mode_str
        if mode_str == "dark":
            page.theme_mode = ft.ThemeMode.DARK
        elif mode_str == "light":
            page.theme_mode = ft.ThemeMode.LIGHT
        else:
            page.theme_mode = ft.ThemeMode.SYSTEM
        state.theme_mode = page.theme_mode
        await storage.set_theme(mode_str)
        _rebuild()

    # ── Safe search chips ──
    safe_chips = []
    for opt in SAFE_SEARCH_OPTIONS:
        is_active = opt["key"] == state.safe_search
        safe_chips.append(
            ft.Chip(
                label=ft.Text(opt["label"], size=FONT_SM, font_family="Outfit"),
                selected=is_active,
                on_click=lambda _, k=opt["key"]: page.run_task(_set_and_rebuild, k),
                bgcolor=ft.Colors.with_opacity(0.12, AppColors.PRIMARY)
                if is_active
                else None,
            )
        )

    async def _set_and_rebuild(key: str):
        await _set("safe_search", key)
        _rebuild()

    # ── Modal helpers ──
    def _close_dialog(e=None):
        page.pop_dialog()

    def _show_clear_dialog(e):
        dlg = ft.AlertDialog(
            modal=True,
            title=ft.Text(
                "Clear Search History?",
                font_family="Outfit",
                size=FONT_LG,
                weight=ft.FontWeight.BOLD,
            ),
            content=ft.Text(
                "This will delete all saved search entries. This action is irreversible.",
                style=ft.TextStyle(height=1.4),
            ),
            actions=[
                ft.TextButton("Cancel", on_click=_close_dialog),
                ft.FilledButton(
                    "Clear All",
                    on_click=lambda _: page.run_task(_do_clear),
                    style=ft.ButtonStyle(
                        bgcolor=AppColors.ERROR, color=ft.Colors.WHITE
                    ),
                ),
            ],
            actions_alignment=ft.MainAxisAlignment.END,
        )
        page.show_dialog(dlg)

    async def _do_clear():
        page.pop_dialog()
        state.search_history.clear()
        await storage.set_history([])
        _rebuild()

    # ── Live Activity Terminal ──
    def _show_logs_dialog(e):
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

        dlg = ft.AlertDialog(
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
                ft.TextButton("Close", on_click=_close_dialog),
            ],
            actions_alignment=ft.MainAxisAlignment.END,
        )
        page.show_dialog(dlg)

    # ── Settings Header ──
    header = ft.Container(
        content=ft.Row(
            [
                ft.IconButton(
                    icon=ft.Icons.ARROW_BACK_ROUNDED,
                    icon_size=ICON_MD,
                    on_click=lambda e: page.run_task(_go_home),
                ),
                ft.Text(
                    "Settings",
                    size=FONT_LG,
                    weight=ft.FontWeight.BOLD,
                    font_family="Outfit",
                ),
            ],
            spacing=4,
        ),
        padding=ft.Padding(4, 8, 16, 8),
    )

    async def _go_home():
        on_navigate("/home")

    # ── Settings Categories ──
    sections = ft.Column(
        [
            AppStyles.section_card(
                "Display Theme",
                ft.Icons.COLOR_LENS_ROUNDED,
                ft.Row(
                    [light_btn, dark_btn, system_btn],
                    spacing=8,
                    alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                ),
                page=page,
            ),
            AppStyles.section_card(
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
                            options=[
                                ft.dropdown.Option(r["key"], r["label"])
                                for r in REGIONS
                            ],
                            on_select=lambda e: page.run_task(
                                _set, "region", e.control.value
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
                                        _set, "max_results", int(e.control.value)
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
                                _set, "timelimit", e.control.value
                            ),
                            filled=True,
                            border_radius=BORDER_RADIUS_MD,
                        ),
                    ],
                    spacing=12,
                ),
                page=page,
            ),
            build_banner_ad(page),
            AppStyles.section_card(
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
                                _set, "backend", e.control.value
                            ),
                            filled=True,
                            border_radius=BORDER_RADIUS_MD,
                        ),
                    ],
                    spacing=10,
                ),
                page=page,
            ),
            AppStyles.section_card(
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
                                _set, "extract_format", e.control.value
                            ),
                            filled=True,
                            border_radius=BORDER_RADIUS_MD,
                        ),
                    ],
                    spacing=10,
                ),
                page=page,
            ),
            AppStyles.section_card(
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
                                _set, "video_quality", e.control.value
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
            ),
            AppStyles.section_card(
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
                            on_change=lambda e: page.run_task(
                                _set, "proxy", e.control.value
                            ),
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
                                        _set, "verify_ssl", e.control.value
                                    ),
                                ),
                            ],
                            alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                        ),
                    ],
                    spacing=12,
                ),
                page=page,
            ),
            AppStyles.section_card(
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
                                        _set, "threads", int(e.control.value)
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
            ),
            AppStyles.section_card(
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
                            on_click=_show_logs_dialog,
                            style=ft.ButtonStyle(
                                bgcolor=AppColors.PRIMARY,
                                color=ft.Colors.WHITE,
                                shape=ft.RoundedRectangleBorder(
                                    radius=BORDER_RADIUS_MD
                                ),
                            ),
                        ),
                    ],
                    spacing=10,
                ),
                page=page,
            ),
            AppStyles.section_card(
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
                            on_click=_show_clear_dialog,
                            style=ft.ButtonStyle(
                                color=AppColors.ERROR,
                                side=ft.BorderSide(1, AppColors.ERROR),
                                shape=ft.RoundedRectangleBorder(
                                    radius=BORDER_RADIUS_MD
                                ),
                            ),
                        ),
                    ],
                    spacing=12,
                ),
                page=page,
            ),
            AppStyles.section_card(
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
                                ft.Text(
                                    "Built with", size=FONT_SM, font_family="Outfit"
                                ),
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
                                    on_click=lambda e: page.run_task(_launch_privacy),
                                ),
                                ft.TextButton(
                                    "Terms of Service",
                                    icon=ft.Icons.GAVEL_ROUNDED,
                                    style=ft.ButtonStyle(color=AppColors.PRIMARY),
                                    on_click=lambda e: page.run_task(_launch_terms),
                                ),
                            ],
                            alignment=ft.MainAxisAlignment.SPACE_EVENLY,
                        ),
                    ],
                    spacing=8,
                ),
                page=page,
            ),
            ft.Container(
                content=ft.Text(
                    "Dux Distributed Global Search (DDGS)",
                    size=10,
                    text_align=ft.TextAlign.CENTER,
                    color=ft.Colors.ON_SURFACE_VARIANT,
                ),
                alignment=ft.Alignment.CENTER,
                padding=ft.Padding(0, 12, 0, 24),
            ),
            build_banner_ad(page),
        ],
        spacing=16,
        scroll=ft.ScrollMode.AUTO,
        expand=True,
    )

    settings_body = ft.Container(
        content=sections,
        padding=16,
        expand=True,
    )

    return ft.View(
        route="/settings",
        controls=[
            ft.SafeArea(
                ft.Container(
                    content=ft.Column([header, settings_body], spacing=0, expand=True),
                    gradient=AppStyles.brand_gradient(page),
                    expand=True,
                ),
                expand=True,
            )
        ],
        padding=0,
        spacing=0,
    )
