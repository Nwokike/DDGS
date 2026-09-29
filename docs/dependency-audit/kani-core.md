# kani (core) dependency audit — v1.10.0

Consumer: DDGS (Flet 1.0.1 search/download/AI-assistant). DDGS usage today: `src/services/kani_backend.py`
(`Kani` subclass `DDGSKani`, `full_round_stream`, `chat_round_stream`, `AIFunction(name, desc, json_schema)`,
`ChatMessage.user/assistant`, `manager.message()/completion()`, `manager.role`, `do_function_call` override,
`ToolSpec` is DDGS-local, not kani) + `src/services/chat_agent.py` (builds specs, emits, approval gate, billing).
MCP is explicitly OUT OF SCOPE for the app — `mcp.py` is inventoried only (§1.10), no adoption proposed.

---

## 1. COMPLETE API INVENTORY

### 1.1 `__init__.py` — re-export surface

- `Kani` — the agent class (see §1.2).
- `AIFunction` — tool wrapper (see §1.3).
- `AIParam` — `Annotated[..., AIParam(desc, title)]` parameter metadata (see §1.3).
- `ai_function` — decorator marking a `Kani` method as a tool (see §1.3).
- `FunctionCallResult(is_model_turn, message)` / `ExceptionHandleResult(should_retry, message)` — tool outcomes (see §1.5).
- `ChatMessage` / `ChatRole` / `FunctionCall` / `ToolCall` / `MessagePart` — chat state (see §1.4).
- `ReasoningPart` — from `.parts`; tagged substring part for reasoning traces (subclass of `MessagePart`).
- `PromptPipeline` — from `.prompts`; composable prompt-building pipeline.
- `chat_in_terminal(ai, ...)`, `chat_in_terminal_async(ai, ...)` — from `.utils.cli`; REPL chat loops for debugging.
- `format_stream(stream)`, `print_stream(stream)`, `format_width(s)`, `print_width(s)` — from `.utils.cli`; stream consume/format helpers.
- `engines`, `exceptions`, `utils` — subpackages/modules; `__version__` (`"1.10.0"`, see §1.9).

### 1.2 `kani.py` — `class Kani`

Constructor — `Kani(engine, system_prompt=None, always_included_messages=None, desired_response_tokens=None, chat_history=None, functions=None, retry_attempts=1)`:

- `engine: BaseEngine` — the LM backend; also supplies `max_context_size`, `prompt_len`, `token_reserve`, `function_token_reserve`, `disable_function_calling_kwargs`. DDGS USES (custom `ReasoningEngine`).
- `system_prompt: str | None` — steering prompt, stripped, stored as `ChatMessage.system` inside `always_included_messages`, never in `chat_history`. DDGS USES (clock-augmented `SYSTEM_PROMPT`; `None` in tool-less `complete()` when empty).
- `always_included_messages: list[ChatMessage] | None` — prefix kept on every prompt; newest history evicted first, these never evicted; not in `chat_history`. DDGS DOES NOT USE.
- `desired_response_tokens: int | None` — headroom kept as `max_context_size − tokens`; default `min(max_context_size // 10, 8192)`; `get_prompt` evicts history to fit. DDGS DOES NOT SET (relies on `DEFAULT_CONTEXT = 131072` so eviction never triggers).
- `chat_history: list[ChatMessage] | None` — starting history (system/always-excluded); **same list object is mutated** unless caller copies. DDGS USES (passes fresh `_to_history()` list each turn — safe).
- `functions: list[AIFunction] | None` — dynamic tools, keyed by name into `self.functions`; plus auto-scan of `@ai_function` methods on the subclass (duplicate name raises `ValueError`; `property` members skipped). DDGS USES (dynamic list only, no `@ai_function` methods).
- `retry_attempts: int` — per-full-round self-correction budget for failed tool calls (see §4). DDGS SETS `retry_attempts=1`.

