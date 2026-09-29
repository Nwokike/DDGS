# Dependency Audit — `flet_cli` 1.0.1 (the `flet` command)

- Package: `flet_cli==1.0.1` (`flet_cli/version.py`: `version = "1.0.1"`)
- Scope: all 45 `.py` files under `.venv/Lib/site-packages/flet_cli/`
- Consumer: DDGS — `uv run flet run` locally; CI (`dev` group pins `flet[cli,desktop]==1.0.1`)
  builds APK (`--split-per-abi`), Windows, Linux+fpm DEB/RPM/TAR via
  `.github/workflows/build-all.yml`
- DDGS `pyproject.toml` today: `[tool.flet]` org/product/company/build_number=8,
  `[tool.flet.app] path="src"`, legacy `[tool.flet.app.boot_screen]
  startup_message`, `[tool.flet.android]` bundle_id/usesCleartextTraffic,
  android permission/meta_data/signing. `src/assets/icon.png` exists
  (icon generation active). CI already sets `FLET_CLI_NO_RICH_OUTPUT=1`,
  passes `--yes`, single `-v`, Android signing env vars.

---

## 1. COMPLETE API INVENTORY

### 1.1 Subcommands (`flet_cli/cli.py::get_parser`)

| Subcommand | Module | Purpose |
|---|---|---|
| `run` (DEFAULT when no subcommand given) | `commands/run.py` | Hot-reload dev loop |
| `build` | `commands/build.py` + `build_base.py` (~3490 lines) | Flutter-platform builds |
| `clean` | `commands/clean.py` | Delete `<app>/build/` |
| `create` | `commands/create.py` | Scaffold from cookiecutter template |
| `debug` | `commands/debug.py` | `flutter run` on device/desktop |
| `test` | `commands/test.py` (+ `test_host.py` re-export) | On-device integration tests via pytest |
| `pack` | `commands/pack.py` | PyInstaller desktop exe/bundle (NOT Flutter) |
| `publish` | `commands/publish.py` | Static Pyodide web site → `dist/` |
| `serve` | `commands/serve.py` | Static file server w/ COOP+COEP headers |
| `devices` | `commands/devices.py` | List connected iOS/Android devices |
| `emulators` | `commands/emulators.py` | List/create/start/delete emulators |
| `doctor` | `commands/doctor.py` | Print env info (thin: Flet ver + Python only) |
| `mcp` | `commands/mcp.py` | LLM-agent MCP server — registered ONLY if `flet_mcp` installed |
| `--version [--json]` | `cli.py` | Text or `{"flet","flutter","linux_dependencies"}` JSON |

Global: `-v/--verbose` (count: `-v`=info, `-vv`=debug + `--verbose` passthrough to
flutter/serious_python + streams subprocess output). App-script args go after a bare
`--` separator (`flet run app.py -- --verbose`); `--` is rejected for non-`run`
commands. Unknown args on `run` produce a hint to use `--`.

### 1.2 `flet run` flags (all in `commands/run.py`)

`script` (default `.`, dir → `main.py`), trailing `script_args`, `-p/--port`,
`--host` (`"*"` = all IPs), `--name` (page route for multi-app), `-m/--module`
(dotted path), `-d/--directory` (watch dir, non-recursive), `-r/--recursive`,
`-n/--hidden`, `-w/--web`, `--ios`, `--android` (QR + LAN URL, android launcher
URL form), `-a/--assets` (default `assets/`, resolved vs script dir, missing dir
dropped with warning unless explicitly typed), `--ignore-dirs` (CSV).
Port default: random free TCP port on Windows/`--web`, fixed 8551 for ios/android,
Unix-domain socket elsewhere. Runtime: child cwd = `.flet/storage/data`,
`FLET_APP_STORAGE_{DATA,CACHE,TEMP}`, `TMPDIR/TEMP/TMP`, `PYTHONPATH+=invoke-cwd`,
`PYTHONIOENCODING=utf-8`, `PYTHONWARNINGS=default::DeprecationWarning`;
`FLET_LOG_LEVEL=info|debug` on `-v/-vv`; missing `flet-web`/`flet-desktop`
auto-installed. Creates git-ignored, Windows-hidden `.flet/` (`storage/`,
`.gitignore` with `*`, README.md). `[tool.flet.app.path]` re-roots script dir.
Hot reload: watchdog `Observer`, 0.5 s debounce, SIGTERM restart.

