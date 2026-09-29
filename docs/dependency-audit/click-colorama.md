# click + colorama — dependency audit (DDGS)

Date: 2026-09-29 · click 8.5.0 · colorama 0.4.6 · consumer: DDGS (`ddgs-app` 2.0.2, Flet GUI) + `ddgs` lib 9.16.0
Chain: `ddgs-app` → `ddgs` → `click` (hard, `Requires-Dist: click>=8.1.8`); `flet[cli,desktop]` → `flet-cli` → `cookiecutter` → `click`; colorama is win32-only transitive (pytest/qrcode/tqdm markers).

## 1. COMPLETE API INVENTORY

### click — decorators (`decorators.py`, re-exported in `__init__.py`)
- `@command(name?, cls?, **attrs)` — turns function into `Command`; name auto-derives (lowercase, `_`→`-`, strips `_command/_cmd/_group/_grp` suffixes); docstring becomes help; `params=` kwarg supported; bare `@command` without parens works.
- `@group(...)` — same as command with `cls=Group`; entry point for multi-command CLIs.
- `@argument(*decls, cls?, **attrs)` — attaches `Argument` to `Command.params` via `__click_params__` memo.
- `@option(*decls, cls?, **attrs)` — attaches `Option`; all kwargs forwarded to `Option` constructor.
- `@confirmation_option("--yes", ...)` — flag + `prompt="Do you want to continue?"`; declines → `ctx.abort()`; `expose_value=False`.
- `@password_option("--password", ...)` — `prompt=True, confirmation_prompt=True, hide_input=True` preset.
- `@version_option(version?, package_name?, prog_name?, message?, ...)` — eager flag; auto-detects version via `importlib.metadata` (falls back to top-level-module→distro mapping); frozen message slots `%(prog)s/%(package)s/%(version)s`.
- `@custom_version_option(callback(ctx)->str, ...)` — NEW 8.5: fully custom `--version` output (git hash, file path, Python version).
- `@help_option("--help", ...)` — eager flag printing `ctx.get_help()` then `ctx.exit()`.
- `@pass_context` — injects current `Context` as first arg.
- `@pass_obj` — injects `ctx.obj` (shared state object) as first arg.
- `@make_pass_decorator(cls, ensure?)` — typed `pass_obj` variant; walks to innermost ctx holding `cls`; `ensure=True` auto-creates it.
- `@pass_meta_key(key, ...)` — NEW-ish (8.0): injects `ctx.meta[key]` as first arg.

### click — core: Command / Group / Context / Parameter (`core.py`, ~3800 lines)
- `Command(name, callback, params, context_settings?, no_args_is_help?, help?, epilog?, short_help?, options_metavar?, ...)` — `main()/make_context()/parse_args()/invoke()/get_help()/get_usage()/to_info_dict()/get_help_option*()`.
- `Group(chain?, invoke_without_command?, no_args_is_help?, ...)` — subcommand dispatch; `chain=True` runs sequences; `allow_extra_args=True` by default on groups; `CommandCollection` merges multiple groups.
- `Context(command, parent?, info_name?, obj?, auto_envvar_prefix?, default_map?, terminal_width?, max_content_width?, resilient_parsing?, allow_extra_args?, allow_interspersed_args?, ignore_unknown_options?, help_option_names?, token_normalize_func?, color?, show_default?)` — per-invocation state: `params/args/_opt_prefixes/meta/obj/invoked_subcommand/command_path`; methods `invoke(cb,*a)/forward(cmd)/call_on_close()/ensure_object()/find_object()/scope()/make_formatter()/get_help()/get_usage()/to_info_dict()/exit()/abort()/fail()`; usable as context manager (runs close callbacks).
- Invocation chain: parent↔child contexts; `ctx.invoke` runs another command with explicit args, `ctx.forward` re-dispatches with current params; `obj` threads app state down; `meta` dict carries cross-cutting data; `default_map` overrides defaults per command; `auto_envvar_prefix` expands per subcommand (`PARENT_SUB`); `resilient_parsing=True` parses with NO callbacks/defaults/interactivity (shell completion path).
- `Parameter` base — `is_eager` (processed before all non-eager), `envvar` (str|list), `default` (value or callable), `required`, `multiple`, `nargs`, `callback(ctx,param,value)`, `expose_value`, `deprecated` flag/message, `type` (ParamType), `get_error_hint()/value_from_envvar()/resolve_envvar_value()/to_info_dict()`.
- `Option` extras — `is_flag` + `flag_value` (+ `--on/--off` slash syntax), `count=True` (`-vvv` counters), `multiple=True` (repeatable), `prompt` (+`confirmation_prompt`, `prompt_required`, `hide_input`), `show_default` (bool|custom string), `show_choices`, `show_envvar`, `hidden`, `allow_from_autoenv`, deprecated-label injection into help.
- `Argument` extras — positional; `nargs=-1` eats remainder; `required` derived from nargs by default.
- `ParameterSource` enum — records whether each value came from commandline/envvar/default/default_map/prompt (introspection for `ctx.get_parameter_source()`).
- Deprecated aliases (warn, gone in 9.0): `BaseCommand→Command`, `MultiCommand→Group`, `OptionParser→optparse`, `__version__→importlib.metadata`, `get_binary_stream/get_text_stream` (private `_get_*` now).

