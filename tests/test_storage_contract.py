"""The .flet/README storage contract, pinned per consumer.

data/   durable: settings+history, conversations, logs, the staged CA.
cache/  regenerable: search caches and the engine (one download rebuilds
        it); the OS may purge it, so nothing irreplaceable lives here.
temp/   scratch: stray FILES cleared at startup; subdirectories survive
        when temp IS cache (Android: getTemporaryDirectory ==
        getCacheDir), because those subdirs are cache tiers.
"""

from __future__ import annotations

import sys
from pathlib import Path

SRC = Path(__file__).resolve().parents[1] / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))


def test_the_single_resolver_owns_every_ddgs_literal():
    """No module may hand-roll its own .ddgs_ui path: data/, cache/ and
    temp/ resolve in ONE place. storage_service keeps a single reference
    only for its documented legacy migration."""
    allowed = {"storage_paths.py", "storage_service.py"}
    offenders = [
        str(path.relative_to(SRC))
        for path in sorted(SRC.rglob("*.py"))
        if path.name not in allowed and ".ddgs_ui" in path.read_text(encoding="utf-8")
    ]
    assert not offenders, f"hand-rolled storage paths: {offenders}"


def test_settings_resolve_into_data_dir(tmp_path, monkeypatch):
    monkeypatch.setenv("FLET_APP_STORAGE_DATA", str(tmp_path / "data"))
    from services.storage_service import _storage_file

    assert _storage_file() == tmp_path / "data" / "storage.json"


def test_legacy_settings_migrate_once(tmp_path, monkeypatch):
    """Plain-python runs kept settings at ~/.ddgs_ui/storage.json; the
    one-time move keeps them when the resolver moves to data/."""
    monkeypatch.setenv("FLET_APP_STORAGE_DATA", str(tmp_path / "data"))
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: tmp_path))
    legacy_dir = tmp_path / ".ddgs_ui"
    legacy_dir.mkdir()
    legacy = legacy_dir / "storage.json"
    legacy.write_text('{"theme": "dark"}', encoding="utf-8")

    from services.storage_service import _migrate_legacy_storage, _storage_file

    _migrate_legacy_storage()
    assert _storage_file().read_text(encoding="utf-8") == '{"theme": "dark"}'
    assert not legacy.exists()
    # second run must not clobber the migrated file
    _storage_file().write_text('{"theme": "light"}', encoding="utf-8")
    _migrate_legacy_storage()
    assert _storage_file().read_text(encoding="utf-8") == '{"theme": "light"}'


def test_conversations_and_logs_are_data_tier(tmp_path, monkeypatch):
    monkeypatch.setenv("FLET_APP_STORAGE_DATA", str(tmp_path / "data"))
    from core.utils import _log_dir_candidates
    from services.conversation_service import conversations_dir

    assert _log_dir_candidates()[0] == str(tmp_path / "data" / "logs")
    assert conversations_dir().is_relative_to(tmp_path / "data")


def test_engine_and_search_cache_are_cache_tier(tmp_path, monkeypatch):
    monkeypatch.setenv("FLET_APP_STORAGE_CACHE", str(tmp_path / "cache"))
    from services.cache_service import CacheService
    from services.engine import engine_cache_path

    assert engine_cache_path() == tmp_path / "cache" / "engine_local.py"
    assert CacheService().root == tmp_path / "cache" / "ddgs"


def test_clear_temp_spares_cache_tiers_when_temp_is_cache(tmp_path, monkeypatch):
    """Android reality: temp == cache. The startup clear strips stray
    files only - never rmtree the cache tiers living beside them."""
    both = tmp_path / "cache"
    both.mkdir()
    monkeypatch.setenv("FLET_APP_STORAGE_TEMP", str(both))
    monkeypatch.setenv("FLET_APP_STORAGE_CACHE", str(both))
    tier = both / "ddgs"
    tier.mkdir()
    (tier / "results.json").write_text("{}")
    stray = both / "stale.html"
    stray.write_text("x")

    from core.storage_paths import clear_temp

    removed = clear_temp()
    assert removed == 1, "only the stray file may go"
    assert not stray.exists()
    assert (tier / "results.json").exists(), "a cache tier was wiped"


def test_clear_temp_still_cleans_scratch_dirs_on_desktop(tmp_path, monkeypatch):
    monkeypatch.setenv("FLET_APP_STORAGE_TEMP", str(tmp_path / "temp"))
    monkeypatch.setenv("FLET_APP_STORAGE_CACHE", str(tmp_path / "cache"))
    scratch = tmp_path / "temp" / "job"
    scratch.mkdir(parents=True)
    (scratch / "a.bin").write_bytes(b"x")

    from core.storage_paths import clear_temp

    assert clear_temp() == 1
    assert not scratch.exists()