### 1.3 `flet build` — targets & shared flags

Targets (`build <macos|linux|windows|web|apk|aab|ipa|ios-simulator>`):
host matrix — ipa/ios-simulator macOS-only; macos/windows/linux host-only;
web/apk/aab anywhere. `--show-platform-matrix` prints it and exits.
Default out dir `<app>/build/<dist>`; `-o/--output` overrides.
`--arch` (repeatable; Android `arm64-v8a|armeabi-v7a|x86_64`, macOS `arm64|x86_64`;
empty Android ⇒ all ABIs the bundled Python supports).
Identity/metadata: `--project/--artifact/--product/--org/--bundle-id/--company/
--copyright/--description/--module-name`; version from `--build-version`
(fallback `project.version` → `tool.poetry.version`) and `--build-number`
(fallback `tool.flet.build_number`) → flutter `--build-name/--build-number`.
Android: `--split-per-abi` (⇔ `tool.flet.android.split_per_abi`),
`--android-legacy-packaging/--no-android-legacy-packaging`,
`--android-extract-packages` (zip-unsafe pkgs, merged over built-in default list
— currently empty), `--android-permissions/--features/--meta-data`
(`K=V` pairs), `[tool.flet.android.provider]` tables, `[tool.flet.android.
gradle_properties]` (default `org.gradle.jvmargs=-Xmx8G …`, android.useAndroidX),
`[tool.flet.android.proguard_rules]` + `proguard_default_rules=false` kill-switch,
`--android-signing-key-store/-store-password/-key-password/-key-alias`
(`key_store`/`key_alias` also in pyproject), `--permissions location|camera|
microphone|photo_library` cross-platform shortcut, `--deep-linking-scheme/-host`.
iOS: `--ios-team-id/--ios-export-method/--ios-provisioning-profile/
--ios-signing-certificate`; unsigned ipa ⇒ `--no-codesign` → `.xcarchive` only;
preflight validates profile (installed? expired? team/bundle-id match) before building.
macOS lanes `--macos-distribution none|developer-id|app-store` (+ pyproject
`[tool.flet.macos.signing]` with per-lane subtables) + `--macos-signing-identity/
--macos-notary-profile/--macos-provisioning-profile/--macos-installer-identity`;
developer-id notarizes+staples; app-store embeds profile, writes installer `.pkg`,
requires `LSApplicationCategoryType`.
Web: `--base-url`, `--web-renderer auto|canvaskit|skwasm` (default **canvaskit** —
auto is ~6–7× slower frame path for Pyodide byte streaming), `--route-url-strategy
path|hash`, `--pwa-background-color/--theme-color` (bg falls through to splash
color), `--no-wasm`, `--no-cdn` (bundles Pyodide+CanvasKit+fonts, ~15 MB canvaskit +
~52 MB publish-mode CDN assets). There is **no `--no-web` flag** (only
`--no-web-splash/--no-ios-splash/--no-android-splash`).
Icons/splash (auto, `flet-platform-assets`): `assets/icon[_<platform>].png`
(.png>webp>jpg…, `.svg` rejected with warning, `.icns/.ico` platform-locked),
`assets/splash[_dark][_<platform>]`, `[tool.flet.]splash` color/dark_color/
android|ios|web toggles, `icon_background` (also Android adaptive bg),
`icon_fit→android_12_fit` + `icon_background→icon_bgcolor` aliases (old names
still read), `[tool.flet.macos.icon_style]`, per-platform icon_background.
Python: `--python-version` (else `project.requires-python` specifier, else manifest
default; beta lines need exact opt-in), pinned manifest date
`PYTHON_BUILD_RELEASE_DATE=20260921`. Packaging: `--compile-app/--no-compile-app`
(on), `--compile-packages/--no-compile-packages` (on), `--cleanup-app` (off),
`--cleanup-packages` (on), `--cleanup-app-files/--cleanup-package-files` globs,
`--exclude` (default `build`; web also drops `assets/` from app.zip),
`--source-packages`, per-platform `dependencies`/`dev_packages` (path-rewritten
`pkg @ file://` + `--no-cache-dir`), requirements.txt fallback, bare `flet==ver`.
`--info-plist/--macos-entitlements` (`K=V`, TOML values), `--flutter-build-args`
(repeatable; also `[tool.flet[.platform].flutter.]build_args`), `[tool.flet.
flutter.pubspec]` merge, `--template/--template-dir/--template-ref`.
CI-oriented shared flags (all build/debug/test/devices/emulators via
`flutter_base.py`): `--no-rich-output`, `--yes`, `--skip-flutter-doctor`.

