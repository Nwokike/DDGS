# kani Auxiliary Modules — Dependency Audit (for 100% capability utilization)

Package: `kani==1.10.0` · Consumer: DDGS (search/download/AI-assistant, streaming chat, reasoning display, citations, tool approvals)
Scope: `prompts/`, `parts/`, `model_specific/`, `utils/`, `_cli.py`, `__main__.py`, `_optional.py`, `_version.py`, `mcp.py` (inventory only — MCP out of scope).

---

## 1. COMPLETE API INVENTORY

### 1a. `kani/prompts/` — chat-template / prompt-building pipeline

**`prompts/__init__.py`** — re-exports `PipelineStep` (base), `PromptPipeline` (pipeline), `ApplyContext` (types).

**`prompts/base.py`**
- `class PipelineStep` — `execute(msgs, functions)`, `explain() -> str`, `explain_example_kwargs() -> dict`; subclass to write custom steps.
- `class FilterMixin(role=None, predicate=None)` — `filtered(msgs)`, `matches_filter(msg)`, `matches_role(role)`, `explain_note(join_sep, plural)`; every filtered step matches only msgs passing ALL of role+predicate.
- `natural_join(elems, sep)` — `"a, b, or c"` helper for explain strings.

**`prompts/pipeline.py` — `class PromptPipeline(Generic[T])`** (fluent builder; `pipe(msgs, functions)` runs it; return type depends on terminal)
- `.translate_role(*, to, warn=None, role=None, predicate=None)` — change roles (e.g. SYSTEM→USER, FUNCTION→USER for models without those roles).
- `.wrap(*, prefix=None, suffix=None, role=None, predicate=None)` — wrap matched msgs with affixes (parts-aware: inserts into list content).
- `.merge_consecutive(*, sep=None, joiner=None, out_role=None, role=None, predicate=None)` — merge consecutive matches; `sep` xor `joiner`; multi-role match REQUIRES `out_role`.
- `.function_call_fmt(func, *, prefix="\n", sep="", suffix="")` — `func(ToolCall)->str|None` appended per tool call (for text-format tool calling).
- `.remove(*, role=None, predicate=None)` — drop matched msgs (context management).
- `.ensure_start(*, role=None, predicate=None)` — strip leading non-matching msgs so prompt starts on a valid role (NOT for system prompts; for orphaned FUNCTION/ASSISTANT after trimming).
- `.ensure_bound_function_calls(id_translator=None)` — validate every FUNCTION binds to a pending ASSISTANT tool call; drops orphan FUNCTION results; auto-binds ID-less FUNCTION when unambiguous; raises `PromptError` on ambiguity; `id_translator` rewrites IDs (e.g. Mistral 9-char).
- `.apply(func, *, role=None, predicate=None)` — per-msg `func(msg)` or `func(msg, ctx)`; return non-ChatMessage only as last step; return None drops the msg.
- `.macro_apply(func)` — `func(messages, functions)` whole-list ad-hoc step (e.g. prepend tools block if empty).
- `.conversation_fmt(*, prefix="", sep="", suffix="", generation_suffix="", user_/assistant_/system_/function_prefix/suffix="", assistant_suffix_if_last=None)` — TERMINAL → `str`; FUNCTION defaults to USER affixes.
- `.conversation_dict(*, system_role="system", user_role="user", assistant_role="assistant", function_role="tool", content_transform=msg.text, additional_keys={})` — TERMINAL → `list[dict]`; CAUTION: drops tool-call metadata unless `additional_keys` re-adds it.
- `.execute(msgs, functions=None, *, deepcopy=False, for_measurement=False)` — run; `for_measurement` skips `ensure_start` (length probing only).
- `.explain(example=None, functions=None, *, all_cases=False)` — print step summary + build/run a synthetic example conversation (side-effect warning for `apply`).

**`prompts/steps.py`** — concrete step classes behind the builder (same names): `TranslateRole`, `Wrap`, `MergeConsecutive`, `FunctionCallFmt`, `Remove`, `EnsureStart`, `EnsureBoundFunctionCalls`, `Apply`, `MacroApply`, `ConversationFmt`, `ConversationDict`; plus `_wrap_content_inplace(msg, prefix, suffix)` parts-aware helper.

**`prompts/types.py`**
- `PipelineMsgT = ChatMessage`; `MessageContentT = str | list[MessagePart|str] | None`; `RoleFilterT = ChatRole | Collection[ChatRole]`; `PredicateFilterT = (msg)->bool`; `FunctionCallStrT = (ToolCall)->str|None`.
- `@dataclass ApplyContext(msg, is_last, idx, messages, functions)` + `.is_last_of_type` — context arg for 2-arg `apply` funcs.
- `ApplyCallableT` (1–2 args), `MacroApplyCallableT(msgs, funcs)`, `ApplyResultT`, `MacroApplyResultT` typevars.

