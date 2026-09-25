"""Kiri License client: Flutterwave-backed Premium for direct builds.

The Worker at license.kiri.ng owns payment policy; this module only speaks
its documented client contract (kiri-license/docs/client-integration.md):

    GET  /catalog   product ids, prices, intervals (safe to cache)
    POST /checkout  start a hosted payment, returns recovery_id + url
    POST /restore   authoritative status + a signed token
    POST /status    same as restore, without a token

This is one implementation for every build. Whether the purchase UI may
be reached is decided by `core.build_channel.CHANNEL`, not by having a
second copy of this file: the Play AAB never offers a purchase row, so
nothing here is reachable there.

Availability, matching the other Kiri apps:

  - the Play build (CHANNEL == "play"): never. It is a free-only build.
  - desktop and web: always. There is no Play Store to bill through.
  - a direct Android APK: only after the user has explicitly opted in,
    because that is the build where Play payment would otherwise have been
    expected and can fail for reasons that are not the app's fault.

Two rules that are not negotiable:

  - a network failure NEVER removes Premium. Only an authoritative
    `revoked`/`expired` from the server downgrades, and a locally valid
    token keeps access until its own expiry.
  - the private signing key and the Flutterwave secret never appear here.
    Only the public verification key, which is safe to ship.
"""

from __future__ import annotations

import logging
import re
import time
from dataclasses import dataclass
from typing import Any

import httpx

from core import license_crypto

logger = logging.getLogger(__name__)

BASE_URL = "https://license.kiri.ng"
ISSUER = "license.kiri.ng"
APP_ID = "ng.kiri.ddgs"  # matches [tool.flet] org + product in pyproject

# Public verification key. Safe to ship: it can only confirm a signature,
# never produce one. Matches LICENSE_PUBLIC_KEY in the Worker's wrangler.toml.
PUBLIC_KEY = (
    "MFkwEwYHKoZIzj0CAQYIKoZIzj0DAQcDQgAE-YfZ-yKdG3wYF1IR0XcpJH4RclABnddMmAG"
    "XFI2J8sbC4gWY2POKc8hVrn0_uHxDZ9ufzwzg4buUimW-IEw4Uw"
)

TIMEOUT = 15.0
# The catalog is safe to cache per its own docs, and it is the only request
# made on the premium screen's first paint.
CATALOG_TTL = 60 * 60

# Product id -> the Play product it is the same tier as, so a user moving
# between channels sees one consistent set of names.
PLAY_EQUIVALENT = {
    "monthly": "premium_monthly",
    "yearly": "premium_yearly",
    "lifetime": "premium_lifetime",
}

_RECOVERY_RE = re.compile(r"^KIRI-([A-Z])-([A-Z0-9_-]{20,})$")
_EMAIL_RE = re.compile(r"^[^\s@]+@[^\s@]+\.[^\s@]+$")

_catalog_cache: dict[str, Any] = {"at": 0.0, "products": []}
# Android opt-in for the direct channel: a direct APK user is offered
# Flutterwave only after telling us Play payment does not work for them.
_DIRECT_OPTIN_KEY = "kiri_license_direct_optin"


class LicenseUnavailable(Exception):
    """This build must not offer the license channel (Play policy)."""


class LicenseError(Exception):
    """The Worker refused or could not be reached."""


def is_available(page=None) -> bool:
    """Whether this build and this user may be offered direct checkout.

    Mirrors the other Kiri apps so the rule is the same everywhere:

      - the Play AAB (CHANNEL == "play"): never. It is a free-only build,
        because selling in-app digital goods there needs a Google Payments
        merchant profile that no account available to us has yet.
      - desktop and web: always. There is no Play Store to bill through.
      - a direct Android APK: only after the user has explicitly opted in.
        That is the build where Play payment would otherwise have been
        expected, and it can fail for reasons that are not the app's
        fault, so the user is asked before we offer the alternative.
    """
    from core.build_channel import CHANNEL

    if CHANNEL == "play":
        return False
    if page is None:
        return True
    try:
        if not page.platform.is_mobile():
            return True
    except Exception:
        return True
    return bool(getattr(page, "_kiri_direct_optin", False))


