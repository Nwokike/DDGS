"""Premium entitlement: one flag, two possible channels.

    premium = play_purchase_active OR license_active

`state.is_premium` stays the single switch that ad_service, credit_service,
wallet and styles read, so none of them change. What is new here is that it
becomes *derived* rather than latched: a licence can now be revoked, and a
Play purchase no longer grants a permanent local boolean that nothing can
take back.

The offline rule, which is the whole point of the local token:

  - a locally valid token keeps Premium until its own `exp`
  - a lifetime token has no `exp`, so it stays valid offline indefinitely
  - a network failure NEVER downgrades. Only an authoritative
    `revoked`/`expired` from the server removes access.

That last line matters more than it looks: someone who buys Premium and then
flies on a plane must not lose it at 30,000 feet.
"""

from __future__ import annotations

import logging

from core.state import state
from services import license_service

logger = logging.getLogger(__name__)


def apply_entitlement() -> bool:
    """Recompute `state.is_premium` from the channel flags and persist it."""
    resolved = bool(getattr(state, "play_premium_active", False)) or bool(
        getattr(state, "license_premium_active", False)
    )
    if getattr(state, "is_premium", False) != resolved:
        state.is_premium = resolved
    return resolved


def set_play_entitlement(active: bool, *, product_id: str = "") -> None:
    """Record the Play Billing channel's answer."""
    state.play_premium_active = bool(active)
    if active and product_id:
        state.premium_source = f"play:{product_id}"
    elif not active:
        state.premium_source = ""
    apply_entitlement()


def _store_license(fields: dict) -> None:
    storage = getattr(state, "credit_service", None)
    storage = getattr(storage, "_storage", None) if storage else None
    if storage is None:
        return
    # Fire-and-forget: the caller is usually a UI callback. A lost write
    # only costs a re-restore, never an incorrect unlock.
    import asyncio

    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        return
    loop.create_task(storage.set_license_record(**fields))


def apply_license_entitlement(entitlement: license_service.Entitlement) -> None:
    """Record the license channel's answer and resolve Premium.

    `offline=True` means the verdict came from the cached token alone. A
    locally valid token is trusted to its expiry; a locally invalid one is
    ignored rather than used to downgrade someone whose token is merely
    stale on disk.
    """
    if entitlement.offline and not entitlement.grants_access:
        logger.debug("offline license check not conclusive: %s", entitlement.status)
        return
    if not entitlement.is_definitive and not entitlement.grants_access:
        # Online but the Worker said something we do not recognise. That is
        # not proof of expiry, so leave the current entitlement alone.
        logger.debug("non-definitive license status ignored: %s", entitlement.status)
        return
    state.license_premium_active = entitlement.grants_access
    state.license_status = entitlement.status
    if entitlement.product:
        state.license_product = entitlement.product
    if entitlement.token:
        _store_license({"token": entitlement.token})
    if entitlement.paid_through is not None:
        _store_license({"paid_through": entitlement.paid_through})
    apply_entitlement()
    if entitlement.grants_access:
        state.premium_source = f"license:{entitlement.product or 'unknown'}"


def clear_license() -> None:
    """Forget the license entirely (user action, not a refund)."""
    state.license_premium_active = False
    state.license_status = ""
    state.license_product = ""
    state.premium_source = ""
    _store_license({"recovery_id": "", "token": "", "status": "", "product": ""})
    apply_entitlement()


async def load_from_storage(storage) -> None:
    """Startup: read the stored license and trust the token offline.

    Runs before any network call so a user with no connection still gets
    the Premium they paid for.

    The persisted `is_premium` value is deliberately NOT used as proof. It
    is a resolved cache from a previous run, and either channel can have
    been revoked since. Loading here recomputes the OR from the channel
    flags, so a stale true cannot survive with no token and no purchase.
    """
    from services import license_service as licenses

    try:
        record = await storage.get_license_record()
    except Exception as exc:
        logger.warning("license record unreadable: %s", exc)
        apply_entitlement()
        return
    state.license_recovery_id = str(record.get("recovery_id") or "")
    if not state.license_recovery_id and not record.get("token"):
        # Nothing on disk proves entitlement through this channel.
        apply_entitlement()
        return
    entitlement = licenses.entitlement_from_token(
        str(record.get("token") or ""), state.license_recovery_id
    )
    state.license_status = entitlement.status
    state.license_product = entitlement.product or str(record.get("product") or "")
    apply_license_entitlement(entitlement)
    logger.info("offline license status: %s", entitlement.status)


async def refresh_from_server(page=None) -> bool:
    """Ask the Worker for the authoritative answer, when we can.

    Returns True only when the server actually ruled. Any failure is
    swallowed on purpose: an unreachable service must not cost the user
    their Premium, because the local token already covers them until it
    expires. The caller needs the boolean so it never tells a user their
    payment was confirmed when no request ever succeeded.
    """
    if not license_service.is_available(page):
        return False
    recovery_id = getattr(state, "license_recovery_id", "")
    if not recovery_id:
        return False
    try:
        entitlement = await license_service.check_status(recovery_id)
    except license_service.LicenseUnavailable:
        return False
    except license_service.LicenseError as exc:
        logger.info("license status check skipped: %s", exc)
        return False
    except Exception as exc:  # never let a network blip touch entitlement
        logger.debug("license status check failed: %s", exc)
        return False
    # Only a definitive verdict may downgrade. A 200 carrying an unknown or
    # transitional status ("pending", a future value) is not proof of
    # expiry, and treating it as one would strip Premium from a paying user
    # on a schema change.
    if entitlement.is_definitive:
        state.license_premium_active = entitlement.grants_access
    state.license_status = entitlement.status
    if entitlement.product:
        state.license_product = entitlement.product
    apply_entitlement()
    if entitlement.grants_access:
        state.premium_source = f"license:{entitlement.product or 'unknown'}"
    logger.info("license status from server: %s", entitlement.status)
    return True


async def restore_license(recovery_id: str) -> license_service.Entitlement:
    """Restore from a recovery ID after reinstall or a data wipe."""
    entitlement = await license_service.restore(recovery_id)
    state.license_recovery_id = entitlement.recovery_id or recovery_id
    _store_license({"recovery_id": state.license_recovery_id})
    if entitlement.token:
        _store_license({"token": entitlement.token})
    _store_license({"status": entitlement.status, "product": entitlement.product})
    state.license_status = entitlement.status
    state.license_product = entitlement.product
    state.license_premium_active = entitlement.grants_access
    apply_entitlement()
    if entitlement.grants_access:
        state.premium_source = f"license:{entitlement.product or 'unknown'}"
    return entitlement
