"""Local credit economy service — SpanInsight's model, DDGS keys.

50 free AI credits daily (200 when premium), UTC date-change reset that
preserves surplus (ad-earned credits survive). Transaction-keyed reservations
prevent overlapping commit/rollback corruption; auto-rollback after 60s.

Only AI entry points spend: manual search, scraping and downloads never call
this service, which is how "the manual way stays free" is enforced.
"""

from __future__ import annotations

import asyncio
import logging
import uuid
from datetime import UTC, datetime

from core.constants import (
    DAILY_FREE_CREDITS,
    PREMIUM_DAILY_CREDITS,
    STORAGE_CREDITS,
    STORAGE_LAST_RESET,
)

logger = logging.getLogger(__name__)


class CreditService:
    """Manages the local credit economy over the app's StorageService."""

    def __init__(self, storage=None):
        self._storage = storage
        self._reservations: dict[str, int] = {}  # tx_id -> amount
        self._rollback_tasks: dict[str, asyncio.Task] = {}  # tx_id -> auto-rollback

    async def initialize(self) -> int:
        """Load credits from storage, reset if new day. Returns current balance."""
        await self._check_daily_reset()
        return await self._get_credits()

    async def reserve(self, amount: int) -> str | None:
        """Optimistically reserve credits. Returns tx id, or None if insufficient.

        Call commit(tx_id) to finalize or rollback(tx_id) to release.
        Auto-rollback after 60 seconds if neither happens.
        """
        current = await self._get_credits()
        total_reserved = sum(self._reservations.values())
        if current - total_reserved < amount:
            return None

        tx_id = str(uuid.uuid4())
        self._reservations[tx_id] = amount
        self._arm_rollback(tx_id, amount)
        return tx_id

    async def reserve_more(self, tx_id: str, extra: int) -> bool:
        """Grow an existing hold. False just means the balance dipped below
        the extra — soft metering: the caller keeps going (never breaks work)."""
        if tx_id not in self._reservations:
            return False
        total_reserved = sum(self._reservations.values())
        if await self._get_credits() - total_reserved < extra:
            return False
        self._reservations[tx_id] += extra
        self._arm_rollback(tx_id, self._reservations[tx_id])
        return True

    def _arm_rollback(self, tx_id: str, amount: int) -> None:
        task = self._rollback_tasks.pop(tx_id, None)
        if task:
            task.cancel()

        async def _auto_rollback():
            await asyncio.sleep(240)
            if tx_id in self._reservations:
                del self._reservations[tx_id]
                self._rollback_tasks.pop(tx_id, None)
                logger.warning(
                    "Auto-rolled back %d reserved credits (tx: %s).", amount, tx_id
                )

        self._rollback_tasks[tx_id] = asyncio.create_task(_auto_rollback())

    async def commit_amount(self, tx_id: str, amount: int) -> int:
        """Settle a hold for an exact charge. May under/over-shoot the hold;
        overdraft clamps at zero - a completed message is never revoked by billing."""
        from core.state import state

        task = self._rollback_tasks.pop(tx_id, None)
        if task:
            task.cancel()
        held = self._reservations.pop(tx_id, 0)
        if amount <= 0:
            return await self._get_credits()
        current = await self._get_credits()
        new_balance = max(0, current - amount)
        await self._storage.set(STORAGE_CREDITS, str(new_balance))
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
        """Finalize a reservation - deduct the full held amount."""
        return await self.commit_amount(tx_id, self._reservations.get(tx_id, 0))

    async def charge(self, amount: int) -> int:
        """Direct debit with no hold; overdraft clamps at zero (soft metering:
        a completed message is never refunded by billing)."""
        from core.state import state

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
        self._reservations.pop(tx_id, None)

    async def spend(self, amount: int) -> tuple[bool, int]:
        """Deduct credits directly (no reservation). Returns (success, remaining)."""
        from core.state import state

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

        current = await self._get_credits()
        new_balance = current + amount
        await self._storage.set(STORAGE_CREDITS, str(new_balance))
        state.credits_remaining = new_balance
        logger.info("Added %d credits. New balance: %d", amount, new_balance)
        return new_balance

    async def get_balance(self) -> int:
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
        last_reset = await self._storage.get(STORAGE_LAST_RESET)
        if last_reset != today:
            current = await self._get_credits()
            daily_cap = await self.get_daily_cap()
            new_balance = max(current, daily_cap)
            await self._storage.set(STORAGE_CREDITS, str(new_balance))
            await self._storage.set(STORAGE_LAST_RESET, today)
            state.credits_remaining = new_balance
            self._reservations.clear()
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
