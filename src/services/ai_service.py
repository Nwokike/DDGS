"""AI service - embedded Kiri Router (auto-model first, free) → Kiri Gateway fallback.

Model choice belongs to the router (owner's directive: no auto logic in
the app). The app sends `state.ai_model` verbatim - default `auto`, the
router's own rotating catalog model - and the router handles ranking,
per-conversation stickiness and in-request failover itself (`auto_order`,
run.py). The app only fetches /v1/models to fill the model picker.

- Router discovery attaches to ANY Kiri router already listening in
  8082-8092 (the user's own instance) before embedding run.py ourselves;
  embed only when none exists.
- Streaming returns finish_reason + assembled `tool_calls` deltas so the
  chat agent can run DDGS tools (OpenAI streaming tool_calls contract:
  arguments arrive as string fragments per index - concatenate, parse at
  finish).
- `stream_llm` does the raw router→gateway failover with NO credit
  reservation (the agent reserves once per whole turn); `stream_chat` keeps
  the reserve→call→commit wrapper for single-shot calls (summaries).

Manual search/scraping never imports this module, so it can never spend
credits. Streaming is httpx SSE on both endpoints - AI never touches primp.
"""

from __future__ import annotations

import asyncio
import json
import logging
import re
import threading
import time
from collections.abc import Callable
from datetime import datetime

import httpx

from core.state import state

logger = logging.getLogger(__name__)

# ── Gateway - Akili's exact Worker secret/header (verified 200 on
#    api.kiri.ng/chat; no new secret to register) ─────────────────────────
GATEWAY_URL = "https://api.kiri.ng"
GATEWAY_SECRET = "mobile-v1"
USER_AGENT = "DDGSApp/2.0.0"

# ── Embedded/attached router ──────────────────────────────────────────────
ROUTER_HOST = "127.0.0.1"
ROUTER_BASE_PORT = 8082
ROUTER_SPAN = 10  # scan 8082..8092 for a running Kiri router before embedding
ROUTER_STICKY_COOLDOWN = 60.0  # prefer gateway for a while after router failure
# A full port-scan miss is remembered this long: the status watchdog ticks
# every 3s, and each miss would otherwise pay a serial 11-port scan.
PROBE_MISS_TTL = 30.0

ANSWER_MAX_TOKENS = 1400
TEMPERATURE = 0.4

class AIUnavailable(Exception):
    """No AI source could answer - callers degrade silently."""


class AIMidStream(Exception):
    """The source died after tokens were delivered - partial answer, no retry."""


class NotEnoughCredits(Exception):
    """Raised before any call when the local reserve fails."""

    def __init__(self, balance: int):
        self.balance = balance
        super().__init__(f"AI credits exhausted ({balance} left)")


# ── Router lifecycle: discover-and-attach, else embed ─────────────────────

_router_server = None  # only set when WE embedded it
_router_port: int | None = None
_router_lock = threading.Lock()
_router_failed_until = 0.0
_catalog: list[dict] = []  # snapshot of models ACTIVE at fetch/attach time
_catalog_fetched_at: float = 0.0  # 0 until the first successful /v1/models
_probe_miss_until = 0.0  # monotonic deadline of the last full-miss scan


def _hint(entry: dict) -> str:
    """Human hint: latency + rate-limit info from the router catalog."""
    parts: list[str] = []
    latency = entry.get("latency_ms")
    if isinstance(latency, int) and latency >= 0:
        parts.append(f"{latency}ms" if latency < 1000 else f"{latency / 1000:.1f}s")
    rate = entry.get("rate_hint") or {}
    if isinstance(rate, dict) and rate.get("label"):
        parts.append(str(rate["label"]))
    status = str(entry.get("status") or "active")
    if status == "rate limited":
        parts.append("rate limited right now")
    elif status == "failed":
        parts.append("failing right now")
    if entry.get("id") == "auto" and not parts:
        parts.append("Free tier, rotates across available models")
    return " · ".join(parts) or "free tier"


