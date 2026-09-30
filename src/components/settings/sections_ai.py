"""Settings → Assistant & Premium: balance, cost table, AI switch, purchases.

Rows follow the Sherlock settings pattern: icon backdrop, title + subtitle,
right-aligned trailing control, 1px divider between rows.
"""

from __future__ import annotations

import flet as ft

from core import ui
from core.constants import (
    COST_STEP,
    DAILY_FREE_CREDITS,
    PREMIUM_DAILY_CREDITS,
    credit_word,
)
from core.state import state
from core.theme import AppColors, AppStyles
from core import tokens
from core.tokens import (
    FONT_SM,
    ICON_SM,
    RADIUS_SM,
)

PREMIUM_PRODUCTS = ["premium_monthly", "premium_yearly", "premium_lifetime"]

# Recurring crawl intervals the edit dialog offers (plan C6). The tool
# schema clamps to 15..1440 minutes, so these cover the whole legal range.
_INTERVALS = (
    ("15", "15m"),
    ("30", "30m"),
    ("60", "1h"),
    ("360", "6h"),
    ("720", "12h"),
    ("1440", "24h"),
)


def _edit_schedule_dialog(page: ft.Page, controller, task: dict) -> None:
    """Edit a scheduled crawl's interval with a SegmentedButton (plan C6)."""
    url = str(task.get("url") or "")
    current = str(int(task.get("interval_minutes") or 60))
    if current not in {v for v, _ in _INTERVALS}:
        current = "60"

    picked = [current]

    async def _save(e=None):
        page.pop_dialog()
        interval = int(picked[0] or current)
        from services import chat_agent
        from services.chat_agent import _persist_schedule

        chat_agent._schedule(url, interval)
        await _persist_schedule()

    page.show_dialog(
        ft.AlertDialog(
            title=ft.Text("Edit crawl schedule", font_family="Outfit"),
            content=ft.Container(
                content=ft.Column(
                    [
                        ft.Text(
                            url,
                            size=FONT_SM,
                            color=ft.Colors.ON_SURFACE_VARIANT,
                            max_lines=2,
                            overflow=ft.TextOverflow.ELLIPSIS,
                            font_family="Outfit",
                        ),
                        ft.SegmentedButton(
                            segments=[
                                ft.Segment(value=v, label=ft.Text(lbl, font_family="Outfit"))
                                for v, lbl in _INTERVALS
                            ],
                            selected=[current],
                            allow_multiple_selection=False,
                            on_change=lambda e: picked.__setitem__(
                                0,
                                (list(e.control.selected) or [current])[0],
                            ),
                        ),
                        ft.Text(
                            "Runs while the app is open.",
                            size=FONT_SM,
                            color=ft.Colors.ON_SURFACE_VARIANT,
                            font_family="Outfit",
                        ),
                    ],
                    tight=True,
                    spacing=12,
                ),
                width=380,
            ),
            actions=[
                ft.TextButton("Cancel", on_click=lambda e: page.pop_dialog()),
                ft.FilledButton("Save", on_click=_save),
            ],
            actions_alignment=ft.MainAxisAlignment.END,
        )
    )

_OPACITY_DIM = 0.6


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
    trailing: ft.Control | None = None,
    stacked: bool = False,
) -> ft.Container:
    """Sherlock settings row; the shape lives in core.ui."""
    return ui.setting_row(icon, title, subtitle, trailing, stacked=stacked)


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

    # ── Thinking depth (plan B9; probed live: the router accepts it) ──
    rows.append(
        _setting_row(
            ft.Icons.PSYCHOLOGY_ROUNDED,
            "Thinking depth",
            "Auto leaves it to the model; Fast and Deep trade speed for care",
            ft.SegmentedButton(
                segments=[
                    ft.Segment(
                        value=value,
                        label=ft.Text(label, font_family="Outfit", size=tokens.FONT_XS),
                    )
                    for value, label in (
                        ("auto", "Auto"),
                        ("low", "Fast"),
                        ("high", "Deep"),
                    )
                ],
                selected=[str(state.reasoning_effort or "auto")],
                allow_multiple_selection=False,
                on_change=lambda e: _save(
                    "reasoning_effort", (e.control.selected or ["auto"])[0]
                ),
            ),
            stacked=True,
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
            "Resets at 00:00 UTC",
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
            f"Each Assistant model step costs {credit_word(COST_STEP)}. "
            "Search, scraping, downloads, overviews and summaries are free",
            ft.Text(
                f"{COST_STEP} / step",
                size=FONT_SM,
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
            crawl_url = str(task.get("url", ""))
            if len(crawl_url) > 48:
                crawl_url = crawl_url[:45] + "..."
            rows.append(
                _setting_row(
                    ft.Icons.SCHEDULE_ROUNDED,
                    crawl_url,
                    f"Every {task.get('interval_minutes', 60)} min · "
                    f"next in {next_in // 60}m {next_in % 60}s · "
                    f"{task.get('pages_saved', 0)} pages last run",
                    ft.Row(
                        [
                            ft.IconButton(
                                icon=ft.Icons.EDIT_ROUNDED,
                                icon_size=ICON_SM,
                                icon_color=ft.Colors.ON_SURFACE_VARIANT,
                                tooltip="Edit crawl interval",
                                on_click=lambda e, u=task: _edit_schedule_dialog(
                                    page, controller, u
                                ),
                            ),
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
                        ],
                        spacing=0,
                        tight=True,
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
