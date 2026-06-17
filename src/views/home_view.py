"""Home view — search bar + 6 DDGS tabs + backend selector."""

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
from core.theme import AppColors
from core.tokens import (
    FONT_XS,
    FONT_SM,
    FONT_MD,
    FONT_XXL,
    SPACING_XS,
    SPACING_SM,
    SPACING_MD,
    SPACING_LG,
    SPACING_XL,
    BORDER_RADIUS_MD,
    BORDER_RADIUS_FULL,
    ICON_MD,
    ICON_XL,
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

    # ── Search input ──
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
        content_padding=ft.padding.symmetric(horizontal=20, vertical=14),
        border_radius=BORDER_RADIUS_FULL,
        border=ft.InputBorder.OUTLINE,
        filled=True,
        fill_color=ft.Colors.SURFACE_CONTAINER_HIGHEST
        if page.theme_mode == ft.ThemeMode.DARK
        else ft.Colors.SURFACE,
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
    search_field.suffix = ft.IconButton(
        icon=ft.Icons.CLEAR_ROUNDED,
        icon_size=ICON_MD,
        on_click=lambda _: setattr(search_field, "value", "") or search_field.update(),
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
                    controls=[
                        ft.Icon(
                            name=tab["icon"],
                            size=ICON_MD,
                            color=AppColors.PRIMARY if is_active else AppColors.OUTLINE,
                        ),
                        ft.Text(
                            tab["label"],
                            size=FONT_XS,
                            weight=ft.FontWeight.W_600
                            if is_active
                            else ft.FontWeight.W_400,
                            color=AppColors.PRIMARY if is_active else None,
                        ),
                    ],
                    horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                    spacing=SPACING_XS,
                    tight=True,
                ),
                padding=ft.padding.symmetric(
                    horizontal=SPACING_MD, vertical=SPACING_SM
                ),
                border_radius=BORDER_RADIUS_MD,
                bgcolor=AppColors.PRIMARY_LIGHT if is_active else None,
                ink=True,
                on_click=lambda _, k=tab["key"]: on_tab_change(k),
            )
        )

    # ── Backend / Time filter row (only for search types) ──
    backend_options = BACKEND_OPTIONS_MAP.get(active_tab, BACKEND_OPTIONS_TEXT)
    current_backend = state.backend or "auto"

    backend_dropdown = ft.Dropdown(
        value=current_backend
        if any(b["key"] == current_backend for b in backend_options)
        else "auto",
        options=[ft.dropdown.Option(b["key"], b["label"]) for b in backend_options],
        on_change=lambda e: page.run_task(_set_backend, e.control.value),
        filled=True,
        text_size=FONT_XS,
        content_padding=ft.padding.symmetric(
            horizontal=SPACING_MD, vertical=SPACING_SM
        ),
        border_radius=BORDER_RADIUS_MD,
        width=150,
    )

    time_dropdown = ft.Dropdown(
        value=state.timelimit or "",
        options=[ft.dropdown.Option(o["key"], o["label"]) for o in TIMELIMIT_OPTIONS],
        on_change=lambda e: page.run_task(_set_timelimit, e.control.value),
        filled=True,
        text_size=FONT_XS,
        content_padding=ft.padding.symmetric(
            horizontal=SPACING_MD, vertical=SPACING_SM
        ),
        border_radius=BORDER_RADIUS_MD,
        width=130,
    )

    async def _set_backend(val: str):
        state.backend = val
        await storage.set_backend(val)
        logger.debug(f"[{LOG_TAG}] Backend: {val}")

    async def _set_timelimit(val: str):
        state.timelimit = val
        await storage.set_timelimit(val)
        logger.debug(f"[{LOG_TAG}] Timelimit: {val}")

    # ── Search button ──
    search_button = ft.FilledButton(
        content=ft.Row(
            controls=[
                ft.Icon(ft.Icons.SEARCH_ROUNDED, size=ICON_MD),
                ft.Text("Search", size=FONT_MD, weight=ft.FontWeight.W_600),
            ],
            spacing=SPACING_SM,
        ),
        on_click=lambda _: do_search(),
        style=ft.ButtonStyle(
            shape=ft.RoundedRectangleBorder(radius=BORDER_RADIUS_FULL),
            padding=ft.padding.symmetric(horizontal=SPACING_XL, vertical=SPACING_MD),
        ),
    )

    # ── Recent searches ──
    recent_section = None
    if state.search_history:
        items = []
        for entry in state.search_history[:5]:
            q = entry.get("query", "")
            st = entry.get("search_type", "text")
            ts = entry.get("timestamp", "")
            tab_info = next((t for t in SEARCH_TABS if t["key"] == st), SEARCH_TABS[0])
            items.append(
                ft.ListTile(
                    leading=ft.Icon(
                        tab_info["icon"], size=ICON_MD, color=AppColors.OUTLINE
                    ),
                    title=ft.Text(q, size=FONT_MD, no_wrap=False, max_lines=1),
                    subtitle=ft.Text(
                        f"{tab_info['label']} · {ts}",
                        size=FONT_XS,
                        color=ft.Colors.ON_SURFACE_VARIANT,
                    ),
                    on_click=lambda _, qq=q: do_search(qq),
                    dense=True,
                )
            )
        recent_section = ft.Container(
            content=ft.Column(
                controls=[
                    ft.Text(
                        "Recent",
                        size=FONT_SM,
                        weight=ft.FontWeight.W_600,
                        color=ft.Colors.ON_SURFACE_VARIANT,
                    ),
                    ft.Column(controls=items, spacing=0),
                ],
                spacing=SPACING_SM,
            ),
            margin=ft.margin.only(top=SPACING_LG),
        )

    # ── Build content ──
    filter_row = ft.Row(
        controls=[backend_dropdown, time_dropdown] if active_tab != "extract" else [],
        alignment=ft.MainAxisAlignment.CENTER,
        spacing=SPACING_SM,
    )

    content = ft.SafeArea(
        content=ft.Column(
            controls=[
                # Header
                ft.Container(
                    content=ft.Column(
                        controls=[
                            ft.Icon(
                                ft.Icons.TRAVEL_EXPLORE_ROUNDED,
                                size=ICON_XL * 2,
                                color=AppColors.PRIMARY,
                            ),
                            ft.Text(
                                "DDGS",
                                size=FONT_XXL,
                                weight=ft.FontWeight.BOLD,
                                color=AppColors.PRIMARY,
                            ),
                            ft.Text(
                                "DuckDuckGo + metasearch",
                                size=FONT_SM,
                                color=ft.Colors.ON_SURFACE_VARIANT,
                            ),
                        ],
                        horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                        spacing=SPACING_XS,
                    ),
                    padding=ft.padding.only(top=SPACING_XL, bottom=SPACING_MD),
                ),
                # Search bar
                ft.Container(
                    content=ft.Column(
                        controls=[
                            search_field,
                            filter_row,
                            ft.Row(
                                controls=[search_button],
                                alignment=ft.MainAxisAlignment.CENTER,
                            ),
                        ],
                        spacing=SPACING_SM,
                        tight=True,
                    ),
                    padding=ft.padding.symmetric(horizontal=SPACING_LG),
                ),
                # Tabs
                ft.Container(
                    content=ft.Row(
                        controls=tab_buttons,
                        alignment=ft.MainAxisAlignment.SPACE_EVENLY,
                        spacing=SPACING_XS,
                    ),
                    padding=ft.padding.symmetric(horizontal=SPACING_SM),
                    margin=ft.margin.symmetric(vertical=SPACING_SM),
                ),
                # Recent
                ft.Container(
                    content=ft.Column(
                        controls=[recent_section] if recent_section else [],
                        scroll=ft.ScrollMode.AUTO,
                        spacing=SPACING_SM,
                    ),
                    padding=ft.padding.symmetric(horizontal=SPACING_LG),
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
        bgcolor=AppColors.BACKGROUND,
    )
