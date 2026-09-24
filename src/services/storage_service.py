"""Storage service — persists all DDGS settings via JSON file in a platform-resilient manner."""

from __future__ import annotations

import asyncio
import json
import logging
import os
import time
from pathlib import Path
from typing import Any

import flet as ft

from core.constants import (
    STORAGE_AI_MODE,
    STORAGE_AI_MODEL,
    STORAGE_ASSISTANT_HISTORY,
    STORAGE_BACKEND,
    STORAGE_DEFAULT_TAB,
    STORAGE_EXTRACT_FORMAT,
    STORAGE_HISTORY,
    STORAGE_IMAGE_COLOR,
    STORAGE_IMAGE_LAYOUT,
    STORAGE_IMAGE_LICENSE,
    STORAGE_IMAGE_SIZE,
    STORAGE_IMAGE_TYPE,
    STORAGE_IS_PREMIUM,
    STORAGE_LICENSE_EMAIL,
    STORAGE_LICENSE_NAME,
    STORAGE_LICENSE_PAID_THROUGH,
    STORAGE_LICENSE_PHONE,
    STORAGE_LICENSE_PRODUCT,
    STORAGE_LICENSE_RECOVERY_ID,
    STORAGE_LICENSE_STATUS,
    STORAGE_LICENSE_TOKEN,
    STORAGE_MAX_RESULTS,
    STORAGE_ONBOARDING_DONE,
    STORAGE_PAGE,
    STORAGE_PROXY,
    STORAGE_REGION,
    STORAGE_SAFE_SEARCH,
    STORAGE_SCHEDULED_SCRAPES,
    STORAGE_SEARCH_DURATION,
    STORAGE_SEARCH_LICENSE,
    STORAGE_SEARCH_RESOLUTION,
    STORAGE_THEME,
    STORAGE_THREADS,
    STORAGE_TIMELIMIT,
    STORAGE_VERIFY_SSL,
    STORAGE_VIDEO_QUALITY,
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
    STORAGE_VIDEO_QUALITY: "best",
    STORAGE_ONBOARDING_DONE: False,
    STORAGE_DEFAULT_TAB: "text",
    STORAGE_AI_MODE: True,
    STORAGE_IS_PREMIUM: False,
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
        self._is_web = bool(getattr(page, "web", False))
        self._prefs: ft.SharedPreferences | None = None

        if self._is_web:
            # Web: async SharedPreferences service; cache loads in initialize().
            self._prefs = ft.SharedPreferences()
        else:
            self._load()

    def _load(self) -> None:
        try:
            _STORAGE_DIR.mkdir(parents=True, exist_ok=True)
            if _STORAGE_FILE.exists():
                raw = _STORAGE_FILE.read_text(encoding="utf-8")
                loaded = json.loads(raw) if raw else {}
                self._cache.update(loaded)
        except (
            ValueError,
            TypeError,
            OSError,
            RuntimeError,
            ConnectionError,
            ImportError,
        ) as e:
            logger.warning("StorageService._load failed: %s", e)

    def _save_now(self) -> None:
        if self._is_web:
            return  # web persists via async SharedPreferences in flush()
        try:
            _STORAGE_DIR.mkdir(parents=True, exist_ok=True)
            _STORAGE_FILE.write_text(
                json.dumps(self._cache, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
            self._dirty = False
            self._last_write = time.monotonic()
        except (
            ValueError,
            TypeError,
            OSError,
            RuntimeError,
            ConnectionError,
            ImportError,
        ) as e:
            logger.warning("StorageService._save_now failed: %s", e)

    async def _save_web(self) -> None:
        try:
            await self._prefs.set("ddgs_storage", json.dumps(self._cache))
            self._dirty = False
            self._last_write = time.monotonic()
        except (
            ValueError,
            TypeError,
            OSError,
            RuntimeError,
            ConnectionError,
            ImportError,
            AttributeError,
        ) as e:
            logger.warning("StorageService._save_web failed: %s", e)

    def flush_now(self) -> None:
        """Synchronously persist dirty state — called from on_close before teardown."""
        if self._dirty and not self._is_web:
            self._save_now()

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
        """Load persisted state. Web reads the async SharedPreferences service."""
        if not (self._is_web and self._prefs):
            return
        try:
            raw = await self._prefs.get("ddgs_storage")
            loaded = json.loads(raw) if raw else {}
            self._cache.update(loaded)
        except (
            ValueError,
            TypeError,
            OSError,
            RuntimeError,
            ConnectionError,
            ImportError,
            AttributeError,
        ) as e:
            logger.warning("StorageService.initialize failed: %s", e)

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
            if not self._dirty:
                return
            if self._is_web:
                await self._save_web()
            else:
                self._save_now()

    @property
    def _theme(self) -> str:
        return str(self._cache.get(STORAGE_THEME, "system"))

    async def get_theme(self) -> str:
        return self._theme

    async def set_theme(self, v: str) -> bool:
        return await self.set(STORAGE_THEME, v)

    async def get_video_quality(self) -> str:
        return str(self._cache.get(STORAGE_VIDEO_QUALITY, "best"))

    async def set_video_quality(self, v: str) -> bool:
        return await self.set(STORAGE_VIDEO_QUALITY, v)

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

    async def get_image_size(self) -> str:
        return str(await self.get(STORAGE_IMAGE_SIZE, ""))

    async def set_image_size(self, v: str) -> bool:
        return await self.set(STORAGE_IMAGE_SIZE, v)

    async def get_image_color(self) -> str:
        return str(await self.get(STORAGE_IMAGE_COLOR, ""))

    async def set_image_color(self, v: str) -> bool:
        return await self.set(STORAGE_IMAGE_COLOR, v)

    async def get_image_type(self) -> str:
        return str(await self.get(STORAGE_IMAGE_TYPE, ""))

    async def set_image_type(self, v: str) -> bool:
        return await self.set(STORAGE_IMAGE_TYPE, v)

    async def get_image_layout(self) -> str:
        return str(await self.get(STORAGE_IMAGE_LAYOUT, ""))

    async def set_image_layout(self, v: str) -> bool:
        return await self.set(STORAGE_IMAGE_LAYOUT, v)

    async def get_image_license(self) -> str:
        return str(await self.get(STORAGE_IMAGE_LICENSE, ""))

    async def set_image_license(self, v: str) -> bool:
        return await self.set(STORAGE_IMAGE_LICENSE, v)

    async def get_search_resolution(self) -> str:
        return str(await self.get(STORAGE_SEARCH_RESOLUTION, ""))

    async def set_search_resolution(self, v: str) -> bool:
        return await self.set(STORAGE_SEARCH_RESOLUTION, v)

    async def get_search_duration(self) -> str:
        return str(await self.get(STORAGE_SEARCH_DURATION, ""))

    async def set_search_duration(self, v: str) -> bool:
        return await self.set(STORAGE_SEARCH_DURATION, v)

    async def get_search_license(self) -> str:
        return str(await self.get(STORAGE_SEARCH_LICENSE, ""))

    async def set_search_license(self, v: str) -> bool:
        return await self.set(STORAGE_SEARCH_LICENSE, v)

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

    async def get_onboarding_done(self) -> bool:
        return bool(await self.get(STORAGE_ONBOARDING_DONE, False))

    async def set_onboarding_done(self, v: bool) -> bool:
        return await self.set(STORAGE_ONBOARDING_DONE, v)

    async def get_default_tab(self) -> str:
        return str(await self.get(STORAGE_DEFAULT_TAB, "text"))

    async def set_default_tab(self, v: str) -> bool:
        return await self.set(STORAGE_DEFAULT_TAB, v)

    async def get_ai_mode(self) -> bool:
        return bool(await self.get(STORAGE_AI_MODE, True))

    async def set_ai_mode(self, v: bool) -> bool:
        return await self.set(STORAGE_AI_MODE, v)

    async def get_scheduled_scrapes(self) -> str:
        return str(await self.get(STORAGE_SCHEDULED_SCRAPES, "[]"))

    async def set_scheduled_scrapes(self, v: str) -> bool:
        return await self.set(STORAGE_SCHEDULED_SCRAPES, v)

    async def get_assistant_history(self) -> str:
        return str(await self.get(STORAGE_ASSISTANT_HISTORY, "[]") or "[]")

    async def set_assistant_history(self, v: str) -> bool:
        return await self.set(STORAGE_ASSISTANT_HISTORY, v or "[]")

    async def get_ai_model(self) -> str:
        return str(await self.get(STORAGE_AI_MODEL, "auto") or "auto")

    async def set_ai_model(self, v: str) -> bool:
        return await self.set(STORAGE_AI_MODEL, v or "auto")

    async def get_is_premium(self) -> bool:
        return bool(await self.get(STORAGE_IS_PREMIUM, False))

    async def set_is_premium(self, v: bool) -> bool:
        return await self.set(STORAGE_IS_PREMIUM, v)

    # ── Kiri License (direct/web channel) ─────────────────────────────
    async def get_license_record(self) -> dict[str, Any]:
        """Everything the license channel needs, in one read."""
        return {
            "recovery_id": str(await self.get(STORAGE_LICENSE_RECOVERY_ID, "") or ""),
            "token": str(await self.get(STORAGE_LICENSE_TOKEN, "") or ""),
            "status": str(await self.get(STORAGE_LICENSE_STATUS, "") or ""),
            "product": str(await self.get(STORAGE_LICENSE_PRODUCT, "") or ""),
            "paid_through": await self.get(STORAGE_LICENSE_PAID_THROUGH, None),
            "email": str(await self.get(STORAGE_LICENSE_EMAIL, "") or ""),
            "name": str(await self.get(STORAGE_LICENSE_NAME, "") or ""),
            "phone": str(await self.get(STORAGE_LICENSE_PHONE, "") or ""),
        }

    async def set_license_record(self, **fields: Any) -> bool:
        """Write only the fields supplied; others are left untouched."""
        allowed = {
            "recovery_id": STORAGE_LICENSE_RECOVERY_ID,
            "token": STORAGE_LICENSE_TOKEN,
            "status": STORAGE_LICENSE_STATUS,
            "product": STORAGE_LICENSE_PRODUCT,
            "paid_through": STORAGE_LICENSE_PAID_THROUGH,
            "email": STORAGE_LICENSE_EMAIL,
            "name": STORAGE_LICENSE_NAME,
            "phone": STORAGE_LICENSE_PHONE,
        }
        ok = True
        for key, value in fields.items():
            storage_key = allowed.get(key)
            if storage_key is None:
                continue
            ok = await self.set(storage_key, value) and ok
        return ok

    async def clear_license_record(self) -> bool:
        return await self.set_license_record(
            recovery_id="",
            token="",
            status="",
            product="",
            paid_through=None,
        )