def set_available(page, enabled: bool) -> None:
    """Record the Android opt-in so the UI can offer or withdraw the channel."""
    if page is not None:
        page._kiri_direct_optin = bool(enabled)


def clear_available(page=None) -> None:
    """Withdraw the opt-in, for the Play build and for anyone who reverts."""
    if page is not None:
        page._kiri_direct_optin = False


async def load_opt_in(storage) -> bool:
    """Restore the opt-in at startup. One key read, never fatal."""
    try:
        return (await storage.get(_DIRECT_OPTIN_KEY)) == "true"
    except Exception:
        logger.debug("could not read the direct-purchase opt-in", exc_info=True)
        return False


async def save_opt_in(storage, enabled: bool) -> bool:
    """Persist the opt-in. The UI calls this when the user chooses."""
    try:
        await storage.set(_DIRECT_OPTIN_KEY, "true" if enabled else "false")
        return True
    except Exception:
        logger.debug("could not save the direct-purchase opt-in", exc_info=True)
        return False


_UNAVAILABLE = (
    "Premium is not available in this build. It is sold on the direct APK, "
    "on desktop and on the web."
)


def _require_available() -> None:
    if not is_available():
        raise LicenseUnavailable(_UNAVAILABLE)


@dataclass(frozen=True)
class Product:
    id: str
    code: str
    kind: str
    interval: str | None
    amount: float
    currency: str
    description: str

    @property
    def is_recurring(self) -> bool:
        return self.kind != "one_time"

    @property
    def label(self) -> str:
        return f"{self.currency} {self.amount:.2f}"


@dataclass(frozen=True)
class Entitlement:
    """The outcome of a restore/status call, or an offline token check."""

    status: str  # active | grace | expired | revoked | unknown
    product: str = ""
    paid_through: str | None = None
    recovery_id: str = ""
    scope: str = ""
    token: str = ""
    offline: bool = False

    @property
    def grants_access(self) -> bool:
        return self.status in ("active", "grace")

    @property
    def is_definitive(self) -> bool:
        """True when the server actually ruled, so a downgrade is safe."""
        return self.status in ("active", "grace", "expired", "revoked")


def parse_recovery_id(value: str) -> str | None:
    """Validate a recovery ID's shape without contacting the Worker."""
    text = str(value or "").strip().upper()
    return text if _RECOVERY_RE.match(text) else None


def valid_email(value: str) -> bool:
    return bool(_EMAIL_RE.match(str(value or "").strip()))


async def _post(path: str, payload: dict[str, Any]) -> dict[str, Any]:
    _require_available()
    url = f"{BASE_URL}{path}"
    try:
        async with httpx.AsyncClient(http2=False, timeout=TIMEOUT) as client:
            resp = await client.post(url, json=payload)
    except httpx.HTTPError as exc:
        # Deliberately a distinct type: the caller must not treat an
        # unreachable Worker as a revoked licence.
        raise LicenseError(f"Could not reach the licence service: {exc}") from exc
    if resp.status_code >= 400:
        code = ""
        try:
            code = str((resp.json() or {}).get("error") or "")
        except ValueError:
            pass
        raise LicenseError(code or f"licence service returned {resp.status_code}")
    try:
        body = resp.json()
    except ValueError as exc:
        raise LicenseError("licence service sent an unreadable reply") from exc
    return body if isinstance(body, dict) else {}


