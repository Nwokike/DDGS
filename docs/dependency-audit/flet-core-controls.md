# Flet 1.0.1 Core Controls — Dependency Audit for DDGS

- Package: `flet==1.0.1`, slice = `controls/` top-level (45 files) + `controls/core/` (38) + `controls/core/canvas/` (15) + `controls/services/` (22). EXCLUDES `material/` and `cupertino/` (covered by other agents).
- Public surface: `flet/__init__.py` is lazy (PEP 562) — `import flet` is cheap; the `if TYPE_CHECKING:` block (~1800 lines) is the canonical export list (535 names).
- DDGS usage verified by grepping `src/` for `ft.<Name>` and bare control names.

---

## 1. COMPLETE API INVENTORY (one compact line per control, grouped by module)

### 1a. Base classes (`controls/*.py`)

- `BaseControl` (`base_control.py`) — root of everything: `key`, `ref`, `data`, lifecycle hooks `init/build/before_update/did_mount/will_unmount`, `before_event(e)` (return False cancels), `update()`, `_invoke_method()` async bridge, sparse dirty-tracking (`_values/_dirty`), `@control("DartName")` decorator wires Dart widget name + `isolated` flag; generator/async-generator event handlers supported, `yield` = intermediate UI flush.
- `Control` (`control.py`) — adds `expand/expand_loose` (only inside Column/Row/View/Page), `col` (ResponsiveRow spans; `0` hides), `opacity` 0–1, `tooltip` (str or Tooltip), `badge`, `visible` (False = fully unmounted, no focus/events), `disabled` (propagates recursively to children), `rtl`.
- `LayoutControl` (`layout_control.py`) — adds `width/height/left/top/right/bottom` (position props only work in Stack/Page.overlay), `align/margin`, transforms `rotate/scale/offset/flip/transform/aspect_ratio`, 8× `animate_*` implicit animations (opacity/size/position/align/margin/rotation/scale/offset, each `bool|int|Animation`), `on_size_change` (throttled by `size_change_interval`, default 10 ms, 0 = every change) with `LayoutSizeChangeEvent(w,h)`, `on_animation_end` (event `data` = animation name, for chaining).
- `ScrollableControl` (`scrollable_control.py`) — mixin for Column/Row/ResponsiveRow/View/ListView/GridView: `scroll` (`ScrollMode` or `Scrollbar`), `auto_scroll` (pins to end incl. in-place growth, suspends while user scrolled away), `auto_scroll_animation` (default 1 s ease; `0` = instant, best for token streaming), `on_scroll` throttled by `scroll_interval` (10 ms) with rich `OnScrollEvent` (type START/UPDATE/END/USER/OVERSCROLL, pixels/min/max/viewport, scroll_delta, direction, overscroll, velocity + helpers `out_of_range/at_edge/extent_before/extent_after/extent_total`), `await scroll_to(offset|delta|scroll_key, duration, curve)` — REQUIRES `auto_scroll=False`, ineffective for on-demand ListView/GridView; `Scrollbar(thumb_visibility/track_visibility/thickness/radius/interactive/orientation)`; `ScrollMode` = AUTO/ADAPTIVE/ALWAYS/HIDDEN.
- `ActionControl` (`action_control.py`) — adds `action: ClientAction | list[ClientAction]` (declarative client intents; base of TextSpan).
- `AdaptiveControl` (`adaptive_control.py`) — adds `adaptive: bool|None` (auto Cupertino variant).
- `DialogControl` (`dialog_control.py`) — adds `open: bool`, `on_dismiss`; shown via `page.show_dialog()/pop_dialog()`.
- `Animation`/`AnimationStyle`/`AnimationCurve` (`animation.py`) — `Animation(duration_ms, curve)`; ~40 curves (ease*, bounce*, elastic*, back*, expo/circ/cubic/quad/quart/quint/sine, fastLinearToSlowEaseIn…); `AnimationStyle(duration, reverse_duration, curve, reverse_curve)`, `no_animation()`, `.copy()`.
- `Event` (`control_event.py`) — all handlers receive `Event(control, name, data)`; `.page`, `.target`; handlers may be 0-arg or 1-arg, sync/async/generator.
- `Ref` (`ref.py`) — `Ref.current` handle to grab a control instance for imperative calls.
- `Key/ValueKey/ScrollKey` (`keys.py`) — `ScrollKey` targets `scroll_to(scroll_key=…)`; `ValueKey` preserves identity across rebuilds.
- `MultiView` (`multi_view.py`) — multi-window host (`view_id`, `initial_data`).

