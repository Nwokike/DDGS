"""History view — past searches."""

from __future__ import annotations

from typing import Callable

import flet as ft

from core.state import state
from core.theme import AppColors
from core.tokens import (
    FONT_XS,
    FONT_MD,
    FONT_LG,
    SPACING_SM,
    SPACING_MD,
    SPACING_XL,
    BORDER_RADIUS_MD,
    ICON_SM,
    ICON_MD,
    ICON_LG,
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
            items.append(
                ft.Container(
                    content=ft.ListTile(
                        leading=ft.Container(
                            content=ft.Icon(
                                icon, size=ICON_MD, color=AppColors.PRIMARY
                            ),
                            padding=ft.padding.all(SPACING_SM),
                            bgcolor=AppColors.PRIMARY_LIGHT,
                            border_radius=BORDER_RADIUS_MD,
                        ),
                        title=ft.Text(
                            q, size=FONT_MD, weight=ft.FontWeight.W_500, max_lines=1
                        ),
                        subtitle=ft.Text(
                            f"{st.capitalize()} · {rc} results · {ts}",
                            size=FONT_XS,
                            color=ft.Colors.ON_SURFACE_VARIANT,
                        ),
                        trailing=ft.IconButton(
                            icon=ft.Icons.ARROW_FORWARD_ROUNDED,
                            icon_size=ICON_SM,
                            on_click=lambda _, qq=q: on_search(qq),
                        ),
                        on_click=lambda _, qq=q: on_search(qq),
                        dense=True,
                    ),
                    border=ft.border.only(
                        bottom=ft.BorderSide(1, ft.Colors.OUTLINE_VARIANT)
                    )
                    if i < len(history) - 1
                    else None,
                )
            )
        history_list = ft.Column(
            controls=items, spacing=0, scroll=ft.ScrollMode.AUTO, expand=True
        )
    else:
        history_list = ft.Container(
            content=ft.Column(
                controls=[
                    ft.Icon(
                        ft.Icons.HISTORY_ROUNDED,
                        size=ICON_LG * 2,
                        color=AppColors.OUTLINE,
                    ),
                    ft.Text(
                        "No history yet",
                        size=FONT_MD,
                        color=ft.Colors.ON_SURFACE_VARIANT,
                    ),
                ],
                horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                spacing=SPACING_SM,
            ),
            padding=ft.padding.all(SPACING_XL),
            expand=True,
            alignment=ft.alignment.center,
        )

    def _show_clear_dialog(e):
        dlg = ft.AlertDialog(
            title=ft.Text("Clear All History?"),
            content=ft.Text("This will remove all saved searches."),
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
        page.views.clear()
        page.views.append(build_history_view(page, on_navigate, on_search, storage))
        page.update()

    content = ft.SafeArea(
        content=ft.Column(
            controls=[
                ft.Container(
                    content=ft.Row(
                        controls=[
                            ft.IconButton(
                                icon=ft.Icons.ARROW_BACK_ROUNDED,
                                icon_size=ICON_MD,
                                on_click=lambda _: on_navigate("/home"),
                            ),
                            ft.Text(
                                "History",
                                size=FONT_LG,
                                weight=ft.FontWeight.W_600,
                                expand=True,
                            ),
                            ft.IconButton(
                                icon=ft.Icons.DELETE_SWEEP_ROUNDED,
                                icon_size=ICON_MD,
                                on_click=_show_clear_dialog,
                                visible=bool(history),
                            ),
                        ]
                    ),
                    padding=ft.padding.symmetric(
                        horizontal=SPACING_MD, vertical=SPACING_SM
                    ),
                ),
                history_list,
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
        bgcolor=AppColors.BACKGROUND,
    )
