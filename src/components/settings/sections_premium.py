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

Shape: KTV Player's. The card is four rows — what Premium is, what a plan
costs, your recovery ID, restore — and the typing happens in a dialog that
only exists once you ask for it. A settings card that lists every field it
will ever need is a form, not a menu.
"""

from __future__ import annotations

import re

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
from services import license_service

_OPACITY_BACKDROP = 0.08
_OPACITY_DIM = 0.6
_ICON_BACKDROP = 36
_ICON_BACKDROP_RADIUS = 10

EMAIL_RE = re.compile(r"^\S+@\S+\.\S+$")

_STATUS_COPY = {
    "active": ("Premium active", "Everything Premium includes is switched on"),
    "grace": ("Payment overdue", "Finish your payment to keep Premium"),
    "expired": ("Premium expired", "Renew to switch Premium back on"),
    "revoked": ("Premium refunded", "A refund turned Premium off"),
}

# The plans, in the order a buyer compares them. The price next to each is
# read from state.license_prices, never written here.
_PLANS = (
    ("monthly", "Renews monthly, cancel any time"),
    ("yearly", "Two months free versus monthly"),
    ("lifetime", "Pay once, keep it"),
)

# One catalog fetch per launch, not one per repaint of this card.
_prices_attempted = False


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


def _field(label: str, value: str = "") -> ft.TextField:
    return ft.TextField(
        label=label,
        value=value,
        dense=True,
        border=ft.OutlineInputBorder(border_radius=BORDER_RADIUS_MD),
        content_padding=ft.Padding(12, 12, 12, 12),
    )


def _buy_button(label: str, on_click) -> ft.FilledButton:
    return ft.FilledButton(
        label,
        on_click=on_click,
        style=ft.ButtonStyle(
            bgcolor=AppColors.PRIMARY,
            color=ft.Colors.WHITE,
            shape=ft.RoundedRectangleBorder(radius=BORDER_RADIUS_MD),
        ),
    )


def _retry_prices(page: ft.Page, premium) -> None:
    """Fetch the catalog once if startup could not reach the Worker.

    Without this a single failed launch leaves the card with no prices
    until the next restart, which reads as "you cannot buy this".
    """
    global _prices_attempted
    if _prices_attempted or state.license_prices:
        return
    _prices_attempted = True

    async def _load() -> None:
        global _prices_attempted
        try:
            products = await premium.kiri_catalog(force=True)
        except Exception:
            _prices_attempted = False  # let a later build try again
            return
        prices = {
            p.id: p.price_label for p in products if p.id and p.amount
        }
        if prices:
            state.license_prices = prices

    try:
        page.run_task(_load)
    except Exception:
        pass


def build_premium_section(page: ft.Page) -> ft.Container:
    """The Premium card. Channel choice is a build-time policy, not a toggle."""
    controller = getattr(page, "_ddgs_controller", None)
    billing = getattr(controller, "billing", None) if controller else None
    narrow = bool(page.width and page.width < 560)
    # The build channel is stamped into the artifact, not chosen at runtime.
    from core.build_channel import CHANNEL

    premium = getattr(controller, "premium", None)
    # Availability is a build property: KTV Player gates it on CHANNEL and
    # so do we. A Play build has no licence service instance at all.
    license_ok = bool(premium) and premium.available
    # Play Billing is only ever offered in a direct build, and only once the
    # store actually lists our products. On the Play AAB this stays False
    # because CHANNEL is "play", so no purchase row can appear.
    play_ok = (
        CHANNEL != "play"
        and bool(billing)
        and page.platform == ft.PagePlatform.ANDROID
    )

    rows: list[ft.Control] = []

    # One billing operation at a time. KTV Player does this with a
    # `license_busy` flag that disables the buttons; DDGS's card is a static
    # build with no repaint, so the guard has to be in the callback itself.
    # Without it a second tap on Continue creates a second real order at the
    # Worker — two pending payment sessions and two recovery IDs for one
    # customer.
    _inflight: set[str] = set()

    async def _exclusive(key: str, coro) -> None:
        if key in _inflight:
            coro.close()
            return
        _inflight.add(key)
        try:
            await coro
        finally:
            _inflight.discard(key)

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

    async def _copy_recovery() -> None:
        recovery_id = state.license_recovery_id
        if not recovery_id:
            _snack("There is no recovery ID to copy yet", "warning")
            return
        try:
            # Built and closed per call. Appending it to page.services left
            # one more service registered on every press, for the life of
            # the process.
            clipboard = ft.Clipboard()
            try:
                page.services.append(clipboard)
                await clipboard.set(recovery_id)
            finally:
                try:
                    page.services.remove(clipboard)
                except ValueError:
                    pass
            _snack("Recovery ID copied. Keep it somewhere safe.", "success")
        except Exception as exc:
            _snack(f"Could not copy automatically: {exc}", "error")

    def _ask_email(product_id: str) -> None:
        """The form appears when you ask to buy, not before.

        KTV Player collects exactly one required field — the email the
        receipt goes to — and this card does the same, with name and phone
        behind it because the Worker takes them but nobody is forced to
        type them.
        """
        email_field = _field("Email for your receipt")
        email_field.hint_text = "you@example.com"
        email_field.keyboard_type = ft.KeyboardType.EMAIL
        name_field = _field("Name (optional)")
        phone_field = _field("Phone (optional)")
        price = state.license_prices.get(product_id, "")
        label = f"{product_id.capitalize()} {price}".rstrip()
        page.show_dialog(
            ft.AlertDialog(
                title=ft.Text(f"Unlock DDGS Premium — {label}", font_family="Outfit"),
                content=ft.Container(
                    content=ft.Column(
                        [
                            ft.Text(
                                "Card, bank transfer and USDC are handled by our "
                                "payment partner. DDGS never sees the card number.",
                                size=FONT_XS,
                                color=ft.Colors.with_opacity(
                                    _OPACITY_DIM, ft.Colors.ON_SURFACE
                                ),
                            ),
                            email_field,
                            name_field,
                            phone_field,
                        ],
                        spacing=SPACE_XS,
                        tight=True,
                    ),
                    width=360,
                    padding=ft.Padding(4, 8, 4, 4),
                ),
                actions=[
                    ft.TextButton(
                        "Cancel", on_click=lambda e: page.pop_dialog()
                    ),
                    ft.FilledButton(
                        "Continue",
                        on_click=lambda e: page.run_task(
                            _exclusive,
                            f"checkout:{product_id}",
                            _checkout(
                                product_id, email_field, name_field, phone_field
                            ),
                        ),
                    ),
                ],
            )
        )

    async def _checkout(
        product_id: str,
        email_field: ft.TextField,
        name_field: ft.TextField,
        phone_field: ft.TextField,
    ) -> None:
        email = (email_field.value or "").strip()
        if not EMAIL_RE.match(email):
            _snack("Enter a valid email address to continue", "warning")
            return
        # Dismiss before the network call: a dialog left open over a slow
        # request reads as a hang, and the button behind it does nothing.
        page.pop_dialog()
        premium = getattr(controller, "premium", None)
        if premium is None:
            _snack("Premium is unavailable in this build", "error")
            return
        try:
            order = await premium.kiri_checkout(
                product_id,
                email,
                name=name_field.value or "",
                phone=phone_field.value or "",
            )
        except license_service.LicenseUnavailable as exc:
            _snack(str(exc), "error")
            return
        except Exception as exc:
            # A timeout or DNS failure is not a LicenseUnavailable. Catching
            # only that leaves the dialog closed with no message at all,
            # which is indistinguishable from a hang at the exact moment the
            # customer is waiting on money.
            _snack(f"Could not start the payment: {exc}", "error")
            return
        # Record the recovery ID BEFORE opening the browser. A browser that
        # will not open is the most common checkout failure, and it must not
        # be the case that loses the only artifact that restores the purchase.
        # Never assign to a control: this card is a rendered component, so
        # its controls are frozen. Write the observable instead and let the
        # component repaint, which is how the recovery row gets its value.
        state.license_recovery_id = order.recovery_id
        if order.checkout_url:
            try:
                await launch_url(order.checkout_url, page)
            except Exception as exc:
                _snack(
                    f"Could not open the payment page: {exc} — your recovery "
                    f"ID is {order.recovery_id}. Keep it; it restores the "
                    "purchase.",
                    "error",
                )
                return
        # Restoring is what issues the signed token: /status never returns
        # one, so pointing a fresh buyer at "Check status" would confirm a
        # payment and still leave Premium off. KTV Player sends them here.
        _snack(
            "Complete the payment in your browser, then tap Restore.",
            "success",
        )

    def _ask_recovery(e=None) -> None:
        field = _field("Recovery ID", state.license_recovery_id)
        field.hint_text = state.license_recovery_id or "KIRI-L-..."
        page.show_dialog(
            ft.AlertDialog(
                title=ft.Text("Restore your license", font_family="Outfit"),
                content=ft.Container(
                    content=ft.Column(
                        [
                            field,
                            ft.Text(
                                "Your recovery ID is shown on the payment receipt. "
                                "It is also stored on this device.",
                                size=FONT_XS,
                                color=ft.Colors.with_opacity(
                                    _OPACITY_DIM, ft.Colors.ON_SURFACE
                                ),
                            ),
                        ],
                        tight=True,
                        spacing=SPACE_XS,
                    ),
                    width=360,
                    padding=ft.Padding(4, 8, 4, 4),
                ),
                actions=[
                    ft.TextButton(
                        "Cancel", on_click=lambda e: page.pop_dialog()
                    ),
                    ft.FilledButton(
                        "Restore",
                        on_click=lambda e: page.run_task(
                            _exclusive, "restore", _restore(field)
                        ),
                    ),
                ],
            )
        )

    async def _restore(field: ft.TextField) -> None:
        recovery_id = (field.value or "").strip().upper()
        page.pop_dialog()
        if not recovery_id:
            _snack("Paste the recovery ID from your receipt first", "warning")
            return
        premium = getattr(controller, "premium", None)
        if premium is None:
            _snack("Premium is unavailable in this build", "error")
            return
        # Captured before the call: the arbiter flips `is_premium` inside
        # kiri_restore, so the pre-flip value is the only record of whether
        # this was an activation.
        was_premium = state.is_premium
        try:
            status = await premium.kiri_restore(recovery_id)
        except license_service.LicenseUnavailable as exc:
            # A refusal (402/403/404) already dropped the unlock inside the
            # client, so the message here is the server's own reason.
            _snack(str(exc), "error")
            return
        except Exception as exc:
            _snack(f"Restore failed: {exc}", "error")
            return
        state.license_recovery_id = recovery_id
        if controller is not None:
            await controller._grant_premium_benefits(
                first_time=not was_premium
            )
            await controller._sync_premium_storage()
        # Branch on the verdict, not on the endpoint's own status word: the
        # arbiter ORs in the Play channel, so `status.unlocks` alone could
        # announce success while the app-wide flag is still False.
        if state.is_premium:
            _snack("Premium restored. Thank you.", "success")
        else:
            _snack(f"That licence is {status.status}", "warning")

    if license_ok and not state.license_prices:
        _retry_prices(page, premium)

    # ── Status ──────────────────────────────────────────────────────────
    if state.is_premium:
        title, subtitle = _STATUS_COPY.get(
            state.license_status if state.license_premium_active else "active",
            ("Premium active", "Everything Premium includes is switched on"),
        )
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
        if state.license_status in _STATUS_COPY:
            # The whole status block used to sit inside `if is_premium`, so
            # grace, expired and revoked were unreachable: a customer whose
            # payment lapsed was shown "What Premium changes" and a wall of
            # buy buttons with no explanation. Say what happened first; the
            # way back is the very next section.
            title, subtitle = _STATUS_COPY[state.license_status]
            rows.append(
                _setting_row(
                    ft.Icons.REPORT_ROUNDED,
                    title,
                    subtitle,
                    ft.Icon(
                        ft.Icons.ERROR_OUTLINE_ROUNDED,
                        size=ICON_SM,
                        color=AppColors.WARNING,
                    ),
                )
            )
            rows.append(_divider())
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
    # Product rows, the recovery ID and Restore are the whole card; the
    # typing lives in dialogs. Nothing is pre-expanded.
    if license_ok and not state.is_premium:
        if state.license_prices:
            for product_id, blurb in _PLANS:
                price = state.license_prices.get(product_id, "")
                if not price:
                    continue
                rows.append(_divider())
                rows.append(
                    _setting_row(
                        ft.Icons.LOCK_OPEN_ROUNDED
                        if product_id == "lifetime"
                        else ft.Icons.AUTORENEW_ROUNDED,
                        product_id.capitalize(),
                        blurb,
                        _buy_button(
                            price,
                            lambda e, pid=product_id: _ask_email(pid),
                        ),
                        stacked=narrow,
                    )
                )
        else:
            # KTV Player renders no buy rows at all when the catalog did not
            # load. Three live buttons labelled "Choose" let a customer start
            # a payment for a price they were never shown, under a heading
            # that says the service is unreachable.
            rows.append(_divider())
            rows.append(
                _setting_row(
                    ft.Icons.CLOUD_OFF_ROUNDED,
                    "Unlock options unavailable",
                    "Could not reach the license service — check your "
                    "connection",
                    ft.Icon(
                        ft.Icons.CLOUD_OFF_ROUNDED,
                        size=ICON_SM,
                        color=ft.Colors.ON_SURFACE_VARIANT,
                    ),
                )
            )

        if state.license_recovery_id:
            rows.append(_divider())
            rows.append(
                _setting_row(
                    ft.Icons.KEY_ROUNDED,
                    "Your recovery ID",
                    state.license_recovery_id,
                    ft.OutlinedButton(
                        "Copy",
                        icon=ft.Icons.CONTENT_COPY_ROUNDED,
                        on_click=lambda e: page.run_task(
                            _exclusive, "copy", _copy_recovery()
                        ),
                    ),
                    stacked=narrow,
                )
            )

    if license_ok:
        rows.append(_divider())
        rows.append(
            _setting_row(
                ft.Icons.RESTORE_ROUNDED,
                "Restore purchases",
                "Re-check ownership (new device / reinstall / after paying)",
                ft.OutlinedButton(
                    "Restore",
                    on_click=_ask_recovery,
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

    return AppStyles.section_card(
        "DDGS Premium",
        ft.Icons.WORKSPACE_PREMIUM_ROUNDED,
        ft.Column(rows, spacing=0, tight=True),
        page=page,
    )
