# Dependency Audit — python-dateutil 2.9.0.post0

> Owner goal: 100% capability utilization. This report inventories the FULL
> dateutil API surface and ranks what DDGS leaves on the table.

**Dependency chain (confirmed in `uv.lock`):** DDGS → `flet-cli` → `arrow 1.4.0`
→ `python-dateutil 2.9.0.post0` (+ `six`). **Transitive, doubly so:** a grep
of `src/` finds zero `import dateutil` and zero `import arrow` hits — the app
ships dateutil without executing a single line of it today.

**How DDGS touches time today (all stdlib):**

| Feature | Current implementation |
|---|---|
| Scheduled recurring crawls | `interval_minutes` only (15–1440, via `schedule_scrape` tool in `src/services/chat_agent.py`); `_scrape_scheduler` in `src/app_controller.py` ticks every 60 s, `next_run = now + interval*60` epoch-float math |
| History timestamps | epoch floats; `relative_time()` in `src/services/conversation_service.py` (`time.time()` deltas → "12m ago" / "Sep 20") |
| Update feed checks | `src/services/update_service.py` — no time logic, fire-on-launch check only |
| Log rotation pruning | `prune_old_logs()` in `src/core/utils.py` — `time.time() - days*86400` cutoff |
| Search result dates | `published` / `date` passed through as **raw strings** in `src/services/search_service.py` (never parsed, never normalized) |

---

## 1. COMPLETE API INVENTORY

### `dateutil.parser` (`parser/_parser.py` 1613 lines, `parser/isoparser.py` 416 lines)
- `parse(timestr, parserinfo=None, *, default=None, ignoretz=False, tzinfos=None, dayfirst=None, yearfirst=None, fuzzy=False, fuzzy_with_tokens=False)` → `datetime` — forgiving parser for ~any human/machine format; missing fields fall back to `default` (defaults to today); raises `ParserError` / `OverflowError`.
- `parser(info=None).parse(...)` — reusable parser instance (same kwargs) for hot loops.
- `parserinfo(dayfirst=False, yearfirst=False)` — subclassable: custom month/day names, JUMP tokens, UTCZONE list, `convertyear()` (2-digit-year pivot); the localization hook.
- `fuzzy=True` — ignores surrounding garbage: `parse("Today is January 1, 2047 at 8:21:00AM", fuzzy=True)`.
- `fuzzy_with_tokens=True` — implies fuzzy, returns `(datetime, ignored_tokens_tuple)`.
- `isoparse(dt_str)` / `isoparser(sep=None)` — strict, fast ISO-8601-only parser (YYYY, YYYY-MM, week dates, ordinals, `T` separator, `Z`/offsets); raises on non-ASCII.
- `ParserError`, `UnknownTimezoneWarning` — error taxonomy for bad input / unresolvable tz names.
- `default` param — unset components inherit from a supplied datetime (e.g. "9am" → today at 9:00).

### `dateutil.rrule` (`rrule.py` 1737 lines — RFC 5545 iCalendar recurrence)
- `rrule(freq, dtstart=None, interval=1, wkst=None, count=None, until=None, bysetpos=None, bymonth=None, bymonthday=None, byyearday=None, byeaster=None, byweekno=None, byweekday=None, byhour=None, byminute=None, bysecond=None, cache=False)` — `freq` ∈ YEARLY/MONTHLY/WEEKLY/DAILY/HOURLY/MINUTELY/SECONDLY; `byweekday` takes `MO..SU` with `n` ("3rd Friday" = `FR(3)`); invalid dates (Feb 30, DST gaps) are **skipped, not coerced** per RFC 3.3.10.
- Navigation: `.after(dt, inc=False)` / `.before(dt, inc=False)` / `.between(after, before, inc=False)` / `.xafter(dt, count, inc)` generator / `.count()` / `dt in rule` / slicing/indexing.
- `rruleset(cache=False)` — compose: `.rrule()` + `.rdate()` inclusions, `.exrule()` + `.exdate()` exclusions (holidays/skip-days).
- `rrulestr(str, dtstart=None, cache=False, forceset=False)` — parse `"FREQ=WEEKLY;BYDAY=MO,WE,FR"` strings; round-trips via `str(rule)`.
- `MO..SU` weekday constants shared with `relativedelta`.

### `dateutil.relativedelta` (`relativedelta.py` 599 lines)
- `relativedelta(years/months/weeks/days/hours/…)` (plural = relative arithmetic; `timedelta` **cannot do months/years**) + singular absolute form (`year=/month=/day=/hour=…` **replaces** the component) + `weekday=MO(+1)` ("next Monday"; combine with `day=` for "first Monday of month") + `leapdays` / `yearday` / `nlyearday`.
- `relativedelta(dt1, dt2)` — diff mode: human decomposition ("2 years, 3 months") for "last crawled X ago" labels.
- Extras: arithmetic/comparison operators, `*`/`/` scaling, `.normalized()` (carry overflow down to integer fields).
- Mnemonic: *plural adds, singular sets.*

