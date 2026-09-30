# Dependency audit — openai client core (v2.54.0)

Scope: the HTTP/SDK layer under kani for DDGS. DDGS builds one
`openai.AsyncOpenAI` per turn (`src/services/kani_backend.py::_build_engine`):
`api_key="any"`, router `base_url`, custom `http_client` (ThoughtTap
transport), `max_retries=2`, `timeout=httpx.Timeout(180.0, connect=4.0)`.
Kani sends `model`, `messages`, `tools`, `temperature`, `stream=True` with
`stream_options={"include_usage": True}` and maps `APIStatusError` /
`APIConnectionError` / `APIError` to app errors.

Package path: `.venv/Lib/site-packages/openai/` (Stainless/Castiron-generated).

---

## 1. COMPLETE API INVENTORY

### 1.1 Constructor — `OpenAI` / `AsyncOpenAI` (`_client.py`)

Every param (identical on both unless noted):

- `api_key: str | Callable | None` — sync accepts `str | Callable[[], str]`;
  async accepts `str | Callable[[], Awaitable[str]]`. A callable is invoked
  per-request (dynamic rotation without rebuilding the client). Falls back to
  `OPENAI_API_KEY`. DDGS passes `"any"`.
- `admin_api_key: str | None` — env `OPENAI_ADMIN_KEY`. Selects the admin
  bearer header on admin routes only.
- `workload_identity: WorkloadIdentity | None` — OAuth token-exchange auth
  (`auth/_workload.py`): `{identity_provider_id, service_account_id,
  provider: {token_type: "jwt"|"id", get_token}, refresh_buffer_seconds?}`
  (default refresh 1200 s). Token cached, auto-refreshed, single 401 retry
  with invalidation. Providers included: `k8s_service_account_token_provider`,
  `azure_managed_identity_token_provider` (Azure IMDS). Mutually exclusive
  with `api_key`.
- `organization: str | None` — env `OPENAI_ORG_ID`; sent as
  `OpenAI-Organization` header (omitted via `Omit()` when None).
- `project: str | None` — env `OPENAI_PROJECT_ID`; sent as `OpenAI-Project`.
- `webhook_secret: str | None` — env `OPENAI_WEBHOOK_SECRET`; used for
  webhook signature verification (`InvalidWebhookSignatureError` otherwise).
- `provider: _Provider | None` — opaque handle from an OpenAI-owned provider
  factory. The ONLY factory in this version is Bedrock (`providers/bedrock.py`
  + `lib/bedrock.py`, incl. legacy-client shims). Mutually exclusive with
  `api_key`, `admin_api_key`, `workload_identity`, `base_url` (raises
  `OpenAIError`). A provider supplies base_url + request/response transforms
  (`_ProviderRuntime`: transform/prepare/normalize hooks).
- `base_url: str | httpx.URL | None` — env `OPENAI_BASE_URL`, default
  `https://api.openai.com/v1`. Trailing slash enforced; settable post-hoc
  (`client.base_url = ...`).
- `websocket_base_url: str | httpx.URL | None` — base for Realtime WebSocket
  connections only (`wss://` derived from `base_url` when unset). NOTE: there
  is NO `websocket_options` param on the constructor in 2.54.0 despite what
  older docs suggest; chat streaming is SSE-over-HTTP and needs nothing here.
- `timeout: float | httpx.Timeout | None | NotGiven` — default
  `httpx.Timeout(600, connect=5.0)` (`_constants.DEFAULT_TIMEOUT`).
  `None` DISABLES timeouts entirely. See Gotchas for the http_client-adoption
  quirk. Per-request override on every method.
- `max_retries: int` — default 2 (`DEFAULT_MAX_RETRIES`). `None` raises
  `TypeError`; `math.inf`/huge number = unlimited. Per-request override via
  `RequestOptions.max_retries` (also `max_retries` on raw `client.get/post`).
- `default_headers: Mapping[str,str] | None` — merged under
  `Accept/Content-Type/User-Agent` + platform headers + org/project headers;
  per-request `extra_headers` win. Also merged with `OPENAI_CUSTOM_HEADERS`
  env (`"Name: value"` per line).
