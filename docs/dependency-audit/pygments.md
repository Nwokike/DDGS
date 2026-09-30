# Pygments 2.21.0 — Dependency Audit for DDGS

- Location: `C:\Users\nwoki\.zcode\workspace\default\DDGS\.venv\Lib\site-packages\pygments\`
- Files: 343 `.py` files | Lexers: 602 builtins | Formatters: 18 classes | Styles: 49 builtins | Filters: 8
- DDGS status: **transitive-only, 0% utilized** — zero `import pygments` / `from pygments` hits in `src/`; it arrives via `rich 15.0.0 → pygments` and `pytest 9.1.1 → pygments` in `uv.lock`. Neither `pygments` nor `rich` is a direct dep in `pyproject.toml` (`ddgs-app` direct deps: certifi, ddgs, flet, flet-ads, httpx, kani, lxml, primp).
- Consumer surfaces: Extract/Reader screen (`src/screens/content_reader_screen.py` renders `ft.Markdown`, no code styling wired) and live terminal/diagnostics output.

## 1. API Inventory (one line each)

- `pygments.highlight(code, lexer, formatter, outfile=None)` — highest-level call; combines `lex()` + `format()`; all three take **instances, not classes** (TypeError guard tells you).
- `pygments.lex(code, lexer)` — returns `(ttype, value)` token iterable via `lexer.get_tokens()`.
- `pygments.format(tokens, formatter, outfile=None)` — returns string, or writes to `outfile` when given.
- `get_lexer_by_name(alias, **options)` — e.g. `python`, `html`, `diff`; raises `ClassNotFound` on unknown alias (always wrap with `TextLexer` fallback).
- `get_lexer_for_filename(fn, code=None)` — fnmatch on `*.py`-style patterns, `analyse_text()` breaks ties.
- `get_lexer_for_mimetype(mime)` — e.g. `text/x-python`, handy for scraped `Content-Type` headers.
- `guess_lexer(text)` / `guess_lexer_for_filename(fn, text)` — scores every lexer via `analyse_text()` (+ vim-modeline check); raises `ClassNotFound` when nothing scores.
- `find_lexer_class(name)` / `find_lexer_class_by_name(alias)` / `get_all_lexers()` / `load_lexer_from_file(path)` — class-level lookup, inventory, and custom-lexer `exec()` loading (untrusted files = code exec, never run on scraped input).
- Token hierarchy essentials — `Token` root; `Text/Whitespace/Escape/Error/Other`; `Keyword.*`, `Name.*` (Function/Class/Tag/Variable…), `Literal.String.*` + `Literal.Number.*`, `Operator`, `Punctuation`, `Comment.*`, `Generic.*` (Deleted/Inserted/Heading/Traceback — diffs); subtype test is `ttype in other`; `string_to_tokentype()` parses dotted names.
- `STANDARD_TYPES` — maps every token to a short CSS class (`k`, `nf`, `s2`, `gd`…); basis of all HTML output.
- `HtmlFormatter` — `<span>` + `<pre>` in `<div class="highlight">`; key opts: `linenos='table'|'inline'`, `hl_lines`, `linenostart/linenostep/linenospecial`, `lineanchors/linespans/anchorlinenos`, `noclasses` (inline styles), `classprefix`, `cssclass`, `nowrap`, `full`+`title`+`cssfile`, `wrapcode` (HTML5 `<code>`), `filename`, `debug_token_types`, subclassable via `wrap()`/`_format_lines()`.
- `HtmlFormatter.get_style_defs(arg)` — returns the CSS for the active style; `arg` is a selector string **or list** prepended to every rule — the theming hook for any WebView display.
- `TerminalFormatter` (`terminal`/`console`) — 16-color ANSI, **ignores `style`**; opts `bg='light'|'dark'`, `colorscheme` dict, `linenos`.
- `Terminal256Formatter` (`terminal256`/`console256`/`256`) — maps the active **style** to nearest 256-color ANSI; `linenos`, `nobold/nounderline/noitalic` kills.
- `TerminalTrueColorFormatter` (`terminal16m`/`console16m`/`16m`) — full 24-bit `38;2;r;g;b` ANSI from the style, same base class as 256.
- `SvgFormatter` (`svg`) — **experimental**; one `<text>` per line with explicit x/y + `<tspan>` token styles; opts `fontfamily/fontsize/linenos/ystep/yoffset/spacehack/nowrap`.
- `ImageFormatter`/`Gif`/`Jpg`/`BmpImageFormatter` (`img/png/gif/jpg`) — renders code to raster via **Pillow (verify installed)**; font search per-OS (DejaVu/Courier New/Menlo).
- `LatexFormatter` (`latex`/`tex`) — `fancyvrb` + `color` packages, full-document mode for PDF export.
- `RtfFormatter` (`rtf`) — full RTF doc output, copy-paste into Word with colors intact.
- `BBCodeFormatter`/`IRCFormatter`/`GroffFormatter`/`PangoMarkupFormatter` — niche sinks: forums, IRC color codes, man pages, Pango→SVG chain.
- `NullFormatter` (`text`/`null`) — byte-identical passthrough, useful as the no-op branch of a formatter switch.
- `RawTokenFormatter` (`raw`/`tokens`, + `RawTokenLexer`) — serializes token streams (`ttype<TAB>repr`, opt. gz/bz2) for caching highlighted extracts.
- `TestcaseFormatter` — emits new-lexer test cases, dev-tooling only.
- Styles (49 via `get_style_by_name`/`get_all_styles`) — light: `default friendly vs xcode autumn borland colorful emacs manni murphy pastie perldoc tango trac lightbulb lovelace stata-light solarized-light gruvbox-light paraiso-light`; dark: `monokai dracula native github-dark night-owl one-dark nord nord-darker gruvbox-dark zenburn fruity inkpot paraiso-dark rrt stata-dark vim solarized-dark material`; neutral/special: `bw rrt sas coffee igor murphy abap algol algol_nu arduino lilypond rainbow_dash staroffice`; custom theme = subclass `Style` with `styles={Token.Keyword: 'bold #ff0000', …}` + `background_color`/`highlight_color`.
- `Style.style_for_token(token)` — returns `color/bold/italic/underline/bgcolor/…` dict: the bridge for mapping tokens to **native Flet `TextSpan`s** without HTML.
- Filters (8, `get_filter_by_name`) — `codetagify` (TODO/FIXME/BUG/NOTE/XXX in comments), `keywordcase`, `highlight` (extra name highlighting), `raiseonerror`, `whitespace` (visible spaces), `gobble` (strip prompts), `tokenmerge`, `symbols`; attach with `lexer.add_filter(f)`.
- Plugins/entry points — `pygments.lexers` / `pygments.formatters` / `pygments.styles` / `pygments.filters` via `importlib.metadata` (`functools.cache`d); third-party lexers auto-appear in `get_all_lexers()`.
- `pygments.util` — `ClassNotFound`, `OptionError`, `get_bool/int/list/choice_opt`, `html_escape` (None-safe), `guess_decode`, `shebang_matches`, `looks_like_xml`, `modeline.get_filetype_from_buffer` (vim modeline powers `guess_lexer`).
- `pygments.cmdline` (`pygmentize`) — CLI with `-S style` style-def dump and `-O opt=val` formatter options; dev/debugging use.

## 2. Latent Capabilities for DDGS (ranked)

1. **Highlighted code blocks in the Extract/Reader screen** — scraped Markdown arrives with ` ```lang ` fences that `ft.Markdown` renders monochrome; run each fence through `get_lexer_by_name(lang)` (fallback: `guess_lexer` → `TextLexer`) + `HtmlFormatter(noclasses=True)` or token→`TextSpan` via `style_for_token()`, and code becomes the best-looking part of the reader. Biggest visible win, near-zero risk.
2. **Terminal-colored diagnostics output** — the live terminal/diagnostics screen can pipe tracebacks/logs through `PythonTracebackLexer`/`TextLexer` + `Terminal256Formatter(style='github-dark')` for instantly scannable colored diagnostics instead of plain text.
3. **`guess_lexer` for unknown scraped snippets** — code blocks without an info string (Stack Overflow copies, inline samples) get language auto-detection instead of being rendered as dead grey text.
4. **Custom `Style` matching the app theme** — one ~20-line `Style` subclass keyed to `AppColors` (see `src/core/theme.py`) makes highlights, `get_style_defs()` CSS, and terminal colors all follow light/dark mode from a single source of truth.
5. **Line numbers + table wrappers for readable code** — `linenos='table'`, `linenostart` (match source line!), `hl_lines` (flag the exact lines an answer refers to), `lineanchors` for deep-linkable lines in long extracts.
6. **Diff highlighting for version comparisons** — `DiffLexer` maps `+`/`-` to `Generic.Inserted`/`Generic.Deleted`; re-extracts of a changed page (or Refresh-vs-cache) render as red/green diffs for free.
7. **SVG code images for a share feature** — `SvgFormatter` output is resolution-independent and Story/post-friendly; `ImageFormatter` (Pillow) is the PNG fallback for platforms that won't take SVG.
8. **`codetagify` filter on scraped code** — TODO/FIXME/BUG/NOTE comments in extracted samples get highlighted automatically, a genuinely useful reader touch nobody else ships.
9. **`RawTokenFormatter` token-stream cache** — highlighted extracts can be cached as token streams next to the 24h page cache (`SearchService` extract path) so re-renders skip re-lexing entirely.
10. **Mimetype-driven lexer choice** — the extractor already sees `Content-Type`; `get_lexer_for_mimetype()` picks the right lexer for `text_rich`/raw fetches without filename guessing.

