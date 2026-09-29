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
| B4 | **Strict tool args - PENDING ROUTER PROBE**: pydantic-sourced schemas are buildable anytime; `response_format=json_schema`/`strict` needs one live probe against the router before UI work | pydantic, openai types | probe first, then ship |
| B5 | **Approval previews** CLOSES AS COVERED: every tool already emits `step_start` with a human label before the approval gate; kani's formatter would duplicate that row | kani prompts | no change needed |
| B6 | **`.kani` export/import** SHIPPED: per-row Export in the chat list writes kani's own zip archive (save dialog, no engine, no network); Import reads `.kani`/`.json` back as a new conversation. Round-trip pinned | kani utils.saveload | one tap exports; import restores with the transcript intact |
| B7 | **Prompt cache + tool steering - PENDING ROUTER PROBE**: `prompt_cache_key`/`tool_choice` variants must be accepted by the router first (unknown params can 400 a free turn) | openai create params | probe first |
| B8 | **Vision answers - PENDING ROUTER CAPABILITY**: needs a router model marked vision-capable before ImageParts are sent | kani parts | router capability first |
| B9 | **Thinking depth setting - PENDING ROUTER PROBE**: `reasoning_effort` may 400 on free models; probe, then a Settings toggle (omit `auto` - owner rule) | openai reasoning params | probe first |

## Phase C — Flet UX shelf (the "best possible app" feel)

