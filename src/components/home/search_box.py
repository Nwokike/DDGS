from __future__ import annotations

from collections.abc import Callable

import flet as ft

from core import tokens
from core.constants import (
    BACKEND_OPTIONS_BOOKS,
    BACKEND_OPTIONS_IMAGES,
    BACKEND_OPTIONS_NEWS,
    BACKEND_OPTIONS_TEXT,
    BACKEND_OPTIONS_VIDEOS,
    EXTRACT_FORMATS,
    MAX_RESULTS_PRESETS,
    REGIONS,
    SAFE_SEARCH_OPTIONS,
    TIMELIMIT_OPTIONS,
)
from core.state import state
from core.theme import AppColors
from core.utils import logger

BACKEND_OPTIONS_MAP = {
    "text": BACKEND_OPTIONS_TEXT,
    "images": BACKEND_OPTIONS_IMAGES,
    "videos": BACKEND_OPTIONS_VIDEOS,
    "news": BACKEND_OPTIONS_NEWS,
    "books": BACKEND_OPTIONS_BOOKS,
}


def build_search_section(
    page: ft.Page,
    active_tab: str,
    search_field_ref: ft.Ref[ft.TextField],
    do_search: Callable,
    storage,
    is_dark: bool,
) -> ft.Container:
    _hint_map = {
        "text": "Search the web...",
        "images": "Search for images...",
        "videos": "Search for videos...",
        "news": "Search for news...",
        "books": "Search for books...",
        "extract": "Paste a URL to fetch its content...",
    }
    _prefix_icon_map = {
        "extract": ft.Icons.LINK_ROUNDED,
    }

    async def _paste_clipboard(e):
        try:
            clipboard = ft.Clipboard()
            text = await clipboard.get()
            if text and search_field_ref.current:
                search_field_ref.current.value = text.strip()
                search_field_ref.current.update()
        except (
            ValueError,
            TypeError,
            AttributeError,
            OSError,
            RuntimeError,
        ) as ex:
            logger.warning(f"Clipboard paste failed: {ex}")

    search_field = ft.TextField(
        ref=search_field_ref,
        value=state.current_query,
        hint_text=_hint_map.get(active_tab, "Search the web..."),
        hint_style=ft.TextStyle(
            size=tokens.FONT_MD,
            weight=ft.FontWeight.W_400,
            italic=True,
            color=ft.Colors.with_opacity(
                0.4, AppColors.DARK_TEXT if is_dark else AppColors.LIGHT_TEXT
            ),
        ),
        text_style=ft.TextStyle(size=tokens.FONT_MD, weight=ft.FontWeight.W_500),
        prefix_icon=_prefix_icon_map.get(active_tab, ft.Icons.SEARCH_ROUNDED),
        content_padding=ft.Padding(left=18, top=14, right=18, bottom=14),
        border_radius=tokens.RADIUS_MD,
        border_width=1.0,
        border_color=ft.Colors.with_opacity(
            0.12, AppColors.DARK_TEXT if is_dark else AppColors.LIGHT_TEXT
        ),
        focused_border_color=AppColors.PRIMARY,
        focused_border_width=1.5,
        border=ft.InputBorder.OUTLINE,
        filled=True,
        bgcolor=AppColors.DARK_SURFACE if is_dark else AppColors.LIGHT_SURFACE,
        cursor_color=AppColors.PRIMARY,
        on_submit=lambda e: page.run_task(do_search),
        suffix=ft.IconButton(
            icon=ft.Icons.PASTE_ROUNDED,
            icon_size=18,
            icon_color=AppColors.PRIMARY,
            tooltip="Paste from clipboard",
            on_click=_paste_clipboard,
        ),
    )

    tools_expanded = False
    tools_container_ref = ft.Ref[ft.Container]()

    async def _set_backend(val: str):
        state.backend = val
        await storage.set_backend(val)

    async def _set_timelimit(val: str):
        state.timelimit = val
        await storage.set_timelimit(val)

    async def _set_safe_search(val: str):
        state.safe_search = val
        await storage.set_safe_search(val)

    async def _set_region(val: str):
        state.region = val
        await storage.set_region(val)

    async def _set_max_results(val: int):
        state.max_results = val
        await storage.set_max_results(val)

    async def _set_extract_format(val: str):
        state.extract_format = val
        await storage.set_extract_format(val)

    def _toggle_tools(_):
        nonlocal tools_expanded
        tools_expanded = not tools_expanded
        if tools_container_ref.current:
            tools_container_ref.current.visible = tools_expanded
            tools_container_ref.current.update()

    def _make_compact_dropdown(label, icon, value, options, on_change, width=140):
        return ft.Column(
            [
                ft.Row(
                    [
                        ft.Icon(icon, size=14, color=ft.Colors.ON_SURFACE_VARIANT),
                        ft.Text(
                            label,
                            size=tokens.FONT_XS,
                            color=ft.Colors.ON_SURFACE_VARIANT,
                            font_family="Outfit",
                            weight=ft.FontWeight.W_500,
                        ),
                    ],
                    spacing=4,
                    tight=True,
                ),
                ft.Dropdown(
                    value=value,
                    options=options,
                    on_select=on_change,
                    filled=True,
                    text_size=tokens.FONT_XS,
                    content_padding=ft.Padding(left=10, top=4, right=10, bottom=4),
                    border_radius=tokens.RADIUS_MD,
                    width=width,
                    height=36,
                ),
            ],
            spacing=2,
            tight=True,
        )

    backend_options = BACKEND_OPTIONS_MAP.get(active_tab, BACKEND_OPTIONS_TEXT)
    current_backend = state.backend or "auto"

    if active_tab == "extract":
        tools_controls = [
            _make_compact_dropdown(
                "Output Format",
                ft.Icons.CODE_ROUNDED,
                state.extract_format,
                [ft.dropdown.Option(f["key"], f["label"]) for f in EXTRACT_FORMATS],
                lambda e: page.run_task(_set_extract_format, e.control.value),
                width=160,
            ),
        ]
    else:
        tools_controls = [
            _make_compact_dropdown(
                "Safe Search",
                ft.Icons.SHIELD_ROUNDED,
                state.safe_search,
                [ft.dropdown.Option(o["key"], o["label"]) for o in SAFE_SEARCH_OPTIONS],
                lambda e: page.run_task(_set_safe_search, e.control.value),
                width=120,
            ),
            _make_compact_dropdown(
                "Region",
                ft.Icons.PUBLIC_ROUNDED,
                state.region,
                [ft.dropdown.Option(r["key"], r["label"]) for r in REGIONS],
                lambda e: page.run_task(_set_region, e.control.value),
                width=180,
            ),
            _make_compact_dropdown(
                "Max Results",
                ft.Icons.FORMAT_LIST_NUMBERED_ROUNDED,
                str(state.max_results),
                [
                    ft.dropdown.Option(str(p["key"]), p["label"])
                    for p in MAX_RESULTS_PRESETS
                ],
                lambda e: page.run_task(_set_max_results, int(e.control.value)),
                width=100,
            ),
            _make_compact_dropdown(
                "Time",
                ft.Icons.SCHEDULE_ROUNDED,
                state.timelimit or "",
                [ft.dropdown.Option(o["key"], o["label"]) for o in TIMELIMIT_OPTIONS],
                lambda e: page.run_task(_set_timelimit, e.control.value),
                width=130,
            ),
            _make_compact_dropdown(
                "Backend",
                ft.Icons.TRAVEL_EXPLORE_ROUNDED,
                current_backend
                if any(b["key"] == current_backend for b in backend_options)
                else "auto",
                [ft.dropdown.Option(b["key"], b["label"]) for b in backend_options],
                lambda e: page.run_task(_set_backend, e.control.value),
                width=160,
            ),
        ]

    tools_toggle = ft.Container(
        content=ft.Row(
            [
                ft.Icon(
                    ft.Icons.TUNE_ROUNDED,
                    size=16,
                    color=AppColors.PRIMARY,
                ),
                ft.Text(
                    "Search Tools",
                    size=tokens.FONT_XS,
                    weight=ft.FontWeight.W_600,
                    color=AppColors.PRIMARY,
                    font_family="Outfit",
                ),
                ft.Icon(
                    ft.Icons.EXPAND_MORE_ROUNDED
                    if not tools_expanded
                    else ft.Icons.EXPAND_LESS_ROUNDED,
                    size=16,
                    color=AppColors.PRIMARY,
                ),
            ],
            spacing=4,
            alignment=ft.MainAxisAlignment.CENTER,
            tight=True,
        ),
        on_click=_toggle_tools,
        padding=ft.Padding(12, 6, 12, 6),
        border_radius=tokens.RADIUS_PILL,
        border=ft.Border.all(1, ft.Colors.with_opacity(0.2, AppColors.PRIMARY)),
        bgcolor=ft.Colors.with_opacity(0.06, AppColors.PRIMARY),
        animate=ft.Animation(200, ft.AnimationCurve.EASE_OUT),
    )

    tools_panel = ft.Container(
        ref=tools_container_ref,
        content=ft.Row(
            controls=tools_controls,
            wrap=True,
            spacing=tokens.SPACE_MD,
            run_spacing=tokens.SPACE_SM,
            alignment=ft.MainAxisAlignment.CENTER,
        ),
        padding=ft.Padding(8, 10, 8, 10),
        border_radius=tokens.RADIUS_MD,
        bgcolor=ft.Colors.with_opacity(0.04, AppColors.PRIMARY),
        border=ft.Border.all(1, ft.Colors.with_opacity(0.08, AppColors.PRIMARY)),
        visible=tools_expanded,
        animate=ft.Animation(200, ft.AnimationCurve.EASE_OUT),
    )

    search_button = ft.FilledButton(
        content=ft.Row(
            [
                ft.Icon(
                    ft.Icons.SEARCH_ROUNDED, size=tokens.ICON_MD, color=ft.Colors.WHITE
                ),
                ft.Text(
                    "Search" if active_tab != "extract" else "Fetch Page",
                    size=tokens.FONT_MD,
                    weight=ft.FontWeight.W_600,
                    color=ft.Colors.WHITE,
                    font_family="Outfit",
                ),
            ],
            spacing=8,
            tight=True,
        ),
        on_click=lambda _: page.run_task(do_search),
        style=ft.ButtonStyle(
            shape=ft.RoundedRectangleBorder(radius=tokens.RADIUS_PILL),
            bgcolor=AppColors.PRIMARY,
            padding=ft.Padding(32, 14, 32, 14),
        ),
    )

    return ft.Container(
        content=ft.Column(
            [
                search_field,
                ft.Row(
                    [tools_toggle],
                    alignment=ft.MainAxisAlignment.CENTER,
                ),
                tools_panel,
                ft.Row([search_button], alignment=ft.MainAxisAlignment.CENTER),
            ],
            spacing=tokens.SPACE_SM,
            tight=True,
            horizontal_alignment=ft.CrossAxisAlignment.STRETCH,
        ),
        padding=ft.Padding(tokens.SPACE_LG, 0, tokens.SPACE_LG, tokens.SPACE_LG),
    )