**`prompts/examples.py`** (synthetic test-case builders, also drive `.explain()`)
- `build_conversation(*, function_call, consecutive_user, consecutive_assistant, consecutive_system, multi_function_call, end_on_assistant=False) -> list[list[ChatMessage]]` — canned groups (weather tool-call, coffee/cereal multi-call, etc.).
- `build_functions(*, function_call=False) -> list[AIFunction]` — canned `get_weather` AIFunction.
- `ALL_EXAMPLE_KWARGS` — parameter names of `build_conversation` (used for `all_cases`).

**`prompts/docutils.py`** — `PARAM_DOCS` (ROLE/PREDICATE/MULTIFILTER RST snippets), `autoparams(f)` decorator templating `{ALL_FILTERS}` into docstrings (internal).

### 1b. `kani/parts/` — multimodal MessagePart types

**`parts/__init__.py`** — re-exports `ReasoningPart`, `TextPart` (both also top-level `kani.*`).

**`parts/text.py` — `class TextPart(MessagePart)`, `content: str`** — `str()` returns content; use only when a model needs metadata in `.extra` alongside text (else plain `str`).

**`parts/reasoning.py` — `class ReasoningPart(MessagePart)`, `content: str`** — hidden CoT (GPT-OSS/Anthropic thinking/DeepSeek R1); `str()` returns `""` so it vanishes from `.text` unless explicitly rendered.

**How parts attach to `ChatMessage`** (`kani/models.py`, supporting): `content: str | list[MessagePart|str] | None`; `.text` concatenates via `str()` (ReasoningParts invisible); `.parts` read-only list view; constructors `ChatMessage.system/user/assistant/function(content, …)` accept str-or-part sequences; `copy_with(text=…/parts=…/content=…)` (exactly one) and `copy_with(function_call=…/tool_calls=…)`; function results carry `tool_call_id`; assistant requests carry `tool_calls: list[ToolCall]` (`ToolCall.from_function/from_function_call`, `FunctionCall.with_args(name, **kwargs)` for few-shots). `MessagePart.extra: dict` for engine metadata. NOTE: rich engine parts (image/audio/file) live in `kani.engines.{openai,anthropic}.parts` + optional `kani-multimodal-core` — **not installed here** (no `kani/ext/`).

### 1c. `kani/model_specific/` — per-model prompt pipelines + output parsers

**`model_specific/__init__.py`** (registry + lookup)
- `PROMPT_PIPELINE_REGISTRY: list[(glob, import_path)]` — `openai/gpt-oss-*`, `meta-llama/Llama-2*`, `meta-llama/Llama-3-*`, `mistralai/Mistral-7B*|Mixtral-8x*|*-2407|*-2409`, `Qwen/Qwen3-*`, `Qwen/Qwen3.5|3.6|3.8-*` → pipeline instance or `build_prompt_pipeline(tokenizer, **kw)`.
- `PARSER_REGISTRY: list[(glob, import_path)]` — `deepseek-ai/DeepSeek-R1*`, `openai/gpt-oss-*`, `meta-llama/Llama-3.*`, `mistralai/*-2404|2405|2407|2409`, `Qwen/Qwen3-*-Thinking*`, `Qwen/Qwen3-*`, `Qwen/Qwen3.5|3.6|3.8-*` → parser class.
- `prompt_pipeline_for_hf_model(model_id, tokenizer=None, search_parents=True, fallback_to_chat_template=True, *, chat_template_reasoning_content_key=None, chat_template_kwargs=None)` — handwritten pipeline → else parent-model recurse → else HF chat template (`ChatTemplatePromptPipeline`).
- `parser_for_hf_model(model_id, search_parents=True)` — cached; returns parser CLASS (does not install it).
- `warn_for_uninitialized_parser(model_id)` — warns if a handwritten parser exists but no `BaseParser` was ever instantiated.
- Activation: **only `HuggingEngine`/llamacpp consult these** (incl. parent-model fallback); OpenAI/Anthropic/Google engines never touch them — parsers must be manually wrapped (`Parser(engine)`).

**`model_specific/base.py` — `class BaseParser(WrapperEngine)`** (alias `BaseToolCallParser`): override `parse_tool_calls(content)->(str, list[ToolCall])` and/or `parse_reasoning(content)->str|list`; `parse_completion(completion)` runs both; `predict`/`stream` parse + buffer streams on delimiter tokens. Ctor: `tool_call_start/end_token`, `reasoning_start/end_token`, `reasoning_always_at_start`, `show_reasoning_in_stream` (stream thinking tokens live), `reasoning_in_stream_color` (gray ANSI).