## 3. Gotchas

- **HTML escaping: output is safe, the widget is the problem.** `HtmlFormatter` escapes all code text (`html.escape`, `quote=False` split per line) and escapes options (`cssclass`, `filename`, `lineanchors`…), so injecting its HTML into a real browser/WebView is XSS-safe; but **`ft.Markdown` does not render raw HTML spans** — highlighted HTML needs a WebView control or a token→`ft.TextSpan` conversion (use `style_for_token()`), never pasted into `ft.Markdown` expecting colors.
- **Flet rich-text path is `TextSpan`, not CSS.** There is no `code_theme`/CSS hook wired on the reader's `ft.Markdown` today — plan on building `ft.Text` + `TextSpan(style=ft.TextStyle(color=…))` runs from the token stream for native rendering.
- **Import weight is small if you're precise, large if you guess.** Package is ~5.5 MB / 343 files but lazily loaded: `get_lexer_by_name` imports exactly one lexer module, so direct highlighting costs ~ms; `guess_lexer()` imports **all 602 lexer classes** — never call it per-fence on long pages, gate it behind "no info string AND short snippet", and prefer `get_lexer_for_filename`/`by_name`.
- **Version 2.x API (`2.21.0` installed).** `highlight(code, lexer_instance, formatter_instance)`; passing classes raises a helpful TypeError. `style=` accepts a name string or `Style` subclass on every formatter **except** `TerminalFormatter` (uses `bg`+`colorscheme`). `linenos=True` means `'table'` (copy-paste-hostile); use `'inline'` when users copy code.
- **`ClassNotFound` is the normal control flow.** Unknown alias, unmatched filename, failed guess, missing style all raise it (a `ValueError` subclass) — every lexer/style lookup needs `try/except ClassNotFound → TextLexer/'default'`.
- **Experimental/optional bits.** `SvgFormatter` is explicitly experimental (fixed-coordinate layout, long files need `linenowidth` tuning); `ImageFormatter` needs Pillow (not confirmed in this venv); `tagsfile` needs `python-ctags` + `lineanchors`; `LatexFormatter` full docs need `fancyvrb`+`color` LaTeX packages.
- **Don't `load_lexer_from_file` on untrusted paths** — it's `exec()` on the file; scraped content must never flow through it.

