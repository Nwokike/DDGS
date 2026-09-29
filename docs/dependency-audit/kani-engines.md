# kani engines — capability audit for DDGS

Auditor: ZCode agent · date: 2026-09-29 · kani installed at `.venv/Lib/site-packages/kani/engines/`
Consumer: `src/services/kani_backend.py` (+ `src/services/reasoning.py` ReasoningEngine/ThoughtTap, `src/services/tokenizer.py`).
Current usage: `ReasoningEngine(OpenAIEngine)` with `client=openai.AsyncOpenAI`, `api_type="chat_completions"`,
`max_context_size=131072`, injected `tokenizer=`, constructor `temperature=`, per-call `max_tokens=`, `engine.stream` via kani's loop.

---

## 1. COMPLETE API INVENTORY

### 1.1 `base.py` — BaseEngine / completions / WrapperEngine

**`BaseCompletion` (ABC)** — contract every completion satisfies:
- `.message -> ChatMessage` (abstract property)
- `.prompt_tokens -> int | None` (None = "kani, estimate with tokenizer")
- `.completion_tokens -> int | None` (same fallback)

**`Completion(BaseCompletion)`** — trivial holder: `__init__(message, prompt_tokens=None, completion_tokens=None)`.

**`BaseEngine` (ABC)** — required interface:
- `max_context_size: int` — hard attribute; kani guarantees `prompt_len(messages, functions) < max_context_size` before calling predict/stream, so this is the eviction trigger.
- `prompt_len(messages, functions=None, **kwargs) -> int` (abstract, sync OR async — has sync+async `@overload`s; use `Kani.prompt_token_len` to hide the difference).
- `predict(messages, functions=None, **hyperparams) -> BaseCompletion` (abstract, async).
- Optional: `stream(messages, functions=None, **hyperparams) -> AsyncIterable[str | BaseCompletion]` — default impl warns and yields full text then the completion; the yielded `BaseCompletion`, when present, MUST be last.
- Optional: `close()` (default no-op) — resource cleanup.
- `disable_function_calling_kwargs = {"include_functions": False}` — kwargs kani's `_full_round` injects when a retry must keep tool schemas visible but forbid calls.
- `__repr__` auto-generated from instance `__dict__` (minus `_`-private and `__ignored_repr_attrs__`).
- Deprecated old-style counting: `message_len(message)` (deprecated 1.7.0, raises if `prompt_len` is async-only), `token_reserve: int = 0`, `function_token_reserve(functions)` (warns "conversational only" when functions passed).

**`WrapperEngine(BaseEngine)`** — decorator base: `__init__(engine, *args, **kwargs)`, copies `max_context_size`, passes through `prompt_len/predict/stream/close`, `__getattr__` forwards everything else. This is the sanctioned pattern for cross-cutting engine middleware (logging, metering, retries).

### 1.2 `mixins.py` — TokenCached

Unbounded lightweight caches (`{int: int}` dicts):
- Prompt level: `prompt_cache_key(messages, functions, **kwargs)` (None when kwargs present = no caching), `get_cached_prompt_len`, `set_cached_prompt_len`.
- Message level: `message_cache_key(message)` — `(role, parts, tool_calls)`; non-str parts hashed by `id()` (stable while in history); `get_cached_message_len`, `set_cached_message_len`.

### 1.3 `openai/engine.py` — OpenAIEngine (TokenCached, BaseEngine), 469 lines

Constructor `__init__(api_key=None, model="gpt-4.1-nano", max_context_size=None, *, api_type=None, organization=None, retry=5, api_base="https://api.openai.com/v1", headers=None, client=None, tokenizer=None, **hyperparams)`:
- Exactly one of `(api_key, client)`; when `client` is given, `organization/retry/api_base/headers` are IGNORED (DDGS passes `client`, so its `max_retries=2`/timeout/UA live on the httpx/openai client, not the engine).
- `max_context_size=None` → prefix lookup in `CONTEXT_SIZES_BY_PREFIX`, else warn + 2048. DDGS passes explicit 131072, bypassing this.
- `api_type=None` → prefix lookup in `API_BY_PREFIX` + warn. DDGS passes `"chat_completions"` explicitly.
- Stores `self.model`, `self.max_context_size`, `self.hyperparams` (constructor-level defaults, merged per-call as `self.hyperparams | hyperparams`), `self.openai_api_type`, `self._tokenizer`.
- `disable_function_calling_kwargs = {"tool_choice": "none"}` (OpenAI spelling of "schemas visible, calls forbidden").

