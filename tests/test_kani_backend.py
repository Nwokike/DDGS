"""kani_backend pins: the loop, the caps, the ids, the words.

The engine here is scripted (no network), so what is under test is what
the app actually relies on: one billable step per model stream, buffers
reset after tool rounds, tool_call ids reaching the step rows, the caps
stopping at round boundaries BEFORE a request fires, and the router's
consumer-facing error strings staying byte-identical.
"""

from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path
from typing import ClassVar

import httpx
import openai
import pytest

SRC = Path(__file__).resolve().parents[1] / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from kani.engines.base import BaseEngine, Completion
from kani.models import ChatMessage, ChatRole, FunctionCall, ToolCall

from services import ai_service, kani_backend
from services.ai_service import AIMidStream, AIUnavailable
from services.chat_agent import ChatCancelled
from services.reasoning import ThoughtTap


class FakeEngine(BaseEngine):
    """Scripted rounds, consumed lazily like kani consumes a real one.

    Each script item is one model round:
        {"kind": "text", "chunks": [...]}                       -> answer
        {"kind": "tool", "id": ..., "pre": [...], "name": ...,
         "args": {...}}                                         -> tool call
    `requests` counts streams actually started, which is how the cap
    test proves a stopped turn never pays for the round it declined.
    """

    disable_function_calling_kwargs: ClassVar[dict] = {"include_functions": False}

    def __init__(self, script: list[dict]) -> None:
        self.script = list(script)
        self.requests = 0
        self.max_context_size = 131072

    async def prompt_len(self, messages, functions=None, **kwargs):
        return 10

    async def predict(self, messages, functions=None, **kwargs):
        raise AssertionError("the app only ever streams")

    async def stream(self, messages, functions=None, **kwargs):
        self.requests += 1
        item = self.script.pop(0)
        if item["kind"] == "text":
            for chunk in item["chunks"]:
                yield chunk
            yield Completion(
                ChatMessage(
                    role=ChatRole.ASSISTANT,
                    content="".join(item["chunks"]),
                )
            )
            return
        for chunk in item.get("pre", []):
            yield chunk
        yield Completion(
            ChatMessage(
                role=ChatRole.ASSISTANT,
                content=None,
                tool_calls=[
                    ToolCall(
                        id=item["id"],
                        type="function",
                        function=FunctionCall(
                            name=item["name"],
                            arguments=json.dumps(item["args"]),
                        ),
                    )
                ],
            )
        )


def _install(monkeypatch, script: list[dict]) -> FakeEngine:
    engine = FakeEngine(script)
    tap = ThoughtTap()

    async def build(model, on_thought):
        tap.callback = on_thought
        return engine, tap

    monkeypatch.setattr(kani_backend, "_build_engine", build)
    return engine


class _Recorder:
    """Collects everything the emit contract would have seen."""

    def __init__(self) -> None:
        self.tokens: list[str] = []
        self.resets = 0
        self.model_steps = 0
        self.tool_calls: list[tuple[str, dict]] = []

    def on_token(self, text: str) -> None:
        self.tokens.append(text)

    def on_round_reset(self) -> None:
        self.resets += 1

    async def on_model_step(self) -> None:
        self.model_steps += 1


def _spec(rec: _Recorder, name: str = "search_web") -> kani_backend.ToolSpec:
    async def run(args: dict) -> str:
        rec.tool_calls.append((kani_backend.call_id(), args))
        return '{"ok": true}'

    return kani_backend.ToolSpec(
        name=name,
        desc="Search the web.",
        parameters={
            "type": "object",
            "properties": {"query": {"type": "string"}},
            "required": ["query"],
            "additionalProperties": False,
        },
        run=run,
    )


async def _turn(engine, rec, **kwargs):
    script_defaults = {
        "system_prompt": "SYS",
        "specs": [_spec(rec)],
        "cancel": asyncio.Event(),
        "on_token": rec.on_token,
        "on_round_reset": rec.on_round_reset,
        "on_model_step": rec.on_model_step,
        "model": "auto",
    }
    script_defaults.update(kwargs)
    return await kani_backend.run_turn("hi", [], **script_defaults)


def test_tool_rounds_reset_buffers_and_count_steps(monkeypatch):
    engine = _install(
        monkeypatch,
        [
            {
                "kind": "tool",
                "id": "call_1",
                "pre": ["Let me search. "],
                "name": "search_web",
                "args": {"query": "cats"},
            },
            {
                "kind": "tool",
                "id": "call_2",
                "pre": ["And again. "],
                "name": "search_web",
                "args": {"query": "dogs"},
            },
            {"kind": "text", "chunks": ["Final ", "answer. "]},
        ],
    )
    rec = _Recorder()
    out = asyncio.run(_turn(engine, rec))

    assert out["steps"] == 3
    assert out["text"] == "Final answer. "
    assert out["served_by"] == "router"
    assert out["model"] == "auto"
    # Tool bodies saw their real tool_call ids (the step rows match on them).
    assert rec.tool_calls == [
        ("call_1", {"query": "cats"}),
        ("call_2", {"query": "dogs"}),
    ]
    # Every round after a tool round told the caller to drop its buffer,
    # so the intermediate "Let me search." never reaches the final text.
    assert rec.resets == 2
    # Reserve ran once per model call after the first.
    assert rec.model_steps == 2
    assert "".join(rec.tokens) == "Let me search. And again. Final answer. "


