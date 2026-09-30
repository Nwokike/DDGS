# httpx 0.28.1 — Dependency Audit for DDGS

> Package: `httpx==0.28.1` under `.venv/Lib/site-packages/httpx/` (23 .py files, all read).
> Consumer: DDGS `src/` — async HTTP layer behind `ai_service` (router probes, catalog fetch),
> `services/reasoning.py` ThoughtTapTransport (SSE tee for kani chat stream),
> `update_service`, `license_service`, `engine.py`, `kani_backend.py` (Timeout object only).
> No `Client.paginate`, no SSE helper, no client-level retry exist in this version.

## 1. COMPLETE API INVENTORY (one line each)

**Clients — `Client` / `AsyncClient` (`_client.py`) constructor params (identical sets):**
- `auth: AuthTypes | None` — `Auth` instance, `(user, pass)` tuple → BasicAuth, or callable → FunctionAuth; client default, per-request overridable via `USE_CLIENT_DEFAULT` sentinel.
- `params: QueryParamTypes | None` — default query params merged into every request (`str|dict|list[tuple]`).
- `headers: HeaderTypes | None` — merged over built-ins (`Accept: */*`, `Accept-Encoding: gzip,deflate,br(,zstd)`, `Connection: keep-alive`, `User-Agent: python-httpx/0.28.1`).
- `cookies: CookieTypes | None` — persistent `Cookies` jar (`dict|list[tuple]|CookieJar|Cookies`); extracted from responses, re-sent automatically.
- `verify: SSLContext | str | bool = True` — `True`→certifi (or `SSL_CERT_FILE`/`SSL_CERT_DIR` when `trust_env`), `False`→no-verify context, `SSLContext`→custom; **`str` path deprecated**.
- `cert: CertTypes | None` — **deprecated**; use `verify=<SSLContext>` + `load_cert_chain()` instead.
- `trust_env: bool = True` — honor env proxies + `SSL_CERT_FILE`/`SSL_CERT_DIR`; DDGS `core/tls.py` workaround exists because of this lookup.
- `http1: bool = True` / `http2: bool = False` — protocol toggles; `http2=True` raises `ImportError` unless `h2` installed (NOT in DDGS venv).
- `proxy: ProxyTypes | None` — single `URL|str|Proxy` applied to all hosts (`all://` mount); `None` + `trust_env` → env-proxy map.
- `mounts: Mapping[str, transport] | None` — per-host transports keyed by `URLPattern` (`"all://"`, `"all://*example.org"`); sorted longest-match; overrides proxy map entries.
- `timeout: TimeoutTypes = 5.0 default` — `float|tuple|Timeout|None`; per-request `timeout=` overrides via `USE_CLIENT_DEFAULT`, `None` disables.
- `follow_redirects: bool = False` — follow 301/302/303/307/308 automatically; else `response.next_request` is populated.
- `limits: Limits = 100 conns / 20 keepalive / 5s expiry` — `Limits(max_connections, max_keepalive_connections, keepalive_expiry)`.
- `max_redirects: int = 20` — over → `TooManyRedirects`.
- `event_hooks: {"request": [...], "response": [...]}` — sync callables on `Client`, async callables on `AsyncClient`; also settable property.
- `base_url: URL | str = ""` — prefix for relative URLs (trailing-slash enforced, path appended).
- `transport: BaseTransport | AsyncBaseTransport | None` — full override; **setting it disables env-proxy map** (`allow_env_proxies = trust_env and transport is None`).
- `default_encoding: str | callable = "utf-8"` — fallback for `response.text` when no charset header (callable = auto-detect hook).
- Lifecycle: `with Client()` / `async with AsyncClient()` or `.close()` / `await .aclose()`; sending on closed client → `RuntimeError`; sync `Client` sending async stream → `RuntimeError`.

