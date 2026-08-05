"""HomeScreen — compact search-first dashboard.

Search bar above the fold, compact category chips, recent searches,
and privacy banner.  Marketing content moved to onboarding only.
"""

from __future__ import annotations

import flet as ft
from flet import Control

from contexts.app_state_ctx import AppStateCtx
from contexts.controller_ctx import ControllerMethodsCtx
from core import theme, tokens
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
from core.styles import build_banner_ad
from core.theme import AppColors
from core.utils import logger

# ── Constants ─────────────────────────────────────────────────────────

BACKEND_OPTIONS_MAP = {
    "text": BACKEND_OPTIONS_TEXT,
    "images": BACKEND_OPTIONS_IMAGES,
    "videos": BACKEND_OPTIONS_VIDEOS,
    "news": BACKEND_OPTIONS_NEWS,
    "books": BACKEND_OPTIONS_BOOKS,
}

SEARCH_TABS = [
    {
        "key": "text",
        "label": "Web",
        "icon": ft.Icons.SEARCH_ROUNDED,
        "color": AppColors.PRIMARY,
    },
    {
        "key": "images",
        "label": "Images",
        "icon": ft.Icons.IMAGE_ROUNDED,
        "color": AppColors.PRIMARY_LIGHT,
    },
    {
        "key": "videos",
        "label": "Videos",
        "icon": ft.Icons.PLAY_CIRCLE_ROUNDED,
        "color": AppColors.ACCENT,
    },
    {
        "key": "news",
        "label": "News",
        "icon": ft.Icons.ARTICLE_ROUNDED,
        "color": AppColors.SUCCESS,
    },
    {
        "key": "books",
        "label": "Books",
        "icon": ft.Icons.BOOK_ROUNDED,
        "color": AppColors.WARNING,
    },
    {
        "key": "extract",
        "label": "Extract",
        "icon": ft.Icons.LANGUAGE_ROUNDED,
        "color": AppColors.PRIMARY_DARK,
    },
]

_HINT_MAP = {
    "text": "Search the web...",
    "images": "Search for images...",
    "videos": "Search for videos...",
    "news": "Search for news...",
    "books": "Search for books...",
    "extract": "Paste a URL to fetch its content...",
}

_TAB_ICONS = {
    "text": ft.Icons.SEARCH_ROUNDED,
    "images": ft.Icons.IMAGE_ROUNDED,
    "videos": ft.Icons.PLAY_CIRCLE_ROUNDED,
    "news": ft.Icons.ARTICLE_ROUNDED,
    "books": ft.Icons.BOOK_ROUNDED,
    "extract": ft.Icons.LANGUAGE_ROUNDED,
}


# ── Compact category chip ─────────────────────────────────────────────


@ft.memo
def _category_chip(
    icon: str,
    label: str,
    color: str,
    is_active: bool,
    on_click=None,
) -> ft.Container:
    """Compact filter-chip style category selector."""
    return ft.Container(
        content=ft.Row(
            [
                ft.Icon(
                    icon,
                    size=16,
                    color=color if is_active else ft.Colors.ON_SURFACE_VARIANT,
                ),
                ft.Text(
                    label,
                    size=12,
                    weight=ft.FontWeight.W_600 if is_active else ft.FontWeight.W_400,
                    color=color if is_active else ft.Colors.ON_SURFACE,
                    font_family="Outfit",
                ),
            ],
            spacing=4,
            tight=True,
        ),
        padding=ft.Padding(12, 6, 12, 6),
        border_radius=20,
        border=ft.Border.all(
            1.5 if is_active else 1,
            color if is_active else ft.Colors.with_opacity(0.15, ft.Colors.ON_SURFACE),
        ),
        bgcolor=ft.Colors.with_opacity(0.1, color)
        if is_active
        else ft.Colors.TRANSPARENT,
        on_click=on_click,
        animate=ft.Animation(tokens.ANIMATION_FAST, ft.AnimationCurve.EASE_OUT),
    )


# ── Compact history row ───────────────────────────────────────────────


