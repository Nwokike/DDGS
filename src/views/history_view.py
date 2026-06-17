from __future__ import annotations

from typing import Callable

import flet as ft

from core.state import state
from core.theme import AppColors
from core.tokens import (
    FONT_XS,
    FONT_SM,
    FONT_MD,
    FONT_LG,
    SPACING_SM,
    SPACING_MD,
    SPACING_XL,
    BORDER_RADIUS_MD,
    BORDER_RADIUS_LG,
    ICON_SM,
    ICON_MD,
)
from core.utils import logger
from services.storage_service import StorageService

LOG_TAG = "HistoryView"

TAB_ICONS = {
    "text": ft.Icons.SEARCH_ROUNDED,
    "images": ft.Icons.IMAGE_ROUNDED,
    "videos": ft.Icons.PLAY_CIRCLE_ROUNDED,
    "news": ft.Icons.ARTICLE_ROUNDED,
    "books": ft.Icons.BOOK_ROUNDED,
    "extract": ft.Icons.DOWNLOAD_ROUNDED,
}

TAB_LABELS = {
    "text": "Web",
    "images": "Images",
    "videos": "Videos",
    "news": "News",
    "books": "Books",
    "extract": "Extract",
}


def build_history_view(
    page: ft.Page, on_navigate: Callable, on_search: Callable, storage: StorageService
) -> ft.View:
    logger.info(f"[{LOG_TAG}] Building history view")
    history = state.search_history

    if history:
        items = []
        for i, entry in enumerate(history):
            q = entry.get("query", "")
            st = entry.get("search_type", "text")
            ts = entry.get("timestamp", "")
            rc = entry.get("results_count", 0)
            icon = TAB_ICONS.get(st, ft.Icons.SEARCH_ROUNDED)
            label = TAB_LABELS.get(st, st.capitalize())
            items.append(
                ft.Container(
                    content=ft.Row(
                        [
                            ft.Container(
                                content=ft.Icon(
                                    icon, size=ICON_MD, color=AppColors.PRIMARY
                                ),
                                padding=ft.Padding(10, 10, 10, 10),
                                bgcolor=ft.Colors.with_opacity(0.1, AppColors.PRIMARY),
                                border_radius=BORDER_RADIUS_MD,
                            ),
                            ft.Column(
                                [
                                    ft.Text(
                                        q,
                                        size=FONT_MD,
                                        weight=ft.FontWeight.W_500,
                                        max_lines=1,
                                        no_wrap=False,
                                    ),
                                    ft.Text(
                                        f"{label} \u00b7 {rc} results \u00b7 {ts}",
                                        size=FONT_XS,
                                        color=ft.Colors.ON_SURFACE_VARIANT,
                                    ),
                                ],
                                spacing=2,
                                expand=True,
                            ),
                            ft.IconButton(
                                icon=ft.Icons.ARROW_FORWARD_ROUNDED,
                                icon_size=ICON_SM,
                                on_click=lambda _, qq=q: on_search(qq),
                            ),
                        ],
                        spacing=SPACING_MD,
                        vertical_alignment=ft.CrossAxisAlignment.CENTER,
                    ),
                    padding=ft.Padding(SPACING_MD, SPACING_SM, SPACING_SM, SPACING_SM),
                    border_radius=BORDER_RADIUS_LG,
                    bgcolor=ft.Colors.SURFACE_CONTAINER_HIGHEST,
                    ink=True,
                    on_click=lambda _, qq=q: on_search(qq),
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
                        color=ft.Colors.with_opacity(0.3, ft.Colors.PRIMARY),
                    ),
                    ft.Container(height=16),
                    ft.Text("No history yet", size=FONT_LG, weight=ft.FontWeight.W_600),
                    ft.Text(
                        "Your searches will appear here",
                        size=FONT_SM,
                        color=ft.Colors.ON_SURFACE_VARIANT,
                    ),
                ],
                horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                spacing=4,
            ),
            padding=ft.Padding(SPACING_XL, SPACING_XL, SPACING_XL, SPACING_XL),
            expand=True,
            alignment=ft.alignment.Alignment(0, 0),
        )

    # ── Clear dialog ──
    def _show_clear_dialog(e):
        dlg = ft.AlertDialog(
            modal=True,
            title=ft.Text("Clear All History?"),
            content=ft.Text(
                "This will remove all saved searches. This cannot be undone."
            ),
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
        page.views.clear()
        page.views.append(build_history_view(page, on_navigate, on_search, storage))
        page.update()

    header = ft.Container(
        content=ft.Row(
            [
                ft.IconButton(
                    icon=ft.Icons.ARROW_BACK_ROUNDED,
                    icon_size=ICON_MD,
                    on_click=lambda _: on_navigate("/home"),
                ),
                ft.Text(
                    "History", size=FONT_LG, weight=ft.FontWeight.BOLD, expand=True
                ),
                ft.IconButton(
                    icon=ft.Icons.DELETE_SWEEP_ROUNDED,
                    icon_size=ICON_MD,
                    on_click=_show_clear_dialog,
                    visible=bool(history),
                    icon_color=AppColors.ERROR,
                ),
            ],
            spacing=4,
        ),
        padding=ft.Padding(SPACING_MD, SPACING_SM, SPACING_MD, SPACING_SM),
    )

    content = ft.SafeArea(
        content=ft.Column(
            [
                header,
                ft.Container(
                    content=history_list,
                    padding=ft.Padding(SPACING_MD, 0, SPACING_MD, 0),
                    expand=True,
                ),
            ],
            spacing=0,
            expand=True,
        ),
    )

    return ft.View(
        route="/history",
        controls=[content],
        padding=0,
        spacing=0,
        bgcolor=ft.Colors.SURFACE,
    )