### 1b. Layout (`controls/core/`)

- `Column` — `controls, alignment (MainAxis), horizontal_alignment, spacing=10, tight, wrap, run_spacing, run_alignment, intrinsic_width`; scrollable + adaptive.
- `Row` — same mirrored (`vertical_alignment` default CENTER, `intrinsic_height`).
- `Stack` — absolute positioning for children (`left/top/right/bottom`), `clip_behavior`, `alignment`, `fit` (LOOSE/EXPAND/PASS_UP); basis for overlays/badges.
- `ResponsiveRow` — 12-virtual-column responsive grid, `columns`, `breakpoints` {xs<576…xxl≥1400}, children use `col={"sm":6}`; scrollable + adaptive.
- `ListView` — virtualized-ish list, `horizontal/reverse/spacing/item_extent/first_item_prototype/prototype_item/divider_thickness/padding/clip_behavior/semantic_child_count/cache_extent/build_controls_on_demand` (on-demand breaks `scroll_to`); DDGS chat uses `auto_scroll=True`.
- `GridView` — `runs_count/max_extent/spacing/run_spacing/child_aspect_ratio` + same virtualization flags as ListView.
- `View` — routable page (`route, appbar, navigation_bar, drawer/end_drawer, bottom_appbar, floating_action_button(+location), vertical/horizontal_alignment, spacing, padding=10, bgcolor/decoration/foreground_decoration, fullscreen_dialog, services, can_pop, on_confirm_pop`).
- `Pagelet` — mini-View embeddable anywhere (appbar/nav bar/FAB/drawers/bottom_sheet without a route).
- `PageView` — swipeable carousel/one-page-at-a-time, `selected_index, keep_page, horizontal/reverse, viewport_fraction (<1 = peeking), snap, implicit_scrolling, pad_ends, clip_behavior, on_change(index in data)`; methods `go_to_page(index,duration,curve)` / `jump_to_page` / `jump_to(pixels)` — onboarding carousel, media pager.
- `SafeArea` — pads past notches/status bars; `avoid_intrusions_{left,top,right,bottom}, maintain_bottom_view_padding` (prevents keyboard layout jumps), `minimum_padding`.
- `TransparentPointer` — passes all hit-tests through to controls below (overlay tap-through).
- `RotatedBox` — layout-level quarter-turns (`quarter_turns`, unlike paint-level `rotate`).
- `Placeholder` — dev fallback box (`fallback_height/width=400`, `stroke_width`), shows where content will go.
- `WindowDragArea` — frameless-window drag region (`maximizable, on_double_tap/on_drag_start/on_drag_end`), pairs with `Window.start_dragging()`.

### 1c. Basic content

