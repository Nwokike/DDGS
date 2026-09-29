# markdown-it-py + mdurl — Dependency Audit (DDGS)

- Versions: `markdown-it-py 4.2.0`, `mdurl 0.1.2` (both under `.venv/Lib/site-packages/`).
- Provenance: **transitive** — pulled in by `rich` (`rich -> markdown-it-py -> mdurl`); `pyproject.toml` does not declare it, and nothing under `src/` imports it.
- Consumer today: all Markdown display goes through **Flet's `ft.Markdown`** (`extension_set="gitHubWeb"`, `on_tap_link=...`) in 4 places — `src/screens/content_reader_screen.py` (Reader), `src/components/ai_overview.py`, `src/components/results/cards.py` (Extract view), `src/screens/chat_screen.py` (assistant replies). `ft.Markdown` is a Flutter-side renderer; markdown-it-py options do **not** affect it. Every latent capability below is therefore a **preprocessing/parsing** opportunity, not a rendering switch.

## 1. COMPLETE API INVENTORY

### Constructor & configuration
- `MarkdownIt(config="commonmark", options_update=None, *, renderer_cls=RendererHTML)` — `config` is a preset name (`default`, `js-default`, `zero`, `commonmark`, `gfm-like`, `gfm-like2`) or a preset dict.
- `.configure(preset, options_update)` — batch-load options + component rule sets (prefers presets over hand-rolled dicts).
- `.set(options)` — replace the whole options dict post-construction (docs advise separate instances per config instead of mutating live).
- `.enable(names, ignoreInvalid=False)` / `.disable(names, ...)` — chainable, searches core/block/inline/inline2 rulers for the rule name.
- `.reset_rules()` — context manager that snapshots active rules and restores them on exit.
- `.get_all_rules()` / `.get_active_rules()` — dicts keyed `core`/`block`/`inline`/`inline2`.
- `.use(plugin, *params, **options)` — plugin loader sugar: `plugin(md, *params, **options)`.
- `.add_render_rule(name, function, fmt="html")` — override rendering for one token type (bound to the renderer instance).
- `md[name]` — `__getitem__` accessor for `"inline"`, `"block"`, `"core"`, `"renderer"`.
- `Ruler`: `.push(before/after/at)` insertion, `.enable/.enableOnly/.disable`, `.getRules/.get_all_rules/.get_active_rules` — the per-chain rule registry behind `enable/disable`.

### Parse / render entry points
- `.parse(src, env)` — full block+inline pass, returns block `Token` list (`inline` tokens carry `children`).
- `.render(src, env)` — `parse` + `renderer.render`, returns HTML string.
- `.parseInline(src, env)` — inline-only pass (single paragraph, no block rules).
- `.renderInline(src, env)` — inline render, result NOT wrapped in `<p>`.
- `.validateLink(url)` — XSS gate for link hrefs (blocks `javascript:/vbscript:/file:/data:` except an image `GOOD_DATA_RE` allowlist).
- `.normalizeLink(url)` — normalize link destinations via mdurl + punycode host recoding.
- `.normalizeLinkText(url)` — normalize `<autolink>` text (punycode to unicode for display).

### Options (all presets share these keys)
- `maxNesting` — recursion guard (20 in commonmark/zero/gfm-like, 100 in default).
- `html` — shorthand for enabling `html_block` + `html_inline` rules (True in commonmark!, False in default/zero).
- `linkify` — autolink bare URLs/emails (False everywhere; needs `linkify-it-py`, see gotchas).
- `typographer` — master switch for `replacements` + `smartquotes` core rules (False everywhere).
- `quotes` — quote-pair string for smartquotes (`"\u201c\u201d\u2018\u2019"`, localizable e.g. Russian `«»„"`).
- `xhtmlOut` — self-close void tags (`<br />` vs `<br>`).
- `breaks` — soft `\n` in paragraphs becomes `<br>`.
- `langPrefix` — CSS class prefix for fenced code language (`language-`).
- `highlight(str, lang, attrs)` — callback returning highlighted HTML for fences (return `''` to fall back to escaping; a `<pre...` return skips the wrapper).
- `tasklists` / `tasklists_editable` — only in `gfm-like2` (True/False); read by the list rule + renderer checkbox.
- `alerts` — only in `gfm-like2` (True); read by the blockquote rule for `> [!NOTE]` GitHub alerts.
- `strikethrough_single_tilde` — only in `gfm-like2` (True); accept `~x~` besides `~~x~~`.