def snapshot_models() -> list[dict]:
    """Active chat-completion models (auto first, then by latency) with hints."""
    return [
        {
            "id": m.get("id"),
            "hint": _hint(m),
            "status": m.get("status", "active"),
        }
        for m in _catalog
    ]


def model_hint(model_id: str) -> str:
    for entry in _catalog:
        if entry.get("id") == model_id:
            return _hint(entry)
    return ""


async def _probe_existing_router() -> int | None:
    """Scan 8082..8092 for a live Kiri router (ours or the user's own).

    A full miss is remembered for PROBE_MISS_TTL so the 3-second status
    watchdog stops paying a serial 11-port scan (up to ~5.5s of refused
    sockets) on every tick while nothing is listening.
    """
    global _probe_miss_until
    if time.monotonic() < _probe_miss_until:
        return None
    async with httpx.AsyncClient(http2=False) as client:
        for port in range(ROUTER_BASE_PORT, ROUTER_BASE_PORT + ROUTER_SPAN + 1):
            try:
                resp = await client.get(
                    f"http://{ROUTER_HOST}:{port}/health", timeout=0.5
                )
                if (
                    resp.status_code == 200
                    and resp.json().get("adapter") == "kiri-router"
                ):
                    _probe_miss_until = 0.0
                    return port
            except Exception:
                pass  # closed port or not a router - keep scanning
    _probe_miss_until = time.monotonic() + PROBE_MISS_TTL
    return None


async def probe_router() -> tuple[str, int | None]:
    """Report the router's live status without starting anything.

    Returns (status, port) where status is one of:
      ready        attached and answering /health
      stopped      a port was known but nothing is answering now
      unavailable  no router, and none is embedded
      starting     embedded server is coming up but not yet healthy

    The picker turns this into an honest label, the same way LM Router's
    ModelPicker distinguishes "Starting gateway..." from "Gateway stopped".
    """
    with _router_lock:
        port = _router_port
    if port is None:
        # Cheap probe only: never embed a server just to report status.
        found = await _probe_existing_router()
        if found is None:
            return ("unavailable", None)
        return ("ready", found)
    try:
        async with httpx.AsyncClient(http2=False) as client:
            resp = await client.get(
                f"http://{ROUTER_HOST}:{port}/health", timeout=2.0
            )
        if resp.status_code == 200:
            return ("ready", port)
    except Exception as exc:
        logger.debug("router health probe failed on %s: %r", port, exc)
    return ("stopped", port)


async def ensure_router(*, verify: bool = False) -> int | None:
    """Attach to a running Kiri router, or embed one. Returns its port.

    `verify=True` health-checks the port we already hold before trusting
    it. Without it a stale port is returned forever, which made the
    picker's "Start router" action look like it did nothing. The picker
    calls it with verify=True; the normal request path does not, because
    paying a 2s probe on every turn is not worth it.
    """
    global _router_server, _router_port
    with _router_lock:
        if _router_port is not None:
            known = _router_port
        else:
            known = None
    if known is not None:
        if not verify:
            return known
        status, _port = await probe_router()
        if status == "ready":
            return known
        # The port is dead. Forget it so the normal attach path runs again.
        with _router_lock:
            if _router_port == known:
                _router_port = None
        logger.info("AI router on %s is gone; re-attaching", known)

    # Publish "starting" before the slow parts so the picker can say so.
    _publish_status("starting", None)

    existing = await _probe_existing_router()
    if existing is not None:
        _router_port = existing
        _publish_status("ready", existing)
        logger.info("AI router: attached to existing instance on %d", existing)
        return existing

    try:
        from services.router import run as router_run

        server, port = router_run.acquire_server(ROUTER_BASE_PORT, ROUTER_SPAN)
        if server is None:
            # Raced with another Kiri instance on the wanted port - attach.
            _router_port = port
            _publish_status("ready", port)
            logger.info("AI router: attached to instance on %d", port)
            return port
        server.access_log = False
        threading.Thread(target=server.serve_forever, daemon=True).start()
        with _router_lock:
            _router_server, _router_port = server, port
        _publish_status("ready", port)
        logger.info("AI router: embedded on %s:%d", ROUTER_HOST, port)
        return port
    except SystemExit:
        logger.warning(
            "AI router: no free port in %d..%d",
            ROUTER_BASE_PORT,
            ROUTER_BASE_PORT + ROUTER_SPAN,
        )
        _publish_status("unavailable", None)
        return None
    except Exception as exc:
        logger.warning("AI router: failed to start: %r", exc)
        _publish_status("unavailable", None)
        return None


