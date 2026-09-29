# Dependency Audit: rich (v15.0.0)

- **Package:** `rich` 15.0.0 — terminal rendering library (terminal-only; no GUI widgets)
- **Location:** `C:\Users\nwoki\.zcode\workspace\default\DDGS\.venv\Lib\site-packages\rich\`
- **Role in DDGS:** transitive only — pulled in by `flet` and `flet-desktop` (CLI/test output). Zero direct imports in `src/`.
- **DDGS consumer status:** the "Live Activity Terminal" (`src/components/settings/sections_about.py`) is a Flet `AlertDialog` with a scrolling `ft.Column` of plain `ft.Text` fed by `InMemoryLogHandler` (`src/core/utils.py`, 200-record cap) — **plain text, no rich anywhere**.
- **Import cost (measured):** bare `import rich` ~0.02 s; full feature import (`console+syntax+table+progress+live+traceback+json+pretty+logging+prompt+panel+text+markup+theme`) ~0.25 s — lazy-import inside CLI/dev-only paths, never at Flet startup.

## 1. COMPLETE API INVENTORY

### Console (`console.py`, ~2700 lines)
- `Console(*, color_system="auto"|"standard"|"256"|"truecolor"|"windows", force_terminal, force_jupyter, force_interactive, soft_wrap, theme, stderr, file, quiet, width, height, style, no_color, tab_size=8, record=False, markup=True, emoji=True, emoji_variant, highlight=True, log_time, log_path, log_time_format="[%X]", highlighter=ReprHighlighter(), legacy_windows, safe_box, get_datetime, get_time)` — width/color auto-detection overridable per instance.
- `print(*objects, sep, end, style, justify, overflow, no_wrap, emoji, markup, highlight, width, height, crop=True, soft_wrap, new_line_start)` — markup/highlight/emoji toggles per call.
- `log(*objects, ...)` — like `print` plus timestamp + caller path columns.
- `rule(title="", *, characters="─", style="rule.line", align="center")` — section divider with centered title.
- `status(status, *, spinner="dots", spinner_style, speed=1.0, refresh_per_second=12.5)` — context-manager spinner for indeterminate work.
- `print_json(json=None, *, data, indent=2, highlight, skip_keys, ensure_ascii, check_circular, allow_nan, default, sort_keys)` — valid-JSON pretty print with `JSONHighlighter`.
- `print_exception(*, width=100, code_width=88, extra_lines=3, theme, word_wrap, show_locals, max_frames)` — one-call pretty traceback.
- `input(prompt="", *, markup, emoji, password=False, stream)` — styled prompt with optional password masking.
- `capture()` / `begin_capture()` / `end_capture()` — context manager returning printed output as `str`.
- `export_text(*, clear=True, styles=False)` / `save_text(path, ...)` — dump record buffer as plain (or ANSI-styled) text; requires `record=True`.
- `export_html(*, theme, clear, code_format, inline_styles=False)` / `save_html(path, ...)` — full shareable HTML page of the session.
- `export_svg(*, title="Rich", theme, clear, code_format, font_aspect_ratio=0.61, unique_id)` / `save_svg(path, ...)` — pixel-faithful terminal screenshot as SVG.
- `pager(pager=None, styles=False, links=False)` — pipe long output through `$PAGER`.
- `screen(style=None, *, color_system)` / `set_alt_screen(enable)` / `clear(home=True)` / `show_cursor(show)` / `set_window_title(title)` / `bell()` — fullscreen + terminal chrome control.
- `measure(renderable, *, options)` / `render(renderable, options)` / `render_lines(...)` — width measurement and segment-level rendering primitives.
- Detection props: `is_terminal`, `is_dumb_terminal`, `color_system`, `size`, `width`/`height` (settable), `encoding`.

### Text (`text.py`) — `Text(plain="", style="", *, justify, overflow, no_wrap, end, tab_size)`
- `Span(start, end, style)` + `stylize(style, start, end)`, `stylize_before`, `apply_meta`, `on(meta, **handlers)` — span-level styling with clickable `@meta` handlers.
- `from_markup(markup, style="", emoji=True)`, `from_ansi(text, ...)` — constructors from markup / ANSI.
- `align("left"|"center"|"right"|"full", width)`, `pad/pad_left/pad_right`, `truncate(max_width, *, overflow="fold"|"crop"|"ellipsis", pad)`, `wrap(console, width, *, justify, overflow, tab_size, no_wrap)` — layout ops.
- `highlight_regex(re_highlight, style_prefix)`, `highlight_words(words, style, *, case_sensitive)` — regex/word highlighting in place.
- `assemble(*parts)`, `join(lines)`, `split(separator)`, `divide(offsets)`, `blank_copy`, `copy`, `append/append_text/append_tokens`, `get_style_at_offset(console, offset)` — composition and inspection.

### Markup (`markup.py`) — `render(markup, style="", emoji=True, emoji_variant)` → `Text`; `escape(markup)` for user content.
- Tags: `[bold|italic|underline|strike|blink|reverse|dim]`, `[red|green|...]` + 256-hex colors, `[link=url]...[/link]`, `[emoji]`, style-attribute tags (`[on blue]`, `[not bold]`), `[/]` implicit close, `[@click	handler]` meta tags; `RE_TAGS`/`RE_HANDLER` regexes are reusable.

### Theme (`theme.py`) — `Theme(styles=None, inherit=True)`; `Theme.read(path)` / `from_file(config_file)` load INI-style `[styles]` files; `ThemeStack.push_theme/pop_theme` for scoped overrides; `theme.config` serializes back to INI.

### Style & Color (`style.py`, `color.py`)
- `Style(color, bgcolor, bold, dim, italic, underline, blink, reverse, strike, link, meta, ...)`; `Style.parse(str)` / `Style.combine(...)` / `Style.chain(...)`.
- `ColorSystem`: STANDARD=1, EIGHT_BIT=2, TRUECOLOR=3, WINDOWS=4 (legacy Win32 console fallback via `_win32_console.py`); palettes in `_palettes.py` (standard/8-bit/Windows).

### Progress (`progress.py`) — `Progress(*columns, console, auto_refresh=True, refresh_per_second, transient, redirect_stdout/stderr, expand, get_time, disable, speed_estimate_period)`; `add_task(description, start=True, total=100.0, completed=0, visible=True, **fields)` → `TaskID`; `update(task_id, *, total, completed, advance, description, visible, refresh, **fields)`; `advance(task_id, advance=1)`; `start_task/stop_task/reset/remove_task`; `track(sequence, ...)` iterator wrapper; `wrap_file(file, total, ...)` for byte streams.
- Built-in columns: `TextColumn`, `BarColumn(bar_width)`, `SpinnerColumn(spinner_name, style, speed)`, `TaskProgressColumn(show_speed)`, `TimeElapsedColumn`, `TimeRemainingColumn(elapsed_when_finished)`, `FileSizeColumn`, `TotalFileSizeColumn`, `MofNCompleteColumn(separator="/")`, `DownloadColumn(binary_units)`, `TransferSpeedColumn`, `RenderableColumn`; custom columns subclass `ProgressColumn` overriding `render(task)`.
- `Task`: `percentage`, `speed`, `elapsed`, `remaining`, `finished`, `started` properties drive custom rendering.

### Table (`table.py`) — `Table(*headers, title, caption, width, min_width, box=HEAVY_HEAD, padding=(0,1), collapse_padding, pad_edge, expand, show_header/footer/edge/lines, leading, style, row_styles, header_style, footer_style, border_style, title_style, title_justify="center", highlight)`; `add_column(header, *, style, justify, width, min_width, max_width, ratio, no_wrap, overflow)`; `add_row(*renderables, style, end_section)`; `add_section()`; `Table.grid(*headers, padding, expand)` borderless variant.
- Box styles (`box.py`): `ASCII`, `ASCII2`, `ASCII_DOUBLE_HEAD`, `SQUARE`, `SQUARE_DOUBLE_HEAD`, `MINIMAL`, `MINIMAL_HEAVY_HEAD`, `MINIMAL_DOUBLE_HEAD`, `SIMPLE`, `SIMPLE_HEAD`, `SIMPLE_HEAVY`, `HORIZONTALS`, `ROUNDED`, `HEAVY`, `HEAVY_EDGE`, `HEAVY_HEAD`, `DOUBLE`, `DOUBLE_EDGE`, `MARKDOWN` (+ legacy-Windows substitutions).

### Panel (`panel.py`) — `Panel(renderable, box=ROUNDED, *, title, title_align="center", subtitle, subtitle_align, expand=True, style, border_style, width, height, padding=(0,1), highlight)`; `Panel.fit(...)` shrink-wraps content.

### Live (`live.py`) — `Live(renderable=None, *, console, screen=False, auto_refresh=True, refresh_per_second=4, transient=False, redirect_stdout/stderr=True, vertical_overflow="ellipsis", get_renderable)`; `update(renderable, *, refresh=False)` swaps content per tick; `refresh()`; `start(refresh=False)`/`stop()`; context-manager + `__enter__/__exit__`; `process_renderables` hook; `LiveRender` handles ellipsis/crop/visible overflow.

### Syntax (`syntax.py`, wraps Pygments) — `Syntax(code, lexer, *, theme=DEFAULT_THEME, dedent, line_numbers, start_line=1, line_range, highlight_lines, code_width, tab_size=4, word_wrap, background_color, indent_guides, padding=0)`; `Syntax.from_path(path, *, encoding, lexer, theme, ...)` with `guess_lexer(path, code)`; `highlight(code, lexer_name)` one-shot; themes via `PygmentsSyntaxTheme(theme_name)` / `ANSISyntaxTheme(style_map)`; `stylize_range(style, start, end)`.

### Pretty (`pretty.py`) — `Pretty(obj, highlighter, indent_size=4, justify, overflow, no_wrap, indent_guides, max_length, max_string, max_depth, expand_all, margin, insert_line)`; `pprint(obj, *, console, indent_guides, max_length, max_string, max_depth, expand_all)`; `install(console, *, max_length, max_string)` replaces the `displayhook`; `is_expandable(obj)`; `Node`/`_Line` traversal engine; `ReprHighlighter` auto-styles reprs.

### JSON (`json.py`) — `JSON(json_str, indent=2, highlight=True, skip_keys, ensure_ascii, check_circular, allow_nan, default, sort_keys)` renderable; `JSON.from_data(data, ...)` skips the string round-trip; `print_json` top-level shortcut in `__init__.py`.

### Traceback (`traceback.py`) — `Traceback(trace=None, *, width=100, code_width=88, extra_lines=3, theme, word_wrap, show_locals, locals_max_length/string/depth, locals_hide_dunder/sunder, indent_guides, suppress=(), max_frames=100)`; `Traceback.from_exception(exc_type, exc_value, tb, ...)`; `Traceback.extract(...)` → `Trace` dataclass (`Stack`/`Frame`); `install(console, *, width, code_width, extra_lines, theme, word_wrap, show_locals, suppress, max_frames, ...)` replaces `sys.excepthook`; `PathHighlighter` styles file paths.

### Logging (`logging.py`) — `RichHandler(level, console, *, show_time, omit_repeated_times, show_level, show_path, enable_link_path, highlighter, markup=False, rich_tracebacks, tracebacks_width/code_width/extra_lines/theme/word_wrap/show_locals/suppress/max_frames, locals_max_length/string, log_time_format="[%x %X]", keywords)` — drop-in `logging.Handler` with optional rich tracebacks.

### Highlighters (`highlighter.py`) — `Highlighter.__call__(text)`; `RegexHighlighter(highlights=[...], base_style)`; `ReprHighlighter` (reprs: numbers/strings/URLs/paths/UUIDs/IPs/bools), `JSONHighlighter` (incl. `json.key` detection), `ISO8601Highlighter` (dates/times/timezones), `NullHighlighter` (disable).

### Inspect (`_inspect.py` + `inspect()` shortcut) — `inspect(obj, *, console, title, help, methods, docs=True, private, dunder, sort=True, all, value=True)` renders a Panel of attributes/methods/signatures.

### Prompt (`prompt.py`) — `Prompt.ask(prompt, *, console, password, choices, show_choices, show_default, default, stream)` → `str`; `IntPrompt` / `FloatPrompt` with validation messages; `Confirm.ask(...)` → `bool` (`choices=["y","n"]`); `PromptBase(password, choices, show_choices, show_default)`; `InvalidResponse` on bad input.

### Misc (one line each)
- `Segment(text, style, is_control)` + `split_cells/split_lines/adjust_line_length/get_shape/set_shape/align_top/bottom/middle` — render pipeline atoms.
- `Control.bell/home/move/move_to/move_to_column/clear/show_cursor/alt_screen/title` + `strip_control_codes/escape_control_codes` — raw terminal codes.
- `Status(status, *, console, spinner="dots", spinner_style, speed, refresh_per_second)` + `update(status, *, spinner, spinner_style, speed)` + `console.status(...)` shortcut.
- `Spinner(name, text, *, style, speed)` + `console.capture()` / `ConsoleThreadLocals` — animation frames (`_spinners.py` data).
- `Markdown(markdown, *, code_theme, justify, hyperlinks, inline_code_lexer, inline_code_theme)` — renders Markdown incl. code fences via `Syntax`.
- `Tree(label, *, style, guide_style, expanded, highlight)` + `add(label, ...)` — directory-style trees.
- `Emoji(name, style, variant)` + ` Emoji.replace(text)` — `:name:` shortcodes (`_emoji_codes.py` data).
- `Rule(title="", *, characters, style, align)` renderable + `Align`, `Padding`, `Constrain`, `Columns`, `Layout` (split_row/split_column), `Screen`, `Pager`, `Scope`, `Bar`, `Styled`, `Constrain` — composable layout renderables.
- `print_json` / `inspect` top-level shortcuts (`__init__.py`); `get_console()` / `reconfigure(...)` global console.
- `TerminalTheme` (`terminal_theme.py`: foreground/background + normal/bright palettes) drives `export_html/svg`.
- `ColorTriplet`, `Palette`, `Filesize.decimal`, `_CELL_WIDTHS`/`_unicode_data`, `_windows.py`/`_win32_console.py`/`_windows_renderer.py` (legacy console), `diagnose.py` (`report()` env dump), `jupyter.py` mixin, `file_proxy.py`, `abc.py`, `_loop.py`, `_pick.py`, `_ratio.py`, `_stack.py`, `_timer.py`, `_log_render.py`, `ansi.py` (`AnsiDecoder`), `protocol.py` (`is_renderable/check_text`), `region.py`, `repr.py` (`rich_repr` decorator), `errors.py` (`MarkupError`, `StyleError`, `MissingStyle`, `StyleSyntaxError`, `ConsoleError`, `LiveError`, `NoSuchLexer`), `default_styles.py`/`themes.py` (DEFAULT theme), `__main__.py` (`python -m rich` demo).

## 2. LATENT CAPABILITIES FOR DDGS (ranked)

1. **`rich.syntax.Syntax` for Reader code blocks** — `Syntax(code, lexer, theme, line_numbers=True, word_wrap=True)` replaces any hand-rolled highlighting in `content_reader_screen.py` (currently `ft.Markdown`-only) with theme + line numbers + wrap in one call; `Syntax.from_path/guess_lexer` auto-detects language for saved files.
2. **Live-style refresh model for the Activity Terminal** — `Live.update(renderable, refresh=True)` is the pattern the Flet `AlertDialog` terminal wants: today it appends plain `ft.Text` per event; a capped render buffer + `Markdown`-code rendering of tracebacks would give per-update rendering instead of unbounded widget growth.
3. **`Console(record=True).export_html(save_html)` for shareable colored logs** — the terminal dialog already has Copy/Share affordances; `save_html(path, inline_styles=True)` produces a single self-contained file for bug reports. CLI/dev-only (Flet cannot render it in-app).
4. **Custom `ProgressColumn` subclasses for the download queue** — `media_downloader.py` already emits `on_progress(written, total)`; a `DownloadColumn + TransferSpeedColumn + TimeRemainingColumn` trio (or one custom `render(task)` merging ETA/bytes/speed) slots into the existing callback for CLI-side batch downloads; the Flet `ft.ProgressBar` in `downloader.py` stays for GUI.
5. **`Table` for receipt/credit history** — `wallet.py` (credit pill only) and `history_screen.py` (`ft.Column` list) have no tabular view; `Table(title, box=ROUNDED, show_lines, row_styles)` + `export_text` gives a copy-pasteable ledger for support. CLI/export-only.
6. **`Traceback` pretty-printing into the logs pipeline** — `Traceback.from_exception(..., show_locals=True, max_frames=...)` or `RichHandler(rich_tracebacks=True)` enriches `InMemoryLogHandler` output that feeds the terminal dialog; `PathHighlighter` keeps paths readable.
7. **`JSON` pretty view for API diagnostics** — `JSON.from_data(payload, indent=2)` + `JSONHighlighter` gives syntax-colored API responses for the diagnostics flow, vs today's raw strings.
8. **Markup for styled system messages** — `[bold]`, `[link=url]`, color tags via `markup.render()` compose chat system/error notices; Flet side maps to `ft.TextSpan` styling (rich itself never renders in Flet).

## 3. GOTCHAS

- **Terminal-only — invisible inside Flet.** Rich renders ANSI to stdout; Flet renders widgets. Every capability above surfaces in DDGS only via (a) the Activity Terminal/logs dialog (plain-text/HTML export), (b) CLI/dev tooling, or (c) as a *pattern* reimplemented with `ft.*` controls. Do not import rich in screen code expecting visual output.
- **Windows width/color detection.** `Console` sniffs `TERM`/`COLORTERM`/`WT_SESSION`/legacy Win32; on old `cmd.exe` it degrades to `ColorSystem.WINDOWS` (16 colors) and `safe_box` ASCII substitution — always pass `width=` explicitly when capturing for the fixed-width terminal dialog, and test under Windows Terminal vs legacy console.
- **Record-buffer memory.** `record=True` keeps every `Segment` in memory until `export_*` with `clear=True`; the 200-record cap in `InMemoryLogHandler` exists for the same reason — mirror it (cap or `clear=True` after export) if wiring `export_html` to the share flow.
- **Import cost placement.** ~0.25 s for the full feature set is fine for `flet_cli`/pytest/CLI entry points but must stay out of the Flet app startup path — lazy-import inside functions.
- **Pygments is a hard dep of `Syntax`.** Using `rich.syntax` pulls `pygments` into the dependency closure; confirm that is acceptable before adopting capability #1.
- **`Live`/alternate-screen vs GUI event loop.** `Live` spawns a refresh thread and hijacks stdout — safe in CLI scripts, breaks under Flet's async UI loop; use only the *update-swap* pattern, never a live `Live` instance, in app code.
- **Markup injection.** `Console.print(..., markup=True)` interprets `[tags]` in *user* content (search queries, page text) — always `escape()` untrusted strings or print with `markup=False`.

## 4. COVERAGE

- **100 / 100 `.py` files accounted for** (167 files on disk incl. `__pycache__`; 100 are `.py` modules).
- **Read completely (22):** `__init__`, `console`, `text`, `markup`, `theme`, `highlighter`, `box`, `panel`, `table`, `live`, `syntax`, `json`, `traceback`, `pretty`, `_inspect`, `prompt`, `logging`, `segment`, `control`, `status`, `style` (class surface), `color` (system enum).
- **Signature-verified via grep/sed (8):** `box` styles, `table`/`panel`/`live`/`syntax`/`json`/`traceback` inits, `progress.add_task/update`, `console.print/rule/status/export_*`, `logging.RichHandler`, `prompt` classes, `pretty.Inspect` inits.
- **Skimmed one-line-each (~70):** `align`, `ansi`, `bar`, `cells`, `color_triplet`, `columns`, `constrain`, `containers`, `default_styles`, `diagnose`, `emoji`, `_emoji_codes`, `_emoji_replace`, `_export_format`, `errors`, `_extension`, `file_proxy`, `filesize`, `_fileno`, `jupyter`, `layout`, `live_render`, `measure`, `markdown`, `_inspect` (covered above), `_log_render`, `_loop`, `_null_file`, `padding`, `pager`, `palette`, `_palettes`, `_pick`, `progress_bar`, `protocol`, `region`, `repr`, `rule`, `scope`, `screen`, `spinner`, `_spinners`, `styled`, `terminal_theme`, `themes`, `tree`, `_timer`, `_stack`, `_ratio`, `_windows`, `_windows_renderer`, `_win32_console`, `_unicode_data/*`, `__main__`, `py.typed`.
- **DDGS side grepped:** `src/` (0 direct rich imports), `sections_about.py` (Activity Terminal dialog), `core/utils.py` (`InMemoryLogHandler`), `services/media_downloader.py` (`on_progress` callback), `components/results/downloader.py` (`ft.ProgressBar`), `screens/{history,chat,content_reader}_screen.py`, `components/wallet.py`, `pyproject.toml`/`uv.lock` (transitive via `flet`, `flet-desktop`, `cookiecutter`).