## 4. Coverage

- **Read completely:** `__init__.py` (lex/format/highlight), `token.py` (full hierarchy + STANDARD_TYPES), `lexers/__init__.py` (all selection/guess APIs), `formatters/__init__.py`, `formatter.py` (base + get_style_defs contract), `formatters/html.py` (all ~30 options + subclassing), `formatters/terminal.py`, `formatters/terminal256.py` (incl. TrueColor), `style.py` (metaclass + style_for_token), `styles/__init__.py`, `plugin.py` (entry points), `util.py`, `console.py` (ANSI helpers).
- **Read partially (headers/options/class surface):** `lexer.py` (base options), `formatters/svg.py`, `formatters/img.py`, `formatters/latex.py`, `formatters/rtf.py`, `formatters/bbcode.py`, `formatters/other.py`, `filters/__init__.py` (FILTERS dict + CodeTagFilter).
- **Enumerated without per-file reads:** all 602 lexer identities via `get_all_lexers()` at runtime + `_mapping.py` spot-checks (Python/Diff/Markdown entries verified); all 18 formatter classes via `formatters/_mapping.py` (complete table, docstring for each); all 49 styles via `styles/_mapping.py` (complete); 8 filters via `FILTERS` dict; DDGS side verified by grepping `src/` (zero hits), `pyproject.toml` (no direct dep), `uv.lock` (`rich 15.0.0 → pygments`, `pytest → pygments`), and `content_reader_screen.py` (`ft.Markdown`, no code styling).
- **Not individually opened:** ~230 lexer implementation modules, ~40 individual style files, `cmdline.py`/`sphinxext.py`/`scanner.py` internals — none affect the API inventory above; lexer/mapping tables are machine-generated and were verified structurally, not line by line.
