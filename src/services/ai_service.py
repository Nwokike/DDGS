"""AI service — embedded Kiri Router (free, primary) with Kiri Gateway fallback.

Architecture (DDGS 2.0 "AI Edition"):
- PRIMARY:  the Kiri Router (vendored run.py) embedded in-process as a daemon
            thread on 127.0.0.1 — zero keys, zero upstream cost, OpenAI-compatible.
- FALLBACK: https://api.kiri.ng/chat (X-App-Secret) on router failure.

Credits are the user-facing economy (SpanInsight model): reserve -> stream ->
commit on success / rollback on failure for EVERY AI action, regardless of
which source served it. Manual search/scraping never imports or calls this
module, so it can never spend credits.

Streaming is httpx SSE on both endpoints — AI never touches primp (the
PRIMP_CRASH path).
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

# ── Gateway (registered in the Kiri Cloudflare Worker, siblings:
#    mobile-v1 / spaninsight-mobile-v1) ─────────────────────────────────────
GATEWAY_URL = "https://api.kiri.ng"
GATEWAY_SECRET = "ddgs-mobile-v1"
USER_AGENT = "DDGSApp/2.0.0"

# ── Embedded router ───────────────────────────────────────────────────────
ROUTER_HOST = "127.0.0.1"
ROUTER_BASE_PORT = 8082
ROUTER_SPAN = 10
ROUTER_STICKY_COOLDOWN = 60.0  # prefer gateway for a while after router failure
ROUTER_MODEL_TTL = 300.0  # seconds to trust the cached model list

ANSWER_MAX_TOKENS = 1400
SUMMARY_MAX_TOKENS = 900
TEMPERATURE = 0.4


class AIUnavailable(Exception):
    """No AI source could answer — callers degrade silently to classic results."""


class AIMidStream(Exception):
    """The source died after tokens were delivered — partial answer, no retry."""


class NotEnoughCredits(Exception):
    """Raised before any call when the local reserve fails."""

    def __init__(self, balance: int):
        self.balance = balance
        super().__init__(f"AI credits exhausted ({balance} left)")


# ── Embedded router lifecycle ─────────────────────────────────────────────

_router_server = None
_router_port: int | None = None
_router_lock = threading.Lock()
_router_failed_until = 0.0
_router_models: list[str] = []
_router_models_at = 0.0


def ensure_router() -> int | None:
    """Start the embedded router once. Returns its port or None if unavailable."""
    global _router_server, _router_port
    with _router_lock:
        if _router_port is not None:
            return _router_port
        try:
            from services.router import run as router_run

            server, port = router_run.acquire_server(ROUTER_BASE_PORT, ROUTER_SPAN)
            if server is None:
                # A Kiri router is already running on the wanted port — attach.
                _router_port = port
                logger.info("AI router: attached to existing instance on %d", port)
                return port
            server.access_log = False
            threading.Thread(target=server.serve_forever, daemon=True).start()
            _router_server, _router_port = server, port
            logger.info("AI router: embedded on 127.0.0.1:%d", port)
            return port
        except SystemExit:
            logger.warning(
                "AI router: no free port in %d..%d",
                ROUTER_BASE_PORT,
                ROUTER_BASE_PORT + ROUTER_SPAN,
            )
            return None
        except Exception as exc:
            logger.warning("AI router: failed to start: %s", exc)
            return None


def stop_router() -> None:
    """Shut the embedded router down (called from page.on_close)."""
    global _router_server, _router_port
    with _router_lock:
        server, _router_server, _router_port = _router_server, None, None
    if server is not None:
        try:
            server.shutdown()
            server.server_close()
            logger.info("AI router: stopped")
        except Exception:
            pass


def shutdown() -> None:
    """Best-effort teardown for app exit."""
    stop_router()


def _router_base() -> str | None:
    if time.monotonic() < _router_failed_until:
        return None
    port = ensure_router()
    if port is None:
        return None
    return f"http://{ROUTER_HOST}:{port}/v1"


async def _pick_model(client: httpx.AsyncClient, base: str) -> str | None:
    """Lowest-latency active free model from the router catalog (cached)."""
    global _router_models, _router_models_at
    if _router_models and time.monotonic() - _router_models_at < ROUTER_MODEL_TTL:
        return _router_models[0]
    try:
        resp = await client.get(f"{base}/models", timeout=10.0)
        data = resp.json().get("data", [])
    except Exception as exc:
        logger.warning("AI router: model catalog failed: %r", exc)
        return None
    usable = [
        m
        for m in data
        if m.get("id") and m.get("status", "active") == "active" and m.get("is_free", True)
    ]
    if not usable:
        usable = [m for m in data if m.get("id")]
    usable.sort(key=lambda m: m.get("latency_ms") or 10**9)
    _router_models = [m["id"] for m in usable]
    _router_models_at = time.monotonic()
    return _router_models[0] if _router_models else None


def _invalidate_models() -> None:
    global _router_models_at
    _router_models_at = 0.0


def _mark_router_failed() -> None:
    global _router_failed_until
    _router_failed_until = time.monotonic() + ROUTER_STICKY_COOLDOWN


# ── SSE consumption (shared shape for both sources) ───────────────────────


async def _consume_sse(resp: httpx.Response, on_token: Callable[[str], None]) -> None:
    """Parse OpenAI-style SSE; forward content deltas only (reasoning dropped)."""
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
        if "error" in chunk:
            raise AIUnavailable(str(chunk.get("error"))[:200])
        choices = chunk.get("choices") or [{}]
        delta = choices[0].get("delta") or {}
        text = delta.get("content") or ""
        if not text:
            message = choices[0].get("message") or {}
            text = message.get("content") or ""
        if text:
            on_token(text)


async def _stream_json_body(resp: httpx.Response, on_token: Callable[[str], None]) -> None:
    """Non-SSE fallback: server answered with a plain JSON completion."""
    body = resp.json()
    choices = body.get("choices") or [{}]
    text = ((choices[0].get("message") or {}).get("content")) or choices[0].get(
        "text", ""
    )
    if text:
        on_token(text)


async def _stream_router(
    client: httpx.AsyncClient, messages: list[dict], on_token: Callable[[str], None]
) -> None:
    base = _router_base()
    if base is None:
        raise AIUnavailable("router cooling down")
    model = await _pick_model(client, base)
    if not model:
        raise AIUnavailable("no router models available")
    payload = {
        "model": model,
        "messages": messages,
        "stream": True,
        "max_tokens": ANSWER_MAX_TOKENS,
        "temperature": TEMPERATURE,
    }
    got_first = False
    try:
        async with client.stream(
            "POST",
            f"{base}/chat/completions",
            json=payload,
            headers={"Authorization": "Bearer any"},
            timeout=httpx.Timeout(180.0, connect=3.0),
        ) as resp:
            if resp.status_code >= 400:
                await resp.aread()
                if resp.status_code == 400 and b"model" in resp.content:
                    _invalidate_models()  # stale catalog — refresh next call
                raise AIUnavailable(f"router HTTP {resp.status_code}")
            ctype = resp.headers.get("content-type", "")
            if "text/event-stream" in ctype:
                def _counting(token: str) -> None:
                    nonlocal got_first
                    got_first = True
                    on_token(token)

                await _consume_sse(resp, _counting)
            else:
                await resp.aread()
                got_first = True
                await _stream_json_body(resp, on_token)
    except AIUnavailable:
        _mark_router_failed()
        raise
    except (httpx.TimeoutException, httpx.RequestError, ValueError, KeyError) as exc:
        _mark_router_failed()
        if got_first:
            raise AIMidStream(str(exc)) from exc
        raise AIUnavailable(f"router failed: {exc}") from exc


async def _stream_gateway(
    client: httpx.AsyncClient, messages: list[dict], on_token: Callable[[str], None]
) -> None:
    payload = {
        "messages": messages,
        "task_type": "text",
        "stream": True,
        "max_tokens": ANSWER_MAX_TOKENS,
        "temperature": TEMPERATURE,
    }
    headers = {"X-App-Secret": GATEWAY_SECRET, "User-Agent": USER_AGENT}
    got_first = False
    attempts = 2  # SpanInsight-style: narrow retry, connect/502/503/504 only
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
                    await _consume_sse(resp, _counting)
                else:
                    await resp.aread()
                    got_first = True
                    await _stream_json_body(resp, on_token)
            return
        except AIUnavailable:
            raise
        except (httpx.TimeoutException, httpx.RequestError, ValueError, KeyError) as exc:
            last_exc = exc
            if got_first:
                raise AIMidStream(str(exc)) from exc
            if attempt + 1 < attempts:
                await asyncio.sleep(0.5 * (2**attempt))
                continue
            break
    raise AIUnavailable(f"gateway failed: {last_exc}")


# ── Orchestration ─────────────────────────────────────────────────────────


async def stream_chat(
    messages: list[dict], cost: int, on_token: Callable[[str], None]
) -> dict:
    """Stream one AI action router-first with credit-metered gateway fallback.

    Returns {"served_by": "router"|"gateway"}.
    Raises NotEnoughCredits, AIUnavailable (nothing delivered) or
    AIMidStream (partial answer already delivered — do not retry).
    """
    credits = getattr(state, "credit_service", None)
    if credits is None:
        raise AIUnavailable("credit service not ready")

    balance = await credits.get_balance()
    tx_id = await credits.reserve(cost)
    if tx_id is None:
        raise NotEnoughCredits(balance)

    served_by = "router"
    try:
        try:
            async with httpx.AsyncClient(http2=False) as client:
                await _stream_router(client, messages, on_token)
        except AIUnavailable as exc:
            logger.info("AI router unavailable (%s) — falling back to gateway", exc)
            served_by = "gateway"
            async with httpx.AsyncClient(http2=False) as client:
                await _stream_gateway(client, messages, on_token)
        await credits.commit(tx_id)
    except BaseException:
        try:
            await credits.rollback(tx_id)
        except Exception:
            logger.exception("credit rollback failed (tx=%s)", tx_id)
        raise
    logger.info("AI action served by %s (cost %d, tx=%s)", served_by, cost, tx_id)
    return {"served_by": served_by}


# ── Prompt builders + response parsing ────────────────────────────────────


def build_answer_messages(
    query: str,
    sources: list[dict],
    mode: str = "standard",
    thread: list[dict] | None = None,
) -> list[dict]:
    """Answer-over-sources prompt. Sources are 1-indexed and citations must match."""
    numbered = "\n".join(
        f"[{i + 1}] {s.get('title', '')} — {s.get('url', '')}\n    {s.get('snippet', '')}"
        for i, s in enumerate(sources[:8])
    )
    depth = (
        "Give a thorough synthesis comparing sources."
        if mode == "deep"
        else "Answer in 2-5 sentences, direct and concrete."
    )
    system = (
        "You are DDGS AI, a private search assistant. "
        "Answer ONLY from the numbered sources below. "
        "Cite claims with [n] matching the source numbers. "
        f"{depth} "
        "End with a final line exactly in this format:\n"
        "RELATED: query one | query two | query three\n"
        "(three short alternative search queries, no numbering)."
    )
    messages: list[dict] = [{"role": "system", "content": system}]
    for turn in thread or []:
        messages.append(
            {"role": turn.get("role", "assistant"), "content": turn.get("text", "")}
        )
    user = f"Sources:\n{numbered}\n\nQuestion: {query}"
    messages.append({"role": "user", "content": user})
    return messages


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


def build_deep_messages(
    query: str, sources: list[dict], pages: list[str]
) -> list[dict]:
    """Premium Deep answer: synthesis over the top pages' extracted text."""
    numbered = []
    for i, s in enumerate(sources[:3]):
        body = (pages[i] if i < len(pages) else "") or s.get("snippet", "")
        numbered.append(
            f"[{i + 1}] {s.get('title', '')} — {s.get('url', '')}\n{body[:2500]}"
        )
    system = (
        "You are DDGS AI in Deep mode. Synthesize a thorough answer across the "
        "full page texts below, noting where sources agree or conflict. "
        "Cite with [1]/[2]/[3]. End with a final line exactly:\n"
        "RELATED: query one | query two | query three"
    )
    return [
        {"role": "system", "content": system},
        {
            "role": "user",
            "content": f"Pages:\n{chr(10).join(numbered)}\n\nQuestion: {query}",
        },
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
