# Dependency audit: net micros (certifi / idna / sniffio) + ruff

Consumer: DDGS (`C:\Users\nwoki\.zcode\workspace\default\DDGS`), `src/` + `pyproject.toml` + `uv.lock`.
Date: 2026-09-29. Versions: certifi 2026.07.22 · idna 3.20 · sniffio 1.3.1 · ruff 0.16.8 (dev-only).

Dependency chains (confirmed in `uv.lock`):
- `httpx 0.28.1` → `certifi`, `httpcore`, `anyio`, `idna`. So `certifi` + `idna` arrive via httpx even before the direct `certifi` declaration.
- `anyio 4.15.1` → `idna`, `sniffio` (sniffio import is optional-guarded inside anyio: `anyio/_core/_eventloop.py` does `import sniffio` in try/except and falls back to assuming asyncio-or-nothing).
- `openai 2.54.0` (via `kani[openai]`) → `anyio`, `httpx`, `sniffio`, `distro`, `jiter`, `pydantic`, `tqdm`.
- `requests 2.34.2` (flet-cli/dev tree) → `certifi`, `charset-normalizer`, `idna`, `urllib3`.
- Other sniffio importers in venv: `httpcore/_synchronization.py`, `httpx/_transports/asgi.py`, `openai/_utils/_sync.py`.
- `ruff` is `dev` dependency-group only (`ruff>=0.16.8`), never shipped to Android.

---

## 1. API inventory

### 1a. certifi — 2-function CA-bundle API

| Symbol | Signature | What it does |
|---|---|---|
| `certifi.where()` | `() -> str` | Path to `cacert.pem`. Lazy-extracts via `importlib.resources.as_file` on 3.11+ (zip-safe), caches in module global, `atexit`-registers cleanup. This is the ONLY certifi call DDGS makes (`src/core/tls.py:47`). |
| `certifi.contents()` | `() -> str` | Bundle PEM text (`read_text(encoding="ascii")`). Unused by DDGS. Test-only/CLI surface. |
| `python -m certifi` / `certifi --contents` | CLI (`__main__.py`, 10 lines) | Prints `where()` or `contents()`. Useful in CI diagnostics, unused by app. |
| `cacert.pem` | data | 121 `BEGIN CERTIFICATE` blocks at audit time. Mozilla bundle snapshot, version-stamped (`__version__ = "2026.07.22"`). |

No classes, no config, no exceptions of its own. Total public surface = 2 functions + 1 CLI flag.

DDGS usage (exact): `src/core/tls.py::_stable_bundle()` calls `certifi.where()`, copies bytes to `<data_dir>/ca/cacert.pem`, and `ensure_ca_bundle()` (called from `src/main.py` before any httpx client exists) repoints `SSL_CERT_FILE` at the staged copy. Design driver is documented in the module docstring: Android points `SSL_CERT_FILE` into the cache dir (= temp dir = wiped by `clear_temp()` seconds after launch), while httpx reads `SSL_CERT_FILE` FIRST at client construction (`httpx/_config.py`), so every client raised `FileNotFoundError` before any I/O. Desktop ships no such variable, hence desktop-tested-clean / phone-broken.

### 1b. idna — IDNA2008/UTS46 codec

Core encode/decode (all in `core.py`):

