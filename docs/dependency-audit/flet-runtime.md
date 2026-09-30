# flet-runtime — flet_desktop · flet_platform_assets · flutter/ (Flet 1.0.1)

> Scope: the *runner* side of Flet — how the desktop window appears on a dev
> machine, how icons/splashes are rendered at `flet build` time, and what the
> `flutter/` Dart overlay is. Python UI controls are covered in
> `flet-core-controls.md`; build/pack CLI in `flet-cli.md`; ads in `flet-ads.md`.

## 1. INVENTORY

### 1a. flet_desktop (pip `flet-desktop` 1.0.1, ~70 KB, pure Python, zero binaries)

Three modules, no `app/` directory in the wheel (see below for why):

| File | Lines | Role |
|---|---|---|
| `__init__.py` | ~700 | Client resolution, download, cache, launch (`open_flet_view` / `open_flet_view_async` / `close_flet_view` / `ensure_client_cached`) |
| `version.py` | 1 | `version = "1.0.1"` — the single pin everything keys off |
| `win_taskbar.py` | ~318 | Windows taskbar identity: stamps `System.AppUserModel.*` props on the Flutter window via `SHGetPropertyStoreForWindow` |

**How the Flutter desktop binary is located and launched.**
`__locate_and_unpack_flet_view(page_url, assets_dir, hidden)` resolves per
platform in strict order:

1. `build/windows/*.exe` (or `build/macos/*.app`, or an executable bit set in
   `build/linux/`) — i.e. output of the latest `flet build` wins.
2. `FLET_VIEW_PATH` env var (dev override; expects `flet.exe` / `.app` / `flet` inside).
3. Versioned cache `~/.flet/client/flet-desktop-{flavor}-{version}[-{fingerprint}]`,
   populated from a bundled archive or downloaded from GitHub Releases.

Launch argv is `[exe, page_url, pid_file, (assets_dir?)]`; `hidden=True` sets
`FLET_HIDE_WINDOW_ON_START=true` in the child env. macOS goes through
`open … -n -W --args`. The client writes its PID to a temp pid-file;
`close_flet_view()` SIGKILLs via that file. Sync and async (`asyncio`
subprocess) open variants exist.

**Env-var overrides (complete list, grepped from source):**

| Var | Read in | Effect |
|---|---|---|
| `FLET_VIEW_PATH` | `__locate_and_unpack_flet_view` | Skip cache/download, use a local client dir |
| `FLET_CLIENT_URL` | `__download_flet_client` | Replace the whole GitHub Releases download URL |
| `FLET_DESKTOP_FLAVOR` | `__get_desktop_flavor` | `full` \| `light` (else `pyproject [tool.flet].desktop_flavor`, else `light` on Linux / `full` elsewhere) |
| `FLET_LINUX_DISTRO` | `__get_linux_distro_id` | Override glibc-based distro pick (`debian10` … `ubuntu24.04`) |
| `FLET_APP_ID` | `__linux_identity_args` | Linux `argv[0]` alias → per-app taskbar grouping / WM_CLASS / Wayland app_id |
| `FLET_APP_USER_MODEL_ID` | `open_flet_view` → `win_taskbar` | Triggers taskbar stamping (set by the `flet pack` PyInstaller hook) |
| `FLET_APP_RELAUNCH_COMMAND` / `_DISPLAY_NAME` / `_ICON` | `win_taskbar.apply_relaunch_props_async` | Taskbar pin target, shown name, icon; derived from the UserModelID path when unset |
| `FLET_HIDE_WINDOW_ON_START` | child client (set when `hidden=True`) | Start hidden (tray-style apps) |

There is **no `FLET_FORCE_LOCAL_SERVER`**. The nearest real knob is
`FLET_FORCE_WEB_SERVER` (read in `flet/app.py`, forced by `flet run --web`):
desktop view is skipped and the app is served over HTTP instead.

**Version pinning.** `flet/utils/pip.py::ensure_flet_desktop_package_installed()`
installs `flet-desktop` on demand and raises `RuntimeError` on any mismatch
between `flet_desktop.version.version` and the Flet SDK version. DDGS pins
`flet[cli,desktop]==1.0.1` in the `dev` dependency group — the two must be
bumped together.

**Download-on-first-use.** No `app/` dir ships in the wheel
(`get_package_bin_dir()` points at a non-existent `<pkg>/app`). First desktop
run downloads `flet-windows.zip` / `flet-macos.tar.gz` /
`flet-linux-{distro}[-light]-{arch}.tar.gz` from
`github.com/flet-dev/flet/releases/download/v{version}/` with a rich progress
bar, extracts to a temp dir, then atomically renames into the cache
(no half-extracted cache ever counts as valid).

**Cache hygiene.** Each use touches a `.last-used` marker; fingerprinted
siblings (see bundling) unused for 30 days are rename-then-delete GC'd
(rename fails on Windows if files are in use → running apps are never
collected); `.trash-*` leftovers from interrupted deletes are swept.

