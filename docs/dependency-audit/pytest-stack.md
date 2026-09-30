# pytest-stack dependency audit (DDGS)

Installed versions (venv): **pytest 9.1.1 · pluggy 1.6.0 · iniconfig 2.3.0**.
Python 3.12. DDGS suite: **287 tests**, run `uv run pytest -q`, gated by ruff + pytest in CI (`quality` job, `uv sync --frozen`).
DDGS pytest config (`pyproject.toml [tool.pytest.ini_options]`): `pythonpath = ["src"]`, `testpaths = ["tests"]` — and nothing else.

Current style (from `tests/test_kani_backend.py`, `tests/test_settings_about.py`, suite-wide grep):
heavy `monkeypatch` + `tmp_path`, `asyncio.run(...)` inside test bodies for async code,
hand-rolled fakes (`FakeEngine`, `_AndroidPage`), per-file `sys.path.insert(0, src)`,
`pytest.raises` mostly **without** `match=` (1 exception: `match="main guard"`),
`@pytest.mark.parametrize` used twice in the whole suite, zero use of `caplog` / `recwarn` /
`pytest.warns` / `capsys` / `capfd` / `approx` / `doctest` / `subtests` / `skip` / `xfail`.

---

## 1. COMPLETE API INVENTORY

### 1a. `pytest` facade (`pytest/__init__.py`, 188 lines — re-exports only)

| Area | Names |
|---|---|
| Fixtures (decorator + built-ins) | `fixture`, `yield_fixture` (deprecated — use `fixture`), `FixtureDef`, `FixtureRequest`, `FixtureLookupError`, `register_fixture` |
| Asserts / outcomes | `raises`, `RaisesExc`, `RaisesGroup`, `approx`, `fail`, `skip`, `xfail`, `exit`, `importorskip`, `deprecated_call`, `warns`, `WarningsRecorder` |
| Marks | `mark` (MarkGenerator: `skip`, `skipif`, `xfail`, `parametrize`, `filterwarnings`, `usefixtures`), `Mark`, `MarkDecorator`, `MarkGenerator`, `param`, `HIDDEN_PARAM` |
| Monkeypatch / capture / log | `MonkeyPatch`, `CaptureFixture`, `LogCaptureFixture` |
| Config / runner | `Config`, `PytestPluginManager`, `Parser`, `OptionGroup`, `ExitCode` (`OK TESTS_FAILED INTERRUPTED INTERNAL_ERROR USAGE_ERROR NO_TESTS_COLLECTED MAX_WARNINGS_ERROR`), `UsageError`, `main`, `console_main`, `cmdline`, `hookimpl`, `hookspec` |
| Node tree (for plugins) | `Session`, `Dir`, `Directory`, `Collector`, `File`, `Item`, `Module`, `Package`, `Class`, `Function`, `Metafunc`, `DoctestItem` |
| Reports | `TestReport`, `CollectReport`, `SubtestReport`, `Subtests`, `CallInfo`, `TestShortLogReport`, `TerminalReporter` |
| Tmp / cache / misc | `TempPathFactory`, `TempdirFactory` (legacy), `Testdir` (legacy), `Cache`, `Stash`, `StashKey`, `ScopeName`, `ExceptionInfo`, `register_assert_rewrite`, `freeze_includes`, `set_trace`, all `Pytest*Warning` types, pytester machinery (`Pytester`, `RunResult`, `HookRecorder`, `LineMatcher`, `RecordedHookCall`) |

### 1b. Built-in fixtures actually available (`pytest --fixtures`)

