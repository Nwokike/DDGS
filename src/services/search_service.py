"""DDGS engine wrapper — exposes every capability with full logging."""

from __future__ import annotations

import asyncio
import time
from typing import Any

from core.state import SearchProgress, SearchResult, state
from core.utils import (
    classify_error,
    log_ddgs_call,
    log_error,
    log_performance,
    logger,
)

LOG_TAG = "SearchService"


# ── Fix fake_useragent 2.x unable to read browsers.jsonl from zipped site-packages ──
# Flet 0.86+ packages pure-Python deps into sitepackages.zip.  fake_useragent's
# find_browser_json_path() does Path(str(importlib_traversable)) which produces a
# useless path inside the zip.  This patch makes load() use importlib.resources
# directly, which handles zips correctly.
def _patch_fake_useragent():
    try:
        import importlib.resources as _ilr
        import json as _json

        import fake_useragent.utils as _fau

        _orig_load = _fau.load

        def _zip_safe_load():
            try:
                return _orig_load()
            except Exception:
                data = (
                    _ilr.files("fake_useragent.data")
                    .joinpath("browsers.jsonl")
                    .read_text()
                )
                result = [
                    _json.loads(line) for line in data.splitlines() if line.strip()
                ]
                if not result:
                    from fake_useragent.errors import FakeUserAgentError

                    raise FakeUserAgentError("browsers.jsonl is empty")
                return result

        _fau.load = _zip_safe_load
    except Exception:
        pass


_patch_fake_useragent()
# ── End fake_useragent patch ──

_DDGS_AVAILABLE = False
try:
    from ddgs import DDGS
    from ddgs.exceptions import DDGSException

    _DDGS_AVAILABLE = True