@ft.memo
def _history_row(
    query: str,
    search_type: str,
    timestamp: str,
    on_click=None,
) -> ft.Container:
    """Compact recent search row."""
    icon = _TAB_ICONS.get(search_type, ft.Icons.SEARCH_ROUNDED)
    return ft.Container(
        content=ft.Row(
            [
                ft.Icon(icon, size=16, color=AppColors.PRIMARY),
                ft.Text(
                    query,
                    size=12,
                    max_lines=1,
                    overflow=ft.TextOverflow.ELLIPSIS,
                    expand=True,
                    font_family="Outfit",
                ),
                ft.Text(
                    timestamp,
                    size=10,
                    color=ft.Colors.ON_SURFACE_VARIANT,
                    font_family="Outfit",
                ),
                ft.Icon(
                    ft.Icons.ARROW_FORWARD_ROUNDED,
                    size=14,
                    color=ft.Colors.ON_SURFACE_VARIANT,
                ),
            ],
            spacing=8,
            vertical_alignment=ft.CrossAxisAlignment.CENTER,
        ),
        padding=ft.Padding(12, 8, 12, 8),
        border_radius=tokens.RADIUS_MD,
        bgcolor=theme.adaptive_glass_bg(),
        border=ft.Border.all(1, theme.adaptive_glass_border()),
        ink=True,
        on_click=on_click,
    )


# ── Feature card ───────────────────────────────────────────────────────


@ft.memo
def _feature_card(
    icon: str,
    title: str,
    desc: str,
    color: str,
    on_click=None,
    page: ft.Page | None = None,
) -> ft.Container:
    """Feature highlight card row."""
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


# ── Step row ───────────────────────────────────────────────────────────


@ft.memo
def _step_row(number: str, title: str, desc: str) -> ft.Row:
    """Numbered step row."""
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


# ── Make compact dropdown (for search tools) ──────────────────────────


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


# ── Main screen ───────────────────────────────────────────────────────