### click — option / prompt / confirmation patterns
- Inline flag: `@option("--shout/--no-shout", default=False)`, `@option("-v","--verbose", count=True)`, `@option("--host", multiple=True)`.
- Prompt-as-option: `@option("--name", prompt=True)` (capitalizes name), `prompt="Your name"`, `confirmation_prompt=True|"custom msg"`, `hide_input=True` (getpass; errors mask the secret via `_mask_hidden_input`).
- `prompt(text, default?, hide_input?, confirmation_prompt?, type?, value_proc?, prompt_suffix=": ", show_default?, err?, show_choices?)` — loops until valid; `Abort` on Ctrl-C/EOF; Choice types auto-render `(a, b)` suffix.
- `confirm(text, default=False|None, abort?, prompt_suffix?, show_default?, err?)` — y/n parsing; `default=None` repeats until answered; `abort=True` raises on "no".
- `confirmation_option` (`--yes`) and `password_option` (`--password`) are the two canned patterns above.

### click — types (`types.py`)
- `STRING` (bytes→str via argv/filesystem/utf-8 fallback), `INT`, `FLOAT`, `BOOL` (bool_states: 1/0/yes/no/true/false/on/off/t/f/y/n/""/case-insensitive strip), `UUID`, `UNPROCESSED` (no conversion; bytes-safe paths).
- `Choice(choices, case_sensitive=True)` — any iterable incl. enums/non-str; `normalize_choice()` overridable + `token_normalize_func` aware; `shell_complete` prefix-matches; metavar `[a|b]`, `{a|b}` for required args.
- `DateTime(formats=[%Y-%m-%d, %Y-%m-%dT%H:%M:%S, %Y-%m-%d %H:%M:%S])` — tries each via strptime.
- `IntRange/FloatRange(min?, max?, min_open?, max_open?, clamp?)` — `x<=N` descriptions; clamp snaps to bound (FloatRange + open + clamp = TypeError).
- `File(mode="r", encoding?, errors?, lazy?, atomic?)` — `"-"` = stdin/stdout; lazy defers creation (writes) / validates-then-closes (reads); atomic writes temp-then-move; auto-close/flush via `ctx.call_on_close`.
- `Path(exists?, file_okay?, dir_okay?, readable?, writable?, executable?, resolve_path?, allow_dash?, path_type?)` — name auto-labels file/directory/path; shell completion emits file/dir markers.
- `Tuple(types)` — composite (`is_composite`, `arity`); requires fixed `nargs`; per-slot types via `convert_type`.
- `ParamType` base — subclass contract: `name`, `convert(value,param,ctx)` accepting already-correct types + `None`-less calls, `fail(msg)` raising `BadParameter`; helpers `split_envvar_value`, `shell_complete`, `to_info_dict`, `get_metavar`, `get_missing_message`; `FuncParamType` wraps plain callables; `convert_type` infers from annotation/default (`int→INT`, `bool→BOOL`, tuple default→`Tuple`, unknown→func wrapper).
- `OptionHelpExtra` — typed dict for envvars/default/range/required help extras.

