"""Reusable widget factories."""

import logging

import flet as ft

from core import tokens

logger = logging.getLogger(__name__)


def build_banner_ad(page: ft.Page, unit_id: str | None = None) -> ft.Control:
    """Build a glass-container-wrapped banner ad (mobile only)."""
    if page.platform not in (ft.PagePlatform.ANDROID, ft.PagePlatform.IOS):
        return ft.Container(width=0, height=0)

    try:
        import flet_ads as fta

        from services.ad_service import AdService

        if not unit_id:
            ad_service = AdService(page)
            unit_id = ad_service.banner_id

        ad = fta.BannerAd(
            unit_id=unit_id,
            width=320,
            height=50,
            on_error=lambda e: None,
        )
    except (
        ValueError,
        TypeError,
        OSError,
        RuntimeError,
        ConnectionError,
        ImportError,
    ) as e:
        logger.warning("Failed to load BannerAd: %s", e)
        return ft.Container(width=0, height=0)

    return ft.Container(
        content=ft.Column(
            [
                ft.Text(
                    "SPONSORED",
                    size=8,
                    weight=ft.FontWeight.W_700,
                    color=ft.Colors.ON_SURFACE_VARIANT,
                    style=ft.TextStyle(letter_spacing=1),
                ),
                ad,
            ],
            horizontal_alignment=ft.CrossAxisAlignment.CENTER,
            spacing=tokens.SPACE_XS,
        ),
        alignment=ft.Alignment.CENTER,
        padding=tokens.SPACE_SM,
        border_radius=tokens.RADIUS_LG,
        bgcolor=ft.Colors.with_opacity(0.05, ft.Colors.ON_SURFACE),
        border=ft.Border.all(1, ft.Colors.with_opacity(0.1, ft.Colors.ON_SURFACE)),
        margin=ft.Margin(
            tokens.SPACE_LG, tokens.SPACE_XS, tokens.SPACE_LG, tokens.SPACE_XS
        ),
    )
