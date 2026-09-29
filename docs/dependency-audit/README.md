# Dependency capability audit

Every package in `.venv` — runtime, build and dev — read source file by
source file by a dedicated agent swarm (43 reports, one per dependency or
tight cluster). Goal (owner): **100% utilization — "there's no need having
a dependency if we are just going to use it for a few use cases."**

Verdicts:

- **ENGINE** — we actively depend on it; the report maps what we still
  don't use.
- **OPPORTUNITY** — installed (usually transitively), barely used, real
  UX/features on the table.
- **BALLAST** — transitive only; keep (removal not actionable / another
  package needs it), never import directly. Honest negatives are results.

## Top cross-cutting wins (correctness first)

| # | Finding | Where |
| :-- | :--- | :--- |
| 1 | **Proxy gap**: `state.proxy` reaches neither primp's media downloads nor any httpx client (search only) — downloads break behind a proxy | `primp.md`, `httpx.md` |
| 2 | **Scraped-HTML XSS pipe**: markdown-it passes `html_inline` tokens through to `ft.Markdown` un-sanitized | `markdown-it.md` |
| 3 | **Mojibake**: Reader hand-decodes without charset sniffing; low-confidence pages garble CJK/Cyrillic | `charset-detectors.md` |
| 4 | **Punycode results**: IDN hosts render raw `xn--…` in result rows | `net-micros-ruff.md` |
| 5 | **primp error surface**: `StatusError.status_code` + primp-native timeouts escape current `except` clauses; fingerprint pinned to `chrome_153` (rots) with no rotate-on-403 | `primp.md` |
| 6 | **CI Android job dies**: default Gradle `-Xmx8G` exceeds the 7 GB runner; Flutter/JDK never cached between jobs | `flet-cli.md` |

## kani — use all of it (owner: "we need every single thing kani can do")

| Capability | Unlocks | Report |
| :--- | :--- | :--- |
| `save()`/`load()` + `.kani` archive | Conversation persistence with tool ids & attachments (replaces hand-rolled JSON projection) | `kani-core.md`, `kani-auxiliary.md` |
| `ReasoningPart` + `BaseParser(show_reasoning_in_stream)` | Native hidden-CoT streaming — Thinking block without our byte-tee hack | `kani-auxiliary.md` |
| `always_included_messages` | RELATED/citation rules pinned against history eviction | `kani-core.md` |
| `auto_truncate=TOOL_OUTPUT_CAP` | Paragraph-aware tool-output caps (no mid-sentence cuts) | `kani-core.md` |
| `enabled` / `get_enabled_functions` | Per-model/per-tier tool gating | `kani-core.md` |
| `max_function_rounds` | Graceful tool-free final answer instead of empty bubbles | `kani-core.md` |
| `assistant_message_thinking(show_args=True)` | Streamed "Thinking… [save_page(url)]" approval previews | `kani-auxiliary.md` |
| Image `MessagePart`s | Send image-search thumbnails to the model visually | `kani-engines.md` |
| `api_type="responses"` | Reasoning continuity + server-side token accounting for o-series | `kani-engines.md` |
| Per-call hyperparams (`response_format`, `seed`, `tool_choice`, `top_p`) | Strict JSON tool args, deterministic tests, chat-vs-tool steering | `kani-engines.md` |
| `msg.extra["openai_usage"]` + TokenCached | **Real token receipts** on every credit charge | `kani-engines.md` |
| `kani` CLI | Prompt/approval debug bench without launching the UI | `kani-auxiliary.md` |
| `PromptPipeline.apply/macro_apply` | Persona/citation injection, orphan-approval hardening | `kani-auxiliary.md` |

## openai — the wire beyond what we send

| Capability | Unlocks | Report |
| :--- | :--- | :--- |
| Final-chunk `usage` (kani already sets `include_usage`) | Exact token billing instead of ~4-chars/token heuristic | `openai-core.md` |
| `response_format=json_schema` / `.parse()` / `pydantic_function_tool` | First-try tool args, typed summary cards | `openai-core.md`, `openai-types.md` |
| `tool_choice` (`required`/`none`/named) | Force search on "find/download", skip tools for chit-chat | `openai-core.md` |
| `prompt_cache_key` + `store` + `metadata` | Cheaper repeated system prompts | `openai-core.md` |
| App proxy on the thought client | Assistant traffic honors `state.proxy` | `openai-core.md` |
| `web_search_options` + `url_citation` annotations | Cited answers straight off the wire | `openai-types.md` |
| `annotations`/`refusal` fields | Source rows + honest declined-states | `openai-types.md` |
| `reasoning_effort`/`verbosity` | Controllable Thinking depth/cost | `openai-types.md` |
| TTS / embeddings / images / files + vector stores | Read-aloud, local semantic history search, `/imagine`, doc Q&A | `openai-beyond-chat.md` |

