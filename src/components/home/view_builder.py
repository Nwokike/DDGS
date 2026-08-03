from __future__ import annotations

from collections.abc import Callable

import flet as ft

from components.home.cards import _action_card, _feature_card, _step_row
from components.home.header import build_appbar, build_hero
from components.home.search_box import build_search_section
from core import theme, tokens
from core.state import state
from core.styles import build_banner_ad
from core.theme import AppColors
from services.storage_service import StorageService

SEARCH_TABS = [
    {
        "key": "text",
        "title": "Web Search",
        "desc": "Global Metasearch",
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

    def _rebuild():
        on_navigate(page.route)

    async def do_search(q: str | None = None):
        query = q or (
            search_field_ref.current.value if search_field_ref.current else ""
        )
        if not query or not query.strip():
            return
        query = query.strip()
        state.current_query = query
        on_search(query, active_tab)

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

    appbar = build_appbar(page, on_navigate, storage, _rebuild)
    hero = build_hero()

    search_section = build_search_section(
        page, active_tab, search_field_ref, do_search, storage, is_dark
    )

    # ── Category Grid selectors ──
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
                ft.Text(
                    "Tap a category to change what you're searching for",
                    size=tokens.FONT_XS,
                    color=ft.Colors.ON_SURFACE_VARIANT,
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
                            "No filter bubbles, no data harvesting.",
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
                    "No profiling, no filter bubbles.",
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

    content = ft.Column(
        controls=[
            hero,
            search_section,
            quick_actions,
            build_banner_ad(page),
            privacy_banner,
            recent_section if recent_section else ft.Container(),
            features_section,
            build_banner_ad(page),
            how_it_works,
            ft.Container(height=16),
            no_account_info,
            build_banner_ad(page),
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
