from __future__ import annotations

import flet as ft

from core.constants import (
    REGIONS,
    TIMELIMIT_OPTIONS,
    BACKEND_OPTIONS_TEXT,
    EXTRACT_FORMATS,
)
from core.state import state
from core.theme import AppColors, AppStyles
from core.tokens import (
    FONT_XS,
    FONT_SM,
    FONT_MD,
    FONT_LG,
    SPACING_SM,
    BORDER_RADIUS_MD,
    ICON_MD,
)
from core.utils import logger
from services.storage_service import StorageService

LOG_TAG = "SettingsView"

SAFE_SEARCH_OPTIONS = [
    {"key": "off", "label": "Off", "desc": "Show all results"},
    {"key": "moderate", "label": "Moderate", "desc": "Filter explicit content"},
    {"key": "on", "label": "Strict", "desc": "Strict filtering"},
]

THEME_OPTIONS = [
    {"key": "light", "label": "Light", "icon": ft.Icons.LIGHT_MODE_ROUNDED},
    {"key": "dark", "label": "Dark", "icon": ft.Icons.DARK_MODE_ROUNDED},
    {
        "key": "system",
        "label": "System",
        "icon": ft.Icons.SETTINGS_SYSTEM_DAYDREAM_ROUNDED,
    },
]


