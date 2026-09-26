"""Tests for the Flet storage layout, the cache, and chat history.

These cover the behaviour the plan committed to, not just imports:
cache TTL and the size cap, the 50-chat limit and its oldest-first
direction, per-chat delete, legacy migration, and the router status ladder
the model picker shows.
"""

from __future__ import annotations

import asyncio
import os
import sys
import time
from pathlib import Path

import pytest

SRC = Path(__file__).resolve().parents[1] / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))


@pytest.fixture(autouse=True)
def _isolated_storage(tmp_path, monkeypatch):
    """Point all three Flet storage locations at a temp dir per test."""
    monkeypatch.setenv("FLET_APP_STORAGE_DATA", str(tmp_path / "data"))
    monkeypatch.setenv("FLET_APP_STORAGE_CACHE", str(tmp_path / "cache"))
    monkeypatch.setenv("FLET_APP_STORAGE_TEMP", str(tmp_path / "temp"))
    # storage_paths resolves the env var on every call, so a fresh
    # monkeypatched value is picked up without reimporting anything.
    yield


def run(coro):
    return asyncio.run(coro)


# ── storage paths ────────────────────────────────────────────────────────
def test_three_storage_locations_resolve(tmp_path, monkeypatch):
    from core.storage_paths import cache_dir, data_dir, temp_dir

    monkeypatch.setenv("FLET_APP_STORAGE_DATA", str(tmp_path / "d"))
    monkeypatch.setenv("FLET_APP_STORAGE_CACHE", str(tmp_path / "c"))
    monkeypatch.setenv("FLET_APP_STORAGE_TEMP", str(tmp_path / "t"))
    assert data_dir() == tmp_path / "d"
    assert cache_dir() == tmp_path / "c"
    assert temp_dir() == tmp_path / "t"
    assert cache_dir().is_dir() and temp_dir().is_dir()


def test_clear_temp_empties_scratch_space(tmp_path, monkeypatch):
    from core.storage_paths import clear_temp, temp_dir

    monkeypatch.setenv("FLET_APP_STORAGE_TEMP", str(tmp_path / "t"))
    (temp_dir() / "scratch.bin").write_text("x", encoding="utf-8")
    (temp_dir() / "sub").mkdir(exist_ok=True)
    (temp_dir() / "sub" / "deep.bin").write_text("y", encoding="utf-8")
    assert clear_temp() == 2
    assert list(temp_dir().iterdir()) == []


# ── cache ────────────────────────────────────────────────────────────────
def test_search_key_is_stable_and_filter_sensitive():
    from services.cache_service import search_key

    a = search_key("Nwokike", "text", region="wt-wt", safesearch="moderate")
    b = search_key("  nwokike ", "text", region="wt-wt", safesearch="moderate")
    c = search_key("Nwokike", "text", region="us-en", safesearch="moderate")
    assert a == b, "case and surrounding space must not fork the cache"
    assert a != c, "a different region must not reuse another region results"


def test_cache_roundtrip_ttl_and_corruption():
    from services.cache_service import CacheService

    async def scenario():
        cache = CacheService()
        assert await cache.get_search("missing") is None
        await cache.put_search("k1", [{"url": "u", "title": "t"}])
        assert (await cache.get_search("k1"))[0]["title"] == "t"

        # expired entries are a miss and are removed
        await cache.set("gone", {"x": 1}, ttl=-1)
        assert await cache.get("gone") is None

        # a hand-edited/corrupt file must not break a search
        cache._path("bad").write_text("{not json", encoding="utf-8")
        assert await cache.get("bad") is None
        assert not cache._path("bad").exists()

    run(scenario())


def test_page_cache_is_scoped_by_format():
    from services.cache_service import CacheService

    async def scenario():
        cache = CacheService()
        await cache.put_page("https://x.test", "text_markdown", "markdown body")
        await cache.put_page("https://x.test", "html", "<html>")
        assert await cache.get_page("https://x.test", "text_markdown") == "markdown body"
        assert await cache.get_page("https://x.test", "html") == "<html>"

    run(scenario())


def test_prune_drops_expired_then_oldest_to_cap():
    from services.cache_service import CacheService

    async def scenario():
        cache = CacheService()
        for i in range(6):
            await cache.set(f"k{i}", {"pad": "x" * 400}, ttl=999)
        # age them so mtime ordering is unambiguous
        files = sorted(cache.root.glob("*.json"))
        for path in files:
            import os

            os.utime(path, (time.time() - 10_000, time.time() - 10_000))
        await cache.set("fresh", {"pad": "y" * 10}, ttl=999)
        stats = await cache.prune(max_bytes=900)
        assert stats["removed"] > 0
        assert cache.stats()["bytes"] <= 900
        assert cache._path("fresh").exists(), "the newest entry must survive"

    run(scenario())


