"""Core package bootstrap.

Runs before any kani/tiktoken import (main and app_shell reach core
first): pin a per-install tiktoken BPE cache so encoding downloads happen
once and survive restarts, instead of re-downloading into %TEMP% on every
launch - and blocking the UI thread on a cold cache, which is exactly
the failure this pin exists to prevent.

Path policy comes from the single resolver (core.storage_paths); this
module must never hand-roll storage locations.
"""

import os


def _pin_tiktoken_cache() -> None:
    if os.environ.get("TIKTOKEN_CACHE_DIR") or os.environ.get("DATA_GYM_CACHE_DIR"):
        return
    from core.storage_paths import cache_dir

    try:
        path = cache_dir() / "tiktoken_cache"
        path.mkdir(parents=True, exist_ok=True)
    except OSError:
        # Read-only dir: tiktoken falls back to its temp cache.
        return
    os.environ["TIKTOKEN_CACHE_DIR"] = str(path)


_pin_tiktoken_cache()
