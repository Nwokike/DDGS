"""Settings → AI & Premium: balance, cost table, AI switch, purchases."""

from __future__ import annotations

import flet as ft

from core.constants import (
    DAILY_FREE_CREDITS,
    PREMIUM_DAILY_CREDITS,
)
from core.state import state
from core.theme import AppColors, AppStyles
from core.tokens import BORDER_RADIUS_MD, FONT_MD, FONT_SM, FONT_XS

PREMIUM_PRODUCTS = ["premium_monthly", "premium_yearly", "premium_lifetime"]


def build_ai_section(page: ft.Page, save_fn) -> ft.Container:
    controller = getattr(page, "_ddgs_controller", None)
    billing = getattr(controller, "billing", None) if controller else None
    is_android = page.platform == ft.PagePlatform.ANDROID
    cap = PREMIUM_DAILY_CREDITS if state.is_premium else DAILY_FREE_CREDITS

    def _save(key: str, value) -> None:
        page.run_task(save_fn, key, value)

    async def _buy(product_id: str) -> None:
        if billing is None:
            return
        try:
            result = await billing.query_products([product_id])
            if not result.products:
                _snack("Product not found — create it in Play Console first.")
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
            _snack("Checking your purchases…")
        except Exception as exc:
            _snack(f"Restore failed: {exc}")

    def _snack(message: str) -> None:
        snack = ft.SnackBar(ft.Text(message))
        snack.open = True
        page.show_dialog(snack)
        try:
            page.update()
        except Exception:
            pass

    controls: list[ft.Control] = [
        ft.Row(
            [
                ft.Icon(
                    ft.Icons.AUTO_AWESOME_ROUNDED, size=22, color=AppColors.ACCENT
                ),
                ft.Text(
                    f"{state.credits_remaining} / {cap} AI credits today",
                    size=FONT_MD,
                    weight=ft.FontWeight.W_600,
                    font_family="Outfit",
                ),
            ],
            spacing=8,
            vertical_alignment=ft.CrossAxisAlignment.CENTER,
        ),
        ft.Text(
            "Reset daily at 00:00 UTC · unused ad-earned credits carry over. "
            "Manual search, scraping and downloads never use credits.",
            size=FONT_XS,
            color=ft.Colors.ON_SURFACE_VARIANT,
        ),
        ft.Row(
            [
                ft.Text("AI answer — 1", size=FONT_XS),
                ft.Text("Summary — 1", size=FONT_XS),
                ft.Text("Follow-up — 1", size=FONT_XS),
                ft.Text("Deep — 5", size=FONT_XS, color=AppColors.PRIMARY),
            ],
            spacing=10,
            wrap=True,
        ),
        ft.Row(
            [
                ft.Text(
                    "AI answers in results",
                    size=FONT_SM,
                    font_family="Outfit",
                    weight=ft.FontWeight.W_500,
                ),
                ft.Container(expand=True),
                ft.Switch(
                    value=state.ai_mode_enabled,
                    on_change=lambda e: _save("ai_mode", e.control.value),
                ),
            ],
            vertical_alignment=ft.CrossAxisAlignment.CENTER,
        ),
    ]

    if state.is_premium:
        controls.append(
            ft.Row(
                [
                    ft.Icon(
                        ft.Icons.CHECK_CIRCLE_ROUNDED,
                        size=18,
                        color=AppColors.SUCCESS,
                    ),
                    ft.Text(
                        "Premium active — ad-free, 200 AI credits/day.",
                        size=FONT_SM,
                        weight=ft.FontWeight.W_600,
                    ),
                ],
                spacing=6,
            )
        )
    elif is_android:
        controls.extend(
            [
                ft.Divider(height=10, thickness=1),
                ft.Text(
                    "DDGS Premium — ad-free + 200 AI credits/day",
                    size=FONT_SM,
                    weight=ft.FontWeight.W_600,
                    font_family="Outfit",
                ),
                ft.Row(
                    [
                        ft.FilledButton(
                            "$3.99 / month",
                            on_click=lambda e: page.run_task(
                                _buy, "premium_monthly"
                            ),
                            style=ft.ButtonStyle(
                                bgcolor=AppColors.PRIMARY,
                                shape=ft.RoundedRectangleBorder(
                                    radius=BORDER_RADIUS_MD
                                ),
                            ),
                            expand=True,
                        ),
                        ft.OutlinedButton(
                            "$24.99 / year",
                            on_click=lambda e: page.run_task(
                                _buy, "premium_yearly"
                            ),
                            style=ft.ButtonStyle(
                                shape=ft.RoundedRectangleBorder(
                                    radius=BORDER_RADIUS_MD
                                ),
                                side=ft.BorderSide(1, AppColors.PRIMARY),
                            ),
                            expand=True,
                        ),
                    ],
                    spacing=8,
                ),
                ft.Row(
                    [
                        ft.TextButton(
                            "Restore purchases",
                            icon=ft.Icons.RESTORE_ROUNDED,
                            on_click=lambda e: page.run_task(_restore),
                        ),
                        ft.Container(expand=True),
                        ft.TextButton(
                            "Lifetime $49.99",
                            on_click=lambda e: page.run_task(
                                _buy, "premium_lifetime"
                            ),
                        ),
                    ],
                ),
                ft.Text(
                    "Billed through Google Play. Cancel anytime in Play Store.",
                    size=FONT_XS,
                    color=ft.Colors.ON_SURFACE_VARIANT,
                ),
            ]
        )
    else:
        controls.append(
            ft.Text(
                "Premium (ad-free + 200 AI credits/day) is available in the "
                "Android app.",
                size=FONT_XS,
                color=ft.Colors.ON_SURFACE_VARIANT,
            )
        )

    _ = DAILY_FREE_CREDITS  # used above via cap
    return AppStyles.section_card(
        "AI & Premium",
        ft.Icons.AUTO_AWESOME_ROUNDED,
        ft.Column(controls, spacing=10),
        page=page,
    )
