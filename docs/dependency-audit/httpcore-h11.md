# Dependency audit: httpcore 1.0.9 + h11 0.16.0

Consumer path: DDGS never touches these directly — everything rides under
`httpx.AsyncClient` (httpx 0.28.1): router probes + `/health` checks, model
catalog fetches, kani-stream transport (`ThoughtTapTransport` in
`src/services/reasoning.py`), license/update services. DDGS pins
`http2=False` on every client it builds. `h2`, `socksio`, `trio` are all
ABSENT from site-packages; `anyio` + `sniffio` + `certifi` are present.

---

## 1. COMPLETE API INVENTORY

### httpcore — top-level (`__init__.py`, `_api.py`)

- `request(method, url, *, headers, content, extensions)` — one-shot request on a throwaway `ConnectionPool()`. Fine for probes; wasteful per-call pool setup vs a shared client.
- `stream(method, url, *, headers, content, extensions)` — same, but yields an unread `Response` inside a context manager (`response.read()` / `iter_stream()` before `close()`).
- `__version__ = "1.0.9"`.

### httpcore — models (`_models.py`)

- `URL(url="", *, scheme, host, port, target)` — accepts a plain string OR pre-parsed components; explicit-component form can express proxy-target URLs and `OPTIONS *` that strings cannot. `URL.origin` derives default ports (http 80 / https 443 / ws 80 / wss 443 / socks5 1080).
- `Origin(scheme, host, port)` — pool connection key; equality decides connection reuse.
- `Request(method, url, *, headers, content, extensions)` — extension keys honored downstream: `"timeout"` (dict), `"trace"` (callback), `"sni_hostname"` (TLS SNI override), `"target"` (rewrites `url.target`).
- `Response(status, *, headers, content, extensions)` — sync: `read()` / `iter_stream()` / `close()`; async: `aread()` / `aiter_stream()` / `aclose()`; streams are single-use (`_stream_consumed` guard). Response extensions set by backends: `"http_version"`, `"reason_phrase"`, `"network_stream"` (raw stream — enables CONNECT/Upgrade tunneling), `"stream_id"` (HTTP/2 only).
- `Proxy(url, auth, headers, ssl_context)` — builds `Proxy-Authorization: Basic` header automatically from `auth=(user, pass)`.
- `ByteStream` — wraps plain bytes so sync and async iteration both work.
- `include_request_headers()` — auto-adds `Host` + `Content-Length` (bytes bodies) or `Transfer-Encoding: chunked` (iterators); everything is ASCII-enforced (`enforce_bytes` rejects non-ASCII str).

### httpcore — pools (`_sync/connection_pool.py`, `_async/connection_pool.py` — identical logic)