- `default_query: Mapping[str,object] | None` — merged into every query string.
- `http_client: httpx.Client | httpx.AsyncClient | None` — custom transport
  (DDGS passes its ThoughtTap client here). Must be an `httpx` (or `httpx2`)
  client instance or `TypeError`. SDK does NOT copy it; `client.close()`
  closes it. `DefaultHttpxClient`/`DefaultAsyncHttpxClient` exported to keep
  SDK defaults (`limits 1000/100 keepalive`, `follow_redirects=True`);
  experimental `DefaultHttpx2Client` variants in `_httpx2.py` (needs
  `pip install openai[httpx2]`, Python 3.10+).
- `_strict_response_validation: bool` — raise `APIResponseValidationError`
  when the router returns schema-invalid data (default False: lenient
  `construct_type`).
- `_enforce_credentials: bool` — raise when no credential at all is found.
- `copy()` / `with_options` — clone with replacements; `default_headers` vs
  `set_default_headers` (merge vs replace, mutually exclusive); same for
  `default_query`/`set_default_query`; also `api_key`, `organization`,
  `project`, `base_url`, `websocket_base_url`, `timeout`, `http_client`,
  `max_retries`.
- `with_raw_response` / `with_streaming_response` — mirror namespaces
  returning `APIResponse` wrappers (status/headers/`retries_taken`) or
  streaming context managers that guarantee close on leak.
- Lifecycle: `close()` / `is_closed()` / `with client:` (sync) and
  `aclose()` / `async with` (async). The wrapper auto-closes on GC but
  explicit close is required for clean shutdown.
- Module-level lazy proxies (`_module_client.py`): `openai.chat`,
  `openai.files`, `openai.responses`, … bound to an env-configured default
  client — irrelevant for DDGS (explicit client), but `openai._load_client`
  exists.
- Env-var summary: `OPENAI_API_KEY`, `OPENAI_ADMIN_KEY`, `OPENAI_ORG_ID`,
  `OPENAI_PROJECT_ID`, `OPENAI_WEBHOOK_SECRET`, `OPENAI_BASE_URL`,
  `OPENAI_CUSTOM_HEADERS`.

### 1.2 `client.chat.completions.create` — full parameter surface

(`resources/chat/completions/completions.py`; `parse()` = same + typed
`response_format`; `stream()` manager = same, returns typed event stream.)

- `messages: Iterable[ChatCompletionMessageParam]` — system/developer/user/
  assistant/tool/function message dicts; content may be text or multimodal
  part lists (text/image/input_audio/file).
- `model: str | ChatModel` — any string (router model ids pass through).
- `stream: bool` — SSE `ChatCompletionChunk` stream (`Stream`/`AsyncStream`).
  Retry loop runs BEFORE the body streams; mid-stream errors raise, no retry.
- `stream_options: {include_usage?: bool, include_obfuscation?: bool}` —
  `include_usage` appends a final chunk with `usage` (choices=[]); all earlier
  chunks carry `usage=None`. If the stream is interrupted the usage chunk may
  NEVER arrive — always code for `usage=None`. `include_obfuscation` pads
  chunk sizes against side-channel analysis (bandwidth cost).
- `tools: Iterable[ChatCompletionToolUnionParam]` — `function` tools
  (`{name, description, parameters, strict}`), `custom` tools, allowed-tools.
- `tool_choice: "none"|"auto"|"required"|AllowedToolChoice|NamedToolChoice|NamedCustom` —
  `none` = never call, `auto` = model decides, `required` = must call,
  named/allowed = force a specific tool or subset.
- `parallel_tool_calls: bool` — allow multiple tool calls per turn.
- `response_format: {type:"text"} | {type:"json_object"} | {type:"json_schema",
  json_schema:{name, schema, strict?}}` — `json_schema`+`strict:true` =
  Structured Outputs (guaranteed schema). `.parse()` overload accepts a
  `pydantic.BaseModel`/dataclass TYPE instead and returns
  `ParsedChatCompletion[T]` (`.message.parsed`, per-tool-call
  `.parsed_arguments`); raises `LengthFinishReasonError` /
  `ContentFilterFinishReasonError` instead of returning truncated content.
- `temperature: float` (0–2), `top_p: float` — sampling. `seed: int | None` —
  best-effort determinism (Beta). `stop: str | list[str] | None` — NOT
  supported on o3/o4-mini reasoning models.
- `max_tokens: int | None` — DEPRECATED in favour of `max_completion_tokens`.
- `max_completion_tokens: int | None` — cap incl. reasoning tokens.
- `n: int | None` — N choices per message (cost × N; streaming + n>1 yields
  per-index deltas).