**Request-building / sending (`Client` + `AsyncClient` mirror):**
- `build_request(method, url, content/data/files/json, params/headers/cookies, timeout, extensions)` — merges client config, returns `Request` without sending.
- `request(method, url, ...same + auth/follow_redirects/timeout/extensions)` — build + send, buffers body (`read`/`aread`).
- `get/options/head/delete(url, params/headers/cookies/auth/follow_redirects/timeout/extensions)` — no body params by design.
- `post/put/patch(url, + content/data/files/json)` — body-capable verbs.
- `stream(method, url, ...)` — context manager (`with` / `async with`) yielding streaming `Response`, auto-`close()` on exit; must consume or close.
- `send(request, stream=False, auth, follow_redirects)` — sends prebuilt `Request` as-is; `stream=True` leaves body open.
- `send` pipeline: `request hooks → single send → response hooks → redirect loop → auth-flow loop`; `response.history` list, `response.elapsed` set on close.

**Timeout / limits / proxy config (`_config.py`):**
- `Timeout(timeout, *, connect/read/write/pool)` — scalar default + per-phase overrides; tuple form `(connect, read, write?, pool?)`; `.as_dict()`; `Timeout(None)` disables all.
- `Limits(*, max_connections=None, max_keepalive_connections=None, keepalive_expiry=5.0)` — pool caps; `DEFAULT_LIMITS = 100/20`.
- `Proxy(url, *, ssl_context=None, auth=(user,pass)|None, headers=None)` — schemes `http/https/socks5/socks5h` (socks needs `socksio` extra); creds stripped from URL into `.raw_auth` (repr masks password); `DEFAULT_TIMEOUT_CONFIG = Timeout(5.0)`, `DEFAULT_MAX_REDIRECTS = 20`.
- `create_ssl_context(verify=True, cert=None, trust_env=True)` — the function DDGS's TLS bug runs through (`_config.py:35` checks `SSL_CERT_FILE` first).

**Retry:**
- No client-level `retries`/`max_retries` — `reasoning.py:203` comment is correct; only `HTTPTransport/AsyncHTTPTransport(retries=0)` passthrough to httpcore connection retries (not HTTP-status retries); app-level retry (openai `max_retries=2`) is the right layer.

**Transports (`_transports/`):**
- `HTTPTransport / AsyncHTTPTransport(verify, cert, trust_env, http1, http2, limits, proxy, uds, local_address, retries=0, socket_options)` — yes, **both accept `retries=`** (the audit question inverted: `verify=` is SSL config, `retries=` is its sibling param); `uds=` unix-socket, `local_address=` bind, per-proxy `HTTPProxy/SOCKSProxy` pools; exceptions mapped httpcore→httpx via `map_httpcore_exceptions()`.
- `ASGITransport(app, raise_app_exceptions=True, root_path="", client=("127.0.0.1",123))` — call ASGI app in-process (async only).
- `WSGITransport(app, raise_app_exceptions=True, script_name="", remote_addr="127.0.0.1", wsgi_errors=None)` — call WSGI app in-process (sync only).
- `MockTransport(handler)` — sync or async callable `Request → Response`; async handler in sync `Client` → `TypeError`; ideal test double, unused by DDGS today.
- `BaseTransport / AsyncBaseTransport` — subclass interface (`handle_request` / `handle_async_request`, `close`/`aclose`, context-manager support); `ThoughtTapTransport(httpx.AsyncHTTPTransport)` follows this pattern.

