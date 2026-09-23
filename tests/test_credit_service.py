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
