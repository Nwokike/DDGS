"""DDGS engine wrapper — exposes every capability with full logging."""

from __future__ import annotations

import asyncio
import time
from typing import Any

from core.state import SearchResult, SearchProgress, state
from core.utils import log_ddgs_call, log_performance, log_error, logger

LOG_TAG = "SearchService"

_DDGS_AVAILABLE = False
try:
    from ddgs import DDGS

    _DDGS_AVAILABLE = True
except ImportError as e:
    DDGS = None
    logger.error(f"[{LOG_TAG}] DDGS import failed: {e}")
    logger.error(f"[{LOG_TAG}] This is critical - primp may have crashed on import")


class SearchService:
    """Wraps DDGS — every method, every parameter, all logged."""

    def __init__(self):
        self._ddgs: DDGS | None = None
        self._is_cancelled = False
        logger.info(
            f"[{LOG_TAG}] SearchService created. DDGS available: {_DDGS_AVAILABLE}"
        )

    @property
    def is_available(self) -> bool:
        return _DDGS_AVAILABLE

    def _build_client(self) -> DDGS:
        """Create DDGS client with current proxy/timeout/verify settings."""
        if self._ddgs is not None:
            return self._ddgs
        logger.debug(f"[{LOG_TAG}] Building DDGS client...")
        start = time.perf_counter()
        try:
            kwargs: dict[str, Any] = {}
            if state.proxy:
                kwargs["proxy"] = state.proxy
            if state.verify_ssl is False:
                kwargs["verify"] = False
            if state.api_url:
                kwargs["api_url"] = state.api_url
            if state.spawn_api:
                kwargs["spawn_api"] = True
            kwargs["timeout"] = 15

            self._ddgs = DDGS(**kwargs)
            if state.threads > 0:
                DDGS.threads = state.threads

            elapsed = time.perf_counter() - start
            logger.info(
                f"[{LOG_TAG}] DDGS client built in {elapsed:.3f}s with proxy={bool(state.proxy)} verify={state.verify_ssl}"
            )
            return self._ddgs
        except Exception as e:
            elapsed = time.perf_counter() - start
            log_error(f"[{LOG_TAG}] DDGS() constructor failed in {elapsed:.3f}s", e)
            raise

    def cancel(self):
        self._is_cancelled = True
        logger.info(f"[{LOG_TAG}] Cancelled")

    async def search(
        self, search_type: str, query: str, on_progress=None
    ) -> SearchProgress:
        """One generic search method — maps to the correct DDGS method with all params."""
        self._is_cancelled = False
        progress = SearchProgress(
            query=query, search_type=search_type, total_results=0, is_running=True
        )
        state.search_progress = progress
        start_time = time.perf_counter()

        try:
            if not _DDGS_AVAILABLE:
                raise RuntimeError("DDGS library unavailable")

            ddgs = await asyncio.to_thread(self._build_client)

            method_map = {
                "text": ddgs.text,
                "images": ddgs.images,
                "videos": ddgs.videos,
                "news": ddgs.news,
                "books": ddgs.books,
            }
            method = method_map.get(search_type)
            if not method:
                raise ValueError(f"Unknown search type: {search_type}")

            params: dict[str, Any] = {"query": query}

            # ——— EVERY DDGS SEARCH PARAMETER ———
            params["region"] = state.region or "wt-wt"

            safemap = {"off": "off", "moderate": "moderate", "on": "on"}
            params["safesearch"] = safemap.get(state.safe_search, "moderate")

            if state.timelimit:
                params["timelimit"] = state.timelimit

            if state.backend and state.backend != "auto":
                params["backend"] = state.backend

            if state.page and state.page > 1:
                params["page"] = state.page

            params["max_results"] = state.max_results or 20

            logger.info(f"[{LOG_TAG}] DDGS.{search_type}({params})")
            log_ddgs_call(search_type, query, params)

            call_start = time.perf_counter()
            try:
                raw = await asyncio.to_thread(lambda: list(method(**params)))
                call_elapsed = time.perf_counter() - call_start
                logger.info(
                    f"[{LOG_TAG}] DDGS.{search_type} → {len(raw)} results in {call_elapsed:.3f}s"
                )
                log_ddgs_call(search_type, query, params, result_count=len(raw))
            except Exception as e:
                call_elapsed = time.perf_counter() - call_start
                log_ddgs_call(search_type, query, params, error=e)
                raise

            parsed = []
            for i, r in enumerate(raw):
                parsed.append(self._parse_one(r, search_type, i))
                progress.loaded_results = i + 1
                if on_progress and (i % 5 == 0 or i == len(raw) - 1):
                    progress.results = parsed
                    try:
                        on_progress(progress)
                    except (
                        ValueError,
                        TypeError,
                        AttributeError,
                        RuntimeError,
                    ) as ex:
                        logger.debug(f"Progress callback error: {ex}")
                if self._is_cancelled:
                    break

            elapsed = time.perf_counter() - start_time
            log_performance(
                f"{search_type}_search", elapsed, query=query, results=len(parsed)
            )

            progress.total_results = len(parsed)
            progress.results = parsed
            progress.is_running = False
            state.last_results[search_type] = parsed

        except (
            ValueError,
            TypeError,
            KeyError,
            AttributeError,
            IndexError,
            OSError,
            RuntimeError,
            ConnectionError,
            ImportError,
            TimeoutError,
        ) as e:
            elapsed = time.perf_counter() - start_time
            log_error(f"[{LOG_TAG}] {search_type} search", e, query=query)
            progress.is_running = False
            progress.error = str(e)
            if "primp" in str(e).lower():
                logger.critical(
                    f"[{LOG_TAG}] PRIMP_CRASH_DETECTED in {search_type}: {e}"
                )

        return progress

    async def extract_url(self, url: str, fmt: str = "text_markdown") -> dict | None:
        """Extract content from a URL in any format."""
        logger.info(f"[{LOG_TAG}] Extracting: {url} fmt={fmt}")
        start = time.perf_counter()
        try:
            ddgs = await asyncio.to_thread(self._build_client)
            result = await asyncio.to_thread(lambda: ddgs.extract(url, fmt=fmt))
            elapsed = time.perf_counter() - start
            log_performance("extract", elapsed, url=url, fmt=fmt)
            logger.info(f"[{LOG_TAG}] Extract success: {type(result)}")
            return result
        except (
            ValueError,
            TypeError,
            KeyError,
            AttributeError,
            IndexError,
            OSError,
            RuntimeError,
            ConnectionError,
            ImportError,
            TimeoutError,
        ) as e:
            elapsed = time.perf_counter() - start
            log_error(f"[{LOG_TAG}] extract({url})", e)
            return None

    def _parse_one(self, raw: dict, search_type: str, index: int) -> SearchResult:
        """Parse a raw result dict into SearchResult."""
        try:
            if search_type == "images":
                return SearchResult(
                    title=raw.get("title", ""),
                    url=raw.get("url", ""),
                    snippet=raw.get("title", ""),
                    search_type=search_type,
                    thumbnail=raw.get("thumbnail", ""),
                    image_url=raw.get("image", ""),
                    width=int(raw["width"]) if raw.get("width") else None,
                    height=int(raw["height"]) if raw.get("height") else None,
                    source=raw.get("source", ""),
                    raw_data=raw,
                )
            elif search_type == "videos":
                stats = raw.get("statistics") or {}
                return SearchResult(
                    title=raw.get("title", ""),
                    url=raw.get("content", ""),
                    snippet=raw.get("description", ""),
                    search_type=search_type,
                    duration=raw.get("duration", ""),
                    embed_url=raw.get("embed_url", ""),
                    publisher=raw.get("publisher", ""),
                    views=int(stats["viewCount"]) if stats.get("viewCount") else None,
                    published=raw.get("published", ""),
                    thumbnail=raw.get("images", {}).get("medium", ""),
                    source=raw.get("uploader", ""),
                    raw_data=raw,
                )
            elif search_type == "news":
                return SearchResult(
                    title=raw.get("title", ""),
                    url=raw.get("url", ""),
                    snippet=raw.get("body", ""),
                    search_type=search_type,
                    date=raw.get("date", ""),
                    source=raw.get("source", ""),
                    thumbnail=raw.get("image", ""),
                    raw_data=raw,
                )
            elif search_type == "books":
                return SearchResult(
                    title=raw.get("title", ""),
                    url=raw.get("url", ""),
                    snippet=raw.get("text", ""),
                    search_type=search_type,
                    raw_data=raw,
                )
            else:
                return SearchResult(
                    title=raw.get("title", ""),
                    url=raw.get("href", ""),
                    snippet=raw.get("body", ""),
                    search_type=search_type,
                    raw_data=raw,
                )
        except (
            ValueError,
            TypeError,
            KeyError,
            AttributeError,
            IndexError,
        ) as e:
            logger.warning(f"[{LOG_TAG}] Parse fail [{index}]: {e}")
            return SearchResult(
                title="Parse Error",
                url="",
                snippet=str(e),
                search_type=search_type,
                raw_data={"error": str(e), "raw": raw},
            )
