"""Ported from SpanInsight's test_credit_service — DDGS credit economy."""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime

import pytest

from core.constants import (
    DAILY_FREE_CREDITS,
    PREMIUM_DAILY_CREDITS,
    STORAGE_CREDITS,
    STORAGE_LAST_RESET,
)
from core.state import state
from services.credit_service import CreditService


class FakeStorage:
    def __init__(self):
        self.d = {}

    async def get(self, key, default=None):
        return self.d.get(key, default)

    async def set(self, key, value):
        self.d[key] = value
        return True


@pytest.fixture()
def svc():
    state.is_premium = False
    state.credits_remaining = DAILY_FREE_CREDITS
    storage = FakeStorage()
    storage.d[STORAGE_LAST_RESET] = datetime.now(tz=UTC).date().isoformat()
    storage.d[STORAGE_CREDITS] = str(DAILY_FREE_CREDITS)
    return CreditService(storage=storage)


def run(coro):
    return asyncio.run(coro)


def test_initial_balance_is_daily_free(svc):
    assert run(svc.initialize()) == DAILY_FREE_CREDITS


def test_reserve_insufficient_returns_none(svc):
    async def go():
        assert await svc.reserve(DAILY_FREE_CREDITS + 1) is None

    run(go())


def test_reserve_then_commit_deducts(svc):
    async def go():
        tx = await svc.reserve(3)
        assert tx is not None
        assert await svc.commit(tx) == DAILY_FREE_CREDITS - 3
        assert await svc.get_balance() == DAILY_FREE_CREDITS - 3

    run(go())


def test_rollback_releases_without_deducting(svc):
    async def go():
        tx = await svc.reserve(5)
        await svc.rollback(tx)
        assert await svc.get_balance() == DAILY_FREE_CREDITS

    run(go())


def test_spend_direct_and_add(svc):
    async def go():
        ok, balance = await svc.spend(10)
        assert ok and balance == DAILY_FREE_CREDITS - 10
        ok, balance = await svc.spend(DAILY_FREE_CREDITS)  # only 40 left
        assert not ok
        assert await svc.add_credits(2) == DAILY_FREE_CREDITS - 8

    run(go())


def test_daily_reset_preserves_surplus(svc):
    async def go():
        await svc._storage.set(STORAGE_CREDITS, "70")
        await svc._storage.set(STORAGE_LAST_RESET, "1970-01-01")
        assert await svc.initialize() == 70  # 70 > 50 cap → kept

    run(go())


def test_daily_reset_tops_up_when_below_cap(svc):
    async def go():
        await svc._storage.set(STORAGE_CREDITS, "3")
        await svc._storage.set(STORAGE_LAST_RESET, "1970-01-01")
        assert await svc.initialize() == DAILY_FREE_CREDITS

    run(go())


def test_premium_reset_uses_premium_cap():
    state.is_premium = True
    state.credits_remaining = PREMIUM_DAILY_CREDITS
    storage = FakeStorage()
    storage.d[STORAGE_LAST_RESET] = "1970-01-01"
    storage.d[STORAGE_CREDITS] = "60"
    svc = CreditService(storage=storage)
    try:
        assert run(svc.initialize()) == PREMIUM_DAILY_CREDITS
    finally:
        state.is_premium = False


def test_reservations_block_double_spend(svc):
    async def go():
        tx1 = await svc.reserve(30)
        tx2 = await svc.reserve(30)
        assert tx1 is not None
        assert tx2 is None  # 50 - 30 reserved < 30

    run(go())


def test_concurrent_reserves_cannot_oversell(svc):
    """The lock serializes reserve: six 10-credit holds on a 50 balance
    must admit exactly five."""
    async def go():
        results = await asyncio.gather(
            *[svc.reserve(10) for _ in range(6)]
        )
        granted = [r for r in results if r is not None]
        assert len(granted) == 5, f"oversell: {len(granted)} holds on 50 credits"
        assert sum(svc._reservations.values()) == 50

    run(go())


def test_commit_bills_the_full_hold_under_lock(svc):
    """commit() must read the hold inside commit_amount's lock (the old
    read-outside raced the rollback timer into a free turn)."""
    async def go():
        balance = await svc.get_balance()
        tx = await svc.reserve(7)
        assert tx is not None
        remaining = await svc.commit(tx)
        assert remaining == balance - 7
        assert tx not in svc._reservations
        assert tx not in svc._active

    run(go())


def test_settlement_is_idempotent(svc):
    """A retried settlement cannot bill twice for one turn."""
    async def go():
        balance = await svc.get_balance()
        tx = await svc.reserve(5)
        first = await svc.commit_amount(tx, 5)
        second = await svc.commit_amount(tx, 5)
        assert first == balance - 5
        assert second == first, "the retry must not debit again"

    run(go())


def test_auto_rollback_defers_while_a_turn_is_active(monkeypatch):
    """The sweep frees orphans only: an active hold survives its timer (a
    single step can outlast ROLLBACK_SECONDS), and the deferral is bounded
    so a leaked active flag cannot pin the balance forever."""
    import services.credit_service as cs

    monkeypatch.setattr(cs, "ROLLBACK_SECONDS", 0.1)
    svc2 = cs.CreditService(storage=FakeStorage())

    async def go():
        tx = await svc2.reserve(10)
        assert tx is not None
        await asyncio.sleep(0.15)  # one fire: deferred, still held
        assert tx in svc2._reservations, "an active turn must keep its hold"
        await asyncio.sleep(0.4)  # past ROLLBACK_MAX_DEFERRALS: sweep takes over
        assert tx not in svc2._reservations, "the bounded sweep must release it"

    run(go())


def test_auto_rollback_frees_an_orphaned_hold(monkeypatch):
    import services.credit_service as cs

    monkeypatch.setattr(cs, "ROLLBACK_SECONDS", 0.1)
    svc2 = cs.CreditService(storage=FakeStorage())

    async def go():
        tx = await svc2.reserve(10)
        assert tx is not None
        svc2._active.discard(tx)  # simulate a turn that died without settling
        await asyncio.sleep(0.25)
        assert tx not in svc2._reservations, "an orphan must be swept"

    run(go())
