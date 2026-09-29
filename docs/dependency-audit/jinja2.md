# jinja2 (+ markupsafe) — Dependency Audit (DDGS)

- Installed: **jinja2 3.1.6**, **markupsafe 3.0.3** (C-extension `_speedups` present; `cp312-win_amd64.pyd`).
- Declared anywhere in `pyproject.toml`? **No.** Not in `[project].dependencies`, not in `[dependency-groups] dev`.
- How it gets into the venv: **dev-only transitive chain** — `flet[cli,desktop]==1.0.1` (dev group) → `flet-cli==1.0.1` → `cookiecutter==2.7.1` → `jinja2` → `markupsafe`. Verified in `uv.lock` (§`cookiecutter` deps list `jinja2`; §`jinja2` deps list only `markupsafe`). Neither the `ddgs` SDK (`click/lxml/primp` only) nor the `ddgs-app` runtime deps pull it in.
- DDGS usage today: **zero imports in `src/`** (grep for `jinja2|jinja|Environment|from_string|SandboxedEnvironment` across `src/` returns nothing). The only consumer is cookiecutter's project-scaffolding path (`StrictEnvironment(undefined=StrictUndefined)`, `FileSystemLoader` in `cookiecutter/generate.py`), exercised by `flet create` / `flet build` scaffolding — never at DDGS runtime.
- Verdict up front: **pure ballast at runtime.** jinja2 + markupsafe ship no value to the running app today, and because they ride the dev-only `flet[cli,desktop]` extra they are absent from any production/`flet build` resolve. Everything below is latent — usable only if DDGS deliberately imports jinja2 in `src/` (which would promote it to a direct dependency and drag it into the Android build).

## 1. COMPLETE API INVENTORY