def test_cached_search_returns_searchresult_objects():
    from core.state import SearchResult
    from services.cache_service import CacheService

    async def scenario():
        cache = CacheService()
        results = [
            SearchResult(title="One", url="https://a", snippet="s"),
            SearchResult(title="Two", url="https://b", snippet="s"),
        ]
        await cache.store_search("q", "text", results, region="wt-wt")
        back = cache.get_cached_search("q", "text", region="wt-wt")
        assert back is not None
        assert [r.title for r in back] == ["One", "Two"]
        assert all(isinstance(r, SearchResult) for r in back)
        # a different region must miss rather than return the wrong list
        assert cache.get_cached_search("q", "text", region="us-en") is None

    run(scenario())


# ── conversations ────────────────────────────────────────────────────────
def test_conversation_roundtrip_and_title():
    from services import conversation_service as cs

    cid = cs.new_conversation_id()
    ok = cs.save_conversation(
        cid,
        [
            {"role": "user", "content": "What is a router?"},
            {"role": "assistant", "content": "A local model server."},
        ],
    )
    assert ok
    loaded = cs.load_conversation(cid)
    assert loaded is not None
    assert loaded["title"].startswith("What is a router?")
    assert len(loaded["messages"]) == 2


def test_empty_conversation_is_not_kept():
    from services import conversation_service as cs

    cid = cs.new_conversation_id()
    cs.save_conversation(cid, [{"role": "user", "content": "hi"}])
    assert cs.load_conversation(cid) is not None
    cs.save_conversation(cid, [])
    assert cs.load_conversation(cid) is None, "an empty chat is not history"


def test_conversation_cap_is_fifty_and_prunes_oldest_first():
    from core.state import state
    from services import conversation_service as cs

    state.active_conversation = ""
    ids = []
    for i in range(55):
        cid = cs.new_conversation_id()
        cs.save_conversation(cid, [{"role": "user", "content": f"q{i}"}])
        ids.append(cid)
    rows = cs.list_conversations()
    assert len(rows) == cs.MAX_CONVERSATIONS == 50
    # The newest conversation must never be the one that gets pruned.
    assert cs.load_conversation(ids[-1]) is not None
    # The oldest ones are the ones that go.
    assert cs.load_conversation(ids[0]) is None


def test_active_conversation_is_never_pruned():
    from core.state import state
    from services import conversation_service as cs

    keeper = cs.new_conversation_id()
    state.active_conversation = keeper
    cs.save_conversation(keeper, [{"role": "user", "content": "keep me"}])
    for i in range(55):
        cs.save_conversation(
            cs.new_conversation_id(), [{"role": "user", "content": f"q{i}"}]
        )
    assert cs.load_conversation(keeper) is not None
    state.active_conversation = ""


def test_delete_and_delete_all_report_outcomes():
    from services import conversation_service as cs

    a = cs.new_conversation_id()
    b = cs.new_conversation_id()
    cs.save_conversation(a, [{"role": "user", "content": "a"}])
    cs.save_conversation(b, [{"role": "user", "content": "b"}])
    assert cs.delete_conversation(a) is True
    assert cs.load_conversation(a) is None
    # deleting something already gone still satisfies the user's intent
    assert cs.delete_conversation(a) is True
    deleted, failed = cs.delete_all()
    assert failed == 0
    assert deleted >= 1
    assert cs.list_conversations() == []


def test_legacy_history_migration_keeps_the_conversation():
    from services import conversation_service as cs

    cid = cs.migrate_legacy_history(
        [
            {"role": "user", "content": "Hello"},
            {"role": "assistant", "content": "Hi there"},
        ]
    )
    assert cid is not None
    loaded = cs.load_conversation(cid)
    assert loaded is not None
    assert len(loaded["messages"]) == 2
    assert cs.migrate_legacy_history([]) is None


def test_turns_rebuild_from_saved_messages():
    from screens.chat_screen import _turns_from_messages

    turns = _turns_from_messages(
        [
            {"role": "user", "content": "q"},
            {"role": "assistant", "content": "a"},
            {"role": "user", "content": "   "},  # blank is dropped
        ]
    )
    assert [t["role"] for t in turns] == ["user", "assistant"]
    assert turns[1]["partial"] is False
    assert turns[1]["cards"] == []


def test_relative_time_reads_naturally():
    from services.conversation_service import relative_time

    now = time.time()
    assert relative_time(now) == "just now"
    assert relative_time(now - 300) == "5m ago"
    assert relative_time(now - 7200) == "2h ago"
    assert relative_time(now - 3 * 86400) == "3d ago"