def test_step_cap_stops_at_the_boundary_without_a_request(monkeypatch):
    engine = _install(
        monkeypatch,
        [
            {
                "kind": "tool",
                "id": f"call_{i}",
                "name": "search_web",
                "args": {"query": str(i)},
            }
            for i in range(8)
        ],
    )
    rec = _Recorder()
    out = asyncio.run(_turn(engine, rec, max_iters=6))

    # Six model rounds happened; the seventh was declined before its
    # request could even start, and with no answer text the turn is empty.
    assert out["steps"] == 6
    assert out["text"] == ""
    assert engine.requests == 6
    assert len(rec.tool_calls) == 6


def test_cancel_at_the_boundary_makes_no_request(monkeypatch):
    engine = _install(monkeypatch, [{"kind": "text", "chunks": ["never"]}])
    rec = _Recorder()
    cancel = asyncio.Event()
    cancel.set()
    with pytest.raises(ChatCancelled):
        asyncio.run(
            kani_backend.run_turn(
                "hi",
                [],
                system_prompt="SYS",
                specs=[_spec(rec)],
                cancel=cancel,
                on_token=rec.on_token,
            )
        )
    assert engine.requests == 0


def test_wall_clock_cap_stops_the_turn(monkeypatch):
    engine = _install(
        monkeypatch,
        [
            {
                "kind": "tool",
                "id": "call_1",
                "name": "search_web",
                "args": {"query": "slow"},
            },
            {"kind": "text", "chunks": ["too late"]},
        ],
    )
    rec = _Recorder()
    out = asyncio.run(_turn(engine, rec, timeout_s=-1.0))
    assert out["steps"] == 0
    assert out["text"] == ""
    assert engine.requests == 0


def test_midstream_cancel_propagates(monkeypatch):
    _install(monkeypatch, [{"kind": "text", "chunks": ["one", "two"]}])
    rec = _Recorder()
    cancel = asyncio.Event()

    def cancel_on_second(token: str) -> None:
        rec.tokens.append(token)
        if len(rec.tokens) >= 2:
            cancel.set()
            raise ChatCancelled()

    with pytest.raises(ChatCancelled):
        asyncio.run(
            kani_backend.run_turn(
                "hi",
                [],
                system_prompt="SYS",
                specs=[_spec(rec)],
                cancel=cancel,
                on_token=cancel_on_second,
            )
        )
    # The step did not finish, so it is not counted - the caller's
    # charge floor (a delivered-text floor of one) is what bills it.
    # Nothing to assert beyond the raise here; the floor lives in chat_agent.


def _status(status: int) -> openai.APIStatusError:
    request = httpx.Request("POST", "http://router.test/v1/chat/completions")
    response = httpx.Response(status, request=request)
    return openai.APIStatusError("boom", response=response, body=None)


def test_error_words_stay_byte_identical(monkeypatch):
    marked: list[int] = []
    monkeypatch.setattr(ai_service, "_mark_router_failed", lambda: marked.append(1))

    with pytest.raises(AIUnavailable) as e429:
        kani_backend._raise_mapped(_status(429), delivered=False)
    assert str(e429.value) == "Kiri's free tier is busy right now. Try again shortly."
    assert not marked  # busy pool: no cooldown

    with pytest.raises(AIUnavailable) as e404:
        kani_backend._raise_mapped(_status(404), delivered=False)
    assert str(e404.value) == "The Assistant refused that request. Pick another model."
    assert not marked  # the router answered: no cooldown either

    with pytest.raises(AIUnavailable) as e500:
        kani_backend._raise_mapped(_status(503), delivered=False)
    assert str(e500.value) == "The Assistant had a server problem. Try again shortly."
    assert marked == [1]

    request = httpx.Request("POST", "http://router.test/v1/chat/completions")
    conn = openai.APIConnectionError(request=request)
    with pytest.raises(AIUnavailable) as econn:
        kani_backend._raise_mapped(conn, delivered=False)
    assert str(econn.value) == "Could not reach the Assistant."
    assert marked == [1, 1]

    with pytest.raises(AIMidStream):
        kani_backend._raise_mapped(conn, delivered=True)


def test_history_is_trimmed_and_roles_filtered():
    history = [{"role": "system", "content": "no"}]
    history += [{"role": "user", "content": f"u{i}"} for i in range(9)]
    history += [{"role": "assistant", "content": "a"}, {"role": "user", "content": ""}]
    converted = kani_backend._to_history(history)
    texts = [(m.role.value, m.text) for m in converted]
    # AGENT_HISTORY_MESSAGES from the end; system and empties dropped.
    assert texts == [
        ("user", "u5"),
        ("user", "u6"),
        ("user", "u7"),
        ("user", "u8"),
        ("assistant", "a"),
    ]


def test_function_schema_is_the_parameters_document_verbatim():
    spec = kani_backend.ToolSpec(
        name="search_web",
        desc="Search the web.",
        parameters={"type": "object", "properties": {}, "required": []},
        run=lambda args: asyncio.sleep(0),
    )
    fn = kani_backend.build_functions([spec])[0]
    assert fn.name == "search_web"
    assert fn.desc == "Search the web."
    assert fn.json_schema == spec.parameters


def test_complete_streams_a_toolless_shot(monkeypatch):
    engine = _install(monkeypatch, [{"kind": "text", "chunks": ["Overview ", "here."]}])
    tokens: list[str] = []
    out = asyncio.run(
        kani_backend.complete(
            [
                {"role": "system", "content": "SYS"},
                {"role": "user", "content": "q"},
            ],
            tokens.append,
            model="auto",
        )
    )
    assert out["text"] == "Overview here."
    assert out["served_by"] == "router"
    assert "".join(tokens) == "Overview here."
    assert engine.requests == 1
