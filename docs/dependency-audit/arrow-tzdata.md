# arrow + tzdata — Dependency Audit (DDGS)

Date: 2026-09-29 · arrow 1.4.0 · tzdata 2026.4 (IANA 2026d)

**Dependency status (uv.lock): arrow is TRANSITIVE-ONLY, zero direct utilization.**
`ddgs-app → flet[cli,desktop] (dev group) → flet-cli → cookiecutter 2.7.1 → arrow → {python-dateutil, tzdata}`.
No file under `src/` imports arrow; it is not in `[project].dependencies`. It ships in the venv
but only because the dev-group CLI chain needs cookiecutter project scaffolding. tzdata rides along
as arrow's declared dependency. Removing neither is action-safe (dev-group owns the chain), but any
DDGS runtime use of arrow adds no new package — the bytes are already paid for.

## 1. COMPLETE API INVENTORY

### Module API (`arrow/__init__.py`, `api.py`, `factory.py`)
- `arrow.get(*args, **kwargs)` — universal constructor: no-arg→utcnow; Arrow→copy; int/float/ts-string→fromtimestamp (UTC default); ISO-8601 str (+basic `YYYYMMDDTHHmmss`)→parse_iso; tzinfo→now@tz; naive datetime/date→UTC; aware datetime→kept; struct_time→utcfromtimestamp; ISO-week tuple→gregorian; (datetime|date, TZ_EXPR)→re-zoned; (str, fmt|list[fmt])→parse with fallback list; (y,M,d,…)→direct constructor; kwargs `locale`, `tzinfo`, `normalize_whitespace`.
- `arrow.now(tz=None)` — now in given TZ_EXPR (str/`tzinfo`/`local`/`utc`/`±HH:MM`/IANA); default = system local.
- `arrow.utcnow()` — now in UTC as Arrow (hides stdlib deprecated `datetime.utcnow()`).
- `arrow.factory(ArrowSubclass)` — factory bound to a custom Arrow subclass.
- Format constants: `FORMAT_ATOM/COOKIE/RFC822/RFC850/RFC1036/RFC1123/RFC2822/RFC3339/RFC3339_STRICT/RSS/W3C`.
- `ParserError` (and `ParserMatchError`) exported for parse-failure handling.

