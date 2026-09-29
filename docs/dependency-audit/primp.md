# primp — Dependency Audit (100% Capability Utilization)

- Installed version: **2.0.1** (`primp>=1.3.1` floor in `pyproject.toml`)
- Role in DDGS: fast async HTTP/2 browser-emulating client (README: "HTTP client: primp (Rust)")
- Package layout: `__init__.py` (re-export only), `__init__.pyi` (the full API surface),
  `primp.pyd` (Rust extension — no Python source to read), `py.typed`
- Transitive consumer: the `ddgs` library itself uses `primp.Client` internally
  (`ddgs/http_client.py`, `ddgs/cli.py`)

## 1. COMPLETE API INVENTORY (from `__init__.pyi` + Rust docstrings)

### Clients — `Client` (sync) and `AsyncClient` (identical signatures)

Constructor params (22):

| Param | Default | Notes |
|---|---|---|
| `auth` | `None` | `tuple[user, password]` basic/digest-style auth |
| `auth_bearer` | `None` | Bearer token applied to all requests |
| `params` | `None` | Default query params on every request |
| `headers` | `None` | Default headers; mutable live via `.headers` prop / `headers_update()` |
| `cookie_store` | `True` | In-memory cookie jar, kept for client lifetime |
| `referer` | `True` | Auto-send Referer on redirects |
| `proxy` | `None` | `str` URL; supports http/https/socks5 (`http://user:pass@host:port`) |
| `timeout` | `None` | Total timeout (s, float) |
| `connect_timeout` | `None` | **Construction-only, read-only after** |
| `read_timeout` | `None` | Also overridable per-request |
| `dns_timeout` | `None` | **Construction-only, read-only after** |
| `impersonate` | `None` | Browser TLS/HTTP2 fingerprint profile, plain `str` — **no enum in stubs** |
| `impersonate_os` | `None` | OS part of fingerprint; app uses `"random"` |
| `follow_redirects` | `True` | Also overridable per-request |
| `max_redirects` | `20` | Redirect cap |
| `verify` | `True` | TLS verification on/off |
| `ca_cert_file` | `None` | Custom PEM bundle path (alt. to `verify=False`) |
| `https_only` | `False` | Refuse plain-HTTP URLs |
| `http2_only` | `False` | Refuse HTTP/1.x endpoints |
| `dns_resolver` | `None` | Custom resolver(s): `str \| list[str] \| tuple[str, ...]` |
| `base_url` | `None` | Prefix for relative request URLs |
| `cookies` | `None` | Seed cookies at construction |

Client members: read/write props `auth`, `auth_bearer`, `params`, `proxy`, `timeout`,
`read_timeout`, `base_url`, `max_redirects`, `follow_redirects`, `headers`;
read-only props `connect_timeout`, `dns_timeout`, `impersonate`, `impersonate_os`
(so **the fingerprint cannot be rotated on a live client — rotation needs a new client**).
Methods: `headers_update()`, `get_cookies(url)`, `set_cookies(url, cookies)`,
`request(method, url, …)` + all 7 verb shortcuts. Per-request params:
`params, headers, cookies, content (bytes), data, json, files, auth, auth_bearer,
timeout, read_timeout, follow_redirects, stream`. Sync client is a context manager;
`AsyncClient` is an async context manager with `async request/get/…`.

### Impersonation profiles (which browser versions exist)

There is **no `impersonate_*` enum** — `impersonate` is a free `str` resolved inside
the Rust binary (rtls layer), so the stub cannot enumerate it. Evidence found:
- Stub docstring example: `impersonate="chrome_146"`.
- `ddgs` uses `impersonate="random"`, `impersonate_os="random"` (also in `ddgs/cli.py`).
- DDGS app pins `impersonate="chrome_153"`, `impersonate_os="random"`.
- Binary string scan of `primp.pyd` surfaces `edge_144`…`edge_153` families plus
  `chrome` / `firefox` / `safari` / `edge` bases and `"random"`;
  OS strings `Windows` / `macOS` / `Linux` are present alongside the
  `impersonate_os` symbol. (Exact versioned `chrome_NNN` rows live in a compressed
  table in the binary and are not reliably enumerable by strings-scan; treat the
  upstream repo as canonical and `"random"` as the rot-proof choice.)
- There are **no** raw JA3-string / custom-TLS-fingerprint params, no `decompress`
  flag, no IP-rotation / proxy-list param, and no connection-pool sizing params
  (`max clients/connections` does not exist — pooling is internal to the client).

### Responses — `Response` / `AsyncResponse`

Props: `url`, `status_code`, `content (bytes)`, `encoding` (**settable** — charset
override), `headers (dict)`, `cookies (dict)`, `text`, **`text_markdown`,
`text_plain`, `text_rich`** (server HTML → Markdown/plain/rich extraction built in).
Methods: `json()`, `raise_for_status()`; sync streaming `read()`,
`iter_bytes(chunk_size)`, `iter_text(chunk_size)`, `iter_lines()`, `next()`,
`close()` + sync CM; async twins `aread()`, `aiter_bytes/aiter_text/aiter_lines()`,
`anext()`, `aclose()` + async CM. Stub warns: *"All property access is synchronous
but may block"* on `AsyncResponse`.

