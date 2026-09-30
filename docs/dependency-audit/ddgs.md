# Dependency Audit — `ddgs` 9.16.0 (namesake search core)

Consumer: `src/services/search_service.py` (`SearchService`) + `src/core/state.py` (defaults).
Package root: `.venv/Lib/site-packages/ddgs/`. ddgs API: `DDGS.text/images/news/videos/books/extract`
only — there is no `maps`, `chat`, `blogs`, `places`, or `translate` method in 9.16.0.

## 1. COMPLETE API INVENTORY

### DDGS class (`ddgs/ddgs.py`) — constructor
- `DDGS(proxy=None, timeout=5, *, verify=True)` — `proxy`: http/https/socks5 URL, or magic alias
  `"tb"` → `socks5h://127.0.0.1:9150` (Tor Browser default); also read from `DDGS_PROXY` env var.
- `timeout` (int|None): per-search wait budget in `_search_sync` (default 5; app sets 15).
- `verify` (bool|str PEM path): forwarded to primp; `False` skips TLS verification.
- `DDGS.threads` (ClassVar, default None): hard cap on search ThreadPool workers; None = automatic.
- Context-manager support (`__enter__`/`__exit__`, no-op) — usable with `with DDGS() as d:`.
- `_engines_cache` (dict): engine instances reused across searches on one client (in-process only;
  there is **no persistent/result cache, no `cache` param, no `fields`/`fieldsets`/`include_raw`
  param** — those do not exist in 9.16.0 despite appearing in some third-party docs).

### DDGS class — search methods (all return `list[dict]`, all raise `DDGSException`/`TimeoutException`)
- `text(query, ...)` → `TextResult{title, href, body}`.
- `images(query, ...)` → `ImagesResult{title, image, thumbnail, url, height, width, source}`.
- `news(query, ...)` → `NewsResult{date, title, body, url, image, source}`.
- `videos(query, ...)` → `VideosResult{title, content(url), description, duration, embed_html,
  embed_url, image_token, images{dict}, provider, published, publisher, statistics{dict}, uploader}`.
- `books(query, ...)` → `BooksResult{title, author, publisher, info, url, thumbnail}`.
- `extract(url, fmt="text_markdown")` → `{url, content}`; `fmt` ∈ `text_markdown | text_plain |
  text_rich | text (raw HTML) | content (raw bytes)`. Backed by primp with random TLS/browser
  impersonation (`impersonate="random"`, `impersonate_os="random"`).

### Shared search params (`_search_sync`, forwarded to every engine's `build_payload`)
- `query` (mandatory; `keywords=` deprecated alias still honored).
- `region` (default `"us-en"`; app defaults to `"wt-wt"`): consumed per-engine — brave/mojeek set
  cookies from it, google sets `hl/lr/cr`, bing-news splits `cc/setlang`, wikipedia picks the
  `lang.` subdomain; annasarchive/yahoo-news ignore it.
- `safesearch` ∈ `on | moderate | off` (default `moderate`).
- `timelimit` ∈ `d | w | m | y` (videos: `d | w | m` only); docstrings claim "or custom date range"
  but every engine maps only the single letters (anything else KeyErrors inside brave/google).
- `max_results` (default 10; `None` = return everything engines yielded, no cap in code).
- `page` (default 1): offset math is per-engine (brave `offset`, mojeek `s=(page-1)*10+1`,
  ddg-images `s=(page-1)*100`, ddg-videos `s=(page-1)*60`, ddg-news `s=(page-1)*30`, yahoo `b=…`).
- `backend` (default `"auto"`): single name, comma-delimited list (`"brave,mojeek"`), or
  `"all"` (= same as auto). Invalid names → `logger.warning` + silent fallback to `auto`.
- `**kwargs` engine extras: images `size/color/type_image/layout/license_image`; videos
  `resolution/duration/license_videos`. Unknown kwargs are silently ignored by engines that
  don't read them.

### Engine registry (`ddgs/engines/`, auto-discovered; `disabled=True` classes excluded)
- text (8 active): `brave` (brave.com), `duckduckgo` (html.duckduckgo.com, provider=bing),
  `google` (google.com/wml, provider=google), `mojeek` (mojeek.com), `yahoo` (search.yahoo.com,
  provider=bing), `wikipedia` (lang.wikipedia.org API, priority 2, limit 1, extra API call fetches
  article extract for `body`), `grokipedia` (grokipedia.com API, priority 1.9, limit 1),
  `startpage` (startpage.com, provider=google). DISABLED: `bing` (text), `yandex`.
