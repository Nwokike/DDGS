"""AdMob service — banner and interstitial ads.

Direct port of Sherlock's production AdService pattern.
Uses test Ad IDs until Play Store launch.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Callable

import flet as ft

from core.state import state

logger = logging.getLogger(__name__)

try:
    import flet_ads as fta

    _HAS_ADS = True
except ImportError:
    _HAS_ADS = False


class AdService:
    """Manages AdMob banner and interstitial ads."""

    USE_TEST_IDS = False  # Production AdMob IDs active

    BANNER_ID_ANDROID_TEST = "ca-app-pub-3940256099942544/9214589741"
    INTERSTITIAL_ID_ANDROID_TEST = "ca-app-pub-3940256099942544/1033173712"

    BANNER_ID_ANDROID_PROD = "ca-app-pub-5679949845754640/9885079510"
    INTERSTITIAL_ID_ANDROID_PROD = "ca-app-pub-5679949845754640/5339329844"

    def __init__(self, page: ft.Page):
        self.page = page
        self.interstitial = None
        self._interstitial_loaded = False
        self._interstitial_shown = False
        self._pending_interstitial = False
        self._active_rewarded_ad = None
        self._on_close: Callable | None = None
        self._can_request_ads: bool = True
        self._consent_manager = None

    @property
    def banner_id(self) -> str:
        if self.USE_TEST_IDS:
            return self.BANNER_ID_ANDROID_TEST
        return self.BANNER_ID_ANDROID_PROD

    @property
    def interstitial_id(self) -> str:
        if self.USE_TEST_IDS:
            return self.INTERSTITIAL_ID_ANDROID_TEST
        return self.INTERSTITIAL_ID_ANDROID_PROD

    def _is_mobile(self) -> bool:
        try:
            return not self.page.web and self.page.platform.is_mobile()
        except (
            ValueError,
            TypeError,
            OSError,
            RuntimeError,
            ConnectionError,
            ImportError,
        ):
            return False

    # ── Consent Management (UMP) ──────────────────────────────────────────────

    async def gather_consent(self):
        """Run UMP consent flow. Only shows UI in regulated regions (EEA/UK)."""
        if state.is_premium or not _HAS_ADS or not self._is_mobile():
            self._can_request_ads = True
            return
        try:
            # flet-ads 1.0 auto-registers services on construction.
            self._consent_manager = fta.ConsentManager()
            await self._consent_manager.request_consent_info_update()
            await self._consent_manager.load_and_show_consent_form_if_required()
            self._can_request_ads = await self._consent_manager.can_request_ads()
        except Exception as e:
            logger.warning("UMP consent flow failed, defaulting to allow ads: %s", e)
            self._can_request_ads = True

    async def show_privacy_options(self):
        """Show privacy options form if required by regulation (GDPR)."""
        if not self._consent_manager:
            return
        try:
            status = (
                await self._consent_manager.get_privacy_options_requirement_status()
            )
            if status == fta.PrivacyOptionsRequirementStatus.REQUIRED:
                await self._consent_manager.show_privacy_options_form()
                self._can_request_ads = await self._consent_manager.can_request_ads()
        except Exception:
            pass

    # ── Ad Controls ───────────────────────────────────────────────────────────

    def get_banner_ad(self) -> ft.Control:
        """Return a banner ad control, or empty container on desktop."""
        if state.is_premium or not _HAS_ADS or not self._is_mobile() or not self._can_request_ads:
            return ft.Container(width=0, height=0)
        try:
            ad = fta.BannerAd(
                unit_id=self.banner_id,
                width=320,
                height=50,
                on_error=lambda e: None,
            )
            return ft.Container(
                content=ad,
                width=320,
                height=50,
                alignment=ft.Alignment.CENTER,
            )
        except (
            ValueError,
            TypeError,
            OSError,
            RuntimeError,
            ConnectionError,
            ImportError,
        ):
            return ft.Container(width=0, height=0)

    async def preload_interstitial(self, on_close: Callable | None = None):
        """Create and load a fresh interstitial (single-use in flet-ads 1.0)."""
        self._on_close = on_close
        if state.is_premium or not _HAS_ADS or not self._is_mobile() or not self._can_request_ads:
            return
        try:
            self._interstitial_loaded = False
            self._interstitial_shown = False
            self.interstitial = fta.InterstitialAd(
                unit_id=self.interstitial_id,
                on_load=self._handle_loaded,
                on_error=self._handle_error,
                on_close=self._handle_close,
            )
        except (
            ValueError,
            TypeError,
            OSError,
            RuntimeError,
            ConnectionError,
            ImportError,
        ):
            self.interstitial = None

    def _handle_loaded(self, e):
        self._interstitial_loaded = True
        if self._pending_interstitial:
            self._pending_interstitial = False
            self.page.run_task(self._show_loaded)

    def _handle_error(self, e):
        logger.error("InterstitialAd error: %s", getattr(e, "data", e))
        self.interstitial = None
        self._interstitial_loaded = False

    async def _show_loaded(self):
        if self.interstitial is None or self._interstitial_shown:
            return
        try:
            await self.interstitial.show()
            self._interstitial_shown = True
        except (
            ValueError,
            TypeError,
            OSError,
            RuntimeError,
            ConnectionError,
            ImportError,
        ) as exc:
            logger.warning("Interstitial show-on-load failed: %s", exc)
            self.interstitial = None
            self._interstitial_loaded = False

    async def _handle_close(self, e):
        self._interstitial_shown = False
        if self._on_close:
            if asyncio.iscoroutinefunction(self._on_close):
                await self._on_close()
            else:
                self._on_close()
        await self.preload_interstitial(on_close=self._on_close)

    async def show_interstitial(self) -> bool:
        """Show the preloaded interstitial; load a fresh one if none is ready.

        InterstitialAd is single-use in flet-ads 1.0, so shown or failed
        instances are replaced. Returns True when an ad is shown or queued to
        show as soon as it finishes loading.
        """
        if state.is_premium or not _HAS_ADS or not self._is_mobile() or not self._can_request_ads:
            return False
        ad = self.interstitial
        if (
            ad is not None
            and self._interstitial_loaded
            and not self._interstitial_shown
        ):
            try:
                await ad.show()
                self._interstitial_shown = True
                return True
            except (
                ValueError,
                TypeError,
                OSError,
                RuntimeError,
                ConnectionError,
                ImportError,
            ):
                self.interstitial = None
                self._interstitial_loaded = False
        # No usable ad: load a fresh one; it shows automatically once loaded.
        self._pending_interstitial = True
        if self.interstitial is None:
            await self.preload_interstitial(self._on_close)
        return True

    async def show_rewarded_interstitial(self, on_close: Callable) -> bool:
        """Show a rewarded interstitial ad, triggering on_close when closed."""
        if state.is_premium or not _HAS_ADS or not self._is_mobile():
            if asyncio.iscoroutinefunction(on_close):
                await on_close()
            else:
                on_close()
            return True

        try:

            async def _show(e):
                await e.control.show()

            async def _close(e):
                self._active_rewarded_ad = None
                if asyncio.iscoroutinefunction(on_close):
                    await on_close()
                else:
                    on_close()

            self._active_rewarded_ad = fta.InterstitialAd(
                unit_id=self.interstitial_id,
                on_load=lambda e: self.page.run_task(_show, e),
                on_close=lambda e: self.page.run_task(_close, e),
                on_error=lambda e: logger.error(
                    "Rewarded Interstitial error: %s", e.data
                ),
            )
            return True
        except (
            ValueError,
            TypeError,
            OSError,
            RuntimeError,
            ConnectionError,
            ImportError,
        ) as err:
            logger.error("Failed to trigger rewarded interstitial: %s", err)
            if asyncio.iscoroutinefunction(on_close):
                await on_close()
            else:
                on_close()
            return False
