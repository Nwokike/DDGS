# Flet 1.0.1 Material Controls — Dependency Audit for DDGS

Package: `flet==1.0.1`, scope `flet/controls/material/`. Consumer: DDGS
(`src/screens/`: home, results, extract, history, settings, chat, content_reader,
onboarding; `src/components/` + `results/`, `settings/`). Every control name below
was grepped against DDGS `src/*.py` (excluding `.flet/` build output).

DDGS baseline (heaviest use): `Text` 205, `Container` 195, `Icon` 79,
`IconButton` 39, `TextButton` 33, `FilledButton` 22, `Divider` 18, `AlertDialog` 18,
plain `SnackBar` 15, `OutlinedButton` 11, `Dropdown` 10, `ProgressRing` 7,
`TextField` (basic) 6, `BottomSheet` 3, `AppBar` 3, `SearchBar`/`ProgressBar`/
`Switch`/`Slider` 2 each, `NavigationBar`/`FloatingActionButton`/`Chip`/`Checkbox`
1 each. Tooltips used only as the `tooltip="…"` string prop (correct usage —
`Tooltip` is a value class, not a `Control`).

## 1. COMPLETE API INVENTORY (one line per control/variant)

- `Button` — base Material button: `content` str-or-Control + `icon`, `style/color/bgcolor/elevation`, `url`, `on_click/long_press/hover/focus/blur`, `focus()`; adaptive.
- `FilledButton` — max-impact button for final actions (Save/Confirm/Search); same API as `Button`. USED (22×).
- `FilledTonalButton` — secondary-color middle ground (e.g. "Next", filters); same API. UNUSED.
- `OutlinedButton` — medium-emphasis alt action; `style` usually needs `shape` + `side`. USED (11×).
- `TextButton` — lowest-priority action, invisible container until hover; `content/icon`. USED (33×).
- `FloatingActionButton` — circular primary action; page-level or inline; `mini`, per-state elevations, `url`. USED 1×.
- `IconButton` — round icon button; `selected/selected_icon` toggle mode, `splash_radius` (M2 only), `style` merged in `before_update`. USED (39×). Variants UNUSED: `FilledIconButton`, `FilledTonalIconButton`, `OutlinedIconButton`.
- `AlertDialog` (`DialogControl`) — `title/content/actions`, `modal`, `icon`, title/content/actions paddings + alignment, `shape`, `scrollable`, `barrier_color`; validation: needs ≥1 of title/content/visible-action. USED (18×).
- `BottomSheet` (`DialogControl`, via `page.show_dialog` — DDGS's established pattern) — `content`, `dismissible/draggable/show_drag_handle`, `scrollable/fullscreen`, `shape/barrier_color/size_constraints`. USED (3×: detail_sheet, content_fetcher, ai_summary).
- `Banner` (`DialogControl`, persistent non-modal top message) — `content` + ≥1 `actions` REQUIRED, `leading`, `force_actions_below`, `on_visible`. UNUSED (offline/cache banners are hand-rolled Containers).
- `SnackBar` (`DialogControl`) + `SnackBarAction` — `content`, `behavior` FIXED/FLOATING, `dismiss_direction` (7-way incl. NONE), `show_close_icon`, `action` (str or SnackBarAction, first-click-only), `duration`, `persist`, `on_action/on_visible`, shape/margin/width (FLOATING only). USED 15× but ALWAYS plain text+bgcolor — no action/close-icon/behavior anywhere.
- `MenuBar` — desktop cascading menu bar; `controls` (≥1 visible), `MenuStyle` (alignment/bgcolor/elevation/padding/side/shape/sizes/density). UNUSED.
- `MenuItemButton` — menu-bar leaf: `content`, `leading/trailing`, `close_on_click`, `focus_on_hover`, `overflow_axis`. UNUSED.
- `SubmenuButton` — cascading submenu: `controls` (MenuItemButtons or nested Submenus), `menu_style`, `alignment_offset`, `on_open/on_close`. UNUSED.
- `PopupMenuButton` — overflow-menu anchor: `items: PopupMenuItem(content/icon/checked/height/padding/label_text_style)`, `menu_position` OVER/UNDER, `on_open/on_cancel/on_select` (selected item id in `data`). UNUSED (only a code comment mentions PopupMenuItem — chat_screen.py:972).
- `ContextMenu` — wraps `content`; `items` (programmatic `open()`) or per-button `primary/secondary/tertiary_items` + triggers DOWN/LONG_PRESS; `open(global/local_position)`; `on_select` (item+index) / `on_dismiss`. UNUSED.
- `DatePicker` (`DialogControl`) — `value/first_date(1900)/last_date(2050)/current_date`, `date_picker_mode` DAY/YEAR, `entry_mode` CALENDAR/INPUT/CALENDAR_ONLY/INPUT_ONLY, help/cancel/confirm/error/format/range/hint/label texts, locale, `on_change/on_entry_mode_change`. UNUSED.
- `DateRangePicker` (`DialogControl`) — `start/end_value`, `save_text`, `error_invalid_range_text`, same calendar/input entry modes. UNUSED.
- `TimePicker` (`DialogControl`) — `value=time`, `entry_mode` DIAL/INPUT/DIAL_ONLY/INPUT_ONLY, `hour_format` SYSTEM/H12/H24, `orientation`, hour/minute/help/cancel/confirm/error labels, `on_change/on_entry_mode_change`. UNUSED.
- `Checkbox` — `value` True/False/(None+`tristate`), `label/label_position/label_style`, per-`ControlState` fill/overlay/border colors, `check/active/hover/focus_color`, `shape`, `on_change`. USED 1× (variants like tristate unused).
- `Radio` (`value` string; `toggleable`) in `RadioGroup` (`content` wrapper, `value`, `on_change`). UNUSED (zero hits).
- `Switch` — `value`, `label(+position/style)`, active/inactive thumb+track colors, per-state `thumb_color/thumb_icon/track_color/track_outline_*`, `adaptive` → CupertinoSwitch on iOS/macOS. USED 2× (per-state styling unused).
- `Slider` — `value/min/max`, `divisions` + `label` with `{value}`, `round` decimals, `interaction` TAP_AND_SLIDE/TAP_ONLY/SLIDE_ONLY/SLIDE_THUMB, `secondary_track_value` (buffering-style), `year_2023`, `on_change/start/end`. USED 2× (basic only).
- `RangeSlider` — dual-thumb `start/end_value` + `label`/`divisions`/`round`, active/inactive/overlay colors. UNUSED.
- `SegmentedButton` + `Segment(value, icon/label)` — `selected: list[str]`, `allow_empty/multiple_selection`, `show_selected_icon`, `direction`, `on_change`. UNUSED.
- `Chip` — `label`, `leading` (Icon/CircleAvatar), `selected` + `on_select` (checkmark) XOR `on_click` (enforced), `delete_icon(+tooltip/color)` + `on_delete`, density/animation styles. USED 1× plain (no select/delete/avatar).
- `AutoComplete` — `value`, `suggestions: AutoCompleteSuggestion(key/value, case-insensitive key filter)`, `suggestions_max_height`, `on_select(index+selection)`/`on_change`, readonly `selected_index`. UNUSED.
- `SearchBar` — full search-view route: `bar_*` (closed: leading/trailing/hint/bgcolor/shape/text-style/padding) + `view_*` (open: leading/trailing/elevation/bgcolor/hint/shape/size) + `controls` suggestions, `full_screen`, `open_view()/close_view(text)`, `on_submit/on_change/on_tap(on_tap_outside_bar/view)`. USED 2× (home_search, model_picker) — suggestion-list wiring underused.
- `Dropdown` (M3) — `value`, `options: DropdownOption(key/text/content/leading/trailing_icon/style)`, `enable_filter/enable_search/editable`, `menu_height/width/style/expanded_insets`, `selected_suffix`, `input_filter/capitalization`, full FormField decoration, `on_select/on_text_change`. USED 10× (basic; no filter/editable/icons).
- `DropdownM2` (legacy) — `Option(key/text/content/alignment)`, `value`, `hint_content`, `select_icon`, `item_height/max_menu_height`, `on_change`. UNUSED (correct — M3 `Dropdown` preferred).
- `TextField` — `value`, `selection` + `on_selection_change`, `keyboard_type` (15: TEXT…DATETIME/EMAIL/URL/WEB_SEARCH…), `multiline/min/max_lines`, `max_length`, `password + can_reveal_password + obscuring_character`, `shift_enter` chat-mode, regex `input_filter` (+Numbers/TextOnly presets), `autofill_hints`, counter/error/helper/hint + prefix/suffix icons, `focus()`, `on_submit/on_tap_outside`. USED 6× basic (only premium email sets `keyboard_type`; no counter/autofill/mask/filter/selection use).
- `FormFieldControl` (base of TextField/DropdownM2) — shared label/hint/helper/error/counter/prefix/suffix/fill/border API; `filled` auto-True when colors set; `border` = single `InputBorder` or per-`ControlState` dict; `collapsed`, `fit_parent_size`. `InputBorder` subclasses: `OutlineInputBorder` / `UnderlineInputBorder` / `NoInputBorder`.
- `Card` — `content`, `variant` ELEVATED/FILLED/OUTLINED, elevation/bgcolor/shadow/shape; adaptive. UNUSED (result cards are Containers).
- `ListTile` — `title/subtitle(/is_three_line)`, `leading/trailing`, `selected + toggle_inputs` (toggles inner Radio/Checkbox/Switch), shape/density/padding/min_height, `on_click/long_press`. UNUSED.
- `ExpansionTile` — standalone expandable ListTile: `title/subtitle`, `controls` when expanded, `affinity`, `maintain_state`, collapsed_* vs expanded colors/shapes, `animation_style`, `on_change` (bool). UNUSED.
- `ExpansionPanel` (only inside `ExpansionPanelList`) — `header/content/expanded/can_tap_header`; list: `elevation/spacing/divider_color/expand_icon_color`, `on_change(index+expanded)`. UNUSED.
- `DataTable` + `DataColumn` (label/numeric/tooltip/`on_sort`) + `DataRow` (cells/selected/`on_select_change`) + `DataCell` (content/placeholder/edit-icon/cell gestures) — sorting, selectable rows, `sort_column_index/ascending`, per-state row colors; ext package `flet-datatable2` for sticky headers/widths. UNUSED.
- `Tabs` system — `Tabs(length + selected_index + content + move_to(index, curve, duration))` wrapping `TabBar(tabs: Tab(label/icon), scrollable, tab_alignment, indicator/UnderlineTabIndicator, secondary, on_click/on_hover)` + `TabBarView(controls per tab, viewport_fraction)`; lengths must match. UNUSED.
- `Divider` (color/height/thickness/indents/radius) USED 18×; `VerticalDivider` (width/thickness) UNUSED.
- `Badge` — notification dot/count; attaches via `badge=` prop (e.g. `FilledIconButton(badge=…)`), `label` (1–4 chars) or dot, offset/alignment/sizes, `label_visible` conditional toggle. UNUSED.
- `CircleAvatar` — `content` initials or `foreground/background_image_src` fallback chain, `radius` vs min/max, `on_image_error`. UNUSED.
- `Tooltip` (VALUE, not Control) — `message`, trigger MANUAL/TAP/LONG_PRESS, show/wait/exit durations, `prefer_below`; applied as `tooltip=` prop (DDGS does this correctly everywhere).
- `SelectionArea` — makes child selectable; wraps Row/Column for multi-select; `on_change`. UNUSED.
- `ProgressBar` — linear; `value=None` = indeterminate, `bar_height`, stop-indicator/track-gap/`year_2023` M3 styling. USED 2× (determinate only).
- `ProgressRing` — circular; `value=None` = indeterminate, stroke width/align/cap, size constraints, padding. USED 7× (all small indeterminate spinners).
- `NavigationBar` — M3 bottom nav; ≥2 `NavigationBarDestination(icon/label/selected_icon/bgcolor)`, `selected_index`, `label_behavior`, indicator color/shape, `on_change`; adaptive → Cupertino tab bar. USED 1× (app_shell).
- `NavigationRail` — side nav 3–5 views; `extended`, `label_type` NONE/ALL/SELECTED, leading/trailing, `group_alignment`, `use_indicator`. UNUSED.
- `NavigationDrawer` — slide-in drawer; `controls` incl. `NavigationDrawerDestination(icon/label/selected_icon/bgcolor)`, `selected_index`, indicator color/shape, `on_dismiss`. UNUSED.
- `BottomAppBar` — bottom bar with FAB `shape` notch + `notch_margin`. UNUSED.
- `AppBar` (adaptive) — `leading/title/actions`, `center_title`, `toolbar_height/opacity`, `force_material_transparency`, `shape`. USED 3×.
- `ReorderableListView` (extends ListView) — drag-reorder with default or custom `ReorderableDragHandle`, header/footer, `on_reorder` (manual list reorder required) + start/end. UNUSED.
- `Container` — core layout primitive: padding/alignment/bgcolor/gradient/border/radius/shape/clip, `ink` ripples, image, blur, shadow, nested `theme/dark_theme/theme_mode`, `url`, `ignore_interactions`; adaptive+action. USED (195×).
- `Icons` — lazy proxy over `icons.json` (full Material set; 8,840-line `icons.pyi` type DB); `Icons.random()`. USED (239×).
- NOT IN Flet 1.0.1 (verified across `flet/controls/`): **Stepper, Carousel, Dismissible** — do not plan around them.

## 2. WHAT DDGS DOESN'T USE — ranked by UX impact

1. **`ContextMenu` + `PopupMenuButton` (checked items)** — zero uses (one comment only). DDGS is a desktop-first app with zero right-click/long-press menus anywhere: result cards, history rows, chat messages all lack contextual actions (Open / Copy URL / Save / Summarize / Remove). Highest leverage: wrap result cards in `ContextMenu` with `secondary_trigger`, checked `PopupMenuItem`s for format choices.
2. **`Badge`** — zero uses; `app_shell.py:113` even comments "No badge". Download-queue count on the download icon and credit balance on the wallet icon are currently invisible or require opening dialogs.
3. **Rich `SnackBar` (`action`/`on_action`, `show_close_icon`, `FLOATING`, `persist`)** — 15 plain-text uses, never an action. Three screens brand deletions "cannot be undone" (`history_screen.py:69`, `settings_screen.py:90`, `chat_screen.py:1005+`) with no Undo affordance — `SnackBarAction("Undo")` + `persist` is the textbook fix.
4. **`SegmentedButton`** — zero uses. Single-select result-type switcher (All/Images/Videos/News, allow_empty_selection=False) is the M3-idiomatic replacement for the format `Dropdown` currently embedded in result cards (`cards.py:145`).
5. **`DatePicker` / `TimePicker` (`DateRangePicker` bonus)** — zero uses, yet scheduling infra already exists (`STORAGE_SCHEDULED_SCRAPES`, `get/set_scheduled_scrapes`, "Cancel scheduled crawl" tooltip in `sections_ai.py:152`) with no UI to pick a crawl time. Entry-mode + locale + min/max-date props cover the whole feature.
6. **`AutoComplete`** — zero uses. Home `SearchBar` and chat inputs have no history/suggestion dropdown; `AutoCompleteSuggestion(key/value)` maps directly onto stored search history.
7. **`ExpansionTile` / `ExpansionPanelList`** — zero uses. Settings screens hand-stack sections; per-result details open a full `BottomSheet` where an inline expansion would be lighter; `maintain_state` keeps chat/reader state.
8. **`Radio`/`RadioGroup`** — zero uses. Search preferences (region / safesearch / backend / timelimit) currently lack a single-select primitive.
9. **`RangeSlider`** — zero uses. Dual-thumb range fits max-results / timelimit windows in advanced settings (`Slider` basic is used 2×; range variant never).
10. **`Banner`** — zero uses (offline/cache notices are hand-rolled Containers in `offline_banner.py`/`cache_banner.py`). `Banner` is the persistent-with-required-action primitive (`content` + ≥1 action enforced).
11. **`SelectionArea`** — zero uses. One-line wrapper makes assistant answers and reader content copy-selectable; currently only `selectable=True` on isolated Texts.
12. **`DataTable`** — zero uses. Extract screen has no tabular presentation for structured results.
13. **`ReorderableListView`** — zero uses. Pinned/history ordering is fixed; drag-reorder with `ReorderableDragHandle` fits both.
14. **`Dropdown` advanced props** (`enable_filter`, `editable`, option leading/trailing icons, `selected_suffix`, `menu_height`) and **`TextField` advanced props** (`max_length`+`counter`, `autofill_hints` — premium email sets only `keyboard_type`, password reveal, `input_filter`, `selection` API, `shift_enter` chat mode) — all at basic usage.
15. **Display-variant depth** — `Card`/`ListTile`/`CircleAvatar`/`VerticalDivider`/`BottomAppBar`/tonal+filled+outlined IconButtons all zero (result cards reinvent `Card`; avatar-less author rows); `NavigationDrawer`/`NavigationRail`/`Tabs`/`MenuBar` zero (`NavigationBar` 1×); `ProgressBar` never indeterminate/styled; `Slider.secondary_track_value` (buffering-style download progress) unused; `Chip` 1 plain use (no select/delete/avatar).

## 3. GOTCHAS

- **Adaptive renders Cupertino on Apple platforms.** ~15 controls mix in `AdaptiveControl` (AppBar, Button, Card, Checkbox, Container, ExpansionPanel/Tile, IconButton, ListTile, NavigationBar/Drawer, OutlinedButton, Radio, Slider, Switch, Tabs…). DDGS never sets `adaptive=` (verified zero hits) so Windows stays Material — but flipping it later silently drops `ft.Theme`/`ColorScheme` styling on iOS/macOS (CupertinoTheme takes over) and orphan the hardcoded `AppColors` hexes. Keep `adaptive` off or budget a Cupertino theme pass.
- **Theme tokens vs hardcoded hex.** `core/theme.py` correctly drives brand via `ft.Theme(color_scheme=…)` mapping `AppColors` (light+dark, Outfit, COMFORTABLE density). State-driven widgets (`Badge`, `SegmentedButton` selected, `NavigationBar` indicator, `Switch` track) resolve from `color_scheme` automatically — hardcoding `AppColors.PRIMARY` per control bypasses light/dark switching. Prefer theme tokens for anything stateful.
- **Deprecated in 1.0.0, removal 1.3.0 — DDGS is clean (verified zero uses, keep it that way):** `InputBorder.OUTLINE/UNDERLINE/NONE` → `OutlineInputBorder()/UnderlineInputBorder()/NoInputBorder()`; `FormFieldControl`/`Dropdown` `border_radius/border_width/border_color/focused_border_*` → `border=`; `DropdownM2.border_radius` → `menu_border_radius`. (Note: bare `border_radius=` on Container/Card/DetailSheet is fine — only the FormField/Dropdown ones are deprecated.)
- **Naming traps:** `Tooltip` is a value (`tooltip="…"` prop — DDGS correct); `Badge` attaches via `badge=` prop, not layout; `SnackBarAction` vs `SnackBar.on_action`; M3 `Dropdown`/`DropdownOption` (filter+editable) vs legacy `DropdownM2`/`Option` (DDGS correctly on M3); `PopupMenuItem` is shared by `PopupMenuButton` AND `ContextMenu`; `MenuBar/MenuItemButton/SubmenuButton` = desktop menu bar, ≠ popup/context; `ExpansionPanel` lives only in `ExpansionPanelList` vs standalone `ExpansionTile`; `Tabs.length` must equal `TabBar.tabs` and `TabBarView.controls` — use `move_to()` for animated jumps; pickers + `Banner` + `BottomSheet` + `AlertDialog` + `SnackBar` are ALL `DialogControl`s shown via `page.show_dialog` (DDGS's BottomSheet pattern generalizes); `Chip` `on_click` XOR `on_select` is enforced; `ProgressBar/Ring` `value=None` = indeterminate; `SearchBar` `bar_*` vs `view_*` split + `open_view()/close_view(text)`.
- **Windows vs Android:** pickers render native-styled dialogs per OS; `keyboard_type`/`autofill_hints` affect mobile keyboards only; `enable_feedback` haptics are Android-only; `Tooltip` = hover on desktop, long-press on mobile (`TooltipTriggerMode`); `Switch.adaptive` changes iOS/macOS only — Windows is always Material.

## 4. COVERAGE

- **56 / 56** `.py` files in `flet/controls/material/` read completely (55 control modules + `__init__`); `icons.pyi` (8,840-line icon DB) + `icons.json` noted via `icons.py` proxy (`Icons.random()` supported).
- Absence of Stepper/Carousel/Dismissible verified by name search across all of `flet/controls/`.
- DDGS verification: full `ft.*` usage census + targeted greps per control family, `AppColors`/theme tokens (`core/theme.py`, `AppColors` class), deprecated-prop scan, and variant-level checks (`FilledTonal*`, `*IconButton`, `Cupertino`, `adaptive=`).
