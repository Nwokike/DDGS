from __future__ import annotations

from typing import Callable

import flet as ft

from core import theme, tokens
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
from services.storage_service import StorageService
from core.utils import logger

LOG_TAG = "HomeView"

SEARCH_TABS = [
    {
        "key": "text",
        "title": "Web Search",
        "desc": "DuckDuckGo Metasearch",
        "icon": ft.Icons.SEARCH_ROUNDED,
        "color": AppColors.PRIMARY,
    },
    {
        "key": "images",
        "title": "Images",
        "desc": "Visual media search",
        "icon": ft.Icons.IMAGE_ROUNDED,
        "color": AppColors.PRIMARY_LIGHT,
    },
    {
        "key": "videos",
        "title": "Videos",
        "desc": "Video streaming indexing",
        "icon": ft.Icons.PLAY_CIRCLE_ROUNDED,
        "color": AppColors.ACCENT,
    },
    {
        "key": "news",
        "title": "News Feed",
        "desc": "Current global stories",
        "icon": ft.Icons.ARTICLE_ROUNDED,
        "color": AppColors.SUCCESS,
    },
    {
        "key": "books",
        "title": "Books",
        "desc": "Linguistic & literature",
        "icon": ft.Icons.BOOK_ROUNDED,
        "color": AppColors.WARNING,
    },
    {
        "key": "extract",
        "title": "Fetch Page",
        "desc": "Read any URL's content",
        "icon": ft.Icons.LANGUAGE_ROUNDED,
        "color": AppColors.PRIMARY_DARK,
    },
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
    is_dark = page.theme_mode == ft.ThemeMode.DARK or (
        page.theme_mode == ft.ThemeMode.SYSTEM
        and page.platform_brightness == ft.Brightness.DARK
    )
    active_tab = state.default_tab
    search_field_ref = ft.Ref[ft.TextField]()

    # ── Search submission logic ──
    def do_search(q: str | None = None):
        query = q or (
            search_field_ref.current.value if search_field_ref.current else ""
        )
        if not query or not query.strip():
            return
        query = query.strip()
        state.current_query = query
        on_search(query, active_tab)

    # ── Quick action helpers ──
    def _prefill_search(q: str, tab: str | None = None):
        nonlocal active_tab
        if search_field_ref.current:
            search_field_ref.current.value = q
        if tab and tab != active_tab:
            active_tab = tab
            state.default_tab = tab
            page.run_task(storage.set_default_tab, tab)
            _rebuild()
        page.run_task(do_search, q)

    async def _paste_clipboard(e):
        try:
            clipboard = ft.Clipboard()
            text = await clipboard.get()
            if text and search_field_ref.current:
                search_field_ref.current.value = text.strip()
                search_field_ref.current.update()
        except Exception as ex:
            logger.warning(f"Clipboard paste failed: {ex}")

    def _rebuild():
        on_navigate(page.route)

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
        _rebuild()

    def _get_theme_icon():
        if page.theme_mode == ft.ThemeMode.DARK:
            return ft.Icons.DARK_MODE_ROUNDED
        elif page.theme_mode == ft.ThemeMode.LIGHT:
            return ft.Icons.LIGHT_MODE_ROUNDED
        return ft.Icons.SETTINGS_SYSTEM_DAYDREAM_ROUNDED

    # ── App Bar ──
    appbar = ft.AppBar(
        leading=ft.Container(
            content=ft.Row(
                [
                    ft.Image(
                        src="icon.svg", width=28, height=28, color=AppColors.PRIMARY
                    ),
                    ft.Text(
                        "DDGS",
                        size=tokens.FONT_LG,
                        weight=ft.FontWeight.BOLD,
                        font_family="Outfit",
                    ),
                ],
                spacing=8,
                tight=True,
            ),
            padding=ft.Padding(12, 0, 0, 0),
        ),
        leading_width=120,
        actions=[
            ft.IconButton(
                icon=_get_theme_icon(),
                icon_size=20,
                on_click=_toggle_theme,
                tooltip="Toggle Theme",
            ),
            ft.IconButton(
                icon=ft.Icons.SETTINGS_ROUNDED,
                icon_size=20,
                on_click=lambda e: on_navigate("/settings"),
                tooltip="Open Settings",
            ),
            ft.Container(width=8),
        ],
        bgcolor=ft.Colors.TRANSPARENT,
        elevation=0,
    )

    # ── Header Hero Section (Matching SpanInsight's build_brand_header) ──
    hero = ft.Container(
        content=ft.Column(
            [
                ft.Container(height=tokens.SPACE_LG),
                ft.Image(
                    src="icon.svg",
                    width=72,
                    height=72,
                    color=AppColors.PRIMARY,
                    fit=ft.BoxFit.CONTAIN,
                ),
                ft.Container(height=tokens.SPACE_SM),
                ft.Text(
                    "Search the web privately.\nFetch any webpage instantly.",
                    size=tokens.FONT_SM,
                    color=ft.Colors.ON_SURFACE_VARIANT,
                    text_align=ft.TextAlign.CENTER,
                    font_family="Outfit",
                    weight=ft.FontWeight.W_500,
                ),
                ft.Container(height=tokens.SPACE_XL),
            ],
            horizontal_alignment=ft.CrossAxisAlignment.CENTER,
            spacing=0,
        ),
    )

    # ── Search textfield input ──
    search_field = ft.TextField(
        ref=search_field_ref,
        value=state.current_query,
        hint_text="Search DuckDuckGo..."
        if active_tab != "extract"
        else "Paste a URL to fetch its content...",
        hint_style=ft.TextStyle(
            size=tokens.FONT_MD,
            weight=ft.FontWeight.W_400,
            italic=True,
            color=ft.Colors.with_opacity(
                0.4, AppColors.DARK_TEXT if is_dark else AppColors.LIGHT_TEXT
            ),
        ),
        text_style=ft.TextStyle(size=tokens.FONT_MD, weight=ft.FontWeight.W_500),
        prefix_icon=ft.Icons.SEARCH_ROUNDED
        if active_tab != "extract"
        else ft.Icons.LINK_ROUNDED,
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
        on_submit=lambda e: do_search(),
        suffix=ft.IconButton(
            icon=ft.Icons.PASTE_ROUNDED,
            icon_size=18,
            icon_color=AppColors.PRIMARY,
            tooltip="Paste from clipboard",
            on_click=_paste_clipboard,
        ),
    )

    # ── Dropdown filters backend/timelimit row ──
    async def _set_backend(val: str):
        state.backend = val
        await storage.set_backend(val)

    async def _set_timelimit(val: str):
        state.timelimit = val
        await storage.set_timelimit(val)

    backend_options = BACKEND_OPTIONS_MAP.get(active_tab, BACKEND_OPTIONS_TEXT)
    current_backend = state.backend or "auto"

    backend_dropdown = ft.Dropdown(
        value=current_backend
        if any(b["key"] == current_backend for b in backend_options)
        else "auto",
        options=[ft.dropdown.Option(b["key"], b["label"]) for b in backend_options],
        on_select=lambda e: page.run_task(_set_backend, e.control.value),
        filled=True,
        text_size=tokens.FONT_XS,
        content_padding=ft.Padding(left=12, top=6, right=12, bottom=6),
        border_radius=tokens.RADIUS_MD,
        width=150,
        height=40,
    )

    time_dropdown = ft.Dropdown(
        value=state.timelimit or "",
        options=[ft.dropdown.Option(o["key"], o["label"]) for o in TIMELIMIT_OPTIONS],
        on_select=lambda e: page.run_task(_set_timelimit, e.control.value),
        filled=True,
        text_size=tokens.FONT_XS,
        content_padding=ft.Padding(left=12, top=6, right=12, bottom=6),
        border_radius=tokens.RADIUS_MD,
        width=130,
        height=40,
    )

    filter_row = ft.Row(
        controls=[backend_dropdown, time_dropdown] if active_tab != "extract" else [],
        alignment=ft.MainAxisAlignment.CENTER,
        spacing=tokens.SPACE_SM,
    )

    search_button = ft.FilledButton(
        content=ft.Row(
            [
                ft.Icon(
                    ft.Icons.SEARCH_ROUNDED, size=tokens.ICON_MD, color=ft.Colors.WHITE
                ),
                ft.Text(
                    "Execute Search",
                    size=tokens.FONT_MD,
                    weight=ft.FontWeight.W_600,
                    color=ft.Colors.WHITE,
                    font_family="Outfit",
                ),
            ],
            spacing=8,
            tight=True,
        ),
        on_click=lambda _: do_search(),
        style=ft.ButtonStyle(
            shape=ft.RoundedRectangleBorder(radius=tokens.RADIUS_PILL),
            bgcolor=AppColors.PRIMARY,
            padding=ft.Padding(32, 14, 32, 14),
        ),
    )

    search_section = ft.Container(
        content=ft.Column(
            [
                search_field,
                filter_row,
                ft.Row([search_button], alignment=ft.MainAxisAlignment.CENTER),
            ],
            spacing=tokens.SPACE_MD,
            tight=True,
            horizontal_alignment=ft.CrossAxisAlignment.STRETCH,
        ),
        padding=ft.Padding(tokens.SPACE_LG, 0, tokens.SPACE_LG, tokens.SPACE_LG),
    )

    # ── Category Grid selectors (Reusing SpanInsight's _action_card design) ──
    def on_tab_change(tab_key: str):
        nonlocal active_tab
        active_tab = tab_key
        state.default_tab = tab_key
        page.run_task(storage.set_default_tab, tab_key)
        _rebuild()

    grid_cards_row1 = []
    grid_cards_row2 = []

    for i, tab in enumerate(SEARCH_TABS):
        is_active = tab["key"] == active_tab
        card = _action_card(
            icon=tab["icon"],
            title=tab["title"],
            subtitle=tab["desc"],
            color=tab["color"],
            is_active=is_active,
            on_click=lambda _, k=tab["key"]: on_tab_change(k),
            page=page,
        )
        if i < 3:
            grid_cards_row1.append(card)
        else:
            grid_cards_row2.append(card)

    quick_actions = ft.Container(
        content=ft.Column(
            controls=[
                ft.Text(
                    "Search Categories",
                    size=tokens.FONT_MD,
                    weight=ft.FontWeight.W_600,
                    font_family="Outfit",
                ),
                ft.Container(height=tokens.SPACE_SM),
                ft.Row(controls=grid_cards_row1, spacing=tokens.SPACE_MD),
                ft.Container(height=tokens.SPACE_MD),
                ft.Row(controls=grid_cards_row2, spacing=tokens.SPACE_MD),
            ],
            spacing=0,
        ),
        padding=ft.Padding(tokens.SPACE_LG, 0, tokens.SPACE_LG, tokens.SPACE_LG),
    )

    # ── Privacy Banner ──
    privacy_banner = ft.Container(
        content=ft.Row(
            controls=[
                ft.Icon(
                    ft.Icons.SHIELD_ROUNDED,
                    size=tokens.ICON_MD,
                    color=AppColors.PRIMARY,
                ),
                ft.Column(
                    controls=[
                        ft.Text(
                            "100% Privacy-First",
                            size=tokens.FONT_SM,
                            weight=ft.FontWeight.W_600,
                            font_family="Outfit",
                        ),
                        ft.Text(
                            "Your searches are never tracked, profiled, or stored. "
                            "No ads, no filter bubbles, no data harvesting.",
                            size=tokens.FONT_XS,
                            color=ft.Colors.ON_SURFACE_VARIANT,
                            font_family="Outfit",
                            style=ft.TextStyle(height=1.3),
                        ),
                    ],
                    spacing=tokens.SPACE_XXS,
                    expand=True,
                ),
            ],
            spacing=tokens.SPACE_MD,
            vertical_alignment=ft.CrossAxisAlignment.CENTER,
        ),
        padding=ft.Padding(
            tokens.SPACE_LG, tokens.SPACE_MD, tokens.SPACE_LG, tokens.SPACE_MD
        ),
        margin=ft.Margin(tokens.SPACE_LG, 0, tokens.SPACE_LG, tokens.SPACE_LG),
        border_radius=tokens.RADIUS_LG,
        bgcolor=ft.Colors.with_opacity(0.06, AppColors.PRIMARY),
        border=ft.Border.all(1, ft.Colors.with_opacity(0.15, AppColors.PRIMARY)),
    )

    # ── Recent Searches section (Reused SpanInsight's _feature_card design) ──
    recent_section = None
    if state.search_history:
        history_cards = []
        for entry in state.search_history[:4]:
            q = entry.get("query", "")
            st = entry.get("search_type", "text")
            ts = entry.get("timestamp", "")
            tab_info = next((t for t in SEARCH_TABS if t["key"] == st), SEARCH_TABS[0])

            card = _feature_card(
                icon=tab_info["icon"],
                title=q,
                desc=f"{tab_info['title']} \u00b7 {ts}",
                color=tab_info["color"],
                on_click=lambda _, qq=q, stt=st: _prefill_search(qq, stt),
                page=page,
            )
            history_cards.append(card)

        recent_section = ft.Container(
            content=ft.Column(
                [
                    ft.Text(
                        "Recent Search Queries",
                        size=tokens.FONT_MD,
                        weight=ft.FontWeight.W_600,
                        font_family="Outfit",
                    ),
                    ft.Container(height=tokens.SPACE_SM),
                    ft.Column(history_cards, spacing=tokens.SPACE_SM),
                ],
                spacing=0,
            ),
            padding=ft.Padding(tokens.SPACE_LG, 0, tokens.SPACE_LG, tokens.SPACE_LG),
        )

    # ── Quick Action Chips (always visible) ──
    def _switch_to_extract(_):
        nonlocal active_tab
        active_tab = "extract"
        state.default_tab = "extract"
        page.run_task(storage.set_default_tab, "extract")
        _rebuild()

    def _switch_to_news(_):
        nonlocal active_tab
        active_tab = "news"
        state.default_tab = "news"
        page.run_task(storage.set_default_tab, "news")
        _rebuild()

    quick_chips = ft.Container(
        content=ft.Column(
            [
                ft.Text(
                    "Quick Actions",
                    size=tokens.FONT_MD,
                    weight=ft.FontWeight.W_600,
                    font_family="Outfit",
                ),
                ft.Container(height=tokens.SPACE_SM),
                ft.Row(
                    controls=[
                        ft.OutlinedButton(
                            content=ft.Row(
                                [
                                    ft.Icon(
                                        ft.Icons.LANGUAGE_ROUNDED,
                                        size=14,
                                        color=AppColors.PRIMARY_DARK,
                                    ),
                                    ft.Text(
                                        "Fetch a URL",
                                        size=tokens.FONT_XS,
                                        weight=ft.FontWeight.W_600,
                                        font_family="Outfit",
                                    ),
                                ],
                                spacing=6,
                                tight=True,
                            ),
                            on_click=_switch_to_extract,
                            style=ft.ButtonStyle(
                                shape=ft.RoundedRectangleBorder(
                                    radius=tokens.RADIUS_PILL
                                ),
                                side=ft.BorderSide(1, AppColors.PRIMARY_DARK),
                                padding=ft.Padding(14, 8, 14, 8),
                            ),
                        ),
                        ft.OutlinedButton(
                            content=ft.Row(
                                [
                                    ft.Icon(
                                        ft.Icons.TRANSLATE_ROUNDED,
                                        size=14,
                                        color=AppColors.PRIMARY,
                                    ),
                                    ft.Text(
                                        "Translate",
                                        size=tokens.FONT_XS,
                                        weight=ft.FontWeight.W_600,
                                        font_family="Outfit",
                                    ),
                                ],
                                spacing=6,
                                tight=True,
                            ),
                            on_click=lambda _: _prefill_search("translate ", "text"),
                            style=ft.ButtonStyle(
                                shape=ft.RoundedRectangleBorder(
                                    radius=tokens.RADIUS_PILL
                                ),
                                side=ft.BorderSide(1, AppColors.PRIMARY),
                                padding=ft.Padding(14, 8, 14, 8),
                            ),
                        ),
                        ft.OutlinedButton(
                            content=ft.Row(
                                [
                                    ft.Icon(
                                        ft.Icons.MENU_BOOK_ROUNDED,
                                        size=14,
                                        color=AppColors.PRIMARY_LIGHT,
                                    ),
                                    ft.Text(
                                        "Define",
                                        size=tokens.FONT_XS,
                                        weight=ft.FontWeight.W_600,
                                        font_family="Outfit",
                                    ),
                                ],
                                spacing=6,
                                tight=True,
                            ),
                            on_click=lambda _: _prefill_search("define ", "text"),
                            style=ft.ButtonStyle(
                                shape=ft.RoundedRectangleBorder(
                                    radius=tokens.RADIUS_PILL
                                ),
                                side=ft.BorderSide(1, AppColors.PRIMARY_LIGHT),
                                padding=ft.Padding(14, 8, 14, 8),
                            ),
                        ),
                        ft.OutlinedButton(
                            content=ft.Row(
                                [
                                    ft.Icon(
                                        ft.Icons.ARTICLE_ROUNDED,
                                        size=14,
                                        color=AppColors.SUCCESS,
                                    ),
                                    ft.Text(
                                        "Latest News",
                                        size=tokens.FONT_XS,
                                        weight=ft.FontWeight.W_600,
                                        font_family="Outfit",
                                    ),
                                ],
                                spacing=6,
                                tight=True,
                            ),
                            on_click=_switch_to_news,
                            style=ft.ButtonStyle(
                                shape=ft.RoundedRectangleBorder(
                                    radius=tokens.RADIUS_PILL
                                ),
                                side=ft.BorderSide(1, AppColors.SUCCESS),
                                padding=ft.Padding(14, 8, 14, 8),
                            ),
                        ),
                    ],
                    wrap=True,
                    spacing=tokens.SPACE_SM,
                    run_spacing=tokens.SPACE_SM,
                ),
            ],
            spacing=0,
        ),
        padding=ft.Padding(tokens.SPACE_LG, 0, tokens.SPACE_LG, tokens.SPACE_LG),
    )

    # ── What DDGS Can Do (Feature Showcase) ──
    features_section = ft.Container(
        content=ft.Column(
            controls=[
                ft.Text(
                    "What DDGS Can Do",
                    size=tokens.FONT_MD,
                    weight=ft.FontWeight.W_600,
                    font_family="Outfit",
                ),
                ft.Container(height=tokens.SPACE_SM),
                _feature_card(
                    ft.Icons.SEARCH_ROUNDED,
                    "Private Web Search",
                    "Search across multiple engines without being tracked. "
                    "No ads, no profiling, no filter bubbles.",
                    AppColors.PRIMARY,
                    page=page,
                ),
                ft.Container(height=tokens.SPACE_SM),
                _feature_card(
                    ft.Icons.LANGUAGE_ROUNDED,
                    "Instant Page Fetch",
                    "Paste any URL and extract the full text content instantly — "
                    "articles, documentation, recipes, anything. "
                    "Save as markdown or plain text.",
                    AppColors.PRIMARY_DARK,
                    page=page,
                ),
                ft.Container(height=tokens.SPACE_SM),
                _feature_card(
                    ft.Icons.IMAGE_ROUNDED,
                    "Image & Video Discovery",
                    "Find images and videos from across the web. "
                    "Download directly to your device with one tap.",
                    AppColors.PRIMARY_LIGHT,
                    page=page,
                ),
                ft.Container(height=tokens.SPACE_SM),
                _feature_card(
                    ft.Icons.ARTICLE_ROUNDED,
                    "Live News Feed",
                    "Get breaking news from every source, uncensored "
                    "and unfiltered by algorithm bias.",
                    AppColors.SUCCESS,
                    page=page,
                ),
                ft.Container(height=tokens.SPACE_SM),
                _feature_card(
                    ft.Icons.BOOK_ROUNDED,
                    "Book & Literature Search",
                    "Find books, papers, and academic texts from "
                    "global archives and open libraries.",
                    AppColors.WARNING,
                    page=page,
                ),
            ],
            spacing=0,
        ),
        padding=ft.Padding(tokens.SPACE_LG, 0, tokens.SPACE_LG, tokens.SPACE_LG),
    )

    # ── How It Works ──
    how_it_works = ft.Container(
        content=ft.Column(
            controls=[
                ft.Text(
                    "How It Works",
                    size=tokens.FONT_MD,
                    weight=ft.FontWeight.W_600,
                    font_family="Outfit",
                ),
                ft.Container(height=tokens.SPACE_SM),
                _step_row(
                    "1",
                    "Choose",
                    "Pick what you're looking for — web pages, images, videos, news, or books",
                ),
                _step_row(
                    "2",
                    "Search",
                    "Type your query and hit search. Adjust filters if you want",
                ),
                _step_row(
                    "3",
                    "Done",
                    "Get private results instantly. Download, save, or open in browser",
                ),
            ],
            spacing=tokens.SPACE_MD,
        ),
        padding=ft.Padding(tokens.SPACE_LG, 0, tokens.SPACE_LG, tokens.SPACE_LG),
    )

    # ── No Account Required Banner ──
    no_account_info = ft.Container(
        content=ft.Row(
            controls=[
                ft.Icon(ft.Icons.BOLT_ROUNDED, size=20, color=AppColors.ACCENT),
                ft.Column(
                    [
                        ft.Text(
                            "Unlimited Searches, No Account Required",
                            size=tokens.FONT_SM,
                            weight=ft.FontWeight.W_600,
                            font_family="Outfit",
                        ),
                        ft.Text(
                            "Search as much as you want. We never ask for "
                            "sign-up, email, or personal data.",
                            size=tokens.FONT_XS,
                            color=ft.Colors.ON_SURFACE_VARIANT,
                            font_family="Outfit",
                            style=ft.TextStyle(height=1.3),
                        ),
                    ],
                    spacing=2,
                    expand=True,
                ),
            ],
            spacing=tokens.SPACE_MD,
            vertical_alignment="center",
        ),
        padding=ft.Padding(
            tokens.SPACE_LG, tokens.SPACE_MD, tokens.SPACE_LG, tokens.SPACE_MD
        ),
        margin=ft.Margin(tokens.SPACE_LG, 0, tokens.SPACE_LG, tokens.SPACE_LG),
        border_radius=tokens.RADIUS_LG,
        bgcolor=ft.Colors.with_opacity(0.06, AppColors.ACCENT),
        border=ft.Border.all(1, ft.Colors.with_opacity(0.15, AppColors.ACCENT)),
    )

    # ── Final Page View layout ──
    content = ft.Column(
        controls=[
            hero,
            search_section,
            quick_actions,
            quick_chips,
            privacy_banner,
            recent_section if recent_section else ft.Container(),
            features_section,
            how_it_works,
            ft.Container(height=16),
            no_account_info,
            ft.Container(height=80),
        ],
        scroll=ft.ScrollMode.AUTO,
        expand=True,
    )

    return ft.View(
        route="/home",
        controls=[
            ft.SafeArea(
                content=ft.Container(
                    content=content,
                    gradient=theme.AppStyles.brand_gradient(page),
                    expand=True,
                ),
                expand=True,
            )
        ],
        appbar=appbar,
        padding=0,
        spacing=0,
    )


# ── Action Card (Reused from SpanInsight) ──
def _action_card(
    icon: str,
    title: str,
    subtitle: str,
    color: str,
    is_active: bool,
    on_click=None,
    page: ft.Page | None = None,
) -> ft.Container:
    """Build a quick action card matching SpanInsight's layout."""
    border_color = AppColors.PRIMARY if is_active else theme.adaptive_glass_border(page)
    bg_color = (
        ft.Colors.with_opacity(0.12, AppColors.PRIMARY)
        if is_active
        else theme.adaptive_glass_bg(page)
    )

    return ft.Container(
        content=ft.Column(
            controls=[
                ft.Container(
                    content=ft.Icon(icon, size=24, color=color),
                    width=44,
                    height=44,
                    border_radius=12,
                    bgcolor=ft.Colors.with_opacity(0.1, color),
                    alignment=ft.Alignment.CENTER,
                ),
                ft.Text(
                    title,
                    size=12,
                    weight=ft.FontWeight.W_600,
                    font_family="Outfit",
                    max_lines=1,
                    overflow="ellipsis",
                ),
                ft.Text(
                    subtitle,
                    size=9,
                    color=ft.Colors.ON_SURFACE_VARIANT,
                    font_family="Outfit",
                    max_lines=1,
                    overflow="ellipsis",
                ),
            ],
            spacing=4,
            horizontal_alignment=ft.CrossAxisAlignment.CENTER,
        ),
        expand=True,
        padding=12,
        border_radius=16,
        bgcolor=bg_color,
        border=ft.Border.all(1.5 if is_active else 1, border_color),
        on_click=on_click,
        ink=True,
    )


# ── Feature Card (Reused from SpanInsight) ──
def _feature_card(
    icon: str,
    title: str,
    desc: str,
    color: str,
    on_click=None,
    page: ft.Page | None = None,
) -> ft.Container:
    """Build a feature card row matching SpanInsight's layout."""
    return ft.Container(
        content=ft.Row(
            controls=[
                ft.Container(
                    content=ft.Icon(icon, size=20, color=color),
                    width=38,
                    height=38,
                    border_radius=10,
                    bgcolor=ft.Colors.with_opacity(0.1, color),
                    alignment=ft.Alignment.CENTER,
                ),
                ft.Column(
                    controls=[
                        ft.Text(
                            title,
                            size=tokens.FONT_SM,
                            weight=ft.FontWeight.W_600,
                            font_family="Outfit",
                            max_lines=1,
                            overflow="ellipsis",
                        ),
                        ft.Text(
                            desc,
                            size=tokens.FONT_XS,
                            color=ft.Colors.ON_SURFACE_VARIANT,
                            max_lines=2,
                            overflow="ellipsis",
                            font_family="Outfit",
                        ),
                    ],
                    spacing=2,
                    expand=True,
                ),
            ],
            spacing=tokens.SPACE_MD,
            vertical_alignment="center",
        ),
        padding=12,
        border_radius=12,
        bgcolor=theme.adaptive_glass_bg(page),
        border=ft.Border.all(1, theme.adaptive_glass_border(page)),
        on_click=on_click,
        ink=on_click is not None,
    )


# ── Step Row (Reused from SpanInsight) ──
def _step_row(number: str, title: str, desc: str) -> ft.Row:
    """Build a numbered step row matching SpanInsight's layout."""
    return ft.Row(
        controls=[
            ft.Container(
                content=ft.Text(
                    number,
                    size=tokens.FONT_SM,
                    weight=ft.FontWeight.W_700,
                    color=ft.Colors.WHITE,
                    text_align=ft.TextAlign.CENTER,
                    font_family="Outfit",
                ),
                width=26,
                height=26,
                border_radius=13,
                bgcolor=AppColors.PRIMARY,
                alignment=ft.Alignment.CENTER,
            ),
            ft.Column(
                controls=[
                    ft.Text(
                        title,
                        size=tokens.FONT_SM,
                        weight=ft.FontWeight.W_600,
                        font_family="Outfit",
                    ),
                    ft.Text(
                        desc,
                        size=tokens.FONT_XS,
                        color=ft.Colors.ON_SURFACE_VARIANT,
                        font_family="Outfit",
                    ),
                ],
                spacing=tokens.SPACE_XXS,
                expand=True,
            ),
        ],
        spacing=tokens.SPACE_MD,
        vertical_alignment=ft.CrossAxisAlignment.CENTER,
    )
