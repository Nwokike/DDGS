"""Assistant model picker - a live pill and menu over the router's models.

Follows the pattern LM Router proved in
`lm-router/src/components/chat_controls.py:60-205`: every startup
circumstance gets its own honest label, so an empty list during discovery
reads as "still starting" rather than as a broken app.

The label logic lives in `model_picker_state()` and is shared by the chat
header pill and the Settings row, so the two can never disagree about what
the router is doing.

List order: `auto` first, then the rest by the router's own latency, each
with its live rate hint. Nothing is hardcoded; the default is `auto`.
"""

from __future__ import annotations

from dataclasses import dataclass

import flet as ft

from core import tokens
from core.state import state
from core.theme import AppColors

_CHAT = ft.Icons.CHAT_BUBBLE_OUTLINE_ROUNDED


@dataclass(frozen=True)
class PickerState:
    """What the picker should show right now."""

    label: str
    discovering: bool
    selected: str
    active: bool
    models: tuple[dict, ...]
    message: str = ""
    action: str = ""


def model_picker_state() -> PickerState:
    """Derive the picker's label, models and empty-state copy from state.

    Mirrors LM Router's label ladder:
      chosen + in catalog -> its name
      starting            -> "Starting router..."
      router stopped      -> "Router stopped"
      models but no match -> "No chat models yet"
      otherwise           -> "Loading models..."

    The chosen name only counts once it is actually present in the catalog
    we hold. Otherwise a saved preference would be shown while the router
    is still starting, which is the stale-label problem this ladder exists
    to avoid.
    """
    from services import ai_service

    models = tuple(ai_service.snapshot_models())
    selected = state.ai_model
    status = getattr(state, "ai_router_status", "starting") or "starting"
    fetched = bool(getattr(ai_service, "_catalog_fetched_at", 0.0))
    # Spin only while we are genuinely still finding out. Once a fetch has
    # completed, an empty list is a real answer, not a wait.
    discovering = status in ("starting", "ready") and not models and not fetched

    current = next(
        (m for m in models if str(m.get("id") or "") == str(selected or "")),
        None,
    )
    # A stopped or unavailable router outranks a stale catalog. The catalog
    # is only a snapshot, so once the router is down the pill used to keep
    # showing a model name forever, and the "Start router" action never
    # appeared because `models` was non-empty.
    if status in ("stopped", "unavailable"):
        label = "Router stopped" if status == "stopped" else "Router unavailable"
    elif current is not None:
        label = "Auto" if str(current.get("id")) == "auto" else str(current["id"])
    elif status == "starting":
        label = "Starting router..."
    elif status == "stopped":
        label = "Router stopped"
    elif status == "unavailable":
        label = "Router unavailable"
    elif fetched:
        label = "No chat models yet"
    else:
        label = "Loading models..."

    message = action = ""
    if status == "stopped":
        message, action = "The local model router stopped.", "Start router"
    elif status == "unavailable":
        message, action = (
            "No local model router is running. Replies will use Kiri Gateway.",
            "Start router",
        )
    elif not models:
        if discovering:
            message, action = "Looking for available models...", ""
        elif status == "stopped":
            message, action = "The local model router stopped.", "Start router"
        elif status == "unavailable":
            message, action = (
                "No local model router is running. Replies will use Kiri Gateway.",
                "Start router",
            )
        else:
            message, action = "No models reported by the router.", "Refresh"

    return PickerState(
        label=label,
        discovering=discovering,
        selected=selected,
        # True only when the saved choice is in the catalog we actually
        # hold, so the pill does not claim a model it cannot see.
        active=current is not None,
        models=models,
        message=message,
        action=action,
    )


def _pill_state(ps: PickerState) -> tuple[str, ft.Control | None]:
    """Pill label + leading icon/spinner."""
    if ps.active:
        icon = ft.Icon(
            _CHAT if ps.selected == "auto" else ft.Icons.MEMORY_ROUNDED,
            size=tokens.ICON_SM,
            color=AppColors.PRIMARY,
        )
        return ps.label, icon
    if ps.discovering:
        return ps.label, ft.ProgressRing(width=12, height=12, stroke_width=2)
    icon = ft.Icon(
        ft.Icons.CLOUD_OFF_ROUNDED
        if ps.action == "Start router"
        else ft.Icons.MEMORY_ROUNDED,
        size=tokens.ICON_SM,
        color=ft.Colors.ON_SURFACE_VARIANT,
    )
    return ps.label, icon


def build_model_pill(
    page: ft.Page,
    *,
    on_open: callable | None = None,
) -> ft.Container:
    """The chat-header pill. Opens the dialog; label reflects live state."""
    ps = model_picker_state()
    label, icon = _pill_state(ps)
    return ft.Container(
        content=ft.Row(
            [
                *( [icon] if icon is not None else [] ),
                ft.Text(
                    label,
                    size=tokens.FONT_XS,
                    weight=ft.FontWeight.W_600,
                    color=AppColors.PRIMARY
                    if ps.active
                    else ft.Colors.ON_SURFACE_VARIANT,
                    max_lines=1,
                    overflow=ft.TextOverflow.ELLIPSIS,
                ),
                ft.Icon(
                    ft.Icons.EXPAND_MORE_ROUNDED,
                    size=12,
                    color=AppColors.PRIMARY
                    if ps.active
                    else ft.Colors.ON_SURFACE_VARIANT,
                ),
            ],
            spacing=2,
            tight=True,
        ),
        padding=ft.Padding(7, 3, 7, 3),
        border_radius=tokens.RADIUS_PILL,
        bgcolor=ft.Colors.with_opacity(0.1, AppColors.PRIMARY)
        if ps.active
        else ft.Colors.with_opacity(0.06, ft.Colors.ON_SURFACE),
        ink=True,
        tooltip="Assistant model",
        on_click=(lambda e: on_open()) if on_open else (lambda e: show_model_picker(page)),
    )


