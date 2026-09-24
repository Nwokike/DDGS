"""On-disk cache for search results and fetched pages.

Backed by Flet's cache directory (`FLET_APP_STORAGE_CACHE`, documented in
`.flet/README.md`): regenerable data the OS may purge under pressure, so
every entry here can be rebuilt by running the search again. Durable user
state never goes in this directory.

Design notes:
  - one JSON file per entry, named by a content key, so a prune never has
    to read the whole cache and a corrupt file only costs one entry
  - atomic writes (`.tmp` + `replace`) because the app can be killed
    mid-write on mobile
  - every entry carries `expires_at`; expired entries are treated as
    misses and deleted on read
  - `prune()` drops expired entries, then oldest-first until the directory
    is back under MAX_BYTES
  - a poisoned or hand-edited file must never break a search, so reads
    swallow decode errors and report a miss
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import time
from pathlib import Path
from typing import Any

from core.storage_paths import cache_dir

logger = logging.getLogger(__name__)

# 30 minutes: long enough that re-running a recent search is instant,
# short enough that "what's happening now" answers stay current.
SEARCH_TTL_SEC = 30 * 60
# 24 hours: a fetched page is stable content, and this is what makes a
# result openable with no connection at all.
PAGE_TTL_SEC = 24 * 60 * 60
# 64 MB cap. Search entries are a few KB; a page can be large, so the cap
# is what actually bounds this directory.
MAX_BYTES = 64 * 1024 * 1024
SCHEMA = 1


def search_key(
    query: str,
    search_type: str,
    *,
    region: str = "",
    safesearch: str = "",
    timelimit: str = "",
    backend: str = "",
) -> str:
    """Stable content key for one search.

    Every input that changes the result set is folded in, so changing the
    region or the engine can never serve a stale list from another
    configuration.
    """
    raw = "\x1f".join(
        [
            str(search_type),
            str(query).strip().lower(),
            str(region),
            str(safesearch),
            str(timelimit),
            str(backend),
        ]
    )
    return "s_" + hashlib.sha1(raw.encode("utf-8")).hexdigest()


def page_key(url: str, fmt: str = "") -> str:
    raw = f"{str(url).strip()}\x1f{fmt!s}"
    return "p_" + hashlib.sha1(raw.encode("utf-8")).hexdigest()


# Fields worth caching. `raw_data` is dropped: it is the unfiltered engine
# payload and dwarfs the useful fields, which would make the 64 MB cap fire
# on a handful of searches.
_RESULT_FIELDS = (
    "title",
    "url",
    "snippet",
    "search_type",
    "thumbnail",
    "image_url",
    "width",
    "height",
    "source",
    "duration",
    "embed_url",
    "publisher",
    "views",
    "published",
    "date",
)


def _result_to_dict(result: Any) -> dict:
    return {
        name: getattr(result, name, None)
        for name in _RESULT_FIELDS
        if getattr(result, name, None) is not None
    }


class CacheService:
    """Async-safe cache with TTL, atomic writes and a size cap."""

    def __init__(self) -> None:
        self._lock = asyncio.Lock()
        self._root: Path | None = None

    @property
    def root(self) -> Path:
        if self._root is None:
            self._root = cache_dir() / "ddgs"
            try:
                self._root.mkdir(parents=True, exist_ok=True)
            except OSError as exc:
                logger.warning("cache dir unavailable (%s); caching disabled", exc)
        return self._root

    def _path(self, key: str) -> Path:
        # Keys are generated hex digests, but never trust a stored key.
        safe = "".join(ch for ch in str(key) if ch.isalnum() or ch in "_-")
        return self.root / f"{safe}.json"

    # ── Core ──────────────────────────────────────────────────────────
    async def get(self, key: str, *, ttl: int | None = None) -> Any | None:
        """Return the cached value, or None on miss/expiry/corruption."""
        path = self._path(key)
        try:
            raw = await asyncio.to_thread(path.read_text, encoding="utf-8")
        except (OSError, ValueError):
            return None
        try:
            entry = json.loads(raw)
        except (ValueError, TypeError):
            await self.delete(key)
            return None
        if not isinstance(entry, dict) or entry.get("schema") != SCHEMA:
            await self.delete(key)
            return None
        expires = entry.get("expires_at")
        effective_ttl = ttl if ttl is not None else entry.get("ttl")
        # Trust the stored expiry, but let the caller tighten it.
        if isinstance(expires, (int, float)) and time.time() > expires:
            await self.delete(key)
            return None
        if (
            isinstance(effective_ttl, (int, float))
            and isinstance(entry.get("stored_at"), (int, float))
            and time.time() - entry["stored_at"] > effective_ttl
        ):
            await self.delete(key)
            return None
        return entry.get("value")

    async def set(self, key: str, value: Any, *, ttl: int) -> bool:
        entry = {
            "schema": SCHEMA,
            "key": key,
            "stored_at": time.time(),
            "expires_at": time.time() + ttl,
            "ttl": ttl,
            "value": value,
        }
        path = self._path(key)

        def _write() -> bool:
            try:
                path.parent.mkdir(parents=True, exist_ok=True)
                tmp = path.with_suffix(".json.tmp")
                tmp.write_text(
                    json.dumps(entry, ensure_ascii=False), encoding="utf-8"
                )
                tmp.replace(path)  # atomic on every platform we ship to
                return True
            except (OSError, ValueError, TypeError) as exc:
                logger.warning("cache write failed for %s: %s", key, exc)
                return False

        async with self._lock:
            return await asyncio.to_thread(_write)

    async def delete(self, key: str) -> bool:
        path = self._path(key)

        def _unlink() -> bool:
            try:
                path.unlink()
                return True
            except FileNotFoundError:
                return True
            except OSError as exc:
                logger.warning("cache delete failed for %s: %s", key, exc)
                return False

        async with self._lock:
            return await asyncio.to_thread(_unlink)

    # ── Typed helpers ─────────────────────────────────────────────────
    async def get_search(self, key: str) -> list[dict] | None:
        value = await self.get(key)
        return value if isinstance(value, list) else None

    async def put_search(self, key: str, results: list[dict]) -> bool:
        return await self.set(key, results, ttl=SEARCH_TTL_SEC)

    async def get_page(self, url: str, fmt: str = "") -> Any | None:
        return await self.get(page_key(url, fmt), ttl=PAGE_TTL_SEC)

    async def put_page(self, url: str, fmt: str, content: Any) -> bool:
        return await self.set(page_key(url, fmt), content, ttl=PAGE_TTL_SEC)

    # ── SearchResult <-> dict ─────────────────────────────────────────
    def get_cached_search(
        self, query: str, search_type: str, **filters: str
    ) -> list[Any] | None:
        """Synchronous read used on the UI task's own path.

        Returns SearchResult objects, or None on a miss. A miss is the
        common case and must stay cheap: this only stats the file.
        """
        from core.state import SearchResult

        key = search_key(query, search_type, **filters)
        path = self._path(key)
        try:
            raw = path.read_text(encoding="utf-8")
            entry = json.loads(raw)
        except (OSError, ValueError, TypeError):
            return None
        if not isinstance(entry, dict) or entry.get("schema") != SCHEMA:
            return None
        expires = entry.get("expires_at")
        if isinstance(expires, (int, float)) and time.time() > expires:
            return None
        rows = entry.get("value")
        if not isinstance(rows, list):
            return None
        results: list[Any] = []
        for row in rows:
            if not isinstance(row, dict) or not row.get("url"):
                continue
            try:
                results.append(SearchResult(**row))
            except (TypeError, ValueError):
                continue
        return results or None

    async def store_search(
        self, query: str, search_type: str, results: list[Any], **filters: str
    ) -> bool:
        rows = [_result_to_dict(r) for r in results]
        return await self.set(
            search_key(query, search_type, **filters), rows, ttl=SEARCH_TTL_SEC
        )

    # ── Maintenance ───────────────────────────────────────────────────
    async def prune(self, *, max_bytes: int = MAX_BYTES) -> dict[str, int]:
        """Drop expired entries, then oldest-first until under the cap.

        Returns {"removed": n, "freed": bytes, "remaining": count}.
        """
        stats = {"removed": 0, "freed": 0, "remaining": 0}
        root = self.root
        try:
            entries = list(root.glob("*.json"))
        except OSError as exc:
            logger.warning("cache prune could not list %s: %s", root, exc)
            return stats

        now = time.time()
        live: list[tuple[float, int, Path]] = []
        for path in entries:
            try:
                size = path.stat().st_size
                mtime = path.stat().st_mtime
            except OSError:
                continue
            expired = False
            # Read the expiry rather than trusting mtime: a file copied in
            # from elsewhere can have a fresh mtime and a stale entry.
            try:
                entry = json.loads(path.read_text(encoding="utf-8"))
                expires = entry.get("expires_at")
                if isinstance(entry, dict) and isinstance(expires, (int, float)):
                    expired = now > expires
            except (OSError, ValueError, TypeError):
                expired = True  # unreadable/garbage: not worth keeping
            if expired:
                try:
                    path.unlink()
                    stats["removed"] += 1
                    stats["freed"] += size
                except OSError:
                    live.append((mtime, size, path))
                continue
            live.append((mtime, size, path))

        total = sum(size for _, size, _ in live)
        if total > max_bytes:
            for mtime, size, path in sorted(live):
                if total <= max_bytes:
                    break
                try:
                    path.unlink()
                    total -= size
                    stats["removed"] += 1
                    stats["freed"] += size
                except OSError:
                    continue
        try:
            stats["remaining"] = len(list(root.glob("*.json")))
        except OSError:
            pass
        if stats["removed"]:
            logger.info(
                "cache prune removed %d entries (%.1f KB)",
                stats["removed"],
                stats["freed"] / 1024,
            )
        return stats

    async def clear(self) -> int:
        removed = 0
        try:
            for path in self.root.glob("*.json"):
                try:
                    path.unlink()
                    removed += 1
                except OSError:
                    continue
        except OSError:
            pass
        return removed

    def stats(self) -> dict[str, Any]:
        try:
            files = list(self.root.glob("*.json"))
            size = sum(f.stat().st_size for f in files)
            return {"entries": len(files), "bytes": size}
        except OSError:
            return {"entries": 0, "bytes": 0}


# Process-wide singleton, mirroring the StorageService pattern.
cache_service = CacheService()
