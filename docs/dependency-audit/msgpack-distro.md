# Dependency audit — msgpack 1.2.2 + distro 1.9.0

Owner goal: 100% capability utilization or honest ballast verdicts.
Consumer: DDGS (`C:\Users\nwoki\.zcode\workspace\default\DDGS`), `src/` makes **zero direct imports** of either package (grep over `src/` clean). Both arrive transitively via `uv.lock`.

| Package | Version | Arrives via | Direct DDGS use |
|---|---|---|---|
| msgpack | 1.2.2 | `flet>=1.0.1` (`uv.lock`: flet deps include `msgpack`) | none — but load-bearing for Flet |
| distro | 1.9.0 | `openai==2.54.0` (`uv.lock`: openai deps include `distro`), pulled in by `kani[openai]` per `pyproject.toml` | none at all |

Backend note (msgpack): **no Rust involved.** Compiled backend is a Cython C extension (`_cmsgpack.cp312-win_amd64.pyd` present in the venv); pure-Python fallback in `fallback.py` is used when the C ext is missing or `MSGPACK_PUREPYTHON` is set.

---

## 1. API INVENTORY

### msgpack (`msgpack/__init__.py` + `fallback.py` + `ext.py` + `exceptions.py`)

One-shot API:
- `packb(o, **Packer-kwargs)` — serialize `o` to `bytes` (autoreset buffer per call).
- `pack(o, stream, **Packer-kwargs)` — serialize `o` and `stream.write()` it.
- `unpackb(packed, **Unpacker-kwargs)` — deserialize one object; raises `ExtraData(unpacked, extra)` on trailing bytes, `ValueError` on truncation, `FormatError`/`StackError` on corrupt/over-nested input.
- `unpack(stream, **Unpacker-kwargs)` — `stream.read()` then `unpackb` (drains the whole stream; not incremental).
- Aliases: `dumps = packb`, `dump = pack`, `loads = unpackb`, `load = unpack` (pickle/simplejson compat shims).

`Packer(default, use_single_float=False, autoreset=True, use_bin_type=True, strict_types=False, datetime=False, unicode_errors='strict', buf_size=None[C-only])`:
- `default` — callable converting unsupported types (Flet passes its control encoder here); called at most once per object.
- `use_single_float` — pack floats as 32-bit (smaller, lossy) instead of 64-bit.
- `autoreset` — `True`: each `pack*` returns `bytes` and clears; `False`: accumulate, read via `.bytes()`/`.getbuffer()`, clear via `.reset()`.
- `use_bin_type` — `True` (spec 2.0): `bytes`→bin family, `str`→str family incl. str8; `False` downgrades bin to raw (legacy compat).
- `strict_types` — exact-type checking; subclasses rerouted to `default`, and **tuples are NOT packed as arrays** (normally tuple→array).
- `datetime` — `True` packs tz-aware `datetime` as Timestamp ext (tzinfo stripped); naive datetimes raise `ValueError` unless `default` handles them.
- `unicode_errors` — encode error handler (default `'strict'`; docs warn against changing it).
- Streaming/chunked methods: `pack_array_header(n)` / `pack_map_header(n)` + raw element packs, `pack_map_pairs(pairs)`, `pack_ext_type(typecode 0–127, data: bytes)`.