- `logprobs: bool | None` + `top_logprobs: int (0–20)` — per-token log probs
  on completion AND streamed chunks (`choice.logprobs.content[]` =
  `{token, logprob, bytes, top_logprobs[]}`).
- `presence_penalty / frequency_penalty: float` (−2…2).
- `logit_bias: dict[str,int]` — token-id → −100…100 bias.
- `reasoning_effort: "none"|"minimal"|"low"|"medium"|"high"|"xhigh"|"max" | None` —
  reasoning-token budget on reasoning models.
- `verbosity: "low"|"medium"|"high" | None` — output verbosity knob.
- `modalities: ["text","audio"] | None` + `audio: {voice, format}` — audio
  output (helpers `helpers/local_audio_player.py`, `helpers/microphone.py`
  stream mic/PCM; need numpy/sounddevice extras).
- `prediction: {content}` — static predicted content (e.g. file being edited)
  for latency discount.
- `web_search_options: {search_context_size?: "low"|"medium"|"high",
  user_location?: {type:"approximate", approximate:{city?, country?,
  region?, timezone?}}}` — native search grounding + locale.
- `service_tier: "auto"|"default"|"flex"|"scale"|"priority"|"fast" | None` —
  processing tier (echoed back on response/chunks).
- `store: bool | None` — persist completion server-side (enables
  `chat.completions.messages.list(completion_id, after, limit, order)` audit
  trail, `Sync/AsyncCursorPage`).
- `metadata: dict (≤16 kv)` — server-side analytics tags.
- `prompt_cache_key: str` + `prompt_cache_options: {ttl?}` (gpt-5.6+) —
  explicit prefix-cache control; `prompt_cache_retention` DEPRECATED →
  `prompt_cache_options.ttl`.
- `safety_identifier: str` — stable per-user id (abuse detection; replaces
  `user`, which is deprecated along with free-form `user: str`).
- `moderation: {input?: policy, output?: policy}` — run moderation inline;
  results echoed on the response/chunk (`moderation` field).
- `function_call` / `functions` — DEPRECATED → `tool_choice`/`tools`.
- `extra_headers / extra_query / extra_body` — per-request escape hatches;
  `extra_body` merges INTO the JSON payload (router-specific fields without
  SDK upgrade); extras beat client-level and method-level values.
- `timeout: float | httpx.Timeout | None | NotGiven` — per-request timeout
  (e.g. 30 s for `models.list`, 180 s for chat).

Related: `completions.stream()` → `ChatCompletionStreamManager` — typed
events (`ChunkEvent`, `ContentDelta/Done`, `RefusalDelta/Done`,
`FunctionToolCallArgumentsDelta/Done`, `Logprobs*Delta/Done`),
`current_completion_snapshot`, `get_final_completion()`;
`ChatCompletionStreamState` for manual accumulation when kani owns the loop.

### 1.3 Streaming types (`types/chat/chat_completion_chunk.py`)

`ChatCompletionChunk`: `id`, `choices[]`, `created`, `model`, `object`,
`service_tier?`, `system_fingerprint?`, `usage: CompletionUsage | None`
(FINAL chunk only, and only with `include_usage`),
`moderation*?` (when moderation requested).
`Choice`: `index`, `delta: {role?, content?, refusal?, function_call?
(deprecated), tool_calls?: [{index, id?, type, function:{name?, arguments
accumulated}}]}`, `finish_reason:
"stop"|"length"|"tool_calls"|"content_filter"|"function_call"|None`,
`logprobs?: {content[]: {token, logprob, bytes, top_logprobs[]}, refusal[]}`.
No first-class `reasoning`/`annotations` fields in 2.54.0 — router-specific
stream fields survive because `BaseModel` uses `extra="allow"`, which is how
the ThoughtTap sees reasoning bytes today. Non-stream `ChatCompletion` adds
`message: {role, content, refusal, tool_calls, function_call?, annotations?}`
and full `usage`.

### 1.4 Exceptions hierarchy (`_exceptions.py`)

