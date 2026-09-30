# Flet 1.0.1 — Cupertino Controls Dependency Audit (for DDGS)

> Scope: `C:\Users\nwoki\.zcode\workspace\default\DDGS\.venv\Lib\site-packages\flet\controls\cupertino\`
> Consumer: DDGS (`C:\Users\nwoki\.zcode\workspace\default\DDGS\src\`) — Windows + Android.
> DDGS status: **zero direct `ft.Cupertino*` references** (verified by grep over `src/`).
> It uses Material equivalents: `NavigationBar`, `AppBar`, `BottomSheet`, `AlertDialog`,
> `TextField`, `Switch`, `Slider`, plus custom `adaptive_glass_*` theme helpers.

---

## 1. COMPLETE API INVENTORY

Every control is exported at top level (`ft.Cupertino*`). One line each: key props / events / methods.

| # | Control | One-line API |
|---|---------|--------------|
| 1 | `CupertinoActionSheet` | `title`, `message`, `actions: list[CupertinoActionSheetAction]`, `cancel` — must set ≥1 (validated); shown via `page.show_dialog(ft.CupertinoBottomSheet(sheet))` |
| 2 | `CupertinoActionSheetAction` | `content` (str/control), `default`, `destructive`, `mouse_cursor`, `on_click` |
| 3 | `CupertinoActivityIndicator` | `radius=10`, `color`, `animating=True`, `progress 0..1` (determinate; designed for pull-to-refresh tick-by-tick) |
| 4 | `CupertinoAlertDialog` | `modal`, `title`, `content`, `actions: list[CupertinoDialogAction]`, `barrier_color`, `inset_animation`; ≥1 of title/content/actions required |
| 5 | `CupertinoAppBar` | `leading/title/trailing`, `bgcolor`, `large` (left-aligned large title vs centered), `automatically_imply_leading/title`, `previous_page_title`, `transition_between_routes` (hero-style iOS route animation), `brightness`, `automatic_background_visibility`, `enable_background_filter_blur`, `border`, `padding` |
| 6 | `CupertinoBottomSheet` | `content` (required), `modal`, `bgcolor`, `height`, `padding`; a `DialogControl` — open with `page.show_dialog(...)` |
| 7 | `CupertinoButton` (+`CupertinoButtonSize` SMALL/MEDIUM/LARGE) | `content`, `icon`, `icon_color`, `bgcolor/color/disabled_bgcolor`, `opacity_on_click=0.4`, `min_size`, `size`, `padding`, `alignment`, `border_radius=8`, `url`, `autofocus`, `focus_color`, `mouse_cursor`; events `on_click/on_long_press/on_focus/on_blur`; method `await focus()` |
| 8 | `CupertinoCheckbox` | macOS-style; `label`, `label_position`, `spacing`, `value` (bool, None if `tristate`), `tristate`, `autofocus`, `check_color`, `active_color=ACTIVE_BLUE`, `focus_color`, `fill_color` + `border_side` (per-`ControlState`), `shape`, `mouse_cursor`, `semantics_label`; events `on_change/on_focus/on_blur` |
| 9 | `CupertinoColors` | 47 named iOS colors (`ACTIVE_BLUE`, `SYSTEM_RED`, `LABEL`, `SYSTEM_BACKGROUND`, `SEPARATOR`, …); helpers `with_opacity(opacity, color)`, `random(exclude, weights)`; values are camelCase strings (`"activeBlue"`) |
| 10 | `CupertinoContextMenu` (**adaptive**) | Full-screen modal on long-press: `content` (moved/expanded into new route), `actions` (≥1 visible, typically `CupertinoContextMenuAction`), `enable_haptic_feedback=True`; extends `AdaptiveControl` |
| 11 | `CupertinoContextMenuAction` (**adaptive**) | `content`, `default`, `destructive`, `trailing_icon`, `on_click`; extends `AdaptiveControl` |
| 12 | `CupertinoDatePicker` (+`CupertinoDatePickerMode` TIME/DATE/DATE_AND_TIME/MONTH_YEAR, +`CupertinoDatePickerDateOrder` dmy/mdy/ymd/ydm) | `value` (default now), `first_date/last_date`, `bgcolor`, `minute_interval` (must divide 60), `minimum_year/maximum_year`, `item_extent=32`, `use_24h_format`, `show_day_of_week` (DATE mode only), `date_picker_mode`, `date_order`, `locale`; event `on_change` (skipped when out of range — picker snaps back) |
| 13 | `CupertinoDialogAction` | For `CupertinoAlertDialog.actions`: `content`, `default` (bold), `destructive` (red), `text_style`, `on_click` |
| 14 | `CupertinoFilledButton` | Subclass of `CupertinoButton`; filled with default background color; no new props |
| 15 | `CupertinoIcons` | Generated iOS icon font proxy (`cupertino_icons.json`-backed, `IconData` values); use as `icon=` anywhere an `IconData` fits |
| 16 | `CupertinoListTile` | iOS `ListTile`: `title` (required), `subtitle`, `leading/trailing` (icon-or-control), `additional_info` (right side, before trailing), `bgcolor`, `bgcolor_activated`, `padding`, `leading_size`, `leading_to_title`, `notched` (Inset-Grouped iOS Notes/Reminders look), `toggle_inputs`, `url`, `on_click` |
| 17 | `CupertinoNavigationBar` | iOS bottom tab bar: `destinations: list[NavigationBarDestination]` (≥2 visible, shared type with Material bar), `selected_index`, `bgcolor`, `active_color`, `inactive_color=INACTIVE_GRAY`, `border`, `icon_size=30`; event `on_change` |
| 18 | `CupertinoPicker` | Generic iOS wheel: `controls` (items), `selected_index`, `item_extent=32`, `bgcolor`, `use_magnifier`, `magnification`, `looping`, `squeeze=1.45`, `diameter_ratio=1.07`, `off_axis_fraction`, `selection_overlay` + `default_selection_overlay_bgcolor`; event `on_change` |
| 19 | `CupertinoRadio` | macOS-style; use inside `RadioGroup`: `label`, `value` (string key), `label_position`, `fill_color`, `active_color=PRIMARY`, `inactive_color`, `autofocus`, `use_checkmark_style`, `toggleable`, `focus_color`, `mouse_cursor`; events `on_focus/on_blur` (change comes from `RadioGroup`) |
| 20 | `CupertinoSegmentedButton` | Bordered iOS segments: `controls` (≥2 visible), `selected_index`, `selected_color/unselected_color/border_color/padding`, `click_color`, `disabled_color/disabled_text_color`; event `on_change` |
| 21 | `CupertinoSlider` | iOS slider: `value/min=0/max=1` (validated; `value` defaults to `min`), `divisions` (None = continuous), `active_color`, `thumb_color`; events `on_change/on_change_start/on_change_end/on_focus/on_blur` |
| 22 | `CupertinoSlidingSegmentedButton` | Modern pill with sliding thumb: `controls` (≥2), `selected_index`, `bgcolor=TERTIARY_SYSTEM_FILL`, `thumb_color`, `padding` (default symmetric v2/h3), `proportional_width` (equal vs content-sized segments); event `on_change` |
| 23 | `CupertinoSwitch` | iOS switch: `label`, `value`, `label_position`, `thumb_color`, `active_track_color`, `inactive_thumb_color/inactive_track_color`, `active/inactive_thumb_image_src` (+`on_image_error`), `on/off_label_color`, `track_outline_color/width` + `thumb_icon` (per-`ControlState`), `autofocus`, `focus_color`; events `on_change/on_focus/on_blur` |
| 24 | `CupertinoTextField` | Subclass of Material `TextField` (inherits all validation/keyboard props) + iOS extras: `placeholder_text/placeholder_style`, `gradient`, `blend_mode`, `shadows`, `image`, `padding=all(7)`, `prefix/suffix_visibility_mode` + `clear_button_visibility_mode` (`OverlayVisibilityMode` NEVER/EDITING/NOT_EDITING/ALWAYS), `clear_button_semantics_label`; `border` accepts per-state `InputBorder`, `NoInputBorder` removes it |
| 25 | `CupertinoTimerPicker` (+`CupertinoTimerPickerMode` hm/hms/ms) | Countdown 0–24h: `value` (`Duration` or int seconds), `mode=HOUR_MINUTE_SECONDS`, `minute_interval/second_interval` (must divide 60), `alignment`, `bgcolor`, `item_extent=32`; event `on_change` (`event.data` matches `value` type) |
| 26 | `CupertinoTintedButton` | Subclass of `CupertinoButton`; tinted-fill style; no new props |

**Adaptive constructs present:** `CupertinoContextMenu` + `CupertinoContextMenuAction`
extend `AdaptiveControl` (have the `adaptive` flag); Material `Switch(adaptive=True)`
auto-renders `CupertinoSwitch` on iOS/macOS. Everything else is fixed-look Cupertino.
**Absent from Flet 1.0.1** (no port): `CupertinoSliverAppBar` (named only in a docstring),
`CupertinoTabBar/TabScaffold/TabView`, page-sheet route, `RefreshControl`
(use `CupertinoActivityIndicator.progress` pattern instead), toolbar, search-text-field
(`CupertinoTextField(placeholder_text=…)` covers it).

---

## 2. LATENT CAPABILITIES FOR DDGS (ranked by UX impact)

Current state: DDGS uses **none** of the 26 — all latent. Ranking assumes Android build
gets iOS-look pieces only where gated by `page.platform`, desktop keeps Material.

### Android experience (gate on `page.platform == PagePlatform.ANDROID`)

1. **`CupertinoActionSheet` + `CupertinoBottomSheet` — share/export & result long-press
   actions.** `detail_sheet.py`, `downloader.py`, `content_fetcher.py` currently use
   Material `BottomSheet`/`AlertDialog`. An action sheet with `destructive=True` on
   Delete and `default` on the primary choice is the KTV-Player-grade pattern for
   per-result actions (Open / Share / Download / Copy link / Delete history item).
   DDGS already branches on `page.platform` (`update_dialog.py:131`), so reuse that gate.
2. **`CupertinoContextMenu` + `CupertinoContextMenuAction` — long-press result cards.**
   Purpose-built for exactly what `cards.py` / `cards_media.py` need: long-press a card,
   it expands into a modal with actions + haptic feedback (`enable_haptic_feedback`).
   These two are `AdaptiveControl`s, so lowest platform risk of the set.
3. **`CupertinoSlidingSegmentedButton` — result-type switcher.** `results_screen.py` /
   filter UI can replace chips/tabs with a sliding pill (Text/Image/Video/News).
   `proportional_width=True` handles uneven labels; lower friction than the bordered
   `CupertinoSegmentedButton` (also available, pick one — sliding is the modern iOS look).
4. **`CupertinoDatePicker` (DATE / MONTH_YEAR) — crawl-schedule / history-range UI.**
   No date input exists in DDGS today; history filtering or scheduled-refresh settings
   would get a native-feel wheel with `first_date/last_date` clamping built in
   (out-of-range selections snap back, `on_change` simply doesn't fire).
5. **`CupertinoNavigationBar` + `CupertinoAppBar(large=True)` — large-title polish.**
   `app_shell.py` uses Material `NavigationBar`; `results_screen.py` /
   `content_reader_screen.py` use Material `AppBar`. On Android builds, swapping to the
   Cupertino tab bar (≥2 `NavigationBarDestination`s — same type, trivial migration)
   and large-title app bar with `transition_between_routes` gives the KTV-Player-style
   scrolling header. Keep Material on Windows.
6. **`CupertinoActivityIndicator` — branded loading states.** Replaces generic spinners
   in `content_fetcher.py` / AI-overview loading; `progress` prop supports a
   pull-to-refresh tick pattern if a refresh gesture is added later.

### Desktop (Windows) polish — use sparingly, never wholesale

7. **`CupertinoSwitch` via `Switch(adaptive=True)`** — the *only* sanctioned adaptive
   path: set the flag on the existing Material `Switch`es (`sections_ai.py:71`,
   `sections_advanced.py:151`) and Windows keeps rendering Material while Apple targets
   get Cupertino. Zero-risk change.
8. **`CupertinoTextField`** — `chat_screen.py:195` input and settings fields
   (`sections_advanced.py:136`, `sections_premium.py:138`) could take the iOS style
   with `placeholder_text`, `clear_button_visibility_mode=EDITING`, prefix/suffix
   visibility modes. It's a `TextField` subclass, so migration is prop-compatible —
   but keep it Android-gated; Windows keeps Material fields.
9. **`CupertinoSlider`** — `sections_advanced.py:187` and `sections_general.py:130`
   sliders (quality picker, font-size) map 1:1 (`value/min/max/divisions`,
   `on_change_start/end` for debounced writes via `hooks/use_debounce.py`).
   Android-gate; the iOS thumb reads better at touch sizes.
10. **`CupertinoListTile(notched=True)`** — settings sections could use Inset-Grouped
    tiles; `additional_info` fits version/status rows (`sections_about.py`).
    Lower priority: cosmetic only.
11. **Buttons (`CupertinoButton/Filled/Tinted`, `CupertinoButtonSize`)** —
    `opacity_on_click=0.4` press fade and `on_long_press` are the only functional gains
    over Material buttons; adopt per-screen on Android, not globally.
12. **`CupertinoPicker` / `CupertinoTimerPicker` / `CupertinoCheckbox` /
    `CupertinoRadio` / `CupertinoAlertDialog` + `CupertinoDialogAction` /
    `CupertinoColors` / `CupertinoIcons`** — niche: generic wheel for fixed option sets,
    countdown for timed refresh, macOS-style toggles (off-brand on Android — prefer
    Switch), dialog only if committing to the iOS dialog aesthetic on Android,
    color/icon tokens usable anywhere as plain values (no platform risk).

---

## 3. GOTCHAS

- **Do NOT render fixed-look Cupertino on Windows.** Only `CupertinoContextMenu(_Action)`
  (extend `AdaptiveControl`) and `Switch(adaptive=True)` (renders `CupertinoSwitch` on
  iOS/macOS, Material elsewhere) adapt automatically. Everything else looks iOS on every
  OS — always gate with the existing `page.platform == ft.PagePlatform.ANDROID` pattern
  (`update_dialog.py:131`, `sections_about.py:56`, `styles.py:28`). DDGS sets no
  `adaptive=True` anywhere today.
- **Action sheets need a wrapper:** `page.show_dialog(ft.CupertinoBottomSheet(sheet))` —
  showing the `CupertinoActionSheet` directly does nothing. `CupertinoBottomSheet`
  (`content` required) and `CupertinoAlertDialog` are `DialogControl`s.
- **Validation raises, it doesn't clamp:** empty `CupertinoActionSheet`
  (no title/message/actions/cancel), `<2` segments/destinations, `ContextMenu` with no
  actions, `minute_interval` not dividing 60, `TimerPicker value ≥ 24h`,
  `Slider value` outside min/max, `show_day_of_week` outside DATE mode all raise
  `ValueError`/`IndexError` at update time.
- **`on_change` silence is by design:** `CupertinoDatePicker` out-of-range scrolls snap
  back without firing `on_change` — don't treat "no event" as a bug in schedule UIs.
- **`Slider.value=None` becomes `min`; `Switch` has no tri-state** (that's
  `CupertinoCheckbox(tristate=True)`); `CupertinoRadio.value` is a string key consumed
  by the parent `RadioGroup`, not a bool.
- **Subclass shortcuts:** `CupertinoFilledButton`/`CupertinoTintedButton` extend
  `CupertinoButton` (no new props — pick by style); `CupertinoTextField` extends Material
  `TextField` (all form props carry over; `border` takes per-`ControlState`
  `InputBorder`, `NoInputBorder` strips it).
- **Imports surface:** all 32 names (`Cupertino*`, `CupertinoColors`, `CupertinoIcons`,
  `CupertinoButtonSize`, `CupertinoDatePickerMode/DateOrder`, `CupertinoTimerPickerMode`,
  `OverlayVisibilityMode`) are re-exported from `flet/__init__.py` — `import flet as ft;
  ft.CupertinoActionSheet(...)`. (Unrelated: `ShareCupertinoActivityType` lives in
  `flet.controls.services.share`, for the iOS share sheet.) `cupertino/__init__.py`
  itself is empty; `cupertino_icons.py` is generated from `cupertino_icons.json`.
- **Docstring ghost:** `CupertinoAppBar` references `CupertinoSliverAppBar` for route
  transitions — that control does not exist in Flet 1.0.1, so large-title collapse-on-
  scroll has no sliver host; `transition_between_routes` still works app-bar to app-bar.

---

## 4. COVERAGE

- **Files read: 27 / 27** (25 control/color/icon modules + `__init__.py` + `cupertino_icons.json`
  backing data; `__pycache__` excluded).
- DDGS `src/` grep: `ft.Cupertino*` hits **0**; Material counterparts in use:
  `NavigationBar` (`app_shell.py:67`), `AppBar` (`results_screen.py:60`,
  `content_reader_screen.py:197`), `BottomSheet` (`ai_summary.py:105`,
  `content_fetcher.py:335`, `detail_sheet.py:356`), `AlertDialog` (7 call sites),
  `TextField` (chat + settings), `Switch` (2), `Slider` (2).
