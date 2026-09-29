"""The kani backend: the agent loop is kani's, wrapped not rebuilt.

Owner decision (Phase 6): kani[openai] speaks the OpenAI wire our
embedded router uses; NO MCP, never in scope; the gateway fallback is
DROPPED - the router is the single AI source. chat_agent keeps every
outer contract it always had (emit protocol, credits per model step,
RELATED/citations, the approval gate, step rows); this module owns the
turn mechanics: engine construction, tool serialization and the
full_round iteration.

Design rules for this backend (our own):
- the thought-tap SSE tee (services.reasoning) so the Thinking block
  still sees the reasoning deltas kani itself throws away;
- the model string passed to the engine verbatim - `auto` is the
  router's to resolve, nothing here substitutes it;
- cancellation at manager boundaries: on_token raising stops a stream
  mid-flight, and a boundary check runs before every model round.
  Never abandon kani's async-for from outside mid-chunk;
- the openai exception ladder mapped onto this app's own words.

Byte-compatibility with the hand-rolled SSE path it replaces:
- one billable step == one model stream. kani yields a StreamManager
  per model round and a DummyStream per tool result; only model rounds
  count, reserve and charge.
- text buffers reset after a tool round (on_round_reset), so an
  intermediate "let me search..." never leaks into the final answer.
- the step cap and the wall-clock cap are checked at round boundaries.
  A manager that has been yielded but not iterated has made no request
  yet, so breaking there costs no HTTP at all.
- 429 / 5xx / 4xx / connect keep the exact consumer strings the router
  path used today; a connection break after a token of THIS step raises
  AIMidStream (and counts the step, like the old AIMidStream branch),
  before one raises AIUnavailable.
"""

from __future__ import annotations

import asyncio
import logging
import time
from collections.abc import Awaitable, Callable
from contextvars import ContextVar
from dataclasses import dataclass
from typing import Any

import httpx
import openai
from kani import AIFunction, ChatMessage, Kani

from core.constants import (
    AGENT_HISTORY_MESSAGES,
    AGENT_MAX_ITERS,
    AGENT_TIMEOUT_S,
    TOOL_OUTPUT_CAP,
)
from services import ai_service
from services.ai_service import AIMidStream, AIUnavailable
from services.reasoning import ReasoningEngine, ThoughtTap, build_thought_client
from services.tokenizer import tokenizer_or_heuristic

logger = logging.getLogger(__name__)

# The router serves chat completions to models whose context windows we
# do not know (`auto`, the free catalog). This budget is far above what
# a 6-message transcript can reach, so kani never evicts history.
DEFAULT_CONTEXT = 131072

# The tool_call_id of the call currently executing, carried into the
# AIFunction body (kani does not pass it down). ContextVar, not a plain
# attribute: kani runs a tool batch with asyncio.gather, and each child
# task reads its own context.
_call_id: ContextVar[str] = ContextVar("ddgs_tool_call_id", default="")


class DDGSKani(Kani):
    """Kani that exposes the active tool_call_id to the tool body.

    The chat screen matches step_done to step_start by id (falling back
    to "running"), so a row without its id never closes. Subclassing is
    the only hook kani leaves for this; the loop itself stays kani's.
    """

    async def do_function_call(self, call, tool_call_id: str | None = None):
        token = _call_id.set(str(tool_call_id or ""))
        try:
            return await super().do_function_call(call, tool_call_id)
        finally:
            _call_id.reset(token)


@dataclass(frozen=True)
class ToolSpec:
    """One tool as chat_agent defines it: schema for the model, code for us.

    `run` receives the parsed arguments and returns the exact JSON text
    the model sees (already serialized and capped). It never raises -
    every failure becomes an error payload, like the old dispatch did.
    """

    name: str
    desc: str
    parameters: dict
    run: Callable[[dict], Awaitable[str]]


def call_id() -> str:
    """The tool_call_id of the call currently executing ("" outside one)."""
    return _call_id.get()