**Per-model modules**
- `deepseek.py: DeepSeekR1Parser` (alias `DeepSeekR1ToolCallParser`) — `<｜tool▁calls▁begin｜>…<｜tool▁call▁begin｜>type<｜tool▁sep｜>name\n```json…` format; `<think>` reasoning, always-at-start.
- `gpt_oss.py: build_prompt_pipeline(tokenizer, **kw)` (defaults reasoning key `"thinking"`); `GPTOSSParser` — Harmony-channels state machine (`analysis`→ReasoningPart, `final`/`commentary`→visible, `to=functions.*`→ToolCall); `_GPTOSSStreamState` filters streams.
- `json.py: NaiveJSONToolCallParser` — whole-response `{"name","parameters"}` JSON ⇒ one ToolCall; buffers streams starting with `{`.
- `llama2.py: LLAMA2_PIPELINE` — `<<SYS>>` wrap + SYSTEM→USER, merge consecutive, `[INST]`/`</s>` `conversation_fmt`.
- `llama3.py: LLAMA3_PIPELINE` (FUNCTION→USER w/ warning, `<|start_header_id|>` fmt); `Llama3XToolCallParser` (`<|python_tag|>` + `{"name","parameters?"}` JSON).
- `mistral.py: MISTRAL_V3_PIPELINE` (SYSTEM→USER warn, merges, `[INST]` wrap, 9-char ID translator, `[TOOL_CALLS]` fmt, `[AVAILABLE_TOOLS]` injection on last USER msg); `MistralToolCallParser` (+ `</s>` stripping in predict/stream); helpers `maybe_json`, `json_tool_call`, `fmt_function_call_result`, `fmt_available_tools`, `ensure_available_tools`, `_fmt_functions`.
- `qwen3.py: build_prompt_pipeline` (reasoning key `"reasoning_content"`); `Qwen3Parser` (`<tool_call>` JSON `{name,arguments}` ×N); `Qwen3ThinkingParser` (same + always-at-start).
- `qwen3_5.py: build_prompt_pipeline` (same default key); `Qwen3_5Parser.parse_one_tool_call` — `<function=name><parameter=p>…` XML-ish inside `<tool_call>`; always-at-start reasoning.

### 1d. `kani/utils/` — helpers

**`utils/message_formatters.py`** (for `Kani.full_round_str(..., message_formatter=…)`): `all_message_contents(msg)` (any role → text); `assistant_message_contents(msg, show_reasoning=True, color=True)` (assistant only; gray ANSI reasoning); `assistant_message_contents_thinking(msg, show_args=False, …)` (assistant text + `Thinking... [fn(args)]` line); `assistant_message_thinking(msg, show_args=False)` (`"Thinking... [name(arg=…); …]"` on tool-call msgs, for use while streaming).

**`utils/saveload.py`**: `save(fp, inst, *, save_format, **kw)` (`"kani"` zip w/ `index.json` + hashed `blobs/xx/digest` attachments, vs `"json"` legacy); `load(fp)->SavedKani` (auto-detects zip); `SavedKani(version, always_included_messages, chat_history)`; `SAVELOAD_CONTEXT_KEY`; `KaniZipSaveContext.save_bytes(data, suffix)/load_bytes(fp)`; `get_ctx(info)` for custom part serializers.

**`utils/cli.py`**: `chat_in_terminal(kani, **kw)` / `chat_in_terminal_async(...)` — REPL (`rounds=0∞`, `stopword`, `echo`, `ai_first`, `width`, `show_function_args/returns`, `verbose=echo+args+returns`, `stream=True`; `@path` multimodal only if multimodal-core installed; `KANI_DEBUG` env); `format_width`, `print_width`, `strip_stream` (trim stream whitespace), `format_stream` (width-wrap), `print_stream`, `ainput`; engine factories `chat_openai/anthropic/google/huggingface(model_id)` (HF auto-wraps parser w/ `show_reasoning_in_stream=True`); `CLIProvider(name, aliases, entrypoint)`, `CLI_PROVIDERS` (openai/oai, anthropic/ant/claude, google/g/gemini, huggingface/hf), `get_cli_providers_including_extensions()` (discovers `kani.ext.*.CLI_PROVIDERS`), `fmt_cli_providers()`, `create_engine_from_cli_arg("provider:model")`.

**`utils/huggingface.py`**: `get_base_models(model_id)->list[str]` (cached; reads HF model-card `base_model` for parent fallback).

**`utils/typing.py`**: `PathLike = str | bytes | os.PathLike`.

**`utils/warnings.py`**: `warn_in_userspace(message, …)` (points at caller, not library); `deprecated(msg, *, category, stacklevel)` decorator.

### 1e. Top-level single files

- **`_cli.py`**: `main()` (argparse: `kani <provider>:<model_id>`, `-V/--version`); `chat(arg)` (build engine → `Kani(engine)` → terminal REPL); `print_version()` (`kani`, Python/platform/env, OPTIONAL_LIBS versions, `kani.ext.*` versions, torch env dump); `print_logo()`; `CLI_EXAMPLES`; `OPTIONAL_LIBS` (multimodal-core, anthropic, google.genai, llama_cpp, openai, transformers).
- **`__main__.py`**: `python -m kani` → `_cli.main()` (+ usage docstring).
- **`_optional.py`**: `_NotInstalledHelper(pkg)` (raises `ImportError: pip install "pkg"` on any attr); `multimodal_core`, `multimodal_cli`, `has_multimodal_core` (**False in this env** — no `kani.ext`, no `kani-multimodal-core` dist).
- **`_version.py`**: `__version__ = "1.10.0"`.
- **`mcp.py` (inventory only)**: `tools_from_mcp_servers(mcp_servers, allowed_tools=None, blocked_tools=None, *, component_name_hook=None)` async CM → `list[AIFunction]`; single-text-result passthrough else Text/Image (`ImagePart.from_b64`)/Audio (`AudioPart.from_file`) parts; at most one of allow/block lists.

---

## 2. LATENT CAPABILITIES FOR DDGS (ranked by UX impact)

DDGS today uses only `Kani`, `AIFunction`, `ChatMessage` (+ `OpenAIEngine`); nothing below is adopted. There are **no token-counting / history-trimming / token-budget helpers anywhere in kani** — confirmed by search; the closest hook is `PromptPipeline.execute(for_measurement=True)`.

1. **`ReasoningPart` + `BaseParser(show_reasoning_in_stream=True)` → native thinking display.** Parsers already split CoT into `ReasoningPart`s (invisible in `.text`, so citations/answers stay clean) and can stream thinking tokens live with gray coloring. DDGS's reasoning pane could consume `msg.parts` directly instead of regex-parsing `<think>` blocks. Applies today to any thinking model; pattern is reusable if DDGS ever wraps its engine.
2. **`assistant_message_contents_thinking` / `assistant_message_thinking` → tool-approval UX.** `"Thinking... [search_web(query='…')]"` lines (with `show_args=True`) are exactly the pending-approval preview DDGS needs during streaming; `assistant_message_contents` (gray reasoning) fits the transcript view. One `functools.partial` wires all three modes.
3. **`utils/saveload.save/load` → conversation persistence with attachments.** `.kani` zip stores `always_included_messages + chat_history` with binary blobs content-addressed (`blobs/xx/sha256`) — covers future image/file attachments; `"json"` keeps legacy compat. Replaces/augments DDGS's `conversations_load` with MessagePart-aware round-tripping.
4. **`kani` CLI (`_cli.py` + `utils/cli.py`) → prompt/approval debug bench.** `kani openai:<model>` gives a streaming REPL with `show_function_args/returns`, `verbose`, `ai_first`, `width`-wrapping for testing the search persona and tool schemas without launching the Flet UI; `kani --version` dumps env/optional/torch diagnostics for bug reports. Extension hook (`kani.ext.*.CLI_PROVIDERS`) could expose DDGS's own backend as `kani ddgs:<model>`.
5. **`PromptPipeline.apply/macro_apply` → persona + citation injection.** A 2-arg `apply` on SYSTEM msgs (via `ApplyContext.is_last_of_type`) prepends the search-persona instructions; a `macro_apply` appends citation blocks to FUNCTION results before they reach the model — no core fork required. `ensure_bound_function_calls` hardens approval-reject paths (drops orphan FUNCTION msgs instead of erroring the API call).
6. **`pipe.explain()` + `build_conversation/build_functions` → regression tests for the assistant.** Step-by-step pipeline explanation plus canned tool-call/multi-call/consecutive-msg fixtures give DDGS ready-made tests for citation merging and approval edge cases.
7. **Multimodal parts (`ImagePart`/`AudioPart` via `kani-multimodal-core`) → visual image-search results.** `ChatMessage.user([text, ImagePart…])` could send image-search thumbnails to a vision model so the assistant describes/ranks them; `mcp.py` already maps MCP image/audio blocks to these parts. BLOCKED: package not installed (`has_multimodal_core=False`) and needs a vision-capable engine + the `@file` CLI syntax only works in the terminal REPL.
8. **`ChatMessage.extra` + `TextPart.extra` → citation metadata channel.** Per-message `extra` dicts survive the pipeline and persist best-effort to disk — a sidecar for source URLs/rankings without polluting model-visible text.
9. **`warn_for_uninitialized_parser` + `get_base_models` → model-picker safety.** If DDGS ever offers local/HF models, one call warns when the selected checkpoint needs a thinking/tool parser; `get_base_models` resolves fine-tune→parent for the picker (cached; needs network for model cards).
10. **`strip_stream/format_stream/print_width` + `warn_in_userspace/deprecated` → small wins.** Stream whitespace trimming and width-wrapping are reusable in any text transcript export; the warning helpers keep DDGS's own deprecations pointed at caller code.

## 3. GOTCHAS

- **Registries are HF-engine-only.** `PROMPT_PIPELINE_REGISTRY`/`PARSER_REGISTRY` (fnmatch globs on HF IDs) are consulted by `HuggingEngine`, never by OpenAI/Anthropic/Google engines. DDGS (OpenAI backend) gets zero automatic benefit; parsers must be manually wrapped as `SomeParser(engine)`.
- **Parsers must wrap, not replace.** `parser_for_hf_model` returns a CLASS; forgetting to wrap triggers `warn_for_uninitialized_parser` (tracked via a global set in `BaseParser.__init__`). Double-wrapping concatenates tool calls with a warning.
- **Reasoning keys differ per family:** gpt-oss `"thinking"` vs Qwen3/3.5 `"reasoning_content"` (`chat_template_reasoning_content_key`); wrong key silently drops thinking from chat templates.
- **`ReasoningPart.__str__ == ""`.** `.text` hides reasoning — any code doing `msg.text` for logging/approval previews will NOT see thinking; iterate `.parts` and `isinstance`-check instead.
- **`conversation_dict` drops tool metadata by default** (`content=msg.text` only); must pass `additional_keys` or function-calling breaks. `merge_consecutive` over multiple roles requires `out_role`. `ensure_start` must not be used for system prompts; it is skipped under `for_measurement=True`.
- **Mistral IDs are rewritten** (`xxxxxxxxx` 9-char via `id_translator`); correlating DDGS approval IDs with Mistral tool IDs needs the same translation.
- **Save format matters.** `"json"` legacy cannot carry binary blobs; `"kani"` zip can. `MessagePart` deserialization needs the defining class imported or `load` raises `MissingMessagePartType`; `extra` values round-trip best-effort (non-JSON → `repr`, Pydantic → `dict`).
- **Optional-guard pattern.** Anything multimodal (`multimodal_core`, `multimodal_cli`) raises `ImportError("pip install kani-multimodal-core")` on first attribute access; always branch on `has_multimodal_core`. Same extra-guard style gates `mcp` (`pip install kani[mcp]`).
- **Streaming parsers buffer.** Tool-call delimiters (`<tool_call>`, `[TOOL_CALLS]`, `{` for NaiveJSON) suppress intermediate tokens until the end token arrives — approval UIs must handle delayed tool-call visibility; `show_reasoning_in_stream=True` is opt-in per parser (HF CLI factory sets it; manual wraps default off).
- **`model_specific` stability warning.** README: APIs here may change on MINOR patches — pin `kani==1.10.0` and re-audit on upgrade.
- **Template formats are per-model bespoke strings**, not a shared schema (DeepSeek `▁` delimiters, Mistral `[TOOL_CALLS]` JSON, Qwen3_5 `<function=name>` XML-ish, Llama3 `<|python_tag|>` JSON) — never hand-construct; always go through the parser.

## 4. COVERAGE

32 / 32 in-scope files read (100%): `prompts/` 7 (`__init__`, `base`, `pipeline`, `steps`, `types`, `examples`, `docutils`), `parts/` 3 (`__init__`, `text`, `reasoning`), `model_specific/` 10 (`__init__`, `base`, `deepseek`, `gpt_oss`, `json`, `llama2`, `llama3`, `mistral`, `qwen3`, `qwen3_5` + `README.md`), `utils/` 7 (`__init__` stub, `cli`, `huggingface`, `message_formatters`, `saveload`, `typing`, `warnings`), `_cli.py`, `__main__.py`, `_optional.py`, `_version.py`, `mcp.py`. Supporting: `models.py` (MessagePart/ChatMessage attachment), `__init__.py` (export surface), DDGS `kani_backend.py`/`reasoning.py` usage grep. Verified absent: `kani/ext/` (no multimodal-core), token-count/trim helpers.
