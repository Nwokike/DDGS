"""Agentic chat turn - DDGS tools, hard caps, COST_STEP per model step.

The model gets 11 tools over our real capabilities: five searches plus
fetch, save, download, scrape, schedule and cancel. Six are read-only and
five need the user to approve them first.

Billing is COST_STEP credits per MODEL STEP, not per user message: a turn
that takes two steps to answer costs 2 * COST_STEP. The Settings copy and
the receipt are both generated from that constant, so they cannot drift
away from what is charged.

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
import os
import time
from collections.abc import Callable
from typing import Any

from core.constants import (
    AGENT_HISTORY_MESSAGES,
    AGENT_MAX_ITERS,
    AGENT_MAX_TOOLS,
    AGENT_TIMEOUT_S,
    COST_STEP,
    TOOL_OUTPUT_CAP,
)
from core.state import state
from services import agent_files, ai_service

logger = logging.getLogger(__name__)

# tool name -> SearchService.search type
# Everything that mutates the user's world needs approval. cancel_scrape
# was missing from this set: it deletes a recurring crawl and persists the
# change, so a hallucinated or prompt-injected call could silently remove
# a schedule the user set up.
_WRITE_TOOLS = {
    "save_page",
    "download_media",
    "scrape_site",
    "schedule_scrape",
    "cancel_scrape",
}

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
    "verify. Answer ONLY from tool results - never invent sources. Cite claims "
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
    "If a tool returns an error or 'No results found', retry ONCE with a "
    "broader query or a different search tool, then answer with what you have. "
    "When search_images returns image_url values, show the single best match "
    "in your reply as ![short description](image_url) so the user sees the "
    "picture, not just a description of it - one image, not a gallery. "
    "If no tool is needed (greetings, math, opinions), just answer."
)


def build_tools() -> list[dict]:
    """OpenAI function schemas for our 11 tools (six read-only, five gated)."""

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
            "Search images. Returns image_url (the direct picture file) plus "
            "the page url. Show one to the user by embedding it in your "
            "markdown reply as ![description](image_url).",
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
    """User-legible tool label: verb first, no quotes, no trailing ellipsis.

    The renderer shows labels verbatim, so every decorative element that
    used to be stripped back off in chat_screen is gone at the source.
    """
    query = str(args.get("query") or "").strip()
    url = str(args.get("url") or "").strip()
    if name == "search_web":
        return f"Searching the web: {query[:80]}"
    if name == "search_images":
        return f"Searching images: {query[:80]}"
    if name == "search_videos":
        return f"Searching videos: {query[:80]}"
    if name == "search_news":
        return f"Searching news: {query[:80]}"
    if name == "search_books":
        return f"Searching books: {query[:80]}"
    if name == "fetch_page":
        host = url.split("/")[2] if "//" in url else url
        return f"Fetching {host[:50]}"
    if name == "save_page":
        fmt = str(args.get("format") or "markdown")
        host = url.split("/")[2] if "//" in url else url
        return f"Saving {host[:40]} as {fmt}"
    if name == "download_media":
        host = url.split("/")[2] if "//" in url else url
        return f"Downloading media from {host[:40]}"
    if name == "scrape_site":
        host = url.split("/")[2] if "//" in url else url
        return f"Crawling {host[:40]}"
    if name == "schedule_scrape":
        host = url.split("/")[2] if "//" in url else url
        return f"Scheduling a crawl of {host[:40]}"
    if name == "cancel_scrape":
        return "Cancelling scheduled crawl"
    return f"Running {name}"


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
        if name == "search_images":
            # An image result's `url` is the page that hosts the picture, not
            # the picture. Hand the model the direct file as well, or it can
            # only describe the image and never show it.
            model_out = []
            for r in results:
                direct = r.image_url or r.thumbnail or ""
                item = {"title": r.title, "url": r.url}
                if direct:
                    item["image_url"] = direct
                if r.snippet:
                    item["snippet"] = r.snippet[:80]
                model_out.append(item)
            return model_out, list(results)
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


async def settle_turn(credits, tx_id: str | None, steps: int) -> int:
    """Charge COST_STEP credits per delivered step (COST_STEP * steps). Never breaks the user's
    work: a finished/partial message is always settled (overdraft clamps at
    zero); zero delivered steps refunds the hold entirely."""
    amount = max(0, steps) * COST_STEP
    if not tx_id:
        if amount:
            return await credits.charge(amount)
        return await credits.get_balance()
    if steps <= 0:
        await credits.rollback(tx_id)
        return await credits.get_balance()
    return await credits.commit_amount(tx_id, amount)


def _charged_steps(steps: int, content_parts: list[str]) -> int:
    """Steps to bill: one floor whenever the user actually saw text.

    Every terminal branch settles through this rule. The Stop button
    delivers CancelledError before `steps` increments, so a branch billing
    raw steps refunded delivered tokens; a crash or dropped connection did
    the same. Delivered work is worth one step, whatever ended the turn.
    """
    delivered = bool("".join(content_parts).strip())
    return max(steps, 1) if delivered else steps


def _error_text(exc: BaseException) -> str:
    """A message a human can act on for any exception.

    `str(TimeoutError())` is the empty string, and the tool row falls back
    to "no results" when the error is empty - so a 30-second search stall
    was reported to the user as "no results". That is both wrong and
    unactionable. Name the exception when it has no message.
    """
    text = str(exc).strip()
    if text:
        return text[:300]
    if isinstance(exc, TimeoutError):
        return "timed out"
    if isinstance(exc, asyncio.CancelledError):
        return "cancelled"
    name = type(exc).__name__
    return name if name else "failed"


def approval_detail(name: str, args: dict) -> str:
    """The arguments a user needs before approving a write, as plain text.

    `pretty_label` deliberately shows only a host, so the old approval card
    asked people to bless a recurring 8-page crawl every 15 minutes on a
    URL they never saw. This is what the label hides.
    """
    url = str(args.get("url") or "").strip()
    parts: list[str] = []
    if url:
        parts.append(url)
    if name == "download_media":
        quality = str(args.get("quality") or "").strip()
        if quality:
            parts.append(f"quality: {quality}")
    if name == "scrape_site":
        pages = args.get("max_pages")
        if pages:
            parts.append(f"up to {pages} pages")
        fmt = str(args.get("format") or "").strip()
        if fmt:
            parts.append(f"saved as {fmt}")
    if name == "save_page":
        fmt = str(args.get("format") or "markdown")
        parts.append(f"saved as {fmt}")
    if name == "schedule_scrape":
        try:
            interval = int(args.get("interval_minutes") or 60)
        except (TypeError, ValueError):
            interval = 60
        parts.append(f"every {interval} minutes")
        pages = args.get("max_pages")
        if pages:
            parts.append(f"up to {pages} pages per run")
    if name == "cancel_scrape":
        target = url or "a scheduled crawl"
        parts = [f"cancelling {target}"]
    return " · ".join(parts)


def tool_outcome(name: str, out: object) -> str:
    """A short, human-readable consequence of a write tool.

    Write tools return a report dict instead of a result list, so
    `count = len(results)` was always 0 and the UI rendered a bare green
    tick with no evidence anything happened - no file, no page count, no
    path. The system prompt tells the model to report exact paths; this
    puts the same fact in the step row where the user can see it without
    reading the model's prose.
    """
    if not isinstance(out, dict):
        return ""
    if out.get("saved_to"):
        return f"saved to {os.path.basename(str(out['saved_to']))}"
    saved = out.get("saved")
    if isinstance(saved, list):
        text = f"{len(saved)} page{'' if len(saved) == 1 else 's'} saved"
        failed = out.get("failed")
        if isinstance(failed, list) and failed:
            text += f", {len(failed)} failed"
        return text
    removed = out.get("removed")
    if isinstance(removed, int):
        if removed <= 0:
            return "nothing to cancel"
        return f"{removed} removed"
    scheduled = out.get("scheduled")
    if isinstance(scheduled, dict):
        return f"every {scheduled.get('interval_minutes')} minutes"
    return ""


async def run_turn(
    user_text: str,
    history: list[dict],
    emit: Callable[[str, dict], None],
    cancel: asyncio.Event,
    on_thought: Callable[[str], None] | None = None,
    ask_confirm: Callable[[str], Any] | None = None,
) -> None:
    """One agent turn - COST_STEP credits per model step, settled on every exit.

    Soft metering: a low balance is never a mid-run kill switch; the turn
    always finishes (balance may clamp to 0). A 0 balance starts blocked.
    """
    credits = getattr(state, "credit_service", None)
    # The question is recorded before any gate: an out-of-credits turn
    # still shows the user what they asked, and Retry can re-send it.
    emit("user", {"text": user_text})
    if credits is None:
        emit("error", {"kind": "unavailable", "steps": 0, "cost": 0})
        return
    balance = await credits.get_balance()
    if balance <= 0:
        emit("error", {"kind": "credits", "balance": 0, "steps": 0, "cost": 0})
        return
    # Best-effort hold; at balance 1 the hold fails and we run hold-less
    # (settlement then charges directly). Credits must never block the work.
    tx = await credits.reserve(COST_STEP)

    emit("assistant_start", {})
    if balance < COST_STEP * 3:
        emit(
            "nudge",
            {"text": "Low credit balance. This message finishes regardless."},
        )

    messages: list[dict] = (
        # The clock line matters here more than anywhere: the model's
        # training data ends before today, so "this week" without a date
        # was answered from its knowledge cutoff.
        [{"role": "system", "content": ai_service.with_clock(SYSTEM_PROMPT)}]
        + history[-AGENT_HISTORY_MESSAGES:]
        + [{"role": "user", "content": user_text[:2000]}]
    )
    tools = build_tools()
    seen_urls: list[str] = []
    served_by = ""
    used_model = ""
    content_parts: list[str] = []
    parts: list[str] = []
    final_text = ""
    steps = 0
    tools_used = 0
    t0 = time.monotonic()
    empty_retried = False
    max_tokens: int | None = None

    def on_token(token: str) -> None:
        if cancel.is_set():
            raise ChatCancelled()
        parts.append(token)
        content_parts.append(token)
        emit("text_partial", {"text": "".join(content_parts)})

    try:
        while steps < AGENT_MAX_ITERS and time.monotonic() - t0 < AGENT_TIMEOUT_S:
            if cancel.is_set():
                raise ChatCancelled()
            if steps > 0 and tx:
                await credits.reserve_more(tx, COST_STEP)  # best-effort, never blocks
            try:
                result = await ai_service.stream_llm(
                    messages,
                    on_token,
                    tools=tools,
                    on_thought=on_thought,
                    model=getattr(state, "ai_model", "auto"),
                    max_tokens=max_tokens,
                )
                steps += 1
            except ai_service.AIMidStream:
                steps += 1
                raise
            served_by = result.get("served_by") or served_by
            used_model = result.get("model") or used_model
            finish = result.get("finish_reason") or ""
            tool_calls = result.get("tool_calls") or []
            if finish == "tool_calls" and tool_calls:
                assistant_msg: dict = {"role": "assistant", "tool_calls": tool_calls}
                if parts:
                    assistant_msg["content"] = "".join(parts)
                messages.append(assistant_msg)
                parts.clear()
                content_parts.clear()
                for tc in tool_calls:
                    if cancel.is_set():
                        raise ChatCancelled()
                    if tools_used >= AGENT_MAX_TOOLS:
                        # The assistant already asked for these calls in the
                        # message we appended above, so every one of them
                        # needs a matching role:tool reply. Breaking here
                        # left the transcript with tool_calls and no tool
                        # responses, which the API rejects as invalid.
                        for remaining in tool_calls[
                            tool_calls.index(tc) :
                        ]:
                            messages.append(
                                {
                                    "role": "tool",
                                    "tool_call_id": remaining.get("id", ""),
                                    "content": json.dumps(
                                        {
                                            "error": "tool limit reached; "
                                            "nothing else was run"
                                        }
                                    ),
                                }
                            )
                        break
                    fn = tc.get("function") or {}
                    name = fn.get("name") or ""
                    try:
                        args = json.loads(fn.get("arguments") or "{}")
                    except ValueError:
                        args = {}
                    label = pretty_label(name, args)
                    emit("step_start", {"label": label, "id": tc.get("id", "")})
                    if name in _WRITE_TOOLS and ask_confirm is not None:
                        allowed = await ask_confirm(label, approval_detail(name, args))
                        if not allowed:
                            emit(
                                "step_error",
                                {
                                    "label": label,
                                    "id": tc.get("id", ""),
                                    "error": "declined",
                                },
                            )
                            tools_used += 1
                            messages.append(
                                {
                                    "role": "tool",
                                    "tool_call_id": tc.get("id", ""),
                                    "content": '{"error": "user declined this action"}',
                                }
                            )
                            continue
                    try:
                        model_out, results = await _dispatch(name, args)
                    except Exception as exc:
                        logger.info("tool %s failed: %r", name, exc)
                        emit(
                            "step_error",
                            {
                                "label": label,
                                "id": tc.get("id", ""),
                                "error": _error_text(exc),
                            },
                        )
                        model_out = {"error": _error_text(exc)}
                        results = []
                    else:
                        emit(
                            "step_done",
                            {
                                "label": label,
                                "id": tc.get("id", ""),
                                "count": len(results),
                                "outcome": tool_outcome(name, model_out),
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
                    messages.append(
                        {
                            "role": "tool",
                            "tool_call_id": tc.get("id", ""),
                            "content": json.dumps(model_out, ensure_ascii=False)[
                                :TOOL_OUTPUT_CAP
                            ],
                        }
                    )
                    if name in ("schedule_scrape", "cancel_scrape"):
                        await _persist_schedule()
                continue  # next model call sees the tool outputs

            final_text = "".join(parts)
            if (
                not final_text.strip()
                and finish == "length"
                and not empty_retried
                and steps < AGENT_MAX_ITERS
            ):
                # Reasoning models can burn the entire budget before any text
                # appears - retry once with a bigger budget, same step count.
                empty_retried = True
                max_tokens = (max_tokens or ai_service.ANSWER_MAX_TOKENS) * 2
                messages.append(
                    {
                        "role": "user",
                        "content": "Your previous reply hit the token limit "
                        "before any text appeared. Answer again, briefly.",
                    }
                )
                continue
            break

        if cancel.is_set():
            raise ChatCancelled()
        if not final_text.strip():
            # The model was called and said nothing. Charging a user for an
            # empty bubble is the kind of thing that makes a paywall feel
            # dishonest, so an answer-less turn is not settled: settle 0,
            # which rolls the whole hold back.
            await settle_turn(credits, tx, 0)
            logger.info(
                "chat turn produced no answer after %d step(s); not charged", steps
            )
            emit(
                "error",
                {
                    "kind": "empty",
                    "model": used_model,
                    "steps": 0,
                    "cost": 0,
                },
            )
            return
        clean, related = ai_service.parse_related(final_text)
        charge = _charged_steps(steps, content_parts)
        emit(
            "text_final",
            {
                "text": ai_service.link_citations(clean, seen_urls),
                "related": related,
                "served_by": served_by,
                "model": used_model,
                "steps": charge,
                "cost": charge * COST_STEP,
            },
        )
        await settle_turn(credits, tx, charge)
    except ChatCancelled:
        # on_token raises the cancel before stream_llm returns, so `steps`
        # is still 0 even though tokens reached the screen. Refunding that
        # would give away delivered work: a model call happened, it just
        # did not finish. _charged_steps applies the floor.
        charge = _charged_steps(steps, content_parts)
        await settle_turn(credits, tx, charge)
        emit(
            "stopped",
            {
                "partial": "".join(content_parts),
                "steps": charge,
                "cost": charge * COST_STEP,
            },
        )
    except ai_service.AIMidStream:
        charge = _charged_steps(steps, content_parts)
        await settle_turn(credits, tx, charge)  # partial work delivered - charge it
        emit(
            "error",
            {
                "kind": "midstream",
                "partial": "".join(content_parts),
                "steps": charge,
                "cost": charge * COST_STEP,
            },
        )
    except ai_service.AIUnavailable as exc:
        charge = _charged_steps(steps, content_parts)
        await settle_turn(credits, tx, charge)
        logger.info("chat turn unavailable: %s", exc)
        emit(
            "error",
            {
                "kind": "unavailable",
                # ai_service messages are already consumer-facing
                # (terse, no internals) - show the router's own words.
                "message": str(exc).strip(),
                "partial": "".join(content_parts),
                "steps": charge,
                "cost": charge * COST_STEP,
            },
        )
    except asyncio.CancelledError:
        # Hard cancel (the Stop button). CancelledError is a BaseException,
        # so it escapes `except Exception` entirely and would leave the
        # reservation un-settled until the auto-rollback fired. This is the
        # branch Stop actually lands in: settle by what was delivered, then
        # let the cancellation through.
        charge = _charged_steps(steps, content_parts)
        await settle_turn(credits, tx, charge)
        logger.info("chat turn cancelled after %d step(s)", charge)
        emit(
            "stopped",
            {
                "partial": "".join(content_parts),
                "steps": charge,
                "cost": charge * COST_STEP,
            },
        )
        raise
    except Exception:
        charge = _charged_steps(steps, content_parts)
        await settle_turn(credits, tx, charge)
        logger.exception("chat turn failed")
        emit(
            "error",
            {
                "kind": "unavailable",
                "partial": "".join(content_parts),
                "steps": charge,
                "cost": charge * COST_STEP,
            },
        )
