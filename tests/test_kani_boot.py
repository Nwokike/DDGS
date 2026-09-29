"""Phase 6 W1: the kani boot kit.

Imports + the tiktoken cache pin + the never-block tokenizer: LM Router
froze its UI on a cold tiktoken download (requests.get, no timeout), so
the rule is: pin the cache before kani loads, only touch the real encoder
when that cache is warm, heuristic otherwise.
"""

from __future__ import annotations

import math
import os
from pathlib import Path


def test_kani_and_engine_import_and_construct():
    from kani import AIParam, Kani
    from kani.ai_function import AIFunction
    from kani.engines.openai import OpenAIEngine

    engine = OpenAIEngine(
        api_key="x", model="gpt-4.1-nano", api_type="chat_completions"
    )
    assert engine is not None
    assert callable(Kani)
    assert callable(AIFunction)
    assert AIParam is not None


def test_tiktoken_cache_pin_targets_the_app_cache(tmp_path, monkeypatch):
    import core

    monkeypatch.delenv("TIKTOKEN_CACHE_DIR", raising=False)
    monkeypatch.delenv("DATA_GYM_CACHE_DIR", raising=False)
    monkeypatch.setenv("FLET_APP_STORAGE_CACHE", str(tmp_path / "cache"))
    core._pin_tiktoken_cache()
    pinned = os.environ["TIKTOKEN_CACHE_DIR"]
    assert pinned == str(tmp_path / "cache" / "tiktoken_cache")
    assert Path(pinned).is_dir()


def test_tiktoken_cache_pin_respects_an_existing_env(tmp_path, monkeypatch):
    import core

    monkeypatch.setenv("TIKTOKEN_CACHE_DIR", str(tmp_path / "custom"))
    core._pin_tiktoken_cache()
    assert os.environ["TIKTOKEN_CACHE_DIR"] == str(tmp_path / "custom")


def test_cold_cache_or_unknown_model_never_touches_tiktoken(tmp_path, monkeypatch):
    """Cold (empty) cache -> heuristic, and unknown model ids fall back
    too: encoding_for_model() downloads with no timeout on a miss."""
    monkeypatch.setenv("TIKTOKEN_CACHE_DIR", str(tmp_path))  # exists, EMPTY
    from services.tokenizer import HeuristicTokenizer, tokenizer_or_heuristic

    text = "hello world this is a test"
    tok = tokenizer_or_heuristic("totally-unknown-model-xyz")
    assert isinstance(tok, HeuristicTokenizer)
    assert len(tok.encode(text)) == math.ceil(len(text) / 4)
