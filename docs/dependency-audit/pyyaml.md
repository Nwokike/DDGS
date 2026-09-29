# PyYAML 6.0.3 — Dependency Audit (DDGS)

**Version:** 6.0.3 · **Location:** `.venv/Lib/site-packages/yaml/` · **Date:** 2026-09-29
**Chain:** `dev: flet[cli,desktop]==1.0.1 → cookiecutter 2.7.1 → pyyaml` (sole consumer:
`cookiecutter/config.py` → `yaml.safe_load` for `~/.cookiecutterrc`). **Zero `import yaml` in `src/`.**
**Persistence in app:** `src/services/storage_service.py` → JSON only (`storage.json`, `json.dumps(indent=2)`).

> Note: the brief asked for `YAML(typ=)` variants (`rt`/`safe`/`base`) — that API belongs to
> **ruamel.yaml**, not PyYAML. PyYAML's equivalent is the Loader/Dumper subclass ladder below.

## 1. COMPLETE API INVENTORY

**Top-level load (one doc):** `safe_load(stream)` → SafeLoader, basic tags only, safe on untrusted input.
**Top-level load (one doc):** `full_load(stream)` → FullLoader, resolves most tags except arbitrary object construction.
**Top-level load (one doc):** `unsafe_load(stream)` → UnsafeLoader, resolves everything incl. `!!python/object` (RCE).
**Top-level load (one doc):** `load(stream, Loader)` → explicit-loader form; `Loader`/`UnsafeLoader` both execute arbitrary code.
**Multi-doc load:** `safe_load_all` / `full_load_all` / `unsafe_load_all` / `load_all` → generators over `---`-separated docs.
**Top-level dump:** `safe_dump(data)` → SafeDumper, basic tags only; `dump(data, Dumper=Dumper)` → full representer set.
**Multi-doc dump:** `safe_dump_all(documents)` / `dump_all(documents)` → `---`-separated stream output.
**Low-level pipeline:** `scan()` yields tokens, `parse()` yields events, `compose()`/`compose_all()` yield node trees.
**Low-level emit:** `emit(events)` / `serialize(node)` / `serialize_all(nodes)` → drive Dumper from events/nodes directly.
**Pure-Python Loaders:** `BaseLoader` (no implicit resolution) < `SafeLoader` < `FullLoader` < `Loader` == `UnsafeLoader`.
**C Loaders (libyaml):** `CBaseLoader` / `CSafeLoader` / `CFullLoader` / `CLoader` / `CUnsafeLoader`, same ladder, 5–10× faster.
**Pure-Python Dumpers:** `BaseDumper` (scalars/collections only) / `SafeDumper` (str/bytes/bool/int/float/list/tuple/dict/set/date/datetime/None) / `Dumper`.
**C Dumpers:** `CBaseDumper` / `CSafeDumper` / `CDumper` (note: CBase/CSafe pair off `Representer`, not `Serializer`-less — check imports).
**C-extension flag:** `yaml.__with_libyaml__` bool; `from .cyaml import *` guarded by try/except ImportError → pure-Python fallback.
**Anchors/aliases:** round-trip supported (`&id` / `*id`); duplicate anchor raises `ComposerError`; shared refs re-emitted as aliases (`id%03d`).
**Custom tags (load):** `yaml.add_constructor(tag, fn(loader, node))` and `add_multi_constructor(prefix, fn(loader, suffix, node))`, per-Loader or global.
**Custom tags (dump):** `yaml.add_representer(type, fn(dumper, data))` and `add_multi_representer(type, ...)` for subclasses.
**Custom scalar typing:** `yaml.add_implicit_resolver(tag, regexp, first=[chars])` and experimental `add_path_resolver(tag, path, kind)`.
**Class-coupled API:** `YAMLObject` + `YAMLObjectMetaclass` — `yaml_tag`/`yaml_loader`/`yaml_dumper` attrs auto-wire `from_yaml`/`to_yaml`.
**Emit option `sort_keys=True`:** sorts mapping output (set `False` for insertion order); `default_flow_style=False` → block style.
**Emit options `indent` (int 2–9, default 2), `width` (default 80, must exceed `indent*2`):** line-wrap control for long scalars.
**Emit options `allow_unicode`, `encoding`, `line_break` (`\n`/`\r`/`\r\n`):** non-ASCII escaping vs raw output, byte-stream mode, newline style.
**Emit options `canonical`, `explicit_start/end`, `version`, `tags`, `default_style`:** verbose/canonical form, `---`/`...` markers, directives.
**Implicit type resolution:** bool/int/float/null/merge(`<<`)/timestamp/value/`=` resolvers with first-char fast-paths (note: `on`/`off`/`yes`/`no` → bool!).
**Errors:** `YAMLError` base; `MarkedYAMLError` (line/column snippet via `Mark`); `ReaderError`/`ScannerError`/`ParserError`/`ComposerError`/`ConstructorError`/`SerializerError`/`EmitterError`/`RepresenterError`/`ResolverError`.
**Reader inputs:** accepts `str`, `bytes` (BOM/encoding autodetect), or file-like objects; appends `\0` sentinel internally.

## 2. STRATEGIC ASSESSMENT

