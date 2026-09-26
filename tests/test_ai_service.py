"""Unit tests for ai_service: model passthrough, tool assembly, and answer
post-processing. Model choice belongs to the router — the app must not rank
or rotate (owner's directive: no auto logic in the app)."""

from __future__ import annotations

import asyncio
import json

import httpx

from services.ai_service import (
    assemble_tool_calls,
    link_citations,
    parse_related,
)


def test_rotation_layer_is_gone():
    """The app-side auto/rotation layer must never come back.

    `auto` is the router's own model (kiri-router/src/auto.js, design doc
    D7): the router ranks, sticks per conversation and fails over in-request.
    The app sends the requested model verbatim.
    """
    from services import ai_service

    for symbol in (
        "rank_models",
        "AIRateLimited",
        "rate_limit_advice",
        "_RouterModelError",
        "ROUTER_CANDIDATES",
        "invalidate_models",
        "_fetch_candidates",
    ):
        assert not hasattr(ai_service, symbol), f"{symbol} must stay deleted"


def _capture_request(model: str | None) -> tuple[dict, dict]:
    """Call _stream_router against a mock transport; return (request, result)."""
    from services import ai_service

    captured: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured.update(json.loads(request.content))
        return httpx.Response(
            200,
            json={
                "choices": [
                    {"message": {"content": "ok"}, "finish_reason": "stop"}
                ]
            },
        )

    async def run() -> tuple[dict, dict]:
        client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
        old_port, old_failed = ai_service._router_port, ai_service._router_failed_until
        ai_service._router_port = 9999  # trust it; never probe or embed
        ai_service._router_failed_until = 0.0
        try:
            result = await ai_service._stream_router(
                client,
                [{"role": "user", "content": "hi"}],
                lambda _t: None,
                None,
                model=model,
            )
            return captured, result
        finally:
            await client.aclose()
            ai_service._router_port = old_port
            ai_service._router_failed_until = old_failed

    return asyncio.run(run())


def test_model_auto_is_passed_through_verbatim():
    request, result = _capture_request("auto")
    assert request["model"] == "auto", "the router's own model must reach the router"
    assert result["model"] == "auto"


def test_default_model_is_auto():
    request, _result = _capture_request(None)
    assert request["model"] == "auto"


def test_explicit_pick_is_never_substituted():
    request, result = _capture_request("GLM-5.3-Flash")
    assert request["model"] == "GLM-5.3-Flash", "no app-side substitution"
    assert result["model"] == "GLM-5.3-Flash"


def test_assemble_tool_calls_merges_fragments():
    fragments = {
        0: {"id": "call_abc", "name": "search_web", "args": '{"query": "par'},
        1: {"id": "", "name": "", "args": ""},
    }
    calls = assemble_tool_calls(fragments)
    assert len(calls) == 2
    assert calls[0]["id"] == "call_abc"
    assert calls[0]["function"]["name"] == "search_web"
    assert calls[0]["function"]["arguments"] == '{"query": "par'
    assert calls[1]["id"] == "call_1"  # auto id for missing
    assert calls[0]["type"] == "function"


def test_parse_related_strips_tail():
    text = "Paris is the capital [1].\nRELATED: France facts | Best of Paris | Loire Valley"
    clean, related = parse_related(text)
    assert "RELATED" not in clean
    assert clean.startswith("Paris is the capital")
    assert related == ["France facts", "Best of Paris", "Loire Valley"]


def test_parse_related_absent():
    clean, related = parse_related("Just an answer with no tail.")
    assert clean == "Just an answer with no tail."
    assert related == []


def test_link_citations_in_range_and_out():
    urls = ["https://a.example", "https://b.example"]
    assert link_citations("see [1] and [2]", urls) == (
        "see [1](https://a.example) and [2](https://b.example)"
    )
    # out-of-range [9] stays literal
    assert link_citations("see [9]", urls) == "see [9]"


def test_catalog_hint_formats():
    from services.ai_service import _hint

    h = _hint(
        {
            "id": "x",
            "latency_ms": 120,
            "rate_hint": {"label": "roughly 200 requests/hour"},
            "status": "active",
        }
    )
    assert "120ms" in h and "200 requests/hour" in h
    assert "rate limited" in _hint({"id": "x", "status": "rate limited"})
    assert "rotates" in _hint({"id": "auto", "status": "active"})


# ── SSE leniency and the probe cache ─────────────────────────────────────
class _FakeResp:
    def __init__(self, lines):
        self._lines = lines

    async def aiter_lines(self):
        for line in self._lines:
            yield line


def test_sse_parser_accepts_spaceless_and_multiline_data():
    from services.ai_service import _consume_sse

    tokens: list[str] = []
    lines = [
        ": keepalive",
        "event: message",
        'data:{"choices":[{"delta":{"content":"hel"}}]}',
        "",
        'data: {"choices":[{"delta":{"content":"lo"}}]}',
        (
            'data: {"choices":[{"delta":{"content":"!"},'
            '"finish_reason":"stop"}]}'
        ),
        "",
        "data: [DONE]",
    ]
    finish, tools = asyncio.run(_consume_sse(_FakeResp(lines), tokens.append, False))
    assert "".join(tokens) == "hello!", tokens
    assert finish == "stop"
    assert tools is None

    # One event split across two data lines (split between JSON tokens,
    # where the spec's newline join is whitespace).
    tokens2: list[str] = []
    lines2 = [
        'data: {"choices":',
        'data: [{"delta":{"content":"multi"}}]}',
        "",
        "data: [DONE]",
    ]
    asyncio.run(_consume_sse(_FakeResp(lines2), tokens2.append, False))
    assert "".join(tokens2) == "multi", tokens2


def test_probe_miss_is_cached(monkeypatch):
    """The 3s watchdog must not pay an 11-port scan per tick."""
    from services import ai_service

    async def go():
        calls = {"n": 0}

        class FakeClient:
            def __init__(self, *a, **k):
                pass

            async def __aenter__(self):
                return self

            async def __aexit__(self, *a):
                return False

            async def get(self, *a, **k):
                calls["n"] += 1
                raise OSError("refused")

        monkeypatch.setattr(ai_service.httpx, "AsyncClient", FakeClient)
        ai_service._probe_miss_until = 0.0
        try:
            assert await ai_service._probe_existing_router() is None
            assert calls["n"] == 11, "a full miss probes every port once"
            assert await ai_service._probe_existing_router() is None
            assert calls["n"] == 11, "the second probe must come from cache"
        finally:
            ai_service._probe_miss_until = 0.0

    asyncio.run(go())
