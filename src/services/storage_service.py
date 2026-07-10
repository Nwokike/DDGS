"""Storage service — persists all DDGS settings via JSON file in a platform-resilient manner."""

from __future__ import annotations

import json
import logging
import os
import time
import asyncio
from pathlib import Path
from typing import Any

import flet as ft

from core.constants import (
    STORAGE_THEME,
    STORAGE_HISTORY,
    STORAGE_SAFE_SEARCH,
    STORAGE_REGION,
    STORAGE_MAX_RESULTS,
    STORAGE_ONBOARDING_DONE,
    STORAGE_DEFAULT_TAB,
    STORAGE_TIMELIMIT,
    STORAGE_BACKEND,
    STORAGE_PROXY,
    STORAGE_VERIFY_SSL,
    STORAGE_THREADS,
    STORAGE_PAGE,
    STORAGE_EXTRACT_FORMAT,
    STORAGE_API_URL,
    STORAGE_SPAWN_API,
)

logger = logging.getLogger(__name__)

# Use Flet sandbox data storage path on Android/iOS mobile to avoid Path.home() permission issues
storage_env = os.getenv("FLET_APP_STORAGE_DATA")
if storage_env:
    _STORAGE_DIR = Path(storage_env)
else:
    _STORAGE_DIR = Path.home() / ".ddgs_ui"

_STORAGE_FILE = _STORAGE_DIR / "storage.json"
_WRITE_DEBOUNCE_SEC = 1.0

DEFAULTS: dict[str, Any] = {
    STORAGE_THEME: "system",
    STORAGE_HISTORY: [],
    STORAGE_SAFE_SEARCH: "moderate",
    STORAGE_REGION: "wt-wt",
    STORAGE_MAX_RESULTS: 20,
    STORAGE_TIMELIMIT: "",
    STORAGE_BACKEND: "auto",
    STORAGE_PAGE: 1,
    STORAGE_PROXY: "",
    STORAGE_VERIFY_SSL: True,
    STORAGE_THREADS: 0,
    STORAGE_EXTRACT_FORMAT: "text_markdown",
    STORAGE_API_URL: "",
    STORAGE_SPAWN_API: False,
    STORAGE_ONBOARDING_DONE: False,
    STORAGE_DEFAULT_TAB: "text",
}


