from __future__ import annotations

from typing import Callable

import flet as ft

from core.constants import (
    BACKEND_OPTIONS_TEXT,
    BACKEND_OPTIONS_IMAGES,
    BACKEND_OPTIONS_VIDEOS,
    BACKEND_OPTIONS_NEWS,
    BACKEND_OPTIONS_BOOKS,
    TIMELIMIT_OPTIONS,
)
from core.state import state
from core.theme import AppColors, AppStyles
from core.tokens import (
    FONT_XS,
    FONT_SM,
    FONT_MD,
    SPACING_SM,
    SPACING_MD,
    SPACING_LG,
    BORDER_RADIUS_MD,
    BORDER_RADIUS_LG,
    BORDER_RADIUS_FULL,
    ICON_MD,
)
from core.utils import logger
from services.storage_service import StorageService

LOG_TAG = "HomeView"

SEARCH_TABS = [
    {"key": "text", "label": "Web", "icon": ft.Icons.SEARCH_ROUNDED},
    {"key": "images", "label": "Images", "icon": ft.Icons.IMAGE_ROUNDED},
    {"key": "videos", "label": "Videos", "icon": ft.Icons.PLAY_CIRCLE_ROUNDED},
    {"key": "news", "label": "News", "icon": ft.Icons.ARTICLE_ROUNDED},
    {"key": "books", "label": "Books", "icon": ft.Icons.BOOK_ROUNDED},
    {"key": "extract", "label": "Extract", "icon": ft.Icons.DOWNLOAD_ROUNDED},
]

BACKEND_OPTIONS_MAP = {
    "text": BACKEND_OPTIONS_TEXT,
    "images": BACKEND_OPTIONS_IMAGES,
    "videos": BACKEND_OPTIONS_VIDEOS,
    "news": BACKEND_OPTIONS_NEWS,
    "books": BACKEND_OPTIONS_BOOKS,
}