def _publish_status(status: str, port: int | None) -> None:
    """Write router lifecycle to observable state, only on a real change.

    The watchdog ticks every 3 seconds; assigning unconditionally would
    repaint the whole UI on every tick for no reason.
    """
    from core.state import state

    if getattr(state, "ai_router_status", None) != status or (
        getattr(state, "ai_router_port", None) != port
    ):
        state.ai_router_status = status
        state.ai_router_port = port


def stop_router() -> None:
    """Stop ONLY an embedded router (never the user's own instance)."""
    global _router_server, _router_port
    with _router_lock:
        server, _router_server = _router_server, None
        _router_port = None
    if server is not None:
        try:
            server.shutdown()
            server.server_close()
            logger.info("AI router: stopped embedded instance")
        except Exception:
            pass
        _publish_status("stopped", None)


def shutdown() -> None:
    stop_router()


def _mark_router_failed() -> None:
    global _router_failed_until
    _router_failed_until = time.monotonic() + ROUTER_STICKY_COOLDOWN


async def _router_base() -> str | None:
    if time.monotonic() < _router_failed_until:
        return None
    port = await ensure_router()
    if port is None:
        return None
    return f"http://{ROUTER_HOST}:{port}/v1"


# ── Model catalog (picker display only - never used to pick) ──────────────


async def _fetch_catalog(client: httpx.AsyncClient, base: str) -> list[dict]:
    """Refresh the picker's snapshot of ACTIVE chat-completion models.

    This feeds snapshot_models() for the model picker and nothing else.
    The request path never consults it: model choice belongs to the router.
    """
    global _catalog, _catalog_fetched_at
    data: list[dict] = []
    for attempt in range(2):
        try:
            resp = await client.get(f"{base}/models", timeout=30.0)
            data = resp.json().get("data", [])
            break
        except Exception as exc:
            logger.warning(
                "AI router: model catalog failed (attempt %d): %r", attempt + 1, exc
            )
            if attempt == 0:
                await asyncio.sleep(1.0)
    if not data:
        return _catalog
    # Recorded even when nothing is chat-eligible, so the picker can tell
    # "not fetched yet" from "fetched, and there are no chat models".
    _catalog_fetched_at = time.monotonic()
    _catalog = [
        m
        for m in data
        if m.get("id")
        and str(m.get("status") or "active") == "active"
        and "chat.completion" in str(m.get("endpoint_type") or "")
    ]
    _catalog.sort(
        key=lambda m: (
            0 if str(m.get("id")).lower() == "auto" else 1,
            m.get("latency_ms")
            if isinstance(m.get("latency_ms"), int)
            else 10**9,
        )
    )
    return _catalog


async def refresh_catalog() -> list[dict]:
    """Attach if needed, then pull a fresh active-model snapshot (picker)."""
    try:
        port = await ensure_router()
        if port is None:
            return snapshot_models()
        async with httpx.AsyncClient(http2=False) as client:
            await _fetch_catalog(client, f"http://{ROUTER_HOST}:{port}/v1")
    except Exception as exc:
        logger.warning("catalog refresh failed: %r", exc)
    return snapshot_models()


# ── SSE consumption with tool_calls assembly ──────────────────────────────