### 1.4 Other subcommands' flags

- `debug [macos|linux|windows|web|ios|android]` (+ all build flags):
  `-d/--device-id`, `--show-devices`, `--release`, `--route`.
- `test [platform]` (+ all build flags): `-d/--device-id`, `--tests-dir`
  (default `tests/`), `-u/--update-goldens`, `--flutter-test-host <dir>`
  (reuse CI-cached provisioned host), `-k <pytest-expr>`. Needs `flet[test]`
  (pytest); `provision_test_host()` importable so plain `pytest` works.
- `pack script`: `-i/--icon`, `-n/--name`, `-D/--onedir` (Win-only, else onefile),
  `--distpath`, `--add-data/--add-binary/--hidden-import` (repeatable),
  `--product-name/--file-description/--product-version/--file-version/
  --company-name/--copyright`, `--codesign-identity`, `--bundle-id`
  (macOS `osx-bundle-identifier`; Linux taskbar id + generated `.desktop` entry
  with `StartupWMClass`), `--debug-console`, `--uac-admin` (Win),
  `--pyinstaller-build-args`, `-y/--yes`. **Deterministic**: fixed-timestamp
  zip/tar + `<archive>.sha256` sidecar keying the runtime client cache.
  `FLET_VIEW_PATH` overrides client binaries.
- `publish [script]`: `--pre` (micropip prereleases), `--python-version`,
  `-a/--assets`, `--distpath`, `--app-name/--app-short-name/--app-description`,
  `--base-url`, `--web-renderer`, `--route-url-strategy`, `--pwa-*`,
  `--no-cdn` (else ~52 MB of `pyodide/`+`canvaskit/` pruned from `dist`).
- `serve [web_root=./build/web] -p/--port` (default 8000; COOP/COEP/CORS headers).
- `devices [ios|android]`: `--device-timeout` (default 10 s),
  `--device-connection both|attached|wireless`.
- `emulators [start|create|delete] [name] --cold`.
- `create [dir]`: `--project-name/--description/--template app|extension/
  --template-ref`.
- `doctor`: no flags beyond `-v`; prints Flet version + Python only
  (Flutter version is a TODO).

### 1.5 Config files & incremental-build machinery (CI-exploitable)

- `pyproject.toml` is the whole config surface (`load_pyproject_toml`,
  dotted getters; sections enumerated in 1.3). Precedence generally:
  CLI > `[tool.flet.<platform>.*]` > `[tool.flet.*]` > env var > default.
  No `fletd` settings file exists — the only `fletd` reference is `pack.py`
  deleting the legacy `fletd` binary from the bundle.
- `build/.hash/{template-1,template-2,icons,splashes,package}` stamps ⇒
  unchanged rebuilds skip cookiecutter re-render, icon/splash regen, and
  site-packages reinstall (`--skip-site-packages` auto-added). Changing bundled
  Python auto-wipes `build/`. Template zip cached at
  `$FLET_CACHE_DIR/build-template/v<ver>/` (immutable, download-once);
  python-build manifest at `$FLET_CACHE_DIR/python-build/`; Pyodide runtimes at
  `$FLET_CACHE_DIR/pyodide/<ver>/`. `build/.python-version` marker guards
  bytecode mixing. Output dirs of previous `--arch`/rename runs are pruned
  before copy so stale artifacts can't leak.
