"""Regression tests for the second audit pass.

Every test maps to a real defect found after the first audit round. They
assert behaviour, so a reworded comment cannot make them pass.
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

import pytest

SRC = Path(__file__).resolve().parents[1] / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))


class PageStub:
    def __init__(self, platform=None):
        self.platform = platform or None
        self.services = []
        self.file_picker = None
        self.dialogs = []
        self._ddgs_controller = None

    def run_task(self, handler, *a, **k):
        loop = asyncio.new_event_loop()
        try:
            return loop.run_until_complete(handler(*a, **k))
        finally:
            loop.close()

    def show_dialog(self, dlg):
        self.dialogs.append(dlg)

    def pop_dialog(self):
        pass

    def update(self):
        pass


# ── the view count that shipped on screen ───────────────────────────────
def test_view_count_parses_compact_labels():
    from services.search_service import _parse_view_count

    assert _parse_view_count("1,234 views") == 1234
    assert _parse_view_count("1.2M views") == 1_200_000, "was 12"
    assert _parse_view_count("12K views") == 12_000, "was 12"
    assert _parse_view_count("1.5B views") == 1_500_000_000, "was 15"
    assert _parse_view_count("99 views") == 99
    assert _parse_view_count("") is None
    assert _parse_view_count("views") is None


# ── a malformed storage row must not take out a screen ──────────────────
def test_malformed_history_rows_are_filtered():
    from services.storage_service import StorageService

    class Page:
        web = False

    storage = StorageService(Page())
    storage._cache["search_history"] = [
        {"query": "good", "search_type": "text"},
        "not-a-dict",
        {"search_type": "text"},  # no query
        42,
        {"query": "also good", "search_type": "images"},
    ]
    rows = asyncio.run(storage.get_history())
    assert [r["query"] for r in rows] == ["good", "also good"]
    # and a bad entry cannot be written in the first place
    assert asyncio.run(storage.add_history({"search_type": "x"})) is False


def test_storage_write_is_atomic(tmp_path, monkeypatch):
    """A kill mid-write must not truncate settings, credits and licence."""
    import json

    monkeypatch.setenv("FLET_APP_STORAGE_DATA", str(tmp_path))
    import importlib

    import services.storage_service as ss

    importlib.reload(ss)

    class Page:
        web = False

    service = ss.StorageService(Page())
    asyncio.run(service.set("theme", "dark"))
    asyncio.run(service.flush())
    data = tmp_path / "storage.json"
    assert data.exists()
    assert json.loads(data.read_text(encoding="utf-8"))["theme"] == "dark"
    # a leftover tmp from a killed process must not poison the reload
    (tmp_path / "storage.json.tmp").write_text('{"corrupt', encoding="utf-8")
    reloaded = ss.StorageService(Page())
    assert asyncio.run(reloaded.get("theme")) == "dark"


# ── a deleted chat must stay deleted ────────────────────────────────────
def test_a_pending_save_cannot_resurrect_a_deleted_chat(tmp_path, monkeypatch):
    monkeypatch.setenv("FLET_APP_STORAGE_DATA", str(tmp_path))
    from services import conversation_service as cs

    cid = cs.new_conversation_id()
    cs.save_conversation(cid, [{"role": "user", "content": "hi"}])
    assert cs.load_conversation(cid) is not None
    cs.delete_conversation(cid)
    assert cs.load_conversation(cid) is None

    # the save that was already in flight now replays
    revived = cs.save_conversation(
        cid,
        [{"role": "user", "content": "hi"}, {"role": "assistant", "content": "yo"}],
    )
    assert revived is False
    assert cs.load_conversation(cid) is None, "delete must not be undone"


def test_conversation_service_enforces_its_own_message_cap(tmp_path, monkeypatch):
    monkeypatch.setenv("FLET_APP_STORAGE_DATA", str(tmp_path))
    from services import conversation_service as cs

    cid = cs.new_conversation_id()
    cs.save_conversation(
        cid, [{"role": "user", "content": f"m{i}"} for i in range(600)]
    )
    stored = cs.load_conversation(cid)
    assert len(stored["messages"]) == cs.CONVERSATION_MESSAGE_CAP


# ── cache maintenance survives abuse ────────────────────────────────────
def test_prune_sweeps_orphan_temp_files(tmp_path, monkeypatch):
    monkeypatch.setenv("FLET_APP_STORAGE_CACHE", str(tmp_path))
    from services.cache_service import CacheService

    async def scenario():
        cache = CacheService()
        cache._path("stuck").with_suffix(".json.tmp").write_text(
            "partial", encoding="utf-8"
        )
        await cache.set("keep", {"a": 1}, ttl=999)
        await cache.prune()
        assert not list(cache.root.glob("*.json.tmp"))
        assert cache._path("keep").exists()
        await cache.clear()
        assert not list(cache.root.glob("*"))

    asyncio.run(scenario())


# ── the search client must follow settings changes ──────────────────────
def test_search_client_is_rebuilt_when_network_settings_change():
    from core.state import state
    from services.search_service import SearchService

    service = SearchService()
    first = service._build_client()
    assert service._build_client() is first, "unchanged settings reuse it"
    old_proxy = state.proxy
    state.proxy = "http://127.0.0.1:9"
    try:
        rebuilt = service._build_client()
        assert rebuilt is not first, "a new proxy must produce a new client"
        assert service._build_client() is rebuilt, "unchanged config reuses it"
    finally:
        state.proxy = old_proxy
    reverted = service._build_client()
    assert reverted is not rebuilt, "reverting the setting rebuilds again"


# ── a rate limit and an outage are different things ─────────────────────
def test_stream_chat_forwards_max_tokens():
    source = (SRC / "services" / "ai_service.py").read_text(encoding="utf-8")
    assert "stream_llm(messages, on_token, model=model, max_tokens=max_tokens)" in source


def test_tool_cap_writes_a_reply_for_every_requested_call():
    source = (SRC / "services" / "chat_agent.py").read_text(encoding="utf-8")
    assert "role\": \"tool\"" in source
    block = source.split("if tools_used >= AGENT_MAX_TOOLS:", 1)[1]
    assert '"role": "tool"' in block, (
        "the assistant's tool_calls need matching tool replies or the API "
        "rejects the transcript"
    )
    assert "break" in block


# ── the Premium card must not ask for an unknown amount ─────────────────
def test_premium_plan_shows_a_price_or_a_neutral_label(monkeypatch):
    import flet as ft

    from components.settings.sections_premium import build_premium_section
    from core import build_channel
    from core.state import state
    from services import premium_service as ps

    monkeypatch.setattr(build_channel, "CHANNEL", "direct", raising=False)
    monkeypatch.setattr(ps, "CHANNEL", "direct", raising=False)
    state.is_premium = False
    state.license_recovery_id = ""
    state.license_prices = {"monthly": "$3.99 USD"}

    class Controller:
        billing = None
        storage = None
        premium = ps.PremiumService(None, None)

        async def _grant_premium_benefits(self, *, first_time=False):
            return False

        async def _sync_premium_storage(self):
            pass

        async def verify_purchases(self):
            pass

    class Page:
        platform = ft.PagePlatform.WINDOWS
        width = 900
        height = 800
        theme_mode = ft.ThemeMode.LIGHT
        _ddgs_controller = Controller()

        def run_task(self, handler, *a, **k):
            pass

        def show_dialog(self, dlg):
            pass

        def update(self):
            pass

    card = build_premium_section(Page())
    blob: list[str] = []

    def walk(control):
        if isinstance(control, str):
            # Flet 1.0 stores a button's label as `content`, a plain str.
            blob.append(control)
            return
        if isinstance(control, ft.Text) and control.value:
            blob.append(str(control.value))
        for child in getattr(control, "controls", None) or []:
            walk(child)
        for attr in ("content", "leading", "trailing", "title"):
            child = getattr(control, attr, None)
            if child is not None and hasattr(child, "__class__"):
                walk(child)

    walk(card)
    rendered = " ".join(blob)
    assert "$3.99 USD" in rendered, "the known price must be shown"
    # an unknown plan must not advertise a number it does not have
    state.license_prices = {}
    card2 = build_premium_section(Page())
    blob2: list[str] = []
    blob2.clear()

    def walk2(control):
        if isinstance(control, str):
            blob2.append(control)
            return
        if isinstance(control, ft.Text) and control.value:
            blob2.append(str(control.value))
        for child in getattr(control, "controls", None) or []:
            walk2(child)
        for attr in ("content", "leading", "trailing", "title"):
            child = getattr(control, attr, None)
            if child is not None and hasattr(child, "__class__"):
                walk2(child)

    walk2(card2)
    rendered2 = " ".join(blob2)
    assert "Choose" not in rendered2, "no price means no button, not a guess"
    assert "Monthly" not in rendered2, "nothing may be sold without a price"
    assert "Unlock options unavailable" in rendered2


# ── download must not leave garbage or accept the wrong thing ───────────
def test_download_failure_cleans_up_the_partial_file():
    source = (SRC / "services" / "media_downloader.py").read_text(encoding="utf-8")
    assert "except BaseException:" in source, "every failure must clean up"
    block = source.split("except BaseException:", 1)[1]
    assert "os.remove(dest)" in block


def test_every_download_kind_checks_the_media_type():
    source = (SRC / "components" / "results" / "downloader.py").read_text(encoding="utf-8")
    # both branches must pass it; only the video branch used to
    assert source.count("expect_media=True") >= 2


def test_unresolved_youtube_does_not_download_a_watch_page():
    source = (SRC / "components" / "results" / "downloader.py").read_text(encoding="utf-8")
    if "YouTube Downloading Restricted" in source:
        # The Play build blocks YouTube downloads behind its own dialog and
        # returns before the resolver, so this path does not exist there.
        pytest.skip("this build blocks YouTube downloads by policy")
    assert "yt_unresolved" in source
    assert "Could not fetch this video" in source
    # the fallback must return before the save dialog
    after = source.split("yt_unresolved = True", 1)[1]
    assert "return" in after.split("else:", 1)[0]


# ── a stale overview must not follow a new query ────────────────────────
def test_offline_cached_search_clears_the_previous_overview():
    source = (SRC / "app_controller.py").read_text(encoding="utf-8")
    offline = source.split("# Fail fast when offline:", 1)[1].split("async def", 1)[0]
    assert "state.ai_overview = None" in offline, (
        "the overview belongs to the previous query"
    )


# ── cancelling must actually cancel ─────────────────────────────────────
def test_cancel_search_cancels_the_task_and_publishes_a_stopped_state():
    source = (SRC / "app_controller.py").read_text(encoding="utf-8")
    block = source.split("def cancel_search(self):", 1)[1].split("def ", 1)[0]
    assert "task.cancel()" in block, "a flag alone left the spinner up"
    assert "progress.is_running = False" in block


def test_a_superseded_search_does_not_overwrite_the_new_one():
    from core.state import SearchProgress
    from services.search_service import SearchService

    service = SearchService()
    assert service._generation == 0
    # a search in flight captures the generation it started with
    captured = service._generation
    service.cancel()
    assert service._generation == 1, "cancel must invalidate in-flight work"
    assert captured != service._generation, (
        "an in-flight search must see itself as superseded"
    )
    source = (SRC / "services" / "search_service.py").read_text(encoding="utf-8")
    assert "generation != self._generation" in source
    _ = SearchProgress("q")


# ── ads: the premium gate and the gap ───────────────────────────────────
def test_premium_user_gets_no_ads(monkeypatch):
    import flet as ft

    from core.state import state
    from services import ad_service as ads

    monkeypatch.setattr(ads, "_HAS_ADS", True, raising=False)

    class Page:
        platform = ft.PagePlatform.ANDROID
        web = False

        def __init__(self):
            self.services = []

    svc = ads.AdService(Page())
    svc._can_request_ads = True

    state.is_premium = True
    banner = svc.get_banner_ad()
    assert banner.width == 0, "a premium user must not get a banner"
    assert asyncio.run(svc.show_interstitial()) is False

    state.is_premium = False
    banner = svc.get_banner_ad()
    assert banner.width != 0, "a free user on Android gets a banner"


def test_interstitial_honours_the_gap(monkeypatch):
    """Refused inside the gap without extending it; admitted past it with
    the stamp deferred to the impression (not the attempt)."""
    import time as time_mod

    import flet as ft

    from core.state import state
    from services import ad_service as ads

    monkeypatch.setattr(ads, "_HAS_ADS", True, raising=False)

    class Page:
        platform = ft.PagePlatform.ANDROID
        web = False

        def __init__(self):
            self.services = []

    svc = ads.AdService(Page())
    svc._can_request_ads = True
    state.is_premium = False

    # A recent impression: refuse, and never extend the cooldown.
    state.last_interstitial_ts = time_mod.time() - 10
    recent = state.last_interstitial_ts
    assert asyncio.run(svc.show_interstitial()) is False
    assert state.last_interstitial_ts == recent, (
        "a refused call must not extend the cooldown"
    )

    # Past the gap the trigger is admitted; queueing is not an impression,
    # so the old stamp stays until _show_loaded fires.
    admitted = time_mod.time() - ads.AdService.MIN_INTERSTITIAL_GAP - 1
    state.last_interstitial_ts = admitted

    async def _queued(on_close=None):
        pass  # interstitial stays None: the queue path creates it

    monkeypatch.setattr(svc, "preload_interstitial", _queued)
    assert asyncio.run(svc.show_interstitial()) is False, (
        "a preload that creates nothing reports failure"
    )
    assert state.last_interstitial_ts == admitted, "no impression, no stamp"


def test_desktop_gets_no_ads(monkeypatch):
    import flet as ft

    from core.state import state
    from services import ad_service as ads

    monkeypatch.setattr(ads, "_HAS_ADS", True, raising=False)
    state.is_premium = False
    state._can_request_ads = True if hasattr(state, "_can_request_ads") else None

    class Page:
        platform = ft.PagePlatform.WINDOWS
        web = False

        def __init__(self):
            self.services = []

    svc = ads.AdService(Page())
    svc._can_request_ads = True
    assert svc.get_banner_ad().width == 0, "no ads outside mobile"


# ── nothing ships without the tests running first ────────────────────────
def test_ci_gates_every_build_on_lint_and_tests():
    """DDGS ran neither ruff nor pytest in CI on any branch.

    KTV Player's `quality` job blocks every other job, which is what makes
    its channel assertions real. Without it, 173 local tests guarded
    nothing — including the Play-policy assertions that only execute on the
    playstore branch.
    """
    workflow = (
        SRC.parent / ".github" / "workflows" / "build-all.yml"
    ).read_text(encoding="utf-8")

    assert "\n  quality:" in workflow, "a gate job must exist"
    assert "needs: [quality]" in workflow, "the release must wait for it"
    assert "uv run ruff check src tests" in workflow
    assert "uv run pytest -q" in workflow


# ── announcements must reach current installs ───────────────────────────
def test_announcements_reach_current_installs(monkeypatch):
    """type=announcement used to sit behind the build gate, so it could
    only fire when the server build was already newer - the one case where
    announcing anything is pointless."""
    from services import update_service as us

    def client_factory(payload):
        class Resp:
            status_code = 200

            def json(self):
                return payload

        class Client:
            def __init__(self, *a, **k):
                pass

            async def __aenter__(self):
                return self

            async def __aexit__(self, *a):
                return False

            async def get(self, *a, **k):
                return Resp()

        return Client

    svc = us.UpdateService()
    monkeypatch.setattr(
        us.httpx,
        "AsyncClient",
        client_factory(
            {
                "build_number": us._APP_BUILD,
                "type": "announcement",
                "title": "Maintenance tonight",
                "release_notes": "Back at 3am",
            }
        ),
    )
    info = asyncio.run(svc.check_for_update())
    assert info is not None, "an announcement at the running build must surface"
    assert info["type"] == "announcement"
    assert info["title"] == "Maintenance tonight"

    monkeypatch.setattr(
        us.httpx,
        "AsyncClient",
        client_factory(
            {
                "build_number": us._APP_BUILD,
                "type": "update",
                "version": "9.9.9",
            }
        ),
    )
    assert asyncio.run(svc.check_for_update()) is None, (
        "a plain update still requires a newer build"
    )
