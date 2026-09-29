# Flet 1.0.1 — Services & Non-Control Surface Audit

Slice: `flet/__init__.py`, `app.py`, `cli.py`, `data_channel.py`, `version.py`,
`pytest_plugin.py`, `auth/` (all), `canvas/__init__.py`, `components/` (all incl.
`hooks/`), `messaging/` (all), `pubsub/` (all), `security/`, `testing/` (all),
`utils/` (all), `fastapi/`, `controls/services/` (all 21), `controls/core/canvas/`
(all 15), plus `controls/` top-level: `animation.py`, `colors.py`, `theme.py`,
`types.py`, `events.py`, `client_action.py`, `device_info.py`, `query_string.py`,
`template_route.py`, `page.py`, `base_page.py`, `material/icons.py`,
`cupertino/cupertino_icons.py`, and `controls/core/`: `window.py`,
`window_drag_area.py`, `gesture_detector.py`, `draggable.py`, `drag_target.py`,
`screenshot.py`, `interactive_viewer.py`.

DDGS usage verified by grep over `src/` (`*.py`, excl. `__pycache__`).

---

## 1. COMPLETE API INVENTORY

### 1a. App entry (`app.py`, `cli.py`, `version.py`, `pytest_plugin.py`, `__init__.py`)

- `ft.run(main, before_main, name, host, port, view, assets_dir, upload_dir, web_renderer, route_url_strategy, no_cdn, export_asgi_app)` — run app; `export_asgi_app=True` returns FastAPI ASGI app instead of running loop. `AppCallable = (Page) -> Any|Awaitable`.
- `ft.app(...)` (alias surface in `__init__`) — same runner family.
- `flet.cli.main()` — `flet` CLI entry (`run`, `build`, `pack`).
- `flet.version.get_flet_version() / get_flutter_version() / from_git() / find_repo_root()` — version introspection.
- `flet.pytest_plugin` — pytest fixtures: `_create_flet_app(request)`, device-mode helpers (`_is_device_mode`, `_resolve_flutter_test_host`, `_import_app_main`) — backing for `FletTestApp`.
- `flet.DataChannelOpenEvent` — fired by Dart when it opens a DataChannel for a control; carries the channel.
- `flet.DataChannel(ABC)` — `on_bytes(handler) / send(payload: bytes) / close()` — dedicated bidirectional byte transport (BYPASSES JSON/msgpack control protocol).
- `flet.__init__` re-exports ~1073 names; `Icons`/`CupertinoIcons` are lazy proxies (`dir(ft.Icons)` lists all; `ft.Icons.random(exclude, weights)` exists).

### 1b. Window / session chrome (`controls/core/window.py`, `window_drag_area.py`, `page.py`, `base_page.py`)