# ── model picker status ladder ───────────────────────────────────────────
@pytest.mark.parametrize(
    "status,fetched,selected,expected,spinner",
    [
        # Still coming up: say so, and show progress.
        ("starting", False, "auto", "Starting router...", True),
        # Ready but the catalog has not arrived yet: still a wait.
        ("ready", False, "", "Loading models...", True),
        # Ready, fetched, and genuinely nothing to choose from: that is an
        # answer, not a wait, so it must not spin forever.
        ("ready", True, "", "Offline", False),
        ("stopped", True, "auto", "Offline", False),
        ("unavailable", True, "auto", "Offline", False),
    ],
)
def test_picker_label_per_router_state(status, fetched, selected, expected, spinner):
    from components.model_picker import model_picker_state
    from core.state import state
    from services import ai_service

    state.ai_router_status = status
    state.ai_model = selected
    ai_service._catalog = []
    ai_service._catalog_at = time.time()
    ai_service._catalog_fetched_at = time.monotonic() if fetched else 0.0
    ps = model_picker_state()
    assert ps.label == expected
    assert ps.discovering is spinner


def test_picker_shows_the_selected_model_when_present():
    from components.model_picker import model_picker_state
    from core.state import state
    from services import ai_service

    catalog = [
        {"id": "auto", "hint": "rotates", "status": "active"},
        {"id": "ling-3.0-flash", "hint": "210ms", "status": "active"},
    ]
    state.ai_router_status = "ready"
    state.ai_model = "ling-3.0-flash"
    ai_service._catalog = list(catalog)
    ai_service._catalog_at = time.time()
    ai_service._catalog_fetched_at = time.monotonic()
    ps = model_picker_state()
    assert ps.label == "ling-3.0-flash"
    assert ps.active is True


def test_picker_does_not_claim_a_model_missing_from_the_catalog():
    from components.model_picker import model_picker_state
    from core.state import state
    from services import ai_service

    state.ai_router_status = "ready"
    state.ai_model = "a-model-we-no-longer-have"
    ai_service._catalog = [{"id": "auto", "hint": "rotates", "status": "active"}]
    ai_service._catalog_at = time.time()
    ai_service._catalog_fetched_at = time.monotonic()
    ps = model_picker_state()
    assert ps.active is False
    assert ps.label == "Offline"


def test_picker_offers_an_action_when_the_router_is_down():
    from components.model_picker import model_picker_state
    from core.state import state
    from services import ai_service

    state.ai_router_status = "stopped"
    state.ai_model = "auto"
    ai_service._catalog = []
    ps = model_picker_state()
    assert ps.action == "Start router"
    assert ps.message


# ── log retention ────────────────────────────────────────────────────────
def test_log_prune_removes_only_old_files(tmp_path):
    from core.utils import prune_old_logs

    old = tmp_path / "app_old.log"
    new = tmp_path / "app_new.log"
    other = tmp_path / "notes.txt"
    for path in (old, new, other):
        path.write_text("x", encoding="utf-8")
    import os

    old_time = time.time() - 30 * 86400
    os.utime(old, (old_time, old_time))
    assert prune_old_logs(str(tmp_path), days=14) == 1
    assert not old.exists()
    assert new.exists()
    assert other.exists()


def test_storage_json_still_roundtrips_unchanged(tmp_path, monkeypatch):
    """The existing settings store must keep working alongside the new dirs.

    storage_service resolves FLET_APP_STORAGE_DATA at import time (it has
    done so since before this feature), so the env var has to be set in a
    subprocess rather than via monkeypatch after the module is loaded.
    """
    import subprocess
    import sys as _sys

    data_dir = tmp_path / "data"
    script = (
        "import asyncio, json, sys\n"
        f"sys.path.insert(0, {str(SRC)!r})\n"
        "from services.storage_service import StorageService\n"
        "class Page: web = False\n"
        "svc = StorageService(Page())\n"
        "assert asyncio.run(svc.set('theme', 'dark')) is True\n"
        "assert asyncio.run(svc.get('theme')) == 'dark'\n"
        # writes are debounced by design; force one so the file is on disk
        "svc.flush_now()\n"
        f"data = json.loads(open({str(data_dir / 'storage.json')!r}, encoding='utf-8').read())\n"
        "assert data['theme'] == 'dark'\n"
        "print('ok')\n"
    )
    env = {
        **dict(os.environ),
        "FLET_APP_STORAGE_DATA": str(data_dir),
    }
    proc = subprocess.run(
        [_sys.executable, "-c", script],
        capture_output=True,
        text=True,
        env=env,
        timeout=120,
        check=False,
    )
    assert proc.returncode == 0, proc.stderr
    assert "ok" in proc.stdout
    assert (data_dir / "storage.json").exists()