- `OpenAIError(Exception)` — root.
  - `APIError` — `message`, `request: httpx.Request`, `body` (decoded JSON or
    raw text or None), `code?`, `param?`, `type?`. ALSO raised for mid-stream
    SSE error payloads (no retry possible there).
    - `APIResponseValidationError` — +`response`, `status_code` (strict mode
      or `response_format` mismatch).
    - `APIStatusError` — +`response`, `status_code`,
      `request_id` (from `x-request-id` header — quote it in router bug
      reports).
      - `BadRequestError` 400 · `AuthenticationError` 401 (→ `OAuthError`
        +`error: OAuthErrorCode` for token-exchange failures) ·
        `PermissionDeniedError` 403 · `NotFoundError` 404 ·
        `ConflictError` 409 · `UnprocessableEntityError` 422 ·
        `RateLimitError` 429 · `InternalServerError` (any 5xx).
    - `APIConnectionError` (DNS/reset/refused — RETRYABLE) → child
      `APITimeoutError` (RETRYABLE).
  - `SubjectTokenProviderError` (+`response?`) — workload-identity fetch
    failures (k8s/Azure helpers).
  - `LengthFinishReasonError` (+`completion`) — only from `.parse()`/stream
    helpers, NOT from plain `create()`. `ContentFilterFinishReasonError` —
    same provenance.
  - `InvalidWebhookSignatureError(ValueError)`.
  - `WebSocketConnectionClosedError` (+`unsent_messages`) /
    `WebSocketQueueFullError` — Realtime only (bounded 1 MiB `SendQueue`).
  - `APIRemovedInV1` (`lib/_old_api.py`: `Completion`, `ChatCompletion`,
    `Engine`, … raise with migration instructions).

### 1.5 Retries / timeouts (`_base_client.py`, `_constants.py`)

- Retryable: transport exceptions (incl. timeouts), HTTP 408, 409, 429,
  ≥500. NOT retried: other 4xx, `Retry-After` > 120 s
  (`MAX_RETRY_AFTER_DELAY`), `x-should-retry: false`; `x-should-retry: true`
  FORCES a retry on any status.
- Delay honor: `retry-after-ms` → `Retry-After` (float seconds accepted) →
  HTTP-date; capped at 120 s, then exponential
  `min(0.5 * 2^attempt, 8.0)` with ±25% jitter (`INITIAL_RETRY_DELAY=0.5`,
  `MAX_RETRY_DELAY=8.0`).
- Loop runs `max_retries + 1` total attempts; fresh request rebuilt per
  attempt; same auto `stainless-python-retry-<uuid4>` idempotency key reused
  across retries (non-GET only). Headers `x-stainless-retry-count`,
  `x-stainless-read-timeout` auto-set (suppressible via explicit headers).
- Retry loop is REQUEST-level: once streaming starts there are no retries.
  httpx itself never retries — the `max_retries` on `build_thought_client`
  is intentionally inert (see its docstring); only
  `AsyncOpenAI(max_retries=…)` matters.
- Defaults: `DEFAULT_TIMEOUT = Timeout(600, connect=5.0)`,
  `DEFAULT_CONNECTION_LIMITS = Limits(1000, max_keepalive 100)`.

### 1.6 Pagination (`pagination.py`)

`SyncPage/AsyncPage` (no real paging, forwards-compat) ·
`Sync/AsyncCursorPage` (`after` = last item id; honours `has_more=false`) ·
`Sync/AsyncConversationCursorPage` (`after` = `last_id`) ·
`Sync/AsyncNextCursorPage` (`after` = `next`). `iter_pages()`,
`get_next_page()`, `has_next_page()`, item iteration (async variant
awaitable + `async for`). Used by `models/files/messages/input_items` lists.

### 1.7 Files API (`resources/files.py`)

`create(file, purpose)` (`purpose`: assistants/fine-tune/batch/eval),
`retrieve`, `list(purpose?, order?, after?)` (cursor pages),
`delete`, `content` / `retrieve_content` (binary download),
`wait_for_processing(id)` — polls until `status == "processed"`.
Accepts bytes/paths/streams (`_files.py` multipart handling).

### 1.8 Responses API (`resources/responses/responses.py` + subresources)

