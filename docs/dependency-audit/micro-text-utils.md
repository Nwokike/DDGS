# Micro Text Utils — Dependency Audit (six / slugify / text_unidecode / binaryornot / repath)

Date: 2026-09-29. Consumer: DDGS (`src/`, Flet desktop app). Method: full source read + `src/` grep + `uv.lock` reverse-dep trace.

**Headline: zero direct imports in `src/` for all five. All five arrive transitively.**
Runtime chain: `ddgs-app → flet → repath → six`, `ddgs-app → … → python-dateutil → six`.
Dev-time chain (via `flet-cli → cookiecutter`, a `[package.dev-dependencies]` entry): `cookiecutter → python-slugify → text-unidecode`, `cookiecutter → binaryornot`, `flet-cli → binaryornot`.
Removing any of them from the lockfile would break a parent package — none are removable ballast, but none earn a direct import either (except via the ideas in §2).

---

## 1. API INVENTORY

### six 1.17.0 — single file `six.py` (1004 lines). PY2/3 compat shim, frozen since the PY2 era.
- Version flags: `PY2`, `PY3`, `PY34` (all constants on PY3; `PY2` is always `False`).
- Type aliases: `string_types` (= `(str,)`), `integer_types` (= `(int,)`), `class_types` (= `(type,)`), `text_type` (`str`), `binary_type` (`bytes`), `MAXSIZE`.
- `six.moves.*` — lazy meta-path importer aliasing ~60 relocated stdlib names: `map`/`filter`/`zip`/`range`/`input`/`intern`, `StringIO`, `urllib_parse`/`urllib_error`/`urllib_request`/`urllib_response`/`urllib_robotparser` (+ full `urllib.*` attr tables), `queue`, `http_client`, `tkinter*`, `winreg`, `reload_module`, `shlex_quote`, etc. `add_move`/`remove_move` mutate the registry.
- Dict iteration: `iterkeys`/`itervalues`/`iteritems`/`iterlists` (= `iter(d.items())` on PY3), `viewkeys`/`viewvalues`/`viewitems` (methodcaller).
- Classes: `with_metaclass(meta, *bases)`, `add_metaclass(metaclass)` decorator, `python_2_unicode_compatible` (no-op on PY3).
- Bytes/text: `b(s)` (latin-1 encode), `u(s)` (identity), `ensure_binary`/`ensure_str`/`ensure_text`, `byte2int`/`indexbytes`/`int2byte`/`iterbytes`.
- Misc: `advance_iterator`/`next` (= builtin `next`), `callable`, `exec_`, `reraise`, `raise_from`, `print_`, unittest alias shims (`assertCountEqual`, `assertRaisesRegex`, …), `create_bound_method`/`create_unbound_method`, `get_method_function`/`get_function_code`/etc.
- Worth knowing: on PY3 **every** branch is a trivial alias — the whole module is dead weight at runtime except as an import namespace for old dependents.

### python-slugify 9.1.1 — `slugify/` package (7 files; logic in 2).
- `slugify(text, entities=True, decimal=True, hexadecimal=True, max_length=0, word_boundary=False, separator='-', save_order=False, stopwords=(), regex_pattern=None, lowercase=True, replacements=(), allow_unicode=False, *, replacement_stage='both', backend='auto', algorithm='legacy') -> str` — accepts `str|bytes|bytearray` (bytes decoded UTF-8/ignore).
  - `entities/decimal/hexadecimal`: decode `&amp;` / `&#233;` / `&#xE9;` HTML refs before cleanup.
  - `max_length=0` = unlimited; `word_boundary=True` truncates to whole words; `save_order=True` keeps initial word order instead of best-fit.
  - `separator`: output delimiter (internal pipeline always uses `-`, mapped at the end in legacy).
  - `stopwords`: drop whole words post-slug; `regex_pattern`: custom disallowed-char regex (default `[^-a-zA-Z0-9]+`, or `[\W_]+` with `allow_unicode`).
  - `lowercase`, `replacements` (ordered literal `old→new` rules), `allow_unicode` (NFKC, skip transliteration), `replacement_stage` (`both`/`pre`/`post`), `backend` (`auto`→prefers `Unidecode` pkg, falls back to `text-unidecode`; also `text-unidecode`/`unidecode`/`anyascii`), `algorithm` (`legacy` default frozen output; `modern` = early entity decode, validated args, emitted-char length budget).