### Presets
- `default` — `html: False`, `maxNesting: 100`, every registered rule active.
- `commonmark` — `html: True`, `maxNesting: 20`; core drops `linkify/replacements/smartquotes`, block drops `table`, inline drops `strikethrough/linkify`.
- `zero` — bare minimum (core: normalize/block/inline/text_join; block: paragraph only; inline: text + balance_pairs/fragments_join) for hand-built configs.
- `gfm-like` — commonmark + `linkify: True`, `html: True`, adds core `linkify`, block `table`, inline `strikethrough`+`linkify` (+inline2 `strikethrough`).
- `gfm-like2` — gfm-like + tasklists, alerts, single-tilde strikethrough.
- `js-default` — alias of `default`.

### Core rules (`parser_core._rules`)
- `normalize` — newline normalization + NULL-char replacement before anything else.
- `block` — run the block chain over source lines.
- `inline` — tokenize inline content of each block token.
- `linkify` — post-pass autolinking of plain-text URLs (gated on `options.linkify` + installed `linkify-it`).
- `replacements` — typographic swaps: `(c)/(tm)/(r)` → ©/™/®, `+-` → ±, `...` → …, `?...`/`!...` collapsing, `--` → –, `---` → — (gated on `typographer`).
- `smartquotes` — straight `'"` → locale `quotes` pairs with apostrophe detection (gated on `typographer`).
- `text_join` — merge adjacent text tokens into one.

### Block rules (`parser_block._rules`, each with terminatoralts)
- `table` — GFM pipe tables (terminates paragraph/reference); OFF in commonmark/default-off lists.
- `code` — 4-space indented code block.
- `fence` — ``` fenced code with info string → `language-` class or `highlight()` output (terminates paragraph/reference/blockquote/list).
- `blockquote` — `>` quotes; honors `alerts` option for `[!NOTE]`-style GitHub alerts.
- `hr` — `***`/`---`/`___` horizontal rule.
- `list` — ordered/bullet lists incl. tight-list handling; honors `tasklists` option (`- [x]` → `checked` meta on `list_item_open`).
- `reference` — `[label]: destination 'title'` link definitions (feeds `env.references`).
- `html_block` — raw HTML block passthrough (gated on `options.html`).
- `heading` — ATX `#`–`######` headings.
- `lheading` — Setext `===`/`---` underlined headings.
- `paragraph` — fallback paragraph collector.
- `make_fence_rule(...)` — factory in `rules_block/fence.py` for custom fence flavors.

### Inline rules (`parser_inline._rules` + `_rules2`)
- `text` — plain-text tokenizer (the fallback everything else defers to).
- `newline` — soft/hard break handling (`  \n` hard break; `breaks` option turns soft into `<br>`).
- `escape` — backslash escapes for ASCII punctuation.
- `backticks` — `` `code` `` spans (matched-length delimiter runs).
- `strikethrough` — `~~x~~` delimiters + `postProcess` pairing (single-tilde only with option).
- `emphasis` — `*`/`_` delimiters + `postProcess` pairing (`__` vs `_` rules included).
- `link` — `[text](href "title")` + reference links via `env.references`.
- `image` — `![alt](src)` (alt rendered via `renderInlineAsText` per CommonMark).
- `autolink` — `<http://x>` / `<user@mail>` autolinks with `normalizeLinkText`.
- `html_inline` — raw inline HTML passthrough (gated on `options.html`).
- `entity` — `&amp;` / `&#123;` entity decoding.
- `linkify` (inline) — bare-URL tokenizing via `linkify-it` (needs option + package).
- `balance_pairs` / `fragments_join` (inline2) — link-pair matching + merging of unused delimiter text.