| Symbol | Role |
|---|---|
| `encode(s, strict=False, uts46=False, std3_rules=False, transitional=False) -> bytes` | U-label domain → A-label ASCII bytes. Splits on U+002E (strict) or 4 Unicode dots, per-label `alabel()`, rejoins. |
| `decode(s, strict=False, uts46=False, std3_rules=False, display=False) -> str` | A-label → Unicode. `display=True` passes undecodable `xn--` labels through lowercased instead of raising — the "decode for display" path (matches UTS46 §4 / WHATWG "domain to Unicode"). **This is the function DDGS does NOT call but should for result rendering (§2).** |
| `alabel(label: str) -> bytes` | Single-label → ACE (`xn--` + punycode), with full validation. |
| `ulabel(label) -> str` | Single-label ACE → Unicode, with RFC 5891 §5.3 canonical re-encode check (rejects fake A-labels like `xn---bbk`). |
| `uts46_remap(domain, std3_rules=True, transitional=False) -> str` | UTS46 §4 mapping (V kept / D deviation kept / M mapped / I ignored / else rejected) + NFC. `transitional` is deprecated no-op emitting `DeprecationWarning`. |
| `check_label`, `check_bidi`, `check_nfc`, `check_hyphen_ok`, `check_initial_combiner`, `valid_contextj`, `valid_contexto`, `valid_label_length`, `valid_string_length` | Granular RFC 5891/5892/5893 validators. Only interesting for custom error UX. |
| `IDNAError` (+ `IDNABidiError`, `InvalidCodepoint`, `InvalidCodepointContext`) | All validation failures. Modern versions carry machine-readable `.code` (stable literal: `input_too_long`, `disallowed_codepoint`, `bidi_rule_1..6`, `uts46_disallowed`, …), `.text`, `.codepoint`, `.position`. Message wording is explicitly NOT stable — match on `.code`. |
| `intranges_contain(int_, ranges)` / `intranges_from_list` (`intranges.py`, 56 lines) | Run-length codepoint-set lookup, O(log #runs). Internal; re-exported at top level. |

Codec registrations (`codec.py` + stdlib neighbours the owner asked about):

| Codec | Name | Semantics |
|---|---|---|
| `idna/codec.py::search_function` | `"idna2008"` | `str.encode("idna2008")` / `bytes.decode("idna2008")`, plus IncrementalEncoder/Decoder (label-buffered streaming) and StreamWriter/Reader. strict-errors only. |
| stdlib `encodings.idna` | `"idna"` | **IDNA 2003** (Nameprep-based) — DIFFERENT protocol, more permissive on some labels, wrong for new TLDs. Do not mix with this package. |
| stdlib `encodings.punycode` | `"punycode"` | Raw PXC bare codec, no label splitting/validation. |
| stdlib `encodings.utf_7` ("7bit") | — | Unrelated to IDN; mail-legacy 7-bit Unicode. Listed only to close the "builtin+7bit" question: nothing to use here. |
| UTS46 mode | `encode(..., uts46=True)` / CLI default | Lenient mapping (casefold, width-fold, dot-unify) BEFORE strict validation. What browsers/httpx effectively do. |
| `compat.py` | `ToASCII` → `encode()`, `ToUnicode` → `decode()`, `nameprep()` → always `NotImplementedError` | RFC 3490 porting shims only. |
| `cli.py` (`python -m idna`) | `-e/--encode`, `-d/--decode`, `--strict` (disables default UTS46 mapping), `--version`, auto-direction by `xn--` presence, stdin pipe | Handy for manual punycode inspection. Unused by app. |

Data tables: `idnadata.py` (1,933 lines: codepoint classes PVALID/CONTEXTJ/CONTEXTO, scripts, joining types, Unicode version tag) + `uts46data.py` (17,117 lines: mapping statuses/replacements). Read by size/sample, not line-by-line (see §4).

DDGS usage: **zero direct imports in `src/`** (grep confirms). Consumed transitively: httpx uses `idna` for IDN hostname encoding on connect; anyio lists it as a dependency. No `idna.decode` display path exists — see §2 gap.

### 1c. sniffio — async-library detector

Entire public surface (`_impl.py`, 96 lines):

| Symbol | Role |
|---|---|
| `current_async_library() -> str` | Returns `"asyncio"` / `"trio"` / `"curio"` (trio-asyncio reports per current mode). Raises `AsyncLibraryNotFoundError` outside async context. Detection order: `thread_local.name` → `current_async_library_cvar` → live `asyncio.current_task()` sniff → `curio.meta.curio_running()`. |
| `AsyncLibraryNotFoundError(RuntimeError)` | The only exception. |
| `current_async_library_cvar: ContextVar[Optional[str]]` | Set by runners (`anyio` sets it on entry); primary fast path. |
| `thread_local.name: Optional[str]` | `threading.local` override — the monkeypatch/test-injection point (set `sniffio.thread_local.name = "asyncio"` to fake a context). |
| `_version.__version__ = "1.3.1"` | Version only. |

No `get_async_library_*` family exists in 1.3.1 despite the prompt's guess — `current_async_library` (+ cvar + thread-local) is the whole API. DDGS usage: **zero direct imports**; consumed inside `anyio._core._eventloop` (`sniffio_current_async_library_cvar` set/get) and `httpcore`/`httpx`/`openai` sync/async bridges. DDGS runs Flet (asyncio); sniffio just lets anyio/httpcore pick the right backend.

### 1d. ruff — wrapper + Rust binary

Python wrapper = 3 files, ~130 lines total: `__init__.py` re-exports `find_ruff_bin`; `__main__.py::_run()` execs the binary (`os.execvp` POSIX, `subprocess.run` on win32 with KeyboardInterrupt→exit-2 guard); `_find_ruff.py::find_ruff_bin()` searches scripts-dirs / prefix / target / user-scheme for the `ruff[.exe]` binary, else raises `RuffNotFound`. The wrapper has NO lint logic — all rules live in the Rust binary.

Binary surface (ruff 0.16.8, `--help` verified): `check | rule | config | linter | clean | format | server | analyze | version`. `check` supports `--fix/--unsafe-fixes/--diff/--watch/--ignore-noqa/--output-format/--target-version/--preview/--extension`.

Rule-family surface (`ruff linter`, full list verified on the installed binary):

> AIR ERA FAST YTT ANN ASYNC S BLE FBT B A COM C4 CPY DTZ T10 DJ EM EXE FIX FA INT ISC ICN LOG G INP PIE T20 PYI PT Q RSE RET SLF SIM SLOT TID TD TC ARG PTH FLY I C90 NPY PD N PERF E/W DOC D F PGH PL UP FURB RUF TRY

Family cheat-sheet for the hardening discussion (§2): `E/W` pycodestyle · `F` Pyflakes · `B` bugbear · `S` bandit (security) · `ASYNC` flake8-async · `UP` pyupgrade · `I` isort · `N` pep8-naming · `D` pydocstyle · `PERF` perflint · `TRY` tryceratops (+ `EM` errmsg, `RET` return, `SIM` simplify, `RUF` ruff-specific, `PL` pylint, `PT` pytest-style, `T20` print, `TID` tidy-imports, `PTH` pathlib, `ASYNC`).

Repo's current gate (`pyproject.toml:73-74`, the ONLY ruff stanza):

```toml
[tool.ruff]
lint.extend-ignore = ["BLE001", "S110"]
```

No `lint.select` ⇒ **ruff defaults apply: `E4,E7,E9,F`** (verified: ruff default select is exactly `["E4","E7","E9","F"]`; `extend-ignore` of `BLE001`/`S110` is currently a no-op because neither `BLE` nor `S` family is selected). So today the gate catches import/syntax errors (F) and a sliver of pycodestyle — nothing about security, async, bugs, or modernization.

---

## 2. Strategic assessment + latent capabilities

### idna — TRANSITIVELY USED, display capability untapped (the real gap)

Wire path works: httpx encodes IDN hosts via `idna.encode` on connect, so `https://münchen.de` fetches fine. What is MISSING is the human side: every URL display path in `src/` renders the raw wire form. Verified: `core/utils.py` (validate/normalize only, returns raw `url`), `components/results/content_fetcher.py:183-195` (filename from raw `netloc`), `services/agent_files.py:49,95-106` (host labels from raw `netloc`), `screens/content_reader_screen.py:127-128` (link rebuild from raw `netloc`), `services/ai_service.py:498 link_citations` (raw URLs into citation markdown). No `idna.decode`, no `unquote`, no pretty-host anywhere. A result linking `http://xn--mnchen-3ya.de/` shows punycode to the user with no Unicode alternative; click/open still works (browser/httpx re-encode), but the display is hostile and punycode-homograph phishing (`xn--` lookalikes) is invisible.

Latent capability, minimal-gate-shaped: `idna.decode(host, uts46=True, display=True)` is purpose-built for this — per-label recovery means one bad label never kills the whole host string. Suggested shape (one helper in `core/utils.py`, opt-in call at render sites only):

```python
def display_host(url: str) -> str:
    try:
        host = urllib.parse.urlsplit(url).hostname or url
        return idna.decode(host, uts46=True, display=True)
    except idna.IDNAError:
        return url  # wire form is the fallback, never crash rendering
```

Cost: `idna` is already in the lockfile via httpx/anyio — declaring it direct adds zero packages (same honest-declaration precedent as `certifi` in `pyproject.toml:15-18`). Test idea: feed `http://xn--mnchen-3ya.de/`, `http://münchen.de/`, `http://example.com/` through `display_host` and assert `münchen.de` / `münchen.de` / `example.com`; plus an invalid-`xn--` label asserting pass-through, not raise. Also consider showing `display_host` as secondary text under the raw URL rather than replacing it, so copy-paste keeps the wire form.

Verdict: **keep (transitive) + optionally promote to direct + add display helper.** No wire-path work needed.

### sniffio — BALLAST WITH PURPOSE (keep, never touch directly)

DDGS never imports it; anyio/httpcore/openai need it to choose asyncio vs trio backends. It is 1 file of consequence (96 lines), zero config, zero maintenance. The only actionable knowledge: async-context bugs ("unknown async library, or not in async context") mean sniffio's cvar/thread-local saw no runner — check for `asyncio.run()` nesting or Flet spawning work outside the loop, not for sniffio itself. Test/monkeypatch hook is `sniffio.thread_local.name`. Verdict: **ballast, justified. No direct import, no pin change.**

### certifi — ALREADY USED, design is correct; upgrade path is "no"

`core/tls.py` is the right fix for the Android cache-wipe class of bug (KTV precedent cited in-docstring: never wipe cache; LM Router precedent: `trust_env=False` — DDGS chose staging over either, preserving user `SSL_CERT_FILE` overrides outside wipe dirs). `contents()` stays unused — fine, `where()` is the API.

PEP 706 / `truststore` / system-store migration: **not recommended** here. `truststore` defers to the OS store, which on Android is the very cache-backed path being dodged, and on desktop adds a native dependency for zero gain (httpx+certifi already validates). The honest upgrade path is process, not code: bump the `certifi>=` floor with Dependabot/uv so the 121-cert snapshot cannot go stale (see §3). Verdict: **used at 50% of a 2-function API, and that is 100% of what matters.**

### ruff — the gate is minimal to the point of decorative; harden WITHOUT changing style

Current gate catches F-errors + E4/E7/E9 only. The `extend-ignore` of `BLE001,S110` signals the owner once considered `BLE`+`S` and backed off — respect that, but note the ignore is currently dead config (no-op until the families are selected).

Proposed diff — additive, no style churn (no formatting, no isort reordering, no docstring mandates), matched to a Flet/async codebase:

```toml
[tool.ruff]
lint.select = ["E4", "E7", "E9", "F", "B", "ASYNC", "UP", "S", "TRY", "PERF"]
lint.ignore = ["S110", "S113", "TRY200", "B008"]
# BLE intentionally NOT selected: bare-except logging is the app's chosen
# crash-resistance pattern (keep BLE001 ignored only if BLE is ever added).
lint.extend-ignore = ["BLE001", "S110"]
```

Why each: `B` (bugbear — mutable defaults, unused loop vars, `except:` passthrough in a codebase that swallows broadly); `ASYNC` (blocking `open()/sleep()` inside async Flet handlers — the single most likely perf sink here); `UP` (py312 target cleanups, zero risk); `S` minus `S110/S113` (flags `subprocess`/`pickle`/`requests-verify=False` while keeping try-except-pass and request-timeout-out silenced per existing taste); `TRY` minus `TRY200` (raise-from discipline in the engine/license paths that already chain manually); `PERF` (list-build in hot result loops). Deliberately EXCLUDED to respect minimal-gate style: `D` (docstring mandates = churn), `I` (import sorting = diff noise), `N/ANN` (naming/annotation mandates), `PL` (noisy), `COM/ISC/Q` (formatting taste), `PT` (test-style, premature), `PTH/EM/RET/SIM/RUF` (adopt later one at a time once the first gate is green).

Rollout that honours the owner's style: add the stanza, run `ruff check --statistics`, fix-or-ignore per code, keep `format` OUT of CI. Note `ruff` stays dev-only: the Rust binary is per-platform (win32/mac/linux wheels, no Android wheel) — it never ships in the APK and CI's Android job must not invoke it.

---

## 3. Gotchas

1. **idna 2008-strict ≠ 2003-lenient ≠ browser-lenient.** This package is IDNA2008 + optional UTS46. IDNA2003 (`encodings.idna`, old tutorials) accepts labels (e.g. ß→ss mapping, some symbols) that 2008 rejects — a domain that "worked" under an old snippet can raise `InvalidCodepoint` here. Browsers/httpx use UTS46-mapping-then-validate, which is why `encode(s, uts46=True)` succeeds where bare `encode(s)` raises. Always pass `uts46=True` for user-facing input; reserve strict mode for wire validation. Catch `IDNAError` (not `UnicodeError` broadly) and match `.code`, never message text.
2. **certifi bundle staleness is the whole risk class.** 121 roots today; Mozilla removals/additions only arrive via package bump. A 2-year-old pin silently trusts distrusted CAs and misses new ones (TLS failures on new sites, not CVEs in the classic sense). Mitigation: keep the `certifi>=2026.7.22` floor moving (uv lock refresh), never vendor `cacert.pem` into the repo, never write the staged copy anywhere but `data_dir()/ca` (wipe-safe, per `tls.py`).
3. **sniffio detection is monkeypatchable global state.** `thread_local.name` overrides everything; `current_async_library_cvar` leaks across `contextvars.copy_context` boundaries in exotic runners. Symptom of misuse is `AsyncLibraryNotFoundError` in threads/callbacks Flet fires outside the loop — fix the call site (marshal back onto the event loop), never wrap sniffio. In tests, set/reset `thread_local.name` with try/finally.
4. **ruff binary-per-platform; dev-only; config-discovery caveat.** No universal wheel — CI matrices need per-OS install (uv handles it) and the Android build job must skip lint. Config discovery walks up from CWD to `pyproject.toml`/`ruff.toml`; running `ruff check` from a subdirectory without `--config` can silently pick the wrong file. Pin `requires-python >=3.12` ↔ `--target-version py312` mentally: `UP` rules otherwise suggest syntax the floor cannot run. Never add ruff to `[project].dependencies` (same reason `flet[cli,desktop]` stays in dev: APK resolution).

---

## 4. Coverage

| Package | Files read fully | Total py files | Notes |
|---|---|---|---|
| certifi | 3 (`__init__.py`, `core.py`, `__main__.py`) | 5 (+ `cacert.pem` counted, not read as source) | Remaining 2 are `tests/test_certify.py` (3 asserts: bundle exists / contents has cert / py.typed exists — verified by cat) and `tests/__init__.py` (empty). |
| idna | 8 (`__init__`, `core`, `codec`, `compat`, `cli`, `__main__`, `intranges`, `package_data`) | 10 | `idnadata.py` (1,933 lines) + `uts46data.py` (17,117 lines) are generated Unicode tables — sized/sampled, not line-read; `core.py` documents their schema. |
| sniffio | 3 (`__init__.py`, `_impl.py`, `_version.py`) | 5 | Remaining 2 are `_tests/test_sniffio.py` + `_tests/__init__.py` (runner-matrix tests, listed not executed). |
| ruff | 3 (`__init__.py`, `__main__.py`, `_find_ruff.py`) | 3 | 100%. Rust binary surface verified live: `--help`, `check --help`, `linter` (full family list), `--version` → 0.16.8. |

Consumer files read: `src/core/tls.py` (full), `pyproject.toml` (full), `src/main.py` header + `src/core/storage_paths.py` excerpt (via grep context), `src/core/utils.py:285-315`, `src/components/results/content_fetcher.py:170-200`, plus grep sweeps for `certifi|idna|sniffio|anyio|httpx`, punycode/IDN display paths, and `uv.lock` blocks for httpx/anyio/idna/sniffio/certifi/openai/requests.