@ft.component
def HomeScreen() -> Control:
    """Compact search-first home dashboard."""
    state = ft.use_context(AppStateCtx)
    controller = ft.use_context(ControllerMethodsCtx)

    active_tab, set_active_tab = ft.use_state(state.default_tab)
    search_query, set_search_query = ft.use_state(state.current_query)
    tools_expanded, set_tools_expanded = ft.use_state(False)

    from flet import context as flet_context

    def _get_page():
        return flet_context.page

    def _is_dark():
        p = _get_page()
        return p.theme_mode == ft.ThemeMode.DARK or (
            p.theme_mode == ft.ThemeMode.SYSTEM
            and p.platform_brightness == ft.Brightness.DARK
        )

    # ── Search logic ──

    def _on_search(e=None):
        query = search_query.strip() if search_query else ""
        if not query:
            return
        state.current_query = query
        state.default_tab = active_tab
        _get_page().run_task(controller.start_search, query, active_tab)

    def _on_paste(e):
        async def _paste():
            try:
                clipboard = ft.Clipboard()
                text = await clipboard.get()
                if text:
                    set_search_query(text.strip())
            except Exception as ex:
                logger.warning(f"Clipboard paste failed: {ex}")

        _get_page().run_task(_paste)

    def _on_tab_change(tab_key: str):
        set_active_tab(tab_key)
        state.default_tab = tab_key
        controller.save("default_tab", tab_key)

    def _on_history_click(query: str, search_type: str):
        set_search_query(query)
        set_active_tab(search_type)
        _get_page().run_task(controller.start_search, query, search_type)

    # ── Theme toggle ──

    def _toggle_theme(e):
        page = _get_page()
        if page.theme_mode == ft.ThemeMode.DARK:
            page.theme_mode = ft.ThemeMode.LIGHT
        elif page.theme_mode == ft.ThemeMode.LIGHT:
            page.theme_mode = ft.ThemeMode.SYSTEM
        else:
            page.theme_mode = ft.ThemeMode.DARK
        state.theme_mode = page.theme_mode
        controller.save("theme", page.theme_mode.value)

    def _get_theme_icon():
        page = _get_page()
        if page.theme_mode == ft.ThemeMode.DARK:
            return ft.Icons.DARK_MODE_ROUNDED
        elif page.theme_mode == ft.ThemeMode.LIGHT:
            return ft.Icons.LIGHT_MODE_ROUNDED
        return ft.Icons.SETTINGS_SYSTEM_DAYDREAM_ROUNDED

    # ── Build UI ──

    is_dark = _is_dark()
    prefix_icon = (
        ft.Icons.LINK_ROUNDED if active_tab == "extract" else ft.Icons.SEARCH_ROUNDED
    )

    # Category chips
    chips = []
    for tab in SEARCH_TABS:
        chip = _category_chip(
            icon=tab["icon"],
            label=tab["label"],
            color=tab["color"],
            is_active=tab["key"] == active_tab,
            on_click=lambda _, k=tab["key"]: _on_tab_change(k),
        )
        chips.append(chip)

    # Recent searches
    recent_rows = []
    if state.search_history:
        for entry in state.search_history[:3]:
            q = entry.get("query", "")
            st = entry.get("search_type", "text")
            ts = entry.get("timestamp", "")
            recent_rows.append(
                _history_row(
                    query=q,
                    search_type=st,
                    timestamp=ts,
                    on_click=lambda _, qq=q, stt=st: _on_history_click(qq, stt),
                )
            )

    # Search tools panel
    backend_options = BACKEND_OPTIONS_MAP.get(active_tab, BACKEND_OPTIONS_TEXT)
    current_backend = state.backend or "auto"

    if active_tab == "extract":
        tools_controls = [
            _make_compact_dropdown(
                "Output Format",
                ft.Icons.CODE_ROUNDED,
                state.extract_format,
                [ft.dropdown.Option(f["key"], f["label"]) for f in EXTRACT_FORMATS],
                lambda e: controller.save("extract_format", e.control.value),
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
                lambda e: controller.save("safe_search", e.control.value),
                width=120,
            ),
            _make_compact_dropdown(
                "Region",
                ft.Icons.PUBLIC_ROUNDED,
                state.region,
                [ft.dropdown.Option(r["key"], r["label"]) for r in REGIONS],
                lambda e: controller.save("region", e.control.value),
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
                lambda e: controller.save("max_results", int(e.control.value)),
                width=100,
            ),
            _make_compact_dropdown(
                "Time",
                ft.Icons.SCHEDULE_ROUNDED,
                state.timelimit or "",
                [ft.dropdown.Option(o["key"], o["label"]) for o in TIMELIMIT_OPTIONS],
                lambda e: controller.save("timelimit", e.control.value),
                width=130,
            ),
            _make_compact_dropdown(
                "Backend",
                ft.Icons.TRAVEL_EXPLORE_ROUNDED,
                current_backend
                if any(b["key"] == current_backend for b in backend_options)
                else "auto",
                [ft.dropdown.Option(b["key"], b["label"]) for b in backend_options],
                lambda e: controller.save("backend", e.control.value),
                width=160,
            ),
        ]

    # ── Assemble ──

    content = ft.Column(
        controls=[
            # Compact header
            ft.Container(
                content=ft.Row(
                    [
                        ft.Row(
                            [
                                ft.Image(
                                    src="icon.png",
                                    width=28,
                                    height=28,
                                    color=AppColors.PRIMARY,
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
                        ft.Row(
                            [
                                ft.IconButton(
                                    icon=_get_theme_icon(),
                                    icon_size=20,
                                    on_click=_toggle_theme,
                                    tooltip="Toggle Theme",
                                ),
                                ft.IconButton(
                                    icon=ft.Icons.SETTINGS_ROUNDED,
                                    icon_size=20,
                                    on_click=lambda e: controller.navigate_tab(2),
                                    tooltip="Settings",
                                ),
                            ],
                            spacing=0,
                        ),
                    ],
                    alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                ),
                padding=ft.Padding(
                    tokens.SPACE_LG, tokens.SPACE_SM, tokens.SPACE_LG, 0
                ),
            ),
            # Search field — modern SearchBar
            ft.Container(
                alignment=ft.Alignment.CENTER,
                content=ft.SearchBar(
                    value=search_query,
                    bar_hint_text=_HINT_MAP.get(active_tab, "Search the web..."),
                    bar_leading=ft.Icon(
                        prefix_icon,
                        color=AppColors.PRIMARY,
                    ),
                    bar_trailing=[
                        ft.IconButton(
                            icon=ft.Icons.PASTE_ROUNDED,
                            icon_size=18,
                            icon_color=AppColors.PRIMARY,
                            tooltip="Paste from clipboard",
                            on_click=_on_paste,
                        ),
                    ],
                    bar_bgcolor=(
                        AppColors.DARK_SURFACE if is_dark else AppColors.LIGHT_SURFACE
                    ),
                    bar_border_side=ft.BorderSide(
                        1,
                        ft.Colors.with_opacity(
                            0.12,
                            AppColors.DARK_TEXT if is_dark else AppColors.LIGHT_TEXT,
                        ),
                    ),
                    bar_shape=ft.RoundedRectangleBorder(radius=tokens.RADIUS_MD),
                    bar_text_style=ft.TextStyle(
                        size=tokens.FONT_MD,
                        weight=ft.FontWeight.W_500,
                    ),
                    bar_hint_text_style=ft.TextStyle(
                        size=tokens.FONT_MD,
                        weight=ft.FontWeight.W_400,
                        color=ft.Colors.with_opacity(
                            0.4,
                            AppColors.DARK_TEXT if is_dark else AppColors.LIGHT_TEXT,
                        ),
                    ),
                    full_screen=True,
                    on_submit=lambda e: _on_search(),
                    on_change=lambda e: set_search_query(e.control.value),
                    autofocus=False,
                ),
                padding=ft.Padding(
                    tokens.SPACE_LG, tokens.SPACE_SM, tokens.SPACE_LG, 0
                ),
            ),
            # Category chips (horizontal scroll)
            ft.Container(
                content=ft.Row(
                    chips,
                    wrap=False,
                    scroll=ft.ScrollMode.AUTO,
                    spacing=tokens.SPACE_SM,
                    alignment=ft.MainAxisAlignment.CENTER,
                ),
                padding=ft.Padding(
                    tokens.SPACE_LG, tokens.SPACE_SM, tokens.SPACE_LG, 0
                ),
            ),
            # Tools toggle + search button
            ft.Container(
                content=ft.Column(
                    [
                        ft.Row(
                            [
                                ft.Container(
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
                                    on_click=lambda e: set_tools_expanded(
                                        not tools_expanded
                                    ),
                                    padding=ft.Padding(12, 6, 12, 6),
                                    border_radius=tokens.RADIUS_PILL,
                                    border=ft.Border.all(
                                        1,
                                        ft.Colors.with_opacity(0.2, AppColors.PRIMARY),
                                    ),
                                    bgcolor=ft.Colors.with_opacity(
                                        0.06, AppColors.PRIMARY
                                    ),
                                    animate=ft.Animation(
                                        tokens.ANIMATION_FAST,
                                        ft.AnimationCurve.EASE_OUT,
                                    ),
                                ),
                            ],
                            alignment=ft.MainAxisAlignment.CENTER,
                        ),
                        # Tools panel
                        ft.Container(
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
                            border=ft.Border.all(
                                1, ft.Colors.with_opacity(0.08, AppColors.PRIMARY)
                            ),
                            visible=tools_expanded,
                            animate=ft.Animation(
                                tokens.ANIMATION_FAST, ft.AnimationCurve.EASE_OUT
                            ),
                        ),
                        # Search button
                        ft.Row(
                            [
                                ft.FilledButton(
                                    content=ft.Row(
                                        [
                                            ft.Icon(
                                                ft.Icons.SEARCH_ROUNDED,
                                                size=tokens.ICON_MD,
                                                color=ft.Colors.WHITE,
                                            ),
                                            ft.Text(
                                                "Search"
                                                if active_tab != "extract"
                                                else "Fetch Page",
                                                size=tokens.FONT_MD,
                                                weight=ft.FontWeight.W_600,
                                                color=ft.Colors.WHITE,
                                                font_family="Outfit",
                                            ),
                                        ],
                                        spacing=8,
                                        tight=True,
                                    ),
                                    on_click=lambda _: _on_search(),
                                    style=ft.ButtonStyle(
                                        shape=ft.RoundedRectangleBorder(
                                            radius=tokens.RADIUS_PILL
                                        ),
                                        bgcolor=AppColors.PRIMARY,
                                        padding=ft.Padding(32, 14, 32, 14),
                                    ),
                                ),
                            ],
                            alignment=ft.MainAxisAlignment.CENTER,
                        ),
                    ],
                    spacing=tokens.SPACE_SM,
                    horizontal_alignment=ft.CrossAxisAlignment.STRETCH,
                ),
                padding=ft.Padding(
                    tokens.SPACE_LG, tokens.SPACE_SM, tokens.SPACE_LG, tokens.SPACE_SM
                ),
            ),
            # Recent searches
            *(
                [
                    ft.Container(
                        content=ft.Column(
                            [
                                ft.Text(
                                    "Recent",
                                    size=tokens.FONT_SM,
                                    weight=ft.FontWeight.W_600,
                                    color=ft.Colors.ON_SURFACE_VARIANT,
                                    font_family="Outfit",
                                ),
                                *recent_rows,
                            ],
                            spacing=tokens.SPACE_SM,
                        ),
                        padding=ft.Padding(
                            tokens.SPACE_LG, 0, tokens.SPACE_LG, tokens.SPACE_SM
                        ),
                    )
                ]
                if recent_rows
                else []
            ),
            # Banner ad (after category chips)
            ft.Container(
                content=build_banner_ad(_get_page()),
                padding=ft.Padding(
                    tokens.SPACE_LG, tokens.SPACE_SM, tokens.SPACE_LG, 0
                ),
            ),
            # What DDGS Can Do (condensed - 3 features)
            ft.Container(
                content=ft.Column(
                    [
                        ft.Text(
                            "What DDGS Can Do",
                            size=tokens.FONT_SM,
                            weight=ft.FontWeight.W_600,
                            font_family="Outfit",
                        ),
                        ft.Container(height=tokens.SPACE_SM),
                        _feature_card(
                            ft.Icons.SEARCH_ROUNDED,
                            "Private Web Search",
                            "Search across engines without being tracked. No profiling, no filter bubbles.",
                            AppColors.PRIMARY,
                            page=_get_page(),
                        ),
                        ft.Container(height=tokens.SPACE_SM),
                        _feature_card(
                            ft.Icons.LANGUAGE_ROUNDED,
                            "Instant Page Fetch",
                            "Paste any URL and extract full text instantly — articles, docs, recipes. Save as markdown or plain text.",
                            AppColors.PRIMARY_DARK,
                            page=_get_page(),
                        ),
                        ft.Container(height=tokens.SPACE_SM),
                        _feature_card(
                            ft.Icons.IMAGE_ROUNDED,
                            "Image & Video Discovery",
                            "Find media from across the web. Download directly to your device.",
                            AppColors.PRIMARY_LIGHT,
                            page=_get_page(),
                        ),
                    ],
                    spacing=0,
                ),
                padding=ft.Padding(
                    tokens.SPACE_LG, 0, tokens.SPACE_LG, tokens.SPACE_LG
                ),
            ),
            # Banner ad (after features)
            ft.Container(
                content=build_banner_ad(_get_page()),
                padding=ft.Padding(
                    tokens.SPACE_LG, 0, tokens.SPACE_LG, tokens.SPACE_SM
                ),
            ),
            # How It Works (3 steps)
            ft.Container(
                content=ft.Column(
                    [
                        ft.Text(
                            "How It Works",
                            size=tokens.FONT_SM,
                            weight=ft.FontWeight.W_600,
                            font_family="Outfit",
                        ),
                        ft.Container(height=tokens.SPACE_SM),
                        _step_row(
                            "1",
                            "Choose",
                            "Pick what you're looking for — web, images, videos, news, books, or fetch a page",
                        ),
                        _step_row(
                            "2",
                            "Search",
                            "Type your query, adjust filters if needed, hit search",
                        ),
                        _step_row(
                            "3",
                            "Done",
                            "Get private results instantly. Download, save, or open in browser",
                        ),
                    ],
                    spacing=tokens.SPACE_SM,
                ),
                padding=ft.Padding(
                    tokens.SPACE_LG, 0, tokens.SPACE_LG, tokens.SPACE_LG
                ),
            ),
            # Privacy banner (prominent)
            ft.Container(
                content=ft.Row(
                    [
                        ft.Icon(
                            ft.Icons.SHIELD_ROUNDED,
                            size=20,
                            color=AppColors.PRIMARY,
                        ),
                        ft.Column(
                            [
                                ft.Text(
                                    "100% Privacy-First",
                                    size=tokens.FONT_SM,
                                    weight=ft.FontWeight.W_600,
                                    font_family="Outfit",
                                ),
                                ft.Text(
                                    "Your searches are never tracked, profiled, or stored. No filter bubbles, no data harvesting.",
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
                border=ft.Border.all(
                    1, ft.Colors.with_opacity(0.15, AppColors.PRIMARY)
                ),
            ),
            ft.Container(height=80),  # Bottom nav bar spacing
        ],
        scroll=ft.ScrollMode.AUTO,
        expand=True,
    )

    return ft.Container(
        content=content,
        gradient=theme.AppStyles.brand_gradient(_get_page()),
        expand=True,
    )