**Bundled-binary entry point (how DDGS.exe goes standalone).** `flet pack`
(PyInstaller) compresses the client dir into an archive + `.sha256` sidecar and
the `hook-flet.py` hook collects it as `flet_desktop/app`. At runtime
`ensure_client_cached()` prefers that archive and keys the cache dir with the
first 12 hex digits of its SHA-256, so a client patched with DDGS's icon and
metadata gets its own cache dir and never collides with the vanilla client or
another app's patched client of the same Flet version.

**Non-`.py` assets in the installed package: none.** No exe, no zip, no data
files — the install is three source files (+ `__pycache__`). The runtime is
entirely a download-or-bundle acquisition, never a shipped binary.

### 1b. flet_platform_assets (pure-Python PIL renderer, ~160 KB, 7 modules)

| Module | Role |
|---|---|
| `__init__.py` | Public re-exports only (`render_icons`, `render_splash`, `load_source`, `write`, option/model types) |
| `_icons.py` | Per-platform icon targets: iOS appiconset (15 sizes, alpha flattened — App Store rejects alpha), macOS appiconset (7 sizes + squircle/drop-shadow grid), Android mipmap (48–192) + adaptive drawable (108–432), Windows `.ico` **16/32/48/256 multi-entry**, web manifest icons + maskable + apple-touch, Linux hicolor 16–512 named by `application_id` |
| `_splash.py` | Splash bitmaps for **android / ios / web only** — there is no desktop splash. Android incl. night variants, Android-12 288dp/240dp circle-crop canvas; iOS launch images 1x/2x/3x + 1×1 background swatches; web light/dark 1x–4x PNGs |
| `_models.py` | `Target` / `AssetSpec` / `IconOptions` / `SplashOptions` / `RenderResult` (assets + `warnings` + `ico` + `stale`) |
| `_source.py` | `load_source()`: EXIF-transpose, palette/CMYK→RGBA, animated GIF first frame, `.ico`/`.icns` treated as pre-rendered passthrough, one-shot downscale of sources > 2048 px (`MAX_SOURCE_SIZE`) |
| `_imaging.py` | Compositing primitives (`place`, `scale_to_fit`, `apple_grid`, `parse_hex_color`, `save_png`/`save_ico`) |
| `_write.py` | `write(result, project_dir, declared_only=True)`: deletes `stale` files, skips undeclared targets; `flet build` calls it with `declared_only=False` for splash/adaptive outputs |

Design rule worth knowing: rendering is pure (image in → images out, no
filesystem), diagnostics are data (`RenderResult.warnings`), and a *generic*
`icon.png` is shrunk to each platform's mask margin while platform-authored
artwork is placed full-bleed and left alone.

**Who consumes it:** `flet_cli/commands/build_base.py` — `render_icons()` +
`write()` for icons, `render_splash()` + `write()` for splash, driven by the
`[tool.flet]` icon/splash settings. DDGS never imports it directly; it runs at
`flet build` time in CI. Tunables that flow through: `IconOptions(background,
macos_style="auto"|"grid"|"raw", application_id)`,
`SplashOptions(color, dark_color, icon_background, icon_dark_background,
icon_fit="contain"|"none")`.

### 1c. flutter/ (NOT a Python package — a Dart overlay directory)

`site-packages/flutter/` contains exactly one thing: `flet_ads/` — the
**Dart/Flutter sources** of the AdMob extension (`pubspec.yaml` name
`flet_ads` 0.1.0, `publish_to: none`, depends on `google_mobile_ads ^9.0.0`
plus a relative `path:` dep on the Flet Flutter package). Contents: 8 Dart
files, 451 lines total (`lib/flet_ads.dart` re-exports `src/extension.dart`).

Purpose: build-time overlay — `flet build` stitches these Dart sources into
the generated Flutter project so the Python `BannerAd`/`InterstitialAd`/
`ConsentManager` controls (see `flet-ads.md`) have native counterparts.
Python API: none; it is never imported by Python code. Dart API surface:
`Extension(FletExtension)` with `ensureInitialized()` (initialises
`MobileAds` on mobile only), `createService()` → `InterstitialAd`,
`ConsentManager`; `createWidget()` → `BannerAd` (`NativeAd` present but
commented out behind a TODO). DDGS already exercises this path — its
`pyproject.toml` sets the AdMob `APPLICATION_ID` meta-data — so the verdict
is **fully utilized, no action**.

## 2. LATENT CAPABILITIES FOR DDGS (ranked)

1. **`FLET_VIEW_PATH` for the hot-reload dev loop.** Point dev machines at one
   pre-downloaded/unpacked client instead of every fresh venv re-downloading
   from GitHub Releases. Document it in the contributor setup; biggest
   time-saver on this list.
