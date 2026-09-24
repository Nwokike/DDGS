"""Kiri License client — UNUSABLE in a Play-distributed build.

This is the playstore branch's stub. The real implementation on `main`
sells Premium through Flutterwave, which is a permitted external checkout
for direct APKs, desktop and web.

Google Play policy forbids steering Play users to an external payment
provider, so a Play build must not contain the button. Hiding it behind a
flag would still ship the code, the endpoint and the recovery-ID UI to Play
review. Replacing the module is the honest version of that: `is_available()`
is False, every entry point refuses, and there is nothing to inspect.

The Play build buys through Play Billing in
`components/settings/sections_premium.py`, which is also a Play-only
variant of that file.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

APP_ID = "ng.kiri.ddgs"
_REASON = (
    "Premium in this build is bought through Google Play, so the direct "
    "checkout channel is not available."
)


class LicenseUnavailable(Exception):
    """Always raised here: Play builds use Play Billing."""


class LicenseError(Exception):
    """Kept so callers can share one except-clause across builds."""


def is_available() -> bool:
    """False in every Play-distributed build."""
    return False


@dataclass(frozen=True)
class Product:
    id: str = ""
    code: str = ""
    kind: str = ""
    interval: str | None = None
    amount: float = 0.0
    currency: str = ""
    description: str = ""


@dataclass(frozen=True)
class Entitlement:
    status: str = "none"
    product: str = ""
    paid_through: str | None = None
    recovery_id: str = ""
    scope: str = ""
    token: str = ""
    offline: bool = False

    @property
    def grants_access(self) -> bool:
        return False

    @property
    def is_definitive(self) -> bool:
        return False


def parse_recovery_id(value: str) -> str | None:
    return None


def valid_email(value: str) -> bool:
    return False


async def fetch_catalog(*, force: bool = False) -> list[Product]:
    raise LicenseUnavailable(_REASON)


async def start_checkout(product_id: str, **kwargs: Any) -> dict[str, Any]:
    raise LicenseUnavailable(_REASON)


async def restore(recovery_id: str) -> Entitlement:
    raise LicenseUnavailable(_REASON)


async def check_status(recovery_id: str) -> Entitlement:
    raise LicenseUnavailable(_REASON)


def verify_token(token: str) -> tuple[bool, str]:
    return (False, "unavailable")


def entitlement_from_token(token: str, recovery_id: str = "") -> Entitlement:
    return Entitlement(status="none", recovery_id=recovery_id, offline=True)