def build_functions(specs: list[ToolSpec]) -> list[AIFunction]:
    """kani AIFunctions from our specs, executing one at a time.

    kani runs a tool batch with asyncio.gather; our tools were always
    sequential (one download, one schedule write, ordered step rows), so
    a per-batch lock keeps that contract. Schemas go through verbatim:
    json_schema is the same `parameters` document the old payload sent.
    """
    lock = asyncio.Lock()
    out: list[AIFunction] = []
    for spec in specs:

        async def inner(spec: ToolSpec = spec, **kwargs: Any) -> str:
            async with lock:
                return await spec.run(kwargs)

        out.append(
            AIFunction(
                inner,
                name=spec.name,
                desc=spec.desc,
                json_schema=spec.parameters,
                # Paragraph-aware cap (plan B2): kani truncates at a
                # paragraph boundary and appends "..." - a blind slice
                # used to cut tool JSON mid-token.
                auto_truncate=TOOL_OUTPUT_CAP,
            )
        )
    return out


def _to_history(history: list[dict]) -> list[ChatMessage]:
    """OpenAI-dict transcript -> kani messages, trimmed like before."""
    out: list[ChatMessage] = []
    for item in (history or [])[-AGENT_HISTORY_MESSAGES:]:
        if not isinstance(item, dict):
            continue
        content = item.get("content")
        if not isinstance(content, str) or not content.strip():
            continue
        role = str(item.get("role") or "")
        if role == "user":
            out.append(ChatMessage.user(content))
        elif role == "assistant":
            out.append(ChatMessage.assistant(content))
    return out


async def _build_engine(
    model: str, on_thought: Callable[[str], None] | None
) -> tuple[ReasoningEngine, ThoughtTap]:
    """One engine per turn: router base, thought tap, bounded timeouts.

    Same wire the old hand-rolled client built: `Bearer any`, the DDGS
    UA (router.kiri.ng answers 403 to default library agents), 180s
    read / 4s connect, two retries. api_type is explicit because `auto`
    and the free catalog match no known model prefix.
    """
    base = await ai_service._router_base()
    if base is None:
        raise AIUnavailable("The Assistant is reconnecting. Try again shortly.")
    tap = ThoughtTap(on_thought)
    timeout = httpx.Timeout(180.0, connect=4.0)
    raw = build_thought_client(timeout=timeout, max_retries=2, tap=tap)
    client = openai.AsyncOpenAI(
        api_key="any",
        base_url=base,
        http_client=raw,
        max_retries=2,
        timeout=timeout,
    )
    engine = ReasoningEngine(
        client=client,
        model=model,
        api_type="chat_completions",
        max_context_size=DEFAULT_CONTEXT,
        # Never let kani's lazy tokenizer touch a cold tiktoken cache:
        # that BPE download has no timeout and used to stall a turn.
        tokenizer=tokenizer_or_heuristic(model),
        temperature=ai_service.TEMPERATURE,
        tap=tap,
    )
    return engine, tap


def _usage_of(message: Any, text: str, model: str) -> dict | None:
    """Exact in/out token usage for the receipt (plan B1).

    Primary source: the router echoes stream usage (kani always asks
    with stream_options.include_usage). Fallback: the local tokenizer
    counts the answer we actually showed - prompt side then stays
    unknown rather than guessed.
    """
    extra = getattr(message, "extra", None) or {}
    raw = extra.get("openai_usage")
    if isinstance(raw, dict) and (raw.get("total_tokens") or raw.get("completion_tokens")):
        return {
            "in": int(raw.get("prompt_tokens") or 0),
            "out": int(raw.get("completion_tokens") or 0),
        }
    if text.strip():
        try:
            encoder = tokenizer_or_heuristic(model)
            return {"out": len(encoder.encode(text))}
        except Exception:
            return None
    return None


