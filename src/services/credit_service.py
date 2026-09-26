"""Local credit economy service - SpanInsight's model, DDGS keys.

50 free AI credits daily (200 when premium), UTC date-change reset that
preserves surplus (ad-earned credits survive). Transaction-keyed reservations
prevent overlapping commit/rollback corruption; auto-rollback after
ROLLBACK_SECONDS (240s, was documented as 60s and never matched the code).

Only AI entry points spend: manual search, scraping and downloads never call
this service, which is how "the manual way stays free" is enforced.
"""

from __future__ import annotations

import asyncio
import logging
import time
import uuid
from datetime import UTC, datetime

from core.constants import (
    DAILY_FREE_CREDITS,
    PREMIUM_DAILY_CREDITS,
    STORAGE_CREDITS,
    STORAGE_LAST_RESET,
)

logger = logging.getLogger(__name__)

# How long an UNSETTLED, INACTIVE hold is trusted before the service gives
# the credits back on its own. The timer defers while the owning turn is
# still active (re-arming up to three intervals), so this window measures
# orphans - a turn whose task died without settling - not turn length: the
# worst-case step (router 180s + gateway 2x120s) runs past 240s and is
# protected by the active guard instead of a bigger number.
ROLLBACK_SECONDS = 240.0
# Ceiling on the deferred sweep: a hold active for this long means the
# active flag itself leaked, so the sweep takes over rather than pinning
# the balance forever.
ROLLBACK_MAX_DEFERRALS = 3