### Renderer (`renderer.py` — `RendererHTML`, `__output__ = "html"`)
- `.render(tokens, options, env)` — block token stream → HTML (dispatches `inline` tokens to `renderInline`, unknown types to `renderToken`).
- `.renderInline(tokens, options, env)` — inline token list → HTML fragment.
- `.renderToken(tokens, idx, options, env)` — generic fallback: tag + escaped attrs + nesting-aware open/close + tight-list `hidden` handling.
- `.renderAttrs(token)` — static, escapes every attr key/value pair.
- `.renderInlineAsText(tokens, options, env)` — markup-stripped text (used for `img alt`).
- `code_inline` — `<code>` with escaped content.
- `code_block` — indented code → `<pre><code>` escaped.
- `fence` — info-string parsing, `highlight()` hook, `langPrefix` class injection without mutating the token.
- `image` — forces `alt` attr (even empty), then generic render.
- `hardbreak` / `softbreak` — `<br>` honoring `xhtmlOut`/`breaks`.
- `text` — HTML-escaped literal text.
- `html_block` / `html_inline` — **raw passthrough** of source HTML (the XSS surface).
- `list_item_open` — injects `<input class="task-list-item-checkbox" disabled type="checkbox">` when `token.meta["checked"]` exists.
- Custom output: subclass `RendererHTML` (override `*_open/*_close` methods) or pass `renderer_cls=` — e.g. rewrite `link_open` hrefs for in-app handling or emit Flet-span tuples instead of HTML.

### Token model (`token.py`)
- Fields: `type`/`tag`/`nesting` (1 open, 0 self-close, -1 close), `attrs` dict, `map` source lines, `level`, `children`, `content`, `markup`, `info` (fence lang / autolink `auto` / list marker), `meta` plugin scratch, `block`, `hidden` (tight lists).
- Methods, one line each: `attrIndex(name)` locate attr; `attrItems()` list pairs; `attrPush(pair)` append; `attrSet(name, value)` upsert; `attrGet(name)` lookup; `attrJoin(name, value)` space-append (CSS classes); `copy(**changes)` clone; `as_dict()/from_dict()` JSON round-trip.

### Syntax tree, helpers, common, CLI
- `SyntaxTreeNode(tokens)` — nest-aware tree over the flat token stream (root/container/leaf), `.to_tokens()` flattens back; natural TOC/outline/DOM mapper.
- `helpers`: `parseLinkDestination` / `parseLinkLabel` / `parseLinkTitle` — low-level link-part scanners reusable for custom inline rules.
- `common.normalize_url` — `validateLink` + `normalizeLink` + `normalizeLinkText` (BAD_PROTO gate + punycode).
- `common`: `entities` (HTML entity table), `html_blocks`/`html_re` (block-tag recognizers), `utils.escapeHtml/unescapeAll/...`.
- `cli/parse.py` — `markdown-it` CLI: convert files/stdin to HTML (handy for offline fixture generation in tests).

### mdurl (URL plumbing under `normalizeLink`)
- `parse(url, slashes_denote_host)` → `URL(protocol, slashes, auth, port, hostname, hash, search, pathname)` NamedTuple.
- `format(url)` — serialize `URL` back to string; `encode(str, ...)` / `decode(str, ...)` percent-codec with `ENCODE/DECODE_DEFAULT_CHARS` + `COMPONENT_CHARS` variants and encode/decode caches.

### Explicitly NOT in core
- `footnote` — no rule, no renderer support, no `mdit-py-plugins` installed: `[^1]` renders as literal text everywhere.
- `tasklists`/`alerts` are **option flags**, not enableable rules — `.enable("tasklists")` raises; set `options_update={"tasklists": True}` or use the `gfm-like2` preset.

## 2. LATENT CAPABILITIES FOR DDGS (ranked)

1. **Scraped-HTML sanitization before `ft.Markdown`** — run Reader/Extract markdown through `MarkdownIt("gfm-like2", {"html": False})` (or a token filter dropping `html_block`/`html_inline`) so hostile `<script>`/`<iframe>` in fetched pages never reach the view. Biggest safety win; ~10 lines in `content_fetcher.py`.
2. **Relative-URL absolutization via token rewrite** — `parse()` the fetched markdown, walk `link_open`/`image` tokens, resolve relative `href`/`src` against the page URL with `mdurl.parse/format` + `normalizeLink`, re-render. Fixes broken images/links from `text_markdown` extraction; complements the existing `on_tap_link` handlers.
3. **Inline parsing for chat/AI-overview snippets** — `renderInline()`/`parseInline()` for single-line assistant text, pills, and related-query chips: bold/links without the block wrapper, cheaper than a full parse.
4. **Typographer polish for the Reader** — `typographer: True` preprocessing (smartquotes + `(c)`/`--`/`...` replacements) for long-form reads; locale-aware via the `quotes` option.
5. **Bare-URL linkification** — `linkify: True` turns pasted URLs in chat/notes into links; requires adding `linkify-it-py` (NOT installed — enabling today raises `ModuleNotFoundError`).
6. **Zero-preset cheap parsing** — `MarkdownIt("zero")` + only needed rules for word counts, excerpt/TOC extraction, or plain-text stripping for search indexing without paying for a full parse.
7. **`SyntaxTreeNode` document outline** — build a section TOC / jump-list for long Reader pages from heading tokens instead of regexing markdown.
8. **Custom renderer for in-app link policy** — override `link_open`/`image` render rules (or a non-HTML `renderer_cls`) to tag external vs in-app URLs, lazy-load images, or emit sanitized Flet-span structures.
9. **`highlight` callback for code fences** — route fenced blocks through the already-vendored `pygments` for consistent code styling in the Reader.
10. **Footnote-shaped citations** — NOT available in core; citation-heavy pages would need `mdit-py-plugins` (new dependency, Android-build vetting required) — listed so nobody assumes `[^1]` works.