## Flet — the UX shelf we haven't touched

| Capability | Unlocks | Report |
| :--- | :--- | :--- |
| `Dismissible` | Swipe-to-delete history rows | `flet-core-controls.md` |
| `InteractiveViewer` | Pinch-zoom image results | `flet-core-controls.md` |
| `KeyboardListener` | Desktop shortcuts (Ctrl+K, Esc, arrows) | `flet-core-controls.md` |
| `Semantics` (+reduce-motion) | Screen-reader labels, live announcements | `flet-core-controls.md` |
| ContextMenu / PopupMenuButton | Right-click on results/history/chat (**0 uses**) | `flet-material.md` |
| `Badge` | Download-queue + credit-balance counts (**0 uses**) | `flet-material.md` |
| Rich SnackBar (action/Undo) | Undo for deletes (**15 plain uses today**) | `flet-material.md` |
| `SegmentedButton` | M3 result-type switcher | `flet-material.md` |
| `DatePicker`/`TimePicker` | Crawl-schedule UI (**0 uses; storage exists**) | `flet-material.md` |
| `Share.share_files` | Native share sheet for saved downloads | `flet-services.md` |
| `HapticFeedback` | Download-complete buzz on mobile | `flet-services.md` |
| Window taskbar/`prevent_close`/`WindowDragArea` | Progress in taskbar, close-confirmation, custom titlebar | `flet-services.md` |
| `FilePicker` (beyond save_file) | Chat attachments, chosen download folder | `flet-services.md` |
| CupertinoActionSheet / ContextMenu / Segmented / DatePicker / large-title navbar | Android polish shelf | `flet-cupertino.md` |
| Splash pipeline (`render_splash` + night + A12) | Branded Android splash (unused today) | `flet-runtime.md`, `flet-cli.md` |
| NativeAd templates + impression/click/paid events + UMP consent | Better monetization + analytics | `flet-ads.md` |
| Flet CLI: `FLET_CACHE_DIR`, gradle `-Xmx`, `--arch`, `--ignore-dirs` | Faster CI + dev loop, smaller APK set | `flet-cli.md` |
| `FLET_VIEW_PATH`/`FLET_CLIENT_URL` | Kill per-run desktop-runtime re-downloads | `flet-runtime.md` |

## Search, extraction, media

| Capability | Unlocks | Report |
| :--- | :--- | :--- |
| ddgs `backend="brave,mojeek"` multi-select | Source chips (multi-backend fan-out) | `ddgs.md` |
| ddgs `page` deep pagination | "Load more" infinite scroll (**wired, never leaves page 1**) | `ddgs.md` |
| ddgs `fields`/`fieldsets`, `cache=` | Leaner payloads, instant repeat searches | `ddgs.md` |
| lxml `make_links_absolute` + `iterlinks` | Correct relative links/images in crawl + Reader | `lxml.md` |
| lxml configured `HTMLParser` (recover/no_network) | Broken-page tolerance + SSRF guard | `lxml.md` |
| Pillow `thumbnail()`/WebP/EXIF-strip/`ImageOps.fit` | Faster grids, smaller saves, privacy, uniform tiles | `pillow.md` |
| qrcode `PilImage`/`print_ascii` | "Open on phone" QR, LAN file handoff | `qrcode.md` |
| pygments `HtmlFormatter` (602 lexers) + rich `Syntax` | Syntax-highlighted Reader code blocks | `pygments.md`, `rich.md` |
| rich `Live`, `ProgressColumn`s, `export_html` | Terminal-buffer rendering, ETA/speed rows, shareable logs | `rich.md` |
| slugify (already installed) | Replace hand-rolled `_slug()`/`sanitize_filename()` with unicode-correct slugs | `micro-text-utils.md` |
| regex `timeout=`/fuzzy/`\p{L}` | Backtracking circuit-breaker, typo-tolerant history search | `regex-tqdm.md` |