Token counting:
- `tokenizer` property — lazy: returns injected tokenizer, else `tiktoken.encoding_for_model(model)`, else warn + `o200k_base`. DDGS injects `tokenizer_or_heuristic()` to avoid the cold-cache BPE download stall.
- `message_len(message)` — 7-token base + text/tool-call/name tokens; image parts via `mm_tokens.tokens_from_image_size`, audio via `tokens_from_audio_duration`; `gpt-4o` + FUNCTION-role hack `+6 + mlen//20`; result cached in TokenCached.
- `function_token_reserve(functions)` — renders tools through the GPT-OSS TypeScript-namespace template (`function_calling.prompt`) and counts with tokenizer; inner impl `lru_cache(maxsize=256)`.
- `_count_tokens_arg_names` (cached_property) — introspects `client.responses.input_tokens.count` signature for the server-side counting call.
- `prompt_len(messages, functions, **kwargs)` — **responses**: server-side `responses.input_tokens.count` (filters kwargs to valid names); **chat_completions**: incremental `cached(messages[:-1]) + message_len(last)` optimisation, else `sum(message_len) + function_token_reserve`.

Translation / request building (all overridable — see §2):
- `translate_functions(functions)` — chat: `[{type:function, function:{name, description, parameters}}]`; responses: flattened `{type:function, name, description, parameters}`.
- `translate_messages(messages)` — runs `OPENAI_PIPELINE` then per-message translator per api_type.
- `translate_kani_message_to_openai(msg)` (static) / `translate_kani_message_to_openai_responses(msg)` (static) — single-message translators.
- `_prepare_request(messages, functions, *, intent, **kwargs)` — returns `(kwargs, translated_messages, tool_specs)`; for responses forces `include=["reasoning.encrypted_content"]` via setdefault+append. `intent` ∈ {chat_completions.create/stream, responses.create/stream, responses.input_tokens.count}.
- `_translate_openai_chat_completion(completion)` — wraps raw response: chat → `ChatCompletion`, responses → `openai_responses_response_to_kani_completion`.

Chat-completions paths:
- `_predict_chat_completions` — `client.chat.completions.create(model, messages, tools, **local)`, wraps in `ChatCompletion`, caches prompt len AND `prompt+completion` len for the extended history, caches message len.
- `_stream_chat_completions` — `create(..., stream=True, stream_options={"include_usage": True})`; yields `delta.content` chunks; reassembles tool-call partials by `index` (concatenates name+arguments); final `Completion` carries real usage when the server sent it, else `prompt_tokens = completion_tokens = None`; stashes `msg.extra["openai_usage"] = DottableDict(usage)`.

Responses paths:
- `_predict_responses` — `client.responses.create(model, input, tools, **local)`; caches `input_tokens` / `total_tokens`.
- `_stream_responses` — `client.responses.stream(...)`; yields only `response.output_text.delta` events; `get_final_response()` → kani completion + usage caches.

Main impl: `predict` / `stream` dispatch on `openai_api_type` (ValueError otherwise); `close()` → `await client.close()`; `__repr__` shows model/max_context_size/hyperparams only.

Message extras contract (docstring): `"openai_completion"` (non-streaming only, full raw completion as DottableDict on `message.extra`), `"openai_usage"` (raw usage dict; streaming path sets it too when server sends usage).

### 1.4 `openai/translation.py` (172 lines) — chat-completions wire