## 3. GOTCHAS

- **Preset HTML defaults are inverted from intuition**: `commonmark` has `html: True`, `default` has `html: False` — constructing bare `MarkdownIt()` (default config is `"commonmark"`) passes scraped HTML straight through.
- **`html=True` is an XSS pipe**: `html_block`/`html_inline` renderer rules emit source HTML verbatim; `validateLink` only guards link hrefs, not embedded tags — always disable or filter for untrusted fetch output.
- **`linkify` without `linkify-it-py` crashes**: `MarkdownIt` sets `self.linkify = None` when the package is missing and the core rule raises `ModuleNotFoundError` on use; the venv has no `linkify` distribution.
- **No footnotes, ever (in core)**: `footnote` appears nowhere in the package; `[^a]` is literal text unless a plugin is added.
- **`tasklists`/`alerts` are not rules**: they live only in `options` and are read by the `list`/`blockquote` rules — enable via `options_update` or the `gfm-like2` preset, not `.enable()`.
- **`default` ≠ GFM**: `default`/`commonmark` lack `table` + `strikethrough`; GFM behavior needs `gfm-like`/`gfm-like2`, and full GFM still lacks raw-HTML filtering per the preset docstring.
- **`breaks` vs `xhtmlOut` vs `langPrefix`** are renderer-consumed, parser-ignored — setting them without using `RendererHTML.render` does nothing.
- **`maxNesting` is a DoS knob**: 20 (commonmark/zero) vs 100 (default); keep it low for unbounded scraped input.
- **Don't mutate a live instance per document**: the class docstring warns options changes defeat internal caching — keep one configured instance per preset (Reader vs chat-inline vs zero).
- **markdown-it-py ≠ what the user sees**: `ft.Markdown` (`gitHubWeb`) renders independently; markdown-it changes only take effect as preprocessing/token rewriting before handing `value=` strings to Flet.

## 4. COVERAGE

- `markdown_it`: 66/66 `.py` files enumerated; fully read: `main.py`, `renderer.py`, `token.py` (API), `presets/__init__.py`, `presets/commonmark.py`, `presets/default.py`, `presets/zero.py`, `rules_block/__init__.py`, `rules_inline/__init__.py`, `rules_core/__init__.py`, `mdurl/__init__.py`; structurally scanned (rule-registration lists, signatures, gating conditions, heads): `parser_block.py`, `parser_core.py`, `parser_inline.py`, `ruler.py`, `utils.py`, `tree.py`, `common/normalize_url.py`, `rules_core/linkify.py`, `rules_core/replacements.py`, `rules_core/smartquotes.py`, `rules_inline/strikethrough.py`, `rules_inline/html_inline.py`, `rules_block/html_block.py`, `rules_block/list.py`, `rules_block/blockquote.py`, `helpers/__init__.py`, `cli/parse.py`, `mdurl/_parse.py`, `_format.py`, `_encode.py`, `_decode.py`, `_url.py`; remainder (individual rule bodies, entities table, punycode, state objects) covered via their registration/docstrings only.
- `mdurl`: 6/6 `.py` files covered (`__init__` fully read, submodules via signatures + `normalize_url` call sites).
- Consumer grep: `src/screens/content_reader_screen.py`, `src/screens/chat_screen.py`, `src/components/ai_overview.py`, `src/components/results/cards.py` (all four `ft.Markdown` call sites confirmed with `extension_set="gitHubWeb"` + `on_tap_link`); `uv.lock` confirms `rich -> markdown-it-py -> mdurl` chain; venv confirms `linkify-it-py` absent.
