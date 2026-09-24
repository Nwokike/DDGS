"""AI service — embedded Kiri Router (auto-model first, free) → Kiri Gateway fallback.

v2 (chat redesign):
- Router discovery attaches to ANY Kiri router already listening in
  8082-8092 (the user's own instance — e.g. Node runtime on 8084) before
  embedding run.py ourselves; embed only when none exists.
- Model choice: the catalog's `auto` chat-completion model first (owner's
  directive — "stick to it so we never have issues"), then healthy
  chat-completion models by latency; per-request rotation over the top
  candidates on 400/401/429/ModelError before failing over to the gateway.
- Streaming returns finish_reason + assembled `tool_calls` deltas so the
  chat agent can run DDGS tools (OpenAI streaming tool_calls contract:
  arguments arrive as string fragments per index — concatenate, parse at
  finish).
- `stream_llm` does the raw router→gateway failover with NO credit
  reservation (the agent reserves once per whole turn); `stream_chat` keeps
  the reserve→call→commit wrapper for single-shot calls (summaries).

Manual search/scraping never imports this module, so it can never spend
credits. Streaming is httpx SSE on both endpoints — AI never touches primp.
"""

from __future__ import annotations

import asyncio
import json
import logging
import re
import threading
import time
from collections.abc import Callable

import httpx

from core.state import state

logger = logging.getLogger(__name__)

# ── Gateway — Akili's exact Worker secret/header (verified 200 on
#    api.kiri.ng/chat; no new secret to register) ─────────────────────────
GATEWAY_URL = "https://api.kiri.ng"
GATEWAY_SECRET = "mobile-v1"
USER_AGENT = "DDGSApp/2.0.0"

# ── Embedded/attached router ──────────────────────────────────────────────
ROUTER_HOST = "127.0.0.1"
ROUTER_BASE_PORT = 8082
ROUTER_SPAN = 10  # scan 8082..8092 for a running Kiri router before embedding
ROUTER_STICKY_COOLDOWN = 60.0  # prefer gateway for a while after router failure
ROUTER_MODEL_TTL = 300.0
ROUTER_CANDIDATES = 3  # models to try per request before failing over

ANSWER_MAX_TOKENS = 1400
TEMPERATURE = 0.4


class AIUnavailable(Exception):
    """No AI source could answer — callers degrade silently."""


class AIMidStream(Exception):
    """The source died after tokens were delivered — partial answer, no retry."""


class NotEnoughCredits(Exception):
    """Raised before any call when the local reserve fails."""

    def __init__(self, balance: int):
        self.balance = balance
        super().__init__(f"AI credits exhausted ({balance} left)")


class _RouterModelError(Exception):
    """Retryable per-model router rejection (400/401/429/ModelError)."""

    def __init__(self, status: int, detail: str = ""):
        self.status = status
        super().__init__(f"router model rejected ({status}) {detail}")


# ── Router lifecycle: discover-and-attach, else embed ─────────────────────

_router_server = None  # only set when WE embedded it
_router_port: int | None = None
_router_lock = threading.Lock()
_router_failed_until = 0.0
_router_models: list[str] = []
_router_models_at = 0.0
_catalog: list[dict] = []  # snapshot of models ACTIVE at fetch/attach time


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
    """Scan 8082..8092 for a live Kiri router (ours or the user's own)."""
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
                    return port
            except Exception:
                pass  # closed port or not a router — keep scanning
    return None


