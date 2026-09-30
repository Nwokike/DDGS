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
from typing import Any, override

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

# The system prompt and the eleven tool schemas are byte-identical on
# every turn - exactly the prefix a prompt cache is for. Probed against
# the live router: accepted (plan B7).
_CACHE_WIRE = {"prompt_cache_key": "ddgs-agent-system-v1"}

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

    @override
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


def _chat_messages(
    items: list[dict], *, limit: int | None = AGENT_HISTORY_MESSAGES
) -> list[ChatMessage]:
    """OpenAI-dict transcript -> kani messages (trim unless limit=None)."""
    out: list[ChatMessage] = []
    window = items if limit is None else (items or [])[-limit:]
    for item in window:
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


def _to_history(history: list[dict]) -> list[ChatMessage]:
    """The per-turn window the model sees (trimmed like before)."""
    return _chat_messages(history)


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
    # 90s of dead air between chunks: enough for a slow-but-alive model,
    # short enough that a hung one is walked away from quickly.
    timeout = httpx.Timeout(90.0, connect=4.0)
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
    if isinstance(raw, dict) and (
        raw.get("total_tokens") or raw.get("completion_tokens")
    ):
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


# Marker the chat layer catches: THIS ATTEMPTED MODEL failed, the
# turn may continue with a different candidate. Never caught by
# _raise_mapped's generic branches above: the outer handler maps
# RouterModelFailed onto the next-candidate path, not onto a terminal
# message, so a single dead model can never end a turn.
class RouterModelFailed(Exception):
    """One candidate model failed; the turn should try the next one."""


