from __future__ import annotations

import flet as ft

from core import tokens
from core.constants import EXTRACT_FORMATS, EXTRACT_FORMAT_SHORT
from core.theme import AppColors


def build_format_chip_bar(
    selected_format: str,
    on_select,
) -> ft.Control:
    """Swipeable format selector chip bar.

    The chips row is the home screen's category-chip pattern verbatim
    (wrap=False + ScrollMode.AUTO on a width-bound Row): on a narrow screen
    the options swipe horizontally instead of clipping. The label sits
    OUTSIDE the scroll area, so the swipe starts on the chips themselves.
    """
    chips = []
    for f in EXTRACT_FORMATS:
        key = f["key"]
        label = EXTRACT_FORMAT_SHORT.get(key, f["label"])
        is_active = key == selected_format
        chips.append(
            ft.Container(
                content=ft.Text(
                    label,
                    size=tokens.FONT_XS,
                    weight=ft.FontWeight.W_600 if is_active else ft.FontWeight.W_400,
                    color=AppColors.PRIMARY if is_active else ft.Colors.ON_SURFACE,
                    font_family="Outfit",
                ),
                padding=ft.Padding(10, 5, 10, 5),
                border_radius=tokens.RADIUS_PILL,
                border=ft.Border.all(
                    1.5 if is_active else 1,
                    AppColors.PRIMARY
                    if is_active
                    else ft.Colors.with_opacity(0.15, ft.Colors.ON_SURFACE),
                ),
                bgcolor=ft.Colors.with_opacity(0.12, AppColors.PRIMARY)
                if is_active
                else ft.Colors.TRANSPARENT,
                ink=True,
                on_click=lambda _, k=key: on_select(k),
            )
        )
    return ft.Row(
        [
            ft.Icon(
                ft.Icons.CODE_ROUNDED,
                size=14,
                color=ft.Colors.ON_SURFACE_VARIANT,
            ),
            ft.Text(
                "Format:",
                size=tokens.FONT_XS,
                color=ft.Colors.ON_SURFACE_VARIANT,
                font_family="Outfit",
                weight=ft.FontWeight.W_500,
            ),
            # The scrollable part gets the remaining width and swipes the
            # chips; wrap=False keeps it one row (home screen's rule).
            ft.Row(
                chips,
                wrap=False,
                scroll=ft.ScrollMode.AUTO,
                spacing=6,
                expand=True,
                vertical_alignment=ft.CrossAxisAlignment.CENTER,
            ),
        ],
        spacing=6,
        vertical_alignment=ft.CrossAxisAlignment.CENTER,
    )
