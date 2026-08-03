"""HistoryScreen — search history list with re-search and clear-all.

Converted from views/history_view.py to declarative @ft.component.
"""

from __future__ import annotations

import flet as ft
from flet import Control

from contexts.app_state_ctx import AppStateCtx
from contexts.controller_ctx import ControllerMethodsCtx
from core import theme, tokens
from core.theme import AppColors

_TAB_ICONS = {
    "text": ft.Icons.SEARCH_ROUNDED,
    "images": ft.Icons.IMAGE_ROUNDED,
    "videos": ft.Icons.PLAY_CIRCLE_ROUNDED,
    "news": ft.Icons.ARTICLE_ROUNDED,
    "books": ft.Icons.BOOK_ROUNDED,
    "extract": ft.Icons.DOWNLOAD_ROUNDED,
}

_TAB_LABELS = {
    "text": "Web",
    "images": "Images",
    "videos": "Videos",
    "news": "News",
    "books": "Books",
    "extract": "Extract",
}


@ft.component
def HistoryScreen() -> Control:
    """Search history with re-search and clear-all."""
    state = ft.use_context(AppStateCtx)
    controller = ft.use_context(ControllerMethodsCtx)

    history = state.search_history

    from flet import context as flet_context

    def _get_page():
        return flet_context.page

    def _on_research(query: str, search_type: str):
        _get_page().run_task(controller.start_search, query, search_type)

    def _on_clear():
        page = _get_page()

        async def _do_clear():
            page.pop_dialog()
            state.search_history.clear()
            await controller.save_async("history", [])

        dlg = ft.AlertDialog(
            modal=True,
            title=ft.Text(
                "Clear All History?",
                font_family="Outfit",
                size=tokens.FONT_LG,
                weight=ft.FontWeight.BOLD,
            ),
            content=ft.Text(
                "This will remove all saved searches. This cannot be undone.",
                style=ft.TextStyle(height=1.4),
            ),
            actions=[
                ft.TextButton("Cancel", on_click=lambda _: page.pop_dialog()),
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

    def _go_home():
        controller.navigate_tab(0)

    # ── Build history list ──
    if history:
        items = []
        for entry in history:
            q = entry.get("query", "")
            st = entry.get("search_type", "text")
            ts = entry.get("timestamp", "")
            rc = entry.get("results_count", 0)
            icon = _TAB_ICONS.get(st, ft.Icons.SEARCH_ROUNDED)
            label = _TAB_LABELS.get(st, st.capitalize())

            items.append(
                ft.Container(
                    content=ft.Row(
                        [
                            ft.Container(
                                content=ft.Icon(
                                    icon, size=tokens.ICON_MD, color=AppColors.PRIMARY
                                ),
                                padding=10,
                                bgcolor=ft.Colors.with_opacity(0.12, AppColors.PRIMARY),
                                border_radius=tokens.BORDER_RADIUS_MD,
                            ),
                            ft.Column(
                                [
                                    ft.Text(
                                        q,
                                        size=tokens.FONT_MD,
                                        weight=ft.FontWeight.W_600,
                                        max_lines=1,
                                        overflow=ft.TextOverflow.ELLIPSIS,
                                        font_family="Outfit",
                                    ),
                                    ft.Text(
                                        f"{label} \u00b7 {rc} results \u00b7 {ts}",
                                        size=tokens.FONT_XS,
                                        color=ft.Colors.ON_SURFACE_VARIANT,
                                        font_family="Outfit",
                                    ),
                                ],
                                spacing=2,
                                expand=True,
                            ),
                            ft.IconButton(
                                icon=ft.Icons.ARROW_FORWARD_ROUNDED,
                                icon_size=tokens.ICON_SM,
                                on_click=lambda _, qq=q, stt=st: _on_research(qq, stt),
                            ),
                        ],
                        spacing=tokens.SPACE_MD,
                        vertical_alignment=ft.CrossAxisAlignment.CENTER,
                    ),
                    padding=ft.Padding(
                        tokens.SPACE_MD,
                        tokens.SPACE_SM,
                        tokens.SPACE_SM,
                        tokens.SPACE_SM,
                    ),
                    border_radius=tokens.BORDER_RADIUS_LG,
                    bgcolor=theme.adaptive_glass_bg(None),
                    border=ft.Border.all(1, theme.adaptive_glass_border(None)),
                    ink=True,
                    on_click=lambda _, qq=q, stt=st: _on_research(qq, stt),
                )
            )

        history_list = ft.Column(
            controls=items, spacing=8, scroll=ft.ScrollMode.AUTO, expand=True
        )
    else:
        history_list = ft.Container(
            content=ft.Column(
                [
                    ft.Container(height=60),
                    ft.Icon(
                        ft.Icons.HISTORY_ROUNDED,
                        size=64,
                        color=ft.Colors.with_opacity(0.3, AppColors.PRIMARY),
                    ),
                    ft.Container(height=16),
                    ft.Text(
                        "No history yet",
                        size=tokens.FONT_LG,
                        weight=ft.FontWeight.W_600,
                        font_family="Outfit",
                    ),
                    ft.Text(
                        "Your searches will appear here",
                        size=tokens.FONT_SM,
                        color=ft.Colors.ON_SURFACE_VARIANT,
                        font_family="Outfit",
                    ),
                ],
                horizontal_alignment="center",
                spacing=4,
            ),
            padding=ft.Padding(
                tokens.SPACE_XL, tokens.SPACE_XL, tokens.SPACE_XL, tokens.SPACE_XL
            ),
            expand=True,
            alignment=ft.Alignment.CENTER,
        )

    # ── Header ──
    header = ft.Container(
        content=ft.Row(
            [
                ft.IconButton(
                    icon=ft.Icons.ARROW_BACK_ROUNDED,
                    icon_size=tokens.ICON_MD,
                    on_click=lambda _: _go_home(),
                ),
                ft.Text(
                    "History",
                    size=tokens.FONT_LG,
                    weight=ft.FontWeight.BOLD,
                    expand=True,
                    font_family="Outfit",
                ),
                ft.IconButton(
                    icon=ft.Icons.DELETE_SWEEP_ROUNDED,
                    icon_size=tokens.ICON_MD,
                    on_click=lambda _: _on_clear(),
                    visible=bool(history),
                    icon_color=AppColors.ERROR,
                ),
            ],
            spacing=4,
        ),
        padding=ft.Padding(
            tokens.SPACE_MD, tokens.SPACE_SM, tokens.SPACE_MD, tokens.SPACE_SM
        ),
    )

    return ft.Container(
        content=ft.Column(
            [
                header,
                ft.Container(
                    content=history_list,
                    padding=ft.Padding(tokens.SPACE_MD, 0, tokens.SPACE_MD, 0),
                    expand=True,
                ),
            ],
            spacing=0,
            expand=True,
        ),
        gradient=theme.AppStyles.brand_gradient(None),
        expand=True,
    )