def build_settings_view(page: ft.Page, storage: StorageService) -> ft.View:
    logger.info(f"[{LOG_TAG}] Building settings view")

    async def _set(key: str, val):
        setattr(state, key, val)
        save = getattr(storage, f"set_{key}", None)
        if save:
            await save(val)

    def _rebuild():
        page.views.clear()
        page.views.append(build_settings_view(page, storage))
        page.update()

    # ── Theme toggle ──
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
        for m, btn in [
            ("light", light_btn),
            ("dark", dark_btn),
            ("system", system_btn),
        ]:
            is_sel = m == mode_str
            btn.border = (
                ft.Border.all(2, AppColors.PRIMARY)
                if is_sel
                else ft.Border.all(1, ft.Colors.with_opacity(0.1, ft.Colors.ON_SURFACE))
            )
            btn.bgcolor = (
                ft.Colors.with_opacity(0.1, AppColors.PRIMARY)
                if is_sel
                else ft.Colors.SURFACE_CONTAINER_HIGHEST
            )
            btn.content.controls[0].color = (
                AppColors.PRIMARY if is_sel else ft.Colors.ON_SURFACE_VARIANT
            )
            btn.content.controls[1].color = (
                AppColors.PRIMARY if is_sel else ft.Colors.ON_SURFACE
            )
            btn.content.controls[1].weight = (
                ft.FontWeight.W_600 if is_sel else ft.FontWeight.NORMAL
            )
        page.update()

    # ── Safe search chips ──
    safe_chips = []
    for opt in SAFE_SEARCH_OPTIONS:
        is_active = opt["key"] == state.safe_search
        safe_chips.append(
            ft.Chip(
                label=ft.Text(opt["label"], size=FONT_SM),
                selected=is_active,
                on_click=lambda _, k=opt["key"]: page.run_task(_set_and_rebuild, k),
                bgcolor=ft.Colors.with_opacity(0.1, AppColors.PRIMARY)
                if is_active
                else None,
            )
        )

    async def _set_and_rebuild(key: str):
        await _set("safe_search", key)
        _rebuild()

    # ── Clear dialog ──
    def _show_clear_dialog(e):
        dlg = ft.AlertDialog(
            modal=True,
            title=ft.Text("Clear History?"),
            content=ft.Text("Removes all saved searches. This cannot be undone."),
            actions=[
                ft.TextButton("Cancel", on_click=lambda _: _close_dialog(dlg)),
                ft.FilledButton(
                    "Clear All",
                    on_click=lambda _: page.run_task(_do_clear, dlg),
                    style=ft.ButtonStyle(
                        bgcolor=AppColors.ERROR, color=ft.Colors.WHITE
                    ),
                ),
            ],
            actions_alignment=ft.MainAxisAlignment.END,
        )
        page.overlay.append(dlg)
        dlg.open = True
        page.update()

    def _close_dialog(dlg):
        dlg.open = False
        page.update()

    async def _do_clear(dlg):
        dlg.open = False
        page.update()
        state.search_history.clear()
        await storage.set_history([])
        _rebuild()

    # ── Header ──
    header = ft.Container(
        content=ft.Row(
            [
                ft.IconButton(
                    icon=ft.Icons.ARROW_BACK_ROUNDED,
                    icon_size=ICON_MD,
                    on_click=lambda e: page.run_task(_go_home),
                ),
                ft.Text("Settings", size=FONT_LG, weight=ft.FontWeight.BOLD),
            ],
            spacing=4,
        ),
        padding=ft.Padding(4, 8, 16, 8),
    )

    async def _go_home():
        page.route = "/home"
        page.views.clear()
        from views.home_view import build_home_view

        page.views.append(
            build_home_view(
                page,
                lambda r: setattr(page, "route", r) or page.run_task(page.update),
                storage,
                lambda q, t: None,
            )
        )
        page.update()

    # ── Sections ──
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
            ),
            AppStyles.section_card(
                "Search",
                ft.Icons.SEARCH_ROUNDED,
                ft.Column(
                    [
                        ft.Text(
                            "Safe Search", size=FONT_MD, weight=ft.FontWeight.W_500
                        ),
                        ft.Text(
                            "Controls explicit content filtering",
                            size=FONT_XS,
                            color=ft.Colors.ON_SURFACE_VARIANT,
                        ),
                        ft.Row(safe_chips, spacing=SPACING_SM),
                        ft.Divider(
                            height=1,
                            color=ft.Colors.with_opacity(0.05, ft.Colors.ON_SURFACE),
                        ),
                        ft.Text("Region", size=FONT_MD, weight=ft.FontWeight.W_500),
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
                        ft.Text(
                            "Results per page", size=FONT_MD, weight=ft.FontWeight.W_500
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
                                    on_change_end=lambda e: page.run_task(
                                        _set, "max_results", int(e.control.value)
                                    ),
                                ),
                                ft.Text(
                                    f"{state.max_results}",
                                    size=FONT_SM,
                                    weight=ft.FontWeight.W_600,
                                    color=AppColors.PRIMARY,
                                ),
                            ],
                            spacing=SPACING_SM,
                            vertical_alignment=ft.CrossAxisAlignment.CENTER,
                        ),
                        ft.Divider(
                            height=1,
                            color=ft.Colors.with_opacity(0.05, ft.Colors.ON_SURFACE),
                        ),
                        ft.Text("Time Limit", size=FONT_MD, weight=ft.FontWeight.W_500),
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
            ),
            AppStyles.section_card(
                "Search Engine",
                ft.Icons.TRAVEL_EXPLORE_ROUNDED,
                ft.Column(
                    [
                        ft.Text(
                            "Override the default search backend",
                            size=FONT_XS,
                            color=ft.Colors.ON_SURFACE_VARIANT,
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
                    spacing=12,
                ),
            ),
            AppStyles.section_card(
                "Page Extraction",
                ft.Icons.DOWNLOAD_ROUNDED,
                ft.Column(
                    [
                        ft.Text(
                            "Default format for URL content extraction",
                            size=FONT_XS,
                            color=ft.Colors.ON_SURFACE_VARIANT,
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
                    spacing=12,
                ),
            ),
            AppStyles.section_card(
                "Connection",
                ft.Icons.WIFI_ROUNDED,
                ft.Column(
                    [
                        ft.Text("Proxy", size=FONT_MD, weight=ft.FontWeight.W_500),
                        ft.TextField(
                            value=state.proxy,
                            hint_text="http://user:pass@host:port",
                            on_change=lambda e: page.run_task(
                                _set, "proxy", e.control.value
                            ),
                            border_radius=BORDER_RADIUS_MD,
                            filled=True,
                        ),
                        ft.Row(
                            [
                                ft.Text(
                                    "SSL Verification",
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
            ),
            AppStyles.section_card(
                "Performance",
                ft.Icons.SPEED_ROUNDED,
                ft.Column(
                    [
                        ft.Text(
                            "Max Threads", size=FONT_MD, weight=ft.FontWeight.W_500
                        ),
                        ft.Text(
                            "0 = automatic",
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
                                    on_change_end=lambda e: page.run_task(
                                        _set, "threads", int(e.control.value)
                                    ),
                                ),
                                ft.Text(
                                    f"{state.threads}",
                                    size=FONT_SM,
                                    weight=ft.FontWeight.W_600,
                                    color=AppColors.PRIMARY,
                                ),
                            ],
                            spacing=SPACING_SM,
                            vertical_alignment=ft.CrossAxisAlignment.CENTER,
                        ),
                    ],
                    spacing=12,
                ),
            ),
            AppStyles.section_card(
                "Advanced (DHT Network)",
                ft.Icons.HUB_ROUNDED,
                ft.Column(
                    [
                        ft.Text("API URL", size=FONT_MD, weight=ft.FontWeight.W_500),
                        ft.Text(
                            "For distributed caching (optional)",
                            size=FONT_XS,
                            color=ft.Colors.ON_SURFACE_VARIANT,
                        ),
                        ft.TextField(
                            value=state.api_url,
                            hint_text="http://localhost:4479",
                            on_change=lambda e: page.run_task(
                                _set, "api_url", e.control.value
                            ),
                            border_radius=BORDER_RADIUS_MD,
                            filled=True,
                        ),
                        ft.Row(
                            [
                                ft.Text(
                                    "Spawn API Server",
                                    size=FONT_MD,
                                    weight=ft.FontWeight.W_500,
                                    expand=True,
                                ),
                                ft.Switch(
                                    value=state.spawn_api,
                                    active_color=AppColors.PRIMARY,
                                    on_change=lambda e: page.run_task(
                                        _set, "spawn_api", e.control.value
                                    ),
                                ),
                            ],
                            alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                        ),
                    ],
                    spacing=12,
                ),
            ),
            AppStyles.section_card(
                "Data",
                ft.Icons.STORAGE_ROUNDED,
                ft.Column(
                    [
                        ft.Text(
                            f"{len(state.search_history)} saved searches",
                            size=FONT_SM,
                            color=ft.Colors.ON_SURFACE_VARIANT,
                        ),
                        ft.OutlinedButton(
                            "Clear Search History",
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
            ),
            AppStyles.section_card(
                "About",
                ft.Icons.INFO_ROUNDED,
                ft.Column(
                    [
                        ft.Row(
                            [
                                ft.Text("Version", size=FONT_MD),
                                ft.Text(
                                    "1.0.0",
                                    size=FONT_MD,
                                    color=ft.Colors.ON_SURFACE_VARIANT,
                                ),
                            ],
                            alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                        ),
                        ft.Row(
                            [
                                ft.Text("Engine", size=FONT_MD),
                                ft.Text(
                                    "DDGS + primp",
                                    size=FONT_MD,
                                    color=ft.Colors.ON_SURFACE_VARIANT,
                                ),
                            ],
                            alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                        ),
                        ft.Row(
                            [
                                ft.Text("Backends", size=FONT_MD),
                                ft.Text(
                                    "9 engines across 5 categories",
                                    size=FONT_MD,
                                    color=ft.Colors.ON_SURFACE_VARIANT,
                                ),
                            ],
                            alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                        ),
                    ],
                    spacing=8,
                ),
            ),
            ft.Container(
                content=ft.Text(
                    "DDGS Search v1.0.0",
                    size=11,
                    text_align=ft.TextAlign.CENTER,
                    color=ft.Colors.ON_SURFACE_VARIANT,
                ),
                alignment=ft.alignment.Alignment(0, 0),
                padding=ft.Padding(0, 10, 0, 20),
            ),
        ],
        spacing=16,
        scroll=ft.ScrollMode.AUTO,
        expand=True,
    )

    settings_body = ft.Container(
        content=sections,
        padding=20,
        expand=True,
    )

    return ft.View(
        route="/settings",
        controls=[
            ft.SafeArea(
                ft.Container(
                    content=ft.Column([header, settings_body], spacing=0, expand=True),
                    bgcolor=ft.Colors.SURFACE,
                    expand=True,
                ),
                expand=True,
            )
        ],
        padding=0,
        spacing=0,
    )