`ft.Window` (desktop only — macOS/Windows/Linux): props —
- `width/height/top/left`, `min_width/min_height/max_width/max_height`, `aspect_ratio`, `bgcolor` (pair with `Page.bgcolor` for transparency), `opacity` (0–1), `brightness`, `maximized/minimized/minimizable/maximizable/resizable/movable(macOS only)/full_screen`, `always_on_top`, `always_on_bottom` (Linux/Win only), `prevent_close` (intercept native close → `on_event(CLOSE)`), `skip_task_bar`, `title_bar_hidden`, `title_bar_buttons_hidden` (macOS), `frameless`, `progress_bar` (0–1 taskbar/dock progress), `focused`, `visible`, `shadow`, `alignment`, `badge_label` (macOS), `icon` (.ico, Windows), `ignore_mouse_events`, `on_event: EventHandler[WindowEvent]`.
- Methods: `wait_until_ready_to_show() / destroy() / center() / close() / to_front() / start_dragging() / start_resizing(edge: WindowResizeEdge)`.
- `ft.WindowEventType`: CLOSE, FOCUS, BLUR, HIDE, SHOW, MAXIMIZE, UNMAXIMIZE, MINIMIZE, RESTORE, RESIZE, RESIZED, MOVE, MOVED, LEAVE_FULL_SCREEN, ENTER_FULL_SCREEN. `WindowResizeEdge`: 8 edges/corners.
- `ft.WindowDragArea(LayoutControl)` — frameless/custom-titlebar drag region (wrap header content).
- `Page` session/task APIs: `run_task(handler, *args)` (async on event loop), `run_thread(handler, *args)` (threadpool), `loop` / `executor` props, `session() -> Session`, `get_control(id)`, `update(*controls)`, `error(msg)`.
- `Page` navigation/views: `navigate(route)`, `push_route(route)` (async), `pop_views_until(route, result)`, `render/render_views`, `route`/`views` props.
- `Page` dialogs/drawers/media: `show_dialog/pop_dialog`, `show_drawer/close_drawer/show_end_drawer/close_end_drawer`, `scroll_to(key, ...)` (BasePage), `take_screenshot() -> bytes`, `take_animation(frames) -> gif bytes` (BasePage), `overlay`/`controls` lists.
- `Page.get_upload_url(file_name, expires) -> str` — page-relative URL feeding `FilePickerUploadFile`.
- `Page.query() -> QueryString` (`query["k"]`, `UrlComponents`: pathname/search/hash) and `Page.url/name` — deep-link/read URL state.
- `Page.get_device_info() -> DeviceInfo|None` (locales, CPUs, arch, memory, model, OS versions, browser fields on web), `Page.set_allowed_device_orientations([...])` (mobile).
- `Page.auth -> Authorization|None`, `Page.login(provider, fetch_user, fetch_groups, scope, saved_token, on_open_authorization_url, complete_page_html, redirect_to_page, authorization)` (async), `Page.logout()`.
- `Page.pubsub -> PubSubClient`; `Page.url_launcher` (persistent service slot); `Page.services` list + `register_service/unregister_services`.
- `PageMediaData`, `PageResizeEvent` (BasePage); `Overlay`, `Dialogs` helpers.

### 1c. PageControl services (all `Service(BaseControl)`, async `_invoke_method` over client channel)

