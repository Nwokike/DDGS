# openai — Beyond Chat Audit (for DDGS)

- Package version audited: **2.54.0** (`_version.py`)
- Install location: `C:\Users\nwoki\.zcode\workspace\default\DDGS\.venv\Lib\site-packages\openai\`
- Consumer today: DDGS (`C:\Users\nwoki\.zcode\workspace\default\DDGS`) streams only `/chat/completions` via kani (`src/services/kani_backend.py` → `import openai`) against a local router.
- Date: 2026-09-29

---

## 1. INVENTORY

### 1.1 `lib/_parsing` — structured-output / tool-call parsers

`lib/_parsing/_completions.py` (288 lines, read fully):

- `parse_chat_completion(*, response_format, input_tools, chat_completion) -> ParsedChatCompletion` — walks every choice, raises `LengthFinishReasonError` / `ContentFilterFinishReasonError`, attaches `message.parsed` + per-tool-call `parsed_arguments`. Could DDGS reuse it for OTHER providers' raw output? **Yes, partially**: it operates on a `ChatCompletion` pydantic object, not raw JSON text — any OpenAI-compatible router response can be coerced with `ChatCompletion.model_validate(dict)` and then parsed. Genuinely foreign schemas (Anthropic, Gemini-native) would need an adapter first.
- `parse_function_tool_arguments(*, input_tools, function) -> object | None` — resolves tool by name, `json.loads` for strict tools, `model_parse_json` for `PydanticFunctionTool`.
- `maybe_parse_content(*, response_format, message) -> T | None` — parses `message.content` into a BaseModel/dataclass via `model_parse_json` / `TypeAdapter.validate_json`.
- `type_to_response_format_param(response_format) -> ResponseFormatParam` — turns a `BaseModel`/dataclass type into a `{"type":"json_schema","json_schema":{...,"strict":True}}` dict via `to_strict_json_schema`.
- `has_parseable_input / has_rich_response_format / is_parseable_tool / validate_input_tools / select_strict_chat_completion_tools` — guards; only `type=="function"` + `strict:true` tools are parseable.
- `pydantic_function_tool(model, *, name, description)` (in `lib/_tools.py`) — builds a strict function-tool dict from a `BaseModel` (name/docstring inferred).

`lib/_parsing/_responses.py` (187 lines, read fully): same idea for the Responses API — `parse_response(*, text_format, input_tools, response)`, `parse_text`, `type_to_text_format_param`, `parse_function_tool_arguments`. Pass-through list covers ~30 output types (`computer_call`, `file_search_call`, `web_search_call`, `mcp_call`, `image_generation_call`, `code_interpreter_call`, `shell_call`, `apply_patch_call`, …).

### 1.2 Chat streaming helpers (`lib/streaming/chat/`)

- `ChatCompletionStream` — `__next__/__iter__`, `get_final_completion()`, `until_done()`, `current_completion_snapshot()`, `close()`; accumulates deltas into a `ParsedChatCompletionSnapshot` and fires typed stream events (`ChatCompletionStreamEvent`).
- `ChatCompletionStreamManager` — context manager returned by `client.chat.completions.stream(...)`.
- `AsyncChatCompletionStream / AsyncChatCompletionStreamManager` — async mirrors.
- `ChatCompletionStreamState.handle_chunk(chunk)` — per-choice delta accumulation incl. tool-call argument stitching.
- `lib/streaming/responses/` — same pattern for Responses API (`ResponseStreamManager`, `ResponseStreamState`).
- `lib/streaming/_assistants.py` (`AssistantEventHandler`, 1041 lines) — `on_event`, `on_text_delta`, `on_tool_call_*`, `on_run_step_*`, `get_final_run/run_steps/messages`, `until_done()`, `__text_deltas__()`.
- Core transport (`_streaming.py`, 427 lines, read fully): `Stream[T] / AsyncStream[T]` (SSE iteration, `[DONE]` handling, `thread.*` special-case, `APIError` on `error` payload), `SSEDecoder` (spec-compliant `event/data/id/retry` parsing), `ServerSentEvent.json()`.

### 1.3 Event-handler / realtime plumbing

- `_event_handler.py` (85 lines, read fully — note: this file is a small `EventHandlerRegistry`, NOT the assistants handler): `add(event_type, handler, *, once)`, `remove`, `get_handlers` (consumes once-handlers), `has_handlers`, `merge_into(target)`. Thread-safe iff `use_lock=True`.
- `resources/realtime/realtime.py`: `AsyncRealtimeConnection.parse_event(data)`, `.on(event_type, handler)`, `.off(...)` — decorator-friendly event subscription over the Realtime websocket.
- `_send_queue.py` (90 lines, read fully): `SendQueue(max_bytes=1MB)` — `enqueue` (raises `WebSocketQueueFullError` when full), `flush_sync/flush_async` (re-queues on failure), `drain`, `__len__/__bool__`.
- `helpers/local_audio_player.py` (165 lines): `LocalAudioPlayer(should_stop)` — `play(...)` TTS PCM chunks via sounddevice/numpy at `SAMPLE_RATE=24000`; `helpers/microphone.py` — mic capture helper for realtime voice loops. Both need the `voice_helpers` extra.
- `lib/_realtime.py` (92 lines): `_Calls/_AsyncCalls.create(*, sdp, session)` — posts `application/sdp` (or multipart `sdp+session` JSON) to `/realtime/calls`, returns binary SDP answer.

### 1.4 Pagination helpers (`pagination.py`, 250 lines, read fully)

- `SyncPage/AsyncPage` — non-paginated forward-compat (`data`, `object`).
- `SyncCursorPage/AsyncCursorPage` — `data, has_more`, next page via `after=<last item id>`; honors `has_more=False`.
- `SyncConversationCursorPage/AsyncConversationCursorPage` — same but keyed on `last_id`.
- `SyncNextCursorPage/AsyncNextCursorPage` — keyed on opaque `next` cursor.
- All expose sync/async iteration + `has_next_page() / next_page_info() / auto_paging_iter()`. Used by `files.list`, `models.list`, `batches.list`, vector-store lists, etc.

### 1.5 Provider system (`_provider.py`, `providers/`, `lib/azure.py`, `lib/bedrock.py`)

- `_provider.py` (65 lines, read fully): opaque `_Provider` handle + `_ProviderRuntime(name, base_url, transform_request, transform_async_request, prepare_request, prepare_async_request, normalize_response, normalize_async_response)`. Definitions live in a `WeakKeyDictionary`; only OpenAI-owned factories can mint one (`"Invalid provider…"` otherwise). **Not a generic "custom provider" plugin API** — DDGS cannot register its own provider through it.
- `providers/bedrock.py` (412 lines, signature-scanned): `bedrock(*, region?, aws_auth?, bearer_token?)` factory → SigV4-signed or bearer auth against Bedrock's `/responses` endpoint, strips `/responses` suffix from base_url, forbids custom `Authorization` header and auto-redirects.
- `lib/bedrock.py` + `lib/_bedrock_auth.py`: `BedrockOpenAI / AsyncBedrockOpenAI` clients (region-derived base URL, SigV4 signing, `_refresh_api_key`).
- `lib/azure.py` (745 lines, signature-scanned): `AzureOpenAI / AsyncAzureOpenAI` (api_key | Azure AD token | token provider, `azure_endpoint` + `api_version` + `azure_deployment`, `_configure_realtime`, mutually-exclusive-auth guard).
- `lib/_old_api.py` (72 lines): legacy `openai.ChatCompletion.create` shims. `lib/_validators.py` (809 lines): strict-schema validators.

### 1.6 `_extras/` (entire, read fully — 4 tiny files)

Lazy optional-dependency proxies: `numpy_proxy` (`openai[voice_helpers]`), `pandas_proxy` (`openai[datalib]`), `sounddevice_proxy` (`openai[voice_helpers]`), plus `_common.format_instructions / MissingDependencyError`. Zero runtime cost until the guarded feature is used.

### 1.7 Module-level plumbing (all read fully)

- `_qs.py` (149 lines): `Querystring(array_format, nested_format)` — `parse / stringify / stringify_items`; array formats `repeat|comma|indices|brackets`, nested `brackets|dots`. Internal; not a public query builder.
- `_files.py` (173 lines): `to_httpx_files / async_to_httpx_files` (PathLike→bytes, tuple passthrough), `read_file_content`, `deepcopy_with_paths` (copy-on-write along file paths). Internal upload machinery DDGS gets for free via `files.create`.
- `_httpx2.py` (151 lines): experimental `httpx2` transport — `DefaultHttpx2Client / DefaultAsyncHttpx2Client`, URL/timeout/auth normalizers. Needs `pip install openai[httpx2]` + Python ≥3.10.
- `_module_client.py` (197 lines): module-level lazy proxies (`openai.chat`, `.beta`, `.files`, `.audio`, `.images`, …) — lets DDGS call `openai.embeddings.create(...)` without constructing a client (uses env-configured global client).

### 1.8 Non-chat endpoint families (method + key params, one line each)

**Audio** (`resources/audio/`):
- `audio.speech.create(*, input≤4096ch, model[tts-1|tts-1-hd|gpt-4o-mini-tts], voice[alloy…cedar|{id}], instructions, response_format[mp3|opus|aac|flac|wav|pcm], speed 0.25–4.0, stream_format[sse|audio]) -> binary` — TTS.
- `audio.transcriptions.create(*, file, model[gpt-transcribe|gpt-4o-transcribe|whisper-1], language, prompt, temperature, timestamp_granularities[word|segment], chunking_strategy, stream?)` — STT (several streaming overloads).
- `audio.translations.create(*, file, model, prompt, response_format, temperature)` — translate-to-English STT.

**Images** (`resources/images.py`): `images.generate(*, prompt≤32k, model[dall-e-2|dall-e-3|gpt-image-*], n 1–10, size, quality[standard|hd|low|medium|high|auto], style[vivid|natural], response_format[url|b64_json], background[transparent|opaque|auto], moderation[low|auto], output_format/compression)`; `images.edit(*, image, mask?, prompt, …)` (4 overloads incl. streaming); `images.create_variation(*, image, n, size)`.

**Embeddings** (`resources/embeddings.py`): `embeddings.create(*, input[str|str[]|tokens], model, dimensions, encoding_format[float|base64, default base64], user)`.

**Moderations** (`resources/moderations.py`): `moderations.create(*, input[str|str[]|multimodal[]], model?)` — harmful-content classifier.

**Files** (`resources/files.py`): `files.create(file, purpose[assistants|batch|fine-tune|vision|user_data|evals], expires_after)`; `retrieve/delete/list/content/retrieve_content/wait_for_processing(file_id)`.

**Uploads** (`resources/uploads/`): `uploads.create(*, bytes, filename, mime_type, purpose)` + `uploads.parts.create/upload` + `uploads.complete/cancel` — resumable multipart large-file upload; `upload_file_chunked(...)` convenience.

**Batches** (`resources/batches.py`): `batches.create(*, completion_window="24h", endpoint[/v1/chat/completions|/v1/embeddings|…], input_file_id, metadata)`; `retrieve/list/cancel`.

**Fine-tuning** (`resources/fine_tuning/`): `fine_tuning.jobs.create(*, model, training_file, validation_file?, hyperparameters, suffix, seed)`; `retrieve/list/cancel/list_events/pause/resume`; `jobs.checkpoints.list(job_id)`; legacy `checkpoints` + `alpha` namespaces.

**Vector stores** (`resources/vector_stores/`): `vector_stores.create(*, name, file_ids, chunking_strategy, expires_after)`; `retrieve/update/list/delete`; `vector_stores.search(vector_store_id, query, filters, max_num_results 1–50, ranking_options, rewrite_query)`; `files.*` attach/detach + `file_batches.*`.

**Responses** (`resources/responses/responses.py`): `responses.create(*, input, instructions, model, reasoning, max_output_tokens, tools, tool_choice, parallel_tool_calls, store, stream, background, conversation, previous_response_id, include, metadata, temperature/top_p, service_tier, prompt_cache_*)`; `stream / parse / retrieve / delete / cancel / compact / connect / input_items.* / input_tokens.*`.

**Realtime** (`resources/realtime/`): `realtime.connect(*, model, call_id?, max_retries, on_reconnecting)` → websocket manager; `realtime.calls.create(*, sdp, session)`; `realtime.client_secrets.create(...)` — ephemeral client tokens.

**Conversations** (`resources/conversations/`): `conversations.create/retrieve/update/delete`; `conversations.items.create/list/retrieve/delete`.

**Models / Completions**: `models.list/retrieve/delete`; `completions.create(*, model, prompt, max_tokens, temperature, stream, …)` — legacy non-chat completions.

**Videos** (`resources/videos.py`, new): `videos.create(prompt, input_reference?, model?, seconds?, size?)`; `create_and_poll/poll/retrieve/list/delete`; `edit/extend/remix`; `download_content`; `create_character/get_character` — text-to-video + character refs.

**Eval / Containers / Skills / Webhooks / Admin**: `evals.create/retrieve/update/list/delete` + `runs.*` — model grading suites; `containers.create/retrieve/list/delete` + `files.*` — sandboxed code-exec workspaces; `skills.create/retrieve/update/list/delete` + `content/versions.*` — reusable tool/skill bundles; `webhooks.unwrap/verify_signature(payload, headers, secret)` — verify incoming OpenAI webhooks; `admin.*` (org/users/projects/api_keys/usage/audit_logs/…) — platform administration (owner keys only).

**Beta** (`resources/beta/`, churn-prone): `beta.assistants.create/retrieve/update/list/delete(*, model, instructions, tools, tool_resources, response_format)`; `beta.threads.create/retrieve/update/delete/create_and_run/create_and_run_poll/create_and_run_stream` + `threads.messages.create/retrieve/update/list/delete` + `threads.runs.*`; `beta.chatkit/realtime/responses` namespaces.

---

## 2. LATENT CAPABILITIES FOR DDGS (ranked by UX impact)

1. **Audio TTS — read search results aloud** (`audio.speech.create` + `LocalAudioPlayer`). Feature: a speaker button on each assistant answer / result card streaming `mp3` into Flet's audio control; hands-free research mode. Needs `voice_helpers` extra + router TTS support.
2. **Embeddings — semantic search over history & scraped pages** (`embeddings.create` + `vector_stores.search`, or local cosine over stored vectors). Feature: "similar past searches" panel and re-ranking of DDG hits against the current question; fully local once vectors are cached.
3. **Images — assistant-generated visuals** (`images.generate`). Feature: `/imagine <prompt>` command rendering `b64_json` inline in the chat view; thumbnail gallery with save-to-downloads.
4. **Speech-to-text — voice query input** (`audio.transcriptions.create` + `helpers/microphone`). Feature: mic button that transcribes into the search box (Whisper via router or local model).
5. **Files + vector stores — analyze scraped documents** (`files.create(purpose=user_data)` → `vector_stores` → `search`). Feature: "attach URL/PDF to conversation" — DDGS uploads scraped pages and lets the assistant cite them (file-search tool).
6. **Moderation — safe results gate** (`moderations.create`). Feature: pre-display flag on NSFW/violent snippets with a blur-and-confirm UI; one cheap call per result batch.
7. **Responses API — upgrade path from chat** (`responses.create/stream/parse` + `lib/_parsing/_responses`). Feature: migrate kani backend to stateful `previous_response_id` threads, native `web_search/file_search` tools, and typed `parse()` instead of hand-rolled JSON extraction.
8. **Realtime voice assistant** (`realtime.connect` + `SendQueue` + event handlers). Feature: push-to-talk conversational mode; high effort (websocket + PCM plumbing in Flet) — park until TTS/STT land.
9. **Batches — bulk enrichment** (`batches.create` + `files`). Feature: overnight "summarize all saved searches" job producing a digest file; only useful once DDGS persists history server-side.
10. **Videos / Fine-tuning / Evals** — low priority: video generation is a novelty slot at best; fine-tuning/evals serve the owner, not the end user (custom ranking model is a far-future play).

---

## 3. GOTCHAS

- **Beta churn**: everything under `beta.*` (assistants/threads/runs) is versioned separately and has already been superseded by Responses/Conversations; Assistants hits end-of-life — do not build DDGS features on it.
- **Auth**: all non-chat endpoints require a real OpenAI bearer key with matching scopes; `admin.*` needs an owner/project key, `realtime.client_secrets` needs a server key (never ship it in the Flet client), webhooks need the signing secret.
- **Router rejection**: a barebones OpenAI-compatible router (chat-only, as DDGS uses today) will 404/422 on `audio.*`, `images.*`, `embeddings`, `moderations`, `files/uploads`, `batches`, `fine_tuning`, `vector_stores`, `realtime`, `responses`, `videos`, `evals` — verify each family against the router (or proxy to api.openai.com) before wiring UI.
- **Binary responses**: `speech.create` and `realtime.calls.create` return `HttpxBinaryResponseContent`, not JSON — stream bytes to disk/audio, don't `.json()` them.
- **Provider lock-in**: `_Provider`/Bedrock/Azure paths only accept OpenAI-minted factories; pointing DDGS at a custom base_url stays on the plain `OpenAI(base_url=…)` client, which is fine.
- **Extra installs**: TTS playback needs `pip install openai[voice_helpers]` (numpy+sounddevice+pandas); `httpx2` transport is experimental.
- **Strict-only parsing**: `parse_chat_completion` silently returns `parsed_arguments=None` for non-`strict` tools — always set `strict:true` or check `has_parseable_input` first.

---

## 4. COVERAGE

- **Files read fully or signature-scanned: ~52 / 1497 total `.py` files** (~3.5% by count — the package is dominated by generated `types/` models and per-endpoint `WithRawResponse` wrappers, which were deliberately skipped).
- Read completely: `_event_handler.py`, `_qs.py`, `_files.py`, `_httpx2.py`, `_module_client.py`, `_send_queue.py`, `_streaming.py`, `_provider.py`, `pagination.py`, `_extras/` (4), `lib/_parsing/` (3), `lib/_tools.py`, `lib/_realtime.py`, `helpers/local_audio_player.py` (partial), `providers/bedrock.py`.
- Signature-scanned (`def`/`class` grep + key-param excerpts): `lib/azure.py`, `lib/bedrock.py`, all of `resources/audio/`, `embeddings.py`, `moderations.py`, `files.py`, `batches.py`, `images.py`, `uploads/`, `videos.py`, `fine_tuning/`, `vector_stores/`, `realtime/`, `conversations/`, `responses/`, `models.py`, `completions.py`, `evals/`, `containers/`, `skills/`, `webhooks.py`, `beta/` (assistants, threads, messages), `lib/streaming/chat/`, `lib/streaming/_assistants.py`.
- Not read (out of scope, generated): `types/` (~1200 files), `__init__` re-export shims, `WithRawResponse/WithStreamingResponse` wrapper classes, `admin/` sub-tree (listed only).