### click — output / styling / progress (`termui.py`, `_termui_impl.py`, `utils.py`)
- `echo(message?, file?, nl=True, err=False, color?)` — THE print replacement: unicode-safe (Windows console), bytes-aware, strips ANSI when not a tty (unless forced), always flushes; broken-pipe-safe via `_PacifyFlushWrapper` (swallows EPIPE on flush).
- `style(text, fg?, bg?, bold?, dim?, underline?, overline?, italic?, blink?, reverse?, strikethrough?, reset=True)` — 16 named colors + `bright_*` + 256-index int + RGB tuple; `reset=False` composes styles.
- `secho(message, ..., **styles)` — `echo(style(...))` in one call; bytes pass through unstyled.
- `unstyle(text)` — strips ANSI codes.
- `progressbar(iterable?/length?, label?, hidden?, show_eta?, show_percent?, show_pos?, item_show_func?, fill_char="#", empty_char="-", bar_template?, info_sep?, width=36, file?, color?, update_min_steps=1)` — context manager; iterate it OR `bar.update(n, item?)`; suppressed when not a tty (label still echoed); `hidden=True` silences fully.
- `clear()` — ANSI clear-screen, tty-guarded no-op otherwise.
- `getchar(echo=False)` / `raw_terminal()` / `pause(info?, err?)` — single-key reads, Windows Unicode caveats, pause no-ops off-tty.
- `edit(text?/filename?, editor?, env?, require_save?, extension=".txt")` — `$EDITOR` launch; `filename` accepts single path or iterable; newline normalization on Windows.
- `launch(url, wait?, locate?)` — open in default app / reveal in file manager.
- `echo_via_pager(text|generator, color?)` + `get_pager_file(color?)` — pipes through `$PAGER`/less/more with streaming flush; `_PagerWriter` handles color downgrade.
- `open_file(filename, mode?, ..., lazy?, atomic?)` — `"-"` yields keep-open stdio wrapper (safe in `with` blocks).
- `format_filename(filename, shorten?)` — surrogate-safe display encoding.
- `get_app_dir(app_name, roaming?, force_posix?)` — XDG/APPDATA/darwin-Support paths.
- Test/override hooks: `visible_prompt_func` / `hidden_prompt_func` (CliRunner patches these), `_getchar` injectable.

### click — testing (`testing.py`)
- `CliRunner(charset="utf-8", env?, echo_stdin?, catch_exceptions?, capture="sys"|"fd")` — `invoke(cli, args?, input?, env?, color?, ...)` runs a command in-process with isolated stdin/stdout/stderr + environ; `isolation(input?, env?, color?)` context manager; `isolated_filesystem()` temp-cwd; `make_env()` merges env; `fd` capture (dup2, non-Windows) also catches C-ext/subprocess output.
- `Result` — `output/stdout/stderr` (text), `*_bytes`, `exit_code`, `exception`, `exc_info`, `return_value`.
- Internals: `EchoingStdin`, `StreamMixer/BytesIOCopy`, `_FDCapture`, `_NamedTextIOWrapper` (fileno behavior per capture mode).

### click — envvar handling
- Per-param `envvar="NAME"` or list (first hit wins); `Context(auto_envvar_prefix="DDGS")` auto-derives `DDGS_SUBCOMMAND_PARAM`; `allow_from_autoenv` gates per-option opt-out; `show_envvar=True` surfaces it in `--help`.
- List splitting: `File`/`Path` split on `os.path.pathsep`, everything else on whitespace (`envvar_list_splitter` overridable per type).

