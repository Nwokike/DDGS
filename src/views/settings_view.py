"""Settings view — every DDGS configurable parameter."""

from __future__ import annotations


import flet as ft

from core.constants import (
    REGIONS,
    TIMELIMIT_OPTIONS,
    BACKEND_OPTIONS_TEXT,
    EXTRACT_FORMATS,
)
from core.state import state
from core.theme import AppColors
from core.tokens import (
    FONT_XS,
    FONT_SM,
    FONT_MD,
    FONT_LG,
    SPACING_SM,
    SPACING_MD,
    SPACING_LG,
    BORDER_RADIUS_MD,
    BORDER_RADIUS_LG,
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


def _build_section(*controls, title: str = "") -> ft.Container:
    return ft.Container(
        content=ft.Column(
            controls=[
                ft.Text(title, size=FONT_LG, weight=ft.FontWeight.W_600),
                ft.Divider(),
                *controls,
            ],
            spacing=SPACING_MD,
        ),
        padding=ft.Padding(
            left=SPACING_LG, top=SPACING_LG, right=SPACING_LG, bottom=SPACING_LG
        ),
        bgcolor=AppColors.SURFACE,
        border_radius=BORDER_RADIUS_LG,
    )


def build_settings_view(page: ft.Page, storage: StorageService) -> ft.View:
    logger.info(f"[{LOG_TAG}] Building settings view")

    async def _set(key: str, val):
        setattr(state, key, val)
        save = getattr(storage, f"set_{key}", None)
        if save:
            await save(val)
        logger.debug(f"[{LOG_TAG}] {key} = {val}")

    def _rebuild():
        page.views.clear()
        page.views.append(build_settings_view(page, storage))
        page.update()

    def _show_clear_dialog(e):
        dlg = ft.AlertDialog(
            title=ft.Text("Clear History?"),
            content=ft.Text("Removes all saved searches."),
            actions=[
                ft.TextButton(
                    "Cancel",
                    on_click=lambda _: setattr(dlg, "open", False) or page.update(),
                ),
                ft.TextButton(
                    "Clear", on_click=lambda _: page.run_task(_do_clear, dlg)
                ),
            ],
        )
        page.show_dialog(dlg)

    async def _do_clear(dlg):
        dlg.open = False
        page.update()
        state.search_history.clear()
        await storage.set_history([])

    # ── Safe search chips ──
    safe_chips = []
    for opt in SAFE_SEARCH_OPTIONS:
        is_active = opt["key"] == state.safe_search
        safe_chips.append(
            ft.Chip(
                label=ft.Text(opt["label"], size=FONT_SM),
                selected=is_active,
                on_click=lambda _, k=opt["key"]: page.run_task(_set_and_rebuild, k),
                bgcolor=AppColors.PRIMARY_LIGHT
                if is_active
                else ft.Colors.SURFACE_CONTAINER,
            )
        )

    async def _set_and_rebuild(key: str):
        await _set("safe_search", key)
        _rebuild()

    # ── Sections ──
    sections = [
        # ── Search ──
        _build_section(
            ft.Text("Safe Search", size=FONT_MD, weight=ft.FontWeight.W_500),
            ft.Text(
                "Controls explicit content filtering",
                size=FONT_XS,
                color=ft.Colors.ON_SURFACE_VARIANT,
            ),
            ft.Row(controls=safe_chips, spacing=SPACING_SM),
            ft.Text("Region", size=FONT_MD, weight=ft.FontWeight.W_500),
            ft.Dropdown(
                value=state.region,
                options=[ft.dropdown.Option(r["key"], r["label"]) for r in REGIONS],
                on_select=lambda e: page.run_task(_set, "region", e.control.value),
                filled=True,
                border_radius=BORDER_RADIUS_MD,
            ),
            ft.Text("Max Results", size=FONT_MD, weight=ft.FontWeight.W_500),
            ft.Text(
                f"{state.max_results} results per search",
                size=FONT_XS,
                color=ft.Colors.ON_SURFACE_VARIANT,
            ),
            ft.Slider(
                value=float(state.max_results),
                min=5,
                max=100,
                divisions=19,
                label="{value}",
                on_change_end=lambda e: page.run_task(
                    _set, "max_results", int(e.control.value)
                ),
            ),
            ft.Text("Time Limit", size=FONT_MD, weight=ft.FontWeight.W_500),
            ft.Dropdown(
                value=state.timelimit or "",
                options=[
                    ft.dropdown.Option(o["key"], o["label"]) for o in TIMELIMIT_OPTIONS
                ],
                on_select=lambda e: page.run_task(_set, "timelimit", e.control.value),
                filled=True,
                border_radius=BORDER_RADIUS_MD,
            ),
            title="Search",
        ),
        # ── Backend ──
        _build_section(
            ft.Text(
                "'Auto' queries all available engines. Choose a specific backend to override.",
                size=FONT_XS,
                color=ft.Colors.ON_SURFACE_VARIANT,
            ),
            ft.Dropdown(
                value=state.backend or "auto",
                options=[
                    ft.dropdown.Option(b["key"], b["label"])
                    for b in BACKEND_OPTIONS_TEXT
                ],
                on_select=lambda e: page.run_task(_set, "backend", e.control.value),
                filled=True,
                border_radius=BORDER_RADIUS_MD,
            ),
            title="Search Engine Backend",
        ),
        # ── Extract ──
        _build_section(
            ft.Text(
                "Default format for URL content extraction",
                size=FONT_XS,
                color=ft.Colors.ON_SURFACE_VARIANT,
            ),
            ft.Dropdown(
                value=state.extract_format,
                options=[
                    ft.dropdown.Option(f["key"], f["label"]) for f in EXTRACT_FORMATS
                ],
                on_select=lambda e: page.run_task(
                    _set, "extract_format", e.control.value
                ),
                filled=True,
                border_radius=BORDER_RADIUS_MD,
            ),
            title="Page Extraction",
        ),
        # ── Connection ──
        _build_section(
            ft.Text("Proxy", size=FONT_MD, weight=ft.FontWeight.W_500),
            ft.TextField(
                value=state.proxy,
                hint_text="http://user:pass@host:port",
                on_change=lambda e: page.run_task(_set, "proxy", e.control.value),
                border_radius=BORDER_RADIUS_MD,
                filled=True,
            ),
            ft.Row(
                controls=[
                    ft.Text(
                        "SSL Verification",
                        size=FONT_MD,
                        weight=ft.FontWeight.W_500,
                        expand=True,
                    ),
                    ft.Switch(
                        value=state.verify_ssl,
                        on_change=lambda e: page.run_task(
                            _set, "verify_ssl", e.control.value
                        ),
                    ),
                ],
                alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
            ),
            title="Connection",
        ),
        # ── Performance ──
        _build_section(
            ft.Text("Max Threads", size=FONT_MD, weight=ft.FontWeight.W_500),
            ft.Text("0 = automatic", size=FONT_XS, color=ft.Colors.ON_SURFACE_VARIANT),
            ft.Slider(
                value=float(state.threads),
                min=0,
                max=20,
                divisions=20,
                label="{value}",
                on_change_end=lambda e: page.run_task(
                    _set, "threads", int(e.control.value)
                ),
            ),
            title="Performance",
        ),
        # ── Advanced ──
        _build_section(
            ft.Text("API URL", size=FONT_MD, weight=ft.FontWeight.W_500),
            ft.Text(
                "For distributed caching (optional)",
                size=FONT_XS,
                color=ft.Colors.ON_SURFACE_VARIANT,
            ),
            ft.TextField(
                value=state.api_url,
                hint_text="http://localhost:4479",
                on_change=lambda e: page.run_task(_set, "api_url", e.control.value),
                border_radius=BORDER_RADIUS_MD,
                filled=True,
            ),
            ft.Row(
                controls=[
                    ft.Text(
                        "Spawn API Server",
                        size=FONT_MD,
                        weight=ft.FontWeight.W_500,
                        expand=True,
                    ),
                    ft.Switch(
                        value=state.spawn_api,
                        on_change=lambda e: page.run_task(
                            _set, "spawn_api", e.control.value
                        ),
                    ),
                ],
                alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
            ),
            title="Advanced (DHT Network)",
        ),
        # ── Data ──
        _build_section(
            ft.Text(
                f"{len(state.search_history)} saved searches",
                size=FONT_SM,
                color=ft.Colors.ON_SURFACE_VARIANT,
            ),
            ft.OutlinedButton(
                "Clear Search History",
                icon=ft.Icons.DELETE_SWEEP_ROUNDED,
                on_click=_show_clear_dialog,
            ),
            title="Data",
        ),
        # ── About ──
        _build_section(
            ft.Row(
                controls=[
                    ft.Text("Version", size=FONT_MD),
                    ft.Text("1.0.0", size=FONT_MD, color=ft.Colors.ON_SURFACE_VARIANT),
                ],
                alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
            ),
            ft.Row(
                controls=[
                    ft.Text("Engine", size=FONT_MD),
                    ft.Text(
                        "DDGS + primp", size=FONT_MD, color=ft.Colors.ON_SURFACE_VARIANT
                    ),
                ],
                alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
            ),
            ft.Row(
                controls=[
                    ft.Text("Backends", size=FONT_MD),
                    ft.Text(
                        "14 engines across 5 categories",
                        size=FONT_MD,
                        color=ft.Colors.ON_SURFACE_VARIANT,
                    ),
                ],
                alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
            ),
            title="About",
        ),
    ]

    content = ft.SafeArea(
        content=ft.Column(
            controls=[
                ft.Container(
                    content=ft.Row(
                        controls=[
                            ft.IconButton(
                                icon=ft.Icons.ARROW_BACK_ROUNDED,
                                icon_size=ICON_MD,
                                on_click=lambda _: page.go("/home"),
                            ),
                            ft.Text(
                                "Settings", size=FONT_LG, weight=ft.FontWeight.W_600
                            ),
                        ]
                    ),
                    padding=ft.Padding(
                        left=SPACING_MD,
                        top=SPACING_SM,
                        right=SPACING_MD,
                        bottom=SPACING_SM,
                    ),
                ),
                ft.Column(
                    controls=sections,
                    spacing=SPACING_MD,
                    scroll=ft.ScrollMode.AUTO,
                    expand=True,
                ),
            ],
            spacing=0,
            expand=True,
        ),
    )

    return ft.View(
        route="/settings",
        controls=[content],
        padding=0,
        spacing=0,
        bgcolor=AppColors.BACKGROUND,
    )