def assemble_tool_calls(fragments: dict) -> list[dict]:
    """Turn per-index delta fragments into complete OpenAI tool_calls.

    fragments: {index: {"id": str, "name": str, "args": str}} - `arguments`
    accumulates as JSON string fragments across chunks; parsing happens at
    the caller once finish_reason == "tool_calls". Pure (unit-tested).
    """
    calls = []
    for idx in sorted(fragments):
        piece = fragments[idx]
        calls.append(
            {
                "id": piece.get("id") or f"call_{idx}",
                "type": "function",
                "function": {
                    "name": piece.get("name") or "",
                    "arguments": piece.get("args") or "",
                },
            }
        )
    return calls


async def _consume_sse(
    resp: httpx.Response,
    on_token: Callable[[str], None],
    collect_tools: bool,
    on_thought: Callable[[str], None] | None = None,
) -> tuple[str, list[dict] | None]:
    """Parse OpenAI-style SSE. Returns (finish_reason, tool_calls|None).

    Lenient per the SSE grammar: `data:` needs no space, consecutive
    `data:` lines join with a newline into one value, and keepalives or
    `event:`/`id:` lines are skipped. A value that parses as JSON on its
    own is dispatched immediately - how every provider this app talks to
    actually frames events - and buffering only engages for a genuinely
    partial value.
    """
    finish = ""
    fragments: dict = {}
    buffer: list[str] = []

    def _process(payload: str) -> str:
        """Handle one event. Returns ok | incomplete."""
        nonlocal finish
        try:
            chunk = json.loads(payload)
        except ValueError:
            return "incomplete"
        if "error" in chunk and not (chunk.get("choices")):
            raise AIUnavailable(str(chunk.get("error"))[:200])
        choices = chunk.get("choices") or [{}]
        choice = choices[0] or {}
        if choice.get("finish_reason"):
            finish = str(choice["finish_reason"])
        delta = choice.get("delta") or {}
        text = delta.get("content") or ""
        message = choice.get("message") or {}
        if not text:
            text = message.get("content") or ""
        if text:
            on_token(text)
        thought = (
            delta.get("reasoning_content")
            or delta.get("reasoning")
            or message.get("reasoning_content")
            or ""
        )
        if not thought:
            details = delta.get("reasoning_details")
            if isinstance(details, list):
                parts = []
                for item in details:
                    if isinstance(item, str):
                        parts.append(item)
                    elif isinstance(item, dict) and item.get("text"):
                        parts.append(str(item["text"]))
                thought = "".join(parts)
        if thought and on_thought:
            on_thought(thought)
        if collect_tools:
            for tc in delta.get("tool_calls") or []:
                idx = tc.get("index", 0)
                piece = fragments.setdefault(idx, {"id": "", "name": "", "args": ""})
                fn = tc.get("function") or {}
                if tc.get("id"):
                    piece["id"] = tc["id"]
                if fn.get("name"):
                    piece["name"] = fn["name"]
                if fn.get("arguments"):
                    piece["args"] += fn["arguments"]
            # some providers stream whole tool_calls only under message
            for tc in (choice.get("message") or {}).get("tool_calls") or []:
                idx = tc.get("index", len(fragments))
                fn = tc.get("function") or {}
                fragments[idx] = {
                    "id": tc.get("id") or f"call_{idx}",
                    "name": fn.get("name") or "",
                    "args": fn.get("arguments") or "",
                }
        return "ok"

    async for line in resp.aiter_lines():
        if not line.startswith("data:"):
            continue
        payload = line[5:]
        payload = payload.removeprefix(" ")
        if payload == "[DONE]":
            break
        buffer.append(payload)
        if _process("\n".join(buffer)) == "ok":
            buffer.clear()
    if buffer:
        # Trailing partial value: only real if it parses, else it is noise.
        _process("\n".join(buffer))
    tool_calls = assemble_tool_calls(fragments) if fragments else None
    if tool_calls and not finish:
        finish = "tool_calls"
    return finish, tool_calls


