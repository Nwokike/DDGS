"""Shared UI primitives: the settings row and the inline notice.

Four files used to each own a 95%-identical "icon box + title + subtitle +
trailing" builder (wallet, AI settings, premium settings, chat history) and
eight places hand-rolled "message + retry button" notices with four
different verbs. One implementation each lives here so every surface renders
the same weights, spacings and tap behaviour.
"""

from __future__ import annotations

import flet as ft

from core import tokens

ICON_BOX = 36
ICON_BOX_RADIUS = 10
OPACITY_BACKDROP = 0.08
OPACITY_DIM = 0.6

# Buttons that sit inline under a message use no padding: the text IS the
# hit target, and flet's default padding made them float.
ZERO_PAD = ft.ButtonStyle(padding=ft.Padding(0, 0, 0, 0))


def setting_row(
    icon: ft.IconData,
    title: str,
    subtitle: str = "",
    trailing: ft.Control | None = None,
    *,
    stacked: bool = False,
    accent: bool = False,
    on_click=None,
    subtitle_lines: int = 3,
) -> ft.Container:
    """Icon backdrop + title/subtitle + trailing control.

    `stacked` puts the trailing control on its own line under the text
    (narrow screens); `accent` marks the active entry (history); `on_click`
    makes the whole row tappable.
    """
    icon_box = ft.Container(
        content=ft.Icon(
            icon,
            size=tokens.ICON_MD,
            color=ft.Colors.PRIMARY if accent else ft.Colors.ON_SURFACE_VARIANT,
        ),
        width=ICON_BOX,
        height=ICON_BOX,
        border_radius=ICON_BOX_RADIUS,
        bgcolor=ft.Colors.with_opacity(OPACITY_BACKDROP, ft.Colors.ON_SURFACE),
        alignment=ft.Alignment.CENTER,
    )
    text_col = ft.Column(
        controls=[
            ft.Text(
                title,
                size=tokens.FONT_MD,
                weight=ft.FontWeight.W_600 if accent else ft.FontWeight.W_500,
                font_family="Outfit",
                color=ft.Colors.PRIMARY if accent else None,
                max_lines=1,
                overflow=ft.TextOverflow.ELLIPSIS,
            ),
            *(
                [
                    ft.Text(
                        subtitle,
                        size=tokens.FONT_XS,
                        color=ft.Colors.with_opacity(OPACITY_DIM, ft.Colors.ON_SURFACE),
                        max_lines=subtitle_lines,
                        overflow=ft.TextOverflow.ELLIPSIS,
                    )
                ]
                if subtitle
                else []
            ),
        ],
        spacing=tokens.SPACE_XXS,
        expand=True,
    )

    if stacked:
        content = ft.Column(
            controls=[
                ft.Row(
                    controls=[icon_box, text_col],
                    spacing=tokens.SPACE_MD,
                    vertical_alignment=ft.CrossAxisAlignment.CENTER,
                ),
                ft.Row(
                    controls=[ft.Container(width=ICON_BOX + tokens.SPACE_MD)]
                    + ([trailing] if trailing is not None else []),
                    spacing=0,
                ),
            ],
            spacing=tokens.SPACE_XS,
        )
    else:
        kids: list[ft.Control] = [icon_box, text_col]
        if trailing is not None:
            kids.append(trailing)
        content = ft.Row(
            kids,
            spacing=tokens.SPACE_MD,
            vertical_alignment=ft.CrossAxisAlignment.CENTER,
        )
    return ft.Container(
        content=content,
        padding=ft.Padding(0, tokens.SPACE_XS, 0, tokens.SPACE_XS),
        on_click=on_click,
        ink=on_click is not None,
        border_radius=tokens.RADIUS_MD,
    )


def notice(
    message: str,
    *,
    level: str = "muted",
    action_label: str | None = None,
    action_icon: ft.IconData | None = None,
    on_action=None,
    italic: bool = False,
) -> ft.Column:
    """One inline notice: a message line with an optional action button.

    `level` is "warning" (recovered problem) or "muted" (informational).
    Action verbs are owned by the caller: "Try again", "Get credits".
    """
    color = (
        ft.Colors.WARNING if level == "warning" else ft.Colors.ON_SURFACE_VARIANT
    )
    controls: list[ft.Control] = [
        ft.Text(
            message,
            size=tokens.FONT_XS,
            color=color,
            italic=italic,
        )
    ]
    if action_label and on_action is not None:
        controls.append(
            ft.TextButton(
                action_label,
                icon=action_icon,
                style=ZERO_PAD,
                on_click=on_action,
            )
        )
    return ft.Column(
        controls,
        spacing=tokens.SPACE_XXS,
        tight=True,
        horizontal_alignment=ft.CrossAxisAlignment.START,
    )