- Determinism: `pack` archives are byte-identical for identical inputs
  (fixed mtimes, sorted entries, zeroed uid/gid). Flutter APK/AAB names are
  normalized (`app-release…` → `<artifact>…`, `-release` dropped).

---

## 2. LATENT CAPABILITIES FOR DDGS (ranked by impact)

1. **Cache the Flet/Flutter toolchain in CI (biggest speedup, zero code).**
   Nothing is cached today: every job re-downloads the Flutter SDK
   (`~/flutter/<ver>`), Temurin JDK 17 (`~/java/`), Android SDK/cmdline-tools,
   the build-template zip + python-build manifest (`$FLET_CACHE_DIR`), and the
   Gradle cache. Set `FLET_CACHE_DIR` to a workspace path and add
   `actions/cache` for it + `~/flutter` + `~/.gradle`. The `.hash` stamps then
   make warm rebuilds skip packaging/template work entirely.
2. **Override Gradle memory for 7 GB GitHub runners.** Default
   `org.gradle.jvmargs=-Xmx8G -XX:MaxMetaspaceSize=4G …` exceeds a standard
   runner's RAM. The template comment says so explicitly. Add
   `[tool.flet.android.gradle_properties] "org.gradle.jvmargs" = "-Xmx4G …"`
   — avoids OOM kills / swap stalls on `build-apk-split`.
3. **Trim the APK ABI matrix.** No `--arch` is passed, so every ABI the bundled
   Python ships is built. `--arch arm64-v8a --arch armeabi-v7a` (or
   `tool.flet.android.target_arch`) drops the emulator-only `x86_64` slice —
   faster builds, fewer/smaller split APKs. (Keep x86_64 only if emulator
   testing matters.)
4. **`--skip-flutter-doctor` / `FLET_CLI_SKIP_FLUTTER_DOCTOR` in CI.**
   Doctor runs only on failure paths today, but setting it removes the last
   failure-path delay and log noise in non-interactive runs (you already set
   the sibling `FLET_CLI_NO_RICH_OUTPUT`).
5. **Move version stamping into `pyproject.toml`.** `--build-version/
   --build-number` CLI args duplicate `project.version` and
   `tool.flet.build_number` (already 8); dropping the CLI args removes the
   drift class the quality gate hand-checks. `--product/--org/--company` are
   likewise already in `[tool.flet]`.
6. **Hot-reload loop upgrades (dev ergonomics).** `-d/-r` directory watching
   (+ `--ignore-dirs` for `src/assets` churn), `-m` module mode, `--web` for
   browser testing, `--android/--ios` QR-to-device runs, per-run `--name` for
   parallel instances, `script_args` after `--` instead of env hacks.
7. **Splash + boot-screen branding, free.** `src/assets/icon.png` already drives
   icons; adding `assets/splash.png` (+ `splash_dark.png`) and
   `[tool.flet.splash] color/dark_color` themes Android12/iOS/web launch
   (see §3 for the legacy-key rename needed first).
8. **`flet test` + `--flutter-test-host` when integration tests land.**
   `provision_test_host()` caches the Flutter host by input hash; pass a
   CI-cached dir via `--flutter-test-host` to skip provisioning.
9. **`flet serve` for web-build smoke tests; `flet clean` for stale-`build/`
   recovery** (Python-version switches already self-clean).
10. **`flet publish --no-cdn`** as an offline/air-gapped fallback for the web
    client; **`flet pack`** only if a PyInstaller single-file exe is ever
    wanted instead of the Flutter Windows build (it already emits version
    info + icon + deterministic archives).
11. **`flet doctor`** — currently near-useless (no Flutter/SDK checks, marked
    TODO); don't wire it into support scripts until it grows.

## 3. GOTCHAS

- **DDGS uses a deprecated boot-screen key.** `[tool.flet.app.boot_screen]
  startup_message` is the legacy location; 1.0.1 maps it onto the built-in
  screen with a deprecation warning. Canonical: `[tool.flet.boot_screen]` with
  `name="flet"` + options table (per-platform `[tool.flet.<platform>.
  boot_screen]` wins per key).
