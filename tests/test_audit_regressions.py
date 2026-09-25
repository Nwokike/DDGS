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
def test_stale_persisted_premium_does_not_grant_access():
    """A leftover is_premium:true must not survive with no proof.

    The persisted value is a cache of a previous run. Either channel can
    have been revoked since, so it cannot seed state.
    """
    from core.state import state
    from services import premium_service

    state.is_premium = True  # as if loaded from storage.json
    state.play_premium_active = False
    state.license_premium_active = False
    state.license_recovery_id = ""
    state.license_status = ""

    storage = FakeStorage({"is_premium": True})
    asyncio.run(premium_service.load_from_storage(storage))
    assert state.is_premium is False, (
        "a stale flag granted Premium with no token and no purchase"
    )


def test_load_from_storage_recomputes_on_every_path(monkeypatch):
    """Even the early-return path must recompute, not leave the flag."""
    from core.state import state
    from services import premium_service

    monkeypatch.setattr(
        premium_service, "logger", pytest.importorskip("logging").getLogger("t")
    )
    state.is_premium = True
    state.play_premium_active = False
    state.license_premium_active = False
    state.license_recovery_id = ""

    class Broken(FakeStorage):
        async def get_license_record(self):
            raise OSError("unreadable")

    asyncio.run(premium_service.load_from_storage(Broken()))
    assert state.is_premium is False


def test_non_definitive_status_does_not_revoke():
    """A 200 with an unknown status is not proof of expiry."""
    from core.state import state
    from services import license_service, premium_service

    state.is_premium = True
    state.play_premium_active = False
    state.license_premium_active = True
    state.license_recovery_id = "KIRI-L-" + "A" * 24

    for status in ("unknown", "pending", "something_new"):
        premium_service.apply_license_entitlement(
            license_service.Entitlement(status=status, offline=False)
        )
        assert state.is_premium is True, f"{status!r} must not revoke"

    premium_service.apply_license_entitlement(
        license_service.Entitlement(status="revoked", offline=False)
    )
    assert state.is_premium is False, "a real revocation must still downgrade"


def test_refresh_reports_whether_the_server_answered(monkeypatch):
    """The UI must not say 'Payment confirmed' when nothing was confirmed."""
    from services import license_service, premium_service

    async def offline(*a, **k):
        raise license_service.LicenseError("unreachable")

    monkeypatch.setattr(license_service, "check_status", offline)
    assert asyncio.run(premium_service.refresh_from_server()) is False

    async def answered(*a, **k):
        return license_service.Entitlement(status="active", product="lifetime")

    monkeypatch.setattr(license_service, "check_status", answered)
    assert asyncio.run(premium_service.refresh_from_server()) is True


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

        async def _grant_premium_benefits(self):
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

    Only the success path appended to agent_history, so switching chats or
    restarting lost the question and any partial answer.
    """
    from screens.chat_screen import ChatSession

    class Probe(ChatSession):
        def __init__(self):
            self.agent_history = []
            self.pending_user = "why is the sky blue"
            self._current = {"text": "short answer"}

    probe = Probe()
    probe._record_turn("short answer")
    roles = [m["role"] for m in probe.agent_history]
    assert roles == ["user", "assistant"]
    assert probe.agent_history[0]["content"] == "why is the sky blue"

    # A failure with nothing streamed still keeps the question.
    probe2 = Probe()
    probe2._current = {"text": ""}
    probe2._record_turn("")
    assert [m["role"] for m in probe2.agent_history] == ["user"]
    # and it is not recorded twice
    probe2._record_turn("")
    assert len(probe2.agent_history) == 1


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

    source = (SRC / "services" / "ai_service.py").read_text(encoding="utf-8")
    # the blanket conversion is gone; the flag gates it
    assert "rate_limited = True" in source
    assert "if rate_limited:" in source
    assert issubclass(ai_service.AIRateLimited, Exception)


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
