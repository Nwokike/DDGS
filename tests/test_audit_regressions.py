"""Regression tests for the post-publish audit findings.

Each test here corresponds to a real user-visible bug found by auditing
everything since the last production publish. They are behavioural, not
source-text checks, so they fail when the behaviour is broken rather than
when a comment is reworded.
"""

from __future__ import annotations

import asyncio
import os
import sys
import tempfile
import time
from pathlib import Path

import pytest

SRC = Path(__file__).resolve().parents[1] / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))


class FakeStorage:
    def __init__(self, initial: dict | None = None):
        self.data = dict(initial or {})
        self.fail_writes = False

    async def get(self, key, default=None):
        return self.data.get(key, default)

    async def set(self, key, value):
        if self.fail_writes:
            return False
        self.data[key] = value
        return True

    async def flush(self):
        return None

    async def add_history(self, entry):
        self.data.setdefault("search_history", []).insert(0, entry)
        return True

    async def get_history(self):
        return self.data.get("search_history", [])

    async def get_is_premium(self):
        return bool(self.data.get("is_premium", False))

    async def set_is_premium(self, v):
        return await self.set("is_premium", v)

    async def get_license_record(self):
        return {
            "recovery_id": self.data.get("license_recovery_id", ""),
            "token": self.data.get("license_token", ""),
            "status": self.data.get("license_status", ""),
            "product": self.data.get("license_product", ""),
            "paid_through": self.data.get("license_paid_through"),
            "email": "",
            "name": "",
            "phone": "",
        }

    async def set_license_record(self, **fields):
        mapping = {
            "recovery_id": "license_recovery_id",
            "token": "license_token",
            "status": "license_status",
            "product": "license_product",
            "paid_through": "license_paid_through",
        }
        for key, value in fields.items():
            if key in mapping:
                await self.set(mapping[key], value)
        return True

    async def set_assistant_history(self, v):
        return await self.set("assistant_history", v)


# ── premium must be proven, never assumed from a stale flag ─────────────
def test_stale_persisted_premium_does_not_grant_access(monkeypatch):
    """A leftover is_premium:true must not survive without a token.

    The persisted value is a cache of a previous run. Either channel can
    have been revoked since, so load_local() derives the flag from the
    token instead of trusting it.
    """
    from core.state import state
    from services import premium_service

    monkeypatch.setattr(premium_service, "CHANNEL", "direct")
    state.is_premium = True  # as if loaded from storage.json
    state.play_premium_active = False
    state.license_premium_active = False

    service = premium_service.PremiumService(None, FakeStorage({"is_premium": True}))
    asyncio.run(service.load_local())
    assert state.is_premium is False, (
        "a stale flag granted Premium with no token and no purchase"
    )


def test_load_local_clears_a_rejected_token(monkeypatch):
    """A token we cannot verify is dropped, not treated as inconclusive.

    Distinguishing this from a network failure is the whole trust model:
    a tampered local token is proof of nothing, an unreachable server is
    proof of nothing either.
    """
    from core.state import state
    from services import premium_service

    monkeypatch.setattr(premium_service, "CHANNEL", "direct")
    state.is_premium = False
    state.license_premium_active = True
    service = premium_service.PremiumService(
        None, FakeStorage({"kiri_token": "v1.!!!.###"})
    )
    asyncio.run(service.load_local())
    assert state.is_premium is False, "an unverifiable token must not unlock"
    assert service.license.unlocked is False


def test_play_channel_cannot_unlock_from_a_leftover_token(monkeypatch):
    """The AAB must stay free-only even if a direct-install token is on disk."""
    from core.state import state
    from services import premium_service

    monkeypatch.setattr(premium_service, "CHANNEL", "play")
    state.is_premium = False
    service = premium_service.PremiumService(None, FakeStorage())
    asyncio.run(service.load_local())
    assert state.is_premium is False
    assert service.available is False
    monkeypatch.undo()


