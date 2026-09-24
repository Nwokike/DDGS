"""Settings → Assistant & Premium: balance, cost table, AI switch, purchases.

Rows follow the Sherlock settings pattern: icon backdrop, title + subtitle,
right-aligned trailing control, 1px divider between rows.
"""

from __future__ import annotations

import flet as ft

from core.constants import (
    DAILY_FREE_CREDITS,
    PREMIUM_DAILY_CREDITS,
)
from core.state import state
from core.theme import AppColors, AppStyles
from core.tokens import (
    BORDER_RADIUS_MD,
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
    billing = getattr(controller, "billing", None) if controller else None
    is_android = page.platform == ft.PagePlatform.ANDROID
    narrow = bool(page.width and page.width < 560)
    cap = PREMIUM_DAILY_CREDITS if state.is_premium else DAILY_FREE_CREDITS

    def _save(key: str, value) -> None:
        page.run_task(save_fn, key, value)

    def _snack(message: str) -> None:
        snack = ft.SnackBar(ft.Text(message))
        snack.open = True
        page.show_dialog(snack)
        try:
            page.update()
        except Exception:
            pass

    async def _buy(product_id: str) -> None:
        if billing is None:
            return
        try:
            result = await billing.query_products([product_id])
            if not result.products:
                _snack("Product not found. Create it in Play Console first.")
                return
            product = result.products[0]
            ok = await billing.buy_non_consumable(
                product_id, offer_token=product.offer_token
            )
            if not ok:
                _snack("Purchase could not start.")
        except Exception as exc:
            _snack(f"Billing error: {exc}")

    async def _restore() -> None:
        if billing is None:
            return
        try:
            await billing.restore_purchases()
            _snack("Checking your purchases")
        except Exception as exc:
            _snack(f"Restore failed: {exc}")

    from components.model_picker import show_model_picker
    from services import ai_service as _ai

    model_hint = _ai.model_hint(state.ai_model) or "active models at attach"

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
    rows.append(
        _setting_row(
            ft.Icons.MEMORY_ROUNDED,
            "Assistant model",
            f"{state.ai_model} · {model_hint}",
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
    rows.append(
        _setting_row(
            ft.Icons.PRICE_CHECK_ROUNDED,
            "What credits are for",
            "A chat reply, a search, or a page fetch costs 1 credit. "
            "Search overviews and page summaries are free",
            ft.Text(
                "1 / step",
                size=FONT_SM,
                color=ft.Colors.ON_SURFACE_VARIANT,
            ),
        )
    )

    # ── Premium ─────────────────────────────────────────────────────────
    if state.is_premium:
        rows.append(_divider())
        rows.append(
            _setting_row(
                ft.Icons.WORKSPACE_PREMIUM_ROUNDED,
                "Premium active",
                "Ad-free, with 200 assistant credits every day",
                ft.Icon(
                    ft.Icons.CHECK_CIRCLE_ROUNDED,
                    size=ICON_MD,
                    color=AppColors.SUCCESS,
                ),
            )
        )
    elif is_android:
        rows.append(_divider())
        rows.append(
            _setting_row(
                ft.Icons.WORKSPACE_PREMIUM_ROUNDED,
                "DDGS Premium",
                "Ad-free, with 200 assistant credits every day",
                ft.FilledButton(
                    "$3.99 / month",
                    on_click=lambda e: page.run_task(_buy, "premium_monthly"),
                    style=ft.ButtonStyle(
                        bgcolor=AppColors.PRIMARY,
                        color=ft.Colors.WHITE,
                        shape=ft.RoundedRectangleBorder(radius=BORDER_RADIUS_MD),
                    ),
                ),
                stacked=narrow,
            )
        )
        rows.append(_divider())
        rows.append(
            _setting_row(
                ft.Icons.CALENDAR_MONTH_ROUNDED,
                "Yearly",
                "Two months free compared with monthly",
                ft.OutlinedButton(
                    "$24.99 / year",
                    on_click=lambda e: page.run_task(_buy, "premium_yearly"),
                    style=ft.ButtonStyle(
                        color=AppColors.PRIMARY,
                        side=ft.BorderSide(1, AppColors.PRIMARY),
                        shape=ft.RoundedRectangleBorder(radius=BORDER_RADIUS_MD),
                    ),
                ),
                stacked=narrow,
            )
        )
        rows.append(_divider())
        rows.append(
            _setting_row(
                ft.Icons.ALL_INCLUSIVE_ROUNDED,
                "Lifetime",
                "Pay once, keep it",
                ft.OutlinedButton(
                    "$49.99",
                    on_click=lambda e: page.run_task(_buy, "premium_lifetime"),
                    style=ft.ButtonStyle(
                        color=AppColors.PRIMARY,
                        side=ft.BorderSide(1, AppColors.PRIMARY),
                        shape=ft.RoundedRectangleBorder(radius=BORDER_RADIUS_MD),
                    ),
                ),
                stacked=narrow,
            )
        )
        rows.append(_divider())
        rows.append(
            _setting_row(
                ft.Icons.RESTORE_ROUNDED,
                "Restore purchases",
                "Billed through Google Play. Cancel anytime in the Play Store",
                ft.TextButton(
                    "Restore",
                    on_click=lambda e: page.run_task(_restore),
                ),
                stacked=narrow,
            )
        )
    else:
        rows.append(_divider())
        rows.append(
            _setting_row(
                ft.Icons.WORKSPACE_PREMIUM_ROUNDED,
                "DDGS Premium",
                "Ad-free, with 200 assistant credits every day",
                ft.Text(
                    "Android only",
                    size=FONT_XS,
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

    _ = DAILY_FREE_CREDITS, RADIUS_SM, PREMIUM_PRODUCTS  # kept for parity
    return AppStyles.section_card(
        "Assistant & Premium",
        ft.Icons.CHAT_BUBBLE_OUTLINE_ROUNDED,
        ft.Column(rows, spacing=0, tight=True),
        page=page,
    )