async def _stream_json_body(
    resp: httpx.Response,
    on_token: Callable[[str], None],
    on_thought: Callable[[str], None] | None = None,
) -> tuple[str, None]:
    body = resp.json()
    choices = body.get("choices") or [{}]
    choice = choices[0] or {}
    message = choice.get("message") or {}
    text = message.get("content") or choice.get("text", "")
    if text:
        on_token(text)
    if on_thought is not None:
        thought = message.get("reasoning") or message.get("reasoning_content") or ""
        if thought:
            on_thought(str(thought))
    return str(choice.get("finish_reason") or ""), None


# ── Router streaming (model passthrough) ──────────────────────────────────


async def _stream_router(
    client: httpx.AsyncClient,
    messages: list[dict],
    on_token: Callable[[str], None],
    tools: list[dict] | None,
    on_thought: Callable[[str], None] | None = None,
    model: str | None = None,
    max_tokens: int | None = None,
) -> dict:
    """One request, model passed through untouched.

    The router owns selection and failover: `auto` means the router picks,
    an explicit id means that model. A rejection reaching here is the
    router's final answer (it already failed over internally), so the app
    surfaces it honestly instead of rotating models itself.
    """
    base = await _router_base()
    if base is None:
        raise AIUnavailable("The Assistant is reconnecting. Try again shortly.")
    chosen = str(model or "auto").strip() or "auto"
    payload: dict = {
        "model": chosen,
        "messages": messages,
        "stream": True,
        "max_tokens": max_tokens or ANSWER_MAX_TOKENS,
        "temperature": TEMPERATURE,
    }
    if tools:
        payload["tools"] = tools
        payload["tool_choice"] = "auto"
    got_first = False
    try:
        async with client.stream(
            "POST",
            f"{base}/chat/completions",
            json=payload,
            headers={"Authorization": "Bearer any"},
            timeout=httpx.Timeout(180.0, connect=4.0),
        ) as resp:
            if resp.status_code >= 400:
                await resp.aread()
                detail = resp.content[:200].decode("utf-8", "replace")
                logger.info(
                    "router refused %s (HTTP %d): %s",
                    chosen,
                    resp.status_code,
                    detail[:120],
                )
                if resp.status_code == 429:
                    # The router already failed over internally; the whole
                    # free pool is capped. Busy, not broken - no cooldown.
                    raise AIUnavailable(
                        "Kiri's free tier is busy right now. Try again shortly."
                    )
                if resp.status_code >= 500:
                    _mark_router_failed()
                    raise AIUnavailable(
                        "The Assistant had a server problem. Try again shortly."
                    )
                # 4xx: the router answered; this request or model id was
                # wrong. The router is alive, so no cooldown either.
                raise AIUnavailable(
                    "The Assistant refused that request. Pick another model."
                )
            ctype = resp.headers.get("content-type", "")

            def _counting(token: str) -> None:
                nonlocal got_first
                got_first = True
                on_token(token)

            if "text/event-stream" in ctype:
                finish, tool_calls = await _consume_sse(
                    resp, _counting, bool(tools), on_thought
                )
            else:
                await resp.aread()
                got_first = True
                finish, tool_calls = await _stream_json_body(resp, _counting, on_thought)
        return {"finish_reason": finish, "tool_calls": tool_calls, "model": chosen}
    except AIUnavailable:
        raise
    except (
        httpx.TimeoutException,
        httpx.RequestError,
        ValueError,
        KeyError,
    ) as exc:
        _mark_router_failed()
        if got_first:
            raise AIMidStream(str(exc)) from exc
        logger.info("router unreachable for %s: %r", chosen, exc)
        raise AIUnavailable("Could not reach the Assistant.") from exc


# ── Gateway streaming ─────────────────────────────────────────────────────