`cache` · `capsys` / `capteesys` / `capsysbinary` · `capfd` / `capfdbinary` ·
`caplog` (`LogCaptureFixture`: `handler records record_tuples messages text clear set_level at_level filtering get_records`) ·
`monkeypatch` (`setattr delattr setitem delitem setenv delenv syspath_prepend chdir context undo`) ·
`recwarn` (`WarningsRecorder`: `list pop clear`) ·
`tmp_path` / `tmp_path_factory` (`mktemp getbasetemp`) ·
`tmpdir` / `tmpdir_factory` (legacy py.path — **avoid, see §3**) ·
`pytestconfig` (session `Config`) · `doctest_namespace` (session dict) ·
`record_property` / `record_xml_attribute` / `record_testsuite_property` (junitxml) ·
`subtests` (`Subtests.test()`) ·
pytester set (`pytester`, `_pytest`, `linecomp`, `LineMatcher` — for testing plugins, not app code).

Auto-loaded third-party plugins found via `pytest11` entry points:
**anyio** (`anyio_backend`, `anyio_backend_name`, `anyio_backend_options`, `free_tcp_port_factory`,
`@pytest.mark.anyio`, `anyio_mode` ini default `strict`) and **flet**
(`flet_app`, `flet_app_function` — but both are `@pytest_asyncio.fixture` and
`pytest_asyncio` is **not installed**, so the flet plugin loads as a documented no-op).

### 1c. Marks (`_pytest/mark/` + `skipping.py`)

`skip(reason)` · `skipif(condition, reason=...)` · `xfail(condition, reason, run, raises, strict=strict_xfail)` ·
`parametrize(argnames, argvalues, ids=..., indirect=...)` + `pytest.param(..., marks=..., id=...)` ·
`filterwarnings("error::DeprecationWarning")` · `usefixtures("name")` · `@pytest.mark.anyio` (async tests via anyio).
`tryfirst`/`trylast` **marks are deprecated** — use `@pytest.hookimpl(tryfirst=True)` in plugins.

### 1d. Flags / ini options worth knowing (`--help` captured in full)

Selection & flow: `-k EXPRESSION` · `-m MARKEXPR` · `-x/--exitfirst --maxfail=` ·
`--lf/--last-failed --ff/--failed-first --nf/--new-first` (need cache) ·
`--sw/--stepwise [--sw-skip --sw-reset]` · `--deselect` · `--ignore/--ignore-glob` ·
`--co/--collect-only --keep-duplicates --continue-on-collection-errors`.
Debug: `--pdb [--pdbcls=] --trace` · `-l/--showlocals` · `--tb=auto/long/short/line/native/no` ·
`-v/-q -r fEsxXaA --durations=N [--durations-min=]` · `--full-trace --show-capture=`.
Capture/logging: `--capture=fd|sys|no|tee-sys (-s)` · `-W/--pythonwarnings= --max-warnings=` ·
`log_cli log_cli_level log_cli_format log_file*` family · `--show-capture`.
Collection/config: `--import-mode=prepend|append|importlib` (default **prepend**) ·
`--doctest-modules --doctest-glob= --doctest-report=cdiff|ndiff|udiff|only_first_failure
--doctest-continue-on-failure --doctest-ignore-import-errors` ·
`-c/--config-file --rootdir= --confcutdir= --noconftest -p PLUGIN`.
Reporting/persistence: `--junit-xml= (+junit_family/suite_name/logging/duration_report/log_passing_tests/prefix)` ·
`--pastebin= --cache-show= --cache-clear --lfnf=` · `--setup-only --setup-plan` ·
`faulthandler_timeout` + `faulthandler_exit_on_timeout` ini (built-in watchdog — **no pytest-timeout needed**) ·
`filterwarnings` ini · `tmp_path_retention_count/policy` · `truncation_limit_lines/chars` ·
`assertion_text_diff_style=ndiff|block` · `xfail_strict` · `addopts pythonpath required_plugins` ·
`verbosity_*` knobs · `PYTEST_ADDOPTS` env. **No `--sugar`**: pytest-sugar not installed, ignore it.
**Timeout**: pytest-timeout NOT installed (confirmed — no dist-info); use `faulthandler_timeout` ini instead.
**Parallel**: `-n` / xdist NOT installed (confirmed); 287 tests collect in ~3 s, don't bother.
**Coverage**: pytest-cov NOT installed (confirmed); use stdlib `coverage run -m pytest` if ever wanted.