- `kani_cm_to_openai_cm(msg)`: FUNCTION+tool_call_id → `tool` message; bare FUNCTION → legacy function message; SYSTEM/USER passthrough (`_msg_kwargs` adds `name`); ASSISTANT+tool_calls → `kani_tc_to_openai_tc` each.
- `_msg_kwargs`: USER messages with list-parts go through `_parts_to_oai` (multimodal); everything else uses `msg.text`.
- `kani_tc_to_openai_tc` / `openai_tc_to_kani_tc` / `openai_fc_to_kani_fc` — ToolCall↔OpenAI dict/dataclass conversions (id/type/name/arguments preserved).
- `_parts_to_oai`: with `multimodal-core`: AudioPart → `input_audio` (wav base64), ImagePart → `image_url` (data URI), else `text`; without it: plain string join (images silently degrade to text — no error).
- `OPENAI_PIPELINE = PromptPipeline().ensure_bound_function_calls().ensure_start(predicate=role != FUNCTION)` — binds orphan tool-call IDs, strips leading FUNCTION messages.
- `openai_cm_to_kani_cm`: `tool` role → FUNCTION; legacy `function_call` → singular ToolCall.
- `ChatCompletion(BaseCompletion)`: keeps `.openai_completion` (raw SDK object); message extras get `openai_completion` + `openai_usage` DottableDicts; `prompt_tokens` = usage.prompt_tokens; **`completion_tokens` = usage.completion_tokens + 5** (ChatML `<|im_start|>assistant`/`<|im_end|>` fudge).
- Deprecated shims `translate_functions` / `translate_messages` delegate to the engine methods.

### 1.5 `openai/translation_responses.py` (197 lines) — responses-API wire

- `OAI_RESPONSES_EXTRA_KEY = "openai_response"` — round-trip cache: if present, kani→OpenAI reuses stored `.output` verbatim (preserves thought signatures/encrypted reasoning across turns).
- `kani_cm_to_openai_responses_inputs(msg)`: FUNCTION+tool_call_id → `FunctionCallOutput(call_id, output)`; bare FUNCTION → ValueError; SYSTEM/USER → `EasyInputMessageParam`; ASSISTANT → reasoning parts (`OpenAIReasoningPart` with id+encrypted_content round-tripped; plain `ReasoningPart` re-keyed via `extra._openai_id/_openai_encrypted_content`) + main message + `ResponseFunctionToolCallParam` per tool call.
- `_parts_to_oai_responses`: ImagePart → `input_image` (detail auto); other multimodal (audio) → warns "use Chat Completions for audio" and degrades to text.
- `openai_responses_response_to_kani_completion(response)`: `ResponseReasoningItem` → `OpenAIReasoningPart`; `ResponseFunctionToolCall` → ToolCall; `ResponseOutputMessage` → text (incl. refusals); anything else → `OpenAIUnknownPart`; extras get full response dump (minus streaming-only keys) + `openai_usage`; tokens = `input_tokens`/`output_tokens`.
- `openai_responses_outputs_to_kani_cm(outputs)` — the list-level assembler above.

### 1.6 `openai/model_constants.py` (85 lines)

- `CONTEXT_SIZES_BY_PREFIX`: gpt-5/5.x (400k–1.05M), o1/o3/o4 (200k), gpt-4.1 (~1.047M), gpt-4o/chatgpt-4o/gpt-audio (128k), gpt-realtime (32k), gpt-4-turbo family (128k), 4-32k (32768), gpt-4 (8192), 3.5-turbo (16385/4096), fine-tunes, babbage/davinci-002 (16384), catch-all `"" → 2048`.
- `API_BY_PREFIX`: responses for gpt-5.5/5.4-pro, gpt-5-codex, gpt-5-pro, gpt-5.1-codex-max, o1/o3-pro, deep-research pair, computer-use; catch-all chat_completions.
- `MM_IMAGE_LOW_COST_SCALE` (per-patch multipliers: gpt-5-mini/nano, 5.4-mini/nano, 4.1-mini/nano, o4-mini) and `MM_IMAGE_OLD_SCALE` (base+per-patch: gpt-5/4o/4.1/4.5, gpt-4o-mini, o1/o3, default 85+170×patches).

### 1.7 `openai/function_calling.py` (260 lines)

Pure token-counting renderer ported from the GPT-OSS chat template: `prompt(functions)` → `"# Tools\n\n" + render_tool_namespace("functions", ...)`; `render_typescript_type` handles array/union(oneOf)/enum/string/number/integer/boolean/object with nullable/default annotations; `render_tool_namespace` emits `// desc\ntype name = (_: {params}) => any;`. Used ONLY for `function_token_reserve` — never sent on the wire.