class StorageService:
    """Platform-resilient key-value storage service matching Sherlock's implementation."""

    def __init__(self, page: ft.Page):
        self._page = page
        self._cache: dict[str, Any] = dict(DEFAULTS)
        self._lock = asyncio.Lock()
        self._dirty = False
        self._last_write: float = 0.0
        self._pending_write_task = None
        self._is_web = bool(getattr(page, "session_id", None))

        if self._is_web:
            self._load_web()
        else:
            self._load()

    def _load_web(self) -> None:
        try:
            cs = self._page.client_storage
            raw = cs.get("ddgs_storage")
            loaded = json.loads(raw) if raw else {}
            self._cache.update(loaded)
        except Exception as e:
            logger.warning("StorageService._load_web failed: %s", e)

    def _load(self) -> None:
        try:
            _STORAGE_DIR.mkdir(parents=True, exist_ok=True)
            if _STORAGE_FILE.exists():
                raw = _STORAGE_FILE.read_text(encoding="utf-8")
                loaded = json.loads(raw) if raw else {}
                self._cache.update(loaded)
        except Exception as e:
            logger.warning("StorageService._load failed: %s", e)

    def _save_now(self) -> None:
        if self._is_web:
            self._save_now_web()
            return
        try:
            _STORAGE_DIR.mkdir(parents=True, exist_ok=True)
            _STORAGE_FILE.write_text(
                json.dumps(self._cache, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
            self._dirty = False
            self._last_write = time.monotonic()
        except Exception as e:
            logger.warning("StorageService._save_now failed: %s", e)

    def _save_now_web(self) -> None:
        try:
            cs = self._page.client_storage
            cs.set("ddgs_storage", json.dumps(self._cache))
            self._dirty = False
            self._last_write = time.monotonic()
        except Exception as e:
            logger.warning("StorageService._save_now_web failed: %s", e)

    def _schedule_write(self) -> None:
        if self._pending_write_task:
            return
        try:
            loop = asyncio.get_event_loop()
            self._pending_write_task = loop.call_later(
                _WRITE_DEBOUNCE_SEC,
                lambda: loop.create_task(self._flush_task()),
            )
        except RuntimeError:
            self._save_now()

    async def _flush_task(self) -> None:
        try:
            await self.flush()
        finally:
            self._pending_write_task = None

    async def initialize(self):
        # Kept for backward compatibility
        pass

    async def get(self, key: str, default: Any = None) -> Any:
        async with self._lock:
            return self._cache.get(key, default)

    async def set(self, key: str, value: Any) -> bool:
        async with self._lock:
            self._cache[key] = value
            self._dirty = True
        self._schedule_write()
        return True

    async def remove(self, key: str) -> bool:
        async with self._lock:
            self._cache.pop(key, None)
            self._dirty = True
        self._schedule_write()
        return True

    async def flush(self) -> None:
        async with self._lock:
            if self._dirty:
                self._save_now()

    @property
    def _theme(self) -> str:
        return str(self._cache.get(STORAGE_THEME, "system"))

    async def get_theme(self) -> str:
        return self._theme

    async def set_theme(self, v: str) -> bool:
        return await self.set(STORAGE_THEME, v)

    @property
    def _history(self) -> list[dict]:
        raw = self._cache.get(STORAGE_HISTORY, [])
        if isinstance(raw, str):
            try:
                return json.loads(raw)
            except json.JSONDecodeError:
                return []
        return list(raw) if isinstance(raw, list) else []

    async def get_history(self) -> list[dict]:
        return self._history

    async def add_history(self, entry: dict) -> bool:
        h = self._history
        h.insert(0, entry)
        return await self.set(STORAGE_HISTORY, h[:100])

    async def set_history(self, h: list[dict]) -> bool:
        return await self.set(STORAGE_HISTORY, h)

    async def get_safe_search(self) -> str:
        return str(await self.get(STORAGE_SAFE_SEARCH, "moderate"))

    async def set_safe_search(self, v: str) -> bool:
        return await self.set(STORAGE_SAFE_SEARCH, v)

    async def get_region(self) -> str:
        return str(await self.get(STORAGE_REGION, "wt-wt"))

    async def set_region(self, v: str) -> bool:
        return await self.set(STORAGE_REGION, v)

    async def get_max_results(self) -> int:
        return int(await self.get(STORAGE_MAX_RESULTS, 20))

    async def set_max_results(self, v: int) -> bool:
        return await self.set(STORAGE_MAX_RESULTS, v)

    async def get_timelimit(self) -> str:
        return str(await self.get(STORAGE_TIMELIMIT, ""))

    async def set_timelimit(self, v: str) -> bool:
        return await self.set(STORAGE_TIMELIMIT, v)

    async def get_backend(self) -> str:
        return str(await self.get(STORAGE_BACKEND, "auto"))

    async def set_backend(self, v: str) -> bool:
        return await self.set(STORAGE_BACKEND, v)

    async def get_page(self) -> int:
        return int(await self.get(STORAGE_PAGE, 1))

    async def set_page(self, v: int) -> bool:
        return await self.set(STORAGE_PAGE, v)

    async def get_proxy(self) -> str:
        return str(await self.get(STORAGE_PROXY, ""))

    async def set_proxy(self, v: str) -> bool:
        return await self.set(STORAGE_PROXY, v)

    async def get_verify_ssl(self) -> bool:
        return bool(await self.get(STORAGE_VERIFY_SSL, True))

    async def set_verify_ssl(self, v: bool) -> bool:
        return await self.set(STORAGE_VERIFY_SSL, v)

    async def get_threads(self) -> int:
        return int(await self.get(STORAGE_THREADS, 0))

    async def set_threads(self, v: int) -> bool:
        return await self.set(STORAGE_THREADS, v)

    async def get_extract_format(self) -> str:
        return str(await self.get(STORAGE_EXTRACT_FORMAT, "text_markdown"))

    async def set_extract_format(self, v: str) -> bool:
        return await self.set(STORAGE_EXTRACT_FORMAT, v)

    async def get_api_url(self) -> str:
        return str(await self.get(STORAGE_API_URL, ""))

    async def set_api_url(self, v: str) -> bool:
        return await self.set(STORAGE_API_URL, v)

    async def get_spawn_api(self) -> bool:
        return bool(await self.get(STORAGE_SPAWN_API, False))

    async def set_spawn_api(self, v: bool) -> bool:
        return await self.set(STORAGE_SPAWN_API, v)

    async def get_onboarding_done(self) -> bool:
        return bool(await self.get(STORAGE_ONBOARDING_DONE, False))

    async def set_onboarding_done(self, v: bool) -> bool:
        return await self.set(STORAGE_ONBOARDING_DONE, v)

    async def get_default_tab(self) -> str:
        return str(await self.get(STORAGE_DEFAULT_TAB, "text"))

    async def set_default_tab(self, v: str) -> bool:
        return await self.set(STORAGE_DEFAULT_TAB, v)