## Time, files, parsing

| Capability | Unlocks | Report |
| :--- | :--- | :--- |
| arrow `humanize()`/locales/`span` | "in 2 hours" history + next-crawl labels (replaces hand-rolled code) | `arrow-tzdata.md` |
| dateutil `rrule` + tz-aware math | Real schedules ("weekdays 9am"), DST-correct `next_run` | `dateutil.md` |
| watchdog observers + debouncer | Live log tail, downloads auto-refresh, run.py hot-reload | `watchdog.md` |
| jiter `partial_mode` / `from_json` / `allow_inf_nan=False` | Mid-stream tool-arg validation, faster parse, garbage rejection | `jiter.md` |
| anyio `to_thread` / memory streams / task groups / `fail_after` | primp+lxml off the UI loop, back-pressured token queues, structured crawls | `anyio.md` |
| msgpack | Faster/smaller caches & journals (optional; Flet's wire format already uses it) | `msgpack-distro.md` |
| pydantic schema-from-model / TypeAdapter / SecretStr | Tool schemas + settings validation with one source of truth | `pydantic.md` |
| tiktoken exact counts | Real token receipts (same win as openai usage — belt and braces) | `tiktoken.md` |
| packaging `Version`/`SpecifierSet`/`Marker` | Runtime feature gates (kani/openai/flet versions), android-vs-desktop branches | `packaging-typing.md` |

## Test & tooling stack

| Capability | Unlocks | Report |
| :--- | :--- | :--- |
| `pytest.raises(match=)`, `parametrize`, `caplog`, `pytest.warns`, `subtests` | Sharper pins, collapsed duplicates, logger assertions, warning-free guarantees | `pytest-stack.md` |
| anyio's idle strict-mode plugin | Async test scaffolding without new deps | `pytest-stack.md` |
| ruff rule families (`B`, `ASYNC`, `UP`, `S`, `TRY`, `PERF`) | The gate is currently default-only (E4/E7/E9/F); proposed additive select in report | `net-micros-ruff.md` |
| `@override` on `DDGSKani.do_function_call`, TypedDict emit protocol, `@deprecated` | Hardened internal contracts (typing_extensions already installed) | `packaging-typing.md` |

## Ballast (honest negatives — keep, never import)

- **requests + urllib3** — pure transit (tiktoken→requests; cookiecutter dev-only); primp+httpx cover every path. (`requests-urllib3.md`)
- **jinja2 + markupsafe, PyYAML, cookiecutter** — dev-only via flet-cli; never ship to devices. Ideas parked in their reports. (`jinja2.md`, `pyyaml.md`, `cookiecutter-oauthlib.md`)
- **oauthlib** — under flet.auth; "No account, ever" policy parks it. (`cookiecutter-oauthlib.md`)
- **distro, six, colorama, sniffio, chardet, annotated_types, py.py/iniconfig/pluggy** — transitive ballast or test-stack plumbing. (`msgpack-distro.md`, `micro-text-utils.md`, `click-colorama.md`, `net-micros-ruff.md`, `charset-detectors.md`, `annotated-types.md`, `pytest-stack.md`)
- **tqdm, click-for-GUI** — DDGS is a GUI; the `ddgs` lib's own click CLI is the power-user path. (`regex-tqdm.md`, `click-colorama.md`)
- **repath** — live Flet routing plumbing, not ballast but app-internal only. (`micro-text-utils.md`)

## Report index

annotated-types · anyio · arrow-tzdata · charset-detectors · click-colorama ·
cookiecutter-oauthlib · dateutil · ddgs · flet-ads · flet-cli ·
flet-core-controls · flet-cupertino · flet-material · flet-runtime ·
flet-services · httpcore-h11 · httpx · jinja2 · jiter · kani-auxiliary ·
kani-core · kani-engines · lxml · markdown-it · micro-text-utils ·
msgpack-distro · net-micros-ruff · openai-beyond-chat · openai-core ·
openai-types · packaging-typing · pillow · primp · pydantic · pygments ·
pytest-stack · pyyaml · qrcode · regex-tqdm · requests-urllib3 · rich ·
tiktoken · watchdog — each a `.md` beside this file.
