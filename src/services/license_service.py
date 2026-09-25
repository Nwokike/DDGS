"""Kiri License client — external checkout for everything Play cannot bill.

Google Play only sells to Play-installed builds (or linked license testers),
so a GitHub-downloaded APK, the Windows build and the Linux build can never
complete a purchase through Play Billing. This client covers exactly those
surfaces, using the same Worker that backs every Kiri app:

    GET  /catalog   -> public products, prices, currency
    POST /checkout  -> Flutterwave hosted page + a recovery ID
    POST /restore   -> entitlement status and a signed offline token
    POST /status    -> status refresh without issuing a token

The Worker is authoritative; the token it returns is a signed cache that
keeps premium working offline (see :mod:`services.license_token`). Nothing
here unlocks premium by itself — a verified token or a live server response
must say so first.

Matches ktv-player/src/services/kiri_license.py wherever the two overlap:
same refusal rules, same storage timing, same "never honour a token you
cannot verify". Only the transport and storage differ, because DDGS carries
its own StorageService and httpx instead of db_manager.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from dataclasses import dataclass

import httpx

from core.constants import (
    KIRI_LICENSE_APP_ID,
    KIRI_LICENSE_BASE_URL,
    KIRI_LICENSE_PUBLIC_KEY,
    KIRI_LICENSE_TIMEOUT,
)
from services.license_token import LicenseClaims, TokenRejected, verify_token

logger = logging.getLogger(__name__)

# Shared with the other Kiri apps so the recovery story reads the same.
SETTING_RECOVERY_ID = "kiri_recovery_id"
SETTING_TOKEN = "kiri_token"
SETTING_PRODUCT = "kiri_product"


class LicenseUnavailable(Exception):
    """The license service could not be reached or refused the request."""


def status_refusal(code: int) -> bool:
    """HTTP codes meaning "this entitlement is not valid" — not transport.

    400 malformed request, 402 payment not valid, 403 app not entitled,
    404 license not found. 429 is deliberately excluded: a throttled
    check must never revoke a real license.
    """
    return code in (400, 402, 403, 404)


@dataclass(frozen=True)
class LicenseProduct:
    id: str
    amount: float
    currency: str
    kind: str
    description: str

    @property
    def price_label(self) -> str:
        symbol = {"USD": "$", "EUR": "€", "NGN": "₦"}.get(self.currency.upper(), "")
        amount = f"{self.amount:,.2f}".rstrip("0").rstrip(".")
        return f"{symbol}{amount} {self.currency.upper()}".strip()


@dataclass(frozen=True)
class Checkout:
    recovery_id: str
    checkout_url: str
    product: str
    amount: float
    currency: str


@dataclass(frozen=True)
class LicenseStatus:
    status: str
    product: str
    recovery_id: str
    token: str | None = None
    claims: LicenseClaims | None = None

    @property
    def unlocks(self) -> bool:
        return self.status in ("active", "grace")


def _client() -> httpx.AsyncClient:
    return httpx.AsyncClient(http2=False, timeout=KIRI_LICENSE_TIMEOUT)


class KiriLicenseService:
    """Talks to the Kiri License Worker and caches the signed entitlement."""

    def __init__(
        self,
        app_id: str = KIRI_LICENSE_APP_ID,
        public_key: str = KIRI_LICENSE_PUBLIC_KEY,
        storage=None,
        on_change: Callable[[], None] | None = None,
    ):
        self.app_id = app_id
        # Injected rather than read from the constant at every call so a key
        # rotation (and the test fixtures, which are signed with their own
        # throwaway pair) is a constructor argument, not a monkeypatch.
        self.public_key = public_key
        # DDGS carries its own StorageService rather than a global db_manager.
        self.storage = storage
        # Owns its entitlement only: it reports the verdict and lets
        # PremiumService mirror it into the app-wide flag.
        self.on_change = on_change
        self.products: list[LicenseProduct] = []
        self.claims: LicenseClaims | None = None
        self._unlocked = False

    # -- local state ---------------------------------------------------------

    @property
    def unlocked(self) -> bool:
        return self._unlocked

    async def recovery_id(self) -> str:
        return str(await self._get(SETTING_RECOVERY_ID)) or ""

    async def cached_product(self) -> str:
        return str(await self._get(SETTING_PRODUCT)) or ""

    async def _get(self, key: str):
        if self.storage is None:
            return None
        try:
            return await self.storage.get(key)
        except Exception:
            logger.debug("licence setting read failed", exc_info=True)
            return None

    async def _store(
        self,
        *,
        recovery_id: str | None = None,
        token: str | None = None,
        product: str | None = None,
    ) -> None:
        if self.storage is None:
            return
        try:
            if recovery_id is not None:
                await self.storage.set(SETTING_RECOVERY_ID, recovery_id)
            if token is not None:
                await self.storage.set(SETTING_TOKEN, token)
            if product is not None:
                await self.storage.set(SETTING_PRODUCT, product)
        except Exception:
            logger.warning("Could not store the licence", exc_info=True)

    async def _apply(self, status: str, claims: LicenseClaims | None) -> None:
        """Record a verified entitlement and let the app re-evaluate.

        Deliberately does NOT set `state.is_premium` itself: the caller
        re-derives it from a single source of truth, so an entitlement can
        only be granted or dropped in one place.
        """
        self._unlocked = status in ("active", "grace") and claims is not None
        logger.info(
            "Kiri license status=%s product=%s unlocked=%s",
            status,
            claims.product if claims else "-",
            self._unlocked,
        )
        if self.on_change is not None:
            self.on_change()

    # -- offline -------------------------------------------------------------

    async def apply_cached_token(self) -> bool:
        """Verify the stored token so premium survives being offline.

        Returns whether the app is unlocked. A rejected token is cleared
        rather than left to fail on every launch — a token we cannot verify
        is a token we do not honour.
        """
        token = await self._get(SETTING_TOKEN)
        if not token:
            self._unlocked = False
            # Nothing left to verify, so stale claims must not survive to
            # be reused by a later status reply.
            self.claims = None
            self._notify_change()
            return False
        try:
            claims = verify_token(token, self.public_key, self.app_id)
        except TokenRejected as ex:
            logger.info("Cached Kiri license rejected (%s)", ex.reason)
            self._unlocked = False
            self.claims = None
            self._notify_change()
            return False
        self.claims = claims
        await self._apply(claims.status, claims)
        return self._unlocked

    # -- server --------------------------------------------------------------

    async def fetch_catalog(self, force: bool = False) -> list[LicenseProduct]:
        if self.products and not force:
            return self.products
        try:
            async with _client() as client:
                response = await client.get(f"{KIRI_LICENSE_BASE_URL}/catalog")
                response.raise_for_status()
                payload = response.json()
        except Exception as ex:
            raise LicenseUnavailable(
                f"Could not reach the license service: {ex}"
            ) from ex
        self.products = [
            LicenseProduct(
                id=str(item.get("id", "")),
                amount=float(item.get("amount") or 0),
                currency=str(item.get("currency") or "USD"),
                kind=str(item.get("kind") or "one_time"),
                description=str(item.get("description") or ""),
            )
            for item in payload.get("products", [])
            if item.get("id")
        ]
        return self.products

    async def checkout(
        self, product_id: str, email: str, *, name: str = "", phone: str = ""
    ) -> Checkout:
        """Start a hosted payment and return where to send the user."""
        body: dict = {
            "app_id": self.app_id,
            "product_id": product_id,
            "email": email,
        }
        if name:
            body["name"] = name[:120]
        if phone:
            body["phone_number"] = phone[:40]
        try:
            async with _client() as client:
                response = await client.post(
                    f"{KIRI_LICENSE_BASE_URL}/checkout", json=body
                )
        except Exception as ex:
            raise LicenseUnavailable(
                f"Could not reach the license service: {ex}"
            ) from ex
        if response.status_code >= 400:
            raise LicenseUnavailable(self._error_message(response, "Checkout failed"))
        try:
            payload = response.json()
        except Exception as ex:
            raise LicenseUnavailable(
                "The license service returned invalid JSON"
            ) from ex
        if not isinstance(payload, dict):
            raise LicenseUnavailable("The license service returned an invalid response")
        checkout = Checkout(
            recovery_id=str(payload.get("recovery_id") or ""),
            checkout_url=str(payload.get("checkout_url") or ""),
            product=str(payload.get("product") or product_id),
            amount=float(payload.get("amount") or 0),
            currency=str(payload.get("currency") or "USD"),
        )
        if not checkout.checkout_url or not checkout.recovery_id:
            raise LicenseUnavailable("The license service returned an incomplete order")
        # Persist the recovery ID immediately: it is the only way back in
        # after the user clears app data.
        await self._store(recovery_id=checkout.recovery_id, product=checkout.product)
        return checkout

    async def restore(self, recovery_id: str) -> LicenseStatus:
        """Redeem a recovery ID and cache the signed entitlement."""
        return await self._query("/restore", recovery_id, issue_token=True)

    async def refresh(self) -> LicenseStatus | None:
        """Re-check the stored entitlement (no token issued)."""
        recovery_id = await self.recovery_id()
        if not recovery_id:
            return None
        return await self._query("/status", recovery_id, issue_token=False)

    def _notify_change(self) -> None:
        """Report a verdict change so the app-wide flag cannot go stale."""
        if self.on_change is not None:
            self.on_change()

    async def _query(
        self, path: str, recovery_id: str, *, issue_token: bool
    ) -> LicenseStatus:
        recovery_id = (recovery_id or "").strip()
        if not recovery_id:
            raise LicenseUnavailable("Enter the recovery ID from your purchase email")
        try:
            async with _client() as client:
                response = await client.post(
                    f"{KIRI_LICENSE_BASE_URL}{path}",
                    json={"recovery_id": recovery_id, "app_id": self.app_id},
                )
        except Exception as ex:
            raise LicenseUnavailable(
                f"Could not reach the license service: {ex}"
            ) from ex
        if response.status_code >= 400:
            # The Worker answers entitlement questions here (402 payment not
            # valid, 403 app not entitled, 404 license not found). That is
            # the server refusing, not the network failing — so a standing
            # unlock is dropped rather than preserved by accident.
            if status_refusal(response.status_code):
                logger.info(
                    "License refused with HTTP %s — dropping unlock",
                    response.status_code,
                )
                self._unlocked = False
                self.claims = None
                self._notify_change()
            raise LicenseUnavailable(self._error_message(response, "Restore failed"))

        try:
            payload = response.json()
        except Exception as ex:
            raise LicenseUnavailable(
                "The license service returned invalid JSON"
            ) from ex
        if not isinstance(payload, dict):
            raise LicenseUnavailable("The license service returned an invalid response")
        status = str(payload.get("status") or "unknown")
        token = payload.get("token") if issue_token else None
        claims: LicenseClaims | None = None
        if token:
            try:
                claims = verify_token(token, self.public_key, self.app_id)
            except TokenRejected as ex:
                logger.warning("Kiri license token rejected: %s", ex.reason)
                self._unlocked = False
                self.claims = None
                self._notify_change()
                raise LicenseUnavailable(
                    "The license service returned a token this app could not verify"
                ) from ex
            if status in ("active", "grace"):
                await self._store(
                    recovery_id=str(payload.get("recovery_id") or recovery_id),
                    token=token,
                    product=str(payload.get("product") or ""),
                )
            else:
                # A valid token for a revoked/expired license must not be
                # cached: next launch would verify it and re-unlock.
                logger.info("Not caching token for status=%s", status)
                await self._store(
                    recovery_id=str(payload.get("recovery_id") or recovery_id),
                    token="",
                    product=str(payload.get("product") or ""),
                )
        else:
            await self._store(
                recovery_id=str(payload.get("recovery_id") or recovery_id),
                product=str(payload.get("product") or ""),
            )
        # A fresh verified token replaces the cache; a status-only reply
        # (which carries no token by design) reuses the one we already
        # verified — the assignment must come after that read, or every
        # refresh wipes the cache with None and unlocks nothing.
        if claims is not None:
            self.claims = claims
        effective = claims if claims is not None else self.claims
        if status not in ("active", "grace"):
            # Revoked/expired: the claims must not outlive the verdict, or
            # the next status-only reply could re-unlock from them.
            self.claims = None
            effective = None
        await self._apply(status, effective)
        return LicenseStatus(
            status=status,
            product=str(payload.get("product") or ""),
            recovery_id=str(payload.get("recovery_id") or recovery_id),
            token=token,
            claims=claims,
        )

    @staticmethod
    def _error_message(response, fallback: str) -> str:
        try:
            body = response.json()
            if isinstance(body, dict) and body.get("message"):
                return str(body["message"])
            if isinstance(body, dict) and body.get("error"):
                return str(body["error"])
        except Exception:
            pass
        return f"{fallback} (HTTP {response.status_code})"