- `smart_truncate(string, max_length=0, word_boundary=False, separator=" ", save_order=False)` — legacy public truncation (note: default separator is `" "`, not `"-"`; negative limits keep slice semantics).
- `slugify.special`: `PRE_TRANSLATIONS` = Cyrillic (`ё→e`, `я→ya`, `х→h`, `у→y`, `щ→sch`, `ю→u`) + German (`ä→ae`, `ö→oe`, `ü→ue`) + Greek (`χ→ch`, `Ξ→X`, `ϒ/υ/ύ/ϋ/ΰ→Y/y`) with auto-uppercased variants via `add_uppercase_char`.
- `__main__.py`: full CLI (`python -m slugify`, flags for every param incl. `--algorithm/--backend/--replacement-stage`).
- Pipeline order (legacy): literal replacements(pre) → quote→`-` → NFKD+transliterate (or NFKC) → entity decode → NFKC/NFKD → lower → strip quotes → `(?<=\d),(?=\d)` removal → disallowed→`-` → dedupe dashes → stopwords → replacements(post) → smart_truncate → separator map.

### text_unidecode 1.3 — `text_unidecode/` (1 code file + 1 data file).
- `unidecode(txt) -> str` — char-by-char `ord()` lookup into `data.bin` (~311 KB, NUL-separated replacement table); codepoints past the table are silently dropped; NUL maps to `\x00`.
- No options, no API surface beyond the one function. Pure-Python + data file; the `backend='auto'` fallback inside slugify when the `Unidecode` package is absent (which is the case in this venv — only `text_unidecode` is installed, so it is the *active* transliteration backend).

### binaryornot 0.4.4 — `binaryornot/` (3 files) + hard dep on `chardet`.
- `check.is_binary(filename) -> bool`: returns `True` for `*.pyc` by extension, else delegates to `helpers.is_binary_string(get_starting_chunk(filename))` (first 1024 bytes).
- `helpers.is_binary_string(chunk)`: Perl/Bendersky heuristic — binary if (control-char ratio > 30% AND high-byte ratio < 5%) OR (both ratios > 80%); then `chardet.detect` confirmation — high-confidence non-ASCII decodable content is rescued to text; final tripwire: any `\x00`/`\xff` byte → binary. Empty input → text (`False`).
- `helpers.get_starting_chunk(filename, length=1024)` (binary-mode read; prints + returns `None` on `IOError` — note: `is_binary_string(None)` would then crash on `len()`), `helpers.print_as_hex(s)` debug aid.