- `ft.Clipboard` — `set(str) / get() -> str|None / set_image(bytes)` (mobile+web only) `/ get_image() -> bytes|None / set_files([paths]) -> bool` (desktop only) `/ get_files() -> [str]` (desktop+Android). `ft.CopyToClipboard(data)` — ClientAction: copies inside user gesture (Safari/web-safe).
- `ft.HapticFeedback` — `heavy_impact() / light_impact() / medium_impact() / vibrate() / selection_click()` (mobile; no-op elsewhere).
- `ft.Share` — `share_text(text, title, subject, preview_thumbnail, share_position_origin, download_fallback_enabled, mail_to_fallback_enabled, excluded_cupertino_activities) -> ShareResult`, `share_uri(uri, ...) -> ShareResult`, `share_files([ShareFile], title, text, subject, ...) -> ShareResult`. `ShareFile(path|data+mime_type+name)`, ctors `from_path / from_bytes`. `ShareResult{status: SUCCESS|DISMISSED|UNAVAILABLE, raw}`. `ShareCupertinoActivityType` (20 iOS/macOS exclusions). `ft.ShareText(text, title, subject)` — gesture-safe ClientAction (no result callback).
- `ft.UrlLauncher` — `launch_url(url|Url, mode=PLATFORM_DEFAULT|IN_APP_WEB_VIEW|IN_APP_BROWSER_VIEW|EXTERNAL_APPLICATION|EXTERNAL_NON_BROWSER_APPLICATION, web_view_configuration{enable_javascript, enable_dom_storage, headers}, browser_configuration{show_title}, web_only_window_name)`, `can_launch_url(url) -> bool`, `close_in_app_web_view()`, `open_window(url, title, width, height)` (web popup), `supports_launch_mode(mode)`, `supports_close_for_launch_mode(mode)`. `ft.OpenUrl(url, target)` — gesture-safe ClientAction (popup-blocker safe).
- `ft.FilePicker` — `pick_files(dialog_title, initial_directory, file_type=ANY|MEDIA|IMAGE|VIDEO|AUDIO|CUSTOM, allowed_extensions, allow_multiple, with_data) -> [FilePickerFile{id,name,size,path,bytes}]`, `save_file(dialog_title, file_name, initial_directory, file_type, allowed_extensions, bytes) -> path|None`, `get_directory_path(dialog_title, initial_directory) -> path|None`, `upload([FilePickerUploadFile{upload_url, method, id|name}])` + `on_result: FilePickerResultEvent / on_upload: FilePickerUploadEvent{file_name, progress 0–1, error}`. `ft.PickFiles` ClientAction. Linux desktop needs Zenity.
- `ft.Connectivity` — `get_connectivity() -> [ConnectivityType: BLUETOOTH|ETHERNET|MOBILE|NONE|OTHER|VPN|WIFI]`, `on_change: ConnectivityChangeEvent{connectivity}`.
- `ft.SharedPreferences` — `set(key, str|int|float|bool|list[str]) / get / contains_key / remove / get_keys(prefix) / clear()` (all async).
- `ft.StoragePaths` — `get_application_cache_directory / get_application_documents_directory / get_application_support_directory / get_downloads_directory / get_temporary_directory / get_console_log_filename / get_library_directory` (Apple only) `/ get_external_storage_directory(s)` (Android only). Web raises `FletUnsupportedPlatformException`; env shortcuts `FLET_APP_STORAGE_CACHE/DATA/TEMP/CONSOLE`.
- `ft.Wakelock` — `enable() / disable() / is_enabled()` (keep awake during long ops).
- `ft.SemanticsService` — `announce_message(message, rtl, assertiveness=POLITE|ASSERTIVE)` (a11y live announcements; Android prefers live_region), `announce_tooltip(message)` (Android), `get_accessibility_features() -> AccessibilityFeatures{accessible_navigation, bold_text, disable_animations, high_contrast, invert_colors, reduce_motion, on_off_switch_labels, supports_announcements}`.
- `ft.BrowserContextMenu` — `enable() / disable() / disabled` (web: browser right-click menu vs Flet menus).
- `ft.ScreenBrightness` — `get/set_system_screen_brightness, can_change_system_screen_brightness (needs WRITE_SETTINGS perm), get/set/reset_application_screen_brightness, is/set_animate, is/set_auto_reset, on_system/application_screen_brightness_change` — Android/iOS only (`before_update` raises elsewhere).
- `ft.Battery` — `get_battery_level() -> int|None / get_battery_state() -> BatteryState / is_in_battery_save_mode()`, `on_state_change: BatteryStateChangeEvent`.
- `ft.ShakeDetector` — `minimum_shake_count=1, shake_count_reset_time_ms=3000, on_shake` (mobile).
- Sensors (`Accelerometer`, `UserAccelerometer`, `Gyroscope`, `Magnetometer`, `Barometer`) — `interval / cancel_on_error / on_reading{...axis/pressure fields} / on_error: SensorErrorEvent`; mobile only.
- `ft.ClientAction` base + `shared_service(T) / action_field(default)` — client-executed actions bound to a shared service method (`CopyToClipboard`, `ShareText`, `OpenUrl`, `PickFiles`); no Python round-trip, gesture-safe on web.

### 1d. Animation (`controls/animation.py`)

- `ft.Animation(duration: Duration|int-ms, curve: AnimationCurve)` + `.copy(...)`; shorthand `AnimationValue = bool|int|Animation` (`True` = 1000ms LINEAR).
- `ft.AnimationCurve` — ~45 curves: LINEAR, EASE/EASE_IN/OUT/IN_OUT (+BACK/CIRC/CUBIC incl. M3 `EASE_IN_OUT_CUBIC_EMPHASIZED`/EXPO/QUAD/QUART/QUINT/SINE/TO_LINEAR), DECELERATE, FAST_OUT_SLOWIN, BOUNCE_IN/OUT/IN_OUT, ELASTIC_IN/OUT/IN_OUT, SLOW_MIDDLE, FAST_LINEAR_TO_SLOW_EASE_IN, LINEAR_TO_EASE_OUT. Implicitly animatable props accept `animate=` (e.g. DDGS uses `animate=ft.Animation(150–200, EASE_OUT)`).
- `ft.AnimationStyle{duration, reverse_duration, curve, reverse_curve}` + `no_animation()` — override Material default animations.

### 1e. Gestures / drag / capture (`gesture_detector.py`, `draggable.py`, `drag_target.py`, `screenshot.py`, `interactive_viewer.py`, `events.py`)