- **Renamed splash keys (1.0.0):** `icon_background→icon_bgcolor`,
  `icon_dark_background→icon_dark_bgcolor`, `icon_fit→android_12_fit`. Old
  names still work via alias — no breakage, but write new names.
- **No `--no-web`, no MSI/DEB/RPM/TAR targets.** Web exclusion is per-feature
  (`--no-wasm`, `--no-cdn`, `--no-web-splash`); Linux packaging beyond the raw
  bundle is yours (fpm, as CI does). `pack` never makes MSI.
- **Platform locks:** ipa/ios-simulator and macOS signing need macOS;
  `ios_export_method` default `debugging`; unsigned ipa silently yields only
  `.xcarchive`. Android needs JDK 17 + cmdline-tools (auto-installed with
  `--yes`, or pre-seed `JAVA_HOME`/`ANDROID_HOME`/`ANDROID_SDK_ROOT`).
  arm64 Linux has no prebuilt Flutter — the CLI git-clones + precaches.
- **macOS lane footguns:** `distribution=none` + ad-hoc is the only lane that
  tolerates `-`; per-lane subtables must be exactly `developer-id|app-store`;
  `app-store` hard-requires provisioning profile + `LSApplicationCategoryType`
  (+ `ITSAppUsesNonExemptEncryption` warning); notary prefers keychain profile
  over ambient `APPLE_API_*`.
- **Silent-merge risks:** `[tool.flet.flutter.pubspec]` replaces (not merges)
  per-section deps; `app-store`/`test_mode` pin `artifact_name=project_name`;
  `--cleanup-packages` defaults ON; provider tables reject `name`/`true`;
  Android permission values must be bool-or-table.
- **Env vars honored (complete, grepped):**
  `FLET_CLI_NO_RICH_OUTPUT`, `FLET_CLI_SKIP_FLUTTER_DOCTOR`, `FLET_CACHE_DIR`,
  `FLET_VIEW_PATH`, `FLET_WEB_RENDERER`, `FLET_WEB_ROUTE_URL_STRATEGY`,
  `FLET_WEB_NO_CDN` (help-text only; read via `tool.flet.web.cdn`/flag path —
  do NOT rely on it), `FLET_ASSETS_DIR` (publish only), `FLET_ANDROID_SIGNING_
  KEY_STORE/_STORE_PASSWORD/_KEY_PASSWORD/_KEY_ALIAS`,
  `FLET_MACOS_SIGNING_IDENTITY/_INSTALLER_IDENTITY/_NOTARY_PROFILE/
  _PROVISIONING_PROFILE`, `APPLE_API_KEY/_KEY_ID/_ISSUER`, `FLET_PYTHON_BUILD_
  RELEASE_DATE/_MANIFEST`, `ANDROID_HOME`, `ANDROID_SDK_ROOT`, `JAVA_HOME`,
  `FLET_TEST_*` (test harness internals), `FLET_APP_STORAGE_*`/`FLET_SERVER_*`/
  `FLET_LOG_LEVEL`/etc. (run→app process contract, not CLI knobs).

## 4. COVERAGE

**45 / 45 `.py` files read** — `cli.py`, `version.py`, `commands/`
(base, options, run, build, build_base [full, 3 passes], flutter_base, pack,
publish, clean, create, debug, devices, doctor, emulators, serve, test,
test_host, mcp), `utils/` (android, android_sdk, cli, distros, flutter,
hash_stamp, ios_sign, jdk, linux_deps, macos_sign [API + identity/signing flow;
per-file crypto internals sampled], merge, plist, processes,
project_dependencies, pyodide, pyproject_toml, python_versions,
template_cache), `__pyinstaller/` (config, hook-flet, macos_utils, win_utils,
utils, `__init__`, rthooks). Consumer: `pyproject.toml [tool.flet*]`,
`.github/workflows/build-all.yml` (all 5 jobs), `src/assets/` listing.
