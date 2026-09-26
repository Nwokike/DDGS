"""Cached-results banner - tells the user results came from disk.

When a search hits the 30-minute cache we render instantly and let the
live search replace the list underneath. This strip is how the user knows
what they are looking at is not necessarily the newest thing, and gives
them a one-tap way to force a fresh run. Same non-blocking pattern as the
offline banner.
"""

from __future__ import annotations

import flet as ft

from core import tokens
from core.theme import AppColors


def build_cache_banner(
    visible: bool,
    *,
    refreshing: bool = False,
    on_refresh=None,
) -> ft.Container:
    """Slim strip shown above results that came from the cache.

    ``refreshing`` is True while the background live search is still
    running, which is the normal case: the cached list is on screen and
    about to be replaced.
    """
    if refreshing:
        message = "Showing saved results. Refreshing…"
    else:
        message = "Showing saved results from this device."

    controls: list[ft.Control] = [
        ft.Icon(
            ft.Icons.HISTORY_ROUNDED,
            size=tokens.ICON_MD,
            color=AppColors.PRIMARY,
        ),
        ft.Text(
            message,
            size=tokens.FONT_SM,
            color=ft.Colors.ON_SURFACE,
            expand=True,
        ),
    ]
    if not refreshing:
        controls.append(
            ft.TextButton(
                "Refresh",
                icon=ft.Icons.REFRESH_ROUNDED,
                on_click=(lambda e: on_refresh()) if on_refresh else None,
            )
        )
    else:
        controls.append(
            ft.ProgressRing(width=14, height=14, stroke_width=2)
        )

    return ft.Container(
        content=ft.Row(
            controls,
            spacing=tokens.SPACE_SM,
            vertical_alignment=ft.CrossAxisAlignment.CENTER,
        ),
        padding=ft.Padding(
            tokens.SPACE_MD, tokens.SPACE_XS, tokens.SPACE_MD, tokens.SPACE_XS
        ),
        bgcolor=ft.Colors.with_opacity(0.10, AppColors.PRIMARY),
        visible=visible,
    )