- `ft.GestureDetector` — ~50 handlers: `on_tap(+down/up/move/cancel)`, `on_double_tap(+down/cancel)`, `on_multi_tap`, `on_secondary/tertiary_tap*`, `on_long_press*(+down/start/move_update/up/end/cancel)`, `on_secondary_long_press*`, `on_horizontal/vertical_drag*(down/start/update/end/cancel)`, `on_pan*(down/start/update/end/cancel)`, `on_right_pan*`, `on_scale*(start/update/end)`, `on_hover/on_enter/on_exit`, `on_scroll`, `on_force_press*`. Event types in `controls/events.py`: `TapEvent/TapMoveEvent/MultiTapEvent/LongPress*/DragDown/Start/Update/End/ForcePress/ScaleStart/Update/End/PointerEvent/ScrollEvent`.
- `ft.Draggable` — `content/content_when_dragging/content_feedback, group="default", axis/affinity, max_simultaneous_drags, on_drag_start/complete/cancel/...`.
- `ft.DragTarget` — `group, on_accept/leave/move/will_accept` (`DragTargetEvent/LeaveEvent/WillAcceptEvent`).
- `ft.Screenshot(content)` — `capture(pixel_ratio, delay) -> PNG bytes` (any control subtree).
- `ft.InteractiveViewer` — pan/zoom wrapper: `reset(animation_duration) / save_state / restore_state / zoom(factor) / pan(dx, dy, dz)` + min/max_scale props.

### 1f. Colors / Icons / Theme (`colors.py`, `material/icons.py`, `cupertino_icons.py`, `theme.py`)

- `ft.Colors` — `str,Enum` of Material palette incl. shades (`BLUE_100…BLUE_900`, `PRIMARY`, `SURFACE_...`, `ON_...`, random access); search via `dir(ft.Colors)` / grep `colors.py` (~493 lines).
- `ft.Icons` — lazy proxy over `material/icons.json` (thousands); `dir(ft.Icons)` enumerates, `ft.Icons.random(exclude, weights)`; `ft.CupertinoIcons` mirrors iOS set (`cupertino_icons.py` + `.json`). NEVER hardcode — verify with `dir()`.
- `ft.Theme` (3604-line `theme.py`): `color_scheme: ColorScheme{primary, secondary, surface, error, ...}`, `text_theme: TextTheme`, `visual_density`, `use_material3`, per-component themes (`AppBarTheme, BottomSheetTheme, CardTheme, CheckboxTheme, ChipTheme, DialogTheme, DropdownTheme, FloatingActionButtonTheme, IconButtonTheme, ListTileTheme, NavigationBarTheme/DrawerTheme/RailTheme, ProgressIndicatorTheme, SearchBarTheme/ViewTheme, SliderTheme, SnackBarTheme, SwitchTheme, TooltipTheme, ...`), `PageTransitionTheme/PageTransitionsTheme`, `SystemOverlayStyle`, `ColorScheme.from_seed(seed_color)`-style ctors. (No `ThemeManager` class in 1.0.1 — theming is `page.theme / page.dark_theme / page.theme_mode`.)

### 1g. PubSub / auth / canvas / data_channel / messaging / security / fastapi

