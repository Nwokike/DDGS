
# DDGS Refactoring Plan: Old Flet → New Declarative React-Style Architecture

## Overview

Migrate DDGS from the old imperative Flet pattern (`page.views`, manual `route_change`, non-reactive state) to the new declarative React-style pattern (`@ft.component`, `use_state`/`use_context`/`use_effect`, `@ft.observable`, `page.render()`), following KTV Player as the reference implementation.

**Goal**: Modern, performant, maintainable code with batched delta updates, reactive state, and functional components — while preserving all existing features and visual design.

---

## Architecture Mapping: Old → New

| Concept | Old (Current) | New (Target) |
|---------|---------------|--------------|
| Entry point | `async def main(page)` with 400 lines | `main(page)` → `AppController(page)` → `page.render(lambda: AppShell())` |
| Routing | `page.on_route_change` + `page.views.clear()` + rebuild | State-based branching in `AppShell` (`state.selected_tab`) |
| State | `AppState()` plain class, manually mutated | `@ft.observable AppState` + `AppStateCtx = ft.create_context(state)` |
| Callbacks | Passed as closures through view builders | `ControllerMethods` dataclass in context |
| Navigation | `navigate(route)` sets `page.route` + manual rebuild | `set_selected_tab(n)` triggers re-render via `use_state` |
| Views | `ft.View(route=..., controls=[...])` appended to `page.views` | `@ft.component` functions returning controls |
| Results | Built inline without route change, views cleared/rebuilt | `state.search_active` flag, `ResultsScreen` component |
| Ads | `build_banner_ad(page)` called in view builders | `BannerAd` component, `use_context` for ad service |

---

## Target Directory Structure

```
src/
├── main.py                    # Minimal: ft.run + AppController init (~30 lines)
├── app_controller.py          # NEW: Business logic extracted from old main.py
├── app_shell.py               # NEW: @ft.component root — branches on state
├── core/
│   ├── constants.py           # Keep as-is
│   ├── state.py               # REWRITE: @ft.observable AppState
│   ├── theme.py               # Keep as-is
│   ├── tokens.py              # Keep as-is
│   ├── styles.py              # Keep (banner ad helper)
│   └── utils.py               # Keep as-is
├── contexts/                  # NEW: Context providers
│   ├── __init__.py
│   ├── app_state_ctx.py       # AppStateCtx = ft.create_context(state)
│   └── controller_ctx.py      # ControllerMethodsCtx with no-op defaults
├── components/                # NEW: Reusable UI components
│   ├── __init__.py
│   ├── banner_ad.py           # Extracted from styles.py
│   ├── search_box.py          # Refactored from views/home/search_box.py
│   ├── result_card.py         # Extracted from views/results/cards.py
│   ├── image_card.py          # Extracted from views/results/cards_media.py
│   ├── category_card.py       # Extracted from views/home/cards.py
│   ├── onboarding_slide.py    # Extracted from views/onboarding_view.py
│   ├── loading_state.py       # NEW: loading/error/empty state components
│   └── nav_bar.py             # NavigationBar component
├── hooks/                     # NEW: Custom React-style hooks
│   ├── __init__.py
│   ├── use_search.py          # Search + extract logic
│   ├── use_settings.py        # Settings persistence
│   └── use_debounce.py        # Debounce hook (from KTV reference)
├── screens/                   # NEW: Page-level @ft.component screens
│   ├── __init__.py
│   ├── onboarding_screen.py   # Converted from views/onboarding_view.py
│   ├── home_screen.py         # Converted from views/home/view_builder.py
│   ├── results_screen.py      # Converted from views/results/view_builder.py
│   ├── history_screen.py      # Converted from views/history_view.py
│   └── settings_screen.py     # Converted from views/settings/view_builder.py
├── services/                  # KEEP as-is (business logic layer)
│   ├── ad_service.py          # Keep (with UMP consent from uncommitted changes)
│   ├── search_service.py      # Keep
│   ├── storage_service.py     # Keep
│   ├── media_downloader.py    # Keep
│   └── youtube/               # Keep
└── views/                     # DELETE after migration complete
    └── (old files removed)
```

