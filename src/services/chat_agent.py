"""Agentic chat turn — DDGS tools, hard caps, one credit per user message.

The model gets six read-only tools over our real capabilities (five searches
+ page fetch). One reserve covers the WHOLE turn regardless of how many tool
calls run inside it (research recommendation: per-message, never per-tool).

Emit protocol (the chat screen consumes these, throttled):
    user                {"text"}
    assistant_start     {}
    text_partial        {"text"}          # full buffer so far, throttled by caller
    step_start          {"label", "id"}
    step_done           {"label", "id", "count"}
    step_error          {"label", "id", "error"}
    results             {"kind", "results: list[SearchResult]"}   # live card block
    text_final          {"text", "related", "served_by"}
    stopped             {}
    error               {"kind": credits|unavailable|midstream}
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
from collections.abc import Callable

from core.constants import (
    AGENT_MAX_ITERS,
    AGENT_MAX_TOOLS,
    AGENT_TIMEOUT_S,
    COST_CHAT,
)
from core.state import state
from services import agent_files, ai_service

logger = logging.getLogger(__name__)

# tool name -> SearchService.search type
TOOL_KINDS = {
    "search_web": "text",
    "search_images": "images",
    "search_videos": "videos",
    "search_news": "news",
    "search_books": "books",
}
SEARCH_TIMEOUT = 30.0
FETCH_TIMEOUT = 25.0

SYSTEM_PROMPT = (
    "You are DDGS AI, a private search assistant WITH TOOLS running inside the "
    "DDGS app. For anything current or factual, call your search_* tools first "
    "(pick the best category), then optionally fetch_page on at most 2 URLs to "
    "verify. Answer ONLY from tool results — never invent sources. Cite claims "
    "with [1], [2] … matching the order of the results you actually used. "
    "Keep answers 2-6 sentences unless the user asks for more. Always end with "
    "a final line exactly in this form:\n"
    "RELATED: query one | query two | query three\n"
    "(three short alternative search queries). "
    "You can also act for the user: save_page keeps a page as Markdown/HTML/text, "
    "download_media downloads a video (YouTube supported) or image, scrape_site "
    "crawls a site and saves every page, and schedule_scrape/cancel_scrape manage "
    "recurring crawls (they run while the app is open). Use them when the user asks. "
    "After saving or downloading, tell them the exact file paths. "
    "If no tool is needed (greetings, math, opinions), just answer."
)


def build_tools() -> list[dict]:
    """OpenAI function schemas for our six read-only tools."""

    def _fn(name: str, desc: str, props: dict, required: list[str]) -> dict:
        return {
            "type": "function",
            "function": {
                "name": name,
                "description": desc,
                "parameters": {
                    "type": "object",
                    "properties": props,
                    "required": required,
                    "additionalProperties": False,
                },
            },
        }

    query_prop = {"query": {"type": "string"}}
    count_prop = {
        "count": {"type": "integer", "minimum": 1, "maximum": 8},
    }
    return [
        _fn(
            "search_web",
            "Search the web for current or factual information. "
            "Returns title/url/snippet results.",
            {**query_prop, **count_prop},
            ["query"],
        ),
        _fn(
            "search_images",
            "Search images. Returns thumbnail/image results.",
            {**query_prop, "count": count_prop["count"]},
            ["query"],
        ),
        _fn(
            "search_videos",
            "Search videos. Returns title/url/duration/thumbnail results.",
            {**query_prop, "count": count_prop["count"]},
            ["query"],
        ),
        _fn(
            "search_news",
            "Search news. Returns title/url/snippet/published results.",
            {**query_prop, **count_prop},
            ["query"],
        ),
        _fn(
            "search_books",
            "Search books. Returns title/url/author results.",
            {**query_prop, "count": count_prop["count"]},
            ["query"],
        ),
        _fn(
            "fetch_page",
            "Fetch one URL as Markdown for grounding/summarizing. "
            "Prefer after search_web when you need the actual page content.",
            {"url": {"type": "string"}},
            ["url"],
        ),
        _fn(
            "save_page",
            "Save one page to the device as a file (Downloads/DDGS). "
            "format: markdown | html | text. Use when the user asks to keep, "
            "save, or archive a page.",
            {
                "url": {"type": "string"},
                "format": {"type": "string", "enum": ["markdown", "html", "text"]},
            },
            ["url"],
        ),
        _fn(
            "download_media",
            "Download a video (YouTube is resolved automatically) or an "
            "image/direct media file to the device (Downloads/DDGS).",
            {
                "url": {"type": "string"},
                "quality": {
                    "type": "string",
                    "enum": ["best", "1080p", "720p", "480p", "360p"],
                },
            },
            ["url"],
        ),
        _fn(
            "scrape_site",
            "Crawl a site: fetch the URL, follow same-site links, and save "
            "every page as files (Downloads/DDGS). Use when the user asks to "
            "scrape/crawl an entire site or save all pages under it.",
            {
                "url": {"type": "string"},
                "max_pages": {"type": "integer", "minimum": 1, "maximum": 8},
                "format": {"type": "string", "enum": ["markdown", "html", "text"]},
            },
            ["url"],
        ),
        _fn(
            "schedule_scrape",
            "Schedule a recurring crawl of a site (e.g. every hour). Runs "
            "while the app is open. Returns the next run time.",
            {
                "url": {"type": "string"},
                "interval_minutes": {"type": "integer", "minimum": 15, "maximum": 1440},
            },
            ["url", "interval_minutes"],
        ),
        _fn(
            "cancel_scrape",
            "Cancel a scheduled crawl by URL.",
            {"url": {"type": "string"}},
            ["url"],
        ),
    ]


def pretty_label(name: str, args: dict) -> str:
    """User-legible tool label — never raw JSON."""
    query = str(args.get("query") or "").strip()
    url = str(args.get("url") or "").strip()
    if name == "search_web":
        return f"Searching the web for “{query}”…"
    if name == "search_images":
        return f"Searching images for “{query}”…"
    if name == "search_videos":
        return f"Searching videos for “{query}”…"
    if name == "search_news":
        return f"Searching news for “{query}”…"
    if name == "search_books":
        return f"Searching books for “{query}”…"
    if name == "fetch_page":
        host = url.split("/")[2] if "//" in url else url
        return f"Fetching {host[:50]}…"
    if name == "save_page":
        fmt = str(args.get("format") or "markdown")
        host = url.split("/")[2] if "//" in url else url
        return f"Saving {host[:40]} as {fmt}…"
    if name == "download_media":
        host = url.split("/")[2] if "//" in url else url
        return f"Downloading media from {host[:40]}…"
    if name == "scrape_site":
        host = url.split("/")[2] if "//" in url else url
        return f"Crawling {host[:40]} and saving pages…"
    if name == "schedule_scrape":
        host = url.split("/")[2] if "//" in url else url
        return f"Scheduling a crawl of {host[:40]}…"
    if name == "cancel_scrape":
        return "Canceling scheduled crawl…"
    return f"Working ({name})…"


def _fmt(args: dict) -> str:
    return {
        "markdown": "text_markdown",
        "html": "text",
        "text": "text_plain",
    }.get(str(args.get("format") or "markdown"), "text_markdown")


def _storage():
    credits = getattr(state, "credit_service", None)
    return getattr(credits, "_storage", None) if credits else None


async def _persist_schedule() -> None:
    storage = _storage()
    if storage:
        await storage.set_scheduled_scrapes(json.dumps(state.scheduled_scrapes))


def _schedule(url: str, interval_minutes: int) -> dict:
    if not url.startswith(("http://", "https://")):
        raise ValueError("url must be http(s)")
    interval_minutes = max(15, min(int(interval_minutes or 60), 1440))
    state.scheduled_scrapes = [
        t for t in state.scheduled_scrapes if t.get("url") != url
    ]
    entry = {
        "url": url,
        "interval_minutes": interval_minutes,
        "next_run": time.time() + interval_minutes * 60,
        "last_run": None,
        "pages_saved": 0,
    }
    state.scheduled_scrapes = [*state.scheduled_scrapes, entry]
    return {"scheduled": entry, "note": "Runs while the app is open"}


def _cancel_schedule(url: str) -> dict:
    before = len(state.scheduled_scrapes)
    state.scheduled_scrapes = [
        t for t in state.scheduled_scrapes if t.get("url") != url
    ]
    return {"cancelled": url, "removed": before - len(state.scheduled_scrapes)}


class ChatCancelled(Exception):
    """User pressed Stop."""


_search_svc = None


def _svc():
    global _search_svc
    if _search_svc is None:
        from services.search_service import SearchService

        _search_svc = SearchService()
    return _search_svc


async def _dispatch(name: str, args: dict):
    """Run one tool. Returns (model_output, list[SearchResult])."""
    if name in TOOL_KINDS:
        query = str(args.get("query") or "")[:200]
        count = min(int(args.get("count") or 8), 8)
        progress = await asyncio.wait_for(
            _svc().search(TOOL_KINDS[name], query, ui=False), SEARCH_TIMEOUT
        )
        if progress.error and not progress.results:
            raise RuntimeError(str(progress.error)[:200])
        results = (progress.results or [])[:count]
        model_out = [
            {
                "title": r.title,
                "url": r.url,
                "snippet": (r.snippet or "")[:300],
            }
            for r in results
        ]
        return model_out, list(results)
    if name == "fetch_page":
        url = str(args.get("url") or "")
        if not url.startswith(("http://", "https://")):
            raise ValueError("url must be http(s)")
        res, err = await asyncio.wait_for(
            _svc().extract_url(url, fmt="text_markdown"), FETCH_TIMEOUT
        )
        if not res:
            raise RuntimeError(err or "fetch failed")
        return {"url": url, "content": str(res.get("content") or "")[:3000]}, []
    if name == "save_page":
        url = str(args.get("url") or "")
        if not url.startswith(("http://", "https://")):
            raise ValueError("url must be http(s)")
        fmt = _fmt(args)
        path = await asyncio.wait_for(
            agent_files.save_page(url, fmt=fmt), agent_files.FETCH_TIMEOUT * 2
        )
        return {"url": url, "saved_to": path}, []
    if name == "download_media":
        url = str(args.get("url") or "")
        if not url.startswith(("http://", "https://")):
            raise ValueError("url must be http(s)")
        path = await agent_files.download_media(
            url, quality=str(args.get("quality") or "best")
        )
        return {"url": url, "saved_to": path}, []
    if name == "scrape_site":
        url = str(args.get("url") or "")
        if not url.startswith(("http://", "https://")):
            raise ValueError("url must be http(s)")
        report = await agent_files.scrape_site(
            url, max_pages=int(args.get("max_pages") or 5), fmt=_fmt(args), svc=_svc()
        )
        return report, []
    if name == "schedule_scrape":
        return (
            _schedule(
                str(args.get("url") or ""), int(args.get("interval_minutes") or 60)
            ),
            [],
        )
    if name == "cancel_scrape":
        return _cancel_schedule(str(args.get("url") or "")), []
    raise ValueError(f"unknown tool: {name}")


async def run_turn(
    user_text: str,
    history: list[dict],
    emit: Callable[[str, dict], None],
    cancel: asyncio.Event,
    on_thought: Callable[[str], None] | None = None,
) -> None:
    """One full agent turn: reserve → tool loop → final answer → commit."""
    credits = getattr(state, "credit_service", None)
    if credits is None:
        emit("error", {"kind": "unavailable"})
        return
    tx = await credits.reserve(COST_CHAT)
    if tx is None:
        emit("error", {"kind": "credits", "balance": await credits.get_balance()})
        return

    emit("user", {"text": user_text})
    emit("assistant_start", {})

    messages: list[dict] = (
        [{"role": "system", "content": SYSTEM_PROMPT}]
        + history[-8:]
        + [{"role": "user", "content": user_text}]
    )
    tools = build_tools()
    seen_urls: list[str] = []
    served_by = ""
    content_parts: list[str] = []
    final_text = ""
    t0 = time.monotonic()
    iters = 0
    tools_used = 0

    def on_token(token: str) -> None:
        content_parts.append(token)
        emit("text_partial", {"text": "".join(content_parts)})

    try:
        while (
            iters < AGENT_MAX_ITERS
            and tools_used < AGENT_MAX_TOOLS
            and time.monotonic() - t0 < AGENT_TIMEOUT_S
        ):
            if cancel.is_set():
                raise ChatCancelled()
            iters += 1
            result = await ai_service.stream_llm(
                messages,
                on_token,
                tools=tools,
                on_thought=on_thought,
                model=getattr(state, "ai_model", "auto"),
            )
            served_by = result.get("served_by") or served_by
            finish = result.get("finish_reason") or ""
            tool_calls = result.get("tool_calls") or []

            if finish == "tool_calls" and tool_calls:
                assistant_msg: dict = {"role": "assistant", "tool_calls": tool_calls}
                if content_parts:
                    assistant_msg["content"] = "".join(content_parts)
                messages.append(assistant_msg)
                content_parts.clear()
                for tc in tool_calls:
                    if cancel.is_set():
                        raise ChatCancelled()
                    fn = tc.get("function") or {}
                    name = fn.get("name") or ""
                    try:
                        args = json.loads(fn.get("arguments") or "{}")
                    except ValueError:
                        args = {}
                    label = pretty_label(name, args)
                    emit("step_start", {"label": label, "id": tc.get("id", "")})
                    try:
                        model_out, results = await _dispatch(name, args)
                    except Exception as exc:
                        logger.info("tool %s failed: %r", name, exc)
                        emit(
                            "step_error",
                            {
                                "label": label,
                                "id": tc.get("id", ""),
                                "error": str(exc)[:140],
                            },
                        )
                        model_out = {"error": str(exc)[:300]}
                        results = []
                    else:
                        emit(
                            "step_done",
                            {
                                "label": label,
                                "id": tc.get("id", ""),
                                "count": len(results),
                            },
                        )
                        if results:
                            kind = {
                                "text": "web",
                                "images": "images",
                                "videos": "videos",
                                "news": "news",
                                "books": "books",
                            }.get(TOOL_KINDS.get(name, "text"), "web")
                            emit("results", {"kind": kind, "results": results})
                            for r in results:
                                if r.url and r.url not in seen_urls:
                                    seen_urls.append(r.url)
                    tools_used += 1
                    if name in ("schedule_scrape", "cancel_scrape"):
                        await _persist_schedule()
                    messages.append(
                        {
                            "role": "tool",
                            "tool_call_id": tc.get("id", ""),
                            "content": json.dumps(model_out, ensure_ascii=False)[:6000],
                        }
                    )
                continue  # next model call sees the tool outputs

            final_text = "".join(content_parts)
            break

        if cancel.is_set():
            raise ChatCancelled()
        if not final_text.strip():
            raise ai_service.AIUnavailable("empty model response")
        clean, related = ai_service.parse_related(final_text)
        emit(
            "text_final",
            {
                "text": ai_service.link_citations(clean, seen_urls),
                "related": related,
                "served_by": served_by,
            },
        )
        await credits.commit(tx)
    except ChatCancelled:
        try:
            await credits.rollback(tx)
        except Exception:
            logger.exception("rollback failed on cancel")
        emit("stopped", {"partial": "".join(content_parts)})
    except ai_service.AIMidStream:
        try:
            await credits.commit(tx)  # partial value was delivered
        except Exception:
            logger.exception("commit failed on midstream")
        emit("error", {"kind": "midstream", "partial": "".join(content_parts)})
    except ai_service.AIUnavailable as exc:
        try:
            await credits.rollback(tx)
        except Exception:
            logger.exception("rollback failed")
        logger.info("chat turn unavailable: %s", exc)
        emit("error", {"kind": "unavailable", "partial": "".join(content_parts)})
    except Exception:
        try:
            await credits.rollback(tx)
        except Exception:
            logger.exception("rollback failed")
        logger.exception("chat turn failed")
        emit("error", {"kind": "unavailable", "partial": ""})