2. **Expose `flet_desktop.version.version` in the About/diagnostics screen.**
   One import, zero cost; turns "desktop window behaves oddly" reports into
   actionable version triples (app / flet SDK / desktop runner) and surfaces
   runner-vs-SDK skew immediately.
3. **`FLET_CLIENT_URL` as a CI/offline escape hatch.** Mirror the
   `flet-windows.zip` artifact internally and set the var in CI and on
   offline test machines. Direct fix for the offline-first-run gotcha below.
4. **Actually use the Android splash pipeline (pairs with the flet_cli audit
   finding that splash is unused).** `render_splash` already handles night
   variants, the Android-12 circle crop (`icon_fit="contain"` default) and
   stale-file cleanup — DDGS only needs splash source + colours in
   `[tool.flet]`. Note the boundary: splash covers Android only; the desktop
   window has no splash concept, where DDGS's `[tool.flet.app.boot_screen]
   startup_message` remains the right mechanism.
5. **Windows icon polish is automatic but verify it.** The multi-entry
   `.ico` (16/32/48/256 — the fix for mushy single-entry taskbar icons) is
   generated by every build; check `build/windows` output actually contains
   all four entries. If DDGS ever hand-tunes an icon, ship it as `.ico`:
   `load_source` treats `.ico`/`.icns` as pre-rendered and skips auto-framing.
6. **`FLET_FORCE_WEB_SERVER` as a dev-loop fallback.** When the desktop
   runner breaks (bad download, version skew), one env var keeps `flet run`
   usable over HTTP instead of blocking development.
7. **Honest ballast — no action:** `FLET_DESKTOP_FLAVOR` /
   `desktop_flavor` (only changes Linux `light` vs `full`; DDGS targets
   Windows + Android), `FLET_LINUX_DISTRO` + glibc table (Linux-only),
   `FLET_APP_ID` (Linux-only), `IconOptions.application_id` /
   Linux hicolor targets (no Linux target), `macos_style` + macOS/iOS icon
   sets (no Apple targets), `win_taskbar` relaunch vars (already set
   correctly by the `flet pack` hook — do not hand-set), `MAX_SOURCE_SIZE`
   / framing internals (sane defaults).

## 3. GOTCHAS

- **Offline first run fails.** The desktop client downloads from GitHub
  Releases on first use; a fresh machine with no network (or a blocked
  `github.com`) cannot open the desktop view at all. Mitigate with #1/#3
  above; never demo DDGS desktop from a cold venv on venue wifi.
- **Exact version lock between `flet` and `flet-desktop`.** Any skew raises
  `RuntimeError` from `ensure_flet_desktop_package_installed()`. DDGS's
  `dev`-group pin handles this — just bump both together and never let CI
  resolve them independently (this is also why desktop packages stay out of
  `[project].dependencies`: `flet build` must never resolve them for Android).
- **Runner ≠ SDK.** The window chrome/taskbar behaviour is owned by the
  downloaded runner, not the Python code — desktop-only bugs need the runner
  version (see #2), and `FLET_VIEW_PATH` to bisect.
- **Splash ≠ desktop.** `render_splash` emits android/ios/web files only;
  expecting a desktop splash image is a dead end — boot screen message is
  the desktop equivalent.
- **Generated-asset dirs are write-managed.** `write()` deletes `stale`
  files (e.g. night splash variants after dark artwork is removed, `.webp`
  leftovers); never hand-place files under Android `res/drawable-*`,
  `LaunchImage.imageset`, or `web/splash` — a rebuild can delete them.
- **Platform-gated imports crash cross-platform.** `win_taskbar` imports
  `ole32/shell32/shlwapi` at module top; it is only imported lazily under
  `is_windows()`. Never import it directly from app or test code.
- **`FLET_APP_ID` fails silent.** A value with `/` or control characters is
  ignored with a log warning and the window stays "flet".
- **Asset size pressure on APK/AAB.** Every mipmap density × (light + night)
  splash PNG ships in the Android build; keep splash/icon sources tight
  (the renderer already caps working size at 2048 px, but source choice is
  still yours).

## 4. COVERAGE

- `flet_desktop`: 3/3 `.py` files read (`__init__`, `version`,
  `win_taskbar`); 0 non-`.py` assets present (verified: no `app/` dir, no
  binaries in the 1.0.1 wheel); 10/10 `FLET_*` vars enumerated; downstream
  wiring confirmed in `flet/app.py`, `flet/utils/pip.py`,
  `flet_cli/commands/pack.py` + `__pyinstaller/hook-flet.py`.
- `flet_platform_assets`: 7/7 modules read; 6/6 platform target sets
  enumerated (ios, macos, android, windows, web, linux); consumer confirmed
  (`flet_cli/commands/build_base.py`).
- `flutter/`: fully enumerated (1 package, 8 Dart files, 451 lines);
  `pubspec.yaml` + `flet_ads.dart` + `src/extension.dart` read; purpose and
  (Dart-only) API documented; no Python surface to miss.