def build_home_view(
    page: ft.Page,
    on_navigate: Callable,
    storage: StorageService,
    on_search: Callable,
) -> ft.View:
    logger.info(f"[{LOG_TAG}] Building home view")

    active_tab = state.default_tab
    search_field = ft.TextField(
        value=state.current_query,
        hint_text="Search DuckDuckGo..."
        if active_tab != "extract"
        else "Enter URL to extract...",
        hint_style=ft.TextStyle(size=FONT_MD, weight=ft.FontWeight.W_400, italic=True),
        text_style=ft.TextStyle(size=FONT_MD, weight=ft.FontWeight.W_500),
        prefix_icon=ft.Icons.SEARCH_ROUNDED
        if active_tab != "extract"
        else ft.Icons.LINK_ROUNDED,
        content_padding=ft.Padding(left=20, top=14, right=20, bottom=14),
        border_radius=BORDER_RADIUS_FULL,
        border=ft.InputBorder.OUTLINE,
        filled=True,
        bgcolor=ft.Colors.with_opacity(0.05, ft.Colors.ON_SURFACE),
        cursor_color=AppColors.PRIMARY,
        autofocus=True,
    )

    def do_search(q: str | None = None):
        query = q or search_field.value
        if not query or not query.strip():
            return
        query = query.strip()
        logger.info(f"[{LOG_TAG}] Search: query={query!r}, type={active_tab}")
        state.current_query = query
        on_search(query, active_tab)

    search_field.on_submit = lambda e: do_search()

    def _prefill_search(q: str, tab: str | None = None):
        nonlocal active_tab
        search_field.value = q
        if tab and tab != active_tab:
            active_tab = tab
            state.default_tab = tab
            page.run_task(storage.set_default_tab, tab)
            search_field.hint_text = "Search DuckDuckGo..."
            search_field.prefix_icon = ft.Icons.SEARCH_ROUNDED
            search_field.update()
        page.run_task(do_search, q)

    # ── Theme toggle ──
    def _toggle_theme(e):
        if page.theme_mode == ft.ThemeMode.DARK:
            page.theme_mode = ft.ThemeMode.LIGHT
        elif page.theme_mode == ft.ThemeMode.LIGHT:
            page.theme_mode = ft.ThemeMode.SYSTEM
        else:
            page.theme_mode = ft.ThemeMode.DARK
        state.theme_mode = page.theme_mode
        page.run_task(storage.set_theme, page.theme_mode.value)
        page.views.clear()
        page.views.append(build_home_view(page, on_navigate, storage, on_search))
        page.update()

    def _get_theme_icon():
        if page.theme_mode == ft.ThemeMode.DARK:
            return ft.Icons.DARK_MODE_ROUNDED
        elif page.theme_mode == ft.ThemeMode.LIGHT:
            return ft.Icons.LIGHT_MODE_ROUNDED
        return ft.Icons.SETTINGS_SYSTEM_DAYDREAM_ROUNDED

    # ── Header ──
    header = ft.Container(
        content=ft.Row(
            [
                ft.Row(
                    [
                        ft.Image(
                            src="icon.png", width=32, height=32, fit=ft.BoxFit.CONTAIN
                        ),
                        ft.Text(
                            "DDGS",
                            size=18,
                            weight=ft.FontWeight.BOLD,
                            color=AppColors.PRIMARY,
                        ),
                    ],
                    spacing=8,
                ),
                ft.Row(
                    [
                        ft.IconButton(
                            icon=_get_theme_icon(),
                            icon_size=20,
                            on_click=_toggle_theme,
                            style=ft.ButtonStyle(
                                bgcolor=ft.Colors.with_opacity(0.08, AppColors.PRIMARY),
                                shape=ft.RoundedRectangleBorder(
                                    radius=BORDER_RADIUS_MD
                                ),
                            ),
                        ),
                        ft.IconButton(
                            icon=ft.Icons.SETTINGS_ROUNDED,
                            icon_size=20,
                            on_click=lambda e: page.run_task(on_navigate, "/settings"),
                            style=ft.ButtonStyle(
                                bgcolor=ft.Colors.with_opacity(0.08, AppColors.PRIMARY),
                                shape=ft.RoundedRectangleBorder(
                                    radius=BORDER_RADIUS_MD
                                ),
                            ),
                        ),
                    ],
                    spacing=6,
                ),
            ],
            alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
        ),
        padding=ft.Padding(16, 12, 16, 12),
    )

    # ── Tab selector ──
    def on_tab_change(tab_key: str):
        nonlocal active_tab
        active_tab = tab_key
        state.default_tab = tab_key
        page.run_task(storage.set_default_tab, tab_key)
        page.views.clear()
        view = build_home_view(page, on_navigate, storage, on_search)
        page.views.append(view)
        page.update()

    tab_buttons = []
    for tab in SEARCH_TABS:
        is_active = tab["key"] == active_tab
        tab_buttons.append(
            ft.Container(
                content=ft.Column(
                    [
                        ft.Icon(
                            tab["icon"],
                            size=ICON_MD,
                            color=AppColors.PRIMARY
                            if is_active
                            else ft.Colors.ON_SURFACE_VARIANT,
                        ),
                        ft.Text(
                            tab["label"],
                            size=9,
                            weight=ft.FontWeight.W_600
                            if is_active
                            else ft.FontWeight.W_400,
                            color=AppColors.PRIMARY
                            if is_active
                            else ft.Colors.ON_SURFACE_VARIANT,
                        ),
                    ],
                    horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                    spacing=2,
                    tight=True,
                ),
                padding=ft.Padding(8, 8, 8, 8),
                border_radius=BORDER_RADIUS_MD,
                bgcolor=ft.Colors.with_opacity(0.1, AppColors.PRIMARY)
                if is_active
                else None,
                ink=True,
                on_click=lambda _, k=tab["key"]: on_tab_change(k),
                animate=ft.Animation(200, ft.AnimationCurve.EASE_OUT),
            )
        )

    # ── Backend / Time filter row ──
    backend_options = BACKEND_OPTIONS_MAP.get(active_tab, BACKEND_OPTIONS_TEXT)
    current_backend = state.backend or "auto"

    backend_dropdown = ft.Dropdown(
        value=current_backend
        if any(b["key"] == current_backend for b in backend_options)
        else "auto",
        options=[ft.dropdown.Option(b["key"], b["label"]) for b in backend_options],
        on_select=lambda e: page.run_task(_set_backend, e.control.value),
        filled=True,
        text_size=FONT_XS,
        content_padding=ft.Padding(left=12, top=8, right=12, bottom=8),
        border_radius=BORDER_RADIUS_MD,
        width=150,
    )

    time_dropdown = ft.Dropdown(
        value=state.timelimit or "",
        options=[ft.dropdown.Option(o["key"], o["label"]) for o in TIMELIMIT_OPTIONS],
        on_select=lambda e: page.run_task(_set_timelimit, e.control.value),
        filled=True,
        text_size=FONT_XS,
        content_padding=ft.Padding(left=12, top=8, right=12, bottom=8),
        border_radius=BORDER_RADIUS_MD,
        width=130,
    )

    async def _set_backend(val: str):
        state.backend = val
        await storage.set_backend(val)

    async def _set_timelimit(val: str):
        state.timelimit = val
        await storage.set_timelimit(val)

    # ── Search button ──
    search_button = ft.FilledButton(
        content=ft.Row(
            [
                ft.Icon(ft.Icons.SEARCH_ROUNDED, size=ICON_MD, color=ft.Colors.WHITE),
                ft.Text(
                    "Search",
                    size=FONT_MD,
                    weight=ft.FontWeight.W_600,
                    color=ft.Colors.WHITE,
                ),
            ],
            spacing=6,
            tight=True,
        ),
        on_click=lambda _: do_search(),
        style=ft.ButtonStyle(
            shape=ft.RoundedRectangleBorder(radius=BORDER_RADIUS_FULL),
            padding=ft.Padding(24, 14, 24, 14),
        ),
    )

    # ── Recent searches ──
    recent_section = None
    if state.search_history:
        items = []
        for i, entry in enumerate(state.search_history[:5]):
            q = entry.get("query", "")
            st = entry.get("search_type", "text")
            ts = entry.get("timestamp", "")
            tab_info = next((t for t in SEARCH_TABS if t["key"] == st), SEARCH_TABS[0])
            items.append(
                ft.Container(
                    content=ft.ListTile(
                        leading=ft.Container(
                            content=ft.Icon(
                                tab_info["icon"], size=16, color=AppColors.PRIMARY
                            ),
                            padding=ft.Padding(8, 8, 8, 8),
                            bgcolor=ft.Colors.with_opacity(0.1, AppColors.PRIMARY),
                            border_radius=BORDER_RADIUS_MD,
                        ),
                        title=ft.Text(
                            q,
                            size=FONT_MD,
                            no_wrap=False,
                            max_lines=1,
                            weight=ft.FontWeight.W_500,
                        ),
                        subtitle=ft.Text(
                            f"{tab_info['label']} \u00b7 {ts}",
                            size=FONT_XS,
                            color=ft.Colors.ON_SURFACE_VARIANT,
                        ),
                        on_click=lambda _, qq=q, st=st: _prefill_search(qq, st),
                        dense=True,
                    ),
                    border_radius=BORDER_RADIUS_MD,
                    ink=True,
                )
            )
        recent_section = ft.Container(
            content=ft.Column(
                [
                    ft.Row(
                        [
                            ft.Icon(
                                ft.Icons.HISTORY_ROUNDED,
                                size=14,
                                color=ft.Colors.ON_SURFACE_VARIANT,
                            ),
                            ft.Text(
                                "Recent",
                                size=FONT_SM,
                                weight=ft.FontWeight.W_600,
                                color=ft.Colors.ON_SURFACE_VARIANT,
                            ),
                        ],
                        spacing=6,
                    ),
                    ft.Column(items, spacing=4),
                ],
                spacing=8,
            ),
            margin=ft.Margin(left=0, top=SPACING_LG, right=0, bottom=0),
        )

    # ── Quick tools (for extract) ──
    quick_tools = None
    if active_tab == "extract":
        quick_tools = ft.Container(
            content=ft.Column(
                [
                    ft.Text(
                        "Try these tools",
                        size=FONT_SM,
                        weight=ft.FontWeight.W_600,
                        color=ft.Colors.ON_SURFACE_VARIANT,
                    ),
                    ft.Row(
                        [
                            ft.Container(
                                content=ft.Column(
                                    [
                                        ft.Icon(
                                            ft.Icons.TRANSLATE_ROUNDED,
                                            size=20,
                                            color=AppColors.PRIMARY,
                                        ),
                                        ft.Text(
                                            "Translate",
                                            size=10,
                                            color=ft.Colors.ON_SURFACE_VARIANT,
                                        ),
                                    ],
                                    horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                                    spacing=4,
                                ),
                                padding=12,
                                bgcolor=ft.Colors.SURFACE_CONTAINER_HIGHEST,
                                border_radius=BORDER_RADIUS_LG,
                                expand=True,
                                ink=True,
                                on_click=lambda _: _prefill_search(
                                    "translate ", "text"
                                ),
                            ),
                            ft.Container(
                                content=ft.Column(
                                    [
                                        ft.Icon(
                                            ft.Icons.MENU_BOOK_ROUNDED,
                                            size=20,
                                            color=AppColors.PRIMARY,
                                        ),
                                        ft.Text(
                                            "Define",
                                            size=10,
                                            color=ft.Colors.ON_SURFACE_VARIANT,
                                        ),
                                    ],
                                    horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                                    spacing=4,
                                ),
                                padding=12,
                                bgcolor=ft.Colors.SURFACE_CONTAINER_HIGHEST,
                                border_radius=BORDER_RADIUS_LG,
                                expand=True,
                                ink=True,
                                on_click=lambda _: _prefill_search("define ", "text"),
                            ),
                            ft.Container(
                                content=ft.Column(
                                    [
                                        ft.Icon(
                                            ft.Icons.QUESTION_ANSWER_ROUNDED,
                                            size=20,
                                            color=AppColors.PRIMARY,
                                        ),
                                        ft.Text(
                                            "Answers",
                                            size=10,
                                            color=ft.Colors.ON_SURFACE_VARIANT,
                                        ),
                                    ],
                                    horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                                    spacing=4,
                                ),
                                padding=12,
                                bgcolor=ft.Colors.SURFACE_CONTAINER_HIGHEST,
                                border_radius=BORDER_RADIUS_LG,
                                expand=True,
                                ink=True,
                                on_click=lambda _: _prefill_search("", "text"),
                            ),
                        ],
                        spacing=8,
                    ),
                ],
                spacing=8,
            ),
            margin=ft.Margin(left=0, top=SPACING_LG, right=0, bottom=0),
        )

    # ── Build content ──
    filter_row = ft.Row(
        controls=[backend_dropdown, time_dropdown] if active_tab != "extract" else [],
        alignment=ft.MainAxisAlignment.CENTER,
        spacing=SPACING_SM,
    )

    content = ft.SafeArea(
        content=ft.Column(
            [
                header,
                ft.Container(
                    content=ft.Column(
                        [
                            ft.Container(
                                content=ft.Column(
                                    [
                                        ft.Image(
                                            src="icon.png",
                                            width=56,
                                            height=56,
                                            fit=ft.BoxFit.CONTAIN,
                                        ),
                                        ft.Text(
                                            "Metasearch",
                                            size=FONT_SM,
                                            color=ft.Colors.ON_SURFACE_VARIANT,
                                        ),
                                    ],
                                    horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                                    spacing=4,
                                ),
                                padding=ft.Padding(0, SPACING_LG, 0, SPACING_MD),
                                alignment=ft.alignment.Alignment(0, 0),
                            ),
                            ft.Container(
                                content=ft.Column(
                                    [
                                        search_field,
                                        filter_row,
                                        ft.Row(
                                            [search_button],
                                            alignment=ft.MainAxisAlignment.CENTER,
                                        ),
                                    ],
                                    spacing=SPACING_SM,
                                    tight=True,
                                ),
                                padding=ft.Padding(
                                    left=SPACING_LG, top=0, right=SPACING_LG, bottom=0
                                ),
                            ),
                            ft.Container(
                                content=ft.Row(
                                    tab_buttons,
                                    alignment=ft.MainAxisAlignment.SPACE_EVENLY,
                                    spacing=2,
                                ),
                                padding=ft.Padding(
                                    left=12, top=SPACING_SM, right=12, bottom=0
                                ),
                                margin=ft.Margin(
                                    left=0, top=SPACING_SM, right=0, bottom=0
                                ),
                            ),
                        ],
                        spacing=0,
                    ),
                    gradient=AppStyles.brand_gradient(),
                    border_radius=ft.BorderRadius(
                        0, 0, BORDER_RADIUS_LG, BORDER_RADIUS_LG
                    ),
                ),
                ft.Container(
                    content=ft.Column(
                        [
                            recent_section if recent_section else ft.Container(),
                            quick_tools if quick_tools else ft.Container(),
                        ],
                        scroll=ft.ScrollMode.AUTO,
                        spacing=SPACING_SM,
                    ),
                    padding=ft.Padding(
                        left=SPACING_LG, top=0, right=SPACING_LG, bottom=0
                    ),
                    expand=True,
                ),
            ],
            spacing=0,
            scroll=ft.ScrollMode.AUTO,
        ),
    )

    return ft.View(
        route="/home",
        controls=[content],
        padding=0,
        spacing=0,
        bgcolor=ft.Colors.SURFACE,
    )