def _finish_of(completion: Any) -> str:
    """finish_reason off the raw OpenAI completion, best-effort."""
    try:
        raw = getattr(completion, "openai_completion", None)
        choices = getattr(raw, "choices", None) or []
        if choices:
            return str(choices[0].finish_reason or "")
    except Exception:
        pass
    return ""


def _raise_mapped(exc: BaseException, *, delivered: bool) -> None:
    """openai's exception ladder -> this app's exact consumer words.

    Mirrors the old _stream_router branches one for one: 429 is a busy
    pool, 5xx marks the router failed, other 4xx means the router
    answered and refused (no cooldown), connection trouble marks it
    failed too - and anything after a token of THIS step was delivered
    is an AIMidStream, so the caller charges for the work shown.
    """
    if isinstance(exc, (AIUnavailable, AIMidStream)):
        raise exc
    if isinstance(exc, openai.APIStatusError):
        if exc.status_code == 429:
            raise AIUnavailable(
                "Kiri's free tier is busy right now. Try again shortly."
            ) from exc
        if exc.status_code >= 500:
            ai_service._mark_router_failed()
            raise AIUnavailable(
                "The Assistant had a server problem. Try again shortly."
            ) from exc
        raise AIUnavailable(
            "The Assistant refused that request. Pick another model."
        ) from exc
    if isinstance(exc, (openai.APIConnectionError, openai.APIError)):
        ai_service._mark_router_failed()
        if delivered:
            raise AIMidStream(str(exc)) from exc
        logger.info("router unreachable: %r", exc)
        raise AIUnavailable("Could not reach the Assistant.") from exc
    raise exc