Instance state: `engine`, `system_prompt`, `max_context_size` (= engine's), `desired_response_tokens`, `always_included_messages`, `chat_history`, `lock: asyncio.Lock`, `retry_attempts`, `functions: dict[str, AIFunction]`.

Entrypoints (all accept `query: QueryType = str | Sequence[MessagePart|str] | None`; `None` = generate with no new user message; every non-`None` query is appended to history first):

- `async chat_round(query, **kwargs) -> ChatMessage` — single model call, **no functions** (`include_functions=False` forced); warns if tools registered and not silenced (see §4). DDGS DOES NOT USE (uses stream variant).
- `async chat_round_str(query, **kwargs) -> str` — `chat_round` returning only `msg.text`. UNUSED.
- `chat_round_stream(query, **kwargs) -> StreamManager` — sync-returned manager; preflight runs lazily inside iteration; holds `self.lock` for the whole stream; `after=add_completion_to_history`. DDGS USES in `complete()` with `query=None`.
- `async full_round(query, *, max_function_rounds=None, **kwargs) -> AsyncIterable[ChatMessage]` — agent loop; yields every non-user message (assistant + function results); parallel tool batch via `asyncio.gather`; `DummyStream` not used here (raw messages). DDGS DOES NOT USE (uses stream variant).
- `async full_round_str(query, message_formatter=assistant_message_contents, *, max_function_rounds=None, **kwargs) -> AsyncIterable[str]` — `full_round` mapped through formatter; default yields assistant text only (falsy formatter results skipped). UNUSED. (Class docstring also mentions a `function_call_formatter` knob — **not present** in this version's signature; `message_formatter` is the only hook.)
- `async full_round_stream(query, *, max_function_rounds=None, **kwargs) -> AsyncIterable[StreamManager]` — agent loop yielding one manager per step; model steps yield live `StreamManager` (`.role is ASSISTANT`), tool results yield `DummyStream` (`.role is FUNCTION`); `max_function_rounds` caps tool rounds (warn + final answer without tools). DDGS USES (`max_tokens=budget` passed as engine kwarg; `max_function_rounds` never set — outer `steps >= max_iters` check instead).
- `async prompt_token_len(messages, functions=None, **kwargs)` — engine token count for a prompt (awaits if awaitable). UNUSED.
- `async get_model_completion(include_functions=True, **kwargs) -> BaseCompletion` — read-only model call; logs via `kani.messages`; does **not** touch history. UNUSED.
- `async get_model_stream(include_functions=True, **kwargs) -> AsyncIterable[str | BaseCompletion]` — streaming twin of above; read-only. UNUSED directly (consumed internally by `_full_round`).
- `async get_prompt(include_functions=True, **kwargs) -> list[ChatMessage]` — builds the prompt under `max_context_size − desired_response_tokens`; always prefix + newest-fitting history slice (sequential search, newest-first); raises `PromptTooLong` (reserve too big), `MessageTooLong` (last message alone too big), `ValueError` (engine counter broken). Overridable. UNUSED as override; runs internally every step.
- `get_enabled_functions() -> list[AIFunction]` — `[f for f in functions.values() if f.enabled]`. Overridable. UNUSED as override.
- `async do_function_call(call: FunctionCall, tool_call_id=None) -> FunctionCallResult` — resolves one call: `NoSuchFunction` if unknown; `await f(**call.kwargs)`; `WrappedCallException(f.auto_retry, e)` on error; result coercion: `ChatMessage`→as-is (+tool_call_id), `list[MessagePart]`→function message, pydantic model→JSON, dict/list→`json.dumps` (fallback `str`), else `str()`; paragraph-aware `auto_truncate` applied; `is_model_turn = (f.after == ASSISTANT)`. DDGS OVERRIDES (sets `ContextVar` tool_call_id, delegates to `super()`).
- `async handle_function_call_exception(call, err: FunctionCallException, attempt: int, tool_call_id=None) -> ExceptionHandleResult` — default: `NoSuchFunction`→"not defined, only use provided functions"; else error text; `should_retry = attempt < retry_attempts and err.retry`. DDGS DOES NOT OVERRIDE (tool bodies never raise by design; only unknown-tool path can reach it).
- `async add_completion_to_history(completion: BaseCompletion)` — `add_to_history(completion.message)`, returns message; stream `after`-callback. Not overridden.
- `async add_to_history(message: ChatMessage)` — `chat_history.append(message)`; async for I/O-capable overrides. Not overridden (DDGS appends directly once for the length-retry nudge).
- `save(fp, *, save_format=None, **kwargs)` — persist `always_included_messages + chat_history` to `.kani`/JSON (format from extension). UNUSED.
- `load(fp, **kwargs)` — restore both lists, **overwriting** current state. UNUSED.
- `_auto_truncate_message(msg, max_len)` — internal paragraph-aware cutter (`\n\n`→`\n`→`. `→`, `→` `, then hard chop with `...`). Runs via `do_function_call` when set.
- Deprecated: `always_len` property (warns; use `prompt_token_len`), `message_token_len(message)` (warns; engine-local estimate). UNUSED.

### 1.3 `ai_function.py` — tools

- `class AIFunction(inner, after=ChatRole.ASSISTANT, name=None, desc=None, auto_retry=True, json_schema=None, auto_truncate=None, enabled=True)` — wrapper; `inner` wrapped in pydantic `validate_call`; async run natively, sync run via `asyncio.to_thread`; warns if no description. DDGS USES with `(inner, name, desc, json_schema)` only.
  - `after: ChatRole` — who speaks next (`ASSISTANT` default → model continues; `USER`/`FUNCTION` end the model turn). DDGS NEVER SETS (always default).
  - `auto_retry: bool` — feeds `WrappedCallException.retry`; model may retry on arg errors. DDGS NEVER SETS (default `True`, inert since bodies never raise).
  - `json_schema: dict | None` — override auto-generated schema (`create_json_schema()` from signature + `AIParam`). DDGS ALWAYS SETS (verbatim OpenAI `parameters` doc).
  - `auto_truncate: int | None` — max **characters** before paragraph-aware truncation + `"..."` (v1.7+: chars, not tokens). DDGS NEVER SETS (manual `[:3000]`/`TOOL_OUTPUT_CAP` slicing instead).
  - `enabled: bool` — excluded from prompt but still executable if called. DDGS NEVER SETS.
  - `async __call__(*args, **kwargs)`; `get_params() -> list[AIParamSchema]` (rejects positional-only/variadic/unannotated params with `FunctionSpecError`); `create_json_schema(include_desc=False)` (`functools.cache`); `__repr__`.
- `ai_function(func=None, *, after, name, desc, auto_retry, json_schema, auto_truncate, enabled)` — decorator for static `Kani`-subclass methods; stores `__ai_function__` dict consumed by `Kani.__init__` scan. DDGS DOES NOT USE (dynamic `AIFunction(...)` list instead).
- `class AIParam(desc, *, title=None)` — `Annotated[T, AIParam(...)]` per-parameter help shown to the model. DDGS DOES NOT USE (schemas hand-written).
- `get_aiparam(annotation) -> AIParam | None` — extracts `AIParam` from `Annotated`. Internal; unused by DDGS.

### 1.4 `models.py` — chat state

- `MESSAGEPART_TYPE_KEY = "__kani_messagepart_type__"` — serdes discriminator for `MessagePart` subclasses.
- `MessagePartType = MessagePart | str`; `QueryType = str | Sequence[MessagePartType] | None` — every round entrypoint accepts plain strings, part lists, or `None`. DDGS passes only `str`/`None`.
- `BaseModel.copy_with(**new)` — `model_copy(update=...)` **without validation**. Base of all kani models.
- `enum ChatRole` — `SYSTEM` / `USER` / `ASSISTANT` / `FUNCTION`, each with docstring. DDGS uses `user/assistant/function` paths; never constructs `SYSTEM`/`FUNCTION` directly.
- `class FunctionCall(name: str, arguments: str)` — one call request; `.kwargs` (cached JSON decode); `.with_args(name, **kwargs)` constructor (for few-shot prompts). DDGS never constructs (receives from engine).
- `class ToolCall(id, type="function", function)` — ID-tagged call; `.from_function(name, *, call_id_=None, **kwargs)`; `.from_function_call(call, call_id_=None)`. DDGS never constructs (reads `message.tool_calls`; IDs via own `ContextVar` bridge).
- `class MessagePart(extra={})` — multimodal/rich-part base; `__str__` **warns** and degrades; subclass registry (`__init_subclass__`) with duplicate-definition warning; type-tagged serdes (`_serialize`/`_validate`, `MissingMessagePartType` if loader lacks the class); `extra` persisted best-effort only. DDGS DOES NOT USE (all-string content).
- `class ChatMessage(role, content, name=None, tool_call_id=None, tool_calls=None, is_tool_call_error=None, extra={})`:
  - `.text -> str | None` — string content, concatenated parts, `None` for pure call requests. DDGS USES (`message.text`).
  - `.parts` — read-only list view (`[]` when content `None`); mutate via `copy_with`. UNUSED.
  - `.function_call` — first call compat accessor; **warns** on multi-call messages — prefer `.tool_calls`. DDGS uses `.tool_calls` (correct).
  - `.is_tool_call_error: bool | None` — set by `_full_round` (`False` success / `True` handled exception) unless impl preset. DDGS NEVER READS.
  - Constructors `system(content)`, `user(content)`, `assistant(content|None)`, `function(name, content, tool_call_id=None)` — all accept `str | Sequence[parts]`. DDGS uses `user()` (+`assistant()` in history rebuild).
  - `copy_with(**new)` — accepts `text=`/`parts=`/`content=` (exactly one) and `function_call=`/`tool_calls=` (exactly one). UNUSED.

### 1.5 `internal.py` — outcomes

- `HasMessage` (ABC, `.message: ChatMessage`).
- `FunctionCallResult(is_model_turn: bool, message)` — next-turn flag + history message. DDGS never constructs (kani builds them; DDGS reads `.role`/`.message()` off managers instead).
- `ExceptionHandleResult(should_retry: bool, message)` — retry flag + error message. Same — never constructed (default handler suffices while bodies never raise).

### 1.6 `streaming.py` — streams

- `class StreamManager(stream_iter, role, *, after=None, lock=None)` — single-use token stream; `after` coro runs on completion; optional lock held for whole iteration; token-then-final-`BaseCompletion` protocol (bare-token streams auto-concatenated into a message, `.strip()`ed); `TypeError` on bad yields, `RuntimeError` on post-completion yields or double-iteration.
  - `.role: ChatRole` — known **before** iteration (DDGS USES to separate model vs tool managers).
  - `async for token in mgr` → `str` tokens; `await mgr` ≡ `await mgr.message()`; `await mgr.completion() -> BaseCompletion`; `await mgr.message() -> ChatMessage` (auto-consumes if never iterated). DDGS USES all three (`completion()` for `finish_reason`, `message()` for text/tool calls).
- `class DummyStream(message)` — pre-resolved result masquerading as a stream (yields `message.text` once + `Completion`); `await .message()` returns the original object. DDGS CONSUMES (yielded per tool result; `await manager.message()`, skips billing) but never constructs.

### 1.7 `exceptions.py`

- `KaniException` base. `PromptTooLong` (prompt won't fit / reserve too big). `MessageTooLong` (last message alone too big). `FunctionCallException(retry: bool)` base for call errors. `WrappedCallException(retry, original)` (tool raised; `str()` = original's; `retry` = `auto_retry`). `NoSuchFunction(name)` (`retry=True` always). `FunctionSpecError` (bad `@ai_function` signature). `MissingModelDependencies` (engine extras absent). `PromptError` (invalid model input). `MissingMessagePartType(fqn, msg)` (+`.fqn`; unknown part type on load). DDGS catches none directly (OpenAI ladder mapped instead; kani-level errors fall to the generic branch).

### 1.8 `json_schema.py`

- `REF_TEMPLATE = "#/$defs/{model}"` — `$ref` template (matches pydantic ≥2.1; downstream engines rely on it).
- `AIParamSchema(name, t, default, aiparam, inspect_param)` + `.required` / `.origin_type` / `.description` / `.title`. Internal to schema gen.
- `JSONSchemaBuilder` (pydantic `GenerateJsonSchema` subclass; drops unset titles; inlines singleton `$ref`s, threshold 2). Internal.
- `create_json_schema(params, name="_FunctionSpec", desc=None) -> dict`. Internal (result cached on `AIFunction`). DDGS bypasses all of it via explicit `json_schema=`.

### 1.9 `_optional.py` / `_version.py`

- `_NotInstalledHelper(pkg)` — raises `ImportError` with install hint on any attribute access.
- `multimodal_core`, `multimodal_cli` (+`has_multimodal_core: bool`) — real `kani.ext.multimodal_core` if `kani-multimodal-core` installed, else helper. DDGS does not use (no image/audio parts).
- `__version__ = "1.10.0"`.

### 1.10 `mcp.py` — INVENTORY ONLY (out of scope, do not adopt)

- `async tools_from_mcp_servers(mcp_servers, allowed_tools=None, blocked_tools=None, *, component_name_hook=None)` — async context manager: connects `ClientSessionGroup` to each MCP server, converts every tool to `AIFunction(name, desc, json_schema=inputSchema)` with a shared `_call_mcp_tool` body (single text block → bare string; multi-block → list of `str | ImagePart | AudioPart` via `multimodal_core`); `allowed/blocked_tools` mutually exclusive (both set → `ValueError`); `component_name_hook(tool_name, serverInfo)` renames to avoid cross-server collisions. Requires `kani[mcp]` (+`kani-multimodal-core` for image/audio results) or raises `ImportError`. DDGS must not use per owner decision.

---

## 2. HOOK/EXTENSION POINTS

| Hook / knob | What it does | How to use | DDGS today |
|---|---|---|---|
| Subclass `Kani` | Full control; `__init__` auto-registers `@ai_function` methods | `class DDGSKani(Kani)` | USES (tool_call_id bridge only) |
| `do_function_call(call, tool_call_id)` | Wrap/instrument/replace tool execution; must raise `FunctionCallException` subtypes for retry flow | `await super().do_function_call(...)` inside timing/logging | OVERRIDDEN (ContextVar only; no timing) |
| `handle_function_call_exception(call, err, attempt, tool_call_id)` | Custom error prompt, logging, retry policy | Return `ExceptionHandleResult(should_retry, message)` | NOT overridden (default OK while bodies never raise) |
| `get_prompt(include_functions, **kwargs)` | Replace context packing (summarization, retrieval injection, per-round pinning) | Override; keep always-prefix contract | NOT overridden |
| `get_enabled_functions()` | Dynamic tool gating (tiers, model caps, A/B) | Override or flip `AIFunction.enabled` | NOT used (static 11-tool list) |
| `add_to_history(msg)` / `add_completion_to_history(c)` | Persist/log every message (DB, analytics, token counts) | Override; keep append semantics | NOT overridden |
| `get_model_completion/stream` | Dry-runs, shadow scoring, logging without mutating state | Call directly (read-only) | NOT used |
| `include_functions` kwarg | Per-call tool visibility (`chat_round` forces `False` + warns) | `full_round(..., include_functions=False)` for a tool-free final pass | NOT used |
| `engine.disable_function_calling_kwargs` | Kwargs merged to silence tools after errors / at round cap | Provided by engine; kani applies automatically | Inherited, never set directly |
| `max_function_rounds` | Native cap on tool rounds per turn (warns, then final answer tool-free) | `full_round_stream(q, max_function_rounds=N)` | NOT used (outer `steps >= max_iters`) |
| `message_formatter` (`full_round_str`) | String projection of each message (default `assistant_message_contents`) | Pass custom formatter for non-stream consumers | NOT used (no non-stream path) |
| Stream `after` callback | Coro run with completion after consume (`add_completion_to_history` default) | `StreamManager(iter, role, after=...)` for custom commit | NOT used (defaults) |
| `AIFunction.after` | `ASSISTANT` → model continues; `USER`/`FUNCTION` → yield turn to user | `@ai_function(after=ChatRole.USER)` for confirm-gated tools | NOT used (all default) |
| `AIFunction.auto_retry` | Whether arg/exec errors are retried (`WrappedCallException.retry`) | `False` for non-idempotent writes | NOT used (default `True`, inert) |
| `AIFunction.json_schema` | Verbatim schema override | Pass OpenAI `parameters` doc | USES for all 11 tools |
| `AIFunction.auto_truncate` (chars) | Paragraph-aware result cap + `"..."` inside `do_function_call` | `AIFunction(..., auto_truncate=3000)` | NOT used (manual slicing) |
| `AIFunction.enabled` | Hidden from prompt, still callable | Flip per model/tier | NOT used |
| `retry_attempts` (+`err.retry`) | `should_retry = attempt < retry_attempts and err.retry`; consecutive-error counter resets on success; exhausted → next model turn runs tool-free | Raise for app rewrite | SET to 1; only unknown-tool path can trigger |
| `is_tool_call_error` | `False`/`True` stamped on every result message (preset values respected) | Branch UI/analytics on it | NEVER READ |
| `QueryType` (`str \| parts \| None`) | Multimodal/composed queries; `None` = no new user turn | `chat_round_stream(None, ...)` | `None` USED in `complete()`; parts unused |
| `save()` / `load()` | `.kani`/JSON persistence of always-prefix + history | Save per conversation, load on reopen | NOT used (custom dict store) |

---

## 3. LATENT CAPABILITIES FOR DDGS (ranked by UX impact)

1. **Conversation persistence via `save()`/`load()`** — `.kani`/JSON round-trip of prefix + history, including tool-call IDs and typed parts. *Feature:* replace the hand-rolled dict transcript in `chat_screen` with `kani.save(conversation_id)` / `.load()` on reopen — restores exact tool attribution and retries, kills the `_to_history` string-only downcast that drops IDs.
2. **`always_included_messages` pinning** — survive eviction while fresh history is cut first. *Feature:* pin the RELATED-line format + "cite [1][2] from results only" micro-rules outside the giant system prompt, so long research turns degrade gracefully instead of forgetting the answer contract first.
3. **`auto_truncate` paragraph-aware caps** — sentence-boundary cutter with `"..."`, applied inside `do_function_call` with a warning log. *Feature:* set `auto_truncate` per tool (e.g. 3000 for `fetch_page`, 800 for searches) and delete the lossy `[:3000]`/`TOOL_OUTPUT_CAP` slicing that today cuts mid-sentence and hides evidence the model needs for citations.
4. **Dynamic tool gating (`enabled` / `get_enabled_functions`)** — hide tools per model, tier, or approval state without rebuilding specs. *Feature:* free-catalog models that mangle `schedule_scrape` args stop seeing it; write tools auto-hide until credits/approval prechecks pass — fewer declined-approval dead ends.
5. **Native `max_function_rounds`** — kani warns and takes a final tool-free answer when the cap hits. *Feature:* pass `max_function_rounds=AGENT_MAX_TOOLS`-adjacent budget so "let me search…" loops terminate inside the runtime with a graceful summary instead of the outer `break` that can leave a turn with no final text (the empty-bubble path).
6. **`AIFunction(after=ChatRole.USER)` turn-pausing** — tool result yields the turn to the user instead of the model. *Feature:* wire the existing approval gate natively: write tools return "awaiting approval", user approves in-chat, next user message resumes — no out-of-band `ask_confirm` plumbing.
7. **`handle_function_call_exception` override** — custom retry prompts ("user declined this action — do not retry, summarize instead"). *Feature:* today's declined-approval payload is just another JSON blob; a handler can mark `is_tool_call_error=True` + `should_retry=False` so the model stops re-proposing the declined crawl.
8. **`is_tool_call_error` UI branching** — already stamped on every result. *Feature:* red vs green step rows and honest `step_error` for model-visible failures instead of today's all-green `step_done`.
9. **Non-stream paths (`full_round`, `full_round_str` + `message_formatter`)** — same loop, no SSE. *Feature:* scheduled-scrape digest worker and share-sheet text export reuse the exact agent (custom formatter emitting `pretty_label` lines + final answer) with zero streaming code.
10. **`prompt_token_len` pre-flight meter** — exact engine token count before calling. *Feature:* "context 80% full — older turns will be summarized" nudge and smarter `AGENT_HISTORY_MESSAGES` trimming (tokens, not message count).
11. **`desired_response_tokens` tuning** — explicit headroom per model. *Feature:* reasoning models that burned the budget pre-text (today's double-budget retry hack) get headroom up front per `tap.last_model`.
12. **Low-level `get_model_completion` / `get_model_stream`** — read-only calls that never touch history. *Feature:* "regenerate" preview and RELATED-query pre-generation without polluting the transcript.
13. **Rich `ChatMessage.parts` + `ReasoningPart`/`PromptPipeline`** — typed spans beyond strings. *Feature:* render the single `![desc](image_url)` result as a real Flet image card from a part instead of markdown-parsing the model's prose; fold `ThoughtTap` deltas into `ReasoningPart`s the model can also see.
14. **Few-shot tool shaping (`ToolCall.from_function` / `FunctionCall.with_args`, `copy_with`)** — seed history with ideal call examples. *Feature:* one canonical `search_images → embed one image` example in fresh sessions teaches the gallery-vs-singleton rule better than the system-prompt paragraph.
15. **`chat_round_str` / `get_prompt` introspection** — one-shot text answers and prompt inspection. *Feature:* settings-screen "test my model" button and a debug view showing exactly what the model saw (prefix vs kept history).

---

## 4. GOTCHAS

- **Locking — never abandon an `async-for` from outside mid-chunk.** `Kani.lock` is held for the *entire* `_full_round` (all model + tool rounds) and, for `chat_round_stream`, for the whole `StreamManager` iteration. Breaking the loop abandons the generator while it still owns the lock / pending `after` commit: history may miss the in-flight message and the next turn can deadlock or double-append. DDGS's pattern is the correct one — cancellation via `on_token raising` + boundary checks *between* managers (a yielded-but-uniterated manager has made no HTTP request yet, so stopping there is free). Keep it.
- **History is a shared mutable list.** `chat_history` passed to the constructor is stored *by reference*; `add_to_history` appends the user query *before* the model call, and stream results commit in the `after` callback only after full consumption. Copy (`mykani.chat_history.copy()`) when forking; never mutate `chat_history` mid-round; DDGS's direct `chat_history.append` nudge is safe only because it runs between managers.
- **`chat_round*` with tools warns.** Any registered function + no explicit `include_functions` → `UserWarning` telling you to use `full_round` (silence with `include_functions=False`). Noisy-log risk if a tool-less path ever shares a kani with tools — DDGS avoids it by constructing a tool-free `Kani` in `complete()`.
- **Retry semantics are narrower than they look.** Counter tracks *consecutive error rounds* (resets on success); `should_retry = attempt < retry_attempts and err.retry`; `NoSuchFunction.retry` is always `True`, `WrappedCallException.retry` is `f.auto_retry`; exhausted retries run the next model turn **tool-free** via `engine.disable_function_calling_kwargs`. With DDGS bodies never raising, `retry_attempts=1` only covers unknown-tool hallucinations — correct, don't raise it expecting tool-error retries that can't happen.
- **Pydantic `validate_call` wraps every tool.** Args are coerced/validated *before* the body runs (a coercion failure surfaces as `WrappedCallException`, i.e. model-retryable, not an app error); sync bodies run in `asyncio.to_thread`; positional-only/variadic/unannotated params raise `FunctionSpecError` at schema build. DDGS's `inner(spec=spec, **kwargs)` + `**kwargs: Any` shape is compatible — but keep bodies total (never raise) or the retry/blog flow changes meaning.
- **More warnings that bite:** `MessagePart.__str__` warns on string coercion (rich data lost); `@ai_function`/`AIFunction` without description warns; `max_function_rounds` hit warns with the pending calls; `auto_truncate` warns per truncation and hard-chops when no chunk boundary fits; `get_prompt` engine counter errors log + escalate to `ValueError`/`PromptTooLong`/`MessageTooLong` — catch the latter two around longANS turns if eviction is ever enabled.
- **`copy_with` skips validation; `extra` is best-effort.** Exactly one of `content/text/parts` and one of `function_call/tool_calls` may be set; `extra` dict values that aren't JSON/pydantic-safe degrade to `repr` on save. Don't stash handles or clients in `extra`.

---

## 5. COVERAGE

- Files read: 10 / 10 — `__init__.py`, `kani.py`, `ai_function.py`, `models.py`, `streaming.py`, `internal.py`, `exceptions.py`, `json_schema.py`, `_optional.py`, `_version.py`, plus `mcp.py` (inventory only, out of scope). `__pycache__` skipped.
- Re-export surface (`ReasoningPart`, `PromptPipeline`, `utils.cli` helpers) noted from `__init__.py`; deep-dives on `engines/`, `parts/`, `prompts/`, `utils/` not required by this audit's file list.
- DDGS usage verified in `src/services/kani_backend.py` + `src/services/chat_agent.py` (11 tools, `DDGSKani.do_function_call` override, `full_round_stream`/`chat_round_stream` iteration, billing/approval/emit layers).