async def ensure_router() -> int | None:
    """Attach to a running Kiri router, or embed one. Returns its port."""
    global _router_server, _router_port
    with _router_lock:
        if _router_port is not None:
            return _router_port

    existing = await _probe_existing_router()
    if existing is not None:
        _router_port = existing
        logger.info("AI router: attached to existing instance on %d", existing)
        return existing

    try:
        from services.router import run as router_run

        server, port = router_run.acquire_server(ROUTER_BASE_PORT, ROUTER_SPAN)
        if server is None:
            # Raced with another Kiri instance on the wanted port — attach.
            _router_port = port
            logger.info("AI router: attached to instance on %d", port)
            return port
        server.access_log = False
        threading.Thread(target=server.serve_forever, daemon=True).start()
        with _router_lock:
            _router_server, _router_port = server, port
        logger.info("AI router: embedded on %s:%d", ROUTER_HOST, port)
        return port
    except SystemExit:
        logger.warning(
            "AI router: no free port in %d..%d",
            ROUTER_BASE_PORT,
            ROUTER_BASE_PORT + ROUTER_SPAN,
        )
        return None
    except Exception as exc:
        logger.warning("AI router: failed to start: %r", exc)
        return None


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


# ── Model choice ──────────────────────────────────────────────────────────


def rank_models(data: list[dict]) -> list[str]:
    """Ordered model candidates: `auto` first, then healthy chat models.

    Pure function (unit-tested). endpoint types seen in the wild:
    '/chat.completion', '/response', '/systemone' — only chat-completion
    models are safe for /v1/chat/completions without translation.
    """

    def is_chat(m: dict) -> bool:
        return "chat.completion" in str(m.get("endpoint_type") or "")

    def active(m: dict) -> bool:
        return str(m.get("status") or "active") == "active"

    def latency(m: dict):
        value = m.get("latency_ms")
        return value if isinstance(value, int) else 10**9

    usable = [m for m in data if m.get("id")]
    autos = [m for m in usable if str(m.get("id")).lower() == "auto" and active(m)]
    chat_active = [m for m in usable if is_chat(m) and active(m)]
    others_active = [m for m in usable if active(m) and m not in chat_active]
    chat_active.sort(key=latency)
    others_active.sort(key=latency)
    ordered: list[dict] = (
        autos
        + chat_active
        + others_active
        + [m for m in usable if m not in autos + chat_active + others_active]
    )
    seen: set[str] = set()
    out: list[str] = []
    for m in ordered:
        mid = str(m["id"])
        if mid not in seen:
            seen.add(mid)
            out.append(mid)
    return out


async def _fetch_candidates(
    client: httpx.AsyncClient, base: str, force: bool = False
) -> list[str]:
    """Model candidates for this request (cached, `auto` first).

    Also snapshots the ACTIVE chat-completion models for the picker
    (see snapshot_models).
    """
    global _router_models, _router_models_at, _catalog
    if (
        not force
        and _router_models
        and time.monotonic() - _router_models_at < ROUTER_MODEL_TTL
    ):
        return _router_models[:ROUTER_CANDIDATES]
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
        return []
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
    _router_models = rank_models(data)
    _router_models_at = time.monotonic()
    return _router_models[:ROUTER_CANDIDATES]


async def refresh_catalog() -> list[dict]:
    """Attach if needed, then pull a fresh active-model snapshot (picker)."""
    try:
        port = await ensure_router()
        if port is None:
            return snapshot_models()
        async with httpx.AsyncClient(http2=False) as client:
            await _fetch_candidates(
                client, f"http://{ROUTER_HOST}:{port}/v1", force=True
            )
    except Exception as exc:
        logger.warning("catalog refresh failed: %r", exc)
    return snapshot_models()


def invalidate_models() -> None:
    global _router_models_at
    _router_models_at = 0.0


# ── SSE consumption with tool_calls assembly ──────────────────────────────