async def run_turn(
    user_text: str,
    history: list[dict],
    *,
    system_prompt: str,
    specs: list[ToolSpec],
    cancel: asyncio.Event,
    on_token: Callable[[str], None],
    on_thought: Callable[[str], None] | None = None,
    on_round_reset: Callable[[], None] | None = None,
    on_model_step: Callable[[], Awaitable[None]] | None = None,
    on_steps: Callable[[int], None] | None = None,
    model: str | None = None,
    max_tokens: int | None = None,
    max_iters: int = AGENT_MAX_ITERS,
    timeout_s: float = AGENT_TIMEOUT_S,
) -> dict:
    """Run one full agent turn through kani's full_round_stream.

    Returns {"text", "steps", "model", "served_by"} - the same facts the
    old stream_llm loop produced. Raises chat_agent's ChatCancelled,
    AIUnavailable or AIMidStream; the caller settles credits exactly as
    it always did. on_token may raise to stop the turn mid-stream;
    on_round_reset fires after a tool round so the caller can drop its
    partial buffer; on_model_step runs before every model call after the
    first (the credit reserve for that step); on_steps mirrors every
    count change so an exception path bills the same steps this loop
    counted (a mid-stream break bills the step it delivered).
    """
    from services.chat_agent import ChatCancelled

    chosen = str(model or "auto").strip() or "auto"
    query = user_text[:2000]
    engine, tap = await _build_engine(chosen, on_thought)
    kani = DDGSKani(
        engine,
        system_prompt=system_prompt or None,
        chat_history=_to_history(history),
        functions=build_functions(specs) if specs else None,
        # kani consults this only when a tool body itself raises; ours
        # never do (they return error payloads), but an unknown-tool
        # correction should keep the tools available for the retry.
        retry_attempts=1,
    )

    t0 = time.monotonic()
    steps = 0
    message: Any = None
    empty_retried = False
    budget = max_tokens or ai_service.ANSWER_MAX_TOKENS
    round_parts: list[str] = []
    final_text = ""

    try:
        async for manager in kani.full_round_stream(
            query,
            # Plan B3: after N tool rounds kani strips the tools for one
            # final round, so an over-cap turn ends with an answer built
            # from what it has instead of the old empty bubble.
            max_function_rounds=max(0, max_iters - 1),
            max_tokens=budget,
        ):
            if cancel.is_set():
                raise ChatCancelled()
            if time.monotonic() - t0 > timeout_s or steps >= max_iters:
                # Today's loop conditions, checked where a boundary
                # exists. The yielded-but-uniterated next manager has
                # made no request yet, so stopping here is free.
                break
            if "function" in str(getattr(manager, "role", "")).lower():
                # Tool result: its body already ran inside kani's gather
                # and emitted its own step rows. Nothing to count.
                await manager.message()
                continue
            if steps and on_model_step is not None:
                await on_model_step()
            delivered = False
            try:
                async for chunk in manager:
                    if chunk:
                        delivered = True
                        round_parts.append(chunk)
                        on_token(chunk)
                message = await manager.message()
            except ChatCancelled:
                raise
            except Exception as exc:
                if delivered:
                    # A step that put tokens on the screen is billable,
                    # exactly like the old `steps += 1` AIMidStream branch.
                    steps += 1
                    if on_steps is not None:
                        on_steps(steps)
                _raise_mapped(exc, delivered=delivered)
                raise  # _raise_mapped always raises; keeps flow honest
            steps += 1
            if on_steps is not None:
                on_steps(steps)
            if message.tool_calls:
                # Intermediate round: this text never belongs to the
                # final answer - clear ours and tell the caller to clear
                # its partial buffer (the emit shows the next round afresh).
                round_parts.clear()
                if on_round_reset is not None:
                    on_round_reset()
                continue
            final_text = "".join(round_parts)
            if not final_text.strip():
                # message already bound; usage rides below
                finish = _finish_of(await manager.completion())
                if (
                    finish == "length"
                    and not empty_retried
                    and steps < max_iters
                ):
                    # A reasoning model can burn the whole budget before
                    # any text appears: retry once with double, same cap.
                    empty_retried = True
                    budget = (max_tokens or ai_service.ANSWER_MAX_TOKENS) * 2
                    kani.chat_history.append(
                        ChatMessage.user(
                            "Your previous reply hit the token limit before "
                            "any text appeared. Answer again, briefly."
                        )
                    )
                    continue
            break
    except ChatCancelled:
        raise
    except asyncio.CancelledError:
        raise
    except (openai.APIError, AIUnavailable, AIMidStream) as exc:
        # Anything openai can still throw outside a stream maps onto the
        # same words; a local bug instead falls through raw to the
        # caller's generic branch (no invented network message).
        _raise_mapped(exc, delivered=False)
        raise

    if cancel.is_set():
        raise ChatCancelled()
    return {
        "text": final_text,
        "steps": steps,
        "model": tap.last_model or chosen,
        "served_by": "router",
        "usage": _usage_of(message, final_text, chosen),
    }


async def complete(
    messages: list[dict],
    on_token: Callable[[str], None],
    *,
    model: str | None = None,
    max_tokens: int | None = None,
) -> dict:
    """One tool-less shot: the search overview and page summaries.

    Same messages-in contract stream_chat always had (system first, then
    user/assistant), same streaming, no tools, no step counting - those
    calls are free and settle nothing.
    """
    from services.chat_agent import ChatCancelled

    chosen = str(model or "auto").strip() or "auto"
    system = ""
    body: list[dict] = []
    for item in messages or []:
        if not isinstance(item, dict):
            continue
        if str(item.get("role") or "") == "system" and not system:
            system = str(item.get("content") or "")
            continue
        body.append(item)
    engine, tap = await _build_engine(chosen, None)
    kani = Kani(
        engine,
        system_prompt=system or None,
        chat_history=_to_history(body),
    )
    manager = kani.chat_round_stream(
        None, max_tokens=max_tokens or ai_service.ANSWER_MAX_TOKENS
    )
    delivered = False
    try:
        async for chunk in manager:
            if chunk:
                delivered = True
                on_token(chunk)
        message = await manager.message()
    except ChatCancelled:
        raise
    except Exception as exc:
        _raise_mapped(exc, delivered=delivered)
        raise
    return {
        "text": message.text or "",
        "model": tap.last_model or chosen,
        "served_by": "router",
    }