`responses.create`: `input` (str or item list), `instructions`, `model`,
`stream`, `stream_options`, `tools`, `tool_choice`, `temperature`, `top_p`,
`top_logprobs`, `max_output_tokens`, `max_tool_calls`, `parallel_tool_calls`,
`reasoning: {effort, summary}`, `text: {format}` (structured output),
`truncation`, `background` (async jobs), `store`, `conversation` /
`previous_response_id` (server-side multi-turn chaining),
`include[]`, `prompt` (prompt-template id), `prompt_cache_key/options/
retention`, `safety_identifier`, `service_tier`, `metadata`, `moderation`,
`user`, + `extra_*`/`timeout`.
`responses.parse()` (pydantic text-format parsing), `responses.stream()`
(`ResponseTextDelta/Done`, `ResponseFunctionCallArgumentsDelta`,
`ResponseCompleted` events), `responses.input_items.list`, and
`responses.input_tokens.count(...)` — PRE-FLIGHT token counting without
calling the model.

### 1.9 Auth helpers (`auth/`)

See constructor `workload_identity`. `WorkloadIdentityAuth` handles caching +
401-refresh; `SubjectTokenProviderError` on fetch failure. Plain Bearer/admin
headers assembled per-request from client state (provider mode sends none).

### 1.10 Event handlers / callbacks (`_event_handler.py`, `lib/streaming/`)

`EventHandlerRegistry`: `add(event, handler, once?)`, `remove`,
`get_handlers`, `has_handlers`, `merge_into` — the callback bus for the
Realtime WebSocket layer, NOT wired into chat completions. Chat-side
equivalents: `.stream()` typed events (above) + `with_raw_response` /
`with_streaming_response` hooks + `post_parser` (`FinalRequestOptions`).
No request/response middleware hook exists on the chat path.

### 1.11 Providers system (`_provider.py`, `providers/`, `lib/azure.py`, `lib/bedrock.py`)

`_Provider` is an opaque capability token: factories build a
`_ProviderDefinition` (`name` + `configure() → _ProviderRuntime` with
request/response transform + auth hooks); only Bedrock ships one
(`providers/bedrock.py`; `BedrockOpenAI` in `lib/bedrock.py`, AWS SigV4 via
bearer env/region). Azure is a parallel subclass family
(`AzureOpenAI/AsyncAzureOpenAI`: `api_version`, `azure_endpoint`,
`azure_deployment`, `api_key`/AD token, per-deployment `copy()`). A local
OpenAI-compatible router needs NEITHER — plain `base_url` is the supported
path, which is what DDGS does.

### 1.12 Misc worth knowing

- `_qs.py`: default array format `repeat`; the chat client uses `brackets`.
- `_response.py`: `APIResponse.parse(to=…)` (cached per type), `.request_id`,
  `.retries_taken`, `.elapsed`, `iter_bytes/iter_text/iter_lines`.
- `lib/_tools.py::pydantic_function_tool(Model)` — strict function tool from
  a pydantic model (name/description inferred); auto-parsed by `.parse()`.
- `lib/_pydantic.py::to_strict_json_schema` — reuse for hand-rolled schemas.
- `resources/models.py`: `list` (sync-paged + async), `retrieve`, `delete`
  — DDGS already uses `GET /models` for health.
- `chat.completions.messages.list` — stored-completion audit (needs
  `store=True`).

---

## 2. LATENT CAPABILITIES FOR DDGS (ranked by UX impact)

DDGS today sends: model/messages/tools/temperature/stream(+usage flag). Kani
reads usage internally for cache bookkeeping but DDGS never sees token
counts; `tool_choice` is kani-default (`auto`, `none` only to disable);
everything below is SDK-supported and unused.

1. **`stream_options.include_usage` receipts → exact credit billing.**
   Kani already requests the final usage chunk; DDGS discards it.
   Accumulate the terminal `chunk.usage` per step (guard `None` — interrupted
   streams never deliver it) and bill `prompt/completion/cached/reasoning`
   tokens in `credit_service` instead of the heuristic tokenizer. Highest
   value: billing correctness for a downloads+assistant app, zero extra
   requests. Fallback to the current heuristic when `usage` is absent (local
   routers often omit it).
2. **Structured outputs (`response_format=json_schema` / `.parse()` +
   `pydantic_function_tool`).** Force the model to emit valid JSON for:
   download-metadata extraction (title/size/format candidates), search-query
   planning (multi-query fan-out), and settings-like answers. Strict tools
   also give `parsed_arguments` for free — removes an entire class of
   `JSON.parse` crashes in the tool loop. Use per-call (kani forwards
   `**hyperparams` → `create()`), not globally, so free chat stays natural.
