"""Assistant model picker — snapshot of the router's active models with status hints.

Lists the models that were `active` in the router catalog at attach/fetch time
(per the owner's LM-Router pattern): `auto` first, then the rest by latency,
each with its live latency and rate-limit hint. Scrollable + filterable (the
router can expose 30+ models). Selecting persists via controller save
"ai_model"; if it later goes rate-limited the client falls back to `auto`.
"""

from __future__ import annotations

import flet as ft

from core import tokens
from core.state import state
from core.theme import AppColors

_CHAT = ft.Icons.CHAT_BUBBLE_OUTLINE_ROUNDED


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

    filter_box = {"q": ""}
    list_col = ft.Column([], spacing=2, scroll=ft.ScrollMode.AUTO, tight=True)

    def _rows() -> list[ft.Control]:
        out: list[ft.Control] = []
        for entry in catalog:
            if filter_box["q"] and filter_box["q"] not in entry["id"].lower():
                continue
            selected = state.ai_model == entry["id"]
            out.append(
                ft.Container(
                    content=ft.Row(
                        [
                            ft.Icon(
                                _CHAT
                                if entry["id"] == "auto"
                                else ft.Icons.MEMORY_ROUNDED,
                                size=16,
                                color=AppColors.PRIMARY
                                if selected
                                else ft.Colors.ON_SURFACE_VARIANT,
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
                                        max_lines=2,
                                        overflow=ft.TextOverflow.ELLIPSIS,
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
        return out

    def _apply_filter(e=None) -> None:
        filter_box["q"] = (e.control.value or "").lower() if e is not None else ""
        list_col.controls = _rows()
        list_col.height = min(
            400, max(56, 52 * len(list_col.controls) + 8)
        )
        try:
            page.update()
        except Exception:
            pass

    list_col.controls = _rows()
    list_col.height = min(400, max(56, 52 * len(list_col.controls) + 8))

    search = ft.SearchBar(
        bar_hint_text="Filter models",
        bar_leading=ft.Icon(
            ft.Icons.SEARCH_ROUNDED, size=18, color=ft.Colors.ON_SURFACE_VARIANT
        ),
        on_change=_apply_filter,
    )

    dlg = ft.AlertDialog(
        title=ft.Text("Assistant model", font_family="Outfit"),
        content=ft.Container(
            content=ft.Column([search, list_col], spacing=6, tight=True),
            width=360,
        ),
        scrollable=True,
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
    # Apply locally first so the checkmark, the Settings row and the chat
    # chip all reflect the choice on this tap, then persist in the
    # background. ctrl.save() also sets state, but only after the storage
    # write, which left the UI looking unchanged.
    state.ai_model = model_id
    if ctrl:
        ctrl.save("ai_model", model_id)