### Core class (`arrow.py`, ~70 public members)
- Constructors: `now/utcnow/fromtimestamp/utcfromtimestamp/fromdatetime/fromdate/strptime('%d-%m-%Y…'-style codes)/fromordinal/iso_calendar-tuple via get`.
- `shift(**plurals, weekday=, quarters=, check_imaginary=True)` — relative arithmetic incl. weekday targeting (MO–SU ints or dateutil days) with DST imaginary-time resolution; `replace(**singulars, tzinfo=, fold=)` — absolute field set / tz re-stamp without conversion.
- `span(frame, count, bounds, exact, week_start)` → (floor, ceil) tuple; `floor/ceil(frame)` truncations; frames: year(s)/quarter(s)/month(s)/week(s)/day(s)/hour(s)/minute(s)/second(s)/microsecond(s).
- `range(frame, start, end, tz, limit)` — point iterator (end inclusive); `span_range(frame, start, end, tz, limit, bounds, exact)` — span-tuple iterator; `interval(frame, start, end, interval, tz, bounds, exact)` — N-frame grouped spans.
- `format(fmt, locale)` — Moment-style tokens: `YYYY YY MMMM MMM MM M DDDD DDD DD D Do dddd ddd d HH H hh h mm m ss s S…SSSSSS X(unix) x(µs) ZZ Z ZZZ(tzname) a A W(ISO week-date)`, `[…]` escapes; ≠ strftime (strptime() is the strftime-code bridge back).
- `humanize(other=None, locale, only_distance, granularity)` — "2 hours ago"/"in 4 hours"; granularity `auto|second|minute|hour|day|week|month|quarter|year` or list for multi-part ("2 hours and 15 minutes"); `only_distance=True` drops in/ago ("11 seconds"); auto-thresholds now→seconds→a minute→minutes→an hour→hours→a day→days→weeks→months→years.
- `dehumanize("2 days ago", locale)` — parses humanized strings back to Arrow; supported locales = DEHUMANIZE_LOCALES (~100 codes incl. en/fr/it/es/el/ja/zh/nl/pl/ru/de/pt/vi/tr/ar/hi/fa + region variants).
- `to(tz)` — convert (vs `replace(tzinfo=)` which re-stamps); TZ_EXPR = tzinfo | IANA str | `local`/`utc`/`Z` | `±HH[:MM]`.
- `is_between(start, end, bounds)` with `()/(]/[)/[]` bounds; full comparison ops + `__add__/__sub__` (timedelta/relativedelta/Arrow→timedelta) + `__hash__/__format__/__str__(isoformat)`.
- Properties: `.datetime` (aware stdlib), `.naive` (tz stripped), `.tzinfo/.fold/.ambiguous/.imaginary` (DST-transition introspection), `.timestamp()/.int_timestamp/.float_timestamp`, `.date()/.time()/.timetuple()/.utctimetuple()/.isocalendar()/.weekday()/.isoweekday()/.toordinal()`, `.ctime()/.isoformat()/.strftime()/.for_json()` (simplejson protocol → isoformat), `.astimezone()/.utcoffset()/.dst()/.timetz()`, `.clone()`.
- `util`: `next_weekday(date, 0-6)` (rrule-based), `is_timestamp`, `normalize_timestamp` (auto ms/µs→s), `iso_to_gregorian`, `validate_ordinal/bounds`.
- `parser.py`: `DateTimeParser(locale)` — `parse_iso` (multi-separator ISO + tz suffixes, optional whitespace normalization) and `parse(str, fmt|[fmts])` token-driven with compiled pattern cache; `TzinfoParser.parse` — `local/utc/UTC/Z`, `±HH[:MM]`, else `ZoneInfo(IANA)` else ParserError.
- `locales.py` (~85 `*Locale` classes, ~6.6k lines): en (+au/be/ca/jp/ph/za/gb/us), fr (+ca), it, es, de (+ch/at), pt (+br), zh-cn/tw/hk, ja, ko, ru/uk/be/pl/bg/mk (+latin)/cs/sk/sl/sr/hr, ar (+levant/dz-tn/mr/ma), fa, he, hi, mr, bn, ta, ml, or, ne, ur, th, lo, vi, id, ms, tl, tr, az, el, nl, sv (+se variants), fi, nb, nn, da, is, et, lv, lt, hu, ro, ca, eu, eo, la, rm, sq, ka, hy, kk, uz, am, sw, zu, af, mt, lb, si (+ta-lk), dehumanize-capable set above.
- UTC/local handling: naive inputs default UTC; `now()` defaults local; `to('local')/to('utc')` round-trips; `fold` preserved for ambiguous DST times.

### tzdata (data-only; `__init__.py` = version + IANA_VERSION only)
- Purpose: bundles the full IANA tz database (`zoneinfo/` region dirs + `zones` name index) as importable package data so `zoneinfo.ZoneInfo("America/…")` works where the OS ships no tz database.
- When Python needs it: Windows (never ships IANA data), Android (same gap — directly relevant: DDGS builds an APK via flet, `tool.flet.android`), minimal Docker/scratch images; CPython `zoneinfo` auto-imports `tzdata` if installed (no code change needed). Linux/macOS desktops ignore it (system `/usr/share/zoneinfo` wins).

## 2. LATENT CAPABILITIES FOR DDGS (ranked by value/effort)