3. **`tool_choice` steering per turn.** `required` when the user intent
   clearly needs search/downloads ("find me…", "download…") — kills the
   "chatty refusal instead of searching" failure mode; `none` for pure
   chit-chat/follow-ups to cut latency and cost; named choice to pin a flaky
   model to the right tool. One-line change at engine-construction or per
   `run_turn` intent.
4. **Prompt caching (`prompt_cache_key` + `store` + `metadata`).** The system
   prompt + tool specs are identical every turn — a stable `prompt_cache_key`
   (bump on app version) lets the router reuse the prefix (latency + cost).
   `metadata` (16 kv: turn id, app version, model) and `store=True` give
   server-side analytics and make `messages.list` a turn replay/audit log.
5. **Honor the app proxy for assistant traffic.** DDGS has proxy settings
   (search path uses them); `build_thought_client` builds a bare
   `httpx.AsyncClient`. Pass `proxy=` (or `mounts=`) from app settings into
   that client so users behind corporate proxies get a working assistant.
   Same edit point can set per-request `timeout` (fast 30 s for health/model
   list vs 180 s chat).
6. **`extra_body` / `extra_headers` for the router.** LM Router/kiri
   extensions (routing hints, tier selection, debug flags) can be sent
   without waiting for an SDK upgrade; per-turn diagnostic headers
   (`X-DDGS-Turn`, attempt count) correlate app logs with `x-request-id`
   (available as `exc.request_id` and `response.request_id`).
7. **`reasoning_effort` + `verbosity` knobs per model tier.** Free-catalog
   reasoning models burn tokens thinking; expose effort (low for quick
   answers, high for research mode) next to the existing temperature setting.
   The ThoughtTap already surfaces the thinking — this controls its cost.
8. **`seed` + `stop` for reproducibility/debuggability.** `seed` for a
   deterministic debug mode; `stop` sequences to fence assistant output
   (e.g. stop before leaking prompt scaffolding). Cheap, low risk.
9. **`logprobs` confidence gating.** Show/emphasize sources when top-token
   confidence is low ("uncertain — verify with sources"), or auto-retry with
   search grounding. Small payload cost; only enable on demand.
10. **`client.copy()` / `with_options` + `default_headers`.** Per-turn client
    variants (diagnostic headers, different timeout) without rebuilding the
    ThoughtTap transport; `set_default_headers` vs merge semantics are
    explicit.
11. **`responses.input_tokens.count` pre-flight.** Replace/augment the
    heuristic tokenizer with an exact count before sending, to enforce
    `DEFAULT_CONTEXT` trims deterministically.
12. **Files API (`create` + `wait_for_processing`).** "Ask about this
    document" UX: user attaches a file, assistant gets it as context.
    Depends on router support; probe before building UI.
13. **`n>1` candidate answers.** Parallel drafts for comparison UX — ranked
    last: multiplies cost, niche benefit.
14. **Native `web_search_options` / `moderation` / audio modalities.** Only if
    the router implements them; DDGS owns search + downloads already, so
    these duplicate in-app strengths. Probe, don't assume.

---

## 3. GOTCHAS

- **No `websocket_options` exists** — the constructor param is
  `websocket_base_url`, Realtime-only. Chat streaming is SSE over plain HTTP.
- **Timeout layering.** Three actors: (a) the raw httpx client DDGS builds,
  (b) the SDK-level `timeout`, (c) per-request `timeout`. If `timeout` is left
  `NotGiven` AND the custom http_client has a non-default timeout, the SDK
  silently ADOPTS the http_client's timeout (structural comparison against
  httpx defaults — an explicitly-set value that happens to equal the default
  is misread as "not set"). DDGS sets the same `Timeout(180, connect=4.0)`
  in both places, so it is consistent today — but change only one side and
  behavior follows the SDK side (passed per-request into
  `build_request(timeout=…)`). `timeout=None` anywhere DISABLES timeouts.
  `x-stainless-read-timeout` echoes the resolved read timeout per attempt.
- **Streaming retries end where the body begins.** The retry loop covers
  connection setup + status errors only. A failure mid-SSE raises `APIError`
  with no retry — hence `_raise_mapped`'s `delivered`/`AIMidStream` split is
  load-bearing; do not "fix" it by raising retryable errors after tokens.
- **`max_retries` lives on the SDK, not the transport.** httpx never retries;
  `build_thought_client(max_retries=…)` is documented-inert. Attempts =
  `max_retries + 1`. Router `Retry-After` (incl. `retry-after-ms` and HTTP
  dates) is honored up to 120 s, then NOT retried — a long router cooldown
  surfaces as `RateLimitError`, which `_raise_mapped` already words as "busy".