### Module-level one-shot functions (sync, temp client each call)

`get / head / options / delete / post / put / patch / request` — accept the union of
client + request params (`impersonate`, `proxy`, `verify`, `ca_cert_file`,
timeouts, `stream`, …). No async equivalents.

### Errors (13) & type aliases

`PrimpError` → `BuilderError`; `RequestError` → `ConnectError`, `TimeoutError`,
`DNSError` → `DNSTimeoutError` (also a `TimeoutError`); `StatusError`
(**carries `.status_code`, `.url`**), `RedirectError`, `BodyError`,
`DecodeError` → `JSONDecodeError` (also a `json.JSONDecodeError`, requests-style);
`UpgradeError`. Aliases: `HeadersType/ParamsType/CookiesType/FilesType`
(`Mapping[str, str] | None`); **`FilesType` accepts filesystem paths only —
in-memory bytes/tuple uploads are not implemented**; `AuthType`.

### What primp does NOT have

No response caching, no retry/backoff policy, no proxy rotation lists, no download
resume (`Range` must be hand-rolled), no upload progress callbacks, no WebSocket,
no custom DNS-over-HTTPS flag beyond `dns_resolver`, no per-host concurrency
limits, no HAR/cookie-file import-export (only `get/set_cookies` in memory).

## 2. DDGS USAGE INVENTORY (exact params used per call site)

| Site | Client | Params passed |
|---|---|---|
| `search_service._primp_client_kwargs()` | `AsyncClient` | `impersonate="chrome_153"`, `impersonate_os="random"`, `timeout`, `proxy` (iff `state.proxy`), `verify=False` (iff `state.verify_ssl is False`) |
| YouTube fallback (`youtubei/v1/search`) | same | `post(url, json=body)`; reads `status_code`, `.json()` |
| OpenLibrary fallback | same | `get(url, params={q, limit})`; reads `status_code`, `.json()` |
| `media_downloader.download_media()` | `AsyncClient` | `impersonate`, `follow_redirects=True`, `timeout=60`; `get(url, headers={Referer?}, stream=True, follow_redirects=True)`; `raise_for_status()`, `headers[content-type/content-length]`, `aiter_bytes(chunk)` |
| `youtube/innertube_client.resolve_youtube()` | `AsyncClient` | `timeout=10`, `follow_redirects=True`, `impersonate="chrome_153"`, `impersonate_os="random"`, `proxy`/`verify` from state; `get(watch, headers={Accept-Language}, follow_redirects=True)` → `.text`; `post(player, json=payload, headers={Content-Type, Android UA})` → `.json()`; `get(base.js)` → `.text` |
| `ddgs` lib (transitive) | sync `Client` | `proxy, timeout, impersonate="random", impersonate_os="random", verify/ca_cert_file`; verbs via `.request()`; exposes `content/status_code/text/text_markdown/text_plain/text_rich` |
| Agent path | — | `agent_files.download_media()` → `media_downloader` (no direct primp use; no `agent_files/` primp import exists) |

Verbs used directly: only `get`, `post`. Never used directly: `head/options/delete/
put/patch/request`, module one-shots, sync `Client`.

## 3. LATENT CAPABILITIES FOR DDGS (ranked by UX impact)

1. **Wire proxy/SSL into `media_downloader` (GAP — real bug).** Search fallbacks and
   InnerTube forward `state.proxy` / `state.verify_ssl`, but `download_media()` builds
   its client with only `impersonate/follow_redirects/timeout`. Users behind a
   corporate/VPN proxy or with the SSL toggle off get working search + broken
   downloads. Fix: reuse `_primp_client_kwargs()` there (pass proxy/verify through).
2. **Fingerprint rotation on 403/429.** App pins `chrome_153` (rots as Chrome ships);
   `ddgs` already uses `"random"`. On `StatusError`/403/429, rebuild the client with
   `impersonate="random"` (or cycle chrome → edge → safari) and retry once. Cheap,
   directly reduces scrape/download blocks. Note rotation requires a **new client**
   (`impersonate` is read-only).
3. **Stop throwing away the cookie jar + connection pool.** Every fallback constructs
   a fresh `AsyncClient` per call, so `cookie_store=True` never survives and
   keepalive/HTTP/2 multiplexing is lost. A shared long-lived `AsyncClient` (one for
   search fallbacks, one for YouTube) buys session cookies for login/age-gated
   sources and H/2-multiplexed parallel media checks. Pair with `get_cookies/
   set_cookies` to persist or inject sessions.
4. **Download resume with `Range`.** Downloader streams correctly (`stream=True` +
   `aiter_bytes`) and cleans partial files, but always restarts. Send
   `headers={"Range": f"bytes={existing}-"}` and append on 206 — big UX win on
   large/flaky video downloads. `aiter_lines/aiter_text` remain available for
   line-oriented endpoints.