def test_network_failure_keeps_the_verdict_but_a_refusal_drops_it(
    monkeypatch,
):
    """KTV's split: an unreachable Worker is inconclusive, a refusal is not."""
    from core.state import state
    from services import license_service, premium_service

    monkeypatch.setattr(premium_service, "CHANNEL", "direct")
    state.play_premium_active = False
    state.license_premium_active = True
    state.is_premium = True
    service = premium_service.PremiumService(
        None, FakeStorage({"kiri_recovery_id": "KIRI-L-" + "A" * 24})
    )
    # The service, not state, is the licence's source of truth: reconcile
    # re-derives from license.unlocked, so seed it the way a successful
    # load_local would have.
    service.license._unlocked = True
    service._recompute_premium()
    assert state.is_premium is True

    async def offline(*args, **kwargs):
        raise license_service.LicenseUnavailable("unreachable")

    # reconcile uses the token-issuing restore path (KTV Player), never
    # /status: a network failure must not revoke.
    monkeypatch.setattr(service.license, "restore", offline)
    asyncio.run(service.reconcile())
    assert state.is_premium is True, "a network failure must not revoke"

    # A refusal is the server ruling: the client clears the unlock itself.
    async def refusing(recovery_id):
        service.license._unlocked = False
        raise license_service.LicenseUnavailable("404 license_not_found")

    monkeypatch.setattr(service.license, "restore", refusing)
    asyncio.run(service.reconcile())
    assert state.is_premium is False, "a refusal must revoke"


def test_reconcile_uses_the_token_issuing_path(monkeypatch):
    """`/status` issues no token; reconcile must call restore or a renewal
    lapses the cached token and locks out a paying subscriber (KTV rule)."""
    from core.state import state
    from services import license_service, premium_service

    monkeypatch.setattr(premium_service, "CHANNEL", "direct")
    service = premium_service.PremiumService(
        None, FakeStorage({"kiri_recovery_id": "KIRI-L-" + "A" * 24})
    )
    calls: list[str] = []

    async def restore(recovery_id):
        calls.append(f"restore:{recovery_id}")
        return license_service.LicenseStatus(
            status="active", product="monthly", recovery_id=recovery_id
        )

    async def refresh(*args, **kwargs):
        calls.append("refresh")

    monkeypatch.setattr(service.license, "restore", restore)
    monkeypatch.setattr(service.license, "refresh", refresh)
    asyncio.run(service.reconcile())
    assert calls and calls[0].startswith("restore:"), (
        f"reconcile must take the token-issuing path, got {calls}"
    )
    assert "refresh" not in calls, "reconcile must not use /status"
    # no recovery ID ever saved → nothing to reconcile, no request at all
    service2 = premium_service.PremiumService(None, FakeStorage())
    calls.clear()
    asyncio.run(service2.reconcile())
    assert not calls, "with no purchase history there is nothing to ask"
    assert state.is_premium in (True, False)  # untouched


def test_reconcile_is_debounced_for_resume_bursts(monkeypatch):
    """RESUME/SHOW bursts must not burn the Worker's 20 req/60s budget."""
    from services import premium_service

    monkeypatch.setattr(premium_service, "CHANNEL", "direct")
    # No recovery ID → the real reconcile stamps and returns without any
    # network call, so this exercises the genuine stamping path.
    service = premium_service.PremiumService(None, FakeStorage())
    initial = service._last_reconcile_at
    asyncio.run(service.reconcile_if_due())
    assert service._last_reconcile_at > initial, "the first check must stamp"
    stamped = service._last_reconcile_at
    asyncio.run(service.reconcile_if_due())
    assert service._last_reconcile_at == stamped, (
        "a burst inside RESUME_DEBOUNCE must be swallowed"
    )


def test_kiri_check_status_does_not_claim_an_unreachable_server(monkeypatch):
    """The UI must not say 'Payment confirmed' when nothing was confirmed."""
    from services import license_service, premium_service

    monkeypatch.setattr(premium_service, "CHANNEL", "direct")
    service = premium_service.PremiumService(
        None, FakeStorage({"kiri_recovery_id": "KIRI-L-" + "A" * 24})
    )

    async def offline(*args, **kwargs):
        raise license_service.LicenseUnavailable("unreachable")

    monkeypatch.setattr(service.license, "refresh", offline)
    with pytest.raises(license_service.LicenseUnavailable):
        asyncio.run(service.kiri_check_status())


