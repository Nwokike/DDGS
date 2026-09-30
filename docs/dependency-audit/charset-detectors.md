# Charset detectors — dependency audit (charset-normalizer + chardet)

Versions pinned in `uv.lock`: `charset-normalizer 3.5.1`, `chardet 5.2.0`.
Neither package is imported anywhere in `src/` — both ride in transitively (see §3).
Consumer context: the app's Extract/Reader pipeline (`SearchService.extract_url` →
`ddgs.DDGS.extract(url, fmt=...)`) decodes inside primp's Rust layer
(`resp.text_markdown` / `text_plain` / `text_rich` / `text` / raw `content`);
`media_downloader.py` streams bytes to disk (`open(dest, "wb")`, Content-Type gate only);
`agent_files.py` writes UTF-8; `content_reader_screen.py` renders already-decoded `str`.

---

## 1. API inventory

### charset-normalizer 3.5.1

Entry points (`api.py`):
- `from_bytes(sequences, steps=5, chunk_size=512, threshold=0.2, cp_isolation=None, cp_exclusion=None, preemptive_behaviour=True, explain=False, language_threshold=0.1, enable_fallback=True)` → `CharsetMatches` — samples `steps`×`chunk_size` blocks, chaos-probes every IANA codec (multibyte first), coherence-scores survivors.
- `from_fp(fp, …same…)` — same via an open binary handle; does not close it.
- `from_path(path, …same…)` — opens in `rb`; can raise `IOError`.
- `is_binary(…same…, enable_fallback=False)` — `True` when nothing matches (strict: no ASCII/UTF-8 fallback).
- `detect(byte_str, should_rename_legacy=False, **kwargs)` (`legacy.py`) — chardet-compat shim returning `{encoding, language, confidence}`; ignores extra kwargs with a warning; `confidence = 1 − chaos` (−0.2 penalty on tiny non-UTF-8 samples); `utf_8`+BOM reported as `utf_8_sig`; names mapped through `CHARDET_CORRESPONDENCE` unless `should_rename_legacy`.
- There is no public `normalise()` function; normalization = `best_guess.output()` (CLI `--normalize` writes `best_guess.output()` = UTF-8 bytes to a sibling file).

`CharsetMatch` (`models.py`):
- `str(match)` — lazily decodes payload (strict); `.encoding`, `.encoding_aliases`, `.language` / `.languages`, `.chaos` / `.percent_chaos`, `.coherence` / `.percent_coherence`, `.bom` / `.byte_order_mark`, `.alphabets` (Unicode block names), `.could_be_from_charset` (all codecs yielding identical `str`), `.raw` (untouched bytes), `.submatch` / `.has_submatch`, `.fingerprint` (hash of decoded str), `.multi_byte_usage`.
- `.output(encoding="utf_8")` — re-encodes to target bytes and rewrites a declared `charset=`/`encoding=` header in the first 8 KiB.
- Ordering: lowest chaos wins; ties (<0.5% chaos gap) break on coherence.

`CharsetMatches`: `.best()` / `.first()` / `[int|str]` (alias-aware lookup) / iterate / `len` / truthiness; `append()` dedups identical fingerprints into submatches.

Detection internals worth knowing:
- `utils.any_specified_encoding()` — preemptive hint: scans first 8 KiB for `encoding=`/`charset=`/`coding=` declarations.
- `utils.identify_sig_or_bom()` + `constant.ENCODING_MARKS` — BOM/SIG fast-path (UTF-8, UTF-7 sigs ×4, GB18030 mark, UTF-16/32 BOMs); UTF-16/32/7 are never tried without a mark.
- `constant.TOO_SMALL_SEQUENCE = 32`, `TOO_BIG_SEQUENCE = 10_000_000` — payloads ≥10 MB decode lazily (first 500 KB probed).
- `md.py` `mess_ratio()` + ~10 `MessDetectorPlugin`s (unprintables, suspicious ranges, accent abuse, CJK rarity…) = chaos score; `cd.py` `coherence_ratio()` / `encoding_languages()` / `mb_encoding_languages()` / `merge_coherence_ratios()` = language score over ~50 `FREQUENCIES` tables; `explain=True` streams TRACE logs.
- CLI (`python -m charset_normalizer`): files…, `-v/--verbose -a/--with-alternative -n/--normalize -m/--minimal -r/--replace -f/--force -i/--no-preemptive -t/--threshold`; JSON via `CliDetectionResult`.

