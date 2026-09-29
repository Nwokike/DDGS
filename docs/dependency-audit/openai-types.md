# Dependency audit: `openai` types (openai 2.54.0)

- Package audited: `C:\Users\nwoki\.zcode\workspace\default\DDGS\.venv\Lib\site-packages\openai\types\`
- Consumer: DDGS — Flet search/download/assistant app. Chat path is
  `ai_service.stream_chat()` -> `kani_backend.complete()` -> kani
  `ReasoningEngine(api_type="chat_completions")` -> `client.chat.completions.create()`
  against a local router (`model="auto"` default). kani translates messages,
  so DDGS never touches these types directly.
- What DDGS actually sends today: `model`, `messages`, `tools` (plain function
  tools, non-strict), `temperature`, `stream=True`, `stream_options={"include_usage": True}`,
  `max_tokens` (only when set). That is the entire wire vocabulary in use.

## 1. TYPE INVENTORY BY AREA

### 1.1 Chat completions — request (`chat/completion_create_params.py`)

- `CompletionCreateParamsBase` (TypedDict; `NonStreaming` adds `stream: False`,
  `Streaming` requires `stream: True`): messages*, model*, audio, frequency_penalty,
  function_call, functions (legacy), logit_bias, logprobs (bool), max_completion_tokens,
  max_tokens, metadata, modalities (`text`|`audio`), moderation (`model*` + policy
  input/output `score`|`block`), n, parallel_tool_calls, prediction (`type: content`),
  presence_penalty, prompt_cache_key, prompt_cache_options (`mode implicit|explicit`,
  `ttl 30m`), prompt_cache_retention (`in_memory`|`24h`), reasoning_effort
  (`none|minimal|low|medium|high|xhigh|max`), response_format (see 1.6),
  safety_identifier, seed, service_tier (`auto|default|flex|scale|priority|fast`),
  stop (str | list), store (bool), stream_options (`include_usage`, `include_obfuscation`),
  temperature, tool_choice (see 1.7), tools, top_logprobs (int), top_p, user, verbosity
  (`low|medium|high`), web_search_options (`search_context_size low|medium|high`,
  `user_location.approximate{city,country,region,timezone}`).
- Reasoning response config (`shared/reasoning.py`): context (`auto|current_turn|all_turns`),
  effort, generate_summary (`auto|concise|detailed`), mode (`standard|pro`), summary.

### 1.2 Chat completions — messages (params + models)

- Roles (`chat_completion_role.py`): `developer|system|user|assistant|tool|function`.
- `ChatCompletionDeveloperMessageParam`: content*, role `developer`.
- `ChatCompletionSystemMessageParam`: content*, role `system`, name.
- `ChatCompletionUserMessageParam`: content* (str | text|image|input_audio|file parts), role `user`, name.
- User content parts: `ChatCompletionContentPartTextParam{text*,type:text}`,
  `ChatCompletionContentPartImageParam{image_url{url*,detail},type:image_url}`,
  `ChatCompletionContentPartInputAudioParam{input_audio{data*,format wav|mp3}}`,
  `File{file{file_data|file_id|filename*},type:file}`.
- `ChatCompletionAssistantMessageParam`: role `assistant`, content, refusal,
  name, audio{id*}, function_call{name*,arguments*} (deprecated), tool_calls[].
- `ChatCompletionToolMessageParam`: content*, role `tool`, tool_call_id*.
- `ChatCompletionFunctionMessageParam`: content*, name*, role `function` (deprecated).
- Response `ChatCompletionMessage`: content, refusal, role `assistant`, annotations[]
  (`type url_citation` + `url_citation{url*,title,start_index,end_index}`),
  audio (`ChatCompletionAudio{id,data,expires_at,transcript}`),
  function_call (deprecated), tool_calls[] (function | custom{id,custom{input*,name*}}).
- `ChatCompletionStoreMessage`: + id, content_parts[] (text|image).

### 1.3 ChatCompletionChunk — streaming deltas (`chat/chat_completion_chunk.py`)

- `ChatCompletionChunk{id, choices[], created, model, object:chat.completion.chunk,
  moderation?, service_tier?, system_fingerprint?, usage?}`.
- `Choice{delta, finish_reason (stop|length|tool_calls|content_filter|function_call), index, logprobs?}`.
- `ChoiceDelta{content?, function_call?{name?,arguments?} (deprecated), refusal?,
  role?, tool_calls?[{index*, id?, function?{name?,arguments?}, type?}]}`.
- `ChoiceLogprobs{content?[], refusal?[]}`; `ChatCompletionTokenLogprob{token, bytes?,
  logprob, top_logprobs[{token,bytes?,logprob}]}`.
- NO `reasoning_content` field in this SDK's chunk delta — DDGS's Thinking tap reads
  vendor `reasoning_content`/`reasoning`/`reasoning_details` SSE keys at the transport
  level (`src/services/reasoning.py`), outside these types.
- Moderation echo: `Moderation{input, output}` each `moderation_results{model, results[]}` |
  `error{code,message}`; per-result `categories{}, category_applied_input_types{},
  category_scores{}, flagged, model`.

### 1.4 ChatCompletion response (non-streaming, `chat/chat_completion.py`)

- `ChatCompletion{id, choices[], created, model, object:chat.completion, moderation?,
  service_tier?, system_fingerprint?, usage?}`.
- `Choice{finish_reason, index, logprobs?, message}`.
- `service_tier` values: `auto|default|flex|scale|priority|fast`.
- Parsed helpers: `ParsedChatCompletion/ParsedChoice/ParsedChatCompletionMessage`
  (+`parsed`, `ParsedFunctionToolCall.parsed_arguments`) for `client.beta.chat.completions.parse()`.

### 1.5 CompletionUsage (`completion_usage.py`; also BatchUsage/ResponseUsage variants)

- `CompletionUsage{completion_tokens*, prompt_tokens*, total_tokens*,
  completion_tokens_details?{accepted_prediction_tokens?, audio_tokens?,
  reasoning_tokens?, rejected_prediction_tokens?},
  prompt_tokens_details?{audio_tokens?, cache_write_tokens?, cached_tokens?}}`.
- `ResponseUsage` adds `input_tokens_details{cache_write_tokens, cached_tokens}` and
  `output_tokens_details{reasoning_tokens}` (same shape, non-optional).
- `BatchUsage` mirrors CompletionUsage with required cached/reasoning details.

### 1.6 response_format variants (shared + shared_params mirror)

- `ResponseFormatText{type:text}` — default.
- `ResponseFormatJSONObject{type:json_object}` — legacy JSON mode (no schema).
- `ResponseFormatJSONSchema{type:json_schema, json_schema{name*, description?,
  schema?, strict?}}` — structured outputs; `strict:true` = guaranteed schema adherence.
- Bonus: `ResponseFormatTextGrammar{type:grammar, grammar*}` (lark|regex),
  `ResponseFormatTextPython{type:python}` — grammar-constrained text.
- Responses API equivalent: `ResponseTextConfig{format?, verbosity?}` with
  `ResponseFormatTextJSONSchemaConfig` (same name/schema/strict shape).

### 1.7 tool_choice variants (`chat_completion_tool_choice_option_param.py`, responses mirrors)

- `'none' | 'auto' | 'required'`.
- `ChatCompletionAllowedToolChoiceParam{type:allowed_tools, allowed_tools{mode auto|required, tools[]}}`.
- `ChatCompletionNamedToolChoiceParam{type:function, function{name*}}` (force one function).
- `ChatCompletionNamedToolChoiceCustomParam{type:custom, custom{name*}}`.
- Custom tools: `ChatCompletionCustomToolParam{type:custom, custom{name*, description?, format?}}`
  with format `text` or `grammar{definition*, syntax lark|regex}`.
- Responses API adds: `ToolChoiceAllowed`, `ToolChoiceTypes` (force a builtin:
  file_search|web_search_preview|computer*|image_generation|code_interpreter),
  `ToolChoiceMcp{server_label*}`, `ToolChoiceShell`, `ToolChoiceApplyPatch`,
  `ToolChoiceCustom`, `programmatic_tool_calling`.

### 1.8 Models (`model.py`, `chat_model.py`, `shared/chat_model.py`, `shared/responses_model.py`)

- `Model{id, created, object:model, owned_by}`; `ModelDeleted{id, deleted, object}`.
- `ChatModel` literal pin list (gpt-5.x incl. 5.6-sol/terra/luna, 5.4/5.5, gpt-5/4.1/4o/4-turbo/3.5-turbo,
  o1/o3/o4-mini + dated snapshots); `AllModels`/`ResponsesModel` = str | ChatModel | extras
  (o1-pro, o3-pro, deep-research, computer-use-preview, gpt-5-codex/pro, daybreak, 5.6-cyber...).
- Audio/speech/image/video/model literal files: `AudioModel` (whisper-1, gpt-transcribe*,
  gpt-4o-transcribe*), `AudioResponseFormat` (json|text|srt|verbose_json|vtt|diarized_json),
  `SpeechModel` (tts-1, tts-1-hd, gpt-4o-mini-tts*), `ImageModel`
  (gpt-image-1/1-mini/1.5/2, chatgpt-image-latest, dall-e-2/3), `VideoModel/VideoModelParam`
  (sora-2, sora-2-pro + dated), `VideoSeconds` (4|8|12), `VideoSize` (720x1280,1280x720,1024x1792,1792x1024),
  `ModerationModel` (omni-moderation-latest, ...), `EmbeddingModel`
  (text-embedding-ada-002, text-embedding-3-small/large).

### 1.9 Responses API (220 files — router does NOT serve this; listed for vocabulary)

- `Response{id, created_at, object:response, model, object, output: ResponseOutputItem[],
  parallel_tool_calls, tool_choice, tools, status?, usage?, service_tier?, reasoning?,
  text?, top_logprobs?, truncation?, conversation?, previous_response_id?, instructions?,
  metadata?, temperature?, top_p?, max_output_tokens?, max_tool_calls?, moderation?,
  prompt_cache_*{key,options,retention}?, safety_identifier?, user?, store?, background?}`.
- Output items (`response_output_item.py`, input mirrors in `response_input_item*.py`):
  `message` (ResponseOutputMessage{id, content[output_text|refusal], role assistant,
  status, phase? commentary|final_answer}), `reasoning` (ResponseReasoningItem{id,
  summary[{text,type:summary_text}], content?[{text,type:reasoning_text}], encrypted_content?,
  status?}), `function_call` (+namespace?, status?), `function_call_output`,
  `custom_tool_call`/`custom_tool_call_output`, `file_search_call` (queries, results[{file_id?,
  filename?, score?, text?, attributes?}], status), `web_search_call` (action:
  search{query?,queries?,sources?} | open_page{url?} | find_in_page{pattern*,url*}),
  `computer_call`(+actions[]), `code_interpreter_call` (outputs: logs|image),
  `image_generation_call`, `local_shell_call`/`shell_call` (commands[], env, timeout_ms),
  `apply_patch_call` (operation create_file|update_file{diff*,path*}|delete_file{path*}),
  `mcp_call`/`mcp_list_tools`/`mcp_approval_request|response`, `tool_search_call|output`,
  `compaction`(+encrypted_content), `program`/`program_output`, `item_reference`.
- Output text (`response_output_text*.py`): `ResponseOutputText{annotations[], text,
  type:output_text, logprobs?[]}`; annotation union: file_citation{file_id,filename,index},
  url_citation{url,title,start_index,end_index}, container_file_citation,
  file_path{file_id,index}; refusal content `ResponseOutputRefusal{refusal,type:refusal}`.
- Reasoning/tool stream events (~60 `response_*.py` event types): text delta/done
  (+logprobs), refusal delta/done, reasoning_summary_text delta/done + part added/done,
  reasoning_text delta/done, function_call_arguments delta/done, custom_tool_call_input
  delta/done, code_interpreter_call code delta/done + in_progress/interpreting/completed,
  file_search/web_search/mcp/computer/image_generation/audio (delta/done) events,
  output_item added/done, content_part added/done, response created/in_progress/
  completed/failed/incomplete/queued.
- Request (`response_create_params.py`): same shape as chat params plus background,
  context_management[{type,compact_threshold?}], conversation (id|param), include[]
  (ResponseIncludable: file_search_call.results, web_search_call.results,
  web_search_call.action.sources, message.input_image.image_url, computer_call_output...),
  input (str | input-item list), max_tool_calls, prompt (id (+variables, version)?),
  store, stream/stream_options{include_obfuscation}, text{format,verbosity}, top_logprobs,
  truncation (auto|disabled).
- Tools (`tool.py`/`tool_param.py`): function (+strict, output_schema, defer_loading,
  allowed_callers), file_search{vector_store_ids*,filters?,max_num_results?,ranking_options?},
  web_search{type web_search(_2025_08_26), filters{allowed_domains?},
  search_context_size?, user_location?}, web_search_preview (+search_content_types[]),
  mcp{server_label*, server_url?, headers?, authorization?, allowed_tools?, require_approval?,
  connector_id? (dropbox/gmail/gcalendar/gdrive/teams/outlook/sharepoint)}, code_interpreter
  (container str|auto{file_ids?,memory_limit?,network_policy?}), computer(_use_preview),
  image_generation (action generate|edit|auto, model, size, quality, moderation...),
  local_shell, shell, apply_patch, custom (+format), namespace{tools[]}, tool_search.
- Input items: EasyInputMessage{content, role, phase?, type? message}, Message,
  input_text/input_image{detail,file_id?,image_url?,prompt_cache_breakpoint?}/
  input_file{file_data?|file_id?|file_url?,filename?,detail?}/input_audio{data,format},
  prompt_cache_breakpoint{mode:explicit} on every content part.
- Beta mirror (`beta/` 409 files): identical Responses vocabulary under `Beta*` names
  + Assistants/Threads/Runs (assistant, thread, run{status}, run_step, message{content[],
  annotations incl. file_citation/file_path}, required_action function_tool_call),
  ChatKit sessions/threads/widgets, `beta/realtime/*` client/server events.

### 1.10 Files / uploads / vector stores / containers / skills

- `FileObject{id, bytes, created_at, filename, object:file, purpose
  (assistants|assistants_output|batch|batch_output|fine-tune|fine-tune-results|vision|user_data),
  status (uploaded|processed|error), expires_at?, status_details?}`;
  `FileCreateParams{file*, purpose* (assistants|batch|fine-tune|vision|user_data|evals),
  expires_after?}`; `Upload{id,bytes,created_at,expires_at,filename,object:upload,
  purpose,status,file?}` + parts (`UploadPart`, `PartCreateParams{data*}`).
- `VectorStore{id, created_at, file_counts, name, object:vector_store, status,
  usage_bytes, expires_after?, ...}`; search params {query*, filters?, max_num_results?,
  ranking_options?{ranker, score_threshold, hybrid_search{embedding_weight,text_weight}},
  rewrite_query?}; search hit {file_id, filename, score, content[{text}], attributes?}.
- `ContainerCreateResponse{id, created_at, name, object, status, expires_after?,
  memory_limit? (1g|4g|16g|64g), network_policy? (allowlist|disabled)}`;
  container files (`container.file{id,bytes,container_id,path,source}`).
- `Skill{id, created_at, default_version, description, latest_version, name}`;
  `SkillVersion{..., skill_id, version}`; skills attach to containers/shell tools
  (SkillReference{skill_id*,version?}, InlineSkill{name*,description*,source{data*,base64 zip}},
  LocalSkill{name*,description*,path*}).

### 1.11 Embeddings / images / audio / moderation

- `EmbeddingCreateParams{input*, model*, dimensions?, encoding_format? (float|base64),
  user?}`; `Embedding{embedding[], index, object:embedding}`;
  `CreateEmbeddingResponse{data[], model, object:list, usage{prompt_tokens,total_tokens}}`.
- `ImageGenerateParams{prompt*, model?, moderation? (low|auto), n?, output_compression?,
  output_format? (png|jpeg|webp), partial_images?, quality?, response_format?, size?,
  style? (vivid|natural), user?, stream?}` (+stream events partial_image/completed with
  usage{input_tokens{image_tokens,text_tokens}}); edit/variation params add image/mask.
- `SpeechCreateParams{input*, model*, voice* (alloy|ash|ballad|coral|echo|sage|shimmer|
  verse|marin|cedar | VoiceID{id*}), instructions?, response_format? (mp3|opus|aac|flac|wav|pcm),
  speed?, stream_format? (sse|audio)}`.
- `TranscriptionCreateParams{file*, model*, chunking_strategy? (auto|server_vad{...}),
  include? ([logprobs]), keywords?, known_speaker_names?/references?, language(s)?,
  prompt?, response_format? (json|text|srt|verbose_json|vtt|diarized_json), temperature?,
  timestamp_granularities? ([word|segment]), stream?}`; responses: Transcription{text,
  languages?, logprobs?, usage?}, TranscriptionVerbose{duration, language, segments[]
  {id,avg_logprob,compression_ratio,start,end,text,tokens}, words[]}, TranscriptionDiarized
  {segments[{id,start,end,speaker,text}]}; stream events text delta/done/segment.
- Moderation: `ModerationCreateParams{input* (str | str[] | text|image_url blocks), model?}`;
  `Moderation{categories{harassment(+threatening), hate(+threatening), illicit(+violent),
  self-harm(+instructions+intent), sexual(+minors), violence(+graphic)}, category_scores{},
  category_applied_input_types{}, flagged}`; omni models add image-applied types.

### 1.12 Batches / evals / fine-tuning / conversations / video

- `Batch{id, completion_window, created_at, endpoint (/v1/responses|/v1/chat/completions|
  /v1/embeddings|/v1/completions|/v1/moderations|/v1/images/generations|/v1/images/edits|
  /v1/videos), input_file_id, object:batch, status, output_file_id?, error_file_id?,
  request_counts?, usage?, metadata?}`; create {completion_window:24h*, endpoint*, input_file_id*}.
- Evals (`evals/` 17 files + `graders/` 15): Eval{id,data_source_config
  (custom{...}|logs|stored_completions), testing_criteria[], name}; graders:
  label_model{input,labels,model,name,passing_labels}, string_check{operation
  eq|ne|like|ilike}, text_similarity{metric cosine|fuzzy|bleu|gleu|meteor|rouge_*},
  python{source}, score_model{range,sampling_params}.
- Fine-tuning (`fine_tuning/` 37): job{id,model,status,...}, methods supervised{dpo|
  reinforcement} hyperparameters, integrations (wandb), checkpoints + permissions.
- Conversations (`conversations/` 24): Conversation{id,created_at,metadata},
  items, message/output_text/refusal/summary_text contents — the stateful wrapper
  around Responses input/output items.
- Video (`video*.py`): Video{id,model(sora-2*),seconds(4|8|12),size,prompt?,status
  queued|in_progress|completed|failed,progress,error?}; create/edit/extend/remix params;
  character params; download variants (video|thumbnail|spritesheet).

### 1.13 Realtime (157 files — present; DDGS has no voice path)

- Session/request: `RealtimeSessionCreateRequest{model?, modalities?, voice?, instructions?,
  input_audio{format,transcription{model,language?,prompt?},noise_reduction?,turn_detection?},
  output_audio{format,voice?,speed?}, tools?, tool_choice?, tracing?, truncation?,
  max_response_output_tokens?, ...}`; transcription sessions; calls (accept/create/refer/reject).
- Client events: conversation_item create/delete/retrieve/truncate, input_audio_buffer
  append/clear/commit (+dtmf/timeout/speech_started|stopped), output_audio_buffer.clear,
  response create/cancel; server events: conversation created/item added|done|created|
  deleted|truncated, input_audio_buffer committed/cleared/speech_started|stopped,
  transcription delta/completed/failed (+segments), response created|done (+status, usage
  {input_token_details,text_tokens?,audio_tokens?,cached_tokens?, output_token_details}),
  audio delta/done + transcript delta/done, text delta/done, function_call_arguments
  delta/done, mcp events, rate_limits.updated, error.
- Conversation items: user|assistant|system messages, function_call, function_call_output,
  input_audio; tools: function (+strict), mcp (+approval flows); reasoning config
  (`RealtimeReasoning{effort?}`), tracing (`RealtimeTracingConfig`), truncation
  (incl. retention_ratio).

### 1.14 Admin / webhooks / misc top-level

- `admin/` (160 files): org/project/user/group/role/invite/api-key/service-account/
  certificates/spend-limits+alerts/rate-limits/model+hosted-tool permissions/data-retention
  CRUD params+responses; usage endpoints (completions/embeddings/images/audio TBD
  speeches+transcriptions/moderations/vector-stores/file-search/web-search/code-interpreter/
  costs) with `*_params` (bucket scoping) + `*_response` (bucketed aggregates).
- `webhooks/` (19): batch cancelled|completed|expired|failed, eval.run canceled|failed|
  succeeded, fine_tuning.job cancelled|failed|succeeded, response cancelled|completed|
  failed|incomplete, realtime/live call incoming, safety_identifier.blocked; each
  {id, created_at, data{id|session_id}, type}; `unwrap_webhook_event`.
- Top-level misc: legacy `Completion` (text_completion) + params (best_of, echo, suffix,
  logprobs int...), `ContentProvenanceCheck` (c2pa|synthid results), websocket
  `WebSocketConnectionOptions` + `ReconnectingEvent/Overrides` (recoverable close codes).

## 2. WIRE FEATURES DDGS NEVER USES (ranked by UX impact)

1. **Strict JSON-schema outputs** — `response_format=ResponseFormatJSONSchema{name*,
   schema*, strict:true}` + `FunctionDefinition{strict:true}` on tool params.
   How: kani accepts per-call hyperparams; pass `response_format` for summary turns
   and `strict:true` + full JSON schemas (additionalProperties:false) on the search/
   download tool specs. Unlocks: tool args that parse first time, machine-grade
   overviews/summaries (typed cards) instead of regex-scraped prose.
2. **Web search tool types** — chat `web_search_options{search_context_size,
   user_location}` and Responses `web_search`/`web_search_preview` (+filters.
   allowed_domains) with `url_citation` annotations already typed in
   `ChatCompletionMessage.annotations`.
   How: offer a router model with a search tool, set `search_context_size:high`
   + user_location, render returned `annotations[].url_citation` as tap-to-open
   sources. Unlocks: cited answers with zero DDGS scraping for fresh topics.
3. **File inputs (send scraped files)** — user content part `File{file_data|file_id|filename}`
   and Responses `input_file`/`input_image`/`input_audio` + vector-store-backed
   `file_search` tool with ranked results.
   How: DDGS already scrapes pages/downloads files — base64 the fetched article or
   upload once (`FilePurpose user_data|vision`) and attach `file_id` to the turn.
   Unlocks: summarize-this-PDF/page Q&A grounded on the real bytes, not pasted excerpts.
4. **Reasoning shapes for a richer Thinking UI** — `reasoning_effort`
   (none|minimal|low|medium|high|xhigh|max), Responses `Reasoning{effort,
   generate_summary, summary}` + `ResponseReasoningItem{summary[], content[],
   encrypted_content?}`, chat `CompletionUsage.completion_tokens_details.
   reasoning_tokens`, `verbosity low|medium|high`.
   How: pass `reasoning_effort:low|medium` on hard turns; read `reasoning_tokens`
   for "thought for N tokens" headers; prefer `summary[]` over raw-stream sniffing.
   Unlocks: controllable depth/cost per turn and a Thinking block fed by typed fields.
5. **Annotations/citations already on the wire** — `ChatCompletionMessage.annotations[]`
   (url_citation) and Responses text annotations (file/url/container-file citations,
   file_path). DDGS renders `![desc](image_url)` manually but never reads these.
   How: after each turn, iterate `message.annotations` and append a Sources row
   (title + url). Unlocks: trustworthy answer cards with one code path.
6. **Refusal + moderation fields** — `message.refusal`, chunk `delta.refusal`,
   `ResponseOutputRefusal`, create-param `moderation{model,policy score|block}` with
   typed `Moderation{...}` echo on responses.
   How: check `refusal` before `content`; surface the kani-mapped refusal distinctly
   from errors (it already maps it — keep the wording). Unlocks: honest "model declined"
   states instead of blank/error bubbles.
7. **service_tier + prompt-caching fields** — `service_tier auto|default|flex|scale|
   priority|fast` (echoed on responses), `prompt_cache_key`, `prompt_cache_options
   {mode implicit|explicit, ttl 30m}`, `prompt_cache_retention in_memory|24h`,
   `prompt_cache_breakpoint{mode:explicit}` per content part, usage
   `prompt_tokens_details{cached_tokens, cache_write_tokens}`.
   How: send stable `prompt_cache_key` per conversation + explicit breakpoints after
   system prompt; read `cached_tokens` in the credit meter. Unlocks: cheaper long
   chats and a "cache hit X%" indicator.
8. **Audio modalities** — `modalities:[text|audio]`, `audio{voice,format}`,
   `ChatCompletionAudio{id,data,expires_at,transcript}`, input-audio parts,
   full TTS/STT/transcribe params, Realtime session types.
   How: `modalities:["audio"]` + voice on a read-aloud turn; play `audio.data`.
   Unlocks: spoken answers / voice input (needs Flet audio playback work).
9. **logprobs / top_logprobs** — `logprobs:true` + `top_logprobs:int` (chat) /
   `top_logprobs` (responses), typed per-token `ChatCompletionTokenLogprob` and
   `ResponseOutputText.logprobs[]`, streaming `ChoiceLogprobs`.
   How: enable on "am I sure?" turns, average token logprob into a confidence dot.
   Unlocks: visible answer-confidence signal; doubles as eval data.
10. **Multi-choice n + prediction + misc incrementals** — `n` (parallel candidates),
    `prediction{content}` (regeneration discount), `seed`, `stop`, `logit_bias`,
    `store/metadata/user/safety_identifier` (attribution/abuse tracking),
    `max_completion_tokens` vs legacy `max_tokens`, `parallel_tool_calls:false`
    (serialize DDGS tool batches), `stream_options.include_obfuscation`,
    `include[]` (responses: file_search/web_search results echo),
    `max_tool_calls`, `truncation`, `previous_response_id`/conversations (server-side
    history instead of resending transcripts).
    How: each is one kwarg through kani hyperparams. Unlocks: "3 answer drafts"
    UX, cheaper rewrites, deterministic runs, serialized tool batches.

## 3. GOTCHAS

- **TypedDict vs BaseModel**: `*Params`/`*Param` files are request-side `TypedDict`s
  (what you send); same-named files without the suffix are response-side pydantic
  `BaseModel`s (what you read). Field optionality often differs between the pair
  (e.g. Responses `ResponseUsage` details required vs chat `CompletionUsage` optional).
- **NotGiven sentinel** (`openai/_types.py:133`): every optional request field defaults
  to `NOT_GIVEN`, not `None`. `None` is a *meaningful* value (e.g. `timeout=None` =
  no timeout; `stream=None` unset). Passing `None` explicitly sends `null` on the wire —
  omit-or-`not_given` to leave a default alone. kani's `hyperparams | hyperparams`
  merge only forwards what DDGS sets, which is why this works today.
- **Required vs optional**: `Required[...]` inside a TypedDict marks must-send keys
  (`messages`, `model`, tool `function.name`, `tool_call_id`...); everything else is
  `NotGiven`-defaulted. `total=False` TypedDicts still accept any subset at runtime —
  the server, not the client, enforces presence.
- **`strict` defaults off**: both `FunctionDefinition.strict` and JSON-schema `strict`
  are opt-in; without them the schema is a hint, not a guarantee. Structured-output
  guarantees additionally need `additionalProperties:false` + all keys in `required`.
- **Deprecated aliases**: `function_call`/`functions` params, `ChatCompletionMessageToolCall`
  (= function variant of the union), `ChatCompletionToolParam` (= function-tool param),
  legacy `Completion` (text_completion) params (`best_of`, `echo`, `suffix`), stored
  `_top` re-exports (`chat_model.ChatModel`). `ChatCompletionResponse` removed in this
  version — import from `openai.types.chat.chat_completion`.
- **Beta mirrors GA**: `beta/*` duplicates Responses/assistants types under `Beta*`
  names; prefer the GA `responses/*` + `conversations/*` paths for new code.
- **Responses != Chat**: DDGS's router serves Chat Completions only; the entire
  Responses/Realtime/Assistants vocabulary will 400 until the router exposes it.
  Gate any adoption behind a capability check.
- **Chunk deltas are sparse**: any `ChoiceDelta` field (content/refusal/tool_calls/
  role) may be absent per frame; `finish_reason` arrives on the terminal frame;
  `usage` only streams when `stream_options.include_usage=True` (already set).

## 4. COVERAGE

- Files read: **1298 / 1298** (`__pycache__` excluded) — every `.py` under
  `openai/types/` parsed via AST and every class/field extracted; zero parse errors.
- Areas: _top 105 files/159 classes, admin 160/420, audio 21/31, beta 409/1141,
  chat 53/104, containers 7/5, conversations 24/26, evals 17/128, fine_tuning 37/43,
  graders 15/30, realtime 157/224, responses 220/544, shared 19/13, shared_params 15/10,
  skills 7/5, uploads 3/2, vector_stores 10/12, webhooks 19/36.
- Method: scripted AST extraction (class bases + annotated fields + aliases/constants)
  into per-area dumps, then targeted reads of chat/shared/responses/audio/_top plus
  consumer verification (`src/services/ai_service.py`, `kani_backend.py`,
  `reasoning.py`, kani `engines/openai/engine.py`) and `openai/_types.py` NotGiven.
- Honesty note: per-file dumps were machine-extracted (one line per class with all
  fields) rather than hand-read line-by-line; prose above was verified against those
  dumps. Truncated alias literals (model pin lists) are summarized, not exhaustive.