### `dateutil.tz` (`tz/tz.py` 1849 lines, `tz/win.py` 370 lines, `tz/_common.py`, `tz/_factories.py`)
- `gettz(name=None)` — smart dispatcher: IANA name → system zoneinfo `tzfile`; Windows name ("Eastern Standard Time") → `tzwin`; POSIX TZ string ("EST5EDT,…") → `tzstr`; `None`/`""` → `tzlocal()`; integer → `tzoffset`; results cached (same object on repeat calls).
- `tzfile(fileobj, filename=None)` — binary Olsen-database reader (full transition tables, correct pre-1970/DST-fold behavior).
- `tzlocal()` — OS-local zone with DST-aware `utcoffset/dst/tzname`, `is_ambiguous()`, `fold` handling.
- `tzutc()` / singleton `UTC` — UTC with `is_ambiguous() is False`.
- `tzoffset(name, offset_seconds)` / `tzstr(s, posix_offset=False)` / `tzrange(stdabbr, stdoffset, dstabbr, dstoffset, start, end)` — static/ad-hoc zones without any database.
- `tzical(fileobj)` — `tzinfo` + transitions parsed from an **iCalendar VTIMEZONE** component (`.keys()` per TZID) — ingest venue/partner calendar feeds directly.
- `tzwin(name)` / `tzwinlocal()` — Windows-registry zones incl. historical bias tables (only meaningful on Windows — DDGS's desktop target).
- `datetime_ambiguous(dt, tz)` / `datetime_exists(dt, tz)` / `resolve_imaginary(dt)` / `enfold(dt, fold=1)` — DST-fold toolkit: detect the repeated 1–2am hour, detect spring-forward gaps, push imaginary times forward to real ones.
- `tzical` + `tzrange` + `tzstr` serialize to RFC strings for persisting schedules in JSON.

### `dateutil.easter` (`easter.py` 89 lines)
- `easter(year, method=EASTER_WESTERN)` with `EASTER_JULIAN=1` / `EASTER_ORTHODOX=2` / `EASTER_WESTERN=3` → `datetime.date`; valid 1583–4099 (Gregorian). Doubles as `rrule(byeaster=…)` input ("crawl the week before Easter").

### `dateutil.utils` (`utils.py` 71 lines)
- `today(tzinfo=None)` — today at midnight, optionally tz-aware (DST-safe day boundaries).
- `default_tzinfo(dt, tzinfo)` — stamp tz **only if naive** (pass-through if already aware); the one-liner for mixed scraped timestamps.
- `within_delta(dt1, dt2, delta)` — fuzzy datetime equality for dedupe ("same crawl within 5 min").

### `dateutil.zoneinfo` (`zoneinfo/__init__.py` 167 lines + `dateutil-zoneinfo.tar.gz` bundle) — skimmed
- `ZoneInfoFile(stream)` / `get_zonefile_instance()` — dateutil's **frozen, bundled** IANA snapshot (works offline / no system tzdata); `gettz()` here is deprecated — prefer `tz.gettz()` (system zoneinfo first). See gotcha §3.

### `_common.weekday` / `tzwin.py` shim
- `_common.weekday(wkday, n)` base class behind both `relativedelta.MO` and `rrule.MO`; `tzwin.py` is a 2-line re-export of `tz.win`.

---

## 2. LATENT CAPABILITIES FOR DDGS (ranked by value × fit)

1. **`rrule` → REAL scheduling UI ("every weekday at 9am").** Today `schedule_scrape` accepts only `interval_minutes` (15–1440), so "weekday mornings" is inexpressible and `next_run = now + interval*60` drifts across DST. `rrule(WEEKLY, byweekday=(MO..FR), byhour=9, byminute=0, dtstart=…)` + `.after(now)` gives exact next-run times; `str(rule)` persists to the existing JSON schedule store; `rrulestr()` reloads it; `rruleset.exdate()` models user "skip" days. Fixes the #1 scheduling gap with zero schema redesign.
2. **Fuzzy `parse()` for scraped result dates.** `search_service.py` passes `published`/`date` through as raw strings — news timestamps ("3 hours ago"-style, RFC 2822, locale formats) are never normalized, so sorting/filtering by recency is impossible. `parse(s, fuzzy=True, default=…)` + `tzinfos=` handles the wild; `isoparse()` fast-paths the well-formed. Directly upgrades search-result quality.
3. **`tz`-aware scheduling across DST.** Interval crawls scheduled the night before a spring-forward/fall-back fire an hour off (or twice). Anchoring `dtstart` with `tz.gettz("America/New_York")` + `datetime_exists()` / `datetime_ambiguous()` guards makes "9am local, always" actually true — matters for a desktop app whose users span zones.
4. **`relativedelta` for "next run" + human labels.** `now + relativedelta(months=+1)` (impossible with `timedelta`); `relativedelta(dt1, dt2)` diff mode powers "last crawled 2d 3h ago" and monthly/quarterly crawl plans; `weekday=FR(-1)` = "last Friday" billing-style anchors for premium quota windows.
5. **`parse()` for history/import date fields.** History rows carry epoch floats that break on import (ISO strings from backups/other tools). `parse()` accepts both, `default_tzinfo()` stamps a zone only when missing — one ingestion path instead of format-sniffing.
6. **`utils.within_delta` + `today()` for dedupe and day buckets.** "Same URL crawled within N min → skip" and DST-safe "today's crawls" grouping in the history screen (current `relative_time()` day-boundary math is naive-local).
7. **`tzical` for partner calendar feeds.** If DDGS ever ingests venue/event calendars, `tzical` resolves their embedded VTIMEZONE blocks without a separate ical parser.
8. **`easter` — locale date features.** Only if DDGS adds holiday-aware scheduling ("skip public holidays", "Easter-week sale crawl"); otherwise correctly unused. Lowest priority, listed for completeness per the 100%-utilization brief.

**Suggested adoption order:** 1 → 2 → 3 (one scheduling PR + one timestamp-normalization PR covers the top 5).

---

## 3. GOTCHAS

- **DST edge cases are the #1 footgun.** `rrule` *skips* nonexistent local times (spring-forward 2:30am silently vanishes from the series — good, but surprising); the repeated fall-back hour makes `.after()` ambiguous unless you disambiguate with `datetime_ambiguous()` + `enfold()`. Always construct scheduling `dtstart`s tz-aware and validate with `datetime_exists()`.
- **`zoneinfo` vs `dateutil.zoneinfo` duplication.** `dateutil.zoneinfo.gettz()` reads a *frozen bundled tarball* (stale vs system tzdata) and is **deprecated**; stdlib `zoneinfo` (3.9+) or `tz.gettz()` (system-first) should win. On Windows desktop (DDGS target) there is no system IANA db — `tz.gettz()` falls back to the bundle/`tzwin`, which is the correct path; just never call `dateutil.zoneinfo.gettz()` directly.
- **`parse()` is permissive by design — garbage in, plausible date out.** `parse("12")` returns day-12 of the current month; `fuzzy=True` will find a date in almost anything. For scraped fields: wrap in try/except `ParserError`, sanity-check the year range (scraped "20" → 2020?), and prefer `isoparse()` when the source claims ISO. Never `parse()` untrusted strings into scheduling decisions without validation.
- **`dayfirst`/`yearfirst` ambiguity.** `parse("01/05/09")` defaults to US month-first; DDGS's international users need explicit `dayfirst` handling or locale-aware `parserinfo` subclasses — otherwise EU news dates flip month/day silently.
- **`count` + `until` together is deprecated** (warns today, will raise). Pick one per rule.
- **`relativedelta(day=31)` clamps, doesn't roll.** Adding `months=+1` to Jan 31 → Feb 28/29 (last-day clamp). Desirable for "monthly crawl", but document it — it is not an error.
- **Import cost is negligible but nonzero.** `dateutil` pulls `six`; `tz.gettz()` lazily reads zone files and caches. Fine for desktop, but keep `rrulestr`/`tzical` parsing off the 60 s scheduler hot path — precompute `next_run`, don't re-expand rules per tick.
- **`tzlocal()` on Windows** reads the registry + DST rules; behavior differs from Linux CI — test scheduling tests with explicit `gettz("…")` zones, not local time.

---

## 4. COVERAGE

**18 / 18 `.py` files read (100%).** Fully read (all lines): `__init__.py`,
`_common.py`, `_version.py`, `relativedelta.py` (599), `rrule.py` (1737),
`easter.py` (89), `utils.py` (71), `tzwin.py` (shim), `parser/__init__.py`,
`parser/_parser.py` (1613), `parser/isoparser.py` (416), `tz/__init__.py`,
`tz/tz.py` (1849), `tz/win.py` (370), `tz/_common.py` (419), `tz/_factories.py`
(80). Skimmed per brief: `zoneinfo/__init__.py` (167) + `zoneinfo/rebuild.py`
(build-time only, not shipped logic) + bundled `dateutil-zoneinfo.tar.gz`
(data, not code). Total library surface ≈ 7,550 lines. Consumer grep:
`src/` (scheduler in `app_controller.py`, `chat_agent.py`; timestamps in
`conversation_service.py`, `search_service.py`, `storage_service.py`;
`core/utils.py` pruning; `services/update_service.py`), plus `uv.lock`
chain confirmation (`arrow 1.4.0 → python-dateutil 2.9.0.post0`).
