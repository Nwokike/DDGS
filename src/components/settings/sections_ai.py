"""Settings → Assistant & Premium: balance, cost table, AI switch, purchases.

Rows follow the Sherlock settings pattern: icon backdrop, title + subtitle,
right-aligned trailing control, 1px divider between rows.
"""

from __future__ import annotations

import flet as ft

from core.constants import (
    COST_STEP,
    DAILY_FREE_CREDITS,
    PREMIUM_DAILY_CREDITS,
    credit_word,
)
from core.state import state
from core.theme import AppColors, AppStyles
from core.tokens import (
    FONT_MD,
    FONT_SM,
    FONT_XS,
    ICON_MD,
    ICON_SM,
    RADIUS_SM,
    SPACE_MD,
    SPACE_XS,
    SPACE_XXS,
)

PREMIUM_PRODUCTS = ["premium_monthly", "premium_yearly", "premium_lifetime"]

_OPACITY_BACKDROP = 0.08
_OPACITY_DIM = 0.6
_ICON_BACKDROP = 36
_ICON_BACKDROP_RADIUS = 10


def _divider() -> ft.Divider:
    return ft.Divider(
        height=1,
        thickness=1,
        color=ft.Colors.with_opacity(_OPACITY_DIM * 0.3, ft.Colors.OUTLINE),
    )


def _setting_row(
    icon: ft.IconData,
    title: str,
    subtitle: str,
    trailing: ft.Control,
    stacked: bool = False,
) -> ft.Container:
    """Icon backdrop + title/subtitle + trailing control, Sherlock style."""
    icon_box = ft.Container(
        content=ft.Icon(
            icon,
            size=ICON_MD,
            color=ft.Colors.ON_SURFACE_VARIANT,
        ),
        width=_ICON_BACKDROP,
        height=_ICON_BACKDROP,
        border_radius=_ICON_BACKDROP_RADIUS,
        bgcolor=ft.Colors.with_opacity(_OPACITY_BACKDROP, ft.Colors.ON_SURFACE),
        alignment=ft.Alignment.CENTER,
    )
    text_col = ft.Column(
        controls=[
            ft.Text(
                title,
                size=FONT_MD,
                weight=ft.FontWeight.W_500,
                font_family="Outfit",
            ),
            ft.Text(
                subtitle,
                size=FONT_XS,
                color=ft.Colors.with_opacity(_OPACITY_DIM, ft.Colors.ON_SURFACE),
            ),
        ],
        spacing=SPACE_XXS,
        expand=True,
    )

    if stacked:
        trailing_line = ft.Row(
            controls=[
                ft.Container(width=_ICON_BACKDROP + SPACE_MD),
                trailing,
            ],
            spacing=0,
        )
        content = ft.Column(
            controls=[
                ft.Row(
                    controls=[icon_box, text_col],
                    spacing=SPACE_MD,
                    vertical_alignment=ft.CrossAxisAlignment.CENTER,
                ),
                trailing_line,
            ],
            spacing=SPACE_XS,
        )
    else:
        content = ft.Row(
            controls=[icon_box, text_col, trailing],
            spacing=SPACE_MD,
            vertical_alignment=ft.CrossAxisAlignment.CENTER,
        )

    return ft.Container(content=content, padding=ft.Padding(0, SPACE_XS, 0, SPACE_XS))


