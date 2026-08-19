"""Offline banner — persistent, non-blocking "you're offline" strip.

Shown on the Home screen while ``state.is_online`` is False.  Purely
presentational: the caller passes the current ``visible`` flag, and the
parent (HomeScreen) re-renders on every connectivity change so the banner
appears/disappears reactively.  History/Settings stay usable; this only
signals that search needs a connection.
"""

from __future__ import annotations

import flet as ft

from core import tokens


def build_offline_banner(visible: bool) -> ft.Container:
    """A slim offline notice shown on Home while the device is offline.

    ``visible`` is bound by the caller to ``not state.is_online``.
    """
    return ft.Container(
        content=ft.Row(
            [
                ft.Icon(
                    ft.Icons.WIFI_OFF_ROUNDED,
                    size=tokens.ICON_MD,
                    color=ft.Colors.ON_ERROR_CONTAINER,
                ),
                ft.Text(
                    "You're offline. Search needs a connection.",
                    size=tokens.FONT_SM,
                    color=ft.Colors.ON_ERROR_CONTAINER,
                    expand=True,
                ),
            ],
            spacing=tokens.SPACE_SM,
            vertical_alignment=ft.CrossAxisAlignment.CENTER,
        ),
        padding=ft.Padding(
            tokens.SPACE_MD, tokens.SPACE_SM, tokens.SPACE_MD, tokens.SPACE_SM
        ),
        bgcolor=ft.Colors.ERROR_CONTAINER,
        visible=visible,
    )