### 1.8 `openai/parts.py` (25 lines) + `mm_tokens.py` (84) + `utils.py` (4)

- `OpenAIUnknownPart(MessagePart)`: `{type, data}` — unknown server features carried opaquely, re-sent verbatim next round, never to other engines.
- `OpenAIReasoningPart(ReasoningPart)`: `{id, encrypted_content}` — multi-turn reasoning continuity for the responses API.
- `tokens_from_image_size(size, model_id, low_detail=False)`: low→85; low-cost models→32px-patch count × multiplier (with 1536-patch downscale); old models→2048/768 rescale, 512px patches, base+scale×patches (warns + defaults for unknown models).
- `tokens_from_audio_duration(seconds, model_id)`: `ceil(seconds × 10)` (empirical, undocumented).
- `DottableDict(dict)` — `__getattr__` → `__getitem__` shim so `extra["openai_usage"].prompt_tokens` works like the old Pydantic model.

### 1.9 Non-OpenAI adapters (module-level survey; app will not use)

- `anthropic/engine.py` — `AnthropicEngine(TokenCached, BaseEngine)`: own `content_transform` pipeline, `_prepare_request`, `_translate_anthropic_message`, server `prompt_len` via count-tokens introspection, `predict/stream/close`, `message_len`+`function_token_reserve(lru)`. `parts.py`: `AnthropicThinkingPart`/`AnthropicUnknownPart`. `mm_tokens.py`: `tokens_from_image_size(size)` (flat per-image, no model_id). `model_constants.py`: all-Claude 200k + catch-all. Extras: thinking-signature round-trip; PDF `BinaryFilePart` document support.
- `google/engine.py` — `GoogleAIEngine(TokenCached, BaseEngine)`: `GOOGLE_PIPELINE` (SYSTEM→USER demotion + bind calls), `ROLE_TRANSFORMS` (assistant→model, function→tool), raw extra key `"google_response"`, async `_prepare_request/_translate_message/_translate_multimodal_part`, full `predict/stream/prompt_len/close`. `mm_tokens.py` adds `tokens_from_video_duration(seconds, model_id, fps, low_res)` — the only video accounting in the package.
- `huggingface/` — `HuggingEngine(BaseEngine)`: local `AutoModelForCausalLM` + `TextIteratorStreamer` thread, `build_prompt` via `PromptPipeline[str|Tensor]`, `_get_generate_args/_get_eos_tokens`, `token_reserve/_infer_token_reserve`; `chat_template_pipeline.py`: `ChatTemplatePromptPipeline` (model-bundled Jinja template, `from_pretrained`, token-reserve inference); `llama2.py`: `LlamaEngine(HuggingEngine)` (Llama-2 default); `__main__.py` CLI runner.
- `llamacpp/base.py` — `LlamaCppEngine(BaseEngine)`: GGUF via `Llama.from_pretrained` or local path (exactly-one rule), `build_prompt`, `_get_generate_args`, `predict/stream/close`, `token_reserve/_infer_token_reserve`.

---

## 2. HOOK/EXTENSION POINTS

Already used by DDGS: `ReasoningEngine(OpenAIEngine)` override + `client=` injection + per-call hyperparams (`manager` loop passes `max_tokens=budget` → `stream(..., **hyperparams)` → `hyperparams | self.hyperparams`).

