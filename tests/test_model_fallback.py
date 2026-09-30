"""Model fallback pins: one dead model never ends a turn.

The router's catalog carries status + rate_hint.tier. The picker only
offers active high/medium models (plus auto), the turn walks them in
fallback order on 429/5xx/empty, and a single model's failure never
blacks out the whole router for 60 seconds. Long prompts ride whole:
no prompt slicing anywhere.
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

SRC = Path(__file__).resolve().parents[1] / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

import httpx
import openai
import pytest


def _catalog(monkeypatch):
    from services import ai_service

    monkeypatch.setattr(
        ai_service,
        "_catalog",
        [
            {
                "id": "auto",
                "status": "active",
                "latency_ms": None,
                "endpoint_type": "chat.completion",
                "rate_hint": {"tier": "high", "label": "rotates"},
            },
            {
                "id": "fast-one",
                "status": "active",
                "latency_ms": 120,
                "endpoint_type": "chat.completion",
                "rate_hint": {"tier": "high", "label": "High"},
            },
            {
                "id": "steady-two",
                "status": "active",
                "latency_ms": 340,
                "endpoint_type": "chat.completion",
                "rate_hint": {"tier": "medium", "label": "Medium"},
            },
            {
                "id": "junk-yard",
                "status": "active",
                "latency_ms": 50,
                "endpoint_type": "chat.completion",
                "rate_hint": {"tier": "low", "label": "Low"},
            },
            {
                "id": "sick-note",
                "status": "failed",
                "latency_ms": 60,
                "endpoint_type": "chat.completion",
                "rate_hint": {"tier": "high", "label": "High"},
            },
        ],
    )


def test_picker_only_offers_auto_plus_high_and_medium(monkeypatch):
    from services import ai_service

    _catalog(monkeypatch)
    shown = [m["id"] for m in ai_service.snapshot_models()]
    assert shown[0] == "auto"
    assert "fast-one" in shown and "steady-two" in shown
    assert "junk-yard" not in shown, "low tier is never offered"
    assert "sick-note" not in shown, "failed status is never offered"

    pool = ai_service.candidate_models()
    assert pool == ["fast-one", "steady-two"], "high first, then medium, by latency"


def test_candidate_pool_excludes_the_just_failed_model(monkeypatch):
    from services import ai_service

    _catalog(monkeypatch)
    assert ai_service.candidate_models(exclude=("fast-one",)) == ["steady-two"]


def test_model_picker_shows_only_pickable_models(monkeypatch):
    from components import model_picker
    from core.state import state
    from services import ai_service

    _catalog(monkeypatch)
    monkeypatch.setattr(ai_service, "_catalog_fetched_at", 9999999999.0)
    monkeypatch.setattr(state, "ai_model", "auto", raising=False)
    ps = model_picker.model_picker_state()
    ids = [m.get("id") for m in ps.models]
    assert ids[0] == "auto"
    assert "junk-yard" not in ids


def _status(status: int) -> openai.APIStatusError:
    request = httpx.Request("POST", "http://router.test/v1/chat/completions")
    response = httpx.Response(status, request=request)
    return openai.APIStatusError("boom", response=response, body=None)


def test_rate_limit_is_a_model_miss_not_a_router_outage(monkeypatch):
    """A 429 no longer trips the 60s router blackout."""
    from services import ai_service, kani_backend

    marked: list[int] = []
    monkeypatch.setattr(ai_service, "_mark_router_failed", lambda: marked.append(1))
    with pytest.raises(kani_backend.RouterModelFailed):
        kani_backend._raise_mapped(_status(429), delivered=False)
    assert not marked, "a busy model must not black out the router"


def test_server_error_is_a_model_miss_not_a_router_outage(monkeypatch):
    from services import ai_service, kani_backend

    marked: list[int] = []
    monkeypatch.setattr(ai_service, "_mark_router_failed", lambda: marked.append(1))
    with pytest.raises(kani_backend.RouterModelFailed):
        kani_backend._raise_mapped(_status(503), delivered=False)
    assert not marked

    request = httpx.Request("POST", "http://router.test/v1/chat/completions")
    conn = openai.APIConnectionError(request=request)
    with pytest.raises(ai_service.AIUnavailable):
        kani_backend._raise_mapped(conn, delivered=False)
    assert marked == [1], "only a dead connection blacks out the router"


def test_full_prompt_reaches_the_engine_whole():
    """No prompt slicing: >2000 chars must reach kani intact."""
    from services import kani_backend

    long_text = "x" * 9000
    msgs = kani_backend._to_history([{"role": "user", "content": long_text}])
    assert len(msgs) == 1
    assert msgs[0].text == long_text, "the prompt must not be sliced"


def test_history_window_is_thirty_not_six():
    """The 6-message amputate is gone: a longer transcript survives."""
    from core.constants import AGENT_HISTORY_MESSAGES
    from services import kani_backend

    assert AGENT_HISTORY_MESSAGES >= 30
    history = [
        {"role": "user" if i % 2 == 0 else "assistant", "content": f"m{i}"}
        for i in range(40)
    ]
    assert len(kani_backend._to_history(history)) == AGENT_HISTORY_MESSAGES


def test_failed_model_falls_back_inside_one_turn(monkeypatch):
    """429 on the chosen model retries the next high/medium candidate.

    A scripted engine keeps the test off the network: model one raises
    429 at stream time, model two answers.
    """
    from kani.engines.base import BaseEngine, Completion
    from kani.models import ChatMessage, ChatRole

    from services import ai_service, kani_backend

    _catalog(monkeypatch)
    monkeypatch.setattr(ai_service, "_mark_router_failed", lambda: None)

    built: list[str] = []

    class _Script(BaseEngine):
        disable_function_calling_kwargs = {}

        def __init__(self, script):
            self.script = script
            self.max_context_size = 131072

        async def prompt_len(self, messages, functions=None, **kwargs):
            return 10

        async def predict(self, messages, functions=None, **kwargs):
            raise AssertionError("streaming only")

        async def stream(self, messages, functions=None, **kwargs):
            for item in self.script:
                yield item

    scripts = {
        # steady-two: a plain answer
        "steady-two": [
            "hello ",
            "there",
            Completion(
                ChatMessage(role=ChatRole.ASSISTANT, content="hello there")
            ),
        ],
    }

    from services.reasoning import ThoughtTap

    async def fake_build(model, on_thought):
        built.append(model)
        if model == "fast-one":
            # fail exactly where the real engine would: inside the stream
            async def fail_stream(*a, **k):
                raise _status(429)
                yield

            engine = _Script([])
            engine.stream = fail_stream  # type: ignore[method-assign]
        else:
            engine = _Script(scripts[model])
        tap = ThoughtTap(on_thought)
        return engine, tap

    monkeypatch.setattr(kani_backend, "_build_engine", fake_build)

    out = asyncio.run(
        kani_backend.run_turn(
            "hello",
            [],
            system_prompt="SYS",
            specs=[],
            cancel=asyncio.Event(),
            on_token=lambda _t: None,
            model="fast-one",
        )
    )
    assert built[0] == "fast-one"
    assert "steady-two" in built, "the turn must walk to the next candidate"
    assert out["text"].strip() == "hello there", "a later candidate answers"


def test_upstream_error_mid_stream_walks(monkeypatch):
    """The owner's exact log: Nvidia overload mid-stream must walk, not die.

    Before the fix this raised out of run_turn and chat_agent logged
    'chat turn failed' - the turn ended on one sick model.
    """
    from kani.engines.base import BaseEngine, Completion
    from kani.models import ChatMessage, ChatRole

    from services import ai_service, kani_backend
    from services.reasoning import ThoughtTap

    _catalog(monkeypatch)
    marked: list[int] = []
    monkeypatch.setattr(ai_service, "_mark_router_failed", lambda: marked.append(1))

    built: list[str] = []

    class _Script(BaseEngine):
        disable_function_calling_kwargs = {}

        def __init__(self, script):
            self.script = script
            self.max_context_size = 131072

        async def prompt_len(self, messages, functions=None, **kwargs):
            return 10

        async def predict(self, messages, functions=None, **kwargs):
            raise AssertionError("streaming only")

        async def stream(self, messages, functions=None, **kwargs):
            for item in self.script:
                yield item

    async def overloaded_stream(*a, **k):
        yield "partial "
        raise openai.APIError(
            "Upstream error from Nvidia: Service temporarily overloaded",
            request=httpx.Request("POST", "http://router.test/v1"),
            body=None,
        )
        yield  # pragma: no cover

    async def answer_stream(*a, **k):
        yield "hello "
        yield "there"
        yield Completion(
            ChatMessage(role=ChatRole.ASSISTANT, content="hello there")
        )

    async def fake_build(model, on_thought):
        built.append(model)
        engine = _Script([])
        engine.stream = overloaded_stream if model == "fast-one" else answer_stream  # type: ignore[method-assign]
        return engine, ThoughtTap(on_thought)

    monkeypatch.setattr(kani_backend, "_build_engine", fake_build)

    out = asyncio.run(
        kani_backend.run_turn(
            "hello",
            [],
            system_prompt="SYS",
            specs=[],
            cancel=asyncio.Event(),
            on_token=lambda _t: None,
            model="fast-one",
        )
    )
    assert out["text"].strip() == "hello there", "the turn must finish"
    assert "steady-two" in built, "the sick model must be walked away from"
    assert not marked, "an upstream error is not a dead router"


def test_hung_model_walks_without_blackout(monkeypatch):
    """A read timeout walks to the next model; the router stays up."""
    from services import ai_service, kani_backend

    request = httpx.Request("POST", "http://router.test/v1/chat/completions")
    timeout = openai.APITimeoutError(request=request)
    marked: list[int] = []
    monkeypatch.setattr(ai_service, "_mark_router_failed", lambda: marked.append(1))

    with pytest.raises(kani_backend.RouterModelFailed) as excinfo:
        kani_backend._raise_mapped(timeout, delivered=True)
    assert "Trying another model" in str(excinfo.value)
    assert not marked, "a hung upstream must not black out the router"


def test_over_cap_walk_rescues_instead_of_failing_the_whole_pool(monkeypatch):
    """A turn that spends its step budget mid-tool-loop still answers.

    The boundary check kept the exhausted `steps` count on every rescue
    attempt, so the next candidate's first round was broken out of before
    it streamed anything: the whole pool logged "said nothing" in ~3s
    and the turn ended with no answer at all (2.1.0 field log). Past the
    cap a rescue attempt gets ONE answer-only round instead - tools are
    stripped so it answers from the tool results already carried.
    """
    from kani import FunctionCall, ToolCall
    from kani.engines.base import BaseEngine, Completion
    from kani.models import ChatMessage, ChatRole

    from services import ai_service, kani_backend
    from services.kani_backend import ToolSpec
    from services.reasoning import ThoughtTap

    _catalog(monkeypatch)
    monkeypatch.setattr(ai_service, "_mark_router_failed", lambda: None)

    async def _ping(args):
        return '{"ok": true}'

    specs = [
        ToolSpec(
            name="ping",
            desc="ping",
            parameters={"type": "object", "properties": {}},
            run=_ping,
        )
    ]

    built: list[str] = []

    class _Script(BaseEngine):
        disable_function_calling_kwargs = {}

        def __init__(self, rounds):
            self.rounds = rounds
            self.calls = 0
            self.max_context_size = 131072

        async def prompt_len(self, messages, functions=None, **kwargs):
            return 10

        async def predict(self, messages, functions=None, **kwargs):
            raise AssertionError("streaming only")

        async def stream(self, messages, functions=None, **kwargs):
            script = self.rounds[min(self.calls, len(self.rounds) - 1)]
            self.calls += 1
            for item in script:
                yield item

    tool_round = Completion(
        ChatMessage(
            role=ChatRole.ASSISTANT,
            content=None,
            tool_calls=[
                ToolCall(
                    id="call-1",
                    type="function",
                    function=FunctionCall(name="ping", arguments="{}"),
                )
            ],
        )
    )
    scripts = {
        # attempt one: one tool round, then an empty final round at the cap
        "fast-one": [
            [tool_round],
            [Completion(ChatMessage(role=ChatRole.ASSISTANT, content=""))],
        ],
        # attempt two: the answer-only rescue round
        "steady-two": [
            [
                "rescued ",
                "answer",
                Completion(
                    ChatMessage(role=ChatRole.ASSISTANT, content="rescued answer")
                ),
            ]
        ],
    }

    async def fake_build(model, on_thought):
        built.append(model)
        return _Script(scripts[model]), ThoughtTap(on_thought)

    monkeypatch.setattr(kani_backend, "_build_engine", fake_build)

    out = asyncio.run(
        kani_backend.run_turn(
            "hello",
            [],
            system_prompt="SYS",
            specs=specs,
            cancel=asyncio.Event(),
            on_token=lambda _t: None,
            model="fast-one",
            max_iters=2,
        )
    )
    assert built == ["fast-one", "steady-two"], "one walk, no pool-wide failure"
    assert out["text"].strip() == "rescued answer", "the over-cap rescue answers"


def test_passive_summary_walks_when_a_candidate_answers_with_nothing(monkeypatch):
    """complete() walked only on exceptions; an empty 200 stream returned
    '' to the summary card as '(empty summary)'. The router answers 200
    with an embedded error for a dead upstream, so empty IS a failure."""
    from kani.engines.base import BaseEngine, Completion
    from kani.models import ChatMessage, ChatRole

    from services import kani_backend
    from services.reasoning import ThoughtTap

    _catalog(monkeypatch)

    built: list[str] = []

    class _Script(BaseEngine):
        disable_function_calling_kwargs = {}

        def __init__(self, script):
            self.script = script
            self.max_context_size = 131072

        async def prompt_len(self, messages, functions=None, **kwargs):
            return 10

        async def predict(self, messages, functions=None, **kwargs):
            raise AssertionError("streaming only")

        async def stream(self, messages, functions=None, **kwargs):
            for item in self.script:
                yield item

    scripts = {
        "fast-one": [Completion(ChatMessage(role=ChatRole.ASSISTANT, content=""))],
        "steady-two": [
            "sum",
            "mary",
            Completion(ChatMessage(role=ChatRole.ASSISTANT, content="summary")),
        ],
    }

    async def fake_build(model, on_thought):
        built.append(model)
        return _Script(scripts[model]), ThoughtTap(on_thought)

    monkeypatch.setattr(kani_backend, "_build_engine", fake_build)

    tokens: list[str] = []
    out = asyncio.run(
        kani_backend.complete(
            [
                {"role": "system", "content": "SYS"},
                {"role": "user", "content": "hi"},
            ],
            lambda t: tokens.append(t),
            model="fast-one",
        )
    )
    assert built == ["fast-one", "steady-two"], "empty is a miss, not an answer"
    assert out["text"].strip() == "summary", "the next candidate answers"
    assert "".join(tokens).strip() == "summary"