| # | Item | Capability spent |
| :-- | :--- | :--- |
| C1 | **Undo SnackBars** (action/Undo) for history delete, conversation delete, schedule cancel — replace "cannot be undone" | material SnackBar |
| C2 | **Badge** CLOSES AS BLOCKED BY DESIGN: `test_no_badge_used_anywhere_in_assistant_ui` records that ft.Badge rendered as a red block over the FAB on this build - the app deliberately carries counts in its own colored chips (the credits chip already does this). Revisit only with an explicitly styled Badge | material Badge | standing pin respected |
| C3 | **Context menus** SHIPPED: long-press (mobile) / right-click (desktop) on every result row - web, image, video, news, books - opens a bottom sheet with open/copy/share and the decoded host as header; primary taps still open the detail sheet | GestureDetector + BottomSheet | one gesture to the three verbs |
| C4 | **SegmentedButton** SHIPPED: the extract card's format Dropdown is now a five-segment switcher (MD/Text/Rich/HTML/Raw, full names on tooltips) - every format visible instead of hidden behind a tap. The Home category chips already do the result-type job and stay | material SegmentedButton | one fewer tap, zero hidden options |
| C5 | **Dismissible** swipe-to-delete on history + conversation rows (with confirm veto) | core Dismissible |
| C6 | **Crawl interval editor** SHIPPED: per-row edit opens a SegmentedButton (15m/30m/1h/6h/12h/24h, the tool schema's legal range) and re-schedules through the Assistant's own `_schedule` path. Date/TimePicker waits for the rrule model (E2), when 'weekdays at 9am' becomes expressible | material SegmentedButton | schedules are no longer set-once |
| C7 | **Skeleton loading** SHIPPED: three shimmering result-row placeholders (avatar bar, title, snippet lines) render under the progress line while searching - the list's shape appears before its data | core Shimmer | the wait reads as progress, not freeze |
| C8 | **Mobile save polish** SHIPPED (haptics + Share): a finished download/save buzzes via HapticFeedback, and the success dialog gains a Share button that hands the real file to the native share sheet (share_files). Large-title navbar + CupertinoActionSheet remain open | HapticFeedback, Share.share_files | save completes with a buzz and a share button |
| C9 | **Desktop** SHIPPED (shortcuts): Esc pops the top dialog, Ctrl+K focuses the Home search (SearchBar registered per render), and the Reader's keyboard handler now chains/restores instead of replacing, so global keys survive it. Window taskbar progress + prevent-close remain open | page.on_keyboard_event | shortcuts work; handler composition is safe |
| C10 | **Zoom SHIPPED, Semantics open**: the detail sheet's image preview pinch-zooms to 5x (wheel on desktop) and pans; Semantics labels + reduce-motion respect on icon buttons remain | InteractiveViewer | photos are inspectable in place |
| C11 | **Splash** branding (Android pipeline exists, unused) + About shows flet runtime version | flet runtime/cli |

## Phase D — Search & media depth (ddgs / lxml / pillow / qrcode / pygments / rich / slugify / regex)

| # | Item | Capability spent |
| :-- | :--- | :--- |
| D1 | **Multi-backend** SHIPPED at the wire: a comma-delimited backend fans one search across several sources, each still validated per category. Multi-select UI parked (state.backend becomes a list = storage-format change, owner-scale) | ddgs backends | fan-out works; UI next |
| D2 | **Deep pagination SHIPPED**: Load more bumps state.page, searches ui=False, dedupes by URL, re-renders through a replaced SearchProgress; fresh queries reset to page 1. Pin test on the merge | ddgs page | results no longer stop at 20 |
| D3 | **CLOSES AS IMPOSSIBLE in ddgs 9.16**: the full audit found no fields/fieldsets trimming and no result cache param (the page-cache service already covers repeat searches). Negative finding recorded, nothing to build | ddgs | verified absence |
| D4 | **CLOSES AS COVERED**: HTML->Markdown conversion happens inside ddgs.extract, which already resolves links - our code never touches raw HTML (the Reader and save_page consume converted text). lxml stays a transitive dep | lxml | verified covered |
| D5 | **OWNER CALL**: EXIF-strip on save needs a JPEG re-encode (quality trade-off) - thumbnail-before-grid and WebP export have no consumer yet. Parked pending the image-pipeline decision | pillow | needs your call |
| D6 | **QR shelf** SHIPPED (open-on-phone): every detail sheet carries a QR button - the link renders as a QR dialog (qrcode -> PIL -> base64, no disk touch). LAN file handoff stays open | qrcode + PIL | scan to continue on mobile |
| D7 | **SHIPPED (flet's own themes)**: rendered Markdown carries a real pygments theme through ft.Markdown's code_theme (DRACULA dark, default light) in the Reader and the extract card. A Python-side pygments renderer is not needed - the Dart parser owns rendering | flet code_theme + MarkdownCodeTheme | code fences are themed |
| D8 | **Filenames** SHIPPED: sanitize_filename is python-slugify now (unidecode transliteration, 64-char cap, word boundaries) - international titles land readable on every filesystem | slugify + text_unidecode | CJK/Arabic titles survive |
| D9 | **SHIPPED**: cipher_solver runs on the regex module with a 5s timeout on all nine pattern executions - fetched YouTube JS is attacker-influenced and backtracking is a hang the read timeout cannot stop. Fuzzy history search parked (search-input design) | regex timeout= | no pathological hangs |

## Phase E — Time, files, throughput (arrow / dateutil / watchdog / anyio / jiter)

| # | Item | Capability spent |
| :-- | :--- | :--- |
| E1 | **CLOSES AS REVIEWED, NOT ADOPTED**: arrow.humanize is more verbose than the hand-rolled compact '12m' form that 12px rows need; locale-native timestamps are an owner-visible setting decision, not a silent swap. arrow stays transitive | arrow | compact form kept deliberately |
| E2 | **OWNER CALL**: rrule schedules change the storage model (interval_minutes -> recurrence) and the C6 editor's contract. C6's interval picker stays until you decide the data model | dateutil rrule | needs your call |
| E3 | **OWNER CALL**: watchdog's log tail and downloads auto-refresh are new standing surfaces; Android has no inotify (polling cost). Candidate for the next batch, not a silent add | watchdog | needs your call |
| E4 | **CLOSES AS VERIFIED**: primp/lxml already run via to_thread (search, writes, parse) and the downloads loop uses it; memory streams and task groups redesign the turn/crawl loops for no gain at today's scale. anyio stays transitive | anyio | verified already-correct |
| E5 | **OWNER CALL**: jiter's parse fast-path is a measured micro-win (json.loads sites exist) but 24.75 vs 75us is invisible next to network time. Parked with the perf backlog | jiter | needs your call |
| E6 | **OWNER CALL**: msgpack persistence is profile-gated - nothing shows JSON as a bottleneck yet. Parked | msgpack | needs a profile |

## Phase F — Foundation (pydantic / packaging / typing / pytest)

| # | Item | Capability spent |
| :-- | :--- | :--- |
| F1 | **OWNER CALL**: pydantic typed settings/history is a cross-cutting refactor of the storage layer; the plan is Phase B4's tool schemas first. Parked at owner scale | pydantic | plan before build |
| F2 | **OWNER CALL**: packaging version-gates + markers. Useful once a dependency's API actually gates a feature; parked | packaging | when it gates something real |
| F3 | **SHIPPED**: DDGSKani.do_function_call carries @override - the one override we own is now marked | typing_extensions override | contract visible |
| F4 | **OWNER CALL**: raises(match=)/caplog/pytest.warns hardening is valuable and incremental; ~10 minutes of test polish, no user-visible gain. Parked for a test-only session | pytest stack | queued for polish |

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
