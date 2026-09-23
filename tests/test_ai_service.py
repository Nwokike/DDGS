"""Unit tests for ai_service pure functions: model ranking, tool assembly,
and answer post-processing."""

from __future__ import annotations

from services.ai_service import (
    assemble_tool_calls,
    link_citations,
    parse_related,
    rank_models,
)


def _m(mid, etype="/chat.completion", status="active", latency=500):
    return {"id": mid, "endpoint_type": etype, "status": status, "latency_ms": latency}


def test_auto_model_wins():
    data = [
        _m("nemotron-3.5-lightning", latency=100),
        _m("auto", latency=None),
        _m("muse-spark", etype="/response", latency=50),
    ]
    ranked = rank_models(data)
    assert ranked[0] == "auto"


def test_chat_models_before_response_and_by_latency():
    data = [
        _m("muse-spark", etype="/response", latency=10),  # fastest but wrong endpoint
        _m("jev", etype="/systemone", latency=20),
        _m("slow-chat", latency=900),
        _m("fast-chat", latency=150),
        _m("dead-chat", status="failed", latency=1),
        _m("limited-chat", status="rate limited", latency=5),
    ]
    ranked = rank_models(data)
    # active chat models first (by latency), then others; inactive last
    assert ranked[0] == "fast-chat"
    assert ranked[1] == "slow-chat"
    assert ranked.index("muse-spark") > ranked.index("slow-chat")
    assert ranked.index("dead-chat") > ranked.index("muse-spark")


def test_rank_empty_and_dup_ids():
    assert rank_models([]) == []
    ranked = rank_models([_m("dup"), _m("dup")])
    assert ranked == ["dup"]


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