### Environment — the constructor surface (`environment.py`, 1672 lines; `Environment.__init__`)
- Loaders (keyword `loader=`): `FileSystemLoader(searchpath, encoding, followlinks)` (multi-dir list OK, `searchpath` may be str/Path/sequence), `PackageLoader(package_name, package_path, encoding)` (templates inside installed packages), `DictLoader(mapping)` (inline dict — best for DDGS's single-file export templates), `FunctionLoader(load_func)` (load from DB/network callback), `ChoiceLoader(loaders)` (first-hit across several), `PrefixLoader(mapping, delimiter="/")` (`"app/header.html"` routing), `ModuleLoader(path)` (precompiled template modules), `BaseLoader` (custom subclass hook: override `get_source`).
- `autoescape=True/False/callable` — off by default (`False`); `select_autoescape(enabled_exts, disabled_exts, default, default_for_string)` helper builds the standard `.html/.htm/.xml`-on callable.
- Async: `Environment(enable_async=True)` → `Template.render_async()` / `generate_async()` coroutine variants; sync `render()` on an async env raises (it calls `asyncio.run` only for the sync entry path — see gotchas).
- Bytecode cache: `bytecode_cache=` with `FileSystemBytecodeCache(directory, pattern)` (persistent `.cache` files) or `MemcachedBytecodeCache(client, prefix, timeout)` (shared cache); base `BytecodeCache` is subclassable (`load_bucket`/`dump_bytecode`); `Bucket` carries code + checksum.
- Undefined handling: `undefined=` ∈ `Undefined` (silent empty, default), `ChainableUndefined` (attribute chains don't raise), `DebugUndefined` (renders `{{ hint }}`), `StrictUndefined` (raises `UndefinedError` on any use — what cookiecutter uses), `make_logging_undefined(logger, base)` factory.
- Globals/filters/tests injection: `env.globals` dict (available in every template), `env.filters` / `env.tests` dicts (register custom `do_*`/`test_*`), `env.extend(**attrs)` / `env.overlay(**overrides)` (scoped copy with changed settings); `pass_context` / `pass_environment` / `pass_eval_context` decorators (`utils.py`) mark custom filter args.
- Delimiter/whitespace knobs: `block_start_string/variable_start_string/comment_start_string` (+ `*_end_string`), `trim_blocks`, `lstrip_blocks`, `keep_trailing_newline`, `newline_sequence`, `line_statement_prefix` / `line_comment_prefix` (single-line `{% %}` without delimiters), `cache_size` (template cache, `-1` = unbounded, `0` = off), `auto_reload` (re-parse on mtime change), `finalize` callable (post-process every rendered value), `optimized=True` (AST optimizer pass), `extensions=[...]` list.
- Core methods: `env.get_template(name)` / `get_or_select_template(names)` / `select_template(names)` (+ `*_async` variants), `env.from_string(source, globals, template_class)`, `env.parse(source)` → AST, `env.lex(source)` → token stream, `env.compile(source/template, raw, filename)` → Python source, `env.getitem(obj, arg)` / `getattr`, `env.call(...)`, `env.concat(list)`, `env.handle_exception()`, `env.add_extension(name)`, `env.install_gettext_callables(...)` / `install_null_translations` / `newstyle_gettext`, `env.compile_templates(target, zip, ignore_errors, py_compile)` (ahead-of-time compile to a zip for `ModuleLoader`).

### Template / TemplateModule / TemplateStream / TemplateExpression (`environment.py:1136+`)
- `Template.render(*args, **kwargs)` → str; `generate()` → str iterator (chunked streaming for big exports); `render_async` / `generate_async` (async envs only); `Template.stream()` → `TemplateStream` (`stream.dump(fp, encoding, errors)` writes incrementally, `disable_buffering()`/`enable_buffering()`).
- `TemplateModule` — `template.make_module(vars, shared)` / `module` attribute: top-level `{% macro %}` and assignments accessible as Python attrs without rendering.
- `TemplateExpression` — `env.compile_expression(source)` → evaluable `{{ ... }}` snippet object.
- Render context plumbing: `template.new_context(vars, shared, locals)` / `environment.context_class` (`runtime.Context`: `resolve_or_missing`, `get_all`, `call`, `derived`); `BlockReference` / `block` scoping, `LoopContext` / `AsyncLoopContext` (`loop.index/index0/revindex/first/last/length/cycle/changed/...`), `Macro` objects (callable, `.catch_varargs/.catch_kwargs/.caller`), `Namespace` (`{% ns = namespace(x=0) %}` mutable counters across scopes), `Cycler` (`cycler.next()/current`), `Joiner` (`joiner()` emits sep only after first use).

### Filters — all 50 in `FILTERS` (`filters.py`, 1873 lines; most useful for DDGS starred)
- ★ `tojson(value, policy, indent)` — safe `|safe`-marked JSON dump for embedding crawl data in exported HTML (`htmlsafe_json_dumps` in utils; `Markup` return so autoescape won't double-escape).
- ★ `urlencode(value)` — dict/list → query string (building engine URLs); `urlize(value, trim_url_limit, nofollow, target, rel)` — bare URLs → `<a>` links (result pages).
- ★ `striptags(value)` — strip SGML/XML tags to plain text (search-result snippet cleanup — but see gotchas, use lxml for real parsing).
- ★ `truncate(s, length=255, killwords=False, end="...", leeway)` / `wordwrap(s, width=79)` / `indent(s, width, first, blank)` / `wordcount(s)` / `trim(value, chars)` / `center(value, width)` — snippet/result formatting.
- `escape`/`e` (markupsafe escape), `forceescape` (double-escape even `Markup`), `safe` (mark `Markup`), `xmlattr(d, autospace)` — dict → `key="value"` attribute string for building tags.
- Collections: `sort(value, attribute, reverse, case_sensitive)` / `dictsort(value, case_sensitive, by)` / `groupby(value, attribute)` → `_GroupTuple(grouper, list)` / `unique(value, attribute)` / `sum(value, attribute, start)` / `min/max(value, attribute)` / `map/select/reject/selectattr/rejectattr` (attribute pipelines) / `batch(value, linecount, fill_with)` / `slice(value, slices, fill_with)` / `first/last/random(value)` / `join(value, d, attribute)` / `list/count/length` / `reverse` / `attr(obj, name)` / `items` (dict/Undefined-safe `.items()`).
- Strings/numbers: `upper/lower/capitalize/title/replace/format/pprint/int/float/string/abs/round(value, precision, method)` / `default(v, default_value, boolean)` (+ alias `d`) / `filesizeformat(value, binary)` (`13 KB` / `13 KiB` — download sizes).
- Filter decorator protocol: `@pass_context/@pass_environment/@pass_eval_context` for context-aware custom filters; async variants (`do_join`, `do_first`, `do_groupby`, etc.) exist as `async def` twins gated on env mode.

### Tests — all ~30 in `TESTS` (`tests.py`, 256 lines)
- `defined/undefined/none/boolean/true/false/integer/float/string/number/mapping/sequence/iterable/callable/escaped/lower/upper/odd/even/divisibleby(num)/sameas(other)/in(seq)/filter(name)/test(name)` + operator aliases (`eq/equalto/==`, `ne/!=`, `gt/greaterthan/>`, `ge/>=`, `lt/lessthan/<`, `le/<=`) — `{% if result.url is defined and result is mapping %}` guards for ragged engine payloads.

### Extensions (`ext.py`, 870 lines)
- `LoopControlExtension` — `{% break %}` / `{% continue %}` in loops (off by default).
- `ExprStmtExtension` — `{% do expr %}` (call methods with side effects, e.g. `results.append(x)`).
- `DebugExtension` — `{% debug %}` dumps the current context (template debugging).
- `InternationalizationExtension` — `{% trans %}`/`{% pluralize %}`/`{% trans %}` blocks + `install_gettext_callables` wiring + `babel_extract`/`extract_from_ast` for catalog extraction (needs `babel` — NOT installed here).
- `Extension` base — custom tags via `tags = {"mytag"}`, `parse()` returning AST `nodes.*`; `ExtensionLoaderMixin` used by cookiecutter's `StrictEnvironment`.

### SandboxedEnvironment (`sandbox.py`, 436 lines)
- `SandboxedEnvironment` — `is_safe_attribute` (blocks `_`-prefixed/private attrs), `is_safe_callable` (blocks unsafe builtins), `modifies_known_mutable` guard (blocks `append/pop/...` mutation on unknown objects), `safe_range` (caps `range()` output), `@unsafe` decorator to mark callables callable-only-inside-sandbox; `intercepts_*` operator interception (`str.format` guarded); `ImmutableSandboxedEnvironment` — blocks ALL mutation.
- `SandboxedFormatter` / `SandboxedEscapeFormatter` — safe `str.format` equivalents for user-controlled format strings.

### Meta API (`meta.py`, 112 lines)
- `find_undeclared_variables(ast)` — set of `{{ names }}` a template needs (validate a user-supplied report template's inputs before rendering).
- `find_referenced_templates(ast)` — `{% extends %}/{% include %}/{% import %}` targets (dependency graph of a template pack).

### Compiler / parser / lexer / nodes / optimizer (normally untouched)
- `compiler.py` (1998 lines): `CodeGenerator` → Python source per template; `has_safe_repr`, `find_undeclared`; `nativetypes.NativeEnvironment/NativeTemplate` — render returns native Python objects instead of str (config-file generation).
- `parser.py`/`lexer.py`/`nodes.py`/`visitor.py`/`idtracking.py`/`optimizer.py`/`debug.py`/`async_utils.py`/`constants.py`/`defaults.py`/`exceptions.py`: grammar, token stream, AST node types (`nodes.Template/Output/For/If/Macro/FilterBlock/...`), `NodeVisitor/NodeTransformer`, symbol tracking, constant folding, rewritten tracebacks, async plumbing, `TokenStream`, default delimiters, full exception tree (`TemplateSyntaxError/TemplateNotFound/TemplatesNotFound/TemplateRuntimeError/UndefinedError/TemplateAssertionError`).

### markupsafe (`__init__.py` 396 lines + `_native.py`; `_speedups` C ext active)
- `Markup(str)` — HTML-safe string: escapes on interpolation (`Markup("<b>{}</b>").format(user)` escapes `user`), `+`/`%`/`join` propagate safety, `.escape()`/`.unescape()`/`.striptags()` methods.
- `escape(s)` — `&<>"'` → entities, returns `Markup`; `escape_silent(None)` → `Markup("")` (None-safe).
- `soft_str(s)` — `str()` that preserves `Markup` and `__html__` protocol objects.
- `EscapeFormatter` — `string.Formatter` subclass that escapes interpolated args (`{0!h}` explicit-escape hook).

## 2. LATENT CAPABILITIES FOR DDGS (ranked by value if jinja2 were deliberately adopted)

1. **HTML export templates for saved pages / scrape results** — today `src/components/results/content_fetcher.py` + `src/services/agent_files.py` touch `.html` with hand-built strings. A `DictLoader` + `from_string` template with `{% for result in results %}` + `tojson` embed + `select_autoescape(["html"])` would replace string-concat page building with a maintainable template, and autoescape would fix the latent XSS hole of injecting scraped titles/snippets into saved HTML. Highest value, but requires promoting jinja2 to a direct dependency (Android-build cost).
2. **Autoescape as XSS safety for scraped content** — `select_autoescape` + `Markup`/`escape` give a principled boundary: scraped engine text stays escaped, only deliberate `|safe` passes through. Currently no such boundary exists; any manual HTML builder in `src/` is one missed `.replace()` from script injection. Adoptable independently of full templating (markupsafe alone is tiny).
3. **`tojson` filter for embedding crawl data in exports** — `do_tojson` emits `Markup`-safe JSON with `<`/`>`/`&` hex-escaped, purpose-built for `<script>var data = {{ results|tojson }};</script>` in saved pages. No manual `json.dumps` + escape dance.
4. **Snippet filters for result rendering** — `striptags`/`truncate`/`wordwrap`/`urlize`/`filesizeformat`/`wordcount` map directly onto search-result presentation (snippet cleanup, title truncation, bare-URL linking, download sizes). `urlize`'s nofollow/target args fit external-result linking.
5. **Scheduled digest / report generation** — `Environment` + `FileSystemLoader` rendering Markdown/text crawl digests (daily result summaries, release-notes/changelog automation from git metadata) without pulling a second engine; `batch`/`groupby`/`dictsort` organize results by engine/date; `TemplateStream.dump()` streams large reports.
6. **Sandbox for user-supplied report formats** — if DDGS ever lets users define a custom crawl-report layout, `SandboxedEnvironment` + `meta.find_undeclared_variables` (input validation) + `StrictUndefined` (fail loudly on typos) is the safe stack. Without the sandbox, user templates = arbitrary code execution via `{{ config.__class__... }}` chains.
7. **Async rendering for big templates** — `enable_async=True` + `render_async` keeps large export renders off the event loop; niche (Flet app is sync-UI) and requires asyncio-native loaders (gotcha §3).
8. **`NativeEnvironment` for config generation** — `NativeTemplate.render` returns real Python objects (lists/dicts, not strings); useful only if DDGS ever generates structured config from templates — no current use case.

## 3. GOTCHAS

- **Autoescape is OFF by default** (`autoescape=False` in `defaults.py`). `Environment()` + `from_string("<b>{{ x }}</b>")` renders `x` raw. Any scraped engine title/snippet/URL interpolated through jinja2 without `select_autoescape` or `autoescape=True` is an XSS sink in saved HTML. This is the single most dangerous default for a search app handling hostile web content.
- **`striptags` is not a sanitizer** — regex-ish tag stripping; `style`/`script` content, event attributes, and malformed markup survive. For untrusted scraped HTML, lxml (already a direct dep) + a real allow-list is the correct tool; `striptags` is fine only for display-snippet shortening.
- **`|safe` / `do_mark_safe` is a loaded gun** — one `{{ snippet|safe }}` on engine-supplied text voids all autoescape protection. Grep-ability tip: any future template containing `|safe` on non-`tojson` data deserves a review comment.
- **Sandbox is a speed bump, not a vault** — `SandboxedEnvironment` blocks known attribute/mutation vectors, but sandbox escapes are found periodically upstream; never render truly adversarial templates server-side without process isolation. Fine for "user customizes their own local report" — not for multi-tenant hosting.
- **Async mode is viral** — `enable_async=True` requires async-compatible loaders/filters everywhere (`generate_async`, async `FunctionLoader`); mixing a sync `FileSystemLoader` callback or calling `.render()` instead of `await .render_async()` raises. DDGS's Flet UI code is synchronous, so async buys nothing today.
- **Who actually pulls it in (say it plainly)** — `flet[cli,desktop]` (a **dev-only** extra, pinned `==1.0.1` in `[dependency-groups]`) → `flet-cli` → `cookiecutter` → `jinja2` → `markupsafe`. Remove dev tooling from the resolve (e.g. `flet build` on CI without dev deps) and jinja2 vanishes. Importing jinja2 from `src/` would flip it from invisible-dev-ballast to a shipped runtime + Android-build dependency — that promotion needs an explicit `pyproject.toml` decision, not an accidental import.
- **`NativeEnvironment` changes return types** — `render()` returns `Any` (e.g. `int`, `list`), not `str`; code assuming strings breaks silently.
- **`StrictUndefined` (cookiecutter's choice) raises on everything** — including `{% if x %}` guards on missing keys; templates written against lenient `Undefined` break when the undefined class is swapped. Pick one per project and stick to it.

## 4. COVERAGE

- **jinja2: 26 / 26 `.py` files read** (`__init__`, `_identifier`, `async_utils`, `bccache`, `compiler`, `constants`, `debug`, `defaults`, `environment`, `exceptions`, `ext`, `filters`, `idtracking`, `lexer`, `loaders`, `meta`, `nativetypes`, `nodes`, `optimizer`, `parser`, `runtime`, `sandbox`, `tests`, `utils`, `visitor`; `__pycache__` excluded, `py.typed` marker noted).
- **markupsafe: 2 / 2 `.py` files read** (`__init__`, `_native`; `_speedups` is C source + compiled `.pyd`, inventoried via its `.pyi` stub surface as used by `__init__`).
- Consumer check: `src/` grep (zero hits), `pyproject.toml` deps (absent), `uv.lock` chain (`flet-cli → cookiecutter → jinja2 → markupsafe`), cookiecutter's `environment.py`/`generate.py` usage sample, DDGS `.html`-touching files (`content_fetcher.py`, `app_controller.py`, `agent_files.py`, `chat_agent.py`) listed as the latent adoption surface.