**Verdict: BALLAST at runtime — keep the package (it is not ours to remove), use none of it.**

- The only dependent in `uv.lock` is **cookiecutter 2.7.1** (`dependencies: [... { name = "pyyaml" } ...]`),
  itself pulled by the **dev-only** `flet[cli,desktop]` group (`flet create` scaffolding templates).
- cookiecutter's single use is `yaml.safe_load` of the user's `~/.cookiecutterrc` — nothing to do with DDGS features.
- `pyproject.toml [project].dependencies` does **not** list cookiecutter or pyyaml → **PyYAML never ships in the
  Android APK** (`flet build` resolves project deps only). Zero size/perf cost on device; zero capability to utilize there.
- The app persists JSON exclusively (`storage_service.py`: `storage.json`, Flet prefs cache). No GitHub-workflow parsing,
  no YAML config, no YAML anywhere in `src/` (grep for `yaml|yml` returns zero hits).
- Removing it is not actionable: it arrives transitively via the dev toolchain, and `uv` has no per-package exclusion
  for transitive dev deps without patching the resolver graph. Cost of carrying it: ~150 KB wheel in the dev venv only.

**If the owner ever wants human-editable artifacts (all would be new features, none exist today):**

1. **Settings export/import as YAML** — `yaml.safe_dump(dict(settings), sort_keys=False, allow_unicode=True, width=120)` for a
   readable backup file next to `storage.json`; re-import strictly via `yaml.safe_load` + schema validation. Genuinely nicer
   than JSON for hand-editing (comments, no brace bookkeeping), and `sort_keys=False` preserves the settings-screen order.
2. **Search-engine rules file** — a user-editable `engines.yaml` (enable/disable engines, per-engine timeout/weight) loaded
   once at startup with `safe_load`; multi-doc (`safe_load_all`) could split defaults vs user overrides in one file with
   `<<` merge keys for shared defaults. Anchors would let power users alias repeated engine stanzas.
3. **Diagnostics/support bundle** — `safe_dump` of versions, engine list, and (redacted) settings into a paste-friendly block
   for bug reports; `explicit_start=True` + `width=100` keeps it clean in chat windows. Safer than JSON for copy/paste
   (no quoting pitfalls) — but all three ideas add a file format the app must then support forever, for marginal gain
   over the JSON it already speaks. Recommendation: do none unless users explicitly ask for hand-editable config.

## 3. GOTCHAS

- **`safe_*` ONLY on any user-influenced input** — `yaml.load`/`Loader`/`UnsafeLoader` deserialize `!!python/object/*` tags
  into arbitrary constructor calls = **remote code execution**; `full_load` is safe from instantiation but still resolves
  `python/name`/`module` lookups, so prefer `safe_load` and add only the constructors you need via `add_constructor`.
- **C extension is NOT guaranteed on Android** — `.venv` has `_yaml.cp312-win_amd64.pyd` and `__with_libyaml__=True` on dev
  machines, but the APK dependency set never includes pyyaml at all; any future direct use must run on the pure-Python
  path (slower, but correct) and must never branch on `__with_libyaml__` for correctness.
- **`on`/`off`/`yes`/`no` parse as booleans** (YAML 1.1 `bool` resolver) — a search engine named `on` in a rules file would
  silently become `True`; quote such scalars or add a custom implicit resolver. Timestamps auto-become `datetime` objects.
- **Duplicate mapping keys:** `construct_yaml_omap`/`pairs` explicitly skip duplicate checks (source comment, constructor.py);
  plain `construct_mapping` raises `ConstructorError` — behavior differs by tag, so validate keys yourself after `safe_load`.
- **Unicode/width:** default `allow_unicode=None` escapes non-ASCII (`\uXXXX`); pass `allow_unicode=True` for readable CJK/Arabic
  output; `width` below `indent*2` is silently ignored (falls back to 80), and long URLs wrap mid-token unless `width` is raised.
- **Merge keys (`<<`) and aliases execute during construction** — `safe_load` handles them, but deeply chained aliases/anchors
  from untrusted input can balloon memory (billion-laughs class); cap input size before parsing anything fetched from the network.
- **`yaml_tag` on `YAMLObject` subclasses registers globally** on `[Loader, FullLoader, UnsafeLoader]` — importing such a module
  silently widens every loader in the process; prefer explicit `add_constructor(..., Loader=SafeLoader)` in app code.

## 4. COVERAGE

**17 / 17 files touched** (`yaml/*.py`, 5,890 lines total): **11 read in full**
(`__init__`, `loader`, `dumper`, `cyaml`, `error`, `composer`, `serializer`, `nodes`, `events`, `tokens`, `reader`),
**6 skimmed strategically** via targeted grep + key sections (`constructor` incl. Full/Unsafe split, `representer` incl.
SafeRepresenter registry, `resolver` implicit table, `emitter` `__init__` options, `scanner`/`parser` class/method maps —
tokenizer/parser internals with no app-facing API beyond `scan()`/`parse()`).
Consumer side: full grep of `src/` for `yaml|yml` (0 hits), `storage_service.py` persistence path, `pyproject.toml`
dependency lists, `uv.lock` `pyyaml` + `cookiecutter` stanzas, and cookiecutter's `config.py` usage site.