def _raise_mapped(exc: BaseException, *, delivered: bool) -> None:
    """openai's exception ladder -> this app's exact consumer words.

    A model-level miss (429/5xx/refused/empty-output) is RouterModelFailed:
    the turn walks to the next high/medium candidate. Only the router
    itself being unreachable (connection to 127.0.0.1 dead) is a global
    failure, and only then is _mark_router_failed called. A single bad
    model can never black out the whole router for 60 seconds.
    """
    if isinstance(exc, (AIUnavailable, AIMidStream, RouterModelFailed)):
        raise exc
    if isinstance(exc, openai.APIStatusError):
        if exc.status_code == 429:
            raise RouterModelFailed(
                "Kiri's free tier is busy right now. Trying another model."
            ) from exc
        if exc.status_code >= 500:
            raise RouterModelFailed(
                "The Assistant had a server problem. Trying another model."
            ) from exc
        raise RouterModelFailed(
            "The Assistant refused that request. Trying another model."
        ) from exc
    if isinstance(exc, openai.APITimeoutError):
        # The router answered; one of its upstream models hung. The router
        # itself is healthy - walk to the next candidate, no blackout.
        raise RouterModelFailed(
            "A model timed out. Trying another model."
        ) from exc
    if isinstance(exc, openai.APIConnectionError):
        # Refused/DNS: every candidate shares this endpoint, so switching
        # models cannot help - the router itself is gone.
        ai_service._mark_router_failed()
        if delivered:
            raise AIMidStream(str(exc)) from exc
        logger.info("router unreachable: %r", exc)
        raise AIUnavailable("Could not reach the Assistant.") from exc
    if isinstance(exc, openai.APIError):
        raise RouterModelFailed(
            "The Assistant had a server problem. Trying another model."
        ) from exc
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
    reasoning_effort: str | None = None,
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
    # No length cap here: user text is cheaper than history and the
    # engine's 131k-token budget rejects itself when genuinely full.
    query = user_text
    # The full transcript rides too: the 30-message window above is the
    # only trimming, and kani itself evicts to the 131k budget. No
    # prompt compression anywhere in this app - that was the whole
    # point of wrapping kani.
    base_history = _to_history(history)
    functions = build_functions(specs) if specs else None

    t0 = time.monotonic()
    steps = 0
    message: Any = None
    empty_retried = False
    budget = max_tokens or ai_service.ANSWER_MAX_TOKENS
    round_parts: list[str] = []
    final_text = ""
    last_model_failed: str | None = None

    candidates = [chosen, *[m for m in ai_service.candidate_models() if m != chosen]]

    def _history_has_query(items: list[ChatMessage]) -> bool:
        return any(m.role.value == "user" and (m.text or "") == query for m in items)

    # The candidate loop is the turn's whole fallback story: the user's
    # model first, then the active high/medium pool by latency. When a
    # candidate dies (429/5xx/refused/hung) or says nothing, the turn
    # walks to the next one with a FRESH engine and a cleared buffer -
    # and it carries the failed candidate's transcript (tool results
    # included) forward, so the next model continues from the searches
    # that already ran instead of repeating them. kani re-adds the query
    # at the start of every round, so it is only passed when the carried
    # history does not already contain it.
    history = list(base_history)
    prev_kani: DDGSKani | None = None
    for attempt, attempt_model in enumerate(candidates):
        if cancel.is_set():
            raise ChatCancelled()
        if attempt:
            logger.info(
                "model %s failed for this turn; trying %s",
                last_model_failed,
                attempt_model,
            )
            round_parts.clear()
            if on_round_reset is not None:
                on_round_reset()
            message = None
            empty_retried = False
            budget = max_tokens or ai_service.ANSWER_MAX_TOKENS
            if prev_kani is not None:
                history = list(prev_kani.chat_history)
        engine, tap = await _build_engine(attempt_model, on_thought)
        kani = DDGSKani(
            engine,
            system_prompt=system_prompt or None,
            chat_history=history,
            functions=functions,
            # kani consults this only when a tool body itself raises; ours
            # never do (they return error payloads), but an unknown-tool
            # correction should keep the tools available for the retry.
            retry_attempts=1,
        )
        prev_kani = kani
        round_query = (
            None if attempt and _history_has_query(history) else query
        )
        try:
            async for manager in kani.full_round_stream(
                round_query,
                # Plan B3: after N tool rounds kani strips the tools for one
                # final round, so an over-cap turn ends with an answer built
                # from what it has instead of the old empty bubble.
                max_function_rounds=max(0, max_iters - 1),
                max_tokens=budget,
                **_CACHE_WIRE,
                # Plan B9: only sent when the user picked a depth; "auto"
                # omits the parameter entirely (owner rule).
                **(
                    {"reasoning_effort": reasoning_effort}
                    if reasoning_effort
                    else {}
                ),
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
                    # its partial buffer (the emit shows the next round
                    # afresh).
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
                        budget = (
                            max_tokens or ai_service.ANSWER_MAX_TOKENS
                        ) * 2
                        kani.chat_history.append(
                            ChatMessage.user(
                                "Your previous reply hit the token limit "
                                "before any text appeared. Answer again, "
                                "briefly."
                            )
                        )
                        continue
                break
        except ChatCancelled:
            raise
        except asyncio.CancelledError:
            raise
        except (
            openai.APIError,
            AIUnavailable,
            AIMidStream,
            RouterModelFailed,
        ) as exc:
            # Anything openai can still throw outside a stream maps onto the
            # same words; a local bug instead falls through raw to the
            # caller's generic branch (no invented network message).
            try:
                _raise_mapped(exc, delivered=False)
            except RouterModelFailed as mapped:
                # This candidate is done; the loop below walks to the next.
                last_model_failed = attempt_model
                logger.info(
                    "candidate model %s failed: %s", attempt_model, mapped
                )
                if attempt + 1 >= len(candidates):
                    raise AIUnavailable(
                        "The Assistant could not answer right now. Try again shortly."
                    ) from mapped
                continue
            raise
        if final_text.strip():
            break
        # A model round that said nothing hands the turn to the next
        # candidate: the caller's settle-0 not-charged branch only fires
        # when every model stayed silent.
        last_model_failed = attempt_model
        logger.info("candidate model %s said nothing; trying the next", attempt_model)

    if cancel.is_set():
        raise ChatCancelled()
    served_model = tap.last_model or attempt_model
    return {
        "text": final_text,
        "steps": steps,
        "model": served_model,
        "served_by": "router",
        "usage": _usage_of(message, final_text, served_model),
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
    # Passive calls get the same walk as agent turns: a 429 on one model
    # used to surface as a bare 'Assistant unavailable' because this path
    # was single-shot. Restarting mid-stream is the one case we refuse -
    # the caller's buffer cannot be rewound, so two answers would glue.
    candidates = [chosen, *[m for m in ai_service.candidate_models() if m != chosen]]
    last_err: Exception | None = None
    for attempt_model in candidates:
        engine, tap = await _build_engine(attempt_model, None)
        kani = Kani(
            engine,
            system_prompt=system or None,
            chat_history=_to_history(body),
        )
        manager = kani.chat_round_stream(
            None, max_tokens=max_tokens or ai_service.ANSWER_MAX_TOKENS, **_CACHE_WIRE
        )
        delivered = False
        try:
            async for chunk in manager:
                if chunk:
                    delivered = True
                    on_token(chunk)
            message = await manager.message()
            return {
                "text": message.text or "",
                "model": tap.last_model or attempt_model,
                "served_by": "router",
            }
        except ChatCancelled:
            raise
        except Exception as exc:
            try:
                _raise_mapped(exc, delivered=delivered)
            except RouterModelFailed as mapped:
                if delivered:
                    raise AIUnavailable(
                        "The Assistant was interrupted. Try again shortly."
                    ) from mapped
                last_err = mapped
                logger.info(
                    "passive candidate %s failed: %s", attempt_model, mapped
                )
                continue
            raise
    raise AIUnavailable(
        "The Assistant could not answer right now. Try again shortly."
    ) from last_err


class _Archive:
    """Duck-typed holder for saveload.save: it reads exactly these two
    attributes, so export needs no engine, no network and no Kani."""

    def __init__(self, messages: list[ChatMessage]) -> None:
        self.always_included_messages: list[ChatMessage] = []
        self.chat_history = messages


def export_archive(messages: list[dict], path) -> None:
    """Write a transcript (OpenAI dicts) as a .kani archive (plan B6).

    The archive is kani's own format - manifest plus content-addressed
    attachment blobs - so any kani tool can read what we wrote, and the
    in-app importer below can read it back.
    """
    from kani.utils import saveload

    saveload.save(
        path,
        inst=_Archive(_chat_messages(messages, limit=None)),
        save_format="kani",
    )


def import_archive(path) -> list[dict]:
    """Read a .kani (or legacy JSON) archive back into our transcript dicts.

    Only user/assistant text is projected - tool-result rows have no
    place in the display transcript (the same rule flat_from_turns
    applies), and attachments inside blobs stay in the archive.
    """
    from kani.utils import saveload

    state = saveload.load(path)
    out: list[dict] = []
    for message in state.chat_history:
        text = message.text
        role = message.role.value
        if role in ("user", "assistant") and text and text.strip():
            out.append({"role": role, "content": text})
    return out