- `Text` — `value|spans(TextSpan[]), text_align/font/size/weight/italic/style/theme_style/max_lines/overflow/no_wrap/color/bgcolor/semantics_label`, `selectable` + `show_selection_cursor/enable_interactive_selection/selection_cursor_*` (cursor props need selectable), `on_tap` + `on_selection_change(TextSelectionChangeEvent)` (BOTH need `selectable=True`); helpers `TextSelection(start/end/is_valid/…)`.
- `TextSpan` (ActionControl) — rich inline span: `text/style/spans/url (str|Url, opens browser)/semantics_label/spell_out/accessibility`, `on_click/on_enter(url hover)/on_exit` — hyperlinks + hoverable citations inside Text/Markdown-free runs.
- `Icon` — `icon/color/size/semantics_label/shadows/fill/apply_text_scaling/grade/weight/optical_size/blend_mode` (variable-font axes).
- `Image` — `src: str|bytes`, `fit/repeat/border_radius/color+color_blend_mode`, `error_content` (DDGS already uses), `placeholder_src (+placeholder_fit, NO svg)`, `fade_in_animation/placeholder_fade_out_animation`, `cache_width/cache_height` (decode-size perf), `filter_quality, anti_alias, gapless_playback` (no flash on src change), `semantics_label/exclude_from_semantics`.
- `RawImage` — streams raw RGBA frames over a DataChannel (camera/canvas-like perf path; needs numpy/PIL helpers in file).
- `Markdown` — `value/selectable/extension_set (GITHUB_WEB/COMMON_MARK/GITHUB_FLAVORED)/code_theme (+MarkdownCustomCodeTheme)/md_style_sheet+code_style_sheet (per-element TextStyles)/shrink_wrap/fit_content/soft_line_break/latex_scale_factor+latex_style`, `auto_follow_links(+target)/image_error_content`, `on_tap_text/on_selection_change/on_tap_link` (DDGS uses on_tap_link in reader only).
- `ShaderMask` — GPU shader blend over content (`shader: Linear|Radial|SweepGradient, blend_mode, border_radius`) — fades, scrims, shimmer-adjacent effects.
- `Shimmer` — animated skeleton loader: `content + (gradient OR base_color+highlight_color [required]), period=1500ms, direction LTR/RTL/TTB/BTT, loop (0=infinite)`.
- `Canvas` (+14 shapes: Arc/Circle/Oval/Rect/Line/Points/Path/Fill/Color/Shadow/Text/Image) — vector drawing surface, `shapes/content/resize_interval/on_resize(CanvasResizeEvent w/h)`.

### 1d. Interaction / gestures / focus