def model_status_subtitle() -> str:
    """One line for the Settings row, under the model name."""
    from services import ai_service

    ps = model_picker_state()
    if ps.active:
        return ai_service.model_hint(ps.selected) or "Active at last fetch"
    if ps.message:
        return ps.message
    return "No model selected"


def show_model_picker(page: ft.Page) -> None:
    """Open the full picker dialog with a live, filterable model list."""

    ctrl = getattr(page, "_ddgs_controller", None)
    ps = model_picker_state()

    if not ps.models or ps.action:
        # Either nothing to list, or the router is down while a stale
        # catalog still exists. In both cases say what is happening and
        # offer the action that helps, rather than presenting a list of
        # models the current state cannot honour.
        async def _load_and_show() -> None:
            from services import ai_service as _ai

            if ps.action == "Start router":
                await _ai.ensure_router(verify=True)
            await _ai.refresh_catalog()
            show_model_picker(page)

        _show_empty_dialog(page, ps, _load_and_show)
        return

    filter_box = {"q": ""}
    list_col = ft.Column([], spacing=2, scroll=ft.ScrollMode.AUTO, tight=True)

    def _rows() -> list[ft.Control]:
        out: list[ft.Control] = []
        for entry in ps.models:
            model_id = str(entry.get("id") or "")
            if not model_id:
                continue
            if filter_box["q"] and filter_box["q"] not in model_id.lower():
                continue
            selected = state.ai_model == model_id
            out.append(
                ft.Container(
                    content=ft.Row(
                        [
                            ft.Icon(
                                _CHAT if model_id == "auto" else ft.Icons.MEMORY_ROUNDED,
                                size=16,
                                color=AppColors.PRIMARY
                                if selected
                                else ft.Colors.ON_SURFACE_VARIANT,
                            ),
                            ft.Column(
                                [
                                    ft.Text(
                                        "Auto" if model_id == "auto" else model_id,
                                        size=tokens.FONT_SM,
                                        weight=ft.FontWeight.W_700
                                        if selected
                                        else ft.FontWeight.W_500,
                                        color=AppColors.PRIMARY
                                        if selected
                                        else ft.Colors.ON_SURFACE,
                                    ),
                                    ft.Text(
                                        entry.get("hint", ""),
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
                    on_click=lambda e, mid=model_id: _select(page, ctrl, mid),
                )
            )
        return out

    def _apply_filter(e=None) -> None:
        filter_box["q"] = (e.control.value or "").lower() if e is not None else ""
        list_col.controls = _rows()
        list_col.height = min(400, max(56, 52 * len(list_col.controls) + 8))
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


def _show_empty_dialog(page: ft.Page, ps: PickerState, on_action) -> None:
    """Dialog for the no-models-yet case: status + the action that helps."""
    controls: list[ft.Control] = [
        ft.Row(
            [
                ft.Icon(
                    ft.Icons.CLOUD_OFF_ROUNDED
                    if ps.action == "Start router"
                    else ft.Icons.MEMORY_ROUNDED,
                    size=20,
                    color=ft.Colors.ON_SURFACE_VARIANT,
                ),
                ft.Text(
                    ps.message,
                    size=tokens.FONT_SM,
                    color=ft.Colors.ON_SURFACE,
                    expand=True,
                ),
            ],
            spacing=8,
            vertical_alignment=ft.CrossAxisAlignment.CENTER,
        )
    ]
    actions: list[ft.Control] = []
    if ps.action:
        controls.append(
            ft.Text(
                ps.action,
                size=tokens.FONT_SM,
                weight=ft.FontWeight.W_600,
                color=AppColors.PRIMARY,
            )
        )
        actions.append(
            ft.FilledButton(
                ps.action,
                on_click=lambda e: _dismiss_then(page, on_action),
                style=ft.ButtonStyle(bgcolor=AppColors.PRIMARY, color=ft.Colors.WHITE),
            )
        )
    actions.append(ft.TextButton("Close", on_click=lambda e: page.pop_dialog()))

    page.show_dialog(
        ft.AlertDialog(
            title=ft.Text("Assistant model", font_family="Outfit"),
            content=ft.Container(
                content=ft.Column(controls, spacing=8, tight=True), width=320
            ),
            actions=actions,
        )
    )


def _dismiss_then(page: ft.Page, action) -> None:
    try:
        page.pop_dialog()
    except Exception:
        pass
    try:
        page.run_task(action)
    except Exception:
        # `action` is an async coroutine function. Calling it here would
        # only build a coroutine nobody awaits, so the user would see a
        # "coroutine was never awaited" warning and nothing would happen.
        # The button is simply inert when the page cannot schedule work.
        import logging

        logging.getLogger(__name__).warning(
            "could not schedule %r: the page refused the task", action
        )


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