5. **Granular timeouts.** Only blanket `timeout` is used (10 s search / 60 s
   download). `connect_timeout` / `dns_timeout` (construction-only) separate
   "server down" from "server slow"; per-request `read_timeout` lets big media
   bodies take longer than API calls without raising the connect budget.
6. **Redirect policy.** `max_redirects` is never set (default 20) — animepahe-style
   hosts with long ad-redirect chains can silently 404-loop; tune per host or at
   least surface `RedirectError` distinctly (see §4).
7. **Charset override.** `response.encoding` is settable but never used — mojibake
   pages from mislabeled sites could be re-decoded instead of shown garbled.
8. **Custom CA instead of `verify=False`.** `ca_cert_file` (also supported through
   `DDGS(verify=<path>)`) lets corp-MITM users stay encrypted; today the SSL toggle
   jumps straight to unverified.
9. **`base_url` + default `params/headers/auth`.** `innertube_client` hand-builds
   every URL/header; a preconfigured client (`base_url="https://www.youtube.com"`,
   default `Accept-Language`) removes duplication. `auth`/`auth_bearer` (client- and
   per-request) are free whenever an authenticated source is added.
10. **Direct `text_markdown/text_plain/text_rich`.** primp extracts these itself, but
    the app only reaches them via `ddgs.extract()`; lightweight "reader mode" fetches
    could skip the ddgs layer. Unused extras of the same tier: `head` (cheap media
    probing before download), `content=`/`data=`/`files=` uploads (only `json=` is
    used), `https_only`/`http2_only` enforcement, custom `dns_resolver`.

## 4. GOTCHAS

- **Exception handlers likely miss primp errors.** Fallback `except` clauses catch
  *builtin* `TimeoutError`/`ConnectionError`/`OSError`, but `primp.TimeoutError`
  derives from `PrimpError`, **not** the builtins — `ConnectError`, `DNSError`,
  `StatusError`, `RedirectError` propagate uncaught. Catch `primp.PrimpError`
  (import defensively, as today) and branch on `StatusError.status_code/.url`
  and `DNSTimeoutError` vs `DNSError`.
- **Sync vs async: correct, with one caveat.** All direct app code uses
  `AsyncClient` + `await` (never blocks the loop); `ddgs`' sync `Client` is always
  run in `asyncio.to_thread` (`search_service` lines ~256/326/459). Caveat: the
  stub warns `AsyncResponse` property access (`.text/.content/.json()`) *"may
  block"* — keep it off hot paths / prefer streaming for large bodies.
- **Android (Flet) availability — verify before release.** The Windows venv uses a
  compiled `primp.pyd`; Android needs a `maturin`-built `aarch64-linux-android`
  wheel from **PyPI** (not `pypi.flet.dev`, which only mirrors Flet packages).
  `primp>=1.3.1` resolves today on desktop — confirm the same floor has Android
  wheels or `flet build` will fail at dependency resolution. (`INTERNET` /
  `ACCESS_NETWORK_STATE` permissions are already declared.)
- **Thread safety.** The shared `DDGS` object (wrapping one sync `Client`) is used
  from `to_thread` workers; the Rust client is `Send/Sync` in practice but primp
  documents no concurrency contract — one client per thread (matching ddgs'
  own `threads` model) is the safe posture.
- **Pinned profile rots; `random` doesn't.** `chrome_153` will age out of
  credibility while `"random"` tracks current releases — prefer `random` for
  fallbacks, keep a pinned profile only where a site is profile-sensitive, and
  revisit the pin quarterly.
- **Uploads are paths-only; timeouts split.** `files={name: path}` — no in-memory
  bytes uploads. `connect_timeout`/`dns_timeout` are construction-only/read-only;
  only `timeout`/`read_timeout` are per-request. No deprecations in 2.0.1 stubs.

## 5. COVERAGE

- primp package: **2/2** Python files read (`__init__.py`, `__init__.pyi`) = 100%
  of the Python surface; Rust behavior sampled via docstrings + `primp.pyd` string
  scan + live `AsyncClient` docstring probe (Rust signatures are `*args/**kwargs`,
  so the `.pyi` is authoritative). `METADATA` checked (name/version only).
- DDGS direct: `services/search_service.py` (full), `services/media_downloader.py`
  (full), `services/youtube/innertube_client.py` (full), `services/agent_files.py`
  (download path), `core/state.py` (proxy/SSL fields), `components/results/
  content_fetcher.py` (fetch path — uses `SearchService`, no direct primp).
- Transitive: `ddgs/http_client.py` (full), `ddgs/cli.py` (primp call site).
- Negative greps (confirming non-use): `primp.Client(`, `get/set_cookies`,
  `headers_update`, `auth_bearer`, `ca_cert`, `dns_resolver`, `http2_only`,
  `https_only`, `cookie_store`, `base_url=` (client), `max_redirects`,
  `connect/dns_timeout`, `aiter_lines/iter_lines`, `.encoding =`,
  `Response.text_markdown` direct — all zero hits in direct app code.