- **Deprecations that 400 on some routers:** `max_tokens` →
  `max_completion_tokens`; `functions`/`function_call` → `tools`/`tool_choice`;
  `user` → `safety_identifier` + `prompt_cache_key`; `prompt_cache_retention`
  → `prompt_cache_options.ttl`. Reasoning models (o3/o4-mini class) reject
  `stop` and sometimes pin `temperature` — guard these per model family.
- **`http_client` interacts with everything.** The SDK never copies it:
  `client.close()` closes YOUR transport; a per-turn engine that never closes
  leaks connections (verify `aclose` on the turn path). Custom headers on the
  raw client merge UNDER SDK/per-request headers. `base_url` trailing slash
  is enforced and relative paths merge — the ThoughtTap client correctly
  leaves `base_url` to the SDK wrapper.
- **Lenient parsing is a feature for routers.** Strict validation is OFF by
  default and `BaseModel(extra="allow")` preserves unknown fields — that is
  WHY router-specific reasoning deltas reach the ThoughtTap. Do not enable
  `_strict_response_validation` globally; it would turn router extensions
  into crashes.
- **`store=True` has a paper trail.** It persists completions server-side
  (listable via `messages.list`) — right for audit, wrong for private chats.
  Keep it opt-in per conversation type.

---

## 4. COVERAGE

41 files read in full; 5 read substantially (remainder is the sync/async
mirror or generation boilerplate); `_utils/` (12 files) + `_validators.py`
skimmed via targeted grep as instructed.

- Full: `_exceptions.py`, `_constants.py`, `_resource.py`, `_provider.py`,
  `_event_handler.py`, `_send_queue.py`, `_qs.py`, `_files.py`, `_httpx2.py`,
  `_module_client.py`, `_streaming.py`, `pagination.py`, `_types.py`,
  `_compat.py`, `lib/_parsing/_completions.py`, `lib/_tools.py`,
  `lib/_old_api.py`, `lib/streaming/chat/_events.py`,
  `types/chat/chat_completion_chunk.py`,
  `types/chat/chat_completion_stream_options_param.py`,
  `types/chat/chat_completion_tool_choice_option_param.py`,
  `types/chat/completion_create_params.py` (key sections),
  `types/completion_usage.py`, `types/shared/reasoning_effort.py`,
  `resources/chat/chat.py`, `resources/chat/completions/completions.py`
  (signature + all param docs), `resources/chat/completions/messages.py`
  (signature), `resources/files.py` + `resources/models.py` (method index),
  `resources/responses/input_items.py` + `input_tokens.py` (method index),
  `resources/responses/responses.py` (`create` param surface),
  `auth/__init__.py`, `helpers/__init__.py`, `providers/__init__.py`,
  `__init__.py` (exports), `_version.py`.
- Substantial: `_client.py` (both constructors, auth, copy, raw/streaming
  wrappers; per-resource accessors skimmed), `_base_client.py` (request
  build, retry loop, sync client; async mirror assumed identical),
  `_response.py` (APIResponse surface; async mirror skimmed),
  `_models.py` (`BaseModel` + `FinalRequestOptions`; validators skimmed),
  `lib/streaming/chat/_completions.py` (stream manager/state API),
  `auth/_workload.py` (types + providers; token-refresh internals skimmed),
  `_legacy_response.py` (class surface; method bodies skimmed).
- Skimmed: `_utils/` internals, `lib/_validators.py` (fine-tune CSV
  validators — N/A to chat), `lib/azure.py` + `lib/bedrock.py` +
  `providers/bedrock.py` (method index only — N/A to local router),
  `helpers/local_audio_player.py` + `helpers/microphone.py` (headers only),
  `lib/_realtime.py`, `lib/_parsing/_responses.py`,
  `lib/streaming/responses/*` (class/function index).
- Cross-checked: `src/services/kani_backend.py`, `src/services/reasoning.py`
  (ThoughtTap transport + `build_thought_client`), kani
  `engines/openai/engine.py` (`_predict/_stream_chat_completions` — confirms
  `stream_options include_usage` already sent, usage discarded by DDGS),
  `src/services/ai_service.py`, `credit_service.py` (no usage-token billing).