- images (2): `duckduckgo` (duckduckgo.com/i.js, provider=bing), `bing` (bing.com/images/async,
  forces count≥35, ignores region/safesearch, timelimit day/week/month/year→minutes map).
- news (3): `duckduckgo` (news.js, provider=bing), `bing` (infinitescrollajax), `yahoo`
  (news.search.yahoo.com; timelimit passed raw as `btf`).
- videos (1): `duckduckgo` (v.js, provider=bing; `resolution`≈high/standart sic, `duration`≈
  short/medium/long, `license_videos`≈creativeCommon/youtube).
- books (1): `annasarchive` (random TLD gd/gl/gk… at import; ignores region/safesearch/timelimit).
- Image filter vocab (ddg-images): size `Small|Medium|Large|Wallpaper`; color `color|Monochrome|
  Red|Orange|Yellow|Green|Blue|Purple|Pink|Brown|Black|Gray|Teal|White`; type
  `photo|clipart|gif|transparent|line`; layout `Square|Tall|Wide`; license
  `any|Public|Share|ShareCommercially|Modify|ModifyCommercially`.
- Cross-cutting: `ResultsAggregator` dedups on `{href,image,url,embed_url}` (frequency-sorted);
  `SimpleFilterRanker` auto-boosts wikipedia.org hits, drops "Category: Wikimedia" pages, then
  title+body > title > body > neither. Text `auto` mode hard-prepends wikipedia+grokipedia.

### Bundled servers/CLI (`api_server/api.py`, `api_server/mcp.py`, `cli.py`)
- `ddgs api`: FastAPI server (port 4479) with typed request models mirroring every search method
  incl. all image/video filters; `extract` endpoint with all 5 formats.
- `ddgs mcp`: 6 MCP tools — `search_text/images/news/videos/books`, `extract_content`.
- CLI extras the app never invokes: `--download` (threaded media download to disk),
  `--output csv|json`, per-command `--threads`, `--proxy`, `--verify` flags.
- Exceptions: `DDGSException`, `TimeoutException`, `RatelimitException` (defined in
  `exceptions.py` but **never raised anywhere in ddgs 9.16.0** — see Gotchas).

## 2. LATENT CAPABILITIES FOR DDGS (ranked by UX impact)

1. **Comma-delimited multi-backend** (`backend="brave,mojeek,startpage"`): app sends one backend
   or auto. UI feature → "Sources…" multi-select chips per search; power users pin their trusted
   engines. Zero backend work — param already forwarded.
2. **`page` deep-pagination UI**: `page` is wired (`state.page`, sent when >1) but nothing in the
   UI ever changes it from 1. UI feature → "Load more" / infinite scroll appending `page=2,3…`.
   (Fresh pages per click; not a cached cursor — label honestly.)
3. **Raise/personalize `max_results` (incl. `None`=uncapped)**: app defaults 20; marketing says
   "up to 100 results" but ddgs itself imposes no ceiling. UI feature → results-count slider up
   to 100 (+ "show everything" for research dives). NOTE interaction with gotcha #1 below.
4. **Bundled REST + MCP servers**: `ddgs api` / `ddgs mcp` ship tested FastAPI + 6 MCP tools with
   zero app exposure. UI/product feature → "Local search API" toggle for user automations, and
   reuse the MCP tool schemas for the in-app chat agent instead of hand-rolled ones.
5. **One-click Tor + custom CA**: proxy/verify DO reach ddgs (`_build_client` passes both —
   confirmed by grep), but the `"tb"` Tor alias, `DDGS_PROXY` env support, and `verify=<PEM path>`
   are unexposed. UI feature → "Route via Tor" preset button + corporate-proxy PEM picker.
6. **`extract(fmt=)` format picker**: `extract_url` already accepts `fmt`, but callers hardcode
   `text_markdown`. UI feature → reader-view mode switch (clean text vs rich vs raw) on saved pages.
