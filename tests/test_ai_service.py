"""Unit tests for ai_service: model passthrough, answer post-processing,
the router probe cache. Model choice belongs to the router — the app must
not rank or rotate (owner's directive: no auto logic in the app).

Streaming itself is kani's now (services.kani_backend); the wire-level
guarantees it took over are pinned in tests/test_kani_backend.py.
"""

from __future__ import annotations

import asyncio

import pytest

from services.ai_service import link_citations, parse_related


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


# ── the model reaches the engine verbatim (no app-side picking) ──────────
def _fake_base(monkeypatch):
    from services import ai_service

    async def fake():
        return "http://127.0.0.1:9999/v1"

    monkeypatch.setattr(ai_service, "_router_base", fake)


def test_model_auto_is_passed_through_verbatim(monkeypatch):
    from services import kani_backend

    _fake_base(monkeypatch)
    engine, _tap = asyncio.run(kani_backend._build_engine("auto", None))
    assert engine.model == "auto", "the router's own model must reach the router"
    assert str(engine.client.base_url).rstrip("/") == "http://127.0.0.1:9999/v1"


def test_default_model_is_auto(monkeypatch):
    from services import ai_service, kani_backend

    seen: list[str] = []
    real = kani_backend._build_engine

    async def spy(model, on_thought):
        seen.append(model)
        return await real(model, on_thought)

    async def no_base():
        return None

    monkeypatch.setattr(kani_backend, "_build_engine", spy)
    monkeypatch.setattr(ai_service, "_router_base", no_base)
    with pytest.raises(ai_service.AIUnavailable):
        asyncio.run(
            kani_backend.run_turn(
                "hi",
                [],
                system_prompt="SYS",
                specs=[],
                cancel=asyncio.Event(),
                on_token=lambda _t: None,
            )
        )
    assert seen == ["auto"]


def test_explicit_pick_is_never_substituted(monkeypatch):
    from services import kani_backend

    _fake_base(monkeypatch)
    engine, _tap = asyncio.run(kani_backend._build_engine("GLM-5.3-Flash", None))
    assert engine.model == "GLM-5.3-Flash", "no app-side substitution"


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
    # Owner's copy (edited 2026-09-27): no "Free tier," lead-in.
    assert _hint({"id": "auto", "status": "active"}) == (
        "Rotates across available models"
    )


# ── the probe cache ─────────────────────────────────────────────────────────
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
