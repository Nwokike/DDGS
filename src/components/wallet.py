"""AI credit pill + wallet dialog — SpanInsight's pattern, DDGS copy."""

from __future__ import annotations

import asyncio
import time

import flet as ft

from core import tokens
from core.constants import (
    AD_TOPUP_COOLDOWN_SEC,
    AD_TOPUP_CREDITS,
    COST_CHAT,
    COST_SUMMARIZE,
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


def build_credit_pill(page: ft.Page) -> ft.Container:
    """Compact color-coded credit chip for the home header."""
    color = _credit_color(state.credits_remaining)
    return ft.Container(
        content=ft.Row(
            [
                ft.Icon(
                    ft.Icons.AUTO_AWESOME_ROUNDED, size=tokens.ICON_SM, color=color
                ),
                ft.Text(
                    str(state.credits_remaining),
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
        tooltip="AI credits — tap for details",
        on_click=lambda e: show_wallet_dialog(page),
    )


def show_wallet_dialog(page: ft.Page) -> None:
    """Balance, cost table, ad top-up (30s cooldown) and the free-manual note."""
    if not hasattr(state, "ad_cooldown_end"):
        state.ad_cooldown_end = 0.0

    is_mobile = page.platform in (ft.PagePlatform.ANDROID, ft.PagePlatform.IOS)
    is_premium = state.is_premium

    hero_number = ft.Text(
        str(state.credits_remaining),
        size=40,
        weight=ft.FontWeight.BOLD,
        color=_credit_color(state.credits_remaining),
    )
    cap_note = ft.Text(
        f"of {200 if is_premium else DAILY_FREE_CREDITS} free daily · resets 00:00 UTC",
        size=tokens.FONT_XS,
        color=ft.Colors.ON_SURFACE_VARIANT,
        text_align=ft.TextAlign.CENTER,
    )
    cooldown_label = ft.Text("", size=tokens.FONT_XS, text_align=ft.TextAlign.CENTER)

    topup_label = (
        f"Watch Ad (+{AD_TOPUP_CREDITS} Credits)"
        if is_mobile
        else f"Simulate Ad (+{AD_TOPUP_CREDITS} Credits)"
    )
    watch_btn = ft.FilledButton(
        topup_label if not is_premium else "Premium active — 200/day",
        icon=ft.Icons.PLAY_CIRCLE_ROUNDED,
        disabled=is_premium,
    )

    dialog_open = True

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
                watch_btn.content = ft.Text(
                    f"Cooldown ({remaining}s)", size=tokens.FONT_SM
                )
            else:
                watch_btn.disabled = False
                watch_btn.content = ft.Text(topup_label, size=tokens.FONT_SM)
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
        hero_number.value = str(new_balance)
        hero_number.color = _credit_color(new_balance)
        cooldown_label.value = f"+{AD_TOPUP_CREDITS} credits added!"
        try:
            hero_number.update()
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

        ok = await AdService(page).show_rewarded_interstitial(_on_watch_success)
        if not ok:
            state.ad_cooldown_end = 0.0

    watch_btn.on_click = lambda e: page.run_task(_on_watch, e)

    def _cost_line(label: str, cost: str) -> ft.Row:
        return ft.Row(
            [
                ft.Text(label, size=tokens.FONT_XS, font_family="Outfit"),
                ft.Text(
                    cost,
                    size=tokens.FONT_XS,
                    color=AppColors.PRIMARY,
                    weight=ft.FontWeight.W_600,
                ),
            ],
            alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
        )

    content = ft.Column(
        [
            ft.Row(
                [
                    ft.Icon(
                        ft.Icons.AUTO_AWESOME_ROUNDED,
                        size=28,
                        color=AppColors.ACCENT,
                    ),
                    ft.Text(
                        "AI Credits",
                        size=tokens.FONT_MD,
                        weight=ft.FontWeight.BOLD,
                        font_family="Outfit",
                    ),
                ],
                alignment=ft.MainAxisAlignment.CENTER,
                spacing=8,
            ),
            ft.Row(
                [hero_number, cap_note],
                alignment=ft.MainAxisAlignment.CENTER,
            ),
            ft.Container(height=6),
            _cost_line("Chat message (any tools it runs)", str(COST_CHAT)),
            _cost_line("Search overview / page summary", str(COST_SUMMARIZE)),
            ft.Container(height=4),
            ft.Text(
                "Manual search, scraping and downloads never use credits.",
                size=tokens.FONT_XS,
                color=ft.Colors.ON_SURFACE_VARIANT,
                text_align=ft.TextAlign.CENTER,
            ),
            ft.Divider(height=12, thickness=1),
            cooldown_label,
            watch_btn,
        ],
        spacing=6,
        tight=True,
        horizontal_alignment=ft.CrossAxisAlignment.CENTER,
    )

    dlg = ft.AlertDialog(
        title=ft.Text("AI Credits", font_family="Outfit"),
        content=ft.Container(
            content=content, width=320, padding=ft.Padding(4, 8, 4, 4)
        ),
        actions=[ft.TextButton("Close", on_click=_close)],
    )
    page.show_dialog(dlg)
    if not is_premium:
        page.run_task(_countdown)


def _credits():
    from core.state import state as _st

    return _st.credit_service