1. **Replace hand-rolled `relative_time()`** (`src/services/conversation_service.py:343` — just-now/12m/3h/Sep-20 chain) with `arrow.get(ts).humanize()` — free locale support + correct month/year rollover the current code lacks (anything >7d collapses to "Sep 20" with no year).
2. **"Next run at 14:03" scheduling display** — `sections_ai.py:145` shows `Every 60 min · next in 4m 12s`; `chat_agent.py:505` shows `every 60 minutes`. One `arrow.get(next_run).to('local').format('HH:mm')` + `.humanize()` ("in 4 minutes") reads better than raw countdown math.
3. **Locale-native time strings** — 85 locales already vendored via the transitive dep; history/chat timestamps (`history_screen.py:95`, `home_screen.py:448`) and AI prompt date (`ai_service.py:434-443`, currently `datetime.now().astimezone()` + manual strftime) can render in the user's language with `format(..., locale=…)`.
4. **Format/parse helpers replacing hand-rolled code** — `time.strftime` scattered in `app_controller.py:763,853`, `core/utils.py:100` (log filenames), `agent_files.py:51`; `Arrow.strptime` + `get(str, [fmt-list])` fallback lists parse user-supplied dates robustly; `for_json()/isoformat()/float_timestamp` standardize the float-epoch timestamps currently passed as raw `time.time()` (`chat_agent.py:278`).
5. **Update-check age** — `update_service.py:62` + `app_controller.py:179`; `arrow.get(checked_at).humanize()` ("checked 3 days ago") beats storing/displaying raw epochs.
6. **Receipt/ledger dates** — `credit_service.py:254` (`datetime.now(tz=UTC).date().isoformat()`), wallet/premium screens; `span('day')/floor('day')` give day-bucketing for daily-credit resets without manual midnight math.
7. **Timezone-aware crawl windows** — `span('day')`, `is_between()`, `to(user_tz)` compose a "crawl only 01:00��05:00 local" gate; `tzdata` guarantees the IANA names resolve on the Android APK where system tzdata is absent.
8. **Log-line timestamps for the diagnostics terminal** — `Arrow.now().format('HH:mm:ss')` is cheaper to read than `time.strftime` + manual tz; `X/x` tokens emit epoch directly for machine lines.
9. **DST-safe recurring math** — current `next_run = time.time() + interval*60` drifts across DST boundaries; `Arrow.now().shift(minutes=n)` with `check_imaginary` + `ambiguous/imaginary` flags handles spring-forward gaps explicitly.
10. **Weekday scheduling** — `shift(weekday=0)` (next Monday) + `util.next_weekday` enable "crawl every Monday" without new code; `range('day', …)` can pre-render a run calendar.

## 3. GOTCHAS

- **Import cost is real but modest**: pure-Python + dateutil; `locales.py` alone is ~160KB/85 classes loaded at `import arrow` (no lazy loading) — fine for a desktop/server app, but on Android startup every millisecond counts, so import lazily inside the formatting helper, not at module top.
- **No stdlib `datetime` returned by default**: must unwrap via `.datetime` (aware) / `.naive`; passing Arrow objects into APIs expecting `datetime` (e.g. flet, sqlite adapters) fails silently or loudly — convert at boundaries.
- **Naive→UTC assumption bites**: `arrow.get(naive_datetime)` silently stamps UTC; DDGS's local-epoch floats (`time.time()`) are safe via `fromtimestamp`, but any naive `datetime` from existing code must go through `get(dt).to('local')` or gains/loses the UTC offset.
- **tz gaps on Android filled by tzdata — only if packaged**: `ZoneInfo` falls back to the `tzdata` PyPI package automatically, but the flet APK build must include it (it is in uv.lock via arrow, verify it lands in the bundle; otherwise IANA names raise `ZoneInfoNotFoundError` → arrow raises `ParserError`).
- **stdlib `datetime.utcnow()` is deprecated (3.12+)**: `ai_service.py`/`credit_service.py` already use aware `now()` correctly, but any future naive-UTC code should call `arrow.utcnow()` instead of touching the deprecated stdlib API.
- **Token dialect ≠ strftime**: `MM` = month in arrow vs minutes in strftime — mixing `format()` tokens with `strftime()` codes in adjacent lines (as DDGS currently does) is a bug farm; pick one per call site (`Arrow.strptime` exists for the strftime side).
- **Transitive-only risk**: DDGS never declared arrow; a future `flet-cli`/cookiecutter update could drop it and break runtime imports added on this advice — if DDGS adopts arrow, promote it to `[project].dependencies` with a floor (`arrow>=1.4.0`).

## 4. COVERAGE

- arrow (8 .py files): `__init__.py` 8/8 read · `api.py` 122/122 read · `factory.py` 339/339 read · `util.py` 117/117 read · `formatter.py` 141/141 read · `constants.py` via cat read · `arrow.py` (~1900 lines): full method-signature grep (~70 members) + full read of now/utcnow/range/span/span_range/interval/replace/shift/to/format/humanize/dehumanize/is_between/strptime/fromordinal/for_json regions (~700 lines) · `parser.py` (~960 lines): class/regex/method survey + full read of TzinfoParser and parse_iso head · `locales.py` (~6600 lines): all 85 class names + DEHUMANIZE_LOCALES set enumerated, per-locale bodies not line-read. Effective: 5/8 fully, 3/8 surveyed-at-signature-level.
- tzdata (data-only, 2 code files + data): `__init__.py` 7/7 read · `zoneinfo/` dir listing + `zones` index sampled (head) — file-count of IANA entries not enumerated (hundreds of zone files, content is data not API).