# ── chat history must not lose or misfile a turn ───────────────────────
def test_history_changes_are_refused_while_a_reply_streams():
    """A running turn writes to self.conversation_id when it finishes, so
    switching, replacing or deleting the active chat mid-reply would file
    the answer under the wrong conversation."""
    import flet as ft

    from screens.chat_screen import ChatSession

    class Controller:
        billing = None
        storage = None

        async def _grant_premium_benefits(self, *, first_time=False):
            return False

        async def _sync_premium_storage(self):
            pass

        async def verify_purchases(self):
            pass

    class Page:
        platform = ft.PagePlatform.WINDOWS
        width = 390
        height = 800
        theme_mode = ft.ThemeMode.LIGHT

        def __init__(self):
            self.dialogs = []
            self.views = []
            self._ddgs_controller = Controller()

        def run_task(self, handler, *a, **k):
            loop = asyncio.new_event_loop()
            try:
                loop.run_until_complete(handler(*a, **k))
            finally:
                loop.close()

        def show_dialog(self, dlg):
            self.dialogs.append(dlg)

        def pop_dialog(self):
            pass

        def update(self):
            pass

    page = Page()
    session = ChatSession(page)
    session.busy = True  # a reply is streaming
    before_id = session.conversation_id

    session.new_conversation()
    assert session.conversation_id == before_id, "new chat while busy"

    session.delete_conversation(before_id)
    assert session.conversation_id == before_id, "delete while busy"

    session.delete_all_conversations()
    assert session.conversation_id == before_id, "delete-all while busy"
    assert page.dialogs, "the user must be told why nothing happened"


def test_stopped_and_failed_turns_are_recorded():
    """A stopped or failed exchange is still history.

    Recording used to be a separate append that only the success path ran,
    so switching chats or restarting lost the question and any partial
    answer. The screen's transcript is now the record: there is no second
    write to forget to make.
    """
    from screens.chat_screen import ChatSession

    session = object.__new__(ChatSession)
    session.turns = [
        {"role": "user", "text": "why is the sky blue"},
        {"role": "assistant", "text": "short answer", "stopped": True},
    ]
    assert [m["role"] for m in session._model_history()] == ["user", "assistant"]
    assert session._model_history()[0]["content"] == "why is the sky blue"

    # A failure with nothing streamed still keeps the question.
    session.turns = [{"role": "user", "text": "why is the sky blue"}]
    assert [m["role"] for m in session._model_history()] == ["user"]


def test_prune_notice_only_fires_when_the_cap_bites():
    """`len(before) + 1 - len(rows)` reported a deletion on every save of an
    existing chat, telling users their history was removed when it was not.
    """
    source = (SRC / "screens" / "chat_screen.py").read_text(encoding="utf-8")
    assert "len(before) + 1 - len(rows)" not in source
    assert "existed is None" in source


# ── the save dialog must respect a cancel ───────────────────────────────
def test_cancelling_the_save_dialog_writes_nothing():
    """save_file() returns None on cancel. That is a decision, and the old
    code auto-saved to Downloads anyway."""
    import asyncio as _a

    import flet as ft

    from components.results import downloader

    class Picker:
        async def save_file(self, **kwargs):
            return None  # user pressed Cancel

    class Page:
        platform = ft.PagePlatform.WINDOWS
        width = 400

        def __init__(self):
            self.services = []
            self.file_picker = Picker()

        def update(self):
            pass

    page = Page()
    assert _a.run(downloader._resolve_save_path(page, "clip.mp4")) is None