async def _stream_gateway(
    client: httpx.AsyncClient,
    messages: list[dict],
    on_token: Callable[[str], None],
    tools: list[dict] | None,
    on_thought: Callable[[str], None] | None = None,
    model: str | None = None,
    max_tokens: int | None = None,
) -> dict:
    payload: dict = {
        "messages": messages,
        "task_type": "text",
        "stream": True,
        "max_tokens": max_tokens or ANSWER_MAX_TOKENS,
        "temperature": TEMPERATURE,
    }
    if tools:
        payload["tools"] = tools
        payload["tool_choice"] = "auto"
    headers = {"Authorization": f"Bearer {GATEWAY_SECRET}", "User-Agent": USER_AGENT}
    got_first = False
    attempts = 2  # SpanInsight-style: narrow retry (connect/502/503/504)
    last_exc: Exception | None = None
    for attempt in range(attempts):
        try:
            async with client.stream(
                "POST",
                f"{GATEWAY_URL}/chat",
                json=payload,
                headers=headers,
                timeout=httpx.Timeout(120.0, connect=10.0),
            ) as resp:
                if resp.status_code >= 400:
                    await resp.aread()
                    if resp.status_code in (502, 503, 504) and attempt + 1 < attempts:
                        await asyncio.sleep(0.5 * (2**attempt))
                        continue
                    logger.info("gateway HTTP %d", resp.status_code)
                    raise AIUnavailable(
                        "The Assistant could not answer. Try again shortly."
                    )
                ctype = resp.headers.get("content-type", "")

                def _counting(token: str) -> None:
                    nonlocal got_first
                    got_first = True
                    on_token(token)

                if "text/event-stream" in ctype:
                    finish, tool_calls = await _consume_sse(
                        resp, _counting, bool(tools), on_thought
                    )
                else:
                    await resp.aread()
                    got_first = True
                    finish, tool_calls = await _stream_json_body(resp, _counting, on_thought)
            return {
                "finish_reason": finish,
                "tool_calls": tool_calls,
                "model": model or "gateway auto",
            }
        except AIUnavailable:
            raise
        except (
            httpx.TimeoutException,
            httpx.RequestError,
            ValueError,
            KeyError,
        ) as exc:
            last_exc = exc
            if got_first:
                raise AIMidStream(str(exc)) from exc
            if attempt + 1 < attempts:
                await asyncio.sleep(0.5 * (2**attempt))
                continue
            break
    logger.info("gateway unreachable: %r", last_exc)
    raise AIUnavailable("Could not reach the Assistant.")


# ── Orchestration ─────────────────────────────────────────────────────────


async def stream_llm(
    messages: list[dict],
    on_token: Callable[[str], None],
    tools: list[dict] | None = None,
    on_thought: Callable[[str], None] | None = None,
    model: str | None = None,
    max_tokens: int | None = None,
) -> dict:
    """Raw router→gateway failover. NO credit handling (agent settles per step).

    Returns {"served_by", "model", "finish_reason", "tool_calls"|None}.
    `model` is what was requested: under `auto` the router picks internally
    and echoes `auto` back, so the app never needs to know the pick.
    Raises AIUnavailable (nothing delivered) or AIMidStream (partial).
    """
    try:
        async with httpx.AsyncClient(http2=False) as client:
            result = await _stream_router(
                client, messages, on_token, tools, on_thought, model, max_tokens
            )
        result["served_by"] = "router"
        return result
    except AIUnavailable as exc:
        logger.info("AI router unavailable (%s) - falling back to gateway", exc)
    except AIMidStream:
        raise
    async with httpx.AsyncClient(http2=False) as client:
        result = await _stream_gateway(
            client, messages, on_token, tools, on_thought, model, max_tokens
        )
    result["served_by"] = "gateway"
    return result