### click — completion scripts (`shell_completion.py`)
- `shell_complete(cli, ctx_args, prog_name, complete_var, instruction)` dispatcher: `<VAR>=bash_complete|zsh_complete|fish_complete|powershell_complete` emits completions; `..._source` emits the eval script.
- `BashComplete/ZshComplete/FishComplete/PowerShellComplete` — `source()` script + `complete()` resolver; `CompletionItem(value, type="plain"|"file"|"dir", help?, **meta)`; `add_completion_class/get_completion_class` registry; `split_arg_string`; `_resolve_context/_resolve_incomplete/_is_incomplete_argument/_is_incomplete_option` traversal.

### click — formatting / parser internals
- `HelpFormatter` (indent_increment, width clamped to terminal max 80), `wrap_text(..., preserve_paragraphs?)` with `\b` no-rewrap blocks and ANSI-aware width (8.4+); `FORCED_WIDTH` test hook; `_textwrap.TextWrapper` measures visible cells.
- `parser.py` (`_OptionParser`, `_Option`, `_Argument`): prefix splitting (`-`/`--`, custom prefixes), `_unpack_args` nargs engine (`-1` wildcard eats remainder, `UNSET` fills gaps), `token_normalize_func` applied to option tokens; `UsageError/NoSuchOption/BadOptionUsage/BadArgumentUsage` origins.

