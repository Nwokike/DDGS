"""Reusable widget factories."""

import logging

import flet as ft

from core import tokens

logger = logging.getLogger(__name__)


def build_banner_ad(page: ft.Page, unit_id: str | None = None) -> ft.Control:
    """Full-width glass banner: Sherlock's exact sizing, no label.

    Revenue-critical sizing: the glass stretches edge-to-edge on every
    screen. Home/History/Results wrap banners in shrink-wrap Columns that
    would pin a bare container at 320px and left-align it, so an outer Row
    (rows fill what their parent offers) hosts an expand=True glass that
    equalizes every parent; the native ad stays 320x50, centered inside
    the stretched glass.

    Never set alignment on a wide Container: it can expand to fill the
    parent's offer, which caused the full-page regression in Sherlock.
    No SPONSORED label by design: Sherlock removed it on purpose.
    """
    from core.state import state

    if state.is_premium or page.platform not in (
        ft.PagePlatform.ANDROID,
        ft.PagePlatform.IOS,
    ):
        return ft.Container(width=0, height=0)

    try:
        import flet_ads as fta

        from services.ad_service import AdService

        if not unit_id:
            ad_service = getattr(state, "ad_service", None) or AdService(page)
            unit_id = ad_service.banner_id

        def _on_ad_error(e):
            logger.warning("Banner ad error: %s", getattr(e, "data", e))

        ad = fta.BannerAd(
            unit_id=unit_id,
            width=320,
            height=50,
            on_error=_on_ad_error,
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

    from core.theme import adaptive_glass_bg, adaptive_glass_border

    glass = ft.Container(
        content=ft.Column(
            [ft.Container(content=ad, width=320, height=50)],
            horizontal_alignment=ft.CrossAxisAlignment.CENTER,
            spacing=tokens.SPACE_XS,
            tight=True,
        ),
        expand=True,
        padding=tokens.SPACE_SM,
        border_radius=tokens.RADIUS_LG,
        bgcolor=adaptive_glass_bg(page),
        border=ft.Border.all(1, adaptive_glass_border(page)),
    )
    return ft.Row(controls=[glass], alignment=ft.MainAxisAlignment.CENTER)