| Hook | How | Example for DDGS |
|---|---|---|
| `engine.stream/predict` override | Subclass (DDGS's ReasoningEngine pattern) or wrap; must keep "completion last" yield contract | Metering wrapper: count `str` chunks → live cost ticker without touching kani_backend |
| `translate_functions` / `translate_messages` / `translate_kani_message_to_openai[_responses]` | Override to rewrite the wire payload | Inject search-result citations as a system suffix; force `tool_choice` per round |
| `_prepare_request(..., intent, **kwargs)` | Last stop before the SDK call; `intent` tells which endpoint | Log/deny-list tool specs; add `include` flags for responses API |
| `disable_function_calling_kwargs` | Class attr kani applies on function-retry rounds | Already correct (`tool_choice:none`); a strict mode could also set `parallel_tool_calls: False` |
| `close()` / transport lifecycle | `await engine.close()` shuts the SDK client | DDGS builds one engine+client per turn and never closes — call `engine.close()` at end of `run_turn`/`complete` (see §4, double-layer retries note) |
| `WrapperEngine` | Composition instead of subclassing | `class MeteredEngine(WrapperEngine)` forwarding to ReasoningEngine, adding token-receipt accumulation |
| `prompt_len` / `message_len` / TokenCached setters | Override or pre-seed `set_cached_prompt_len` | Pre-seed known system-prompt length once at startup; skip recounting every round |
| `ChatMessage.extra` keys | Read `openai_completion/openai_usage/openai_response` off the returned message | Real token receipts (see §3.4); finish_reason checks already partially done via `_finish_of` |
| `OpenAIUnknownPart` / `OpenAIReasoningPart` passthrough | Preserved across rounds automatically | Keep reasoning continuity if/when moving to responses API — no code needed |

---

## 3. LATENT CAPABILITIES FOR DDGS (ranked by UX impact)

1. **Multimodal image parts — send image-search results to the model.** `parts.ImagePart` + `_parts_to_oai` already encode `image_url` data-URIs on chat-completions; `message_len`/`mm_tokens` already budget them. Feature: "look at this" — user taps a thumbnail from image search, DDGS attaches it (downscaled, `tokens_from_image_size` pre-check) to the next turn. Responses-API path supports images too; audio would need chat-completions (responses warns and degrades audio to text).
2. **`api_type="responses"` — the reasoning-model API.** Response objects carry `OpenAIReasoningPart(id, encrypted_content)` round-tripped automatically, `output_text.delta` streaming, server-side `input_tokens.count`, unknown features preserved as `OpenAIUnknownPart`. Feature: when the router serves o-series/gpt-5-pro/deep-research models, switch api_type per model id instead of forcing chat-completions — reasoning continuity survives multi-turn tool loops without the ThoughtTap SSE hack. Note DDGS's ThoughtTap already parses `response.reasoning_summary_text.delta` frames, so the Thinking block keeps working during migration.
3. **Per-call hyperparams passthrough (`top_p/seed/penalties/response_format/tool_choice/...`).** Anything in `hyperparams` merges over constructor defaults straight into `create()`. Features: `response_format={"type":"json_object"}` for the RELATED/citations extractor; `seed` for reproducible overview summaries; `tool_choice="required"` for "must use search" turns; `frequency_penalty` to de-loop rambling answers. Zero engine changes — just pass kwargs from `run_turn`.
4. **Real token receipts from the usage cache.** Streaming sets `stream_options.include_usage` and stashes `msg.extra["openai_usage"]` + TokenCached prompt/message lens; non-streaming sets `openai_completion` too. Feature: per-step receipt rows (prompt/completion/total, cached vs billed) next to the existing served-by model id — replaces heuristic credit estimates with server numbers. Access via `await manager.completion()` → `.message.extra["openai_usage"]`.
5. **Cheap non-stream `predict` for background calls.** `complete()` (overview/page summaries) streams today to reuse `on_token`, but `predict` returns one `ChatCompletion` with full `openai_completion` extra and no SSE overhead. Feature: use `kani.chat_round(...)` for free background summaries — fewer connections, full raw response for receipts, same text out.
6. **Context eviction via `prompt_len` (currently dead code).** `DEFAULT_CONTEXT=131072` is deliberately unreachable for a 6-message transcript, so kani never trims. Feature: long "research session" mode — lower `max_context_size` per turn and let kani's built-in eviction summarize/trim instead of the hard `[-AGENT_HISTORY_MESSAGES:]` slice in `_to_history`.
7. **Anthropic/Google adapters — multi-provider future.** Same `BaseEngine` contract, same tool loop; swapping provider = swapping engine. Feature: "bring your own key" Claude/Gemini option, or Gemini for video-understanding turns (`tokens_from_video_duration` is unique to Google). No kani_backend loop changes needed.
8. **`engine.close()` lifecycle.** One `AsyncOpenAI`+httpx client is built per turn and never closed. Feature: `await engine.close()` in a `finally` in `run_turn`/`complete` — stops socket/FD creep during long sessions. (With per-turn engines there is no reuse argument against it.)
9. **HuggingFace/llama.cpp — offline fallback.** Local `HuggingEngine`/`LlamaCppEngine` behind the same loop. Feature: airplane-mode small-model fallback for summaries; realistically last priority (torch/GGUF deps, device management).

## 4. GOTCHAS

- **Streaming vs non-stream completion shape.** Non-stream yields `ChatCompletion` with `.openai_completion` (raw SDK object) + `+5` ChatML fudge on `completion_tokens`. Streaming yields a plain `Completion` with NO `openai_completion` extra — only `openai_usage` when the server sent usage. DDGS's `_finish_of` already handles this (reads `openai_completion.choices[0].finish_reason`, defaults `""`).
- **`finish_reason` access paths.** Stream chunks' `finish_reason` is consumed internally and NOT surfaced; only `await manager.completion()` → `.message.extra[...]` has it. The empty-text/`length` retry in `run_turn` is the right pattern; don't look for finish reasons on streamed strings.
- **Usage arrives only with `stream_options={"include_usage": True}`** (engine sets it) AND only on routers that forward it. When absent, both token counts are `None` and kani falls back to tokenizer estimation — receipts code must handle `None`, and the cold-cache heuristic path in `tokenizer.py` will be the source.
- **Tokenizer choices.** Injected tokenizer wins; lazy tiktoken load can download BPE with no timeout (DDGS's `tokenizer_or_heuristic` guard exists for exactly this); unknown model ids raise KeyError inside tiktoken → engine warns + `o200k_base`. Router model ids like `auto` never match a real encoding — heuristic is the steady state, not the fallback.
- **Double-layer retries.** Engine `retry=5` applies ONLY when it builds its own client; DDGS passes `client=` so engine retry is inert and `openai.AsyncOpenAI(max_retries=2)` + httpx timeouts own all retry behavior. Don't "fix" stalls by raising engine `retry` — it's ignored in this configuration.
- **Responses-API quirks.** Requires `include=["reasoning.encrypted_content"]` (auto-added); bare FUNCTION messages raise ValueError (pipeline must bind first); audio input warns + degrades to text (stay on chat-completions for audio); token counting hits the network (`input_tokens.count`) instead of local tiktoken; per-turn engines lose the `openai_response` round-trip cache (fresh engine per turn = no encrypted-content reuse — either reuse engines across turns or accept re-reasoning).
- **Per-turn engine construction.** `_build_engine` creates client+engine every turn: `max_context_size` prefix lookup and `API_BY_PREFIX` warnings are skipped only because DDGS passes both explicitly — keep passing them if new model families arrive, or the `""` catch-alls (2048 tokens / chat_completions) silently apply.
- **`message_len` override shadows the deprecated base signature** (sync `def message_len`, not the abstract `prompt_len`) — intentional: chat-completions counting stays local/sync while responses counting goes async/server-side. Don't "unify" them.
- **ThoughtTap fragility.** The tap sniffs raw SSE `data:` frames for `reasoning_content/reasoning/reasoning_details` + responses-typed deltas; a router that renames these fields darkens the Thinking block with no error. The `last_model` stamp has the same dependency (`payload.model`).

## 5. COVERAGE

Files read (17) / total engine files (17 + `__pycache__`): `engines/base.py`, `engines/mixins.py`, `engines/__init__.py`, `engines/openai/` — `__init__.py`, `engine.py`, `function_calling.py`, `mm_tokens.py`, `model_constants.py`, `parts.py`, `translation.py`, `translation_responses.py`, `utils.py` (all 9, line by line) — plus surveyed `anthropic/engine.py,model_constants.py,parts.py,mm_tokens.py`, `google/engine.py,mm_tokens.py`, `huggingface/base.py,chat_template_pipeline.py,llama2.py,__main__.py`, `llamacpp/base.py`. Consumer files: `src/services/kani_backend.py`, `src/services/reasoning.py`, `src/services/tokenizer.py`.