### repath 0.9.0 — single file `repath.py` (297 lines). Express-style path→regex compiler (port of JS `path-to-regexp`).
- `pattern(path, end=True, strict=False) -> str`: `str` path → tokenize → regex source; accepts a compiled regex (passes through `.pattern`) or a list of paths (`(?:a|b)` alternation).
- `compile(path, flags=0, **options) -> re.Pattern`, `match(path, string, flags=0, **options) -> Match|None`.
- `parse(string) -> list`: tokenizer — `:name`, `:name(\d+)`, `(groups)`, `*` wildcards, `?`/`+`/`*` suffixes, `\` escapes; unnamed groups get numeric names.
- `tokens_to_pattern(tokens, end, strict)`: named groups become `(?P<name>…)`; non-strict appends `(?:/(?=$))?`.
- `template(path) -> fn(obj)`: reverse router — builds a URL string from a dict (percent-encodes via `six.moves.urllib.parse.quote`, validates values against token patterns, raises `KeyError`/`ValueError`/`TypeError` on mismatch).
- Internal: `escape_string`, `escape_group`, `PATH_REGEXP`, `PATTERNS` (REPEAT/OPTIONAL/REQUIRED). Depends on `six` (`string_types`, `text_type`, `moves.urllib.parse`).

---

## 2. STRATEGIC ASSESSMENT + LATENT CAPABILITIES

| Package | Verdict | Rationale |
|---|---|---|
| six | **Legacy ballast (transitive-only)** | Nothing in `src/` imports it; kept alive by `repath` + `python-dateutil`. Never import in new code. |
| python-slugify | **Adopt — highest-value latent capability** | Already in the tree (via cookiecutter); `src/` hand-rolls what it does, worse. |
| text-unidecode | **Adopt implicitly via slugify** | No reason to call `unidecode()` directly; it rides along as slugify's backend. |
| binaryornot | **Opportunistic — one real use case** | Dev-time dep (cookiecutter/flet-cli); using it at runtime adds a `chardet` read path for a niche check. |
| repath | **Live infrastructure (transitive)** | Powers Flet routing (`flet/components/router.py`, `flet/controls/template_route.py`); DDGS is a Flet app so this is load-bearing framework plumbing, not ballast. |

### Latent capability → concrete idea (ranked)
1. **`agent_files._slug()` is ASCII-only and host-only** (`src/services/agent_files.py:48-52`: `re.sub(r"[^A-Za-z0-9._-]+", "-", host)` on the URL *hostname*, truncated to 48 chars). Non-ASCII hosts/titles collapse to dashes and the page title is ignored entirely. Replace with `slugify(title or host, max_length=48, word_boundary=True, save_order=True)` — unicode-correct, title-aware saved-page filenames for free since the package is already vendored.
2. **`media_downloader.sanitize_filename()` hand-rolls Windows-char stripping** (`src/services/media_downloader.py:33-48` — replaces `[\\/:*?"<>|\r\n\t]` with `_`, keeps case/spaces/unicode). Layering `slugify(name, separator="_", …)` (or `allow_unicode=True` for CJK titles) in front gives transliterated, filesystem-safe download names; unidecode turns e.g. `W28 书籍` into ASCII instead of mojibake-or-underscores.
3. **Sniff-then-handle downloads with `binaryornot.is_binary()`**: `media_downloader.download_media()` currently trusts `expect_media`/content-type and raises `NotMediaError` on HTML. A post-download `is_binary()` sniff on `FORMAT_EXT["content"] → ".bin"` saves (see `agent_files.FORMAT_EXT`, `agent_files.py:60-66`) would route "is this actually text I can extract?" before text-vs-binary handling.
4. **repath is available for any in-app deep-link/mini-router need**: `repath.template("/page/:id")` builds URLs and `repath.match()` dispatches them — but only reach for it if DDGS grows real route templates; today Flet owns that layer.
5. **six: do nothing.** If `python-dateutil` ever drops its `six` import (it still uses `integer_types`, `text_type`, `six.moves.range/_thread/winreg` in `rrule.py`, `_parser.py`, `tz/*`), six exits the tree on its own.

---

## 3. GOTCHAS

- **slugify `max_length` counts characters, filesystems count bytes.** ext4/NTFS cap a component at 255 *bytes*; transliterated CJK expands ~1:3. Keep `max_length ≤ ~100` *and* byte-check (`len(name.encode('utf-8'))`) before writing — neither `_slug()` nor `sanitize_filename()` does this today.
- **unidecode is lossy and non-invertible** (phonetic approximations: `ü→u`, `χ→ch`, CJK → rough romanization; unknown codepoints vanish). Fine for display filenames, never for round-trip identity — always pair with the existing `unique_path()` / timestamp-stamp scheme.
- **slugify legacy-vs-modern outputs differ** (entity-decode order, stopword case handling, truncation budget). Pin `algorithm='legacy'` (the default) anywhere output stability matters (saved filenames users may reference), so a future `algorithm` default flip can't rename files out from under the user.
- **binaryornot samples only the first 1024 bytes, leans text, and drags chardet.** UTF-16 files (NUL every other byte) trip the `\x00` rule → false *binary*; small/high-entropy text can false-positive either way. Treat it as a hint, not a verdict — keep the `NotMediaError`/content-type path as the authority.
- **`get_starting_chunk` returns `None` on `IOError`** (and prints), which then crashes `is_binary_string` on `len()`. Guard the call site if adopted.
- **six: never import.** `PY2` is dead, every alias is the stdlib name — `from six.moves.urllib.parse import quote` is just `urllib.parse.quote` with extra steps. If seen in new code, it's a bug-shaped habit.
- **repath `match()` ignores its `flags` argument** (line 264: `compile(path, flags=0, …)` — hardcoded `0`). Pass `repath.compile(path, flags=re.I)` explicitly if case-insensitive routes are ever needed.

---

## 4. COVERAGE — files read / total per package

- **six**: 1/1 — `six.py` (1004 lines, read fully).
- **python-slugify**: 5/7 — `slugify.py` (220), `_legacy.py` (159), `special.py` (21), `__init__.py`, `__main__.py` (CLI); skipped `__version__.py` (metadata constants) and `py.typed` (marker).
- **text-unidecode**: 1 code file + data table sized — `__init__.py` (22 lines, read fully); `data.bin` (~311 KB NUL-separated lookup table, binary — verified size/mtime, not read line-by-line).
- **binaryornot**: 3/3 — `check.py`, `helpers.py`, `__init__.py` (version only).
- **repath**: 1/1 — `repath.py` (297 lines, read fully).
- **Consumer trace**: `grep -ri` over `src/` for all five names (zero direct hits); `uv.lock` reverse-deps confirmed (`cookiecutter→slugify/binaryornot`, `flet→repath→six`, `dateutil→six`); downstream call sites read (`agent_files.py:48-52`, `media_downloader.py:33-48`, Flet `router.py`/`template_route.py` repath call sites).