7. **Thread-cap control beyond on/off**: `DDGS.threads` is set from `state.threads`, but default 0
   means "ddgs auto" with no UI explanation. UI feature → Speed↔Coverage slider (fewer workers =
   faster first paint; more = broader engine fan-out; see gotcha #1).
8. **CLI-style download/export**: `--download` (parallel media fetch) and csv/json export exist in
   `cli.py`. UI feature → "Export results (.json/.csv)" and "Download all images" buttons reusing
   the existing `media_downloader` + `cache_service`.
9. **Correction of marketing count**: "10 search engines" overcounts effective parallelism — only
   one engine per *provider* runs per search (duckduckgo≡yahoo on bing; google≡startpage), and
   text `auto` always spends 2 slots on wikipedia+grokipedia (1 result each). Honest UI copy:
   "8 sources across 6 providers" + show which backends actually answered (already logged).
10. **Negative findings (do NOT roadmap)**: no `fields`/`fieldsets` payload-trimming, no result
    `cache` param, no `maps`/`chat`/`blogs` categories, no custom date-range timelimits in 9.16.0.
    The app's own `cache_service` page cache already covers the repeat-search case.

## 3. GOTCHAS

1. **`max_results` throttles engine fan-out**: `max_workers = min(unique_providers,
   ceil(max_results/10)+1)`. With the app default 20 → only ~3 providers are even queried; "10
   engines" is only approached with large `max_results` + `backend=all`. Raising the results-count
   slider (item 3 above) is also a coverage control — document it as such.
2. **Provider dedup, not engine dedup**: one engine per provider string per search. Explicit
   `backend="duckduckgo,yahoo"` (both provider=bing) still queries only one of them; the shuffle
   decides which. Never present same-provider backends as additive.
3. **`RatelimitException` is dead code in 9.16.0**: defined, never raised. Rate limits arrive as
   generic `DDGSException`/empty results — the app's `isinstance(primary_err, RatelimitException)`
   branch in `_surface_fallback_failure` can never fire from ddgs itself; keep the
   string-classification path (`classify_error`) as the real detector.
4. **Silent backend substitution**: unknown/empty backend logs a warning and reruns as `auto` —
   results may come from engines the user explicitly deselected. The app's ENGINES-membership guard
   at the send site is the correct mitigation; keep it on any new multi-backend UI.
5. **Threads block the event loop budget**: search is sync ThreadPool work wrapped in
   `asyncio.to_thread`; `timeout` bounds only the inter-batch `wait`, not total latency, and
   wikipedia makes a second serial HTTP call per search. Cancel/generation guards in
   `SearchService` are load-bearing — don't remove them when adding "load more".
6. **Version drift vs older docs**: 9.16 is metasearch-aggregator shaped (`_search_sync` fan-out,
   `ResultsAggregator`, `SimpleFilterRanker`), not the old `DDGS().text()` single-provider client;
   `keywords` is a deprecated alias, backend lists-as-Python-lists are deprecated (use CSV string),
   `bing`/`yandex` text engines are `disabled=True`, and `resolution` vocab has upstream typo
   `"standart"`. Pin `ddgs==9.16.*` and re-audit the registry on every bump (auto-discovery means
   new engines appear/disappear silently).
7. **SSL/impersonation note**: `verify=False` fully disables TLS verification through primp, and
   impersonation is `"random"` profile per client — reproducible TLS-fingerprint issues should set
   a fixed profile in `_primp_client_kwargs` rather than toggling verify off.

## 4. COVERAGE

30/30 `.py` files under `.venv/Lib/site-packages/ddgs/` touched: 14 read in full (`ddgs.py`,
`__init__.py`, `base.py`, `results.py`, `http_client.py`, `engines/__init__.py`, `utils.py`,
`exceptions.py`, `similarity.py`, `cli.py`, plus `brave.py`, `annasarchive.py`, `grokipedia.py`,
`wikipedia.py` payload/extract paths); remaining 13 engine files + `api_server/api.py|mcp.py`
via targeted extraction (class attrs, all `build_payload` filters, request/MCP signatures).
Consumer grep: `src/services/search_service.py` (651 lines, full read) + `src/core/state.py`
param defaults. Proxy/verify reach ddgs: CONFIRMED (`_build_client`, lines 188–225).
