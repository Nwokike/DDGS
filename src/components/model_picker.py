"""AI model picker — snapshot of the router's active models with status hints.

Lists the models that were `active` in the router catalog at attach/fetch
time (per the owner's LM-Router pattern): `auto` first, then the rest by
latency, each with its live latency and rate-limit hint. Selecting a model
persists it (controller save "ai_model"); if it later goes rate-limited the
client silently falls back to `auto` and the hint updates on the next refresh.
"""

from __future__ import annotations

import flet as ft

from core import tokens
from core.state import state
from core.theme import AppColors


def show_model_picker(page: ft.Page) -> None:
    from services import ai_service

    ctrl = getattr(page, "_ddgs_controller", None)
    catalog = ai_service.snapshot_models()
    if not catalog:
        # No router attached yet — attach on demand so the list is real.
        async def _load_and_show() -> None:
            await ai_service.refresh_catalog()
            show_model_picker(page)

        page.run_task(_load_and_show)
        return

    rows: list[ft.Control] = []
    for entry in catalog:
        selected = state.ai_model == entry["id"]
        rows.append(
            ft.Container(
                content=ft.Row(
                    [
                        ft.Icon(
                            ft.Icons.AUTO_AWESOME_ROUNDED
                            if entry["id"] == "auto"
                            else ft.Icons.MEMORY_ROUNDED,
                            size=16,
                            color=AppColors.PRIMARY if selected else ft.Colors.ON_SURFACE_VARIANT,
                        ),
                        ft.Column(
                            [
                                ft.Text(
                                    entry["id"],
                                    size=tokens.FONT_SM,
                                    weight=ft.FontWeight.W_700
                                    if selected
                                    else ft.FontWeight.W_500,
                                    color=AppColors.PRIMARY
                                    if selected
                                    else ft.Colors.ON_SURFACE,
                                ),
                                ft.Text(
                                    entry["hint"],
                                    size=9,
                                    color=ft.Colors.ON_SURFACE_VARIANT,
                                ),
                            ],
                            expand=True,
                            spacing=0,
                        ),
                        *(
                            [
                                ft.Icon(
                                    ft.Icons.CHECK_ROUNDED,
                                    size=16,
                                    color=AppColors.PRIMARY,
                                )
                            ]
                            if selected
                            else []
                        ),
                    ],
                    vertical_alignment=ft.CrossAxisAlignment.CENTER,
                ),
                padding=ft.Padding(8, 6, 8, 6),
                ink=True,
                border_radius=tokens.RADIUS_SM,
                bgcolor=ft.Colors.with_opacity(0.05, AppColors.PRIMARY)
                if selected
                else None,
                on_click=lambda e, mid=entry["id"]: _select(page, ctrl, mid),
            )
        )

    dlg = ft.AlertDialog(
        title=ft.Text("AI model", font_family="Outfit"),
        content=ft.Container(
            content=ft.Column(rows, spacing=2, tight=True),
            width=340,
        ),
        actions=[
            ft.TextButton(
                "Close",
                on_click=lambda e: page.pop_dialog(),
            ),
        ],
    )
    page.show_dialog(dlg)


def _select(page: ft.Page, ctrl, model_id: str) -> None:
    try:
        page.pop_dialog()
    except Exception:
        pass
    if ctrl:
        ctrl.save("ai_model", model_id)