async def fetch_catalog(*, force: bool = False) -> list[Product]:
    """Product list from the Worker. Cached briefly; safe to cache per docs."""
    _require_available()
    if (
        not force
        and _catalog_cache["products"]
        and time.monotonic() - _catalog_cache["at"] < CATALOG_TTL
    ):
        return list(_catalog_cache["products"])
    try:
        async with httpx.AsyncClient(http2=False, timeout=TIMEOUT) as client:
            resp = await client.get(f"{BASE_URL}/catalog")
        resp.raise_for_status()
        raw = (resp.json() or {}).get("products") or []
    except (httpx.HTTPError, ValueError) as exc:
        logger.warning("license catalog unavailable: %s", exc)
        return list(_catalog_cache["products"])
    products = [
        Product(
            id=str(item.get("id") or ""),
            code=str(item.get("code") or ""),
            kind=str(item.get("kind") or "one_time"),
            interval=item.get("interval"),
            amount=float(item.get("amount") or 0.0),
            currency=str(item.get("currency") or "USD"),
            description=str(item.get("description") or ""),
        )
        for item in raw
        if isinstance(item, dict) and item.get("id")
    ]
    if products:
        _catalog_cache["products"] = products
        _catalog_cache["at"] = time.monotonic()
    return products


async def start_checkout(
    product_id: str,
    *,
    email: str,
    name: str = "",
    phone: str = "",
) -> dict[str, Any]:
    """Create a hosted payment. Returns recovery_id and checkout_url.

    The caller must persist recovery_id immediately: it is the only way back
    in after the user clears app data.
    """
    if not valid_email(email):
        raise LicenseError("Enter a valid email address to continue.")
    payload: dict[str, Any] = {
        "app_id": APP_ID,
        "product_id": str(product_id),
        "email": str(email).strip(),
    }
    if name.strip():
        payload["name"] = name.strip()[:120]
    if phone.strip():
        payload["phone_number"] = phone.strip()[:40]
    body = await _post("/checkout", payload)
    recovery_id = str(body.get("recovery_id") or "")
    if not recovery_id:
        raise LicenseError("The payment service did not return a recovery ID.")
    return {
        "recovery_id": recovery_id,
        "checkout_url": str(body.get("checkout_url") or ""),
        "product": str(body.get("product") or product_id),
        "status": str(body.get("status") or "pending"),
        "amount": body.get("amount"),
        "currency": str(body.get("currency") or "USD"),
    }


def _entitlement_from_body(
    body: dict[str, Any], recovery_id: str, *, offline: bool = False
) -> Entitlement:
    return Entitlement(
        status=str(body.get("status") or "unknown"),
        product=str(body.get("product") or ""),
        paid_through=body.get("paid_through"),
        recovery_id=recovery_id,
        scope=str(body.get("scope") or ""),
        token=str(body.get("token") or ""),
        offline=offline,
    )


async def restore(recovery_id: str) -> Entitlement:
    """Authoritative status plus a fresh signed token."""
    clean = parse_recovery_id(recovery_id)
    if not clean:
        raise LicenseError("That recovery ID does not look right.")
    body = await _post("/restore", {"recovery_id": clean, "app_id": APP_ID})
    return _entitlement_from_body(body, clean)


async def check_status(recovery_id: str) -> Entitlement:
    """Refresh without requesting a new token."""
    clean = parse_recovery_id(recovery_id)
    if not clean:
        raise LicenseError("That recovery ID does not look right.")
    body = await _post("/status", {"recovery_id": clean, "app_id": APP_ID})
    return _entitlement_from_body(body, clean)


def verify_token(token: str) -> tuple[bool, str]:
    """Offline signature and claim check. Never raises."""
    return license_crypto.is_entitled(
        token, PUBLIC_KEY, app_id=APP_ID, issuer=ISSUER
    )


def entitlement_from_token(token: str, recovery_id: str = "") -> Entitlement:
    """Entitlement derived purely from a cached token, for offline use."""
    if not token:
        return Entitlement(status="none", recovery_id=recovery_id, offline=True)
    ok, _reason = verify_token(token)
    if not ok:
        return Entitlement(status="invalid", recovery_id=recovery_id, offline=True)
    try:
        claims = license_crypto.verify_token(token, PUBLIC_KEY)
    except license_crypto.TokenError:
        return Entitlement(status="invalid", recovery_id=recovery_id, offline=True)
    return Entitlement(
        status=str(claims.get("status") or "unknown"),
        product=str(claims.get("product") or ""),
        recovery_id=recovery_id,
        scope=str(claims.get("scope") or ""),
        token=token,
        offline=True,
    )
