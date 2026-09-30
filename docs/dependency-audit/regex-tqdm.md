# Dependency Audit: regex + tqdm

Consumer: DDGS (`C:\Users\nwoki\.zcode\workspace\default\DDGS`). Neither package is a direct
dependency in `pyproject.toml`; both ride in transitively. DDGS `src/` uses only stdlib
`import re` (8 files) and zero `tqdm` imports. Both ARE importable at zero install cost
— they are already in the venv — so "ballast" below means "unused today, available for
direct use", not "remove".

| Package | Version | Pulled in by | Direct use in DDGS |
|---|---|---|---|
| regex | 2026.9.29 | `tiktoken` (tokenizer for AI features) | none — 8 files use stdlib `re` |
| tqdm | 4.70.1 | `openai` (SDK dep) | none — progress UI is custom Flet |

---

## 1. API INVENTORY

### regex — everything `re` lacks

Syntax/semantics (from `regex/_main.py` module docstring, ground truth):
- **Fuzzy matching** — `(?:pattern){e<=2}`, `{i<=1,s<=2,d<=1}`, cost equations (`1i+1s+1d<3`) — insertions/deletions/substitutions with limits.
- **Unicode properties** — `\p{name=value}` / `\P{...}` (scripts, categories, blocks), `\X` grapheme cluster, `\h` horizontal whitespace, `\G` (search-start anchor), `\K` (keep only what follows).
- **Possessive quantifiers** — `*+`, `++`, `?+`, `{m,n}+` (no backtracking, faster + ReDoS-resistant).
- **Atomic groups** — `(?>...)`; backtracking control verbs `(*FAIL)`, `(*PRUNE)`, `(*SKIP)`.
- **Branch reset** — `(?|A|B)` reuses group numbers across alternatives.
- **Recursive / subroutine calls** — `(?P>name)`, `(?R)`-style group calls (note: `Scanner` explicitly rejects recursive patterns).
- **Named lists** — `\L<name>` with list passed as kwarg.
- **Set operators** (VERSION1) — `||` union, `~~` sym-diff, `&&` intersection, `--` difference, nestable sets.
- **Overlapping matches** — `findall`/`finditer(..., overlapped=True)`.
- **Best/enhanced fuzzy** — flags `BESTMATCH`/`ENHANCEMATCH` (default is first match).
- **Partial matches** — `partial=True` (match a prefix of the full pattern; for streaming/incremental input).
- **Reverse matching** — `REVERSE` flag (right-to-left search); `POSIX` leftmost-longest; `WORD` Unicode word breaks; `FULLCASE` folding; `VERSION0`/`VERSION1` behaviour switch.
- **`timeout=` param on EVERY op** — `match/search/sub/split/findall/finditer/...` all accept `timeout=` (seconds); raises `TimeoutError` — a backtracking circuit-breaker stdlib `re` has no equivalent of.
- **`concurrent=` param** — releases the GIL during matching for threaded use.
- **`subf`/`subfn`** — format-string (not template-string) substitution variants; `splititer` lazy-split iterator; `prefixmatch` alias of `match`; `template()` compiled-template patterns.
- **`Scanner`** — lexer class for tokenizing (`regex/_regex_core.py:4480`); `escape(special_only=, literal_spaces=)` richer than `re.escape`.
- **Cache control** — `cache_all()`, `purge()`, `_MAXCACHE = 500` compiled-pattern cache (vs `re`'s 512, but explicitly tunable).

### tqdm — module-by-module (31 files)

- `tqdm/std.py` (1532 lines, the whole engine) — `tqdm(iterable, desc, total, leave, file=sys.stderr, ncols, mininterval, maxinterval, miniters, ascii, disable, unit, unit_scale, unit_divisor, dynamic_ncols, smoothing=0.3, bar_format, initial, position, postfix, nrows, colour, delay, gui)`; methods `update/set_description/set_postfix/write/external_write_mode/wrapattr/pandas/trange`.
- `tqdm/asyncio.py` — `tqdm_asyncio` with `__aiter__/__anext__` (`async for i in trange(n)`), plus `as_completed()` and `gather()` wrappers for `asyncio` fan-out with one bar.
- `tqdm/notebook.py` + `autonotebook.py`/`auto.py` — ipywidgets bars; auto-dispatch console vs notebook.
- `tqdm/gui.py` + `tk.py` — matplotlib-animation / Tk GUI bars (desktop only).
- `tqdm/cli.py` + `__main__.py` — `... | python -m tqdm | ...` pipe auto-wrapping for shell pipelines.
- `tqdm/rich.py`, `keras.py`, `dask.py`, `_tqdm_pandas.py` — rich-live, Keras-callback, Dask, pandas integrations.
- `tqdm/contrib/` — `concurrent.thread_map/process_map`, `itertools` (chain/product/permutations/combinations/batched with bars), `logging` (tqdm-compatible log redirect), `discord/slack/telegram/bells` notifiers.
- `tqdm/_monitor.py`, `utils.py`, `completion.sh`, `tqdm.1` — background perf monitor, env helpers, shell completion, manpage.

---

## 2. LATENT CAPABILITIES FOR DDGS (ranked)

Verdict context: both packages are **usable directly** (already installed, importable, no
`pyproject` change needed to experiment). Ranked by value/effort for DDGS's actual
workloads — heavy text processing (URL cleaning, RELATED parsing, snippet truncation,
YouTube cipher/HTML scraping) and custom Flet download-progress UI.

1. **`regex` `timeout=` on scraper patterns (stability, ~2 lines)** — `innertube_client.py`
   and `cipher_solver.py` run `re.search` against adversarial third-party HTML/JS. Wrapping
   those calls with `regex.search(..., timeout=1.0)` guards catastrophic backtracking on
   hostile input. Highest value: a hang-prevention circuit-breaker stdlib cannot provide.
2. **Possessive quantifiers in hot URL/HTML patterns (perf, free)** — `format_parser.py`
   `_VIDEO_ID_RE`, `engine.py` sanitizers: `[^...]*+` / `\d++` variants cut backtracking on
   every search/download-list parse. Drop-in once `import regex as re` is aliased.
3. **`\p{...}` Unicode properties for query cleanup (i18n correctness)** — `engine.py:91`
   `[^A-Za-z0-9.+_-]` label sanitizer and `agent_files.py:50` slugifier silently mangle
   non-Latin input; `\p{L}\p{N}` keeps CJK/Arabic/Cyrillic queries intact.
4. **Fuzzy matching for typo-tolerant history/search (feature)** — `(?:query){e<=2}` +
   `BESTMATCH` gives typo-tolerant matching over cached titles/history with zero new deps.
5. **`overlapped=True` finditer for snippet/citation extraction** — `ai_service.py`
   `_CITE_RE`/`_RELATED_RE` parsing could catch adjacent markers stdlib skips.
6. **`tqdm.contrib.concurrent.thread_map` for multi-file crawls (maybe)** — only if DDGS
   ever adds a CLI/batch mode; the Flet GUI already owns progress display, so core tqdm
   bars are redundant there. `tqdm.asyncio.gather/as_completed` is the async analogue if
   batch fetching parallelizes.
7. **`tqdm.contrib.logging` redirect (hygiene)** — only relevant if tqdm is adopted for
   batch jobs; prevents bar/log interleaving. Not needed today.

Honest ballast note: `tqdm`'s notebook/gui/keras/dask/rich frontends and discord/slack
notifiers have no DDGS consumer (Flet app, not notebooks) — count them as dead weight if
vendoring size ever matters. `regex` has no dead weight: every extra is one import away
from the 8 files already doing regex work. Transitive owners: `regex` ← `tiktoken`,
`tqdm` ← `openai`; do NOT remove either from the lock file.

---

## 3. GOTCHAS

- **regex is a superset with subtly different defaults** — default `VERSION0` is
  `re`-compatible, but `VERSION1` changes set/flag semantics; `(?flags)` scoping and some
  flag aliases differ. Aliasing `import regex as re` needs a test pass over the 8
  consumer files, especially `cipher_solver.py` (complex patterns).
- **Compiled-pattern cache is bounded and global** — `_MAXCACHE = 500`; dynamically
  generated patterns (per-video cipher regexes) can churn it. Call `purge()` or
  `cache_all(False)` for high-cardinality generated patterns.
- **`timeout=` raises, it doesn't return None** — callers must catch `TimeoutError`
  (defined in `regex`) or a guarded scrape becomes a crash.
- **tqdm writes to `stderr` by default** — fine for CLI, but noisy/polluting in app logs
  and invisible inside the Flet GUI. `disable=True` on non-TTY or `file=` redirect is
  mandatory; never let a bar own progress the Flet UI already shows.
- **regex ships a C extension** — `_regex.cp312-win_amd64.pyd` is present on this
  Windows venv, and PyPI serves per-platform wheels (macOS universal2 in `uv.lock`), so
  desktop/mobile installs resolve normally; pure-Python fallback does not exist, so any
  exotic target without a wheel would fail at install, not at import. (Reported per audit
  brief: installed OK.)
- **`Scanner` can't do recursive patterns** — raises `error("recursive regex not
  supported by Scanner")`; use compiled-pattern `match` loops instead for nested
  structures.

---

## 4. COVERAGE

- **regex** (5 files incl. tests): `__init__.py` read fully (3 lines, pure re-export);
  `_main.py` read fully in chunks (759/759 lines: docstring API + all public functions +
  cache internals); `_regex_core.py` interface-skimmed (parser/flag classes, `Scanner`
  at :4480, ~60 def/class signatures of 4675 lines); `_regex*.pyd` presence-checked
  (binary); `tests/` not read (upstream suite, out of scope).
- **tqdm** (31 files): `__init__.py`, `asyncio.py` read fully; `std.py` read in full for
  signature/docstring/params + method list (engine body skimmed); `cli.py`, `gui.py`,
  `notebook.py`, `contrib/concurrent.py`, `contrib/itertools.py` header/first-class
  skimmed; remaining shims (`auto.py`, `rich.py`, `keras.py`, `dask.py`, `tk.py`,
  `contrib/logging.py`, discord/slack/telegram/bells, `_monitor.py`, `utils.py`)
  inventoried by purpose via imports/`__all__`/docstrings.
