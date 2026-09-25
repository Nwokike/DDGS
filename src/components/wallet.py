"""AI credit pill + wallet dialog — SpanInsight's pattern, DDGS copy."""

from __future__ import annotations

import asyncio
import time

import flet as ft

from contexts.app_state_ctx import AppStateCtx
from core import tokens
from core.constants import (
    AD_TOPUP_COOLDOWN_SEC,
    AD_TOPUP_CREDITS,
    COST_STEP,
    DAILY_FREE_CREDITS,
)
from core.state import state
from core.theme import AppColors


def _credit_color(credits: int) -> str:
    if credits > 20:
        return AppColors.SUCCESS
    if credits >= 5:
        return AppColors.WARNING
    return AppColors.ERROR


def build_credit_pill(page: ft.Page, credits: int) -> ft.Container:
    """Compact color-coded credit chip for the home header."""
    color = _credit_color(credits)
    return ft.Container(
        content=ft.Row(
            [
                ft.Icon(
                    ft.Icons.CHAT_BUBBLE_OUTLINE_ROUNDED, size=tokens.ICON_SM, color=color
                ),
                ft.Text(
                    str(credits),
                    size=tokens.FONT_SM,
                    weight=ft.FontWeight.W_600,
                    color=color,
                ),
            ],
            spacing=4,
            tight=True,
        ),
        padding=ft.Padding(8, 4, 10, 4),
        border_radius=tokens.RADIUS_PILL,
        bgcolor=ft.Colors.with_opacity(0.12, color),
        border=ft.Border.all(1, ft.Colors.with_opacity(0.25, color)),
        ink=True,
        tooltip="Assistant credits, tap for details",
        on_click=lambda e: show_wallet_dialog(page),
    )