**Models (`_models.py`):**
- `Request(method, url, *, params/headers/cookies/content/data/files/json/stream/extensions)` — auto `Host`, `Content-Length: 0` on POST/PUT/PATCH, `Content-Length` vs chunked; `.content` (needs `read()`), `.read()/.aread()`, `.stream`, `.url/.method/.headers/.extensions`.
- `Response(status_code, *, headers/content/text/html/json/stream, request, extensions, history, default_encoding)` — `.content/.text/.json()/.cookies/.links (Link-header dict)/.raise_for_status()/.url/.status_code/.http_version/.reason_phrase/.elapsed/.history/.next_request/.is_closed/.is_stream_consumed/.request`; `.read()/.aread()` buffer; `.iter_bytes(chunk_size)/.iter_text()/.iter_lines()/.iter_raw()` + `aiter_bytes/aiter_text/aiter_lines/aiter_raw`; `.close()/.aclose()`; `ResponseNotRead/RequestNotRead/StreamConsumed/StreamClosed` on misuse.
- `Headers` — case-insensitive multi-dict (`get/get_list/multi_items/raw/encoding`); sensitive values obfuscated in repr.
- `Cookies` — jar with `extract_cookies/set_cookie_header/update/get`; per-request `cookies=` deprecated (see Gotchas).
- `codes` (`_status_codes.py`, IntEnum) — `codes.OK`, `codes.SEE_OTHER`, etc., used internally for redirect-rewrite rules.

**Auth (`_auth.py`):** `Auth` base (`auth_flow` generator + `sync/async_auth_flow` overrides, `requires_request_body/response_body` flags); `BasicAuth(user, pass)`; `DigestAuth(user, pass)` (MD5/SHA-256/512, `-sess` variants; **`auth-int` qop raises NotImplementedError**); `NetRCAuth(file=None)`; implicit `FunctionAuth` from any callable; URL-embedded `user:pass@host` auto-fallback to Basic.
**Content (`_content.py`):** `content=` takes `str|bytes|sync|async byte-iterable` (dict rejected with hint); iterables without length → chunked; `data=` dict → urlencoded, `files=` → multipart, `json=` → compact JSON (`allow_nan=False`).
**Multipart (`_multipart.py`):** `MultipartStream(data, files, boundary=random16)`; `FileField` 2/3/4-tuples `(filename, fileobj[, content-type[, headers]])`, mimetype guessed, `BytesIO` required (no `StringIO`/text mode); unknown file length → chunked.
**Decoders (`_decoders.py`):** `gzip/deflate/br/zstd/identity` via `SUPPORTED_DECODERS` (brotli/zstd optional deps); `LineDecoder/TextDecoder/ByteChunker` back `iter_lines/iter_text`.
**URLs (`_urls.py`, `_urlparse.py`):** `URL(url, params=...)` (`.host/.port/.scheme/.path/.query/.raw_path/.netloc/.is_relative_url/.copy_with()/.join()`), `QueryParams` mapping+merge, `URLPattern` mount matcher.
**Types (`_types.py`):** `TimeoutTypes/ProxyTypes/AuthTypes/CookieTypes/HeaderTypes/QueryParamTypes/RequestContent/RequestData/RequestFiles/FileTypes/CertTypes/RequestExtensions/SyncByteStream/AsyncByteStream`.
**Top-level one-shot API (`_api.py`, sync only):** `httpx.request/get/options/head/post/put/patch/delete/stream(method, url, params/content/data/files/json/headers/cookies/auth/proxy/timeout/follow_redirects/verify/trust_env)` — each builds a throwaway `Client`; no async equivalent (use `AsyncClient`).
**CLI (`_main.py`):** `python -m httpx <URL> [OPTIONS]` via click+rich+pygments (needs `httpx[cli]` extras; not installed here); pretty-prints response, not a library API.
**Exceptions (`_exceptions.py`):** `HTTPError → {RequestError → {TransportError → {TimeoutException → {Connect/Read/Write/PoolTimeout}, NetworkError → {Connect/Read/Write/CloseError}, ProtocolError → {Local/RemoteProtocolError}, ProxyError, UnsupportedProtocol}, DecodingError, TooManyRedirects}, HTTPStatusError}` + `InvalidURL/CookieConflict/StreamError → {StreamConsumed/StreamClosed/ResponseNotRead/RequestNotRead}`; `request_context()` attaches `.request`.
**Utils (`_utils.py`):** `get_environment_proxies()` (`HTTP(S)_PROXY/ALL_PROXY/NO_PROXY` incl. `*`, CIDR, localhost rules), `peek_filelike_length`, `primitive_value_to_str`, `URLPattern`.