- `ConnectionPool(*, ssl_context, proxy, max_connections=10, max_keepalive_connections=None, keepalive_expiry=None, http1=True, http2=False, retries=0, local_address=None, uds=None, network_backend=None, socket_options=None)` — async mirror `AsyncConnectionPool` is line-identical except `await`/`aclose` (verified by diff; only backend default differs: `SyncBackend()` vs `AutoBackend()`).
- `max_connections` — cap on concurrent connections; over-limit requests BLOCK on an `Event`/`AsyncEvent` until a slot frees or the per-request `timeout["pool"]` fires (`PoolTimeout`). `None` = unbounded (`sys.maxsize`).
- `max_keepalive_connections` — cap on idle connections kept (clamped to `max_connections`); surplus idle closed on every assign pass. `None` = unbounded.
- `keepalive_expiry` — seconds an idle connection may live before being closed on the next assign pass; `None` = never expires (current DDGS behavior — idle sockets linger until the server kills them).
- `retries` — connect-attempt retries per `HTTPConnection` (default 0); backoff `0s, 0.5s, 1s, 2s, 4s…` (`RETRIES_BACKOFF_FACTOR = 0.5`, `exponential_backoff()`), applies ONLY to `ConnectError`/`ConnectTimeout`, slept via `backend.sleep()`.
- `local_address` — source address for `connect_tcp`; `"0.0.0.0"` forces IPv4, `"::"` forces IPv6.
- `uds` — Unix-domain-socket path instead of TCP (raises on win32 in sync backend).
- `socket_options` — iterable of `SOCKET_OPTION` = `(level, optname, value)` triples passed to `setsockopt()` on every new socket; `TCP_NODELAY=1` is always force-added. This is the SO_KEEPALIVE / TCP_KEEPIDLE / SO_LINGER injection point (sync backend applies them; anyio backend's loop is a no-op pragma — options silently ignored on async path).
- `network_backend` — injectable `NetworkBackend`/`AsyncNetworkBackend`; seam for tests (`MockBackend(buffer, http2=False)`, `AsyncMockBackend`) and for custom transports like `ThoughtTapTransport`.
- `pool.connections` — live introspection list (`<HTTPConnection [origin, HTTP/1.1, ACTIVE/IDLE, Request Count: N]>`); usable for a Diagnostics screen connection readout.
- `handle_request()` reads `timeout["pool"]` from request extensions; unsupported schemes (`""`, non-http/ws) raise `UnsupportedProtocol`.

### httpcore — connections (`_sync/connection.py`, `_async/connection.py`)

- `HTTPConnection(origin, ssl_context, keepalive_expiry, http1, http2, retries, local_address, uds, network_backend, socket_options)` — one origin, lazy connect under a lock; ALPN offers `["http/1.1", "h2"]` when `http2=True` else `["http/1.1"]`; negotiated `h2` selects `HTTP2Connection`, else `HTTP11Connection`. `sni_hostname` extension overrides TLS SNI. Async mirror identical.
- `info()` — `"CONNECTING"` / `"CONNECTION FAILED"` / delegates to inner connection.

### httpcore — HTTP/1.1 backend (`_sync/http11.py`, `_async/http11.py`)

- `HTTP11Connection(origin, stream, keepalive_expiry)` — states NEW → ACTIVE → IDLE → CLOSED; one request at a time (`ConnectionNotAvailable` otherwise); reuse requires full DONE/DONE h11 cycle + `start_next_cycle()`, else the connection is closed.
- `READ_NUM_BYTES = 64*1024` — socket read chunk size.
- `MAX_INCOMPLETE_EVENT_SIZE = 100*1024` — passed as h11 `max_incomplete_event_size`: caps buffered request/response line + headers (DoS guard), vs h11's own default of 16 KiB.
- `has_expired()` — keepalive timeout OR server-initiated disconnect detected via `is_readable` socket peek (select/poll, zero-timeout — no I/O cost).
- Handles `101` + `CONNECT 2xx` by returning the raw `network_stream` in extensions (`HTTP11UpgradeStream` preserves trailing bytes) — the WebSocket-upgrade escape hatch.
- Write errors mid-request are swallowed to still attempt reading the response (server may have answered with an error status).

### httpcore — HTTP/2 backend (`_sync/http2.py`, `_async/http2.py`, 592 lines each)

- `HTTP2Connection(origin, stream, keepalive_expiry)` — multiplexed streams, flow-control windows bumped by `2**24` on connect and per-stream, `ENABLE_PUSH=0`, `MAX_CONCURRENT_STREAMS=100` local / tracks server `RemoteSettingsChanged`. Requires the `h2` package — NOT INSTALLED, so `http2=True` raises `RuntimeError` at construction (both sync and async `__init__` stubs). DDGS's `http2=False` everywhere is therefore the only working setting today.

### httpcore — proxies (`http_proxy.py`, `socks_proxy.py`, both flavors)

- `HTTPProxy(proxy_url, proxy_auth, proxy_headers, ssl_context, proxy_ssl_context, …same pool knobs…)` — plain-http origins use `ForwardHTTPConnection` (absolute-URI request to proxy); https origins use `TunnelHTTPConnection` (CONNECT + `start_tls`, ALPN-aware, emits `ProxyError("STATUS reason")` on non-2xx). `proxy_ssl_context` is separate from origin `ssl_context` (and rejected for `http://` proxies).
- `SOCKSProxy` / `Socks5Connection` — `socks5`/`socks5h` schemes, NO_AUTH or USERNAME/PASSWORD via `socksio` — NOT INSTALLED, constructor raises `RuntimeError`. Dead code path for DDGS today.

### httpcore — network backends (`_backends/`)

- `NetworkBackend.connect_tcp(host, port, timeout, local_address, socket_options)` / `connect_unix_socket(path, timeout, socket_options)` / `sleep()`; `NetworkStream.read/write/close/start_tls/get_extra_info()`.
- `SyncBackend` — stdlib sockets; `SyncStream.get_extra_info()` keys: `"ssl_object"`, `"client_addr"`, `"server_addr"`, `"socket"` (raw socket — SO_KEEPALIVE/status escape hatch), `"is_readable"`. Includes `TLSinTLSStream` (MemoryBIO-based TLS-over-TLS for proxied HTTPS).
- `AnyIOBackend` / `TrioBackend` / `AutoBackend` — async variants; `AutoBackend` sniffs asyncio-vs-trio per call. Same `get_extra_info` keys on `AnyIOStream`.
- `MockBackend(buffer, http2=False)` / `MockStream` (+ async) — canned-bytes backend for offline tests.
- Timeout mapping is per-operation: connect → `ConnectTimeout`/`ConnectError`, read → `ReadTimeout`/`ReadError`, write → `WriteTimeout`/`WriteError`, pool wait → `PoolTimeout`; all under `TimeoutException` / `NetworkError` (`_exceptions.py`: 15 classes incl. `LocalProtocolError`/`RemoteProtocolError` mapped from h11 errors).
- Timeouts arrive per-request as `extensions["timeout"] = {"connect":…, "read":…, "write":…, "pool":…}` — exactly the dict `httpx.Timeout` builds.

### httpcore — Trace / telemetry (`_trace.py`)

- `Trace(name, logger, request, kwargs)` — if `request.extensions["trace"]` is set, calls `trace("loggerprefix.event", info)` with `event ∈ {connect_tcp, connect_unix_socket, start_tls, retry, send_request_headers, send_request_body, receive_response_headers, receive_response_body, response_closed, send_connection_init, receive_remote_settings, close}` each firing `.started` / `.complete` (with `return_value`) / `.failed` (with `exception`). Sync callbacks must be plain functions, async must be `async def` (TypeError otherwise). ALSO mirrors everything to `logging.DEBUG` on `httpcore.connection` / `httpcore.http11` / `httpcore.http2` / `httpcore.proxy` / `httpcore.socks` loggers — zero-code observability via log level alone.
- httpx reachability: httpx's `TimeoutExtension`/`TraceExtension`-style per-request extensions dict is forwarded verbatim to httpcore, so a `trace` (or httpx `event_hooks`, which wrap the same span points at a coarser level) passed on any DDGS `client.get/post(extensions={...})` call reaches these hooks with no transport change.

### h11 0.16.0 (pure-Python HTTP/1.1 state machine, 11 files)

- `Connection(our_role=CLIENT|SERVER, max_incomplete_event_size=16384)` — `send(event) -> bytes`, `send_with_data_passthrough()` (zero-copy/sendfile passthrough of `Data.data`), `receive_data(bytes)` (`b""` = EOF), `next_event() -> Event | NEED_DATA | PAUSED`, `start_next_cycle()` (keep-alive reuse, raises unless DONE/DONE), `trailing_data -> (bytes, closed)` (post-upgrade bytes), `send_failed()`, `states`/`our_state`/`their_state` properties.
- Events (`_events.py`): `Request(method, target, headers, http_version)` (HTTP/1.1 mandates Host; validates method/target chars), `Response(status_code≥200, headers, reason, http_version)`, `InformationalResponse(100–199; 101 drives protocol-switch)`, `Data(data, chunk_start, chunk_end)`, `EndOfMessage(headers=[])` — **TRAILERS SUPPORTED**: chunked-reader parses trailer headers into `EndOfMessage.headers`, chunked-writer emits them (`0\r\n` + headers); Content-Length + trailers = `LocalProtocolError`.
- Framing (`_readers.py`/`_writers.py`): content-length (with `read_eof` error on truncation), chunked (chunk extensions discarded; `read_eof` on mid-chunk EOF), http/1.0-until-EOF; `Expect: 100-continue` tracked (`client_is_waiting_for_100_continue`); obsolete line-folding tolerated; responses to HEAD / 204 / 304 / CONNECT-2xx forced to empty body.
- Limits: outbound `send()` always emits `HTTP/1.1` (raises otherwise); inbound status line tolerates missing reason phrase; `Content-Length` capped at 20 digits, conflicting values rejected; only `Transfer-Encoding: chunked` accepted (others → 501-hinted error); header line+block size capped by `max_incomplete_event_size` — httpcore raises it to 100 KiB; oversize → `RemoteProtocolError` with `error_status_hint=431`.
- `Headers` sequence type preserves raw casing (`raw_items()`) while comparing lowercase; state machine (`_state.py`): IDLE/SEND_RESPONSE/SEND_BODY/DONE/MUST_CLOSE/CLOSED/ERROR + MIGHT_SWITCH_PROTOCOL/SWITCHED_PROTOCOL for CONNECT/Upgrade; keep-alive auto-disabled on `Connection: close` or HTTP/1.0 (no HTTP/1.0 keep-alive support, by design).
- `error_status_hint` on every `ProtocolError` suggests the server response code for the failure — directly displayable in diagnostics.

---

## 2. LATENT CAPABILITIES FOR DDGS (ranked)

1. **`trace` extension → Diagnostics "Live Activity Terminal"** (zero new deps): pass `extensions={"trace": cb}` on router/health/catalog/stream calls; log `connect_tcp.started/complete`, `start_tls.*`, `send_request_headers.*`, `receive_response_headers.complete` (status+headers in `return_value`), `*.failed` (exception object). Gives per-call connect/TLS/TTFB breakdown in the existing terminal UI. Even cheaper first step: set `logging.DEBUG` on `httpcore.*` loggers — same span names, no code.
2. **Pool sizing for parallel tool fetches** (`httpx.Limits` → `max_connections` / `max_keepalive_connections`): DDGS builds a fresh `AsyncClient` per call site (defaults: 100 max, 20 keepalive) — rapid parallel tool/catalog fetches over one router origin multiplex over a single HTTP/1.1 connection sequentially; an explicit shared client with tuned `Limits` + `keepalive_expiry` removes per-call TCP+TLS setup. Confirm with `pool.connections` readout.
3. **`keepalive_expiry` tuning for rapid tool calls**: currently `None` (idle sockets held until server RST, then one failed reuse before recovery). A modest expiry (e.g. 30–60 s) matching the router's idle timeout avoids stale-socket hiccups on bursty tool traffic.
4. **`socket_options` → TCP keepalive for long kani streams** (`SO_KEEPALIVE`, `TCP_KEEPIDLE` via `(socket.SOL_SOCKET, socket.SO_KEEPALIVE, 1)` triples through `httpx` → pool): detects dead peers mid-SSE-stream instead of hanging a 180 s read timeout. Note: sync-backend only honors these reliably; anyio path ignores them (no-op loop) — verify on the async path before relying.
5. **Custom `ssl_context` for self-signed local routers** (`httpx.AsyncClient(verify=custom_ctx)` → pool `ssl_context` → `start_tls`): lets `ensure_router`/embedded-router HTTPS use a pinned local CA instead of certifi, complementing the `SSL_CERT_FILE` staging in `src/core/tls.py`. `sni_hostname` extension covers SNI edge cases.
6. **Granular per-phase timeouts already partially used — extend them**: kani leg sets `Timeout(180.0, connect=4.0)`; router probes pass `timeout=0.5/2.0` positionally (applies to ALL phases). Splitting probe timeouts (`connect=0.3, read=0.5, pool=1.0`) stops one slow port from eating the 11-port scan budget.
7. **HTTP/2 — NOT AVAILABLE, do not pursue**: needs `h2` package (absent; constructor raises `RuntimeError`). Even if added, router + OpenAI-compatible endpoints are HTTP/1.1; multiplexing gains ~zero for DDGS's sequential tool-call pattern. Same verdict for SOCKS (`socksio` absent).
8. **`pool.connections` + `Response.extensions["http_version"/"reason_phrase"]` for Diagnostics**: live connection-state readout and exact reason phrases without extra requests. `network_stream` extension also enables future CONNECT-tunnel/Upgrade features (e.g. WebSocket transport) with no new dependency.

## 3. GOTCHAS

- **Retry ownership**: httpcore `retries` (default 0) retries ONLY TCP/TLS establishment with 0/0.5/1/2…s backoff — never HTTP 5xx/429, never request replays. DDGS's "two retries" on the kani leg live one layer up in `openai.AsyncOpenAI(max_retries=2)`; httpx itself never retries. Do not expect idempotent-request retry from this stack; do not raise httpcore `retries` to fix 5xx flakiness (it only slows connect storms).
- **Import boundary**: `httpcore`/`h11` are httpx internals — DDGS must configure them exclusively via `httpx.AsyncClient(limits=Limits(...), timeout=Timeout(...), verify=..., transport=...)` and per-request `extensions={...}`. Direct `import httpcore/h11` in app code couples DDGS to httpx's private transport contract.
- **Extension-key contract**: `timeout` dict keys are exactly `connect/read/write/pool`; `trace` callback must be `async def` on the async path (sync function → `TypeError` at first span).
- **No HTTP/2 without `h2`, no SOCKS without `socksio`** — both raise `RuntimeError` at construction, not import; `http2=False` (current) is the only safe setting.
- **h11 limits**: no HTTP/1.0 keep-alive (downgraded to close), outbound always HTTP/1.1, chunk extensions silently dropped, `Content-Length`+trailers illegal, header block capped (100 KiB via httpcore) with 431-hinted errors on overflow.
- **`socket_options` async caveat**: honored by `SyncBackend`, silently skipped by `AnyIOBackend` — DDGS's all-async traffic means keepalive tuning via this knob needs verification, not assumption.
- **Single-use response streams**: `iter_stream()`/`aiter_stream()` raise on second iteration; `ThoughtTapTransport` must tee, never re-iterate.
- **Android CA interplay** (`src/core/tls.py`): httpx resolves `SSL_CERT_FILE` at CLIENT CONSTRUCTION — any custom `verify=` context for local routers must be built after `ensure_ca_bundle()` runs, or the staged bundle path is bypassed.

## 4. COVERAGE

- **httpcore 1.0.9: 31 / 31 `.py` files read** (8 root: `__init__`, `_api`, `_exceptions`, `_models`, `_ssl`, `_synchronization`, `_trace`, `_utils`; 8 `_sync`; 8 `_async` — `connection_pool`, `http11`, `http_proxy`, `socks_proxy`, `http2` verified line-identical to sync via diff, `connection`/`interfaces`/`__init__` read fully; 7 `_backends`: `base`, `sync`, `mock`, `auto`, `anyio`, `trio`, empty `__init__`). `__pycache__` excluded.
- **h11 0.16.0: 11 / 11 `.py` files read** (`__init__`, `_abnf`, `_connection`, `_events`, `_headers`, `_readers`, `_receivebuffer`, `_state`, `_util`, `_version`, `_writers`).
- DDGS consumer surface sampled: `src/services/reasoning.py` (`ThoughtTapTransport`, `build_thought_client`), `kani_backend.py` (engine timeouts/retries), `ai_service.py` (router probes, `http2=False`), `core/tls.py` (CA staging), `license_service.py`, plus `httpx` client-construction grep across `src/`.
- Environment confirmed: `h2` absent, `socksio` absent, `trio` absent; `anyio`/`sniffio`/`certifi`/httpx 0.28.1 present.