- `Page.pubsub -> PubSubClient`: `send_all(msg) / send_all_on_topic(topic, msg) / send_others(msg) / send_others_on_topic(topic, msg) / subscribe(handler) / subscribe_topic(topic, handler) / unsubscribe[_topic|_all]()`. Hub (`PubSubHub`) fans out across sessions server-side.
- Auth: `OAuthProvider{client_id, client_secret, authorization_endpoint, token_endpoint, redirect_url, scopes, user_scopes, user_endpoint, user_id_fn, group_scopes, PKCE code_challenge/method/verifier, authorization_params}` + `_fetch_user/_fetch_groups` overrides; built-ins `GitHubOAuthProvider / GoogleOAuthProvider / Auth0OAuthProvider / AzureOAuthProvider`; `AuthorizationService`: `get_authorization_data() -> (url, state)`, `request_token(code)`, `get_token()` (auto-refresh), `dehydrate_token(saved_json)`; `OAuthToken{access_token, scope, token_type, expires_in/at, refresh_token}` + `to_json/from_json`; `User(dict){id, ...}`, `Group(dict){name}`.
- Canvas (`flet.canvas`): `Canvas(shapes, content, resize_interval, on_resize: CanvasResizeEvent{w,h})` + `capture(pixel_ratio) / get_capture() -> PNG bytes / clear_capture()`; shapes `Shape` → `Arc/Circle/Oval/Rect/Line/Path/Points(+PointMode)/Text/Image/Color/Fill/Shadow` with `ft.Paint` styling.
- `DataChannel`: raw-bytes RPC beside the control protocol (open via `on_data_channel_open` on a control; Dart `FletBackend.of(context).openDataChannel()`); `_ProtocolMuxedDataChannel(channel_id, conn)` multiplexes over socket; `Connection.send_data_channel_frame / data_channel_for / unregister_data_channel`.
- Messaging (`messaging/`): `MessageAction`: REGISTER_CLIENT, PATCH_CONTROL, CONTROL_EVENT, UPDATE_CONTROL_PROPS, INVOKE_METHOD, SESSION_CRASHED, PYTHON_OUTPUT (msgpack over socket); `Session`: patch/diff engine (`schedule_update`, `apply_patch`, `handle_invoke_method_results`, update scheduler), `SessionStore` (per-session `set/get/contains_key/remove/get_keys/clear`); servers `FletSocketServer / FletDartBridgeServer / PyodideConnection`.
- Security: `encrypt/decrypt(plain, secret) -> str` (Fernet), `encrypt_aes_gcm_256/decrypt_aes_gcm_256`.
- `flet.fastapi` (re-exports `flet_web.fastapi`): `FastAPI, FletApp, FletOAuth, FletStaticFiles, FletUpload, app, app_manager` — self-host Flet as ASGI (`ft.run(..., export_asgi_app=True)`).

### 1h. Components framework (`components/` + hooks + `router.py`)

- `@ft.component` + `Component` (lifecycle `did_mount/will_unmount`, `update()`, mount/render/unmount effect runners, observable auto-subscription); `Renderer.render(root_fn, *args)`, context push/pop.
- `ft.observable` / `Observable` (+`ObservableList/Dict`, `subscribe/unsubscribe/notify`); `ft.memo` (render memoization); `create_context/default/provider + use_context`.
- Hooks: `use_state(initial) -> (value, set_state)`, `use_effect(fn, deps)` + `on_mounted/on_unmounted/on_updated`, `use_memo(factory, deps)`, `use_ref(initial) -> MutableRef`, `use_callback(fn, deps)`, `use_dialog(dialog)`.
- `Router` (React-Router-like): `Route{path (:param, :opt?, :wild*, regex), index, component, children, loader, outlet, modal, recursive}`, `Router(routes, manage_views, ...)`, hooks `use_route_location/params/outlet/loader_data/view_path/is_route_active`, layout routes + modal overlays + swipe-back view stacks.
- `TemplateRoute(route)` — `resource/page/...` template matching; `QueryString`/`UrlComponents`.

### 1i. Testing (`testing/`)

- `FletTestApp(main, ...)` — boots real app in Flutter test host: `.page`, `.tester`, `resize_page(w,h)`, `assert_screenshot(name)` (golden PNG compare), `assert_gif(...)`, `create_gif(...)`, `DisposalMode`.
- `Tester` (Service): `pump/pump_and_settle`, `find_by_text/text_containing(regex)/key/tooltip/icon -> Finder{id,count,index (+.first/.last/.at(i))}`, `tap/mouse_click/right_mouse_click/mouse_double_click/long_press/enter_text/mouse_hover/drag/drag_from/tap_at/..._at`, `take_screenshot(name) -> PNG` (mobile only), `teardown()`. `RemoteTester` for attached runs.

### 1j. Utils (`utils/`)