async def stream_chat(
    messages: list[dict],
    cost: int,
    on_token: Callable[[str], None],
    model: str | None = None,
    max_tokens: int | None = None,
) -> dict:
    """Single-shot metered call (cost 0 = free passive; >0 = reserve/settle)."""
    credits = getattr(state, "credit_service", None)
    if cost <= 0:
        # Free passive calls (search overview, page summary) skip credits.
        return await stream_llm(messages, on_token, model=model, max_tokens=max_tokens)
    if credits is None:
        raise AIUnavailable("Assistant credits are unavailable right now.")
    tx_id = await credits.reserve(cost)
    if tx_id is None:
        raise NotEnoughCredits(await credits.get_balance())
    try:
        result = await stream_llm(messages, on_token, model=model, max_tokens=max_tokens)
        await credits.commit(tx_id)
    except AIMidStream:
        # Tokens were delivered - charge fairly.
        await credits.commit(tx_id)
        raise
    except BaseException:
        try:
            await credits.rollback(tx_id)
        except Exception:
            logger.exception("credit rollback failed (tx=%s)", tx_id)
        raise
    return {"served_by": result.get("served_by", "")}


# ── Prompt builders + response parsing ────────────────────────────────────


def _clock_line() -> str:
    """What day it is, as a human would say it.

    The model's training data ends well before today, so a prompt asking
    what happened "this week" was answered from its knowledge cutoff and
    confidently returned last year's news. LM Router solves this the same
    way; one line at the top of the system prompt removes the whole class
    of stale-date answers.
    """
    moment = datetime.now().astimezone()
    offset = moment.strftime("%z")
    if len(offset) == 5:  # +0100 -> +01:00
        offset = f"{offset[:3]}:{offset[3:]}"
    zone = moment.tzname() or "local"
    return (
        f"Current date and time: {moment.strftime('%Y-%m-%d %H:%M:%S')} "
        f"({offset} {zone}, {moment.strftime('%A')}). "
        "Treat 'today', 'this week' and 'recently' relative to THIS "
        "timestamp, never your training data."
    )


def with_clock(system_prompt: str) -> str:
    """Prepend the clock line to a system prompt."""
    base = (system_prompt or "").strip()
    return _clock_line() + "\n\n" + base


def build_overview_messages(query: str, sources: list[dict]) -> list[dict]:
    """Passive answer-over-snippets prompt for the search-results overview."""
    numbered = "\n".join(
        f"[{i + 1}] {s.get('title', '')} - {s.get('url', '')}\n    {s.get('snippet', '')}"
        for i, s in enumerate(sources[:8])
    )
    system = (
        "You are DDGS AI. Answer the question ONLY from the numbered sources. "
        "Cite claims with [n] matching the source numbers. 2-5 direct sentences. "
        "End with a final line exactly in this form:\n"
        "RELATED: query one | query two | query three"
    )
    return [
        {"role": "system", "content": with_clock(system)},
        {"role": "user", "content": f"Sources:\n{numbered}\n\nQuestion: {query}"},
    ]


def build_summary_messages(title: str, content: str) -> list[dict]:
    """Page summarization prompt (content already extracted locally)."""
    system = (
        "You are DDGS AI. Summarize the page below in at most 5 tight bullets, "
        "then one short takeaway line. Facts only, no preamble, no citations."
    )
    body = content[:8000]
    return [
        {"role": "system", "content": with_clock(system)},
        {"role": "user", "content": f"Title: {title}\n\n{body}"},
    ]


_RELATED_RE = re.compile(r"\n?\s*RELATED:\s*(.+)\s*$", re.IGNORECASE | re.DOTALL)
_CITE_RE = re.compile(r"\[(\d{1,2})\]")


def parse_related(text: str) -> tuple[str, list[str]]:
    """Split the trailing RELATED: line off an answer. Returns (clean, queries)."""
    match = _RELATED_RE.search(text)
    if not match:
        return text.strip(), []
    clean = text[: match.start()].strip()
    queries = [q.strip() for q in match.group(1).split("|") if q.strip()][:4]
    return clean, queries


def link_citations(text: str, urls: list[str]) -> str:
    """Rewrite bare [n] citations into markdown links so they tap through."""

    def _sub(match: re.Match) -> str:
        idx = int(match.group(1))
        if 1 <= idx <= len(urls) and urls[idx - 1]:
            return f"[{idx}]({urls[idx - 1]})"
        return match.group(0)

    return _CITE_RE.sub(_sub, text)