---

## Implementation Phases

### Phase 1: Foundation (No Visual Changes)

**Step 1.1**: Commit uncommitted UMP consent changes
- Commit the existing working tree changes (pyproject.toml bump, ad_service UMP, main.py gather_consent)
- This establishes the flet 0.86.2 baseline

**Step 1.2**: Rewrite `core/state.py` with `@ft.observable`
- Add `@ft.observable` decorator to `AppState`
- Add new navigation fields: `selected_tab: int = 0`, `search_active: bool = False`, `has_accepted_terms: bool = False`
- Keep all existing fields with same defaults
- Keep `SearchResult` and `SearchProgress` dataclasses unchanged

**Step 1.3**: Create `contexts/` directory
- `app_state_ctx.py`: `AppStateCtx = ft.create_context(state)`
- `controller_ctx.py`: `ControllerMethods` dataclass with no-op defaults for: `start_search`, `run_extract`, `cancel_search`, `go_home`, `navigate_tab`, `save_setting`

**Step 1.4**: Create `app_controller.py`
- Extract all business logic from old `main.py` into `AppController` class
- Methods: `init()`, `start_search()`, `run_extract()`, `cancel_search()`, `load_settings()`, `save_setting()`
- Mount UI: `self.page.render(lambda: ControllerMethodsCtx(methods, lambda: AppShell()))`

### Phase 2: AppShell + Screens

**Step 2.1**: Create `app_shell.py`
- `@ft.component` function
- `use_context(AppStateCtx)` for state
- `use_context(ControllerMethodsCtx)` for callbacks
- `use_effect` to sync NavigationBar to `page.views[0].navigation_bar` (imperative escape hatch, same pattern as KTV)
- State-based branching: OnboardingScreen → ResultsScreen → HomeScreen/HistoryScreen/SettingsScreen

**Step 2.2**: Convert `OnboardingScreen` to `@ft.component`
- `use_state` for slide index, agreement checkbox
- Preserve: swipe gestures (GestureDetector), dot indicators, Skip/Next/Get Started, privacy/terms links

**Step 2.3**: Convert `HomeScreen` to `@ft.component`
- `use_state` for search query, active category tab
- `use_memo` for category grid (depends on `state.default_tab`)
- Preserve: hero, search box with tools panel, category grid, privacy banner, recent queries, features section, how-it-works, no-account banner, banner ads

**Step 2.4**: Convert `ResultsScreen` to `@ft.component`
- `use_context(AppStateCtx)` for `search_progress`, `extract_result`
- Conditional rendering: loading → error → results → empty
- Preserve: all result card types (text, image, video, news, books, extract), banner ads every 4th item, image grid, download functionality, video rate-limit notice

**Step 2.5**: Convert `HistoryScreen` to `@ft.component`
- `use_context(AppStateCtx)` for `search_history`
- `use_state` for clear-all dialog open state
- Preserve: history list with type icons, tap to re-search, clear all with confirmation dialog

**Step 2.6**: Convert `SettingsScreen` to `@ft.component`
- `use_context(AppStateCtx)` for all settings
- `use_state` for local UI state (expanded sections, slider values)
- Preserve: theme selector (3 cards), search rules (chips, dropdowns, slider), backends, extraction format, downloads (video quality), connection (proxy, SSL), performance (threads), activity terminal, local storage, about section

### Phase 3: Reusable Components

