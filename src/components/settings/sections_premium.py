"""Settings → DDGS Premium.

Premium is one entitlement with two possible channels:

  - **Kiri License** (card, bank transfer, USDC via Flutterwave) for direct
    builds, desktop and web. This is what a Windows user has, because Play
    Billing does not exist there.
  - **Google Play Billing** for the Play-distributed build.

The Play branch of this repository replaces this whole file with a
Play-only variant and ships a stub `license_service`, so an external
checkout button is not merely hidden in a Play build, it is absent from it.
See the module docstring in src/services/license_service.py.

Prices always come from the Worker's live /catalog rather than constants, so
changing a price there needs no app release.
"""

from __future__ import annotations

import flet as ft

from components.results.downloader import launch_url
from core.constants import DAILY_FREE_CREDITS, PREMIUM_DAILY_CREDITS
from core.state import state
from core.theme import AppColors, AppStyles
from core.tokens import (
    BORDER_RADIUS_MD,
    FONT_MD,
    FONT_SM,
    FONT_XS,
    ICON_MD,
    ICON_SM,
    SPACE_XS,
    SPACE_XXS,
)
from services import license_service, premium_service

_OPACITY_BACKDROP = 0.08
_OPACITY_DIM = 0.6
_ICON_BACKDROP = 36
_ICON_BACKDROP_RADIUS = 10

_STATUS_COPY = {
    "active": ("Premium active", "Everything Premium includes is switched on"),
    "grace": ("Payment overdue", "Finish your payment to keep Premium"),
    "expired": ("Premium expired", "Renew to switch Premium back on"),
    "revoked": ("Premium refunded", "A refund turned Premium off"),
}


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


def _field(label: str, value: str, *, password: bool = False) -> ft.TextField:
    return ft.TextField(
        label=label,
        value=value,
        dense=True,
        password=password,
        can_reveal_password=password,
        border=ft.OutlineInputBorder(border_radius=BORDER_RADIUS_MD),
        content_padding=ft.Padding(12, 12, 12, 12),
    )