## 2. LATENT CAPABILITIES FOR DDGS (ranked by value × ease)

1. **Route the app proxy into httpx clients (gap, high value).** `state.proxy` is wired only to primp/search (`search_service.py:47,204`); every `httpx.AsyncClient(...)` in `ai_service.py:128,173,369`, `engine.py:59`, `license_service.py:100`, `update_service.py:64`, plus `ThoughtTapTransport`, passes no `proxy=` — corporate-proxy users bypass it on AI/license/update traffic. Fix: shared client factory reading storage proxy → `proxy=state.proxy or USE_ENV`, keep `trust_env=True`.
2. **Event hooks for logging/metrics (easy win).** `event_hooks={"request":…, "response":…}` unused everywhere; one hook pair on the shared factory gives per-request latency/status/URL (redacted) logging — currently only a `logger.info` inside httpx itself.
3. **`MockTransport` for tests (easy win).** Tests hand-roll fakes (`FakeEngine` in `test_kani_backend.py`, `FakeStorage` in `test_license.py`, ad-hoc `httpx.Response(...)` at `test_kani_backend.py:287+`); `MockTransport(sync_or_async_handler)` + `AsyncClient(transport=…)` covers `ai_service` probes, catalog fetch, license/update paths with real client semantics (redirects, hooks, timeouts).
4. **Stop minting short-lived clients; tune `Limits` (perf).** Router health probes (`timeout=0.5/2.0`) and catalog fetch each open `async with AsyncClient(http2=False)` → default pool `100/20/5s` never reused; use one long-lived client per service (or at least explicit `Limits(max_connections=…, keepalive_expiry=…)`) so keep-alive actually applies.
5. **Transport `retries=` for flaky probes (small, targeted).** `AsyncHTTPTransport(retries=1)` is the only built-in retry and is unused; consider it for the UDP-ish router health probes — but keep LLM-call retry at the openai layer (`max_retries=2`, as `reasoning.py` already does), since httpx retries never cover HTTP 5xx.
6. **Auth helpers instead of hand-made headers.** Bearer tokens are hand-set; `Auth` subclass or one-line `FunctionAuth` centralizes refresh/retry-on-401 (Digest 401→replay flow comes free if ever needed); `(user, pass)` tuple shortcut available.
7. **Cookie jar (dormant).** Client-level `Cookies` persistence unused — only matters if router/catalog/gateway ever becomes session-based; do not add pre-emptively.
8. **`Response.links` + `next_request` for catalog paging (dormant).** No `Client.paginate` exists in 0.28 — paging is hand-rolled; `_fetch_catalog` (`ai_service.py:321`) is a single `GET {base}/models`, so nothing to page today; `links` Link-header parser is ready if the endpoint ever paginates.
9. **Streaming iterators for SSE/probes (dormant).** No `aiter_sse`/EventSource helper exists — `aiter_lines/aiter_text/aiter_bytes` + `client.stream()` is the toolkit; probes use buffered `get` (correct for health checks); the kani stream already tees raw bytes in `ThoughtTapTransport`, so no change needed.
10. **HTTP/2: keep `http2=False` (deliberate).** `h2` is not installed in the venv — `http2=True` would crash with `ImportError`; local router/health/catalog endpoints gain nothing from multiplexing; revisit only with a multiplexed remote + `pip install httpx[http2]`, ideally per-host via `mounts={"all://": HTTPTransport(http2=True), …}`.
11. **Centralize `base_url` + default headers/timeout.** `base_url=`, default `headers={"User-Agent":…}`, and `Timeout(180, connect=4)`-style config are per-call today; a factory issuing `AsyncClient(base_url=…, headers=…, timeout=…)` removes the per-request `timeout=` overrides in `ai_service.py:132,175,331`.
12. **SSL/`trust_env` wiring.** `verify=`/`create_ssl_context()` unused directly — correct, since defaults + `core/tls.py` repair cover it; wire `state.verify_ssl` (currently primp-only) into the shared httpx factory as `verify=…` when that setting must apply to AI/license/update traffic too.