def assemble_tool_calls(fragments: dict) -> list[dict]:
    """Turn per-index delta fragments into complete OpenAI tool_calls.

    fragments: {index: {"id": str, "name": str, "args": str}} — `arguments`
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
    """Parse OpenAI-style SSE. Returns (finish_reason, tool_calls|None)."""
    finish = ""
    fragments: dict = {}
    async for line in resp.aiter_lines():
        if not line.startswith("data: "):
            continue
        data = line[6:]
        if data == "[DONE]":
            break
        try:
            chunk = json.loads(data)
        except ValueError:
            continue
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
                    piece["name"] = (
                        (piece["name"] + fn["name"]) if False else fn["name"]
                    )
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


# ── Router streaming (multi-candidate) ────────────────────────────────────


async def _stream_router(
    client: httpx.AsyncClient,
    messages: list[dict],
    on_token: Callable[[str], None],
    tools: list[dict] | None,
    on_thought: Callable[[str], None] | None = None,
    model: str | None = None,
    max_tokens: int | None = None,
) -> dict:
    base = await _router_base()
    if base is None:
        raise AIUnavailable("router cooling down")
    candidates = await _fetch_candidates(client, base)
    if not candidates:
        raise AIUnavailable("no router models available")
    if model:
        # Explicit user pick: try it, then fall back to auto once if it is
        # rate-limited/missing — never blindly rotate off a chosen model.
        picked = (
            [model] + (["auto"] if model != "auto" and "auto" in candidates else [])
        )
        candidates = [c for c in picked if c] or candidates

    last_error: Exception | None = None
    for candidate in candidates:
        payload: dict = {
            "model": candidate,
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
                    if (
                        resp.status_code in (400, 401, 429, 500, 502, 503, 504)
                        or "Model" in detail
                    ):
                        # Retryable per-model rejection (rate limit / overload /
                        # unknown model) → rotate through candidates. A generic
                        # 400 that isn't model-related means the request itself
                        # is wrong (e.g. tools unsupported) — not worth retrying.
                        if resp.status_code == 400 and "model" not in detail.lower():
                            raise AIUnavailable(f"router rejected request: {detail}")
                        last_error = _RouterModelError(resp.status_code, detail)
                        invalidate_models()
                        continue
                    raise AIUnavailable(f"router HTTP {resp.status_code}")
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
            return {"finish_reason": finish, "tool_calls": tool_calls, "model": candidate}
        except AIUnavailable:
            _mark_router_failed()
            raise
        except _RouterModelError as exc:
            last_error = exc
            continue
        except (
            httpx.TimeoutException,
            httpx.RequestError,
            ValueError,
            KeyError,
        ) as exc:
            _mark_router_failed()
            if got_first:
                raise AIMidStream(str(exc)) from exc
            last_error = exc
            break  # connectivity is model-independent — go to gateway
    _mark_router_failed()
    raise AIUnavailable(f"router exhausted candidates: {last_error}")


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
                    raise AIUnavailable(f"gateway HTTP {resp.status_code}")
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
            return {"finish_reason": finish, "tool_calls": tool_calls}
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
    raise AIUnavailable(f"gateway failed: {last_exc}")


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

    Returns {"served_by", "finish_reason", "tool_calls"|None}.
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
        logger.info("AI router unavailable (%s) — falling back to gateway", exc)
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
        raise AIUnavailable("credit service not ready")
    tx_id = await credits.reserve(cost)
    if tx_id is None:
        raise NotEnoughCredits(await credits.get_balance())
    try:
        result = await stream_llm(messages, on_token, model=model)
        await credits.commit(tx_id)
    except AIMidStream:
        # Tokens were delivered — charge fairly.
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


def build_overview_messages(query: str, sources: list[dict]) -> list[dict]:
    """Passive answer-over-snippets prompt for the search-results overview."""
    numbered = "\n".join(
        f"[{i + 1}] {s.get('title', '')} — {s.get('url', '')}\n    {s.get('snippet', '')}"
        for i, s in enumerate(sources[:8])
    )
    system = (
        "You are DDGS AI. Answer the question ONLY from the numbered sources. "
        "Cite claims with [n] matching the source numbers. 2-5 direct sentences. "
        "End with a final line exactly in this form:\n"
        "RELATED: query one | query two | query three"
    )
    return [
        {"role": "system", "content": system},
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
        {"role": "system", "content": system},
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
