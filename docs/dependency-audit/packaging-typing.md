# packaging + typing_extensions + typing_inspection — Dependency Audit (DDGS)

> Versions observed (venv): `packaging 26.3` · `typing-extensions 4.16.0` · `typing-inspection 0.4.4` · Python `3.12.14` · `kani 1.10.0` · `openai 2.54.0` · `flet 1.0.1` · `pydantic 2.13.5` · `requires-python >=3.12`.
> Consumer: `C:\Users\nwoki\.zcode\workspace\default\DDGS\src\` — **zero direct imports** of any of the three packages (grep `packaging|typing_extensions|typing_inspection|^from packaging|^import packaging` → no hits in `src/`).
> Dependents (`uv.lock`): `packaging` ← `flet`, `pytest`/`pluggy` chain; `typing-extensions` ← `anyio` (py<3.15 marker), `openai`, `pydantic`, `pydantic-core`, transitively `typing-inspection`; `typing-inspection` ← `pydantic` only. All three are **transitive-only / ballast today** unless DDGS imports them directly.
> Verdict up front: keep all three (they ride along with flet/pydantic/openai/kani anyway); convert from ballast to leverage with ~5 small, safe direct uses (see §2). No removal action.

---

## 1. API INVENTORY

### 1.1 packaging (26.3) — per module, one line per public name

**`packaging.version` — PEP 440 version parsing/comparison (semver-ISH, not semver):**
- `Version` — PEP 440 version object; rich-compare, `major/minor/micro`, `pre/post/dev/local`, `is_prerelease/is_postrelease/is_devrelease`, `base_version/public/release/epoch`, `from_parts()`.
- `parse` — `str → Version` (legacy fallback removed; raises on garbage).
- `InvalidVersion` — raised by `Version`/`parse` on non-PEP-440 input.
- `VERSION_PATTERN` — the PEP 440 regex (verbatim constant, useful for pre-validation).
- (module-internal `normalize_pre` visible via `dir()` — do not import directly.)

**`packaging.specifiers` — version clauses `>=, ==, ~=, …`:**
- `SpecifierSet` — comma-AND set, e.g. `SpecifierSet(">=2.0,<3.0")`; `in` operator (`"2.54.0" in SpecifierSet(">=2.0,<3.0")`), `.filter()`, `.contains(v, prereleases=…)`.
- `Specifier` — single clause (e.g. `Specifier("~=1.4.2")`); operators `== != <= >= < > ~= ===` (`~=` = compatible-release, `===` = arbitrary string equality).
- `BaseSpecifier` — abstract base of both above.
- `InvalidSpecifier` — raised on bad specifier strings.

**`packaging.requirements` — PEP 508 requirement strings:**
- `Requirement` — parses `"kani[mistral,openai]>=1.2; python_version>=\"3.10\""` → `.name/.extras/.specifier/.marker/.url`.
- `InvalidRequirement` — raised on bad requirement strings.

**`packaging.markers` — environment/platform conditions (THE tool for conditional imports):**
- `Marker` — parses/evaluates `sys_platform=="win32" and python_version>="3.12"`; `.evaluate(environment?)`, `evaluate_extras_and_python_version()`.
- `default_environment` — `() → Environment` dict actually observed: `implementation_name/name/version, os_name, platform_machine/release/system/version, platform_python_implementation, python_full_version/python_version (3.12 here), sys_platform (win32 here)`.
- `Environment` — `TypedDict` of the marker keys above.
- `EvaluateContext` — literal type for the `environment` arg of `Marker.evaluate`.
- `InvalidMarker` — bad marker string; `UndefinedComparison` — meaningless comparison; `UndefinedEnvironmentName` — unknown key (subclass of `KeyError`).
- Marker variables: `os_name, sys_platform, platform_machine/system/release/version, python_version/python_full_version, implementation_name/version, platform_python_implementation, extra` — string ops `== != in not in`, version-aware compare for python versions.

**`packaging.tags` — wheel compatibility (reason about Android/desktop wheels):**
- `Tag` — single `(interpreter, abi, platform)` triple; `parse_tag()` inverse.
- `sys_tags()` — 42 tags on this box, first `cp312-cp312-win_amd64`, last `py30-none-any`; the ordered supported-tag list.
- `compatible_tags / cpython_tags / generic_tags / pure_python_tags` — tag generators (pure-python = `py3-none-any`).
- `interpreter_name / interpreter_version` — current interpreter shards.
- `platform_tags` — current platform shards; `mac_platforms / ios_platforms / android_platforms` — per-OS platform-tag expanders (Android entry point for APK-wheel reasoning).
- `create_compatible_tags_selector` — build a `is-compatible(tag)` predicate from interpreter+platform lists.
- `PythonVersion / AppleVersion` — version helpers for tag construction.
- `INTERPRETER_SHORT_NAMES` — `{"python":"py","cpython":"cp","pypy":"pp",…}` map.
- `InvalidTag / TooManyTagsError / UnsortedTagsError` — tag errors.

**`packaging.utils` — name/filename normalization:**
- `canonicalize_name` — PEP 503 (`typing-extensions` stays, `Foo_Bar` → `foo-bar`).
- `canonicalize_version` — PEP 440 normalize without parsing.
- `is_normalized_name` — bool check.
- `parse_wheel_filename` — `"flet-0.28.3-py3-none-any.whl" → (name, Version, BuildTag, frozenset[Tag])`.
- `parse_sdist_filename` — sdist analogue.
- `NormalizedName` — `NewType`-ish normalized-name str; `BuildTag` — `(number, name)` tuple; `InvalidName / InvalidWheelFilename / InvalidSdistFilename` — errors.

**`packaging.metadata` — wheel/sdist METADATA (RFC 822 / core metadata 2.x):**
- `parse_email(data, PetriNet?) → RawMetadata` — parse `METADATA` file bytes/str.
- `Metadata` — validated frozen dataclass (`name/version/requires_dist/…`); `RawMetadata` — raw dict typedef.
- `RFC822Message / RFC822Policy` — email-message subclasses used by parser.
- `InvalidMetadata` — validation error; `ExceptionGroup` — 3.11-shim re-export (real stdlib on 3.12).

**`packaging.direct_url` — PEP 610 `direct_url.json`:**
- `DirectUrl` — `{url, info, subdirectory?}` with `.to_dict()/.from_dict()`; `ArchiveInfo (hashes) / DirInfo (editable?) / VcsInfo (vcs/commit/requested_revision)` — the three `info` variants.
- `DirectUrlValidationError` — bad payload.

**`packaging.licenses` — SPDX license expressions:**
- `canonicalize_license_expression(expr) → NormalizedLicenseExpression` — validates/normalizes `MIT OR Apache-2.0`.
- `NormalizedLicenseExpression` — validated str; `InvalidLicenseExpression` — error (`packaging.licenses._spdx` = SPDX id dataset, not imported directly).

**`packaging.dependency_groups` — PEP 735 `[dependency-groups]`:**
- `resolve_dependency_groups(toml_dict, *groups) → tuple[Requirement,…]` — resolver entry point.
- `DependencyGroupResolver` — resolver object; `DependencyGroupInclude` — `{include-group = "…"}` record.
- `CyclicDependencyGroup / DuplicateGroupNames / InvalidDependencyGroupObject` — errors.

**`packaging.pylock` — PEP 751 `pylock.toml`:**
- `Pylock` — lockfile object (`.from_dict/.to_dict/.from_path`); `Package` — locked-package record.
- `PackageWheel / PackageSdist / PackageArchive / PackageDirectory / PackageVcs` — the five origin variants.
- `is_valid_pylock_path(path)` — filename check; `PylockValidationError / PylockUnsupportedVersionError / PylockSelectError` — errors.

**`packaging.ranges` — new-style version ranges:**
- `VersionRange` — range object (successor vocabulary to `SpecifierSet`; checkratchet/pin APIs live here in 26.x).

**`packaging.errors` — shims:** `ExceptionGroup` only.

**Private backing (`_elffile/_manylinux/_musllinux/_parser/_tokenizer/_structures/_ranges`)** — ELF parsing, manylinux/musllinux detection, marker/requirement grammar; never import directly.

### 1.2 typing_extensions (4.16.0) — ALL 121 `__all__` names, one line each

Core aliases / re-exports (prefer stdlib on 3.12; TE copy only matters for older Pythons — see §3): `AbstractSet, Any, AnyStr, AsyncContextManager, AsyncGenerator, AsyncIterable, AsyncIterator, Awaitable, BinaryIO, Callable, ChainMap, ClassVar, Collection, Concatenate, Container, ContextManager, Coroutine, Counter, DefaultDict, Deque, Dict, Final, ForwardRef, FrozenSet, Generator, Generic, Hashable, IO, IntVar, ItemsView, Iterable, Iterator, KeysView, List, Literal, Mapping, MappingView, Match, MutableMapping, MutableSequence, MutableSet, Optional, OrderedDict, Pattern, Protocol, Sequence, Set, Sized, Reversible, SupportsAbs/Bytes/Complex/Float/Index/Int/Round, TYPE_CHECKING, Text, TextIO, Tuple, Type, Union, cast, no_type_check, no_type_check_decorator, overload, final, get_args, get_origin, get_type_hints, is_protocol, runtime, runtime_checkable, get_original_bases, get_overloads, clear_overloads, get_protocol_members (TE-only, see below), assert_type (stdlib since 3.11, TE backport), reveal_type, assert_never, AsyncIterable…` — each line: typing-compatible alias/decorator/introspection identical to `typing` on 3.12; import from `typing` instead.

Forms that are NEW vs 3.12 stdlib or carry DDGS value (★ = use-worthy, see §2):
- ★ `NotRequired` — TypedDict optional key (stdlib 3.11+ too, but canonical for event payloads).
- ★ `Required` — TypedDict force-required key (even under `total=False`).
- ★ `ReadOnly` — TypedDict read-only item (3.13+ stdlib; TE-only on 3.12 — conversation-history items).
- ★ `override` — marks overriding methods (stdlib 3.12+, use stdlib; missing on `DDGSKani.do_function_call` today).
- ★ `deprecated` — `@deprecated("msg")` decorator (TE-only on 3.12; `warnings` category override — chat-emit protocol evolution).
- ★ `dataclass_transform` — marks decorators that behave like `@dataclass` (stdlib 3.11+; for DDGS decorator factories).
- ★ `LiteralString` — `str` that is definitely a literal (stdlib 3.11+; SQL/prompt-template safety).
- ★ `TypeAliasType` — `Type X = …` old-style explicit alias with type params (stdlib 3.12+; prefer `type X =` syntax on 3.12 but TE form is runtime-compatible).
- ★ `TypeVarTuple` — variadic type var (stdlib 3.11+; hook/event pipelines).
- ★ `ParamSpec` (+ `ParamSpecArgs/ParamSpecKwargs`) — decorator param forwarding (stdlib 3.10+; hook wrappers).
- ★ `Unpack` — unpack `TypedDict`/`TypeVarTuple` into `*args/**kwargs` (stdlib 3.11+/3.12+).
- ★ `Never` — bottom type, stricter than `NoReturn` for impossible branches (stdlib 3.11+).
- ★ `assert_type` — static assert `assert_type(x, Expected)` (stdlib 3.11+; dev-time checks, zero runtime cost beyond arg eval).
- ★ `Self` — method returns-own-class (stdlib 3.11+; fluent builders in `app_controller/services`).
- ★ `TypeGuard` — user-defined narrow predicate (stdlib 3.10+).
- ★ `TypeIs` — stricter `TypeGuard` (stdlib 3.13+; **TE-only on 3.12** — message-role discriminators).
- ★ `Doc` — `Annotated`-based doc metadata (TE-only; documents `Annotated` fields without comments).
- ★ `TypeForm` — "is itself a type" annotation (TE-only; plugin registries that pass classes around).
- ★ `Format` — `__format__` protocol annotation helper (TE-only, 4.16 new).
- ★ `NoDefault / NoExtraItems` — sentinels for `Parameter` defaults / `TypedDict closed+extra_items` (TE-only; `NoExtraItems` pairs with PEP 728 `closed=True` TypedDicts).
- ★ `Sentinel / sentinel()` — named unique sentinels with `repr` (TE-only; replaces `object()` / `_MISSING` patterns).
- ★ `get_annotations` — `inspect.get_annotations` backport with `Format` support (TE-only semantics on 3.12).
- ★ `evaluate_forward_ref` — safe `ForwardRef` evaluator honoring `Format`/`owner`/`globals` (TE-only; lazy model imports).
- ★ `get_protocol_members` — list `Protocol` members incl. non-method (TE-only; structural checks on emit-protocol).
- ★ `is_typeddict` — runtime `TypedDict` check (stdlib 3.10+ has it too, TE copy is version-proof).
- ★ `NamedTuple` — TE `NamedTuple` with `__orig_bases__`/defaults fixes (stdlib exists; TE copy only if hitting 3.12 bugs — `InspectedAnnotation` is a `NamedTuple` downstream).
- ★ `TypedDict` — TE `TypedDict` with `closed/extra_items` (PEP 728) kwargs on 4.16 (stdlib 3.12 lacks them — extra-shape control for event dicts).
- ★ `Buffer` — `collections.abc.Buffer` backport (3.12 stdlib exists; TE copy for cross-version byte paths — image/QR bytes).
- `CapsuleType` — `PyCapsule` type (C-extension interop; not DDGS-relevant).
- `NewType / TypeVar / TypeAlias` — classic alias machinery (stdlib equivalents exist; `TypeAlias` = annotation-only marker).
- `Reader / Writer` — `typing.io` legacy aliases (prefer `BinaryIO/TextIO`).
- `Awaitable…Hashable` support-protocol aliases — legacy re-exports, one line each, no independent behavior.
- `disjoint_base` — mark a class as disjoint-base for union narrowing (TE-only, narrow use).
- `type_repr` — `typing` internal repr helper (debugging only).

### 1.3 typing_inspection (0.4.4) — `introspection` + `typing_objects` (+ empty `__init__`)

**`typing_inspection.introspection` — annotation-shape analysis (pydantic's engine, reusable):**
- `inspect_annotation(ann, *, annotation_source, unpack_type_aliases='skip'|'lenient'|'eager') → InspectedAnnotation` — unwrap qualifiers + `Annotated` metadata; the single entry point.
- `InspectedAnnotation` — `NamedTuple(type, qualifiers, metadata, …)` result record.
- `AnnotationSource` — `IntEnum(CLASS/DATACLASS/NAMED_TUPLE/TYPED_DICT/FUNCTION/ASSIGNMENT_OR_VARIABLE/…)` — which qualifiers are legal where.
- `Qualifier` — qualifier enum (`Final/ClassVar/Required/NotRequired/ReadOnly/…`); `ForbiddenQualifier` — raised when a qualifier appears in the wrong source.
- `UNKNOWN` — sentinel when no type expression exists (`x: Final = 1`).
- `get_literal_values(ann, *, type_check=False, unpack_type_aliases='eager') → Generator` — yield `Literal[…]` members through aliases.
- `is_union_origin(obj)` — `Union` vs `types.UnionType` check (deprecated path on 3.14+; use `typing_objects.is_union`).

**`typing_inspection.typing_objects` — `is_*` predicates over typing forms (one line each):**
- `is_any/is_annotated/is_classvar/is_concatenate/is_deprecated/is_final/is_forwardref/is_generic/is_literal/is_literalstring/is_namedtuple/is_never/is_newtype/is_nodefault/is_noextraitems/is_noreturn/is_notrequired/is_paramspec/is_paramspeckwargs/is_paramspecargs/is_readonly/is_required/is_self/is_typealias/is_typealiastype/is_typeguard/is_typeis/is_typevar/is_typevartuple/is_union/is_unpack` — each `Any → bool`, version-proof across `typing`/`typing_extensions` spellings (handles `X | Y` vs `Union`, PEP 695 aliases, TE backports).
- `alias/te_alias/target` — helpers/constants for resolving TE-vs-stdlib spellings; `DEPRECATED_ALIASES/DEPRECATED_ALIASES_IDS` — legacy-alias tables.

---

## 2. STRATEGIC ASSESSMENT + LATENT CAPABILITIES

**Status: 0% direct utilization — 100% transitive ballast.** Nothing in `src/` imports any of the three. They exist because `flet→packaging`, `pydantic→typing-extensions+typing-inspection`, `anyio/openai→typing-extensions`. Owner intent (100% capability or honest ballast) → keep (cannot drop without dropping flet/pydantic) and promote five cheap wins:

1. **Version-gate kani/openai/flet at runtime (`packaging.version` + `SpecifierSet`).** Installed: kani 1.10.0, openai 2.54.0, flet 1.0.1. `kani_backend.py::_to_history` and `DDGSKani.do_function_call` assume today's kani shapes; a one-helper `requires("kani>=1.10")` using `importlib.metadata.version + packaging.Version/SpecifierSet.__contains__` turns silent breakage on upgrade into a legible error and lets DDGS enable extras only when supported (e.g. new kani tool-call args, new openai response fields). ~15 lines in `core/` or `services/update_service.py` (already the version-checking service — natural home alongside its `@dataclass` version record).
2. **`Marker` for Android-vs-desktop branches.** `default_environment()` keys (`sys_platform, platform_system/machine, os_name, python_version, implementation_name`) subsume the hand-rolled `platform`/`sys` checks scattered in `core/storage_paths.py` ("on Android this directory IS the cache dir") and flet platform code. `Marker('sys_platform=="android"').evaluate()` is testable without a device (pass a fake environment dict) — unlike `sys.platform` monkeypatching. Also `packaging.tags.android_platforms/ios_platforms` answer "which wheel tag would this APK need" when triaging Android install failures.
3. **`Requirement` for user-facing dependency errors.** `sections_about.py` (update feed) and pip-error surfaces can parse `Requirement("flet>=1.0.1")` instead of string-splitting names/versions — handles extras+markers+URL reqs correctly.
4. **Typed conversation events (`NotRequired/Required/ReadOnly/closed TypedDict`).** `chat_screen.emit(event: str, data: dict)` and `_to_history(history: list[dict])` are `dict`-typed today — every consumer re-validates by convention. A `ChatEvent(TypedDict, closed=True)` with `Required[event: LiteralString]` + `NotRequired[data]` (+ `ReadOnly` history items) makes the emit protocol checkable and documents evolution; `assert_type(evt["event"], str)` in tests is free.
5. **`@override` + `@deprecated` hygiene.** `DDGSKani.do_function_call` (kani_backend.py:78) overrides `Kani.do_function_call` with no `@override` — a signature drift in kani 1.11+ becomes silent. One decorator (import from `typing`, 3.12 has it) fixes it. `@deprecated` (TE-only on 3.12) is the graceful path for renaming chat-emit events or old search-service entry points. `dataclass_transform` matters only if DDGS builds decorator factories over its many `@dataclass(frozen=True)` models (state, license_token, model_picker) — otherwise ballast. `typing_inspection.inspect_annotation` matters only if DDGS builds dataclass/TypedDict tooling (schema export, event-doc generator, strict config loader) — today pydantic owns that job, so leave it transitive until such a tool is written; then prefer it over hand-rolled `get_type_hints` walks because it already handles `Annotated`+qualifiers+PEP 695 aliases.

Honest ballast (do NOT force): `pylock/dependency_groups/metadata/direct_url/licenses/ranges`, most `tags.*` beyond android/ios triage, `CapsuleType/Reader/Writer/Doc/Format/Sentinel/disjoint_base/TypeForm` — no DDGS use case; `Buffer` (stdlib covers 3.12); TE re-exports of everything already in `typing`.

## 3. GOTCHAS

- **typing_extensions drift on 3.12 is real and directional.** Probed: `override/TypeAliasType/NotRequired/Required/Unpack/TypeVarTuple/ParamSpec/assert_type/Never/LiteralString/Self/dataclass_transform/TypeGuard/Buffer` exist in BOTH `typing` and TE 4.16 (import from `typing`); `TypeIs/ReadOnly/deprecated/TypeForm/Doc/NoDefault/NoExtraItems/get_protocol_members/evaluate_forward_ref/Format/Sentinel` are **TE-only on 3.12** (stdlib gains them in 3.13/3.14 or never). Rule: stdlib-first; TE only for the second list — and pin `typing-extensions>=4.12` if any TE-only form is used (4.16 observed).
- **packaging is PEP 440, NOT semver.** `Version("1.10.0") > Version("1.2.3")` works, but `1.0a1 < 1.0`, epochs (`1!2.0`), post/dev/local segments, and `~=` (compatible-release: `~=1.4.2` ≡ `>=1.4.2,==1.4.*`) have no semver equivalent. Never hand-compare version tuples; always `Version` + `SpecifierSet.__contains__` with `prereleases=` explicit (pre-releases are excluded by default).
- **Markers look like Python but aren't.** `Marker.evaluate()` takes an optional environment dict — missing keys raise `UndefinedEnvironmentName`, bad comparisons raise `UndefinedComparison`; `extra` is only meaningful when the requirer passes it. Version comparisons inside markers are PEP 440-aware (good) but string comparisons are case-sensitive (bad surprise for `platform_system`).
- **`SpecifierSet("")` matches everything** (empty set = no constraint) — a missing floor in config silently passes; validate non-empty when a gate is intended.
- **Wheel tags are ordered most-to-least specific**; `sys_tags()[0]` is the current best, not a set — membership-test, don't index, when checking compatibility.

## 4. COVERAGE

- `packaging`: **22 source files total** (`__init__, version, specifiers, requirements, markers, tags, utils, metadata, direct_url, licenses/__init__, licenses/_spdx, dependency_groups, pylock, ranges, errors, _parser, _tokenizer, _structures, _ranges, _elffile, _manylinux, _musllinux` + `py.typed`); all 15 public modules inventoried via runtime `dir()` + live probes (`Version` ordering, `SpecifierSet.__contains__`, `Requirement` parse of `kani[mistral,openai]>=1.2`, `default_environment()` keys, `sys_tags()` count/endpoints, `canonicalize_name/parse_wheel_filename`, `android_platforms/ios_platforms` presence) + line counts (`version 1252, specifiers 1457, markers 576, tags 1053, utils 370, requirements 192, metadata 1054, ranges 2067, pylock 943, _ranges 836, _parser 418` lines); private `_manylinux/_musllinux/_elffile` triaged by purpose, not line-read.
- `typing_extensions`: **1 file, 4422 lines**; `__all__` (121 names) fully enumerated one-line-each above; 3.12 stdlib-vs-TE presence matrix probed for 22 key names + `Buffer/Sentinel`; key-def grep (`NoDefault/NoExtraItems/Sentinel` singletons, `TypedDict closed/extra_items` kwargs).
- `typing_inspection`: **4 files total** (`__init__.py` 0 lines — empty, `introspection.py` 587, `typing_objects.py` 620, `typing_objects.pyi` 421 + `py.typed`); `dir()`-inventoried both modules; `inspect_annotation/get_literal_values/is_union_origin/AnnotationSource/InspectedAnnotation` source-opened (first ~900 chars each); all 30+ `is_*` predicates enumerated.
- Consumer/dependents: `grep src/ + pyproject.toml + uv.lock` for all three spellings; `uv.lock` reverse-deps recorded; installed versions via `importlib.metadata`; DDGS touchpoints confirmed (`services/kani_backend.py:70,78,133`, `screens/chat_screen.py:1070`, dataclass sites, `requires-python >=3.12`).
