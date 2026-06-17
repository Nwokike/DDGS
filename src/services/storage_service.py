"""Storage service — persists all DDGS settings."""

from __future__ import annotations

import json
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
from core.utils import log_error

LOG_TAG = "Storage"


class StorageService:
    """Flet client-storage wrapper with cache."""

    def __init__(self, page: ft.Page):
        self.page = page
        self._cache: dict[str, Any] = {}

    async def initialize(self):
        pass

    async def get(self, key: str, default: Any = None) -> Any:
        try:
            if key in self._cache:
                return self._cache[key]
            val = await self.page.client_storage.get_async(key)
            if val is not None:
                self._cache[key] = val
                return val
            return default
        except Exception as e:
            log_error(f"Storage.get({key})", e)
            return default

    async def set(self, key: str, value: Any) -> bool:
        try:
            self._cache[key] = value
            await self.page.client_storage.set_async(key, value)
            return True
        except Exception as e:
            log_error(f"Storage.set({key})", e)
            return False

    async def remove(self, key: str) -> bool:
        try:
            self._cache.pop(key, None)
            await self.page.client_storage.remove_async(key)
            return True
        except Exception:
            return False

    async def flush(self):
        pass

    # ── Theme ──
    async def get_theme(self) -> str:
        return await self.get(STORAGE_THEME, "system")

    async def set_theme(self, v: str) -> bool:
        return await self.set(STORAGE_THEME, v)

    # ── History ──
    async def get_history(self) -> list[dict]:
        raw = await self.get(STORAGE_HISTORY)
        try:
            return json.loads(raw) if raw else []
        except json.JSONDecodeError:
            return []

    async def add_history(self, entry: dict) -> bool:
        h = await self.get_history()
        h.insert(0, entry)
        return await self.set(STORAGE_HISTORY, json.dumps(h[:100]))

    async def set_history(self, h: list[dict]) -> bool:
        return await self.set(STORAGE_HISTORY, json.dumps(h))

    # ── Search settings ──
    async def get_safe_search(self) -> str:
        return await self.get(STORAGE_SAFE_SEARCH, "moderate")

    async def set_safe_search(self, v: str) -> bool:
        return await self.set(STORAGE_SAFE_SEARCH, v)

    async def get_region(self) -> str:
        return await self.get(STORAGE_REGION, "wt-wt")

    async def set_region(self, v: str) -> bool:
        return await self.set(STORAGE_REGION, v)

    async def get_max_results(self) -> int:
        return int(await self.get(STORAGE_MAX_RESULTS, 20))

    async def set_max_results(self, v: int) -> bool:
        return await self.set(STORAGE_MAX_RESULTS, v)

    async def get_timelimit(self) -> str:
        return await self.get(STORAGE_TIMELIMIT, "")

    async def set_timelimit(self, v: str) -> bool:
        return await self.set(STORAGE_TIMELIMIT, v)

    async def get_backend(self) -> str:
        return await self.get(STORAGE_BACKEND, "auto")

    async def set_backend(self, v: str) -> bool:
        return await self.set(STORAGE_BACKEND, v)

    async def get_page(self) -> int:
        return int(await self.get(STORAGE_PAGE, 1))

    async def set_page(self, v: int) -> bool:
        return await self.set(STORAGE_PAGE, v)

    # ── Connection ──
    async def get_proxy(self) -> str:
        return await self.get(STORAGE_PROXY, "")

    async def set_proxy(self, v: str) -> bool:
        return await self.set(STORAGE_PROXY, v)

    async def get_verify_ssl(self) -> bool:
        return await self.get(STORAGE_VERIFY_SSL, True)

    async def set_verify_ssl(self, v: bool) -> bool:
        return await self.set(STORAGE_VERIFY_SSL, v)

    async def get_threads(self) -> int:
        return int(await self.get(STORAGE_THREADS, 0))

    async def set_threads(self, v: int) -> bool:
        return await self.set(STORAGE_THREADS, v)

    # ── Extract ──
    async def get_extract_format(self) -> str:
        return await self.get(STORAGE_EXTRACT_FORMAT, "text_markdown")

    async def set_extract_format(self, v: str) -> bool:
        return await self.set(STORAGE_EXTRACT_FORMAT, v)

    # ── Advanced ──
    async def get_api_url(self) -> str:
        return await self.get(STORAGE_API_URL, "")

    async def set_api_url(self, v: str) -> bool:
        return await self.set(STORAGE_API_URL, v)

    async def get_spawn_api(self) -> bool:
        return await self.get(STORAGE_SPAWN_API, False)

    async def set_spawn_api(self, v: bool) -> bool:
        return await self.set(STORAGE_SPAWN_API, v)

    # ── Onboarding ──
    async def get_onboarding_done(self) -> bool:
        return await self.get(STORAGE_ONBOARDING_DONE) == "true"

    async def set_onboarding_done(self, v: bool) -> bool:
        return await self.set(STORAGE_ONBOARDING_DONE, "true" if v else "false")

    # ── Default tab ──
    async def get_default_tab(self) -> str:
        return await self.get(STORAGE_DEFAULT_TAB, "text")

    async def set_default_tab(self, v: str) -> bool:
        return await self.set(STORAGE_DEFAULT_TAB, v)
