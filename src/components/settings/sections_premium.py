"""Settings -> DDGS Premium -- PLAY BUILD VARIANT.

The `main` branch version of this file also sells Premium through the Kiri
License Worker (Flutterwave: card, bank transfer, USDC) for direct APKs,
desktop and web. Google Play policy forbids an external-checkout prompt in
a Play-distributed app, so this branch ships only Play Billing. The client
for the other channel is a stub in `services/license_service.py`, so there
is no endpoint and no recovery-ID flow in this build at all.

The entitlement itself is unchanged: `state.is_premium` stays the single
flag that ads and the credit cap read, resolved by
`services/premium_service.py` from whichever channel is present.
"""

from __future__ import annotations

import flet as ft

from core.constants import DAILY_FREE_CREDITS, PREMIUM_DAILY_CREDITS
from core.state import state
from core.theme import AppColors, AppStyles
from core.tokens import (
    BORDER_RADIUS_MD,
    FONT_MD,
    FONT_XS,
    ICON_MD,
    ICON_SM,
    SPACE_XS,
    SPACE_XXS,
)

_OPACITY_BACKDROP = 0.08
_OPACITY_DIM = 0.6
_ICON_BACKDROP = 36
_ICON_BACKDROP_RADIUS = 10

PLAY_PLANS = (
    ("premium_monthly", "$3.99 / month", "Billed every month by Google Play"),
    ("premium_yearly", "$24.99 / year", "Two months free versus monthly"),
    ("premium_lifetime", "$49.99", "Pay once, keep it"),
)


def _divider() -> ft.Divider:
    return ft.Divider(
        height=1,
        thickness=1,
        color=ft.Colors.with_opacity(_OPACITY_DIM * 0.3, ft.Colors.OUTLINE),
    )


def _setting_row(icon, title, subtitle, trailing, stacked=False) -> ft.Container:
    """Sherlock settings row: icon backdrop, title + subtitle, control."""
    icon_box = ft.Container(
        content=ft.Icon(icon, size=ICON_MD, color=ft.Colors.ON_SURFACE_VARIANT),
        width=_ICON_BACKDROP,
        height=_ICON_BACKDROP,
        border_radius=_ICON_BACKDROP_RADIUS,
        bgcolor=ft.Colors.with_opacity(_OPACITY_BACKDROP, ft.Colors.ON_SURFACE),
        alignment=ft.Alignment.CENTER,
    )
    text_col = ft.Column(
        controls=[
            ft.Text(
                title, size=FONT_MD, weight=ft.FontWeight.W_500, font_family="Outfit"
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
        content = ft.Column(
            controls=[
                ft.Row(
                    controls=[icon_box, text_col],
                    spacing=16,
                    vertical_alignment=ft.CrossAxisAlignment.CENTER,
                ),
                ft.Row(controls=[ft.Container(width=_ICON_BACKDROP + 16), trailing]),
            ],
            spacing=SPACE_XS,
        )
    else:
        content = ft.Row(
            controls=[icon_box, text_col, trailing],
            spacing=16,
            vertical_alignment=ft.CrossAxisAlignment.CENTER,
        )
    return ft.Container(content=content, padding=ft.Padding(0, SPACE_XS, 0, SPACE_XS))


def build_premium_section(page: ft.Page) -> ft.Container:
    """Play-only Premium card: Play Billing, or a note on desktop."""
    controller = getattr(page, "_ddgs_controller", None)
    billing = getattr(controller, "billing", None) if controller else None
    narrow = bool(page.width and page.width < 560)
    play_ok = bool(billing) and page.platform == ft.PagePlatform.ANDROID

    def _snack(message: str, level: str = "info") -> None:
        snack = ft.SnackBar(
            ft.Text(message),
            bgcolor={
                "error": AppColors.ERROR,
                "success": AppColors.SUCCESS,
                "warning": AppColors.WARNING,
            }.get(level, AppColors.PRIMARY),
        )
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
            ok = await billing.buy_non_consumable(
                product_id, offer_token=result.products[0].offer_token
            )
            if not ok:
                _snack("Purchase could not start.")
        except Exception as exc:
            _snack(f"Billing error: {exc}", "error")

    rows: list[ft.Control] = []

    if state.is_premium:
        rows.append(
            _setting_row(
                ft.Icons.WORKSPACE_PREMIUM_ROUNDED,
                "Premium active",
                "No ads, and your daily Assistant credits are raised to "
                f"{PREMIUM_DAILY_CREDITS}",
                ft.Icon(
                    ft.Icons.CHECK_CIRCLE_ROUNDED,
                    size=ICON_MD,
                    color=AppColors.SUCCESS,
                ),
            )
        )
    else:
        rows.append(
            _setting_row(
                ft.Icons.WORKSPACE_PREMIUM_ROUNDED,
                "What Premium changes",
                "Removes ads and raises your daily Assistant credits from "
                f"{DAILY_FREE_CREDITS} to {PREMIUM_DAILY_CREDITS}. "
                "Everything else in DDGS stays the same",
                ft.Icon(
                    ft.Icons.WORKSPACE_PREMIUM_ROUNDED,
                    size=ICON_SM,
                    color=AppColors.PRIMARY,
                ),
            )
        )

    if play_ok:
        for product_id, label, blurb in PLAY_PLANS:
            rows.append(_divider())
            rows.append(
                _setting_row(
                    ft.Icons.LOCAL_OFFER_ROUNDED,
                    label,
                    blurb,
                    ft.FilledButton(
                        "Subscribe" if "month" in product_id else "Buy",
                        on_click=lambda e, pid=product_id: page.run_task(_buy, pid),
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
                ft.Icons.RESTORE_ROUNDED,
                "Restore purchases",
                "Billed through Google Play. Cancel anytime in the Play Store",
                ft.TextButton(
                    "Restore",
                    on_click=lambda e: page.run_task(
                        controller.verify_purchases if controller else (lambda: None)
                    ),
                ),
                stacked=narrow,
            )
        )
    else:
        rows.append(_divider())
        rows.append(
            _setting_row(
                ft.Icons.PHONE_ANDROID_ROUNDED,
                "Premium on Android",
                "Premium is sold through Google Play in this build",
                ft.Text(
                    "Android only",
                    size=FONT_XS,
                    color=ft.Colors.ON_SURFACE_VARIANT,
                ),
            )
        )

    return AppStyles.section_card(
        "DDGS Premium",
        ft.Icons.WORKSPACE_PREMIUM_ROUNDED,
        ft.Column(rows, spacing=0, tight=True),
        page=page,
    )
