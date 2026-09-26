"""Premium: resolves whether this user is entitled, and from which channel.

Two channels exist and they are independent:

  - **Kiri License** (license.kiri.ng) - Flutterwave checkout plus a signed
    entitlement token. Works on the direct APK, Windows and Linux with no
    Google permission at all.
  - **Google Play Billing** - present in the source and dormant until the
    store actually reports products for this package.

The Play AAB ships free-only: `core.build_channel.CHANNEL == "play"` gates
every licence method, so no Worker request is made, no purchase UI is
rendered, and a token left over from a direct install can never unlock it.

Ported from ktv-player/src/services/premium_service.py: `load_local`
verifies the cached token offline, `reconcile` uses the token-issuing
`/restore` path, `reconcile_if_due` debounces foreground bursts, an hourly
loop keeps renewals/revokes current, the checkout watcher finishes a hosted
payment automatically, and `_recompute_premium` is the single place the
derived flag is written. The extra Play helpers exist only because DDGS
ships a Play channel build flag where KTV keeps the same gate without a
second entitlement source.

Core rules:

- The entitlement is a **signed token** verified offline on every start -
  never a bare local flag. A token the app cannot verify drops Premium; a
  network that cannot be reached does not.
- The recovery ID is stored immediately: it is the only way back in after
  the user clears app data.
"""

from __future__ import annotations

import asyncio
import logging
import time
from collections.abc import Callable

from core.build_channel import CHANNEL
from core.constants import PREMIUM_DAILY_CREDITS
from core.state import state
from services import license_service
from services.license_service import KiriLicenseService, LicenseUnavailable

logger = logging.getLogger(__name__)

__all__ = [
    "LicenseUnavailable",
    "PremiumService",
    "apply_entitlement",
    "page_has_ads",
    "unlock_message",
]


def page_has_ads(page) -> bool:
    """True where ads are actually requested (mirrors ad_service gates).

    Only native phones/tablets show ads: web and desktop never request
    any, so claiming "no ads" there would be a lie. Unknown page ->
    assume ads (most installs are phone APKs), like KTV Player.
    """
    try:
        return bool(page.platform.is_mobile()) and not getattr(page, "web", False)
    except Exception:
        return True


def unlock_message(page) -> str:
    """Platform-honest unlock toast (KTV's premium_unlocked_message)."""
    if page_has_ads(page):
        return "Premium unlocked. Ads removed."
    return f"Premium unlocked. {PREMIUM_DAILY_CREDITS} credits a day."