`Unpacker(file_like=None, read_size=0, use_list=True, raw=False, timestamp=0, strict_map_key=True, object_hook=None, object_pairs_hook=None, list_hook=None, unicode_errors='strict', max_buffer_size=100MiB, ext_hook=ExtType, max_str_len/max_bin_len/max_array_len/max_map_len/max_ext_len)`:
- `file_like` — if given, pulls via `.read(read_size)`; else push-driven via `.feed(bytes)` + iteration.
- `use_list` — `True`→arrays become `list`, `False`→`tuple`.
- `raw` — `False` (default): raw decoded UTF-8→`str`; `True`: raw stays `bytes` (bin types always `bytes` either way).
- `timestamp` — ext `-1` decoding: `0`=Timestamp object, `1`=float unix, `2`=int unix-nano, `3`=UTC `datetime`.
- `strict_map_key` — `True` (default): only `str`/`bytes` map keys accepted, else `ValueError`.
- `object_hook` / `object_pairs_hook` (mutually exclusive) — post-process each map (dict / generator of pairs, simplejson-style).
- `list_hook` — post-process each array.
- `unicode_errors` — decode error handler for invalid UTF-8 payloads.
- `max_buffer_size` (default 100 MiB; `0`→`2**31-1` in this build) — `BufferFull` guard for untrusted input; per-type caps `max_str_len/max_bin_len/max_array_len` (def. = buffer size) `max_map_len` (def. = half) `max_ext_len` (def. = buffer size); the first two are deprecated in favor of `max_buffer_size`.
- `ext_hook` — callable `(code, data)` for non-timestamp ext (default re-wraps as `ExtType`).
- Streaming methods: `feed()`, iterator/`next()`, `unpack()`, `skip()` (zero-copy jump over a value), `read_array_header()`/`read_map_header()` (pre-size containers), `read_bytes(n)`, `tell()` (stream offset).

`ext.py`:
- `ExtType(code: int 0–127, data: bytes)` — namedtuple wire type for custom extensions.
- `Timestamp(seconds: int, nanoseconds: int 0–999_999_999)` — immutable ext `-1`; `to_bytes()`/`from_bytes()` (32/64/96-bit forms), `from_unix()`/`to_unix()` (float), `from_unix_nano()`/`to_unix_nano()` (int, lossless), `from_datetime()` (tz-aware; naive treated as local)/`to_datetime()` (UTC).

`exceptions.py`:
- `UnpackException` — base (but unpack may also raise non-subclass errors: catch `Exception` to be safe).
- `BufferFull` — input exceeded `max_buffer_size`; `OutOfData` — truncated feed (streaming only); `FormatError(ValueError)` — bad header; `StackError(ValueError)` — nesting past `DEFAULT_RECURSE_LIMIT = 1024` (also surfaced from `RecursionError`).
- `ExtraData(unpacked, extra)` — one-shot unpack with trailing bytes (`.unpacked` = first object, `.extra` = leftover buffer).
- Deprecated aliases: `UnpackValueError = ValueError`, `PackException = Exception`, `PackValueError = ValueError`, `PackOverflowError = OverflowError` (packing overflow itself raises builtin `OverflowError` for >uint64 ints).

Referencable? **No** — msgpack has no object-identity/reference system (unlike pickle); shared or cyclic structures are duplicated (cycles → `ValueError: recursion limit exceeded`), so never pack object graphs with shared mutable state and expect aliasing back.

### distro (`distro/__init__.py` + `distro/distro.py` + `distro/__main__.py`)

Consolidated accessors (all delegate to a module-global `LinuxDistribution()` for the **current** OS):
- `linux_distribution(full_distribution_name=True)` — **deprecated since 1.6.0** (DeprecationWarning); `(name|id, version, codename)` shim for `platform.linux_distribution`.
- `id()` — machine-readable distro ID (`ubuntu`, `debian`, `rhel`, …) via os-release → lsb_release → release-file → uname, lowercased + normalized through tables.
- `name(pretty=False)` — human name (`CentOS Linux`); `pretty=True` appends version+codename (`PRETTY_NAME` preferred).
- `version(pretty=False, best=False)` — version string; `best=True` picks the most precise across sources instead of first non-empty; `pretty=True` appends `(codename)`.
- `version_parts(best=False)` — `(major, minor, build_number)` tuple parsed from `version()` (empty strings for missing parts).
- `major_version(best=False)` / `minor_version(best=False)` / `build_number(best=False)` — single components of the above.
- `like()` — space-separated `ID_LIKE` parent IDs (os-release only, e.g. `debian`, `rhel fedora`).
- `codename()` — release codename (`VERSION_CODENAME`/`UBUNTU_CODENAME` preferred, else parsed from `VERSION`).
- `info(pretty=False, best=False)` — everything as one `InfoDict`: `{id, version, version_parts:{major,minor,build_number}, like, codename}`.
- `os_release_info()` / `lsb_release_info()` / `distro_release_info()` / `uname_info()` — raw per-source dicts (lowercased keys).
- `os_release_attr(attribute)` / `lsb_release_attr(attribute)` / `distro_release_attr(attribute)` / `uname_attr(attribute)` — single item from one source, `""` if absent (there is **no** module-level `oslevel_info()` — AIX oslevel is a `LinuxDistribution` method only).
- Normalization tables: `NORMALIZED_OS_ID` (`ol`���`oracle`, `opensuse-leap`→`opensuse`), `NORMALIZED_LSB_ID` (Oracle/RHEL quirks), `NORMALIZED_DISTRO_ID` (`redhat`→`rhel`).
- `LinuxDistribution(include_lsb, os_release_file, distro_release_file, include_uname, root_dir, include_oslevel)` — testable instance against custom files/`root_dir` (subprocess sources forcibly off with `root_dir` to avoid false data); lazily-parses/caches each source via `cached_property`.
- CLI: `python -m distro [--json|-j] [--root-dir|-r DIR]` — human lines or `info()` as JSON (handy for crash-report capture without writing code).

