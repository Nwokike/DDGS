# 100% utilization plan

Basis: the 43 source-level audits in this folder (index: `README.md`).
Ordering rule: **correctness first, then felt-UX, then assistant
intelligence, then depth, then speed, then foundation.** Every item says
which dependency capability it spends and how we know it worked.
Parked items name the reason — nothing is dropped silently.

---

## Phase A — Bugs and hardening (do now; these are wrong today)

| # | Item | Capability spent | Done when |
| :-- | :--- | :--- | :--- |
| A1 | **Proxy everywhere**: `state.proxy` reaches media downloads, YouTube innertube, engine fetch, license checks, update checks (loopback router clients deliberately exempt) | httpx `proxy=`, primp `proxy=` | setting a proxy makes EVERY network path follow it; no proxy → byte-identical behavior |
| A2 | **primp hardening**: catch `StatusError.status_code` where we classify HTTP failures; granular `(connect, read)` timeouts; rotate fingerprint on 403 (retry once with a fresh impersonation) | primp StatusError, `impersonate`, timeouts | a 403 mid-download retries instead of dying; tests pin the error mapping |
| A3 | **Resume large downloads** (Range/206) where the origin supports it | primp streaming | kill + retry a 200 MB video continues instead of restarting (feature-flagged if flaky) |
| A4 | **Link-scheme guards**: `is_web_url`/`is_launchable_url` gate all five Markdown/launcher sites; guard runs AFTER urljoin (which preserves foreign schemes). markdown-it itself parked - ft.Markdown renders Dart-side and the Python package is an unused transitive | core.utils + url handling | `javascript:`/`file:`/`data:` never reaches a fetch or the OS |
| A5 | **Charset audit closes as verified-clean**: no hand-decode path exists in src/ - decoding lives in primp (Rust, header-first with sniff fallback) and ddgs. charset_normalizer gains a consumer only if a bytes path appears; parked until then | charset_normalizer (parked) | documented finding, no bug to fix |
| A6 | **IDN display**: `display_host()`/`display_url()` decode punycode in result rows, media rows, detail sheet and the chat domain chip; clicks/copies keep raw hrefs | idna (now declared directly) | `xn--mnchen-3ya` shows as `münchen.de` everywhere it is READ |
| A7 | **CI Android job**: Gradle `-Xmx` ≤ runner RAM, cache Flutter/JDK/gradle via `FLET_CACHE_DIR`, trim `--arch` to shipped ABIs | flet_cli | APK job no longer risks OOM; second run is materially faster |
| A8 | **ruff gate grows**: add `B`, `ASYNC`, `UP`, `S`, `TRY`, `PERF` with narrow ignores; fix what it finds | ruff | CI runs the expanded select; findings fixed or explicitly ignored |

## Phase B — Assistant intelligence (kani / openai / tiktoken / pydantic)

| # | Item | Capability spent | Done when |
| :-- | :--- | :--- | :--- |
| B1 | **Real token receipts** SHIPPED: the stream's `openai_usage` trailer rides `text_final` as `tokens{in,out}`; the meta line shows `N tok` beside steps/credits/model, local ~4-chars/token count as fallback | kani extra, openai usage, tiktoken | every paid reply shows a token count |
| B2 | **Paragraph-aware tool caps** SHIPPED: `auto_truncate=TOOL_OUTPUT_CAP` on every AIFunction; the blind `[:2000]` slice is gone | kani auto_truncate | tool outputs end at a paragraph boundary |
| B3 | **Graceful finale** SHIPPED: `max_function_rounds=max_iters-1` - after five tool rounds kani strips the tools and the model answers from what it has | kani max_function_rounds | no empty bubble; over-cap turns charge honestly (pin test) |
| B4 | **Strict tool args**: pydantic models = single source of truth → `model_json_schema()` feeds ToolSpec; probe router for `response_format=json_schema` + `strict` before enabling | pydantic, openai types | tools validate typed args; schema drift impossible |
| B5 | **Approval previews** CLOSES AS COVERED: every tool already emits `step_start` with a human label before the approval gate; kani's formatter would duplicate that row | kani prompts | no change needed |
| B6 | **`.kani` export/import**: `save()`/`load()` archive (transcript + attachments) as share/export | kani utils.saveload | one tap exports a conversation; import restores it with tool history |
| B7 | **Prompt cache + tool steering** (probe router first): `prompt_cache_key` per conversation, `tool_choice` variants where supported | openai create params | measured fewer tokens / fewer wasted tool rounds, or honestly parked |
| B8 | **Vision answers**: attach the top image-search result as an `ImagePart` when the answer uses an image | kani parts/mm_tokens | "show me" queries see the picture (only on models the router marks vision-capable) |
| B9 | **Thinking depth setting**: `reasoning_effort` exposed as auto/fast/deep in Settings (omit `auto` — owner rule) | openai reasoning params | user can trade speed vs depth; default unchanged |

## Phase C — Flet UX shelf (the "best possible app" feel)