- `platform_utils`: `is_windows/macos/linux/linux_server/ios/android/mobile/embedded/pyodide/asyncio/get_platform/get_arch/get_bool_env_var`.
- `files`: `copy_tree/rmtree/safe_tar_extractall/safe_zip_extractall/is_within_directory/which/get_current_script_dir`; `network`: `get_free_tcp_port/get_local_ip`; `strings.random_string`; `slugify`; `hashing.sha1/calculate_file_hash`; `browser.open_in_browser`; `vector.Vector`; `from_dict/convert_value`; `object_model.patch_dataclass`; `validation.V + validate(instance)` (declarative field rules).

---

## 2. WHAT DDGS DOESN'T USE (ranked by UX impact)

Already USED (do not re-suggest): `Connectivity+on_change`, `UrlLauncher.launch_url` (persistent service), `FilePicker.save_file`, `Clipboard.set/get`, `CopyToClipboard`, `SharedPreferences` (web path), `Theme/ColorScheme`, `Animation/EASE_OUT`, `GestureDetector` (basic taps), `Icons`, `page.window.min_width/min_height`, `page.run_task/show_dialog`, `ShareText` (1×), `OpenUrl`.

1. **Share.share_files / share_uri (+ ShareFile.from_path/from_bytes)** — IMPACT: HIGH. Download app with exactly one `ShareText` call; native sheet for saved images/videos/files (the core artifact of a downloader) is missing. `share_files([ShareFile.from_path(path)])` after `save_file`.
2. **HapticFeedback.light_impact / selection_click / vibrate** — IMPACT: HIGH (mobile). Zero usage. One-liners on download-complete, pull-to-refresh settle, toggle changes; `selection_click` for model picker/slider steps.
3. **Window taskbar + close UX: `page.window.progress_bar`, `prevent_close` + `on_event(CLOSE)`, `always_on_top`, `to_front/center`, `WindowDragArea`** — IMPACT: HIGH (desktop). Only min-size set. Taskbar progress during downloads/scrapes, exit-confirm while downloads run, drag region for custom titlebar.
4. **FilePicker.pick_files (+with_data) / get_directory_path / upload + Page.get_upload_url** — IMPACT: HIGH. Only `save_file` used. Enables chat attachments (screenshots, docs for AI summarizer), user-chosen download folder, server upload flows.
5. **PubSub (`page.pubsub.subscribe/send_all[_on_topic]`)** — IMPACT: MEDIUM-HIGH. Zero usage. Multi-window sync (second window, settings↔home), broadcast download-progress / connectivity without prop-drilling; topics per download-id.
6. **Canvas (+ capture/get_capture) for progress rings / waveforms** — IMPACT: MEDIUM. Zero usage. Custom download rings, audio-level viz, sparkline thumbs; `get_capture()` → shareable PNG.
7. **Screenshot.capture / InteractiveViewer (zoom/pan/reset) / page.take_screenshot** — IMPACT: MEDIUM. Zero usage. Pinch-zoom result images, screenshot-a-card-to-share, bug-report capture.
8. **SemanticsService.announce_message + AccessibilityFeatures** — IMPACT: MEDIUM. Zero usage. Spoken "Download complete / 3 results" for async ops; respect `disable_animations/reduce_motion`.
9. **Clipboard.get (paste) / set_files / UrlLauncher.can_launch_url / supports_launch_mode / open_window** — IMPACT: MEDIUM. `get()` + paste-button on Home search; `can_launch_url` before external open; `open_window` sized popup on web.
10. **StoragePaths.get_downloads_directory / get_application_documents_directory** — IMPACT: MEDIUM. Zero usage. Default save location = real Downloads dir instead of app sandbox; user-data vs cache separation.
11. **Draggable/DragTarget (+ full GestureDetector: long_press/drag/pan/scale/scroll/hover)** — IMPACT: MEDIUM. Only basic taps used. Drag-to-reorder history/queue, swipe-to-dismiss cards, long-press context menus, hover states on desktop.
12. **Testing: FletTestApp + Tester + assert_screenshot/assert_gif + Finder** — IMPACT: MEDIUM (quality). Zero usage. CI golden tests for home/results/settings screens; `enter_text+tappump_and_settle` search-flow tests.
13. **OAuth (Page.login/logout + GitHub/Google providers + dehydrate_token)** — IMPACT: MEDIUM (future). Zero usage. Sign-in for sync/premium; token persist via `OAuthToken.to_json`.
14. **DataChannel binary RPC** — IMPACT: LOW-MEDIUM. Zero usage. Bulk scrape payloads / image bytes without base64-in-JSON overhead.
15. **Wakelock / Battery.is_in_battery_save_mode / BrowserContextMenu / ScreenBrightness / ShakeDetector / sensors** — IMPACT: LOW (niche). Wakelock during long AI/scrape on mobile; battery-save → reduce prefetch; `BrowserContextMenu.disable()` for app-like web right-click; rest N/A for this app.