---

## 2. STRATEGIC ASSESSMENT + LATENT CAPABILITIES

### msgpack — VERDICT: ballast with a purpose (do not remove, do not direct-use lightly)

Yes — it **is Flet's wire format**. `flet/messaging/protocol.py` builds the Python→Dart encoder (`configure_encode_object_for_msgpack`, passed as `msgpack.packb(..., default=...)`, with custom `ExtType(1/2/3)` for date/time/Duration) and `flet_socket_server.py` does `msgpack.unpackb(packet, ext_hook=decode_ext_from_msgpack)` / `msgpack.packb(...)` on the socket bridge. Every Flet UI update flows through it. Zero DDGS `src/` imports is the *correct* state — touching its global config (e.g. `MSGPACK_PUREPYTHON`) would only slow Flet down.

Latent capabilities worth knowing (all optional, none urgent):
- **Compact binary persistence for search caches/history** — `packb`/`unpackb` round-trips of result lists/history dicts are ~30–50% smaller and 2–4× faster than JSON for large payloads; natural fit if DDGS ever caches result pages or chat history on disk. Enables `AutocompletionCache`-style blobs without schema code.
- **Efficient append-only event/log journal** — `Packer(autoreset=False)` + `Unpacker.feed()` is a purpose-built streaming journal: append events with one packer, tail/replay with one feeding unpacker, `skip()` over uninteresting records. Cheaper than JSONL for a diagnostics/event log.
- **Cross-platform state snapshots** — versioned `ExtType` payloads (same pattern Flet uses for Duration) give forward-compatible snapshot blobs for session/workspace state.
- **Android availability** — `uv.lock` ships 66 msgpack wheels (CPython 3.9–3.13 × win/mac/manylinux/musl) but **no Android wheel**; on Android (`flet build apk`) it falls back to pure-Python (`MSGPACK_PUREPYTHON` semantics) unless the build recipe compiles the C ext. Functionally complete either way (fallback is a full implementation, just slower) — but a msgpack-heavy cache design would pay the pure-Python tax on-device, so keep payloads modest or benchmark on the APK before committing.

### distro — VERDICT: pure transitive ballast (zero DDGS touchpoints)

`distro` is **not** under rich (rich 15's deps are just `markdown-it-py` + `pygments`) — it arrives via `openai==2.54.0` (platform telemetry for API headers), itself pulled by `kani[openai]`. On this Windows-first project it can only ever return empty strings/`{}` (see Gotchas). It costs ~60 KB and does nothing. Keep it (removing it means fighting `openai`'s declared deps) but never add a direct import for Windows/macOS logic.