- `GestureDetector` — 60+ handlers: tap family (tap/down/up/move/cancel, multi_tap, double_tap, secondary/tertiary), long-press family (down/cancel/press/start/move_update/up/end + secondary/tertiary), drag (horizontal/vertical/pan/right-pan down/start/update/end/cancel), scale (start/update/end), force-press (desktop trackpad), `on_hover/on_enter/on_exit` (+`HoverEvent`), `on_scroll`, `mouse_cursor`, throttles `drag_interval/hover_interval` (default 0 = unthrottled), `multi_tap_touches`, `trackpad_scroll_causes_scale`, `allowed_devices`, `exclude_from_semantics` — invisible hit-area/hover wrapper for ANY control.
- `KeyboardListener` — `content/autofocus/include_semantics`, `on_key_down/on_key_up/on_key_repeat(Key{Down,Up,Repeat}Event.key)` + `await focus()` — in-app shortcuts; page-level alternative `Page.on_keyboard_event(KeyboardEvent key/shift/ctrl/alt/meta)`.
- `Dismissible` — swipe-to-dismiss row: `content/background/secondary_background` (secondary REQUIRES background), `dismiss_direction`, per-direction `dismiss_thresholds{0–1}`, `movement_duration=200ms/resize_duration=300ms/cross_axis_end_offset`, `on_update(DismissibleUpdateEvent direction/progress/reached/previous_reached)`, `on_dismiss`, `on_confirm_dismiss` + `await confirm_dismiss(bool)` veto flow, `on_resize`.
- `Draggable` — `content/content_when_dragging/content_feedback/group/axis/affinity/max_simultaneous_drags/on_drag_start/on_drag_complete`; `DragTarget` — `content/group/on_will_accept(DragWillAcceptEvent)/on_accept/on_leave/on_move` — same-group drag-and-drop.
- `InteractiveViewer` — pan/zoom/rotate viewport: `pan_enabled/scale_enabled/trackpad_scroll_causes_scale/constrained (False = content can exceed viewport)/min_scale=0.8/max_scale=2.5 (min clamped by boundary_margin — default Margin.all(0) blocks zoom-out below ~1.0)/scale_factor/interaction_end_friction_coefficient/clip_behavior/alignment/boundary_margin/interaction_update_interval=200ms/on_interaction_start/update/end` + methods `reset(animation_duration)/save_state/restore_state/zoom(factor)/pan(dx,dy,dz)`.
- `Hero` — shared-element transition (`tag/content/transition_on_user_gestures`) across route changes.
- `AnimatedSwitcher` — crossfade/rotate/scale content swaps (`content/duration=1s/reverse_duration/switch_in_curve/switch_out_curve/transition FADE|ROTATION|SCALE`).
- `AutofillGroup` — autofill scoping (`content/dispose_action COMMIT|HIDE`; 700-line `AutofillHint` enum: email/password/one-time-code/…).
- `ReorderableDragHandle` — drag handle for material ReorderableListView (`content/mouse_cursor`).
- `Screenshot` — `await capture(pixel_ratio, delay) -> PNG bytes` of wrapped control (share/export snapshots).
- `Semantics` — full a11y annotation: `label/hint_text/value/increased/decreased_value/checked/toggled/selected/expanded/button/slider/textfield/link/header/image/obscured/read_only/focusable/focus/multiline/max_value_length/current_value_length/heading_level/live_region/container/exclude_semantics/mixed` + a11y actions (`on_tap/on_double_tap/on_increase/on_decrease/on_dismiss/on_scroll_*/on_copy/on_cut/on_paste/on_long_press/on_move_cursor_*/on_did_gain/lose_accessibility_focus/on_set_text/on_*_hint_text`); `MergeSemantics(content)` merges subtree; `SemanticsService.announce_message(msg, rtl, assertiveness)/announce_tooltip/get_accessibility_features()` (accessible_navigation/bold_text/disable_animations/high_contrast/invert_colors/reduce_motion…).
- `FletApp` — embeds a second Flet app/webview (`url/args/assets_dir/force_pyodide/reconnect_*ms/boot_screen_*/app_error_message/on_error/on_connect/on_python_output`).
- `Window` (desktop) — `bgcolor/size/pos/min/max/aspect_ratio/opacity/brightness/maximized/minimized/minimizable/maximizable/resizable/movable/full_screen/always_on_top/on_event(WindowEventType…)` + `wait_until_ready_to_show/center/close/destroy/to_front/start_dragging/start_resizing(edge)`; frameless chrome via `WindowDragArea`.

### 1e. Types / styling values

