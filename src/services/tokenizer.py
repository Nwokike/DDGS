"""Token counting that can never block a turn.

kani's OpenAIEngine counts prompt tokens with tiktoken, and tiktoken
downloads its BPE file on first use with NO timeout - on a cold cache
that froze LM Router's UI mid-launch. The rule, ported from there:

- ``core`` pins TIKTOKEN_CACHE_DIR before any kani import (so the BPE
  file lands in one stable place, downloaded once),
- the real encoder is only touched when that cache is already warm,
- otherwise a local ~4-chars/token heuristic counts instantly.

Context budgeting only needs approximate counts, so a turn always starts
immediately either way.
"""

from __future__ import annotations

import math
import os
from pathlib import Path

import tiktoken


class HeuristicTokenizer:
    """Local approximation: deterministic, instant, no network."""

    name = "heuristic"

    def encode(self, text: str) -> list[int]:
        return list(range(max(1, math.ceil(len(str(text)) / 4))))

    encode_ordinary = encode


def tokenizer_or_heuristic(model_id: str):
    """The real tiktoken Encoding when the BPE cache is warm, else local.

    Warmth is checked BEFORE calling tiktoken: a cold
    TIKTOKEN_CACHE_DIR means encoding_for_model() would download with no
    timeout, and unknown model ids (the free catalog's) raise KeyError
    anyway - both fall through to the heuristic.
    """
    try:
        cache = os.environ.get("TIKTOKEN_CACHE_DIR")
        if cache and Path(cache).is_dir() and any(Path(cache).iterdir()):
            return tiktoken.encoding_for_model(model_id)
    except Exception:
        pass
    return HeuristicTokenizer()