### colorama (0.4.6, 6 core files)
- `init(autoreset=False, convert=None, strip=None, wrap=True)` — swaps `sys.stdout/stderr` for `AnsiToWin32` wrappers; `wrap=False` + any other flag = ValueError; registers `atexit(reset_all)`.
- `deinit()` — restores original streams; `reinit()` — re-applies wrappers; `colorama_text(*a,**k)` — context-manager scoped init/deinit.
- `just_fix_windows_console()` — no-op off win32 / if already init'd / if already fixed; else enables native VT processing on modern consoles, wraps only legacy ones.
- `AnsiToWin32(wrapped, convert?, strip?, autoreset?)` — `should_wrap()` (False = passthrough); `write()` → `write_and_convert` (CSI regex strip + Win32 calls) or plain; `reset_all()`; `convert_osc` handles title sequences; `StreamWrapper` transparent proxy (isatty/closed/PyCharm-aware).
- `WinTerm` (`winterm.py`) — `fore/back/style/reset_all/set_console`, cursor set/adjust, `erase_screen/erase_line`, `set_title`; LIGHT_EX emulated by borrowing BRIGHT bits (tracked separately so they don't clobber).
- `win32.py` — ctypes bindings: handles, ScreenBufferInfo, TextAttribute, CursorPosition, FillConsole, Title, ConsoleMode + `ENABLE_VIRTUAL_TERMINAL_PROCESSING` + `winapi_test()`.
- `ansi.py` — `Fore/Back` (8 + RESET + 8 LIGHT_EX), `Style` (BRIGHT/DIM/NORMAL/RESET_ALL), `Cursor` (UP/DOWN/FORWARD/BACK/POS), `code_to_chars/set_title/clear_screen/clear_line`.

## 2. STRATEGIC VERDICT — NOT ballast (keep; do not expand)

- **click is load-bearing, just not in `src/`.** Zero `import click` in DDGS app code (only Flet `on_click=` handlers — false-positive grep noise) and no `[project.scripts]` entry: the GUI is correctly click-free. The weight comes from the `ddgs` LIBRARY (9.16.0, hard dep `click>=8.1.8`, installed 8.5.0), whose `cli.py` (~700 lines) is a complete chained group — `version/text/images/videos/news/books/extract/mcp/api` — exercising the real surface: `@group(chain=True)`, `Choice`+`multiple=True`+callback backends, `is_flag` switches, `secho` color output with `--no-color`, `wrap_text`, `progressbar` downloads, `echo(err=True)`. Every desktop/venv install already ships a working terminal search: `ddgs text -q "query" -m 10`, `ddgs images -q ... -o out.json`, `ddgs api -d`. Deleting click is impossible without forking the search library.
- **colorama is incidental ballast-with-a-purpose.** Nothing in the click 8.5 path touches it (8.5.0 changelog: "Colorama is no longer used for color on Windows" — native VT via `_winconsole.py`). It installs on this box only through win32-marked transitive deps (pytest, qrcode, tqdm). Keep the marker, never import it directly.
- **Opportunity, weighed honestly:** a `ddgs "query" --json` power-user CLI and a `ddgs doctor` (router health, TLS bundle, engine reachability, provider keys) are genuinely buildable — group + Choice + progressbar + secho + CliRunner tests + completion scripts are all proven in-house by `ddgs/cli.py`, and a CLI mode could ride the same venv/desktop builds. BUT it adds packaging (console entry point, Windows VT/SIGPIPE quirks), test surface, and docs for users who ALREADY have the `ddgs` CLI from the library, against a repo whose router engine is stdlib-only by policy and whose product is GUI-first. **Recommendation: no new CLI scope. Document the existing `ddgs` CLI as the power-user path; revisit `doctor` only if support tickets justify it.**

## 3. GOTCHAS

- click 8.x deprecation cliff: `BaseCommand/MultiCommand/OptionParser/__version__/get_binary_stream/get_text_stream` warn now, removed in 9.0 — never touch them in new code.
- Eager evaluation: `is_eager` options (version/help) run BEFORE all others AND before validation; callbacks must guard `ctx.resilient_parsing` (completion probes) or they fire during tab-complete.
- `resilient_parsing` also suppresses defaults and prompting — completion-safe by design, confusing when debugging ("why is my callback not running?").
- Password/prompt masking: `hide_input` errors mask the secret in messages, but the raw value still flows through `value_proc`/callbacks — don't log it.
- `BOOL` accepts `""` as False and 14 spellings; `IntRange/FloatRange` `clamp` silently snaps instead of failing; `FloatRange` + open bound + clamp raises TypeError at construction.
- `File` lazy+atomic: reads validate-then-close, writes defer creation; `"-"` never closes the underlying stdio even in `with` blocks (by design).
- `Tuple` REQUIRES fixed `nargs`; `Choice` normalization is affected by `token_normalize_func` — case-insensitive contexts change accepted spellings.
- `show_default` as STRING shows custom text instead of the value (8.3.3); `no_args_is_help` + `chain=True` groups need explicit testing (empty-invoke behavior differs Group vs Command).
- Color: `echo(color=...)` overrides context; piped output strips ANSI silently — `--no-color` flags (like ddgs') exist because of this; `style(reset=False)` leaks styles into subsequent text by design.
- SIGPIPE: `echo` flush swallows EPIPE, but raw `print()` in the same app (cf. `ddgs version` using `print`) does NOT — mixed usage crashes pipes inconsistently.
- Windows: click 8.5 enables native VT processing as a side effect (`enable_vt_processing`); legacy consoles fall back to Win32 calls; `colorama.init()` globally swaps `sys.stdout/stderr` + atexit hook — double-init and `wrap=False`+flags conflicts are the classic breakage; `just_fix_windows_console()` is the safe idempotent entry, not `init()`.
- colorama `strip` defaults: strips ANSI when piped OR legacy console; `autoreset` adds a reset write per call (throughput cost in hot loops); OSC title sequences are swallowed on the Win32 path.

## 4. COVERAGE

- click: **17/17** `.py` files read — `__init__` (full), `decorators` (full), `core` (structure grep + Context/Option sections), `termui` (full), `types` (full, 2 passes), `exceptions` (full), `globals` (full), `utils` (echo/open_file/app_dir sections), `testing` (structure + CliRunner section), `shell_completion` (structure + header/sources), `parser` (structure + header/unpack), `formatting` (structure + wrap_text), `_compat` (header), `_winconsole` (header), `_termui_impl` (structure grep), `_textwrap` (header), `_utils` (full, sentinels).
- colorama: **6/6** core files read fully — `__init__`, `ansi`, `ansitowin32`, `initialise`, `win32`, `winterm` (`tests/` intentionally excluded).
- Consumer evidence: `ddgs/cli.py` (full read), `uv.lock` (click/colorama/reverse-dep stanzas), `pyproject.toml` (full), `src/` click-grep (Flet `on_click` only, no `import click`), `flet_cli/{cli,commands/base}.py` spot-check.