### chardet 5.2.0

- `detect(byte_str, should_rename_legacy=False)` → `{encoding, confidence, language}` — one-shot: `feed()` whole buffer then `close()`.
- `detect_all(byte_str, ignore_threshold=False, should_rename_legacy=False)` — ranked list of every prober above threshold (unique to chardet; no charset-normalizer equivalent).
- `UniversalDetector(lang_filter=ALL, should_rename_legacy=False)` — streaming workflow: `feed(chunk)` → check `.done` → `close()` → `.result`; BOM short-circuits to confidence 1.0; `PURE_ASCII → ESC_ASCII / HIGH_BYTE` state machine; `MINIMUM_THRESHOLD = 0.20`; ISO-8859→Windows remap when bytes in `0x80–0x9F` seen; opt-in `LEGACY_MAP` renames (e.g. `gb2312→GB18030`, `euc-kr→CP949`).
- Prober roster: `UTF8Prober` (utf-8); `UTF1632Prober` (UTF-16/32 LE/BE); `MBCSGroupProber` (SHIFT_JIS, EUC-JP, GB2312, EUC-KR, CP949, Big5, EUC-TW, Johab); `SBCSGroupProber` (windows-1251/KOI8-R/ISO-8859-5/MacCyrillic/IBM866/IBM855 Russian, ISO-8859-7/windows-1253 Greek, ISO-8859-5/windows-1251 Bulgarian, TIS-620 Thai, ISO-8859-9 Turkish, Hebrew logical+visual pair); `EscCharSetProber` (HZ-GB-2312, ISO-2022-CN/JP/KR); `Latin1Prober`; `MacRomanProber`; `HebrewProber` (visual-vs-logical decider, not a detector itself).
- Base `CharSetProber`: `feed()` / `state` (`DETECTING/FOUND_IT/NOT_ME`) / `get_confidence()` / `charset_name` / `language`; machinery: `CodingStateMachine`, `CharDistributionAnalysis`, `JPCtx`; `enums.LanguageFilter` (per-script prober subsets); `ResultDict` = `{encoding, confidence, language}`; `cli/chardetect.py` (`description_of()`, `--minimal`, `-l/--legacy`, stdin support).

---

## 2. Strategic assessment + latent capabilities

**Reachability today: LOW for direct calls, MEDIUM for indirect leverage.** Grep over `src/` shows zero direct imports of either library and zero hand-decoding of fetched web bytes: `media_downloader.py` only reads `content-type`/`content-length` headers and writes chunks verbatim; `engine.py:87` decodes an ASCII `VERSION` token; `reasoning.py:165` sniffs SSE `content-type`; `youtube/cipher_solver.py:67` does `unicode_escape` decoding of a JS hex blob. All page decoding happens inside primp (Rust) via `ddgs`' `HttpClient` wrapper, and `httpx` (AI/chat paths) defaults to `utf-8` with header charset only. So neither detector is on the hot path — but the app's whole value surface (Reader + international results + downloaded files) is exactly where mis-decoded text shows up as mojibake.

Concrete, reachable ideas (ranked):
1. **Reader garble-fix**: when `fmt="content"` (raw bytes) is requested, run `charset_normalizer.from_bytes(sample).best()` before decode and show `encoding · chaos%` in the Reader header — fixes garbled non-UTF-8 pages (Shift_JIS, windows-1251, GB18030) that primp labels wrong.
2. **Downloaded text-file handling**: after `media_downloader` finishes a `text/*` (non-media) payload, detect encoding and either convert to UTF-8 on save or suffix the filename (`name.shift_jis.txt`) instead of writing mojibake as UTF-8.
3. **Content-Type vs sniffing conflicts**: `charset_encoding` (httpx) / primp header charset is trusted blindly today; on `UnicodeDecodeError`-adjacent garble (high chaos score on the decoded `str` re-encoded), prefer the sniffed codec — one `except` branch in the extract wrapper.
4. **Confidence-threshold UX**: surface a "low-confidence decode" warning when `1 − chaos < 0.5` (chardet: `confidence < 0.5`), offering one-tap retry through the next-best match (`matches[1]` / `detect_all()[1]`).
5. **BOM hygiene on save**: `_save_text_content` writes UTF-8 without BOM; use `match.bom` / `identify_sig_or_bom()` to preserve-or-strip deliberately so files reopen correctly in Notepad/Excel.
6. **`detect_all()` for CJK ambiguity**: Big5 vs GB2312 vs EUC-TW ties are common; the ranked list (chardet-only capability) fits a "try next encoding" affordance better than charset-normalizer's single best.

