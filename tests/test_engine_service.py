"""Engine live-fetch spec (LM Router parity).

Owner directive: run.py is never hardcoded. It is fetched from
router.kiri.ng on every cold start, validated, imported, and only then
allowed to replace the last-known-good cache. These tests pin all three
rules: no bundled engine, the anti-brick chain, and the honest terminal
error.
"""

from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

from services import engine as engine_mod
from services.engine import EngineUnavailable, load_engine

SRC = Path(__file__).resolve().parents[1] / "src"

GOOD_ENGINE = b'''#!/usr/bin/env python3
"""Fake but contract-complete engine."""

VERSION = "9.9.9"

def acquire_server(want, span=10):
    return ("fake-server", want)

if __name__ == "__main__":
    pass
'''

# Passes _validate (main guard + VERSION) but blows up on import: the
# stage where a naive implementation used to overwrite the good cache.
UNIMPORTABLE_ENGINE = b'''VERSION = "1.2.3"
def acquire_server( :
if __name__ == "__main__":
'''

# Imports cleanly but lacks the one contract ensure_router calls.
NO_CONTRACT_ENGINE = b'''VERSION = "1.0.0"
x = 1
if __name__ == "__main__":
'''


def _cache_at(tmp_path: Path, monkeypatch) -> Path:
    cache = tmp_path / "engine_local.py"
    monkeypatch.setattr(engine_mod, "engine_cache_path", lambda: cache)
    return cache


async def _offline(url: str) -> bytes:
    raise ConnectionError("offline")


def test_fresh_fetch_replaces_cache_and_reports_fetched(tmp_path, monkeypatch):
    cache = _cache_at(tmp_path, monkeypatch)

    async def good(url: str) -> bytes:
        return GOOD_ENGINE

    monkeypatch.setattr(engine_mod, "_download", good)
    module, how = asyncio.run(load_engine())
    assert how == "fetched 9.9.9"
    assert callable(module.acquire_server)
    assert cache.read_bytes() == GOOD_ENGINE


def test_fetch_failure_falls_back_to_cache(tmp_path, monkeypatch):
    cache = _cache_at(tmp_path, monkeypatch)
    cache.write_bytes(GOOD_ENGINE)
    monkeypatch.setattr(engine_mod, "_download", _offline)
    module, how = asyncio.run(load_engine())
    assert how == "cached 9.9.9"
    assert callable(module.acquire_server)


def test_unimportable_download_cannot_brick_the_cache(tmp_path, monkeypatch):
    cache = _cache_at(tmp_path, monkeypatch)
    cache.write_bytes(GOOD_ENGINE)

    async def bad(url: str) -> bytes:
        return UNIMPORTABLE_ENGINE

    monkeypatch.setattr(engine_mod, "_download", bad)
    _module, how = asyncio.run(load_engine())
    # Falls through to the untouched last-known-good copy.
    assert how == "cached 9.9.9"
    assert cache.read_bytes() == GOOD_ENGINE
    assert not (tmp_path / "engine_local.new.py").exists()


def test_loadable_engine_without_acquire_server_is_rejected(tmp_path, monkeypatch):
    cache = _cache_at(tmp_path, monkeypatch)
    cache.write_bytes(GOOD_ENGINE)

    async def wrong(url: str) -> bytes:
        return NO_CONTRACT_ENGINE

    monkeypatch.setattr(engine_mod, "_download", wrong)
    _module, how = asyncio.run(load_engine())
    assert how == "cached 9.9.9"
    # The wrong-but-loadable download must not have replaced the cache.
    assert cache.read_bytes() == GOOD_ENGINE


def test_both_tiers_down_raises_honest_error(tmp_path, monkeypatch):
    _cache_at(tmp_path, monkeypatch)  # empty cache dir
    monkeypatch.setattr(engine_mod, "_download", _offline)
    with pytest.raises(EngineUnavailable) as excinfo:
        asyncio.run(load_engine())
    assert "Connect to the internet" in str(excinfo.value)
    assert engine_mod.ENGINE_URL in str(excinfo.value)


def test_validate_rejects_structural_garbage():
    with pytest.raises(ValueError, match="main guard"):
        engine_mod._validate(b"print('hello')")


def test_engine_url_is_the_single_constant():
    # The one allowed constant: where to fetch from. The engine itself
    # must never be baked into the app.
    assert engine_mod.ENGINE_URL == "https://router.kiri.ng/run.py"


def test_no_bundled_engine_is_shipped():
    """The router is never vendored: upstream changes constantly."""
    assert not (SRC / "services" / "router").exists()
    ai_src = (SRC / "services" / "ai_service.py").read_text(encoding="utf-8")
    assert "from services.router" not in ai_src
