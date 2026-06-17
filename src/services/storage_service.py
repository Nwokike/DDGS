"""Storage service — persists all DDGS settings via JSON file."""

from __future__ import annotations

import json
import os
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
    """File-based JSON settings persistence."""

    def __init__(self, page: ft.Page):
        self.page = page
        self._cache: dict[str, Any] = dict(DEFAULTS)
        self._file_path: str | None = None

    async def initialize(self):
        data_dir = None
        for method_name in (
            "get_application_support_directory",
            "get_application_cache_directory",
            "get_application_documents_directory",
        ):
            try:
                method = getattr(ft.StoragePaths(), method_name)
                data_dir = await method()
                if data_dir:
                    break
            except Exception:
                continue
        if not data_dir:
            import tempfile

            data_dir = tempfile.gettempdir()
        self._file_path = os.path.join(data_dir, "ddgs_settings.json")
        loaded = await self._load()
        self._cache.update(loaded)

    async def _load(self) -> dict[str, Any]:
        try:
            if self._file_path and os.path.exists(self._file_path):
                with open(self._file_path, encoding="utf-8") as f:
                    return json.load(f)
        except Exception as e:
            log_error("Storage._load", e)
        return {}

    async def _save(self):
        try:
            if self._file_path:
                with open(self._file_path, "w", encoding="utf-8") as f:
                    json.dump(self._cache, f)
        except Exception as e:
            log_error("Storage._save", e)

    async def get(self, key: str, default: Any = None) -> Any:
        return self._cache.get(key, default)

    async def set(self, key: str, value: Any) -> bool:
        try:
            self._cache[key] = value
            await self._save()
            return True
        except Exception as e:
            log_error(f"Storage.set({key})", e)
            return False

    async def remove(self, key: str) -> bool:
        try:
            self._cache.pop(key, None)
            await self._save()
            return True
        except Exception:
            return False

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
