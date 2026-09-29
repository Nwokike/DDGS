# tiktoken 0.14.0 — dependency audit for DDGS

Consumer wiring: `src/services/tokenizer.py` → `tokenizer_or_heuristic(model_id)` returns a real
`Encoding` only when `TIKTOKEN_CACHE_DIR` is already warm, else `HeuristicTokenizer`
(`~4 chars/token`, fake ids from `range()` — `len()` only, never `decode()`).
`src/core/__init__.py` pins `TIKTOKEN_CACHE_DIR` to `<cache_dir>/tiktoken_cache` before any kani
import. `src/services/kani_backend.py` passes it as `tokenizer=` to kani's `ReasoningEngine`
(`OpenAIEngine`, `max_context_size=DEFAULT_CONTEXT`) for prompt-len / context budgeting.
Today DDGS therefore uses exactly: `encoding_for_model` + `Encoding.encode` (inside kani).
Everything below is latent.

## 1. COMPLETE API INVENTORY

### 1a. `Encoding` class (`core.py`) — construction
- `Encoding(name, *, pat_str, mergeable_ranks, special_tokens, explicit_n_vocab=None)`.
  `max_token_value` = max over all ranks; `explicit_n_vocab` asserts
  `len(mergeable)+len(special) == n` and `max_token_value == n-1`.
- Pickles by reference: registered encodings serialize as just their name
  (`__getstate__`/`__setstate__` round-trip through the registry).

### 1b. `Encoding` — encode side
| Method | Notes |
|---|---|
| `encode_ordinary(text)` | Ignores special tokens (`disallowed_special=()` equivalent, faster). Safe for untrusted/scraped text. |
| `encode(text, *, allowed_special=set(), disallowed_special="all")` | **Default raises `ValueError`** on any special-token-like substring (`<\|endoftext\|>` etc.). `allowed_special="all"` encodes them as tokens; `disallowed_special=()` encodes as plain text. This is the prompt-injection guard for scraped content. |
| `encode_to_numpy(text, ...)` | Returns `np.uint32` array via zero-copy tiktoken buffer (needs `numpy`, not a hard dep). |
| `encode_ordinary_batch(texts, num_threads=8)` / `encode_batch(texts, num_threads=8, ...)` | `ThreadPoolExecutor` fan-out for bulk scrapes. |
| `encode_with_unstable(text, ...)` | Returns `(stable_tokens, completions)` — token prefix guaranteed to be a byte-prefix of the text; marked unstable API. Built for streaming/chunking. |
| `encode_single_token(str\|bytes)` | One token → value. Encodes ALL special tokens; `KeyError` if absent. |
| `_encode_single_piece`, `_encode_only_native_bpe` (needs `regex` pkg), `_encode_bytes` | Private; python-side regex splitting reference. |
- Lone-surrogate fixup: `encode*` repairs invalid UTF-16 surrogates via `surrogatepass→replace`, so encode→decode does **not** round-trip hostile strings.

### 1c. `Encoding` — decode side
| Method | Notes |
|---|---|
| `decode(tokens, errors="replace")` | **Lossy by default** — non-UTF-8 bytes become U+FFFD. Pass `errors="strict"` for fidelity. |
| `decode_bytes(tokens)` | Lossless bytes. |
| `decode_single_token_bytes(token)` | Decodes special tokens too; `KeyError` if unknown. Per-token stream inspection. |
| `decode_tokens_bytes(tokens)` | Per-token byte list — token-boundary visualization. |
| `decode_with_offsets(tokens)` | `(text, char-offsets)`; currently **raises** on invalid UTF-8 (strict). |
| `decode_batch / decode_bytes_batch(..., num_threads=8)` | Parallel batch decode. |
| `token_byte_values()` | Full vocab dump (`list[bytes]`, index = token id). |

### 1d. `Encoding` — vocab / special-token metadata
- `max_token_value: int`, `n_vocab` (legacy alias = `max_token_value+1` — prefer the former).
- `special_tokens_set` (`cached_property`), `is_special_token(int)`, `eot_token` property
  (raises `KeyError` on encodings without `<|endoftext|>` — all 7 shipped ones have it).
- `_special_token_regex` is `lru_cache(maxsize=128)` — thread-safe by construction.

### 1e. Top-level functions
- `get_encoding(name)` (`registry.py`): double-checked locking under `threading.RLock`; unknown name → `ValueError` listing found plugins + tiktoken version.
- `list_encoding_names()` → `['gpt2','r50k_base','p50k_base','p50k_edit','cl100k_base','o200k_base','o200k_harmony']`.
- `encoding_for_model(model)` / `encoding_name_for_model(model)` (`model.py`): exact `MODEL_TO_ENCODING`
  lookup, then `MODEL_PREFIX_TO_ENCODING` prefix match (matches even non-existent versions like
  `gpt-3.5-turbo-FAKE`); unknown → **`KeyError`** (this is what drops DDGS to the heuristic).