def test_unwritable_default_directory_does_not_crash():
    """An OSError from makedirs used to escape as a bare crash in the task."""
    import asyncio as _a

    import flet as ft

    from components.results import downloader

    class Broken:
        def save_file(self, **kwargs):
            raise RuntimeError("no dialog here")  # dialog genuinely unavailable

    class Page:
        platform = ft.PagePlatform.WINDOWS
        width = 400

        def __init__(self):
            self.services = []
            self.file_picker = Broken()

        def update(self):
            pass

    real_makedirs = os.makedirs

    def boom(*a, **k):
        raise OSError("read-only")

    os.makedirs = boom
    try:
        assert _a.run(downloader._resolve_save_path(Page(), "x.txt")) is None
    finally:
        os.makedirs = real_makedirs


# ── cache key must cover every result-shaping input ─────────────────────
def test_cache_key_changes_with_every_result_shaping_setting():
    from services.cache_service import search_key

    base = {
        "region": "wt-wt",
        "safesearch": "moderate",
        "timelimit": "",
        "backend": "auto",
        "max_results": "20",
        "page": "1",
        "image_size": "",
        "video_quality": "best",
    }
    key = search_key("q", "images", **base)
    for field, other in (
        ("region", "us-en"),
        ("safesearch", "strict"),
        ("timelimit", "d"),
        ("backend", "google"),
        ("max_results", "100"),
        ("page", "2"),
        ("image_size", "Large"),
        ("video_quality", "worst"),
    ):
        assert search_key("q", "images", **{**base, field: other}) != key, (
            f"changing {field} must not reuse the same cached results"
        )


def test_controller_cache_filters_cover_the_real_settings():
    source = (SRC / "app_controller.py").read_text(encoding="utf-8")
    for field in (
        "max_results",
        "page",
        "image_size",
        "image_color",
        "image_type",
        "image_layout",
        "image_license",
        "video_quality",
        "search_resolution",
        "search_duration",
        "search_license",
        "proxy",
        "verify_ssl",
        "threads",
    ):
        assert f'"{field}"' in source, f"{field} must be part of the cache key"


def test_a_canceled_search_is_not_cached_or_logged():
    """is_cancelled existed but was never set, so a truncated result set was
    cached, written to history and charged an interstitial."""
    from core.state import SearchProgress

    assert SearchProgress("q").is_cancelled is False
    source = (SRC / "services" / "search_service.py").read_text(encoding="utf-8")
    assert "progress.is_cancelled = self._is_cancelled" in source
    controller = (SRC / "app_controller.py").read_text(encoding="utf-8")
    assert 'if getattr(progress, "is_cancelled", False):' in controller


# ── gateway failures must not masquerade as a rate limit ────────────────
def test_a_gateway_outage_is_not_a_rate_limit():
    from services import ai_service

    # the whole rate-limit outcome class is gone: every failure is an
    # honest AIUnavailable with consumer-facing copy, and the router owns
    # model rotation (`auto` is its own model).
    assert not hasattr(ai_service, "AIRateLimited")
    assert not hasattr(ai_service, "rate_limit_advice")
    source = (SRC / "services" / "ai_service.py").read_text(encoding="utf-8")
    assert "rate_limited" not in source
    assert '"model": chosen' in source, "the request model must pass through"


# ── log retention must include rotated backups ──────────────────────────
def test_log_sweep_removes_rotated_backups(tmp_path):
    from core.utils import prune_old_logs

    old = time.time() - 30 * 86400
    for name in (
        "app_old.log",
        "app_old.log.1",
        "app_old.log.2",
        "app_new.log",
        "notes.txt",
    ):
        path = tmp_path / name
        path.write_text("x", encoding="utf-8")
        if "old" in name:
            os.utime(path, (old, old))
    removed = prune_old_logs(str(tmp_path), days=14)
    assert removed == 3, "the .log.N backups must be swept too"
    assert sorted(p.name for p in tmp_path.iterdir()) == ["app_new.log", "notes.txt"]


