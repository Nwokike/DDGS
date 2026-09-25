"""Premium: resolves whether this user is entitled, and from which channel.

Two channels exist and they are independent:

  - **Kiri License** (license.kiri.ng) — Flutterwave checkout plus a signed
    entitlement token. Works on the direct APK, Windows and Linux with no
    Google permission at all.
  - **Google Play Billing** — present in the source and dormant until the
    store actually reports products for this package.

The Play AAB ships free-only: `core.build_channel.CHANNEL == "play"` gates
every licence method, so no Worker request is made, no purchase UI is
rendered, and a token left over from a direct install can never unlock it.

Mirrors ktv-player/src/services/premium_service.py: `load_local` verifies
the cached token offline, `reconcile` talks to the Worker after the first
frame and re-derives even on failure, and `_recompute_premium` is the single
place the derived flag is written. The extra Play helpers exist only
because DDGS ships two channels where KTV ships one.

Core rules:

- The entitlement is a **signed token** verified offline on every start —
  never a bare local flag. A token the app cannot verify drops Premium; a
  network that cannot be reached does not.
- The recovery ID is stored immediately: it is the only way back in after
  the user clears app data.
"""

from __future__ import annotations

import logging

from core.build_channel import CHANNEL
from core.state import state
from services import license_service
from services.license_service import KiriLicenseService, LicenseUnavailable

logger = logging.getLogger(__name__)

__all__ = [
    "LicenseUnavailable",
    "PremiumService",
    "apply_entitlement",
]


def apply_entitlement() -> bool:
    """Resolve the derived flag from whichever channel is entitled."""
    resolved = bool(getattr(state, "play_premium_active", False)) or bool(
        getattr(state, "license_premium_active", False)
    )
    if getattr(state, "is_premium", False) != resolved:
        state.is_premium = resolved
    return resolved


class PremiumService:
    """Owns the licence verdict and derives `state.is_premium` from it."""

    def __init__(self, page=None, storage=None):
        self.page = page
        self.storage = storage
        self.backend: str = "none"  # "kiri" | "none"
        self.license = KiriLicenseService(
            storage=storage, on_change=self._recompute_premium
        )
        if CHANNEL == "play":
            # Free-only build: no purchase surface of any kind is wired up,
            # so nothing for Play policy to look at.
            logger.info("Play channel build — premium disabled, free tier with ads")
            return
        self.backend = "kiri"

    # -- verdict --------------------------------------------------------------

    @property
    def available(self) -> bool:
        """True when this build may offer a direct purchase at all."""
        return self.backend == "kiri"

    def _premium_disabled(self) -> bool:
        if CHANNEL == "play":
            logger.info("Purchase ignored: the Play build has no premium")
            return True
        return False

    def _recompute_premium(self) -> None:
        """Mirror the licence verdict into the app-wide flag.

        The Play channel contributes independently, so both are ORed: a
        refunded licence must not cancel a Play purchase, and a Play
        purchase must survive a licence lapse.
        """
        state.license_premium_active = bool(self.license.unlocked)
        if state.license_premium_active:
            state.license_status = "active"
            state.premium_source = (
                f"license:{self.license.claims.product if self.license.claims else ''}"
            ).rstrip(":")
        else:
            state.license_status = state.license_status or ""
        apply_entitlement()

    def set_play_entitlement(self, active: bool, *, product_id: str = "") -> None:
        """Record the Play Billing channel's answer."""
        state.play_premium_active = bool(active)
        if active and product_id:
            state.premium_source = f"play:{product_id}"
        elif not active and not state.license_premium_active:
            state.premium_source = ""
        apply_entitlement()

    # -- startup / reconcile --------------------------------------------------

    async def load_local(self) -> None:
        """Verify the cached token — safe on the boot path.

        Offline by design: a paid app keeps Premium with no network at all,
        and a token that no longer verifies (expired, tampered, revoked)
        drops it again. A rejected token is *dropped*, not treated as
        inconclusive: only a network failure is inconclusive.
        """
        if CHANNEL == "play":
            # Free-only build: a token left over from a direct install
            # must never unlock it.
            state.license_premium_active = False
            state.play_premium_active = False
            apply_entitlement()
            return
        try:
            await self.license.apply_cached_token()
        except Exception:
            logger.warning("Could not verify the cached licence", exc_info=True)
        self._recompute_premium()

    async def reconcile(self) -> None:
        """Refresh the entitlement with the Worker.

        A network round-trip, so this runs *after* the first frame, never
        on the boot path. It runs even while unlocked: the Worker is
        authoritative when reachable, so a refunded or revoked licence must
        land. Only a network failure keeps the local verdict.
        """
        if CHANNEL == "play":
            return
        try:
            await self.license.refresh()
        except LicenseUnavailable as ex:
            logger.info("Kiri license refresh: %s", ex)
        except Exception:
            logger.debug("Kiri license refresh failed", exc_info=True)
        finally:
            # Re-derive even on failure: a refusal or a rejected token has
            # already cleared the licence, and the flag must follow it.
            self._recompute_premium()

    # -- Kiri License surface -------------------------------------------------

    async def kiri_catalog(self) -> list[license_service.LicenseProduct]:
        """Products offered by the licence Worker, or [] when offline."""
        if self._premium_disabled():
            return []
        try:
            return await self.license.fetch_catalog()
        except LicenseUnavailable as ex:
            logger.info("License catalog unavailable: %s", ex)
            return []
        except Exception:
            logger.debug("License catalog failed", exc_info=True)
            return []

    async def kiri_checkout(
        self, product_id: str, email: str, *, name: str = "", phone: str = ""
    ) -> license_service.Checkout:
        """Create a hosted payment and save the recovery ID."""
        if self._premium_disabled():
            raise LicenseUnavailable("Premium is not available in this build")
        checkout = await self.license.checkout(
            product_id, email, name=name, phone=phone
        )
        return checkout

    async def kiri_restore(self, recovery_id: str) -> license_service.LicenseStatus:
        """Redeem a recovery ID; raises LicenseUnavailable with a reason."""
        if self._premium_disabled():
            raise LicenseUnavailable("Premium is not available in this build")
        status = await self.license.restore(recovery_id)
        self._recompute_premium()
        await self._persist_verdict()
        return status

    async def kiri_check_status(self):
        """Re-check the saved entitlement, keeping the local token offline."""
        if self._premium_disabled():
            return None
        try:
            status = await self.license.refresh()
        except LicenseUnavailable as ex:
            # A refusal (402/403/404) already dropped the unlock inside the
            # client, so the verdict must be re-derived — not swallowed.
            logger.info("Licence status refused: %s", ex)
            self._recompute_premium()
            await self._persist_verdict()
            raise
        self._recompute_premium()
        await self._persist_verdict()
        return status

    # -- persistence ----------------------------------------------------------

    async def _persist_verdict(self) -> None:
        """Write the derived flag back to disk for the next launch."""
        if self.storage is None:
            return
        try:
            await self.storage.set("is_premium", bool(state.is_premium))
        except Exception:
            logger.debug("Could not persist the premium flag", exc_info=True)