### 1e. Key signatures (verified by introspection)

- `pytest.raises(exc, *, match=...)` — `match` is `re.search` on `str(exc)`; `RaisesExc` adds `.matches()`, `.fail_reason`.
- `pytest.warns(Warning, *, match=...)` → `WarningsChecker`; `pytest.deprecated_call()` for deprecation pins.
- `pytest.approx(expected, rel=None, abs=None, nan_ok=False)` — scalars, sequences, mappings, Decimal, timedelta, numpy.
- `pytest.fixture(scope="function"|"class"|"module"|"package"|"session", params=None, autouse=False, ids=None, name=None)`.
- `MonkeyPatch` is `final`; `context()` gives a local undo scope; `syspath_prepend` beats hand `sys.path.insert`.
- Outcomes: `fail(msg, pytrace=True)`, `skip(reason)`, `xfail(reason)`, `exit(msg, returncode)`, `importorskip(modname)`.
- `caplog.set_level("DEBUG", logger="kani")`, `caplog.at_level(...)`, `caplog.record_tuples`, `caplog.messages`.
- `tmp_path_factory.mktemp(basename, numbered=True)`; `request` fixture (`FixtureRequest`/`SubRequest`:
  `param`, `node`, `config`, `addfinalizer`, `getfixturevalue`, `applymarker`).
- `pytest.param(v, marks=..., id=...)` for per-case marks/ids; `Metafunc.parametrize` + `pytest_generate_tests` hook for dynamic cases.

### 1f. Assertion rewriting (`_pytest/assertion/` — full dir read)

`rewrite.py` (`AssertionRewritingHook`, `AssertionRewriter`, pyc cache tagged `PYTEST_TAG`),
comparators (`_compare_any/sequence/mapping/set`, `compare_text` with ndiff/block diff),
`truncate.py` (`truncation_limit_*`), `util.py` (`pytest_assertrepr_compare` hook —
custom plugins can pretty-print app types). Practical fallout: plain `assert a == b`
already yields set/dict/text diffs; `assert x in long_string` shows `_notin_text` context;
`register_assert_rewrite("my_helper_module")` needed if assertions move into non-test helpers
(else they report as plain AssertionError without introspection).

### 1g. Collection & reporting machinery (one-liners)