Latent capabilities — all Linux-only, so only relevant to packaging/support tooling, never the app runtime:
- **Linux DEB/RPM build specifics** — `id()` + `like()` + `major_version()` is exactly the branching key for "are we on `debian`-like (DEB) or `rhel`/`fedora`-like (RPM)?" in CI/packaging scripts and install docs.
- **Crash-report environment tagging** — `info()` (or `python -m distro -j`) is a one-line OS fingerprint to attach to bug reports; `LinuxDistribution(root_dir=...)` even lets tests assert packaging logic against fixture roots.
- **Telemetry-free diagnostics** — `distro.id()`/`version()` in a diagnostics/bug-report screen answers "is this a Chromebook (Linux `chromiumos`)? WSL (`ID_LIKE=debian` under a Windows kernel)? a minimal container (`{}`)?" with no network, no tracking.
- **Adaptive docs/links** — `like()`-based branching can serve distro-correct install commands (apt vs dnf vs pacman) and flag distro-specific browser quirks (e.g. missing system CA store, snap-confinement) in help text.

---

## 3. GOTCHAS

msgpack:
- `raw=False` default means incoming str lands as `str` (UTF-8 decoded), `raw=True` keeps `bytes` — the #1 interop bug when the other side (e.g. Dart, Go) distinguishes string vs bytes strictly.
- Map keys are restricted: `strict_map_key=True` default rejects non-`str`/`bytes` keys on unpack with `ValueError`; JSON's implicit int→str coercion does not exist — int keys fail loudly instead.
- NaN/Infinity pack natively as IEEE-754 doubles (no `allow_nan` gate like `json`); strict-JSON consumers downstream will still choke on them — sanitize if a JSON bridge follows.
- `datetime` support is opt-in **both** directions (`Packer(datetime=True)` + `Unpacker(timestamp=1/2/3)`); naive datetimes raise `ValueError`, tz-aware lose their tzinfo (converted to UTC epoch). Flet sidesteps this with its own `ExtType(1/2)` date/time codecs — follow that pattern for custom types.
- One-shot `unpackb` raises `ExtraData` on trailing bytes — always pack/unpack symmetric framing (length-prefix or one object per message) rather than concatenating `packb` outputs into one buffer.
- Security: never `unpackb` untrusted bytes without `max_buffer_size`/`max_*_len` caps (default 100 MiB each; `max_map_len` defaults to half); and note the code/doc mismatch — `0` means `2**31-1` in this build, not `2**32-1` as the docstring claims.
- No reference tracking: shared sub-objects duplicate, cycles explode at `DEFAULT_RECURSE_LIMIT=1024` (`ValueError`/`StackError`) — keep payloads trees, or memoize with `default`/`object_hook` yourself.
- `strict_types=True` silently changes tuple behavior (tuples stop packing as arrays) — a nasty surprise if enabled globally for "accuracy".

distro:
- On non-Linux (this project's Windows/macOS dev machines, and any Windows user install) **everything is empty**: `id()`→`""`, `version()`→`""`, `info()`→all-`""`, `*_info()`→`{}`. Any branching on it must treat `""` as "not Linux", never as an error.
- Shells out to `lsb_release`/`uname`/`oslevel` via `subprocess` on first access of those sources — fine on Linux, but don't call it in hot paths; results are cached per `LinuxDistribution` instance, and the module-global instance caches process-wide.
- `linux_distribution()` emits `DeprecationWarning` — grep-able tech-debt flag if it ever appears in DDGS code; use `id()`/`version()`/`name()`.
- `version(best=True)` vs default can disagree across sources (Debian/CentOS precision quirks documented in the docstring) — pin `best=` explicitly wherever a version comparison drives packaging decisions.

---

## 4. COVERAGE

- msgpack: **4/4 `.py` files read completely** — `__init__.py` (56 lines), `exceptions.py` (49), `fallback.py` (942), `ext.py` (184). C-extension behavior verified by presence (`_cmsgpack.cp312-win_amd64.pyd`) + fallback parity; C sources (not shipped as `.py`) not read — no API surface missed, the fallback documents every parameter.
- distro: **3/3 files read completely** — `distro/distro.py` (1403 lines), `distro/__init__.py` (54), `distro/__main__.py` (4).
- Consumer tracing: `src/` grep (no direct imports), `uv.lock` reverse-deps (flet→msgpack, openai→distro), `pyproject.toml` (`kani[openai]` chain), `flet/messaging/protocol.py` + `flet_socket_server.py` (wire-format confirmation), wheel-list check (66 msgpack wheels, no Android target).
