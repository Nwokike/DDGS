"""Gateway engine: run.py fetched live from router.kiri.ng, never vendored.

Owner directive: upstream changes constantly, so a
bundled snapshot would silently shadow it. Every cold start fetches
ENGINE_URL fresh, validates it, imports it, and only then replaces the
last-known-good cache; a broken download can never brick offline starts.
When both tiers fail the caller reports "unavailable" honestly -
there is no fallback source anymore (owner: router only).

The only constant is where to fetch from (ENGINE_URL); what must
never be hardcoded is the engine itself.
"""

from __future__ import annotations

import asyncio
import contextlib
import importlib.util
import logging
import os
import re
from pathlib import Path

import httpx

from components.settings.version import _APP_VERSION
from core.constants import ENGINE_URL
from core.storage_paths import cache_dir
from services.net_clients import httpx_proxy

logger = logging.getLogger(__name__)

MODULE_NAME = "ddgs_engine"
VERSION_RE = re.compile(rb'VERSION = "([^"]+)"')
USER_AGENT = f"DDGSApp/{_APP_VERSION}"


class EngineUnavailable(RuntimeError):
    """Live fetch failed and no cached engine exists."""


def engine_cache_path() -> Path:
    """Last-known-good engine, in CACHE tier (not the repo).

    .flet/README: cache is for things that can be rebuilt, and this file
    is exactly that - one download rebuilds it. clear_temp spares it by
    name, and if the OS purges the dir the next start simply re-fetches.
    """
    return cache_dir() / "engine_local.py"


async def _download(url: str) -> bytes:
    # router.kiri.ng answers 403 to default library user-agents, so the
    # app could never fetch
    # its own engine without this header. One bounded retry: a transient
    # blip must not fall through to the cache tier.
    last: Exception | None = None
    for attempt in range(2):
        try:
            async with httpx.AsyncClient(http2=False, proxy=httpx_proxy()) as client:
                resp = await client.get(
                    url,
                    headers={"User-Agent": USER_AGENT},
                    timeout=30.0,
                    follow_redirects=True,
                )
                resp.raise_for_status()
                return resp.content
        except Exception as exc:
            last = exc
            if attempt == 0:
                logger.warning("engine download failed (%s); retrying once", exc)
                await asyncio.sleep(1.0)
    raise last  # type: ignore[misc]


def _validate(data: bytes) -> str:
    """Structural check of a downloaded engine + its VERSION label.

    The label is only ever displayed ("fetched 1.0.0"), never compared, so
    a local normalisation is enough and no version library is needed.
    """
    if b'if __name__ == "__main__":' not in data:
        raise ValueError("missing main guard")
    match = VERSION_RE.search(data)
    if not match:
        raise ValueError("missing VERSION token")
    raw = match.group(1).decode("ascii", errors="replace").strip()
    if not raw:
        raise ValueError("empty VERSION token")
    # Keep only what is safe to print in a status label.
    label = re.sub(r"[^A-Za-z0-9.+_-]", "", raw)[:40]
    if not label:
        raise ValueError(f"unusable VERSION token: {raw!r}")
    return label


def _load_module(path: Path) -> object:
    spec = importlib.util.spec_from_file_location(MODULE_NAME, path)
    if spec is None or spec.loader is None:
        raise ImportError(f"cannot load engine from {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    if not callable(getattr(module, "acquire_server", None)):
        # The one contract ensure_router depends on. Checked before the
        # cache replace too, so a loadable-but-wrong engine cannot
        # overwrite the last-known-good copy.
        raise TypeError(f"engine at {path} has no acquire_server()")
    return module


async def load_engine() -> tuple[object, str]:
    """Live download first, then the last-known-good runtime cache.

    Returns (module, "fetched <version>" | "cached <version>").
    """
    cache = engine_cache_path()
    # The file MUST end in .py: spec_from_file_location returns None (no
    # loader) for unrecognized suffixes, which would reject a perfect
    # download.
    tmp = cache.with_name(cache.stem + ".new.py")
    try:
        data = await _download(ENGINE_URL)
        version = _validate(data)
        cache.parent.mkdir(parents=True, exist_ok=True)
        # Prove the download BEFORE touching the cache: a bad upstream that
        # passes _validate (main guard + VERSION) must not overwrite the
        # good copy and then fail to import. Only a loadable download with
        # the acquire_server contract replaces the last-known-good file.
        tmp.write_bytes(data)
        module = _load_module(tmp)
        os.replace(tmp, cache)
        return module, f"fetched {version}"
    except Exception as exc:
        logger.warning("engine download unusable (%s); trying last cached copy", exc)
        with contextlib.suppress(OSError):
            tmp.unlink(missing_ok=True)
    try:
        data = cache.read_bytes()
        version = _validate(data)
        return _load_module(cache), f"cached {version}"
    except Exception as exc:
        raise EngineUnavailable(
            f"Could not reach {ENGINE_URL} and no cached engine is "
            f"available ({exc}). Connect to the internet and retry.",
        ) from exc
