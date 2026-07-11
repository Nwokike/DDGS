from __future__ import annotations

from typing import Callable

import flet as ft

from core import theme, tokens
from core.state import state
from core.theme import AppColors
from core.styles import build_banner_ad
from services.storage_service import StorageService
from core.utils import logger

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
                                on_click=lambda _, qq=q, stt=st: on_search(qq, stt),
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
                    bgcolor=theme.adaptive_glass_bg(page),
                    border=ft.Border.all(1, theme.adaptive_glass_border(page)),
                    ink=True,
                    on_click=lambda _, qq=q, stt=st: on_search(qq, stt),
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

    # ── Clear dialog ──
    def _show_clear_dialog(e):
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

    async def _do_clear():
        page.pop_dialog()
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
                    icon_size=tokens.ICON_MD,
                    on_click=lambda _: on_navigate("/home"),
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
                    on_click=_show_clear_dialog,
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

    content = ft.SafeArea(
        content=ft.Column(
            [
                header,
                ft.Container(
                    content=history_list,
                    padding=ft.Padding(tokens.SPACE_MD, 0, tokens.SPACE_MD, 0),
                    expand=True,
                ),
                build_banner_ad(page),
            ],
            spacing=0,
            expand=True,
        ),
    )

    return ft.View(
        route="/history",
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
        padding=0,
        spacing=0,
        bgcolor=ft.Colors.SURFACE,
    )