def build_ai_section(page: ft.Page, save_fn) -> ft.Container:
    controller = getattr(page, "_ddgs_controller", None)
    narrow = bool(page.width and page.width < 560)
    cap = PREMIUM_DAILY_CREDITS if state.is_premium else DAILY_FREE_CREDITS

    def _save(key: str, value) -> None:
        page.run_task(save_fn, key, value)

    from components.model_picker import (
        model_picker_state,
        model_status_subtitle,
        show_model_picker,
    )
    from services import ai_service as _ai

    rows: list[ft.Control] = []

    # ── Assistant mode ──────────────────────────────────────────────────
    rows.append(
        _setting_row(
            ft.Icons.CHAT_BUBBLE_OUTLINE_ROUNDED,
            "Assistant mode",
            "Show the Ask Assistant button on the search screen",
            ft.Switch(
                value=state.ai_mode_enabled,
                on_change=lambda e: _save("ai_mode", e.control.value),
                active_color=AppColors.PRIMARY,
            ),
            stacked=narrow,
        )
    )
    rows.append(_divider())

    # ── Assistant model ─────────────────────────────────────────────────
    # Subtitle comes from the same state the chat pill uses, so both
    # surfaces report the router identically (starting / ready / stopped).
    _picker = model_picker_state()
    rows.append(
        _setting_row(
            ft.Icons.MEMORY_ROUNDED,
            "Assistant model",
            (
                f"{_picker.label} · {model_status_subtitle()}"
                if _picker.active
                else model_status_subtitle()
            ),
            ft.TextButton(
                "Change",
                on_click=lambda e: show_model_picker(page),
            ),
            stacked=narrow,
        )
    )
    rows.append(_divider())

    # ── Credits ─────────────────────────────────────────────────────────
    rows.append(
        _setting_row(
            ft.Icons.BOLT_ROUNDED,
            f"{state.credits_remaining} of {cap} credits left today",
            "Resets at 00:00 UTC. Ad-earned credits carry over",
            ft.Icon(
                ft.Icons.BOLT_ROUNDED,
                size=ICON_SM,
                color=AppColors.ACCENT,
            ),
        )
    )
    rows.append(_divider())

    # ── Cost table ──────────────────────────────────────────────────────
    # Generated from COST_STEP, never typed by hand. A literal "1 credit"
    # here while the agent charges COST_STEP is how a paying user ends up
    # silently overcharged.
    rows.append(
        _setting_row(
            ft.Icons.PRICE_CHECK_ROUNDED,
            "What credits are for",
            f"A chat reply, a search, or a page fetch costs "
            f"{credit_word(COST_STEP)}. Search overviews and page summaries "
            "are free",
            ft.Text(
                f"{COST_STEP} / step",
                size=FONT_SM,
                color=ft.Colors.ON_SURFACE_VARIANT,
            ),
        )
    )

    # ── Data routing ────────────────────────────────────────────────────
    rows.append(_divider())
    rows.append(
        _setting_row(
            ft.Icons.PRIVACY_TIP_ROUNDED,
            "Where your messages go",
            _ai.ROUTER_DISCLOSURE,
            ft.Icon(
                ft.Icons.INFO_OUTLINE_ROUNDED,
                size=ICON_SM,
                color=ft.Colors.ON_SURFACE_VARIANT,
            ),
        )
    )

    # ── Scheduled crawls ────────────────────────────────────────────────
    if state.scheduled_scrapes:
        import time as _time

        rows.append(_divider())
        for task in state.scheduled_scrapes:
            next_in = max(0, int((task.get("next_run") or 0) - _time.time()))
            rows.append(
                _setting_row(
                    ft.Icons.SCHEDULE_ROUNDED,
                    task.get("url", ""),
                    f"Every {task.get('interval_minutes', 60)} min · "
                    f"next in {next_in // 60}m {next_in % 60}s · "
                    f"{task.get('pages_saved', 0)} pages last run",
                    ft.IconButton(
                        icon=ft.Icons.DELETE_OUTLINE_ROUNDED,
                        icon_size=ICON_SM,
                        icon_color=ft.Colors.ON_SURFACE_VARIANT,
                        tooltip="Cancel scheduled crawl",
                        on_click=lambda e, u=task: page.run_task(
                            controller.cancel_scheduled_scrape,
                            u.get("url") or "",
                        ),
                    ),
                )
            )

    _ = DAILY_FREE_CREDITS, RADIUS_SM  # kept for parity
    return AppStyles.section_card(
        "Assistant",
        ft.Icons.CHAT_BUBBLE_OUTLINE_ROUNDED,
        ft.Column(rows, spacing=0, tight=True),
        page=page,
    )