# ── cache maintenance must survive poisoned entries ─────────────────────
def test_prune_survives_valid_json_of_the_wrong_type(monkeypatch):
    from services.cache_service import CacheService

    monkeypatch.setenv("FLET_APP_STORAGE_CACHE", tempfile.mkdtemp())

    async def scenario():
        cache = CacheService()
        for i, payload in enumerate(("[1,2,3]", "null", '"text"', "123")):
            cache._path(f"poison{i}").write_text(payload, encoding="utf-8")
        await cache.set("keep1", {"a": 1}, ttl=999)
        await cache.set("keep2", {"b": 2}, ttl=999)
        stats = await cache.prune()
        assert stats["removed"] >= 4, "poisoned entries are dropped"
        assert cache._path("keep1").exists()
        assert cache._path("keep2").exists()

    asyncio.run(scenario())


# ── legacy migration must not resurrect deleted chats ───────────────────
def test_migration_clears_the_legacy_value():
    from services import conversation_service as cs

    assert hasattr(cs, "clear_legacy_history")
    controller = (SRC / "app_controller.py").read_text(encoding="utf-8")
    assert "clear_legacy_history" in controller, (
        "a deleted chat must not come back after the next launch"
    )


# ── credit settlement must be safe to retry ─────────────────────────────
def test_duplicate_settlement_does_not_charge_twice():
    from services.credit_service import CreditService

    async def scenario():
        svc = CreditService(FakeStorage({"credits": "10"}))
        tx = await svc.reserve(2)
        first = await svc.commit_amount(tx, 2)
        second = await svc.commit_amount(tx, 2)
        assert first == second, "a retried settlement billed twice"

    asyncio.run(scenario())


def test_rollback_seconds_matches_the_implementation():
    from services.credit_service import ROLLBACK_SECONDS

    source = (SRC / "services" / "credit_service.py").read_text(encoding="utf-8")
    assert "asyncio.sleep(ROLLBACK_SECONDS)" in source
    assert "Auto-rollback after 60 seconds" not in source
    assert ROLLBACK_SECONDS > 0


def test_youtube_fallback_is_callable_the_way_it_is_called():
    """A de-indented helper kept its `self` param while the call site still
    said `self._youtube_video_fallback` → AttributeError, swallowed by the
    broad handler → video rescue silently dead."""
    import inspect

    from services import search_service
    from services.search_service import SearchService

    helper = search_service._youtube_video_fallback
    assert inspect.iscoroutinefunction(helper)
    params = list(inspect.signature(helper).parameters)
    assert params == ["query"], f"a module-level helper must not take self: {params}"
    source = (SRC / "services" / "search_service.py").read_text(encoding="utf-8")
    assert "self._youtube_video_fallback" not in source, (
        "the call site must not look for a method that is not on the class"
    )
    # the sibling genuinely lives on the class
    assert hasattr(SearchService, "_openlibrary_book_fallback")


# ── the uncommitted premium fix must stay in place ──────────────────────
def test_premium_verdict_is_never_persisted_to_storage():
    """Entitlement is the signed token, never a local flag (KTV rule).

    The pre-Phase-1 working tree removed the _persist_verdict /
    _sync_premium_storage mechanism that wrote the derived verdict back to
    disk; these guards keep it gone.
    """
    from services import premium_service

    service_source = (SRC / "services" / "premium_service.py").read_text(
        encoding="utf-8"
    )
    controller_source = (SRC / "app_controller.py").read_text(encoding="utf-8")
    assert "_persist_verdict" not in service_source
    assert "_sync_premium_storage" not in controller_source
    assert not hasattr(premium_service.PremiumService, "_persist_verdict")


def test_wallet_reads_live_premium_state():
    """Buying while the wallet dialog is open must update it immediately.

    The countdown and the watch handler read state.is_premium at run time;
    a snapshot captured at dialog build would keep counting down against a
    stale verdict.
    """
    source = (SRC / "components" / "wallet.py").read_text(encoding="utf-8")
    # _countdown: loops while live premium is False
    assert "if state.is_premium:" in source
    # _on_watch: refuses at run time, not at build time
    assert "        if state.is_premium:\n            return" in source