`python.py`: `pytest_pycollect_makeitem/makemodule`, `Metafunc`, `IdMaker`, `CallSpec2`,
`async_fail` (coroutine tests without a plugin fail with a clear message — the reason
`asyncio.run` wrappers exist today). `nodes.py`: `Node/Collector/File/Item/FSCollector/Directory`.
`reports.py`: `TestReport/CollectReport` + JSON serialise hooks (powers `--lf`, junitxml, cache).
`runner.py`: `runtestprotocol`, `CallInfo`, `SetupState`. `terminal.py`: `TerminalReporter`,
`-r` chars, `--durations`, code highlighting (`PYTEST_THEME*`).
`cacheprovider.py`: `Cache.get/set/mkdir` + `--lf/--ff/--nf/--sw` plugins (`.pytest_cache/`).
`stepwise.py`: `--sw` family. `junitxml.py`: `LogXML`, record_* fixtures. `doctest.py`:
`DoctestModule/DoctestTextfile/DoctestItem`, `doctest_namespace` fixture.
`unittest.py`: unittest TestCase support incl. twisted edge. `subtests.py` (pytest 9 new):
`subtests` fixture + `verbosity_subtests` ini. `threadexception.py`/`unraisableexception.py`:
fail loudly on thread/GC exceptions. `tracemalloc.py`, `timing.py` (`Instant/Duration/MockTiming`),
`pastebin.py`, `debugging.py` (`--pdb/--trace`, `pytestPDB`, `post_mortem`),
`faulthandler.py` (timeout watchdog), `freeze_support.py`, `helpconfig.py`,
`setuponly.py`/`setupplan.py` (`--setup-only/--setup-plan`), `stash.py` (`Stash/StashKey`
type-safe node bag), `scope.py` (`Scope` ordering), `compat.py`, `deprecated.py`
(`YIELD_FIXTURE` etc. — don't use), `warning_types.py` (all `Pytest*Warning`).

### 1h. pluggy (`pluggy/` — 7 files, all read)

`_manager.py` (`PluginManager`: `register/unregister`, `add_hookspecs`,
`load_setuptools_entrypoints("pytest11")`, `check_pending`, `subset_hook_caller`,
`parse_hookimpl_opts/parse_hookspec_opts`); `_hooks.py` (`HookCaller`, `HookRelay`,
`HookImpl`, `HookSpec`, `HookspecMarker/HookimplMarker` = `pytest.hookimpl/hookspec`);
`_callers.py` (`_multicall` — wrapper/tryfirst/trylast ordering, old-style hookwrappers);
`_result.py` (`HookCallError`, `Result`); `_tracing.py` (`TagTracer`); `_warnings.py`
(`PluggyWarning`). **Assessment**: relevant only if DDGS writes a local plugin
(`conftest.py` hooks or a `pytest11` entry point). The ~70 `pytest_*` hookspecs in
`_pytest/hookspec.py` (`pytest_generate_tests`, `pytest_collection_modifyitems`,
`pytest_fixture_setup`, `pytest_assertrepr_compare`, `pytest_make_parametrize_id`,
`pytest_runtest_*`, …) are the extension surface; nothing needed until the
"source-pin fixture" idea (§2.9) graduates to a real plugin.

### 1i. iniconfig (`iniconfig/` — 4 files, all read)

Tiny INI parser: `IniConfig.parse/get/lineof`, `parse_ini_data/parse_lines`,
`ParseError`. Sole job in this stack: reading the `[pytest]` section of
`pytest.ini/tox.ini/setup.cfg`. **DDGS uses `pyproject.toml`, so iniconfig is
effectively dormant** — no action, just know why it's installed.

### 1j. py.py (1 file, 15 lines, read whole)

Legacy shim — re-exports `_pytest._py.error` + `_pytest._py.path` as `py.error/py.path`
only when the real `pylib` isn't installed. **Status: dead compat weight, do not
import `py` in tests**; use `pathlib` (`tmp_path`) instead. (`_pytest._py.path.LocalPath`
and `legacypath.TempdirFactory/Testdir` are the same legacy family — avoid.)

---

## 2. LATENT CAPABILITIES FOR DDGS (ranked by value ÷ effort)

1. **`pytest.raises(..., match=)` everywhere** — suite uses bare `raises` except once.
   Router error strings, license `TokenRejected`, `ChatCancelled` paths are already
   "byte-identical" pins done via `.value ==`; `match=` (regex search) makes them
   one-liners and catches message drift at the raise site. Near-zero cost.
2. **`@pytest.mark.parametrize` to collapse source-string pin tests** — the audit/design
   suites repeat the same "source contains X" shape dozens of times. Parametrize over
   `(needle, haystack_fn)` cuts ~30% of those files and makes missing pins visible as
   case ids. Only 2 parametrized tests exist today.
3. **`caplog` for logger behaviour** — kani/ai-service logging is currently unasserted.
   `caplog.set_level("DEBUG", logger=...)` + `caplog.record_tuples` turns log output
   into pins; `caplog.clear()` between phases. No test uses it today.
4. **`pytest.warns` / `recwarn` warning-free guarantees** — kani + flet emit
   deprecations; `@pytest.mark.filterwarnings("error")` on strict suites plus targeted
   `pytest.warns(...)` where noise is known converts warning drift into failures.
   Zero usage today.
5. **`pytest.approx` for float assertions** — credit/pricing math, durations, similarity
   scores currently use exact `==` or manual epsilon. `approx(rel=1e-6)` is clearer and
   failure output shows both sides.
6. **Fixture factories replacing hand-rolled helpers** — `_AndroidPage/_DesktopPage`,
   `_texts()`, `FakeEngine`, `_Recorder`-style helpers recur per file.
   `@pytest.fixture` factories in one `tests/conftest.py` (params + `request.param`
   for variants) remove ~100 lines of copy-paste. Only 2 fixtures exist suite-wide.
7. **`subtests` fixture (pytest 9, already installed)** — multi-row pin tests
   (settings rows, banner rows) currently abort on first failure; `with subtests.test(msg=...)`
   reports every row. Ideal for the "carries the KTV rows" style tests.
8. **`--pdb / --trace / --showlocals` workflow** — `-l` shows locals in tracebacks;
   `--pdb` drops into post-mortem on failure; `--trace` breaks per test.
   Free, just document in contributor notes. (`pytest.set_trace()` also exists.)
9. **Custom "source pin" fixture/plugin** — the recurring pattern
   `assert needle in Path(src_file).read_text()` deserves a declarative helper:
   `def source_pin(path, *needles)` fixture or a `pytest_generate_tests`-driven
   table. Start as a `tests/conftest.py` helper; graduate to `pytest_assertrepr_compare`
   prettier diffs only if pins get noisy. pluggy needed only at that stage.
10. **`faulthandler_timeout` ini as hang watchdog** — no pytest-timeout installed
    (confirmed); `faulthandler_timeout = 60` in `[tool.pytest.ini_options]` dumps
    thread tracebacks on hangs (kani streams, httpx retries) for zero dependencies.
11. **`--doctest-modules` for docstring examples** — pure helpers (cache keys, TTL math,
    text utils) can carry doctests; opt-in per-file via `__test__` or a second
    `pytest --doctest-modules src/...` CI line so app collection stays clean.
12. **`cache` fixture / `--lf --ff` workflow** — `--lf` re-runs only failures,
    `--ff` failures-first; the `cache` fixture can persist expensive probe data
    between sessions. Free once developers know the flags.
13. **`tmp_path_factory` + `tmp_path_retention_policy=failed`** — session-scoped
    factories for heavy fixtures (tokenizer cache, storage roots); retention policy
    keeps only failed-test dirs for post-mortem.
14. **`pytest.mark.skipif(sys.platform == ...)` for platform rows** — Play-channel vs
    desktop assertions currently branch inside test bodies; `skipif`/`xfail(raises=...)`
    makes platform scoping declarative and visible in `-v -r s` output.
15. **`--junit-xml` for CI** — one flag gives the build workflow a machine-readable
    report; combine with `record_property` for build-number metadata.

Explicitly NOT recommended: pytest-xdist (`-n`, not installed — 3 s suite doesn't need
it), pytest-cov (not installed — stdlib coverage if ever wanted), pytest-sugar
(not installed — terminal reporter is fine), `tmpdir`/`py.path` (legacy),
`yield_fixture` (deprecated), `--pastebin` (deprecated service).

---

## 3. GOTCHAS

1. **Async runs via `asyncio.run()`, not a plugin — and that's currently correct.**
   `pytest-asyncio` is NOT installed (confirmed: no dist-info; flet's plugin degrades
   to no-op without it). `anyio` IS installed with `@pytest.mark.anyio` available, but
   `anyio_mode` defaults to `strict` and no test uses the marker — the anyio plugin is
   idle. Options: keep `asyncio.run()` (simplest, works), or adopt `@pytest.mark.anyio`
   + `anyio_backend` fixture (needs `anyio_mode` decision; anyio's own warning says
   don't enable auto-mode alongside asyncio auto-mode). Do NOT mix all three.
2. **`sys.path.insert(0, src)` in every test file is redundant.** `pyproject`
   sets `pythonpath = ["src"]` (pytest ≥7 feature, honoured here — collection works
   from root). The inserts are harmless (guarded by `if str(SRC) not in sys.path`)
   but hide the real mechanism; also note `--import-mode=prepend` (default) is what
   makes rootdir-relative `tests/` imports work. If collection ever breaks, check
   `rootdir`/ini discovery (`findpaths.py`: pyproject > pytest.ini > tox.ini > setup.cfg),
   not the inserts.
3. **Assertion rewriting only applies to test modules + conftest.** Helpers imported
   from `src/` get rewritten only if registered (`register_assert_rewrite`) or matching
   `python_files`. Consequence: `assert` inside `src/services/*` helpers shows bare
   messages — keep rich assertions in test bodies, or call `register_assert_rewrite`
   for a helper module. Truncation (`truncation_limit_lines/chars`) can also clip the
   giant flet-tree diffs; raise the limits if failure output gets cut.
4. **`tmpdir` vs `tmp_path`, `Testdir` vs `Pytester`.** Lowercase `tmpdir`/`Testdir`
   are the legacy `py.path` API (deprecated path, kept for compat). Always use
   `tmp_path` (pathlib). Same for `yield_fixture` → `fixture`, `tryfirst` mark →
   `@pytest.hookimpl`.
5. **pluggy hook ordering.** Wrapper hooks run outermost-first; `tryfirst/trylast`
   only order within the same hook. Relevant only when writing `conftest.py` hooks
   (e.g. a future `pytest_collection_modifyitems` for source pins).
6. **Cache/state dirs.** `.pytest_cache/` (lastfailed, stepwise, `--cache-show`) and
   numbered `tmp_path` dirs accumulate under `/tmp` (or `PYTEST_DEBUG_TEMPROOT`);
   `tmp_path_retention_count/policy` bounds them. Add `.pytest_cache/` to `.gitignore`
   if not already there.
7. **Warning filters are global-by-default.** A bare `filterwarnings = ["error"]` ini
   would flip third-party (kani/flet/httpx) deprecations into collection errors —
   scope with `pytest.mark.filterwarnings` per module instead, and keep
   `-W`/`--max-warnings=` for CI experiments.
8. **`capsys` vs `capfd` vs `caplog` are independent captures.** `capsys` (sys-level)
   misses C-level/fd writes (use `capfd`); neither sees `logging` (use `caplog`).
   Flet control tests asserting on objects need none of these — but the day a test
   asserts printed output, pick the right one.

---

## 4. COVERAGE — files read / total per package

| Package | Files read / total | Method |
|---|---|---|
| `pytest/` | **3 / 3** (`__init__.py`, `__main__.py`, `py.typed`) | full read |
| `_pytest/` | **76 / 76 `.py` files** (every module incl. `assertion/` full dir, `config/`, `mark/`, `_code/`, `_io/`, `_py/`) | AST top-level scan of all + full targeted introspection of `monkeypatch`, `python_api`, `raises`, `recwarn`, `capture`, `logging`, `tmpdir`, `cacheprovider`, `outcomes`, `fixtures`, `stash`, `subtests`, `mark.structures`, `config`; live `pytest --fixtures/--help/--markers/--collect-only` |
| `pluggy/` | **8 / 8** (`__init__`, `_callers`, `_hooks`, `_manager`, `_result`, `_tracing`, `_version`, `_warnings`) | AST scan + `PluginManager`/`HookCaller` introspection |
| `iniconfig/` | **4 / 4** (`__init__`, `_parse`, `_version`, `exceptions`) | full read (`__init__` 249 lines, `_parse` 163 lines) |
| `py.py` | **1 / 1** (15-line shim) | full read |
| Bonus (auto-loaded plugins discovered) | `anyio/pytest_plugin.py` (options section), `flet/pytest_plugin.py` (full, 130 lines) | targeted read |

Not installed (confirmed via dist-info scan — absence is a finding, §1d/§3.1):
`pytest-xdist`, `pytest-cov`, `pytest-timeout`, `pytest-asyncio`, `pytest-sugar`,
`pytest-mock`, `pytest-rerunfailures`, `hypothesis`, `respx`/`responses`.