- There is **no `list_models` function** — the catalog is the `MODEL_TO_ENCODING` dict keys
  (~40 entries: chat, reasoning `o1/o3/o4-mini`, embeddings, `gpt-oss-→o200k_harmony`, deprecated
  `r50k/p50k` families, `gpt2`). There is also **no `encodings.py`** in 0.14.0 — constructors live
  in the plugin module below. There is **no `encode_with_special_tokens`** method — the equivalent
  is `encode(text, allowed_special="all")`.

### 1f. `load.py` — cache / remote loading
- `read_file(blobpath)`: local path → direct read; `http(s)://` → `requests.get` **with no timeout**;
  anything else (blobstore URIs) → optional `blobfile` dep.
- `read_file_cached(blobpath, expected_hash)`: resolution order
  `TIKTOKEN_CACHE_DIR` → `DATA_GYM_CACHE_DIR` → `<tmp>/data-gym-cache`; **`""` disables caching**.
  Cache key = `sha1(url)`; sha256-verified against `expected_hash`, corrupt cache evicted + refetched,
  mismatch on fresh download raises `ValueError`; atomic write (`uuid.tmp` + `os.rename`); `OSError`
  on write is swallowed unless the user explicitly set a cache dir.
- `load_tiktoken_bpe(url, expected_hash)` / `data_gym_to_mergeable_bpe_ranks(...)` (legacy GPT-2
  `vocab.bpe`+`encoder.json` path) / `dump_tiktoken_bpe(...)` (needs `blobfile`).
- All 7 encodings download from `https://openaipublic.blob.core.windows.net/...`, each pinned with a
  sha256 `expected_hash` in `tiktoken_ext/openai_public.py`.
- Hard runtime deps: `regex`, `requests`. Optional: `blobfile` (non-HTTP URIs, dump), `numpy`
  (only `encode_to_numpy`). Core BPE is a compiled Rust extension (`_tiktoken.*.pyd`).

### 1g. Registry + plugin mechanism (`registry.py`)
- Plugins are **not setuptools entry points** (no `entry_points.txt` in dist-info): `tiktoken_ext`
  is a namespace package scanned via `pkgutil.iter_modules`, each submodule must expose an
  `ENCODING_CONSTRUCTORS: dict[str, callable]`; duplicates or missing attribute → `ValueError`;
  discovery is `lru_cached`, constructor search guarded by `RLock`.
- Plugins present here: exactly **one** module, `tiktoken_ext/openai_public.py`, with 7 constructors:
  `gpt2` (50257), `r50k_base` (50257), `p50k_base` (50281), `p50k_edit` (+FIM tokens),
  `cl100k_base` (+`<|fim_*|>`, `<|endofprompt|>`), `o200k_base` (200k), `o200k_harmony`
  (= o200k_base ranks + ~90 chat-channel specials: `<|startoftext|>`, `<|return|>`,
  `<|constrain|>`, `<|channel|>`, `<|start|>`, `<|end|>`, `<|message|>`, `<|call|>`,
  `<|reserved_200000…201087|>`). Note `o200k_harmony()` re-invokes `o200k_base()`, i.e. a second
  cache read per first construction.
- `_educational.py` (`SimpleBytePairEncoding`, `bpe_train`, `bpe_encode`, `visualise_tokens`) is a
  pure-python reference **not exported** from `tiktoken/__init__.py` — the only timeout-free,
  no-network fallback, but slow and special-token-unaware.

## 2. LATENT CAPABILITIES FOR DDGS (ranked)

1. **Exact token receipts for the credits UI.** `len(enc.encode_ordinary(reply))` per reply replaces
   the `~4 chars/token` heuristic in the receipt row. `encode_ordinary` is the right call: fastest,
   never raises on `<|...|>`-looking text. Cache the `Encoding` per model id; fall back to heuristic
   only on cold cache/`KeyError` (reuse `tokenizer_or_heuristic`, check `.name != "heuristic"`).
2. **Prompt-size warnings before sending big scrapes.** `encode_ordinary` the assembled prompt,
   compare against kani's `DEFAULT_CONTEXT`; warn/trim before the paid call instead of failing mid-turn.
3. **Context-limit guard via `max_token_value` + engine budget.** `enc.max_token_value` sanity-checks
   ids from any source; prompt+completion estimate vs `max_context_size` gives an early
   "will exceed context" banner. Unknown free-catalog models: catch `KeyError` → `o200k_base` default
   (current newest OpenAI family) instead of pure heuristic.