def build_premium_section(page: ft.Page) -> ft.Container:
    """The Premium card. Channel choice is a build-time policy, not a toggle."""
    controller = getattr(page, "_ddgs_controller", None)
    billing = getattr(controller, "billing", None) if controller else None
    narrow = bool(page.width and page.width < 560)
    # The build channel is stamped into the artifact, not chosen at runtime.
    from core.build_channel import CHANNEL

    license_ok = license_service.is_available(page)
    # Play Billing is only ever offered in a direct build, and only once the
    # store actually lists our products. On the Play AAB this stays False
    # because CHANNEL is "play", so no purchase row can appear.
    play_ok = (
        CHANNEL != "play"
        and bool(billing)
        and page.platform == ft.PagePlatform.ANDROID
    )

    email_field = _field("Email", "")
    name_field = _field("Name (optional)", "")
    phone_field = _field("Phone (optional)", "")
    recovery_field = _field("Recovery ID", state.license_recovery_id)

    rows: list[ft.Control] = []

    def _snack(message: str, level: str = "info") -> None:
        from core.theme import AppTheme  # noqa: F401  (kept for future theming)

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

    async def _save_contact() -> None:
        if controller is None or controller.storage is None:
            return
        await controller.storage.set_license_record(
            email=email_field.value or "",
            name=name_field.value or "",
            phone=phone_field.value or "",
        )

    async def _copy_recovery() -> None:
        recovery_id = recovery_field.value or state.license_recovery_id
        if not recovery_id:
            _snack("There is no recovery ID to copy yet", "warning")
            return
        try:
            clipboard = ft.Clipboard()
            page.services.append(clipboard)
            await clipboard.set_data(recovery_id)
            _snack("Recovery ID copied. Keep it somewhere safe.", "success")
        except Exception as exc:
            _snack(f"Could not copy automatically: {exc}", "error")

    async def _checkout(product_id: str) -> None:
        email = (email_field.value or "").strip()
        if not license_service.valid_email(email):
            _snack("Enter a valid email address to continue", "warning")
            return
        await _save_contact()
        try:
            result = await license_service.start_checkout(
                product_id,
                email=email,
                name=name_field.value or "",
                phone=phone_field.value or "",
            )
        except license_service.LicenseUnavailable as exc:
            _snack(str(exc), "error")
            return
        except license_service.LicenseError as exc:
            _snack(f"Could not start the payment: {exc}", "error")
            return
        recovery_field.value = result["recovery_id"]
        state.license_recovery_id = result["recovery_id"]
        if controller is not None and controller.storage is not None:
            await controller.storage.set_license_record(
                recovery_id=result["recovery_id"]
            )
        url = result.get("checkout_url") or ""
        if url:
            await launch_url(url, page)
        _snack(
            "Finish the payment in your browser, then tap Check status.",
            "success",
        )

    async def _restore() -> None:
        recovery_id = (recovery_field.value or "").strip()
        if not recovery_id:
            _snack("Paste the recovery ID from your receipt first", "warning")
            return
        try:
            entitlement = await premium_service.restore_license(recovery_id)
        except license_service.LicenseUnavailable as exc:
            _snack(str(exc), "error")
            return
        except license_service.LicenseError as exc:
            _snack(f"Restore failed: {exc}", "error")
            return
        if entitlement.grants_access:
            _snack("Premium restored. Thank you.", "success")
            if controller is not None:
                await controller._grant_premium_benefits()
                await controller._sync_premium_storage()
        else:
            _snack(f"That licence is {entitlement.status}", "warning")

    async def _check_status() -> None:
        if not state.license_recovery_id:
            _snack("Buy Premium first, then check the status", "warning")
            return
        answered = await premium_service.refresh_from_server(page)
        if controller is not None:
            await controller._sync_premium_storage()
        if not answered:
            # Never claim a confirmation we did not receive. Saying
            # "Payment confirmed" after a failed request is the one message
            # a buyer would be most misled by.
            _snack(
                "Could not reach the payment service. Check your connection "
                "and try again.",
                "warning",
            )
        elif state.license_status in ("active", "grace"):
            _snack("Payment confirmed. Premium is on.", "success")
        else:
            _snack(f"Payment status: {state.license_status}", "warning")

    async def _opt_in_direct(enabled: bool) -> None:
        """Turn the direct channel on or off and remember the choice.

        A direct APK user reaches this only after telling us Play payment
        is not working for them, which is the build where it can fail for
        reasons that are not ours.
        """
        license_service.set_available(page, enabled)
        if controller is not None and controller.storage is not None:
            try:
                if not await license_service.save_opt_in(
                    controller.storage, enabled
                ):
                    # save_opt_in swallows the error and returns False, so
                    # the choice would silently vanish on restart.
                    _snack(
                        "Could not remember that choice. It will reset when "
                        "you restart.",
                        "warning",
                    )
            except Exception as exc:
                _snack(f"Could not save that choice: {exc}", "error")
        _snack(
            "Direct checkout enabled. Pull in from the direct APK."
            if enabled
            else "Direct checkout turned off.",
            "success",
        )

    async def _play_buy(product_id: str) -> None:
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

    # ── Status ──────────────────────────────────────────────────────────
    if state.is_premium:
        title, subtitle = _STATUS_COPY.get(
            state.license_status if state.license_premium_active else "active",
            ("Premium active", "Everything Premium includes is switched on"),
        )
        if state.license_status in ("grace",):
            title, subtitle = _STATUS_COPY["grace"]
        rows.append(
            _setting_row(
                ft.Icons.WORKSPACE_PREMIUM_ROUNDED,
                title,
                subtitle,
                ft.Icon(
                    ft.Icons.CHECK_CIRCLE_ROUNDED,
                    size=ICON_MD,
                    color=AppColors.SUCCESS,
                ),
            )
        )
        if state.premium_source:
            rows.append(_divider())
            rows.append(
                _setting_row(
                    ft.Icons.SOURCE_ROUNDED,
                    "Granted by",
                    "Credit cap is now "
                    f"{PREMIUM_DAILY_CREDITS} a day and ads are switched off",
                    ft.Text(
                        state.premium_source.split(":", 1)[-1] or "DDGS",
                        size=FONT_SM,
                        color=ft.Colors.ON_SURFACE_VARIANT,
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

    # ── License channel (direct, desktop, web) ───────────────────────────
    if license_ok:
        rows.append(_divider())
        rows.append(
            _setting_row(
                ft.Icons.CREDIT_CARD_ROUNDED,
                "Your details",
                "Used only for the receipt. Card and bank transfer are "
                "handled by our payment partner, never by DDGS",
                ft.Icon(
                    ft.Icons.LOCK_OUTLINE_ROUNDED,
                    size=ICON_SM,
                    color=ft.Colors.ON_SURFACE_VARIANT,
                ),
            )
        )
        rows.append(
            ft.Container(
                content=ft.Column(
                    [email_field, name_field, phone_field],
                    spacing=SPACE_XS,
                    tight=True,
                ),
                padding=ft.Padding(_ICON_BACKDROP + 16, 0, 0, SPACE_XS),
            )
        )

        rows.append(_divider())
        rows.append(
            _setting_row(
                ft.Icons.SHOPPING_CART_ROUNDED,
                "Choose a plan",
                "One-time payment or a plan that renews until you cancel",
                ft.Icon(
                    ft.Icons.PAYMENTS_ROUNDED,
                    size=ICON_SM,
                    color=ft.Colors.ON_SURFACE_VARIANT,
                ),
            )
        )
        for product_id, blurb in (
            ("monthly", "Renews monthly, cancel any time"),
            ("yearly", "Two months free versus monthly"),
            ("lifetime", "Pay once, keep it"),
        ):
            rows.append(_divider())
            price = state.license_prices.get(product_id, "")
            rows.append(
                _setting_row(
                    ft.Icons.LOCAL_OFFER_ROUNDED,
                    f"{product_id.capitalize()} {price}".rstrip() if price
                    else product_id.capitalize(),
                    blurb,
                    ft.FilledButton(
                        price or "Choose",
                        on_click=lambda e, pid=product_id: page.run_task(
                            _checkout, pid
                        ),
                        style=ft.ButtonStyle(
                            bgcolor=AppColors.PRIMARY,
                            color=ft.Colors.WHITE,
                            shape=ft.RoundedRectangleBorder(
                                radius=BORDER_RADIUS_MD
                            ),
                        ),
                    ),
                    stacked=narrow,
                )
            )

        rows.append(_divider())
        rows.append(
            _setting_row(
                ft.Icons.KEY_ROUNDED,
                "Your recovery ID",
                "Save this. It is the only way to restore Premium after "
                "clearing app data or moving to another device",
                ft.TextButton(
                    "Copy",
                    icon=ft.Icons.CONTENT_COPY_ROUNDED,
                    on_click=lambda e: page.run_task(_copy_recovery),
                ),
                stacked=narrow,
            )
        )
        rows.append(
            ft.Container(
                content=ft.Column(
                    [recovery_field],
                    spacing=SPACE_XS,
                    tight=True,
                ),
                padding=ft.Padding(_ICON_BACKDROP + 16, 0, 0, SPACE_XS),
            )
        )
        rows.append(_divider())
        rows.append(
            _setting_row(
                ft.Icons.RESTORE_ROUNDED,
                "Restore or check status",
                "Paste your recovery ID to restore, or confirm a payment you "
                "just made",
                ft.Row(
                    [
                        ft.TextButton(
                            "Restore",
                            on_click=lambda e: page.run_task(_restore),
                        ),
                        ft.TextButton(
                            "Check status",
                            on_click=lambda e: page.run_task(_check_status),
                        ),
                    ],
                    spacing=4,
                    tight=True,
                ),
                stacked=narrow,
            )
        )

    # ── Play channel (Play-distributed builds only) ─────────────────────
    if play_ok and not license_ok:
        for product_id, label, blurb in (
            ("premium_monthly", "$3.99 / month", "Billed every month by Google Play"),
            ("premium_yearly", "$24.99 / year", "Two months free versus monthly"),
            ("premium_lifetime", "$49.99", "Pay once, keep it"),
        ):
            rows.append(_divider())
            rows.append(
                _setting_row(
                    ft.Icons.LOCAL_OFFER_ROUNDED,
                    label,
                    blurb,
                    ft.FilledButton(
                        "Subscribe" if "month" in product_id else "Buy",
                        on_click=lambda e, pid=product_id: page.run_task(
                            _play_buy, pid
                        ),
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
                        controller.verify_purchases
                        if controller
                        else (lambda: None)
                    ),
                ),
                stacked=narrow,
            )
        )

    # ── No purchase channel in this build ───────────────────────────────
    if not license_ok and not play_ok:
        # The Play AAB lands here. Say where Premium IS available, so the
        # card is an honest explanation rather than a dead end, and offer
        # no purchase control of any kind.
        from core.build_channel import CHANNEL

        if CHANNEL == "play":
            rows.append(_divider())
            rows.append(
                _setting_row(
                    ft.Icons.OPEN_IN_NEW_ROUNDED,
                    "Premium is not sold in this build",
                    "This is the Google Play version, which is free with ads. "
                    "Premium is sold on the direct APK, on desktop and on "
                    "the web",
                    ft.Text(
                        "Free tier",
                        size=FONT_XS,
                        color=ft.Colors.ON_SURFACE_VARIANT,
                    ),
                )
            )
        else:
            # A direct Android APK that has not opted in yet.
            rows.append(_divider())
            rows.append(
                _setting_row(
                    ft.Icons.PAYMENTS_ROUNDED,
                    "Google Play payment not working?",
                    "Buy Premium here with a card, bank transfer or USDC "
                    "instead of through Google Play",
                    ft.OutlinedButton(
                        "Enable",
                        on_click=lambda e: page.run_task(_opt_in_direct, True),
                        style=ft.ButtonStyle(
                            color=AppColors.PRIMARY,
                            side=ft.BorderSide(1, AppColors.PRIMARY),
                            shape=ft.RoundedRectangleBorder(
                                radius=BORDER_RADIUS_MD
                            ),
                        ),
                    ),
                    stacked=narrow,
                )
            )

    return AppStyles.section_card(
        "DDGS Premium",
        ft.Icons.WORKSPACE_PREMIUM_ROUNDED,
        ft.Column(rows, spacing=0, tight=True),
        page=page,
    )