**Ballast verdict**: `charset-normalizer` = justified ballast today (hard `requests` dependency, ~small, and the right tool if idea 1–5 is ever built). `chardet` = pure transitive ballast (see §3) — do not add a direct dependency on it; if detection is ever needed, standardize on charset-normalizer and let `chardet` ride along untouched.

## 3. Gotchas

- **Both installed = redundancy, and the wrong one wins inside `requests`.** `chardet 5.2.0` arrives via `flet-cli → cookiecutter → binaryornot → chardet`; `charset-normalizer 3.5.1` via `requests 2.34.2`. Worse: `requests/compat.py:_resolve_char_detection()` tries `("chardet", "charset_normalizer")` **in that order**, so `Response.apparent_encoding` currently resolves to **chardet**, not charset-normalizer, whenever both are present. Any code path relying on `requests`' fallback guessing gets chardet semantics (different name spellings, e.g. `Windows-1252` vs `cp1252`).
- **`detect()` cost scales with buffer size — truncate the sample.** chardet's `detect()` feeds the entire buffer through every prober group; charset-normalizer self-limits to `steps × chunk_size` (default 5×512 B) but still trial-decodes dozens of codecs. Never pass a full multi-MB download; slice the first ~32–100 KiB (past the 8 KiB meta-charset zone) for detection.
- **Pure-Python speed.** chardet is 100% Python state machines + bigram models — noticeably slower than charset-normalizer (which ships `cd`/`md` Rust speedups: `cd.cp312-win_amd64.pyd`, `md.cp312-win_amd64.pyd`, with `.py` fallbacks). On low-end/Android targets, prefer charset-normalizer and keep detection off the UI thread (`asyncio.to_thread`, as `extract_url` already does).
- **httpx does not sniff.** `httpx.Response.encoding` = explicit setter → `Content-Type` charset → `default_encoding` (`"utf-8"` string; a callable *can* enable autodetection but nothing in `src/` sets one). Missing/mislabelled server charsets therefore decode as UTF-8 with `errors="replace"` — this is precisely the Reader-mojibake vector idea 1 addresses. primp's `.text*` decoding is Rust-internal with the same header-first behavior.

## 4. Coverage

- **charset-normalizer: 10 / 12 `.py` files read fully** (`__init__`, `__main__`, `api`, `constant`, `legacy`, `models`, `utils`, `version`, `cli/__init__`, `cli/__main__`); `cd.py` read partially (imports + public-function heads) and `md.py` inventoried via class/function listing (compiled `.pyd` speedups have no readable source by nature).
- **chardet: 9 / 49 `.py` files read fully** (`__init__`, `universaldetector`, `charsetprober`, `enums`, `resultdict`, `version`, `mbcsgroupprober`, `sbcsgroupprober`, `cli/chardetect`); remaining 40 (individual probers, state tables, frequency models, `__main__`, `cli/__init__`, `metadata/languages`) inventoried via targeted grep (charset names, group rosters, state-machine roles) — sufficient because they are data tables behind the 9 files above.
- Consumer evidence: full `src/` grep for `charset_normalizer|chardet|from_bytes|UniversalDetector`, decode/encoding/content paths in `content_reader_screen.py`, `media_downloader.py`, `agent_files.py`, `services/youtube/`, `search_service.py:extract_url`, `ddgs/ddgs.py:extract`, `ddgs/http_client.py`, plus `uv.lock` dependency edges and `requests/compat.py`, `httpx/_models.py`, `primp/__init__.pyi` decode behavior.