def show_wallet_dialog(page: ft.Page) -> None:
    """Balance, cost table, ad top-up (30s cooldown) and the free-manual note."""
    if not hasattr(state, "ad_cooldown_end"):
        state.ad_cooldown_end = 0.0

    is_mobile = page.platform in (ft.PagePlatform.ANDROID, ft.PagePlatform.IOS)
    is_premium = state.is_premium

    balance_text = ft.Text(
        str(state.credits_remaining),
        size=tokens.FONT_XL,
        weight=ft.FontWeight.BOLD,
        color=_credit_color(state.credits_remaining),
    )
    cooldown_label = ft.Text("", size=tokens.FONT_XS, text_align=ft.TextAlign.CENTER)

    # The simulated ad is a development affordance, not a product feature:
    # it pretended to play an ad on desktop, where no ad will ever exist.
    # Desktop users are pointed at Premium instead.
    topup_label = f"Watch Ad (+{AD_TOPUP_CREDITS} Credits)"
    watch_btn = ft.FilledButton(
        content=ft.Row(
            [
                ft.Icon(
                    ft.Icons.PLAY_CIRCLE_ROUNDED,
                    size=tokens.ICON_SM,
                    color=ft.Colors.WHITE,
                ),
                ft.Text(
                    topup_label if not is_premium else "Premium active, 200/day",
                    size=tokens.FONT_SM,
                    color=ft.Colors.WHITE,
                ),
            ],
            spacing=6,
            tight=True,
        ),
        bgcolor=AppColors.PRIMARY,
        disabled=is_premium,
    )

    dialog_open = True

    def _open_premium(e=None):
        """Desktop has no ads to watch: send the user to the Premium card."""
        _close()
        ctrl = getattr(page, "_ddgs_controller", None)
        if ctrl is not None:
            ctrl.navigate_tab(2)
            try:
                page.update()
            except Exception:
                pass

    def _close(e=None):
        nonlocal dialog_open
        dialog_open = False
        try:
            page.pop_dialog()
        except Exception:
            pass

    async def _countdown():
        while dialog_open:
            remaining = int(state.ad_cooldown_end - time.time())
            if is_premium:
                break
            if remaining > 0:
                watch_btn.disabled = True
                watch_btn.content = ft.Row(
                    [
                        ft.Icon(
                            ft.Icons.PLAY_CIRCLE_ROUNDED,
                            size=tokens.ICON_SM,
                            color=ft.Colors.WHITE,
                        ),
                        ft.Text(
                            f"Cooldown ({remaining}s)",
                            size=tokens.FONT_SM,
                            color=ft.Colors.WHITE,
                        ),
                    ],
                    spacing=6,
                    tight=True,
                )
            else:
                watch_btn.disabled = False
                watch_btn.content = ft.Row(
                    [
                        ft.Icon(
                            ft.Icons.PLAY_CIRCLE_ROUNDED,
                            size=tokens.ICON_SM,
                            color=ft.Colors.WHITE,
                        ),
                        ft.Text(topup_label, size=tokens.FONT_SM, color=ft.Colors.WHITE),
                    ],
                    spacing=6,
                    tight=True,
                )
            try:
                watch_btn.update()
            except Exception:
                return
            if remaining <= 0:
                break
            await asyncio.sleep(0.5)

    async def _on_watch_success():
        new_balance = await _credits().add_credits(AD_TOPUP_CREDITS)
        state.credits_remaining = new_balance
        balance_text.value = str(new_balance)
        balance_text.color = _credit_color(new_balance)
        cooldown_label.value = f"+{AD_TOPUP_CREDITS} credits added!"
        try:
            balance_text.update()
            cooldown_label.update()
        except Exception:
            pass

    async def _on_watch(e):
        if is_premium:
            return
        now = time.time()
        if state.ad_cooldown_end > now:
            cooldown_label.value = f"Please wait {int(state.ad_cooldown_end - now)}s."
            try:
                cooldown_label.update()
            except Exception:
                pass
            return
        state.ad_cooldown_end = now + AD_TOPUP_COOLDOWN_SEC
        watch_btn.disabled = True
        try:
            watch_btn.update()
        except Exception:
            pass
        page.run_task(_countdown)
        from services.ad_service import AdService

        ad_service = getattr(state, "ad_service", None) or AdService(page)
        ok = await ad_service.show_rewarded_interstitial(_on_watch_success)
        if not ok:
            state.ad_cooldown_end = 0.0

    watch_btn.on_click = lambda e: page.run_task(_on_watch, e)

    def _row(
        icon: ft.IconData,
        title: str,
        subtitle: str,
        trailing: ft.Control,
    ) -> ft.Container:
        icon_box = ft.Container(
            content=ft.Icon(icon, size=tokens.ICON_MD, color=ft.Colors.ON_SURFACE_VARIANT),
            width=36,
            height=36,
            border_radius=10,
            bgcolor=ft.Colors.with_opacity(0.08, ft.Colors.ON_SURFACE),
            alignment=ft.Alignment.CENTER,
        )
        return ft.Container(
            content=ft.Row(
                [
                    icon_box,
                    ft.Column(
                        [
                            ft.Text(
                                title,
                                size=tokens.FONT_MD,
                                weight=ft.FontWeight.W_500,
                                font_family="Outfit",
                            ),
                            ft.Text(
                                subtitle,
                                size=tokens.FONT_XS,
                                color=ft.Colors.with_opacity(
                                    0.6, ft.Colors.ON_SURFACE
                                ),
                            ),
                        ],
                        spacing=2,
                        expand=True,
                    ),
                    trailing,
                ],
                spacing=tokens.SPACE_MD,
                vertical_alignment=ft.CrossAxisAlignment.CENTER,
            ),
            padding=ft.Padding(0, tokens.SPACE_XS, 0, tokens.SPACE_XS),
        )

    def _cost_row(label: str, cost: str) -> ft.Control:
        if cost == "free":
            return _row(
                ft.Icons.MONEY_OFF_ROUNDED,
                label,
                "No credits used",
                ft.Text(
                    "Free",
                    size=tokens.FONT_SM,
                    weight=ft.FontWeight.W_600,
                    color=AppColors.SUCCESS,
                ),
            )
        return _row(
            ft.Icons.BOLT_ROUNDED,
            label,
            "One assistant step",
            ft.Text(
                f"{cost} credit",
                size=tokens.FONT_SM,
                weight=ft.FontWeight.W_600,
                color=AppColors.PRIMARY,
            ),
        )

    rows: list[ft.Control] = [
        _row(
            ft.Icons.CHAT_BUBBLE_OUTLINE_ROUNDED,
            "Assistant credits",
            f"of {200 if is_premium else DAILY_FREE_CREDITS} free daily, resets 00:00 UTC",
            balance_text,
        ),
        ft.Divider(
            height=1,
            thickness=1,
            color=ft.Colors.with_opacity(0.18, ft.Colors.OUTLINE),
        ),
        _cost_row("Chat reply, search, or page fetch", str(COST_STEP)),
        ft.Divider(
            height=1,
            thickness=1,
            color=ft.Colors.with_opacity(0.18, ft.Colors.OUTLINE),
        ),
        _cost_row("Search overview and page summary", "free"),
        ft.Divider(
            height=1,
            thickness=1,
            color=ft.Colors.with_opacity(0.18, ft.Colors.OUTLINE),
        ),
        _row(
            ft.Icons.PLAY_CIRCLE_ROUNDED,
            topup_label,
            "A short ad adds credits. Unused ad credits carry over",
            ft.Icon(
                ft.Icons.PLAY_CIRCLE_ROUNDED,
                size=tokens.ICON_SM,
                color=AppColors.ACCENT,
            ),
        ),
    ]

    if is_mobile and not is_premium:
        actions: list[ft.Control] = [cooldown_label, watch_btn]
    elif not is_premium:
        # Desktop: no ad to watch, so offer the thing that actually works.
        actions = [
            ft.TextButton(
                "Go Premium, remove ads and get 200 a day",
                icon=ft.Icons.WORKSPACE_PREMIUM_ROUNDED,
                icon_color=AppColors.PRIMARY,
                on_click=lambda e: _open_premium(),
            )
        ]
    else:
        actions = []

    content = ft.Column(
        [
            *rows,
            *actions,
        ],
        spacing=tokens.SPACE_XS,
        tight=True,
        horizontal_alignment=ft.CrossAxisAlignment.CENTER,
    )

    dlg = ft.AlertDialog(
        title=ft.Text("Assistant credits", font_family="Outfit"),
        content=ft.Container(
            content=content, width=340, padding=ft.Padding(4, 8, 4, 4)
        ),
        actions=[ft.TextButton("Close", on_click=_close)],
    )
    page.show_dialog(dlg)
    # The cooldown loop only has anything to update when the ad button is
    # actually on screen.
    if not is_premium and is_mobile:
        page.run_task(_countdown)


def _credits():
    from core.state import state as _st

    return _st.credit_service


@ft.component
def CreditPill() -> ft.Container:
    """Header credit pill as a component so it re-renders on every change."""
    app_state = ft.use_context(AppStateCtx)
    return build_credit_pill(ft.context.page, app_state.credits_remaining)