# Cadence, deliberately asymmetric (KTV Player):
# - checkout: seconds, because the user is holding the phone waiting for
#   the money to land. Flutterwave's hosted session is ~15 minutes.
# - steady state: hourly + on foreground resume + at launch. Entitlements
#   change at month boundaries, not second boundaries - a per-minute loop
#   would burn battery and drain the Worker's shared 20 req/60s budget for
#   nothing. The signed token's own `exp` enforces expiry offline anyway;
#   these checks exist to refresh renewals and catch revokes while running.
CHECKOUT_WATCH_INTERVAL = 5.0
CHECKOUT_WATCH_TIMEOUT = 15 * 60.0
RECONCILE_INTERVAL = 60 * 60.0
RESUME_DEBOUNCE = 60.0


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
        # KTV Player broadcasts every verdict change so an open Settings
        # screen repaints. Without this the card is a snapshot taken when
        # Settings was built: a restore shows a success snackbar above buy
        # buttons, and a lapse still reads "Premium active".
        self._listeners: list[Callable[[], None]] = []
        self.license = KiriLicenseService(
            storage=storage, on_change=self._recompute_premium
        )
        # Strong refs: asyncio only holds weak references to tasks, and a
        # bare create_task can be collected mid-flight (ad_service pattern).
        self._checkout_watch_task: asyncio.Task | None = None
        self._reconcile_task: asyncio.Task | None = None
        # Negative so the very first resume check is never debounced away.
        self._last_reconcile_at = time.monotonic() - RESUME_DEBOUNCE
        if CHANNEL == "play":
            # Free-only build: no purchase surface of any kind is wired up,
            # so nothing for Play policy to look at.
            logger.info("Play channel build - premium disabled, free tier with ads")
            return
        self.backend = "kiri"

    # -- verdict --------------------------------------------------------------

    @property
    def available(self) -> bool:
        """True when this build may offer a direct purchase at all."""
        return self.backend == "kiri"

    def add_listener(self, callback: Callable[[], None]) -> None:
        """Subscribe to verdict changes. Mirrors KTV's listener API."""
        if callback not in self._listeners:
            self._listeners.append(callback)

    def remove_listener(self, callback: Callable[[], None]) -> None:
        try:
            self._listeners.remove(callback)
        except ValueError:
            pass

    def _notify_listeners(self) -> None:
        # One broken subscriber must not stop the others, and must not
        # escape into the entitlement code that is calling us.
        for callback in list(self._listeners):
            try:
                callback()
            except Exception:
                logger.exception("premium listener failed")

    def _commit(self) -> None:
        """Re-derive, log the transition, and tell every subscriber."""
        previous = bool(state.is_premium)
        resolved = apply_entitlement()
        if resolved != previous:
            # The line that makes a wrong premium state diagnosable in the
            # field; KTV logs it and DDGS did not.
            logger.info("Premium state -> %s", resolved)
        self._notify_listeners()

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
        recorded = str(getattr(self.license, "status", "") or "")
        if state.license_premium_active:
            claims = self.license.claims
            # The signed token carries the real status. Hard-coding "active"
            # here is what made the grace copy in the Premium card dead
            # code: grace is an unlocked state, so it always fell through
            # to the active wording.
            state.license_status = (
                str(getattr(claims, "status", "") or recorded or "active")
            )
            state.premium_source = (
                f"license:{getattr(claims, 'product', '') or ''}"
            ).rstrip(":")
        else:
            # Keep the Worker's last word when it explains the lapse, and
            # drop everything else. The old `or ""` preserved the previous
            # value verbatim, which is how a revoked licence went on
            # rendering "Premium active".
            state.license_status = (
                recorded if recorded in ("expired", "revoked") else ""
            )
            if not state.play_premium_active:
                state.premium_source = ""
        self._commit()

    def set_play_entitlement(self, active: bool, *, product_id: str = "") -> None:
        """Record the Play Billing channel's answer."""
        state.play_premium_active = bool(active)
        if active and product_id:
            state.premium_source = f"play:{product_id}"
        elif not active and not state.license_premium_active:
            state.premium_source = ""
        self._commit()

    # -- startup / reconcile --------------------------------------------------

    async def load_local(self) -> None:
        """Verify the cached token - safe on the boot path.

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
            state.license_status = ""
            state.premium_source = ""
            self._commit()
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

        Uses the **token-issuing** path on purpose (KTV Player): `/status`
        never re-issues the signed token, so after a renewal the cached
        token's `exp` would lapse while the server still said `active` - a
        paying subscriber locked out until a manual Restore. `restore()`
        answers the same and re-arms the token in one round-trip (same rate
        bucket).
        """
        if CHANNEL == "play":
            return
        self._last_reconcile_at = time.monotonic()
        recovery_id = await self.license.recovery_id()
        if not recovery_id:
            # Nothing was ever purchased - nothing to reconcile.
            self._recompute_premium()
            return
        try:
            await self.license.restore(recovery_id)
        except LicenseUnavailable as ex:
            logger.info("Kiri license refresh: %s", ex)
        except Exception:
            logger.debug("Kiri license refresh failed", exc_info=True)
        finally:
            # Re-derive even on failure: a refusal or a rejected token has
            # already cleared the licence, and state.is_premium must follow.
            self._recompute_premium()

    async def reconcile_if_due(self) -> None:
        """Debounced reconcile for foreground-resume and the hourly loop.

        RESUME/SHOW arrives in bursts (app switcher flickers, permission
        dialogs); without the debounce a burst could burn the Worker's
        shared 20 req/60s per-IP budget in one second.
        """
        if self._premium_disabled():
            return
        if time.monotonic() - self._last_reconcile_at < RESUME_DEBOUNCE:
            return
        await self.reconcile()

    # -- background watchers -------------------------------------------------

    def start_reconcile_loop(self) -> None:
        """Hourly entitlement check while the app runs (after boot reconcile)."""
        if self._premium_disabled():
            return
        self.stop_reconcile_loop()
        if self.page is None:
            return
        self._reconcile_task = self.page.run_task(self._reconcile_loop)
        logger.info(
            "Hourly license reconcile started (interval %.0fs)", RECONCILE_INTERVAL
        )

    def stop_reconcile_loop(self) -> None:
        task = self._reconcile_task
        self._reconcile_task = None
        if task is not None and not task.done():
            task.cancel()

    async def _reconcile_loop(self) -> None:
        while True:
            await asyncio.sleep(RECONCILE_INTERVAL)
            await self.reconcile_if_due()

    def start_checkout_watch(self, recovery_id: str) -> None:
        """Finish a hosted payment automatically: poll restore every few
        seconds until the server confirms, the window ends, or the app closes.

        Lives on the service (not the Settings screen) so navigating away or
        rebuilding the tab cannot orphan it (KTV Player).
        """
        if self._premium_disabled() or not recovery_id:
            return
        self.stop_checkout_watch()
        if self.page is None:
            return
        self._checkout_watch_task = self.page.run_task(
            self._checkout_watch_loop, recovery_id
        )
        logger.info(
            "Checkout watcher started (interval %.0fs)", CHECKOUT_WATCH_INTERVAL
        )

    def stop_checkout_watch(self) -> None:
        task = self._checkout_watch_task
        self._checkout_watch_task = None
        if task is not None and not task.done():
            task.cancel()

    async def _checkout_watch_loop(self, recovery_id: str) -> None:
        deadline = time.monotonic() + CHECKOUT_WATCH_TIMEOUT
        while time.monotonic() < deadline:
            await asyncio.sleep(CHECKOUT_WATCH_INTERVAL)
            try:
                status = await self.license.restore(recovery_id)
            except LicenseUnavailable as ex:
                # Pending (202), not verified yet (404/402), throttled (429)
                # or offline - the money is still moving; keep waiting.
                logger.info("Checkout watcher waiting: %s", ex)
                continue
            if status.status in ("active", "grace") and self.license.unlocked:
                # restore() already stored the token and flipped the flag
                # (license on_change -> _recompute_premium); listeners have
                # rebuilt every screen - this is just the human confirmation.
                # `unlocked` (not just the status text) demands a verified
                # token, so a signing misconfiguration can never toast a lie.
                logger.info(
                    "Checkout watcher unlocked product=%s status=%s",
                    status.product,
                    status.status,
                )
                self._notify(unlock_message(self.page))
                return
        logger.info("Checkout watcher timed out - Restore purchases remains available")

    def shutdown(self) -> None:
        """Cancel every background task (app close)."""
        self.stop_checkout_watch()
        self.stop_reconcile_loop()

    def _notify(self, message: str) -> None:
        """Human confirmation on the open page (KTV's notify(), DDGS snack)."""
        page = self.page
        if page is None:
            return
        try:
            import flet as ft

            page.show_dialog(ft.SnackBar(ft.Text(message, font_family="Outfit")))
        except Exception:
            logger.debug("premium notify failed", exc_info=True)

    # -- Kiri License surface -------------------------------------------------

    async def kiri_catalog(
        self, force: bool = False
    ) -> list[license_service.LicenseProduct]:
        """Products offered by the licence Worker, or [] when offline."""
        if self._premium_disabled():
            return []
        try:
            return await self.license.fetch_catalog(force=force)
        except LicenseUnavailable as ex:
            logger.info("License catalog unavailable: %s", ex)
            return []
        except Exception:
            logger.debug("License catalog failed", exc_info=True)
            return []

    async def kiri_checkout(
        self, product_id: str, email: str
    ) -> license_service.Checkout:
        """Create a hosted payment, save the recovery ID, start auto-finish.

        Email only, exactly like KTV Player: the hosted page collects the
        rest, and a shorter form converts better.
        """
        if self._premium_disabled():
            raise LicenseUnavailable("Premium is not available in this build")
        checkout = await self.license.checkout(product_id, email)
        # KTV notifies here too: the open card must repaint as soon as an
        # order exists, or the recovery-ID row never appears.
        self._notify_listeners()
        # The browser takes over from here; this watcher is what makes the
        # app unlock itself when the user comes back from a paid checkout.
        self.start_checkout_watch(checkout.recovery_id)
        return checkout

    async def kiri_restore(self, recovery_id: str) -> license_service.LicenseStatus:
        """Redeem a recovery ID; raises LicenseUnavailable with a reason."""
        if self._premium_disabled():
            raise LicenseUnavailable("Premium is not available in this build")
        status = await self.license.restore(recovery_id)
        self._recompute_premium()
        return status

    async def kiri_check_status(self):
        """Re-check the saved entitlement, keeping the local token offline."""
        if self._premium_disabled():
            return None
        try:
            status = await self.license.refresh()
        except LicenseUnavailable as ex:
            # A refusal (402/403/404) already dropped the unlock inside the
            # client, so the verdict must be re-derived - not swallowed.
            logger.info("Licence status refused: %s", ex)
            self._recompute_premium()
            raise
        self._recompute_premium()
        return status