class CreditService:
    """Manages the local credit economy over the app's StorageService."""

    def __init__(self, storage=None):
        self._storage = storage
        self._reservations: dict[str, int] = {}  # tx_id -> amount
        # Holds owned by a turn that is still running: the auto-rollback
        # defers to these, so the sweep can never free work in flight.
        self._active: set[str] = set()
        self._rollback_tasks: dict[str, asyncio.Task] = {}  # tx_id -> auto-rollback
        # Balance read-modify-write is a check-then-act, so two operations
        # interleaving between the read and the write lose one. Every
        # mutation of the balance now runs under this lock.
        self._lock = asyncio.Lock()
        # The UTC day this instance has already checked for a reset.
        self._reset_day: str = ""

    async def initialize(self) -> int:
        """Load credits from storage, reset if new day. Returns current balance."""
        await self._check_daily_reset()
        return await self._get_credits()

    async def reserve(self, amount: int) -> str | None:
        """Optimistically reserve credits. Returns tx id, or None if insufficient.

        Call commit(tx_id) to finalize or rollback(tx_id) to release.
        The auto-rollback sweeps only holds no live turn claims (see
        _arm_rollback); an in-flight turn's hold defers until it settles.
        """
        tx_id = str(uuid.uuid4())
        # Check and reserve as one step under the lock. Without this two
        # concurrent turns can both see the same free balance and both win.
        # (The old pre-lock read was a dead TOCTOU copy of this check.)
        async with self._lock:
            current = await self._get_credits()
            total_reserved = sum(self._reservations.values())
            if current - total_reserved < amount:
                return None
            self._reservations[tx_id] = amount
            self._active.add(tx_id)
        self._arm_rollback(tx_id, amount)
        return tx_id

    async def reserve_more(self, tx_id: str, extra: int) -> bool:
        """Grow an existing hold. False just means the balance dipped below
        the extra - soft metering: the caller keeps going (never breaks work)."""
        async with self._lock:
            if tx_id not in self._reservations:
                return False
            total_reserved = sum(self._reservations.values())
            if await self._get_credits() - total_reserved < extra:
                return False
            self._reservations[tx_id] += extra
            held = self._reservations[tx_id]
        self._arm_rollback(tx_id, held)
        return True

    def _arm_rollback(self, tx_id: str, amount: int) -> None:
        task = self._rollback_tasks.pop(tx_id, None)
        if task:
            task.cancel()
        born = time.monotonic()

        async def _auto_rollback():
            while True:
                await asyncio.sleep(ROLLBACK_SECONDS)
                # Same lock as settlement: a hold disappearing underneath a
                # delivery that is about to commit loses that charge silently.
                async with self._lock:
                    if tx_id not in self._reservations:
                        return
                    deferments = int((time.monotonic() - born) // ROLLBACK_SECONDS)
                    if tx_id in self._active and deferments < ROLLBACK_MAX_DEFERRALS:
                        # A live turn still owns this hold: one step can run
                        # longer than ROLLBACK_SECONDS (router + gateway
                        # timeouts), and freeing its hold here would let the
                        # later commit silently no-op - delivered work for
                        # free. Wait for the turn to settle.
                        logger.debug("rollback deferred, turn active (tx: %s)", tx_id)
                        continue
                    del self._reservations[tx_id]
                    self._active.discard(tx_id)
                    self._rollback_tasks.pop(tx_id, None)
                    logger.warning(
                        "Auto-rolled back %d reserved credits (tx: %s).", amount, tx_id
                    )
                    return

        self._rollback_tasks[tx_id] = asyncio.create_task(_auto_rollback())

    async def commit_amount(self, tx_id: str, amount: int | None = None) -> int:
        """Settle a hold. `amount=None` deducts the full held amount, read
        under the lock (the old commit() read the hold outside the lock, so
        a rollback landing between the read and the settle billed zero).
        Explicit amounts may under/over-shoot the hold; overdraft clamps at
        zero - a completed message is never revoked by billing.

        Idempotent. A second call with the same tx_id finds no hold and
        returns without charging, so a retried settlement cannot bill the
        user twice for one turn.
        """
        from core.state import state

        task = self._rollback_tasks.pop(tx_id, None)
        if task:
            task.cancel()
        async with self._lock:
            self._active.discard(tx_id)
            if tx_id not in self._reservations:
                logger.info("settlement for %s already applied", tx_id)
                return await self._get_credits()
            held = self._reservations.pop(tx_id, 0)
            if amount is None:
                amount = held
            if amount <= 0:
                return await self._get_credits()
            current = await self._get_credits()
            new_balance = max(0, current - amount)
            await self._storage.set(STORAGE_CREDITS, str(new_balance))
            # Published inside the lock so a concurrent reward or reset
            # cannot overwrite it with a value that ignores this debit.
            state.credits_remaining = new_balance
        logger.info(
            "Settled %d credits (held %d, tx: %s). Remaining: %d",
            amount,
            held,
            tx_id,
            new_balance,
        )
        return new_balance

    async def commit(self, tx_id: str) -> int:
        """Finalize a reservation - deduct the full held amount (read and
        billed under one lock)."""
        return await self.commit_amount(tx_id)

    async def charge(self, amount: int) -> int:
        """Direct debit with no hold; overdraft clamps at zero (soft metering:
        a completed message is never refunded by billing)."""
        from core.state import state

        # Read, write and publish under one lock: otherwise an ad reward
        # or a daily reset landing between the read and the write silently
        # loses one of the two operations.
        async with self._lock:
            current = await self._get_credits()
            new_balance = max(0, current - amount)
            await self._storage.set(STORAGE_CREDITS, str(new_balance))
            state.credits_remaining = new_balance
        logger.info("Charged %d credits. Remaining: %d", amount, new_balance)
        return new_balance

    async def rollback(self, tx_id: str) -> None:
        """Release a reservation without deducting credits."""
        task = self._rollback_tasks.pop(tx_id, None)
        if task:
            task.cancel()
        async with self._lock:
            self._reservations.pop(tx_id, None)
            self._active.discard(tx_id)

    async def spend(self, amount: int) -> tuple[bool, int]:
        """Deduct credits directly (no reservation). Returns (success, remaining)."""
        from core.state import state

        async with self._lock:
            current = await self._get_credits()
            total_reserved = sum(self._reservations.values())
            if current - total_reserved < amount:
                return False, current
            new_balance = current - amount
            await self._storage.set(STORAGE_CREDITS, str(new_balance))
            state.credits_remaining = new_balance
        logger.info("Spent %d credits. Remaining: %d", amount, new_balance)
        return True, new_balance

    async def add_credits(self, amount: int) -> int:
        """Add credits (ad rewards, premium grant). Returns the new balance."""
        from core.state import state

        async with self._lock:
            current = await self._get_credits()
            new_balance = current + amount
            await self._storage.set(STORAGE_CREDITS, str(new_balance))
            state.credits_remaining = new_balance
        logger.info("Added %d credits. New balance: %d", amount, new_balance)
        return new_balance

    async def get_balance(self) -> int:
        # The reset used to be reachable only from initialize(), i.e. only
        # at launch: an app left open across 00:00 UTC never refilled, so
        # "resets 00:00 UTC" was untrue for every long session and a premium
        # cap bought late in the day waited until the next restart.
        await self._check_daily_reset()
        return await self._get_credits()

    async def check_balance(self, amount: int) -> tuple[bool, int]:
        balance = await self._get_credits()
        return balance >= amount, balance

    async def get_daily_cap(self) -> int:
        """Premium users refill to the premium cap."""
        from core.state import state

        if getattr(state, "is_premium", False):
            return PREMIUM_DAILY_CREDITS
        return DAILY_FREE_CREDITS

    async def _check_daily_reset(self) -> None:
        """UTC date change tops the balance up to the cap, preserving surplus."""
        from core.state import state

        today = datetime.now(tz=UTC).date().isoformat()
        # Memoised: this now runs on every balance read, and a storage round
        # trip per read would be a tax on the hot path.
        if self._reset_day == today:
            return
        last_reset = await self._storage.get(STORAGE_LAST_RESET)
        if last_reset == today:
            self._reset_day = today
            return
        async with self._lock:
            # Re-check the memo under the lock: two concurrent entries on a
            # day boundary would otherwise both top up (idempotent today,
            # but the second pass must find the work already done).
            if self._reset_day == today:
                return
            # Re-read under the lock: the clock is checked outside it, but
            # two concurrent entries could both pass and both top up.
            current = await self._get_credits()
            daily_cap = await self.get_daily_cap()
            new_balance = max(current, daily_cap)
            await self._storage.set(STORAGE_CREDITS, str(new_balance))
            await self._storage.set(STORAGE_LAST_RESET, today)
            state.credits_remaining = new_balance
            self._reset_day = today
            # Deliberately NOT clearing self._reservations. A turn in flight
            # at midnight holds a reservation it is about to settle; clearing
            # it made that turn's later commit find nothing and silently
            # charge zero for delivered work. Holds are short-lived and
            # self-rollback after ROLLBACK_SECONDS regardless.
        logger.info(
            "Daily credit reset: balance preserved/topped up at %d.", new_balance
        )

    async def _get_credits(self) -> int:
        from core.constants import DAILY_FREE_CREDITS as _default

        val = await self._storage.get(STORAGE_CREDITS)
        try:
            return int(val) if val else _default
        except (TypeError, ValueError):
            return _default


_credit_service: CreditService | None = None


def init_credit_service(storage) -> CreditService:
    """Create the process-wide singleton (called once by AppController)."""
    global _credit_service
    _credit_service = CreditService(storage=storage)
    return _credit_service


def get_credit_service() -> CreditService | None:
    return _credit_service