## 3. GOTCHAS

- **Services must be registered/persistent.** A transient `ft.UrlLauncher()` (or any `Service`) created and dropped has no client channel — DDGS already learned this (`app_controller.py` keeps `self.url_launcher`; `downloader.py` re-registers). Rule: construct once, assign to `page`/`page.services` or hold a strong ref; same for Clipboard/Share/FilePicker/HapticFeedback.
- **Everything service-side is `async` over the client bridge.** `await page.run_task(coro)` from sync handlers; never block the event loop (downloads use `run_task` correctly). `control.update()`/`page.update()` batching required after mutation — missing `update()` = silent no-op UI.
- **Platform gates raise — check before calling.** `Clipboard.set_image` (mobile+web only), `set_files/get_files` (desktop/Android only), ALL `StoragePaths` (raise on web), `ScreenBrightness` (`before_update` raises off mobile), `FilePicker` needs Zenity on Linux desktop, `Tester.take_screenshot` mobile-only, `Window` desktop-only, sensors mobile-only, `BrowserContextMenu` web-only (no-op elsewhere).
- **Gesture-safe ClientActions vs methods.** On web/Safari, clipboard-write, `window.open`, `navigator.share` ONLY work inside the user gesture: prefer `CopyToClipboard/OpenUrl/ShareText/PickFiles` actions on buttons; the `await service.*` equivalents may be blocked as unsolicited popups. Trade-off: actions return no result.
- **Windows vs Android availability.** Window chrome APIs (titlebar, frameless, taskbar `progress_bar`, `.ico` icon) = desktop; HapticFeedback/ScreenBrightness/sensors/ShakeDetector/Wakelock = mobile; `Share.share_files` needs real paths (web needs bytes variant); `can_launch_url` returns False on web except http(s).
- **Auth token lifecycle.** `login()` → `request_token` → auto-refresh in `get_token()`; persist with `OAuthToken.to_json()` and restore via `dehydrate_token()` — DDGS premium/license flow could reuse this instead of custom storage.
- **PubSub is in-process fan-out, not persistent.** Messages don't survive restart; unsubscribe on dispose to avoid handler leaks across view rebuilds.
- **Canvas capture is async and stateful.** `await capture()` then `get_capture()`; `clear_capture()` to drop the backing bitmap (memory).

## 4. COVERAGE

- Slice total: **~132 files** (top-level 7 + auth 11 + canvas 1 + components 14 + messaging 7 + pubsub 3 + security 1 + testing 5 + utils 21 + fastapi 1 + controls/services 22 + controls/core/canvas 15 + controls top-level 12 + controls/core 7 + icons 2).
- Read fully: **~40 files** (all of `controls/services/` high-value: clipboard, haptic, share, url_launcher, file_picker, storage_paths, connectivity, shared_preferences, screen_brightness, wakelock, semantics, browser_context_menu; `window.py`, `canvas.py`, `animation.py`, `tester.py`, `finder.py`, `authorization_service.py`, `oauth_provider.py`, `oauth_token.py`, `app.py` (entry), `fastapi/__init__`, `canvas/__init__`, `material/icons.py`, plus targeted reads).
- Signature-scanned via grep (`class/def/__all__` + props/events): **all remaining ~92 files** — every public class, method, prop, event, and enum in the slice is reflected in §1.
- `messaging/flet_socket_server.py`, `flet_dart_bridge_server.py`, `pyodide_connection.py` (server internals, no public consumer API) — noted, not itemized.
- DDGS `src/` grep: full `ft.*` frequency survey + targeted greps for all 40+ candidate APIs; USED vs UNUSED claims above are grep-verified.