- `types.py` — `MainAxisAlignment/CrossAxisAlignment/VerticalAlignment/TextAlign/TextOverflow(CLIP|ELLIPSIS|FADE|VISIBLE)/FontWeight(W100–W900 + NORMAL/BOLD)/MouseCursor (BASIC/CLICK/TEXT/WAIT/…)/PointerDeviceType/ClipBehavior(NONE…HARD_EDGE)/BlendMode/ScrollMode/ThemeMode/Brightness/PagePlatform/AppLifecycleState/Orientation/DeviceOrientation/FloatingActionButtonLocation/VisualDensity/Url(url,target BLANK|SELF|PARENT|TOP)/Locale/LocaleConfiguration/ResponsiveRowBreakpoint/StrokeCap/StrokeJoin`.
- `alignment.py` — `Alignment(x,y -1..1) + presets (TOP_LEFT…BOTTOM_RIGHT, CENTER), Axis`.
- `transform.py` — `Rotate(angle_radians, alignment)/Scale(scale_x/scale_y)/Offset(x,y fraction of size)/Flip(horizontal/vertical)/Matrix4/Transform`.
- `border.py` — `Border(all/symmetric/only, BorderSide(color,width,stroke_align INSIDE|CENTER|OUTSIDE)), BorderStyle(SOLID|NONE)`.
- `border_radius.py` — `BorderRadius(all/horizontal/vertical/only, elliptical option)`.
- `box.py` — `BoxDecoration(color/gradient/image/shadows/border/border_radius/shape RECT|CIRCLE/background_blur…), BoxShadow, BoxFit(NONE|CONTAIN|COVER|FILL|FIT_HEIGHT|FIT_WIDTH|SCALE_DOWN), BoxConstraints, DecorationImage, FilterQuality, ColorFilter, BlurStyle`.
- `blur.py` — `Blur(sigma_x/sigma_y, tile_mode CLAMP|DECAL|MIRROR|REPEATED)`.
- `gradients.py` — `LinearGradient/RadialGradient/SweepGradient(begin/end/colors/stops/tile_mode/rotation…)`.
- `painting.py` — `Paint(color/blend/shader/…), PaintLinear/Radial/SweepGradient, PaintingStyle(FILL|STROKE)` (Canvas/Semantics-adjacent low level).
- `buttons.py` — `ButtonStyle(color/bgcolor/overlay/shadow/elevation/animation_duration/padding/side/shape/alignment/enable_feedback/text_style/icon_size/icon_color/visual_density/mouse_cursor — all ControlState-aware)` + shapes `Stadium/Circle(eccentricity)/RoundedRectangle(radius)/Beveled/ContinuousRectangle`.
- `text_style.py` — `TextStyle(size/weight/italic/decoration+style/color/bgcolor/shadow/letter/word/line-height/font_family…), StrutStyle, TextThemeStyle (DISPLAY_*/HEADLINE_*/TITLE_*/LABEL_*/BODY_*)`.
- `padding.py`/`margin.py` — `Padding/Margin(all/symmetric/only, l/t/r/b)`.
- `geometry.py` — `Size(w,h), Rect`.
- `duration.py` — `Duration(days/hours/minutes/seconds/milliseconds/microseconds), DateTimeValue`.
- `control_state.py` — `ControlState (HOVERED/FOCUSED/PRESSED/DRAGGED/SELECTED/…)` for state-dependent styling.
- `theme.py` — full `Theme/ColorScheme/TextTheme/*Theme` system (3600 lines; theming agent's area, listed for completeness).
- `device_info.py` — `get_device_info()` → Android/iOS/Linux/Mac/Windows/Web structs.
- `client_action.py` — `ClientAction` base (declarative client intents behind `ActionControl.action`).
- `context.py` — `context` object: `page`, auto-update toggling, components mode.
- `template_route.py`/`query_string.py` — `TemplateRoute` pattern routing, `page.query` parsing.

### 1f. Services (`controls/services/` — page.services or direct construct)

- `Clipboard` — `await set/get (text), set_image/get_image (bytes, desktop), set_files/get_files (paths)`; `CopyToClipboard` client action (one-shot copy without service).
- `Share` — `await share_text(text, subject?, …)/share_uri(uri)` + `ShareFile.from_path/from_bytes` (native sheet; DDGS uses ShareText action in 1 place only).
- `UrlLauncher` — `launch_url` (DDGS uses for downloads/auth).
- `FilePicker` — open/save/pick with upload events (`PickFiles` action).
- `SharedPreferences` — `set/get/contains_key/remove/get_keys(clear)` (DDGS uses).
- `HapticFeedback` — `heavy/medium/light_impact, vibrate, selection_click` (mobile feel).
- `BrowserContextMenu` — `await enable()/disable()` (web right-click on/off — pair with custom menus).
- `Connectivity` — `ConnectivityType (WIFI/MOBILE/NONE…)` + change events (DDGS already reads type).
- `SemanticsService` — screen-reader announcements + accessibility flags (see 1d).
- `StoragePaths` — platform dirs; `Wakelock` — keep screen on (reading/video); `ScreenBrightness` — get/set + change events; sensors `Accelerometer/Gyroscope/Magnetometer/UserAccelerometer/Barometer/Battery` + `ShakeDetector` (shake-to-…); `Url`-adjacent `OpenUrl` action.
- `Service` base — custom services via `@control` + `register_service`, `on_data_channel_open` for binary streams (RawImage pattern).

### 1g. Page shell (`base_page.py` / `page.py` — operator-relevant)

- `page.views` (routing stack) + `route/on_route_change/on_view_pop/can_pop/on_confirm_pop`, `push_route/navigate/pop_views_until`, `page.query/url`.
- `page.overlay` (floating layer for menus/toasts), `show_dialog/pop_dialog`, `show_drawer/close_drawer(+end)`.
- `page.update(*controls)` targeted updates; `run_task (async)/run_thread (sync off-UI-thread)`; `on_keyboard_event`; `on_connect/on_disconnect`; `login/logout/auth/session/pubsub`; `get_device_info/set_allowed_device_orientations`; `show_semantics_debugger`.

---

## 2. WHAT DDGS DOESN'T USE (ranked by UX impact; all verified zero-hit in `src/`)

DDGS already uses well: Column/Row/Stack/ListView(auto_scroll chat)/View/SafeArea/GestureDetector(4×)/Markdown/Image(error_content)/Text(selectable)/tooltip/ft.Animation/SearchBar/Clipboard/UrlLauncher/FilePicker/SharedPreferences/ShareText(1×)/ScrollMode.AUTO.

1. **`Dismissible` — swipe-to-delete history + swipe actions on rows.** history_screen has no swipe UX; `dismiss_direction`, per-direction `background` (red delete) / `secondary_background` (archive), `on_confirm_dismiss` + `confirm_dismiss(bool)` gives undo-snackbar flow; `on_update(progress/reached)` drives haptic/opacity feedback. Highest-impact mobile UX gap.
2. **`InteractiveViewer` — pinch-zoom image results.** cards_media/detail_sheet show images with only `error_content`; wrap in InteractiveViewer (`max_scale=2.5`, `boundary_margin` to allow zoom-out, `reset()/zoom()/pan()`, `constrained=False` for oversized) for gallery-grade zoom. Zero usage today.
3. **`Shimmer` — skeleton loaders for results/chat/AI streaming.** Replaces spinners with `base_color+highlight_color` (or gradient) pulsing placeholders over result-card shapes; `period/direction/loop`. No loading-state polish control in use.
4. **`KeyboardListener` (+ `Page.on_keyboard_event`) — desktop shortcuts.** No keyboard UX despite desktop target: Ctrl+K focus search, Esc closes sheets, arrows navigate results, Enter opens. `autofocus` + `await focus()`; page-level `KeyboardEvent(key/shift/ctrl/alt/meta)` for globals; pairs with `TextField.autofocus` (home only).
5. **`Semantics`/`MergeSemantics`/`SemanticsService` — accessibility.** Zero annotations: icon-only buttons (chat/home) lack `label/hint_text`, streaming answers never announced (`announce_message`), no `heading_level/live_region` on results; check `get_accessibility_features().reduce_motion` to gate animations. (tooltip= is used widely but is not a screen-reader substitute.)
6. **`AnimatedSwitcher` — content transitions.** Screen/empty-state/step-row swaps snap; FADE/SCALE/ROTATION with `duration/switch_in/out_curve` animates chat step rows, AI-overview reveal, empty→results.
7. **`scroll_to` + `ScrollKey` + `on_scroll` — programmatic scroll.** Chat/results never jump: no back-to-top FAB (`on_scroll` USER/UPDATE + `extent_before`), no scroll-to-citation (`scroll_to(scroll_key=…)`), no infinite-scroll trigger (`at_edge/extent_after`). Note: needs `auto_scroll=False` where used; chat's pin-suspend comment shows the team already fought this API.
8. **`TextSpan.url/on_click/on_enter` + `SelectionArea` (material) — rich chat citations.** Citations are plain text; TextSpan gives inline hyperlinks with hover (`on_enter/on_exit`) inside selectable Text; SelectionArea wraps whole answer blocks for one-gesture copy. Markdown `on_tap_text/on_selection_change` also unused.
9. **`Draggable`/`DragTarget` — drag results into download queue / reorder.** Detail_sheet/downloader flow is tap-only; same-`group` DnD with `content_feedback` ghost + `on_accept` drop target on queue/FAB. Desktop-heavy win.
10. **`Hero` — shared-element image transitions.** Results grid → detail_sheet image jumps; matching `tag` animates the thumbnail into the sheet.
11. **`PageView` — onboarding carousel + media pager.** Onboarding uses DragEndEvent manually; PageView gives `viewport_fraction` peeking, `snap`, `go_to_page/jump_to_page`, `on_change`.
12. **`ResponsiveRow` — adaptive mobile/desktop grids.** Results/settings use fixed Column/Row; `col={"sm":6,"lg":4}` breakpoints collapse gracefully; `col=0` hides per-breakpoint.
13. **`GridView` virtualization flags.** If image grids grow: `build_controls_on_demand/max_extent/child_aspect_ratio/cache_extent/semantic_child_count` (same for ListView: `item_extent/divider_thickness/build_controls_on_demand`).
14. **`HapticFeedback` + `Wakelock` + `ScreenBrightness`.** No tactile feedback on mobile actions (`selection_click` on chip toggles, `medium_impact` on swipe-delete); Wakelock for content_reader long reads.
15. **`Screenshot.capture()` — share result cards as PNG.** detail_sheet shares text only; wrap card → PNG bytes → `ShareFile.from_bytes` / `Clipboard.set_image`.
16. **`Clipboard.set_image/get_image/set_files` + `Share.share_uri/ShareFile`.** Only text copy/share used; image results can't be copied/shared as files.
17. **`BrowserContextMenu.disable()` (web).** Custom right-click menus need the native one suppressed; unused.
18. **`Image` perf props.** Only `error_content` used: add `placeholder_src` (+fade in/out), `cache_width/cache_height`, `filter_quality`, `gapless_playback` (no flash on src swap in carousels).
19. **`on_hover/on_enter/on_exit/mouse_cursor` (GestureDetector/Container-level).** Desktop rows/cards have no hover affordance; `mouse_cursor=CLICK` + hover tint is a cheap desktop win. `drag/hover_interval` throttle if handlers get hot.
20. **`on_size_change/size_change_interval` + `on_animation_end`.** No layout-aware logic (e.g. collapsing app bar, chaining animations).
21. **`Canvas` shapes + `ShaderMask`.** No custom drawing: gradient fade-outs on long text (`ShaderMask` + LinearGradient), waveform/progress art (`Canvas`), image scrims for readability.
22. **`Pagelet` / `TransparentPointer` / `RotatedBox`.** Embedded mini-scaffold for sheets; tap-through overlays; cheap rotated badges (“NEW”, watermarks).
23. **`AutofillGroup` + `AutofillHint`.** Login/settings forms miss OS autofill (email/password/one-time-code).
24. **`FletApp` / `RawImage` / `Window` APIs.** Niche: embedded sub-apps, raw frame streaming, desktop window chrome (`center/to_front/start_dragging`, frameless + `WindowDragArea`).

Explicitly NOT in Flet 1.0.1 (do not port from Flutter/0.x tutorials): `RefreshIndicator`/`PullToRefresh`, `MouseRegion`, `Listener`, `AnimatedContainer/AnimatedOpacity` — verified absent; emulate pull-to-refresh with `OnScrollEvent` OVERSCROLL + `overscroll/velocity`, hover with `GestureDetector.on_hover`, implicit animation with `animate_*` props.

---

## 3. GOTCHAS — Flet 1.0 vs 0.x + runtime rules

- **Lazy exports:** `flet/__init__.py` uses PEP 562; `from flet import X` still works, but static analysis of the file shows only `__version__` eager. No behavior change, just faster import.
- **`update()` rules:** control must be mounted (`page` set) and not frozen, else `RuntimeError`. Prefer targeted `page.update(ctrl)` / `ctrl.update()` over full-page updates; chat_screen already does per-row updates for streaming — keep it.
- **Streaming pattern (1.0 power feature):** event handlers may be generators — `yield` flushes an intermediate UI patch. Prefer this over manual `update()` loops in long handlers (also `page.run_task` for async background work, `run_thread` for sync).
- **`auto_scroll` vs `scroll_to` are mutually exclusive:** `scroll_to` requires `auto_scroll=False`; on-demand ListView/GridView ignore `scroll_to` entirely. Chat's comment about the removed hand-rolled pin detector confirms 1.0.1 lacks scroll-position getters — use `on_scroll` event math instead.
- **Throttles everywhere:** `scroll_interval` (10 ms), `size_change_interval` (10 ms), `resize_interval` (Canvas, 10 ms), `interaction_update_interval` (200 ms), `drag_interval/hover_interval` (GestureDetector, default 0 = unthrottled — set if janky).
- **`before_update()` must never call `update()`** (infinite loop); `before_event` returning `False` cancels dispatch.
- **`visible=False` ≠ `opacity=0`:** invisible controls are removed from tree — no focus, no events, no semantics. Use opacity/offstage-style for hidden-but-live.
- **`disabled` cascades** to all descendants — disabling a Column disables its TextFields (useful for forms-wide locks).
- **SafeArea + keyboard:** set `maintain_bottom_view_padding=True` where the keyboard overlays flexible layouts, else rows jump; `minimum_padding` guarantees breathing room on notch-less devices.
- **GestureDetector has no `on_click`** — it's `on_tap`; secondary (right-click) needs `on_secondary_tap`, and web needs `BrowserContextMenu.disable()` for custom menus.
- **`Text.on_tap/on_selection_change` require `selectable=True`** (silent no-op otherwise); `selection_cursor_*` likewise.
- **`Dismissible.secondary_background` requires `background`** (ValueError in `before_update`); `Shimmer` requires `gradient` OR both colors.
- **`InteractiveViewer` zoom-out trap:** default `boundary_margin=Margin.all(0)` prevents effective `min_scale < 1` — widen margins to allow zoom-out.
- **`Image.placeholder_src` doesn't support SVG**; remote `src` accepts `bytes` too (share pipeline can skip disk).
- **Dialogs:** `DialogControl.open` + `page.show_dialog/pop_dialog` (dialogs live in `page._dialogs`, not the view tree — don't `add()` them).
- **Keys matter on rebuild:** lists rebuilt per keystroke (chat steps) should carry `ValueKey`/`ScrollKey` or state/focus jumps; `col=0` responsive-hide keeps state, `visible=False` drops it.
- **Desktop-only APIs guard:** `Window.*`, `Clipboard.set_image/get_files`, `ScreenBrightness.set` throw/unsupported on web-mobile — gate by `page.platform`.
- **`expand` only works** inside Column/Row/View/Page; silently ignored elsewhere (common “why won't it fill” bug).

---

## 4. COVERAGE

- **120 / 120 files inventoried** in-slice: `controls/*.py` 45/45, `controls/core/*.py` 38/38, `controls/core/canvas/*.py` 15/15, `controls/services/*.py` 22/22, plus `flet/__init__.py` export surface (535 names).
- Method: full reads of `base_control/control/layout_control/scrollable_control/animation/control_event/action/adaptive/dialog` + `dismissible/interactive_viewer/animated_switcher/draggable/keyboard_listener/shimmer/semantics/page_view/safe_area/screenshot`; dataclass-field introspection dump (1912 lines) covering every control's full prop list; class/field skims for types/border/box/gradients/transform/text_style/buttons/services/canvas/page.
- DDGS usage: `grep ft.\w+` + bare-name sweep over all of `src/` (counts captured in §2 intro).
