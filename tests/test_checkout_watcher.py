"""Checkout watcher: backoff, jitter, and the hard-refusal abort.

The watcher exists so the user does not have to press Restore the moment a
payment lands. But the Worker it polls runs on the **free tier** of
Workers KV, where the account gets 1,000 *writes* per day across every
request. A fixed 5-second poll for the whole 15-minute window spends ~180
of those writes for one checkout, which is how a single purchase attempt
can exhaust a day's budget.

So the cadence is deliberately shaped (see premium_service.py):

- base interval + jitter + backoff after consecutive failures - fast while
  the payment is landing, slow once it clearly hasn't;
- a stop on the terminal codes. The server has already judged the payment;
  polling the rest of the window cannot change the answer.

404 is *not* terminal: right after a successful payment the entitlement
record may not exist yet (webhook lag), and the payment is usually real.
Aborting on that would tell a paying user to restore again.

See also ktv-player/tests/test_checkout_watcher.py (where this cadence was
first pinned) and kiri-license/docs/kv-free-tier-budget.md.
"""

from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager

import pytest

RECOVERY = "KIRI-L-DDGSTEST0000000000001"

# The pinned WebCrypto vector from tests/test_license.py: a real P-256
# signature over the base64url payload, app "ng.kiri.ddgs", product
# "lifetime", status "active", exp null.
_VECTOR_PUB = (
    "MFkwEwYHKoZIzj0CAQYIKoZIzj0DAQcDQgAE-r-u3gRG8Ik3wJ3ffIHf_NYv0AWhIcfLL"
    "MjY9nG6TQHTAo_cCMw995JGjQCVlJeacKV9ben8ZVpwQ3wqbkbDdw"
)
_VECTOR_TOKEN = (
    "v1.eyJpc3MiOiJsaWNlbnNlLmtpcmkubmciLCJ2IjoxLCJlbnQiOiJhYmMiLCJhcHAiOiJuZy5raXJpLmRkZ3MiLCJwcm9kdWN0IjoibGlmZXRpbWUiLCJzY29wZSI6InVuaXZlcnNhbCIsIm1vZGUiOiJvbmVfdGltZSIsInN0YXR1cyI6ImFjdGl2ZSIsInBhaWRfdGhyb3VnaCI6bnVsbCwiaWF0IjoxNzUwMDAwMDAwLCJleHAiOm51bGx9"
    ".HQIjQ6Q98mIKLASt5c66Lr_TcV5h15Hxm5tCfDmjoWZ0-dmYVNNNevU0ugUUWp6mYhCBDHFM8aD2-hly399LPw"
)


class FakeResponse:
    def __init__(self, status_code: int, payload: dict | None = None) -> None:
        self.status_code = status_code
        self._payload = payload if payload is not None else {}

    def json(self) -> dict:
        return self._payload


class _FakeClient:
    """Scripted `post`; every call is recorded so the loop is countable."""

    def __init__(self, urls: list[str], script: list) -> None:
        self.urls = urls
        self.script = list(script)

    async def post(self, url, **kwargs):
        self.urls.append(str(url))
        if not self.script:
            raise AssertionError("unexpected extra request")
        item = self.script.pop(0)
        if isinstance(item, Exception):
            raise item
        return item


def _faked_client(monkeypatch, script, urls):
    """Point license_service._client at a scripted client.

    `service.license` calls the module-level `_client`, so this intercepts
    every request the watcher makes.
    """
    client = _FakeClient(urls, script)

    @asynccontextmanager
    async def _client():
        yield client

    monkeypatch.setattr("services.license_service._client", _client)
    return client


def _active():
    return FakeResponse(
        200,
        {"status": "active", "product": "lifetime", "token": _VECTOR_TOKEN},
    )


def _not_found():
    return FakeResponse(404, {"error": "license_not_found"})


def _pending():
    return FakeResponse(202, {"status": "pending"})


def _refused():
    return FakeResponse(403, {"error": "app_not_entitled"})


def _payment_not_valid():
    return FakeResponse(402, {"error": "payment_not_valid"})


def _service():
    """A service whose license verifies the pinned test vector.

    The fixture token is signed by a throwaway pair, so the production key
    baked into the default constructor would reject it and the unlock path
    under test could never fire.
    """
    from services.license_service import KiriLicenseService
    from services.premium_service import PremiumService

    premium = PremiumService(None, None)
    premium.license = KiriLicenseService(
        public_key=_VECTOR_PUB, on_change=premium._recompute_premium
    )
    return premium


def _run(monkeypatch, script):
    """Run one watcher loop and report how many requests it made."""
    urls: list[str] = []
    _faked_client(monkeypatch, script, urls)
    premium = _service()
    asyncio.run(premium._checkout_watch_loop(RECOVERY))
    return urls


@pytest.fixture
def fast_watcher(monkeypatch):
    """Deterministic cadence: real seconds would make the suite slow, and
    the jitter term would make it non-reproducible."""
    from services import premium_service

    monkeypatch.setattr(premium_service, "CHECKOUT_WATCH_INTERVAL", 0.005)
    monkeypatch.setattr(premium_service, "CHECKOUT_WATCH_TIMEOUT", 0.5)
    monkeypatch.setattr(premium_service.random, "uniform", lambda low, high: 0.0)


@pytest.fixture(autouse=True)
def _reset_premium():
    from core.state import state

    state.license_premium_active = False
    state.is_premium = False
    yield
    state.license_premium_active = False
    state.is_premium = False


# -- polling does not stop early ---------------------------------------------


def test_a_pending_payment_gives_up_after_the_window(fast_watcher, monkeypatch):
    """202 payment_pending is not a verdict: wait the whole window out."""
    urls = _run(monkeypatch, [_pending()] * 50)
    assert len(urls) >= 2, "a pending payment must keep polling"


def test_a_404_keeps_polling_until_the_record_appears(fast_watcher, monkeypatch):
    """Webhook lag looks like a 404. The payment is real - keep polling."""
    urls = _run(monkeypatch, [_not_found(), _not_found(), _active()])
    assert len(urls) == 3, f"404 must not be terminal, got {urls}"


# -- the abort ---------------------------------------------------------------


@pytest.mark.parametrize("refusal", [_refused(), _payment_not_valid()])
def test_a_hard_refusal_stops_the_watcher_after_one_poll(
    fast_watcher, monkeypatch, refusal
):
    """402/403 will never resolve: stop, and stop spending the budget.

    The write budget is the reason this matters. Polling a dead licence for
    the rest of the window spends requests that a later purchase - or a
    token refresh - needs, and gets an answer we already have.
    """
    urls = _run(monkeypatch, [refusal] * 20)
    assert len(urls) == 1, f"a terminal refusal must stop the watcher, got {urls}"


# -- cadence -----------------------------------------------------------------


def test_transient_failures_back_off(fast_watcher, monkeypatch):
    """Consecutive failures widen the interval; a success resets it."""
    sleeps: list[float] = []
    real_sleep = asyncio.sleep

    async def _recorded_sleep(seconds, *args, **kwargs):
        sleeps.append(seconds)
        await real_sleep(0)

    from services import premium_service

    monkeypatch.setattr(premium_service.asyncio, "sleep", _recorded_sleep)

    # Two failures, then the unlock script runs out on the third poll.
    urls = _run(monkeypatch, [_not_found(), _not_found(), _active()])

    assert len(urls) == 3, f"expected three polls, got {urls}"
    assert len(sleeps) >= 3
    assert sleeps[0] < sleeps[1] < sleeps[2], (
        f"backoff must widen the interval, got {sleeps}"
    )