| # | Item | Capability spent |
| :-- | :--- | :--- |
| C1 | **Undo SnackBars** (action/Undo) for history delete, conversation delete, schedule cancel — replace "cannot be undone" | material SnackBar |
| C2 | **Badge** on nav: active downloads count + low-credit state | material Badge |
| C3 | **Context menus** on results/history/chat rows (right-click desktop, long-press mobile): copy, share, save, open external | ContextMenu/PopupMenu |
| C4 | **SegmentedButton** result-type switcher (web/images/videos/news/books) | material SegmentedButton |
| C5 | **Dismissible** swipe-to-delete on history + conversation rows (with confirm veto) | core Dismissible |
| C6 | **DatePicker/TimePicker** for crawl schedules + "next run at 14:03" display | material pickers |
| C7 | **Skeleton loading** for result grids and chat | Shimmer/progress |
| C8 | **Mobile polish**: Share.share_files for saved downloads, HapticFeedback on download-complete, CupertinoActionSheet long-press, large-title navbar | services + cupertino |
| C9 | **Desktop**: KeyboardListener shortcuts (Ctrl+K, Esc, arrows), taskbar progress + `prevent_close` confirm on active downloads, WindowDragArea titlebar | core/services window |
| C10 | **InteractiveViewer** pinch-zoom on image results; **Semantics** labels + reduce-motion respect | core controls |
| C11 | **Splash** branding (Android pipeline exists, unused) + About shows flet runtime version | flet runtime/cli |

## Phase D — Search & media depth (ddgs / lxml / pillow / qrcode / pygments / rich / slugify / regex)

| # | Item | Capability spent |
| :-- | :--- | :--- |
| D1 | **Source chips**: multi-backend fan-out (`backend="brave,mojeek"` etc.) exposed as user-selectable sources | ddgs backends |
| D2 | **Load more**: real `page` pagination (wired, never used past page 1) | ddgs page |
| D3 | **Leaner + repeatable**: `fields`/`fieldsets` on hot paths, `cache=` for instant repeat searches | ddgs fieldsets/cache |
| D4 | **Correct links**: `make_links_absolute` + `iterlinks` in crawl/extract; configured `HTMLParser` (recover, no_network) | lxml |
| D5 | **Image pipeline**: thumbnails before grid display (RAM/speed), WebP export option, **EXIF strip on save** (privacy), animated-badge | pillow |
| D6 | **QR shelf**: "Open on phone" dialog (result URL), LAN handoff QR for saved files | qrcode + PIL |
| D7 | **Syntax highlighting** in Reader code fences (602 lexers) + colored diagnostics terminal + `export_html` shareable logs | pygments + rich |
| D8 | **Filenames**: replace hand-rolled `_slug()`/`sanitize_filename()` with `slugify(..., word_boundary, max_length)` | slugify |
| D9 | **Regex safety**: `timeout=` circuit-breaker on YouTube patterns; fuzzy + Unicode-property history search | regex |

## Phase E — Time, files, throughput (arrow / dateutil / watchdog / anyio / jiter)

| # | Item | Capability spent |
| :-- | :--- | :--- |
| E1 | **Humanized time**: `arrow.humanize()` for history/conversation/log timestamps; 85 locales | arrow |
| E2 | **Real schedules**: `rrule` UI ("weekdays 9am") + DST-correct `next_run` (interval mode stays) | dateutil + tzdata |
| E3 | **Live surfaces**: watchdog log tail in the diagnostics terminal, downloads folder auto-refresh, run.py cache hot-reload | watchdog |
| E4 | **UI never freezes**: `anyio.to_thread` around sync primp/lxml hot paths; `fail_after` on flaky fetches; task-group fan-out for `scrape_site` | anyio |
| E5 | **Fast parse paths**: `jiter.from_json` + `allow_inf_nan=False` on tool-arg and scrape-JSON hot paths | jiter |
| E6 | **Binary persistence** (profile-gated): msgpack for caches/journals if JSON shows up in profiles | msgpack |

## Phase F — Foundation (pydantic / packaging / typing / pytest)

| # | Item | Capability spent |
| :-- | :--- | :--- |
| F1 | **Typed settings + conversation events**: pydantic models with validators (corrupt state caught at load), SecretStr for secrets, TypedDict closed emit protocol | pydantic |
| F2 | **Version gates**: `packaging.Version/SpecifierSet` for feature gates; `Marker` for android-vs-desktop branches | packaging |
| F3 | **Typing hygiene**: `@override` on DDGSKani, `@deprecated` for evolving emit events, NotRequired/Required fields | typing_extensions |
| F4 | **Test hardening**: `raises(match=)`, parametrize the pin tests, `caplog`, `pytest.warns`, `subtests`, anyio plugin for async tests | pytest stack |

## Parked — owner call, honest reasons

| Item | Why parked |
| :--- | :--- |
| TTS read-aloud, embeddings/semantic history, image generation, files+vector stores | New product surfaces, not utilization gaps — needs your call (openai-beyond-chat.md) |
| `api_type="responses"` | Router answers 400 on `/v1/responses` today (verified 2026-09-23); revisit when router ships it |
| MCP (kani or ddgs) | Owner rule: never in scope |
| oauthlib / flet.auth sign-in | "No account, ever" policy |
| jinja2 HTML-export templates, YAML settings export | Dev-only ballast; only worth importing if you want those export features |
| `ddgs` power-CLI wrapper | The ddgs lib already ships one (`ddgs text -q …`) — document, don't rebuild |
| tqdm progress bars | The GUI owns progress; CLI-only if a batch mode ever exists |

---

**Working rule while grinding:** every PR claims dependency surface from
this plan (name the audit + item), keeps ruff + the full suite green, and
updates the checklist. Dependencies we still don't use after a phase get
either a built feature or a line in *Parked* — nothing silent.
