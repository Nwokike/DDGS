# jiter — Dependency Audit (100% Capability Utilization)

- Version audited: **0.17.0** (via `openai>=2.54.0` → `kani[openai]`; direct import nowhere in `src/`)
- Package dir: `C:\Users\nwoki\.zcode\workspace\default\DDGS\.venv\Lib\site-packages\jiter\`
- Binary present: `jiter.cp312-win_amd64.pyd` (465,920 bytes) — Rust extension, no pure-Python fallback
- Consumer role: openai-python's JSON parser for streaming + non-streaming responses
  (`openai/lib/streaming/chat/_completions.py:443` content `parsed`, `:461` strict-tool `parsed_arguments`)

## 1. COMPLETE API INVENTORY

Entire public surface (`__all__`): `from_json`, `cache_clear`, `cache_usage`, `__version__`, `LosslessFloat`.
There is **no** `jiter.extract`, **no** `json_parse`, **no** `strict` param, **no** `buffer_size` param,
and **no** key-extraction / selective-key API. Anything named like that in plans or comments is imaginary —
verify before referencing.

### `from_json(json_data, /, *, allow_inf_nan=True, cache_mode='all', partial_mode=False, catch_duplicate_keys=False, float_mode='float') -> Any`

Exact parameter names from `__init__.pyi` (runtime `inspect.signature` shows `Ellipsis` sentinels for
`cache_mode`/`partial_mode`/`float_mode`, resolving to the stub defaults `'all'`/`False`/`'float'`):

| Param | Values | Meaning |
|---|---|---|
| `json_data` (positional-only) | `bytes` only | The JSON document. **Must be `bytes`.** |
| `allow_inf_nan` | `True` (default) / `False` | `True` accepts `Infinity`, `-Infinity`, `NaN` as floats. `False` rejects them (`ValueError: expected value at line 1 column 7`). This is the closest thing to a "strict mode" — there is no param literally named `strict`. |
| `cache_mode` | `'all'`/`True` (default), `'keys'`, `'none'`/`False` | String-cache policy: cache all strings, only object keys, or nothing. Trades memory for speed on repetitive keys (e.g. 50-result scrape reports repeating `title`/`url`/`score`). |
| `partial_mode` | `False`/`'off'` (default), `True`/`'on'`, `'trailing-strings'` | Incomplete-input handling. `'off'` raises. `'on'` parses what is complete and **silently discards** the last incomplete value (`b'{"a": 1, "b": '` → `{'a': 1}`). `'trailing-strings'` keeps the last incomplete string (`b'{"msg": "hel'` → `{'msg': 'hel'}`). |
| `catch_duplicate_keys` | `False` (default) / `True` | `True` raises `ValueError: Detected duplicate key "a" at line 1 column 14`. Off by default (last-wins, like stdlib). |
| `float_mode` | `'float'` (default), `'decimal'`, `'lossless-float'` | `'decimal'` returns `decimal.Decimal` (exact, slower). `'lossless-float'` returns `LosslessFloat` holding the raw JSON bytes slice. |

### `LosslessFloat` — exact-precision floats without Decimal cost

Holds the underlying float bytes; `__float__()` converts, `__bytes__()` returns the raw slice,
`.as_decimal()` builds a `Decimal`. Verified: `b'1.234567890123456789'` round-trips exactly through
`bytes()`/`as_decimal()` while `float()` gives `1.2345678901234567`. Use for money/credit balances
(`credit_service.py`) where float error is unacceptable but Decimal-everywhere is overkill.

### `cache_clear() -> None` / `cache_usage() -> int`

Reset the string cache / report its size in bytes (measured `2` after one small parse, `0` after clear).
The cache is per-process and shared across threads (a parse in flight on another thread keeps its cache).

### String handling: bytes in, never str

`from_json` accepts **only `bytes`**. Verified probes: `str`, `bytearray`, and `memoryview` all raise
`TypeError: 'str' object is not an instance of 'bytes'` (resp. `bytearray`, `memoryview`).
Every call site must `.encode("utf-8")` first ��� exactly what openai-python does
(`from_json(bytes(content, "utf-8"), ...)`). There is no `str` fast path; passing SSE `data:` line
strings directly will crash. Note `json_data` is positional-only (`/`), so it cannot be passed by keyword.

### Error types

- All parse failures raise **plain builtin `ValueError`** (verified: malformed input, duplicate keys,
  rejected `Infinity`). There is **no `jiter.JsonError` or custom exception class**.
- Messages carry line/column (`key must be a string at line 1 column 2`), which is *more* informative
  than stdlib's position offsets — good for logging which scraper fed bad JSON.
- Critical interop fact: stdlib raises `json.JSONDecodeError` (a `ValueError` **subclass**); jiter raises
  bare `ValueError`. Code doing `except json.JSONDecodeError` will **not** catch jiter failures, while
  `except ValueError` catches both. Any shared parse helper must normalize to one type.
- Wrong input type raises builtin `TypeError`.

### Performance claims from docstrings

None — the docstrings make **zero** performance claims (they document arguments only). The speed claim is
established by measurement, not prose: on a 16,063-byte scrape-shaped document
(50 results × 200-char title + 60-char URL + float score), benchmarked in this venv:
`json.loads` 75.07 µs vs `from_json` 24.75 µs per parse — **~3.0× faster**. The advantage grows with
document size and key repetition (string cache). Import cost is negligible: `import jiter` 4.7 ms
(measured cheaper than `import json` at 22.9 ms in the same session — either way, noise-level at startup).

## 2. LATENT CAPABILITIES FOR DDGS (ranked by value)

**1. Partial tool-call argument parsing during streaming (`partial_mode='on'`).**
openai-python already parses *its own snapshot* with `partial_mode=True`, but that result lives inside
openai's accumulator — DDGS's dispatch layer (`chat_agent.py` tool dispatch, `kani_backend.py`) re-parses
finished argument strings from scratch. The unused capability: feed the *accumulating* argument buffer
through `from_json(buf.encode(), partial_mode='on')` per chunk to **early-validate and early-route** —
e.g. detect which tool is being called and pre-warm it (start the scrape/search while the model is still
finishing the argument JSON) instead of waiting for `finish_reason == "tool_calls"`. openai proves the
pattern; DDGS just doesn't apply it to its own buffer. Caveat: `'on'` drops the trailing incomplete value,
so treat every partial result as provisional and do one final `partial_mode=False` parse at completion.

**2. Drop-in `json.loads` replacement on hot paths (~3× faster, measured).**
Eleven `json.loads` call sites exist in `src/` and none use jiter: `reasoning.py:142` (per-frame payload
parse — highest frequency), `innertube_client.py:101` (regex-extracted `player_response`, large),
`cache_service.py:129/230/303`, `storage_service.py:132/210/271`, `conversation_service.py:109`,
`license_token.py:176`, `app_controller.py:368`. A two-line helper
(`def fast_loads(s: str): return from_json(s.encode("utf-8"))`) applied to the per-frame and
large-document sites is free throughput. Note `cache_service`/`storage_service` parse on the UI-adjacent
path — 50 µs saved per parse compounds over history restores.

**3. `allow_inf_nan=False` as scraper-output sanitizer.**
Scraped pages (`engine.py`, `innertube_client.py`) and LLM outputs occasionally contain `NaN`/`Infinity`,
which stdlib `json.loads` *silently accepts* by default too — but with jiter you can reject at parse time
instead of discovering `float('nan')` downstream in ranking/credit math. Recommended for the scrape-report
and tool-output parse sites: fail fast with a line/column error rather than poisoning scores.

**4. `float_mode='decimal'` / `'lossless-float'` for money paths.**
`credit_service.py` / `premium_service.py` balances parsed via stdlib floats inherit binary-float error.
`float_mode='decimal'` gives exact `Decimal` at parse time (no post-conversion drift);
`'lossless-float'` keeps the raw bytes for audit logging (`bytes()` reproduces the exact wire value)
while still allowing `float()` for display. Only worth it on the 2–3 money-touching parse sites.

**5. `catch_duplicate_keys=True` for untrusted JSON.**
Scraper- and model-produced JSON with duplicated keys currently resolves last-wins silently. Enabling this
on tool-argument and scrape-report parses turns key-confusion (accidental or adversarial) into a loud
`ValueError` with the offending key named. Zero cost when off; enable per-call-site, not globally.

**6. `cache_mode='keys'` tuning for repetitive scrape payloads.**
Default `'all'` caches every string (values included) — fine for small docs, wasteful for 50-result
reports with megabyte-unique body text. `'keys'` keeps the speedup where it matters (repeated
`title`/`url`/`score` keys) without pinning unique value strings in the process-wide cache.
Pair with `cache_usage()` monitoring; call `cache_clear()` on memory-pressure signals if `'all'` is kept.

Explicitly **not available** (checked stub + runtime `dir()`): streaming/incremental parsers, key-path
extraction (`extract(doc, "results[0].url")` style), `strict=` flag, `buffer_size=`, `parse_float=`/
`parse_int=` hooks, and `str` input. If DDGS wants "extract one key from a huge tool output without
parsing the whole doc," jiter 0.17.0 cannot do it — that would need `ijson` or manual framing.

## 3. GOTCHAS

- **Bytes-only input.** `str`/`bytearray`/`memoryview` → `TypeError`. Every SSE `data:` line and every
  `json.loads(some_str)` migration must `.encode("utf-8")` first. Forgetting this is the #1 migration bug.
- **Exception-type mismatch with stdlib.** jiter raises bare `ValueError`; stdlib raises
  `json.JSONDecodeError(ValueError)`. `except json.JSONDecodeError` around a `from_json` call silently
  misses failures. Normalize in one helper: catch `ValueError` and re-raise a single app-level error.
- **`partial_mode=True` returns plausible-but-incomplete data.** `b'[1, 2, '` → `[1, 2]` with no flag
  saying "truncated." Never persist or act on a partial parse except for pre-warming/validation; always
  re-parse the finished buffer strictly. `'trailing-strings'` additionally invents a string value from a
  fragment — useful for live-transcript display, dangerous for dispatch decisions.
- **Android availability is a packaging question, not a code question.** The extension ships only as a
  compiled `.pyd`/`.so` (this venv: `jiter.cp312-win_amd64.pyd`, 465,920 bytes — present and importable).
  `uv.lock` lists wheels for win/mac/manylinux (incl. `manylinux aarch64` + `armv7l`, which is what the
  Android target needs) — but the Flet APK build resolves from **pypi.flet.dev**, not PyPI (cf. the lxml
  ceiling comment in `pyproject.toml`). Owner must confirm jiter is mirrored on pypi.flet.dev for the
  Android ABI, or the APK job dies with "No matching distribution found" exactly like the lxml case.
  There is no pure-Python fallback: if the wheel is missing on that index, `import jiter` (and therefore
  `import openai`) fails at startup. Mitigation if mirroring fails: pin `openai` usage to response paths
  that don't import the streaming module — but both `parsed` call sites live in the streaming module, so
  in practice the mirror entry is mandatory.
- **String cache is process-global.** `cache_mode='all'` (default) pins strings process-wide until
  `cache_clear()`. On a long-lived chat session parsing many large unique documents, monitor
  `cache_usage()`; prefer `cache_mode='keys'` or `'none'` for bulk scrape ingestion.
- **No `str` fast path means encode cost.** The `.encode("utf-8")` copy partially offsets the ~3× parse
  win on tiny documents (<1 KB the margin shrinks; still never slower in measurement, but don't expect
  miracles on 200-byte config files).
- **Defaults are permissive.** Out of the box jiter accepts `NaN`/`Infinity` and duplicate keys exactly
  like stdlib — switching parsers without setting `allow_inf_nan=False` / `catch_duplicate_keys=True`
  buys speed but zero additional safety.

## 4. COVERAGE

Files read (package = 100% of meaningful sources):
- `...\.venv\Lib\site-packages\jiter\__init__.py` (5 lines, re-export shim — full)
- `...\.venv\Lib\site-packages\jiter\__init__.pyi` (64 lines, complete stub — full; sole source of
  param names/defaults/docstrings since the Rust extension exposes no `__doc__`)
- `...\.venv\Lib\site-packages\jiter\jiter.cp312-win_amd64.pyd` (binary — API surface enumerated via
  `dir()`/`inspect.signature`; docstrings confirmed absent at runtime)
- `...\.venv\Lib\site-packages\jiter\py.typed` (marker only)
- Consumer evidence: `openai/lib/streaming/chat/_completions.py:430-470` (both `from_json` call sites),
  `src/services/kani_backend.py`, `src/services/chat_agent.py` (tool dispatch + `json.dumps` sites),
  grep over all `src/` `json.loads` sites (11 hits), `uv.lock` jiter wheel table, `pyproject.toml`
- Behavioral probes executed in-venv: input-type matrix, all `partial_mode`/`float_mode`/`cache_mode`
  values, `allow_inf_nan=False`, duplicate keys, error type/message capture, 16 KB benchmark,
  import-cost timing

Total: **4/4 package files + stub + runtime probing + all consumer call sites. Nothing unread.**