4. **Stream debugging with decode.** `decode_tokens_bytes` visualizes boundaries;
   `decode`/`decode_with_offsets` reconstruct partial streams; `decode_single_token_bytes` inspects
   suspect tokens. Remember `decode` is lossy by default — use `errors="strict"` or `decode_bytes`
   when fidelity matters.
5. **Exact-billing encode.** `encode(text, allowed_special="all")` (the closest thing to the
   hypothesized `encode_with_special_tokens`) counts what the provider counts, including control
   tokens DDGS injects — use for settlement math, `encode_ordinary` for display math.
6. **Streaming-safe chunking.** `encode_with_unstable` yields a guaranteed-stable token prefix plus
   completions — correct way to split a scrape/reply mid-stream without re-tokenizing from scratch.
7. **Single-token byte decode for split diagnostics.** `decode_single_token_bytes` /
   `encode_single_token` pinpoint which token broke a chunk boundary (both `KeyError` on OOV —
   handle it; heuristic ids are NOT real ids and must never reach these).
8. **Model-catalog labels.** `MODEL_TO_ENCODING` keys + `encoding_name_for_model` give per-model
   "counted with o200k_base" labels in the model picker; `list_encoding_names()` populates a
   tokenizer dropdown. No `list_models` exists — don't go looking for it.
9. **Bulk paths.** `encode_batch`/`decode_batch(num_threads=8)` for multi-result scrape pages;
   `encode_to_numpy` for zero-copy pipelines (adds `numpy`); `token_byte_values()` for vocab tooling.
   `eot_token`/`is_special_token` for stop-token handling.

## 3. GOTCHAS

- **Cold cache freezes.** `requests.get(url)` in `load.py` has **no timeout** — first-ever encode on a
  cold cache blocks until the BPE file (~tens of MB) downloads. This is exactly why
  `tokenizer_or_heuristic` checks cache warmth first; never call `encoding_for_model` on the UI path
  without that guard, and never "warm" it on launch's critical path either — background it.
- **Cache-dir resolution.** `TIKTOKEN_CACHE_DIR` wins, then `DATA_GYM_CACHE_DIR`, then
  `<tmp>/data-gym-cache` (re-downloaded per temp clean). `""` disables caching entirely (every call =
  network). DDGS pins per-install via `core/__init__.py` — keep that before any kani/tiktoken import.
- **Unknown-model `KeyError`.** `encoding_for_model("free-catalog-model")` raises; DDGS catches broadly
  → heuristic. Recommended: `try/except KeyError → get_encoding("o200k_base")` as the modern default.
- **Special-token threat on scraped text.** Default `encode()` *raises* on `<|endoftext|>`-like
  substrings attackers can plant in pages. For untrusted input always use `encode_ordinary` (or
  `disallowed_special=()`); only opt into `allowed_special` for tokens DDGS itself emits.
- **Decode lossiness.** `decode()` defaults to `errors="replace"`; split multi-byte sequences across
  stream chunks silently become U+FFFD. Reconstruct from `decode_bytes`, or `errors="strict"` to fail loud.
- **Android packaging.** Core BPE is compiled Rust (`_tiktoken.*.pyd` per ABI) — cross-compiling for
  Android (chaquopy/python-for-android) is the hard part, plus mandatory `regex`+`requests` wheels.
  Pure-python `_educational` works anywhere but is orders of magnitude slower and ignores special
  tokens — heuristic-or-server-side counting is the pragmatic mobile story.
- **Thread safety.** Registry construction is `RLock`-guarded and cached; batch helpers spawn their own
  `ThreadPoolExecutor(num_threads=8)`; `CoreBPE.encode/decode` hold no per-call Python state and are
  safe to share one `Encoding` across threads — but don't share one `ThreadPoolExecutor`-sized burst
  per keystroke; reuse the `Encoding` object.
- **Heuristic ids are fake.** `HeuristicTokenizer.encode` returns `range(ceil(len/4))` — passing those
  ints to any `decode*`/`is_special_token` yields garbage or `KeyError`. Branch on
  `tokenizer.name == "heuristic"` before any decode path.

## 4. COVERAGE

- `tiktoken` package: **6/6 `.py` read** — `__init__.py`, `core.py`, `load.py`, `model.py`,
  `registry.py`, `_educational.py` (plus 1 Rust binary `_tiktoken.cp312-win_amd64.pyd`, not source-readable).
  Corrections to the brief: no `encodings.py` exists in 0.14.0 (constructors live in the plugin module).
- `tiktoken_ext` plugins dir: **1/1 module read** — `openai_public.py` (namespace package, no
  `__init__.py`, no entry-points mechanism).
- Consumer files read: `src/services/tokenizer.py`, `src/core/__init__.py`,
  `src/services/kani_backend.py` (engine-construction snippet), `src/services/credit_service.py` (grep).