**Step 3.1**: Extract reusable components from old view helpers
- `components/search_box.py` — SearchBox with `use_state` for tools panel toggle
- `components/result_card.py` — ResultCard, VideoResultCard, NewsResultCard
- `components/image_card.py` — ImageCard with download capability
- `components/category_card.py` — CategoryCard with active state
- `components/onboarding_slide.py` — OnboardingSlide with dot indicators
- `components/banner_ad.py` — BannerAd wrapping ad_service
- `components/nav_bar.py` — NavBar (used in AppShell's use_effect)

**Step 3.2**: Create loading/error/empty state components
- `components/loading_state.py` — LoadingState (ProgressRing + text)
- `components/loading_state.py` — ErrorState (icon + message + retry)
- `components/loading_state.py` — EmptyState (illustration + message)

### Phase 4: Custom Hooks

**Step 4.1**: Create hooks
- `hooks/use_search.py` — wraps search/extract logic, manages SearchProgress
- `hooks/use_settings.py` — wraps storage.get_*/set_*, returns `(value, setter)` per setting
- `hooks/use_debounce.py` — debounce value changes (adapted from KTV)

### Phase 5: Clean Up

**Step 5.1**: Update `main.py` to minimal entry point (~30 lines)
- `ft.run(main)` with `AppController` init
- Wire `on_view_pop`, `on_disconnect`

**Step 5.2**: Remove old `views/` directory entirely

**Step 5.3**: Verify no dead code with ruff lint

### Phase 6: Polish + Performance

**Step 6.1**: Add `ft.memo()` to expensive components (ResultCard, CategoryCard, ImageCard)

**Step 6.2**: Optimize re-renders with `use_memo` for derived data, `use_callback` for stable function references

**Step 6.3**: Visual polish — verify all screens match current design, test theme switching, test full navigation flow

---

## Cherry-Pick Strategy (main → playstore)

After all work is complete on `main`:

1. **Do NOT cherry-pick** these files (they intentionally differ between branches):
   - `.github/workflows/build-all.yml` (multi-platform vs AAB-only)
   - `README.md` (multi-platform vs Play Store focused)

2. **Cherry-pick everything else** — the refactored architecture is branch-agnostic

3. **After cherry-pick**, manually resolve the 2-3 files that differ:
   - Add YouTube download restriction dialog to results/download flow
   - Add "Edition: Google Play Edition" row to settings about section
   - Verify CI workflow still builds AAB correctly

---

## Key Design Decisions

1. **State-based routing** (not `Router`): KTV Player doesn't use `Router` either — tabs + state branching is simpler and sufficient for DDGS's 3-tab navigation + results overlay.

2. **NavigationBar via `use_effect`**: Imperative attachment to `page.views[0].navigation_bar` — same deliberate escape hatch pattern as KTV Player for page-level chrome.

3. **Results as inline component**: `state.search_active` flag shows/hides ResultsScreen in AppShell — no view stack manipulation. Hardware back button sets `search_active = False`.

4. **Keep services unchanged**: SearchService, StorageService, AdService, MediaDownloader are pure business logic — only their integration points change (closure passing → context).

5. **Observable state for all shared data**: Settings, search history, theme mode, ad service reference all live in AppState — components auto-subscribe via `use_context(AppStateCtx)`.

---

## Verification Checklist

- [ ] All existing features work identically
- [ ] Onboarding flow (3 slides, agreement, skip/next/get started)
- [ ] Home screen (hero, search, categories, recent, features, how-it-works)
- [ ] Search (all 6 types: text/images/videos/news/books/extract)
- [ ] Results display (text cards, image grid, video cards, news, books, extract)
- [ ] Download functionality (images, videos, extracted content)
- [ ] YouTube video playback (via InnerTube fallback)
- [ ] History (list, re-search, clear all)
- [ ] Settings (all sections: theme, search rules, backends, downloads, connection, performance, about)
- [ ] AdMob banner ads in correct positions
- [ ] AdMob interstitial after download + after search
- [ ] UMP consent flow
- [ ] Theme switching (dark/light/system)
- [ ] Offline handling and error states with retry
- [ ] Navigation bar (3 tabs, correct highlighting)
- [ ] Hardware back button behavior
- [ ] App disconnect (storage flush)
- [ ] No regressions in build configuration