## 3. GOTCHAS

- **Lifecycle: must `aclose`.** Every `AsyncClient` holds a connection pool — `async with` (as probes/license/update do) or explicit `await aclose()`; `license_service._client()` returns a bare client, so callers must not drop the `async with` at `:257,290,345`.
- **Timeout layering with the openai SDK.** Per-request `timeout=` beats client default via the `USE_CLIENT_DEFAULT` sentinel (`None` = disable, not "default"); `build_thought_client` sets `Timeout(180, connect=4)` on httpx while `openai.AsyncOpenAI(timeout=…, max_retries=2)` wraps it — keep openai's timeout ≥ httpx's or httpx wins the race opaquely.
- **HTTP/2 dep.** `h2` absent → any `http2=True` raises `ImportError` at construction, not at request time; `AsyncHTTPTransport(http2=…)` same.
- **`transport=` kills env proxies.** `allow_env_proxies = trust_env and transport is None` (`_client.py:685,1399`) — `ThoughtTapTransport` therefore ignores `HTTP_PROXY/NO_PROXY`; proxy support there must be coded into the custom transport or added via `mounts`.
- **0.28 deprecations (all `DeprecationWarning`):** `verify=<str path>` → `ssl.create_default_context(cafile/capath=…)`; `cert=…` → `verify` context + `load_cert_chain()`; per-request `cookies=…` → set on the client (ambiguous persistence); `data=<bytes>` → `content=<bytes>`.
- **Generator bodies + redirect/auth replay → `StreamConsumed`.** Redirects preserve the body stream; a one-shot generator cannot be re-sent — use bytes or seekable file-likes for POSTs that may redirect or Digest-auth.
- **Buffered vs streaming errors.** Non-stream `request()` auto-`read()`s; `.stream()` responses must be consumed/`close()`d inside the CM or connections leak; accessing `.content/.text/.json()` on an unread streaming response raises `ResponseNotRead`.
- **Digest `auth-int` unsupported** (`NotImplementedError`); `NetRCAuth` reads `~/.netrc` keyed by host — surprising in a desktop app, avoid.
- **Redirect semantics:** 303 → GET, 302 → GET (browser compat), 301 POST → GET; `Authorization` stripped cross-origin except direct http→https upgrade; `Cookie` re-derived from jar; fragment from original preserved; cap `max_redirects=20`.
- **SOCKS/CLI/zstd/br extras not installed** — `socksio`, `brotli`, `zstandard`, `click/rich/pygments`, `h2` all absent: SOCKS proxies, CLI, and br/zstd decoding paths raise `ImportError` on use.

## 4. COVERAGE

- Files read: 23 / 23 — `__init__.py`, `__version__.py`, `_api.py`, `_auth.py`, `_client.py`, `_config.py`, `_content.py`, `_decoders.py`, `_exceptions.py`, `_main.py`, `_models.py`, `_multipart.py`, `_status_codes.py`, `_transports/__init__.py`, `_transports/asgi.py`, `_transports/base.py`, `_transports/default.py`, `_transports/mock.py`, `_transports/wsgi.py`, `_types.py`, `_urlparse.py`, `_urls.py`, `_utils.py`.
- DDGS call sites grepped: `src/services/ai_service.py`, `reasoning.py`, `kani_backend.py`, `license_service.py`, `update_service.py`, `engine.py`, `core/tls.py`, `main.py`, `core/storage_paths.py`, `search_service.py` (proxy), `tests/test_kani_backend.py`, `tests/test_license.py`.