except ImportError as e:
    DDGS = None
    DDGSException = Exception  # fallback
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
            raw = []
            primary_err: Exception | None = None
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
                if search_type not in ("videos", "books"):
                    raise
                # videos/books fall through to their engine fallback below;
                # remember the primary error so we can surface a real
                # offline/server error if the fallback also fails.
                primary_err = e

            parsed = []
            if raw:
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
            elif search_type == "videos":
                logger.info(
                    f"[{LOG_TAG}] DDGS.videos returned 0 results/rate-limited; attempting YouTube InnerTube fallback"
                )
                yt_results, yt_err = await self._youtube_video_fallback(query)
                if yt_results:
                    parsed = yt_results
                    logger.info(
                        f"[{LOG_TAG}] YouTube InnerTube fallback → {len(parsed)} results"
                    )
                else:
                    self._surface_fallback_failure(
                        progress, search_type, primary_err, yt_err
                    )
            elif search_type == "books":
                logger.info(
                    f"[{LOG_TAG}] DDGS.books returned 0 results; attempting OpenLibrary fallback"
                )
                book_results, ol_err = await self._openlibrary_book_fallback(query)
                if book_results:
                    parsed = book_results
                    logger.info(
                        f"[{LOG_TAG}] OpenLibrary fallback → {len(parsed)} results"
                    )
                else:
                    self._surface_fallback_failure(
                        progress, search_type, primary_err, ol_err
                    )

            elapsed = time.perf_counter() - start_time
            log_performance(
                f"{search_type}_search", elapsed, query=query, results=len(parsed)
            )

            progress.total_results = len(parsed)
            progress.results = parsed
            progress.is_running = False
            progress.error = None
            state.last_results[search_type] = parsed

        except (
            DDGSException,
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

    async def extract_url(
        self, url: str, fmt: str = "text_markdown"
    ) -> tuple[dict | None, str | None]:
        """Extract content from a URL in any format. Returns (result_dict, error_string)."""
        logger.info(f"[{LOG_TAG}] Extracting: {url} fmt={fmt}")
        start = time.perf_counter()
        try:
            ddgs = await asyncio.to_thread(self._build_client)
            result = await asyncio.to_thread(lambda: ddgs.extract(url, fmt=fmt))
            elapsed = time.perf_counter() - start
            log_performance("extract", elapsed, url=url, fmt=fmt)
            logger.info(f"[{LOG_TAG}] Extract success: {type(result)}")
            return result, None
        except (
            DDGSException,
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
            return None, str(e)

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
                    views=int(stats["viewCount"])
                    if stats.get("viewCount") is not None
                    and str(stats["viewCount"]).isdigit()
                    else None,
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

    @staticmethod
    def _surface_fallback_failure(
        progress: SearchProgress,
        search_type: str,
        primary_err: Exception | None,
        fallback_err: str | None,
    ) -> None:
        """Surface a real network/server/rate-limit error when BOTH the primary
        DDGS call and its engine fallback produced nothing.

        When both simply returned zero results (no error), this is a genuine
        "no matches" and ``progress.error`` is left unset.
        """
        err_str = str(primary_err) if primary_err is not None else ""
        if not err_str:
            err_str = fallback_err or ""
        if not err_str:
            return
        category = classify_error(err_str)
        if category in ("offline", "server", "rate_limit"):
            progress.error = err_str
            if search_type == "videos" and category == "rate_limit":
                progress.is_rate_limited = True

    async def _youtube_video_fallback(
        self, query: str
    ) -> tuple[list[SearchResult], str | None]:
        """Fetch video search results from YouTube InnerTube API when DDGS.videos is rate-limited."""
        try:
            import primp

            client = primp.Client(timeout=10)
            body = {
                "context": {
                    "client": {
                        "clientName": "WEB",
                        "clientVersion": "2.20240101.00.00",
                        "hl": "en",
                        "gl": "US",
                    }
                },
                "query": query,
            }
            resp = await asyncio.to_thread(
                lambda: client.post(
                    "https://www.youtube.com/youtubei/v1/search", json=body
                )
            )
            if resp.status_code != 200:
                return [], f"HTTP {resp.status_code}"
            data = resp.json()
            contents = (
                data.get("contents", {})
                .get("twoColumnSearchResultsRenderer", {})
                .get("primaryContents", {})
                .get("sectionListRenderer", {})
                .get("contents", [])
            )
            items = (
                contents[0].get("itemSectionRenderer", {}).get("contents", [])
                if contents
                else []
            )
            parsed = []
            for item in items:
                if "videoRenderer" in item:
                    vr = item["videoRenderer"]
                    title = vr.get("title", {}).get("runs", [{}])[0].get("text", "")
                    video_id = vr.get("videoId", "")
                    url = f"https://www.youtube.com/watch?v={video_id}"
                    duration = vr.get("lengthText", {}).get("simpleText", "")
                    views_str = vr.get("viewCountText", {}).get("simpleText", "") or ""
                    views = None
                    if views_str:
                        num_part = "".join(
                            c for c in views_str.split()[0] if c.isdigit()
                        )
                        if num_part:
                            views = int(num_part)
                    publisher = (
                        vr.get("ownerText", {}).get("runs", [{}])[0].get("text", "")
                    )
                    thumbnail = (
                        vr.get("thumbnail", {})
                        .get("thumbnails", [{}])[-1]
                        .get("url", "")
                    )
                    if title and video_id:
                        parsed.append(
                            SearchResult(
                                title=title,
                                url=url,
                                snippet=f"{publisher} • {duration}"
                                if publisher
                                else title,
                                search_type="videos",
                                thumbnail=thumbnail,
                                duration=duration,
                                publisher=publisher,
                                views=views,
                            )
                        )
            return parsed, None
        except (
            ValueError,
            TypeError,
            AttributeError,
            KeyError,
            IndexError,
            OSError,
            RuntimeError,
            ConnectionError,
            ImportError,
            TimeoutError,
        ) as ex:
            logger.warning(f"[{LOG_TAG}] YouTube video fallback error: {ex}")
            return [], str(ex)

    async def _openlibrary_book_fallback(
        self, query: str
    ) -> tuple[list[SearchResult], str | None]:
        """Fetch book search results from OpenLibrary API when DDGS.books returns 0 results or fails."""
        try:
            import primp

            client = primp.Client(timeout=10)
            resp = await asyncio.to_thread(
                lambda: client.get(
                    "https://openlibrary.org/search.json",
                    params={"q": query, "limit": "20"},
                )
            )
            if resp.status_code != 200:
                return [], f"HTTP {resp.status_code}"
            docs = resp.json().get("docs", [])
            results = []
            for doc in docs:
                title = doc.get("title", "")
                authors = ", ".join(doc.get("author_name", []))
                cover_i = doc.get("cover_i")
                thumb = (
                    f"https://covers.openlibrary.org/b/id/{cover_i}-M.jpg"
                    if cover_i
                    else ""
                )
                key = doc.get("key", "")
                url = f"https://openlibrary.org{key}" if key else ""
                first_publish_year = doc.get("first_publish_year", "")
                snippet = (
                    f"{authors} ({first_publish_year})"
                    if authors
                    else f"Published {first_publish_year}"
                    if first_publish_year
                    else title
                )
                if title:
                    results.append(
                        SearchResult(
                            title=title,
                            url=url,
                            snippet=snippet,
                            search_type="books",
                            thumbnail=thumb,
                        )
                    )
            return results, None
        except (
            ValueError,
            TypeError,
            AttributeError,
            KeyError,
            IndexError,
            OSError,
            RuntimeError,
            ConnectionError,
            ImportError,
            TimeoutError,
        ) as ex:
            logger.warning(f"[{LOG_TAG}] OpenLibrary book fallback error: {ex}")
            return [], str(ex)
