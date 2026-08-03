"""AppShell — top-level shell branching onboarding vs dashboard.

Follows the KTV Player pattern: a @ft.component that reads observable
state and conditionally renders the appropriate screen.  The NavigationBar
is attached imperatively to page.views[0].navigation_bar via use_effect
(deliberate escape hatch for page-level chrome).
"""

from __future__ import annotations

import logging

import flet as ft
from flet import Control

from contexts.app_state_ctx import AppStateCtx
from contexts.controller_ctx import ControllerMethodsCtx

logger = logging.getLogger("AppShell")

_TAB_NAMES = ("Home", "History", "Settings")
_TAB_ICONS = (
    ft.Icons.HOME_ROUNDED,
    ft.Icons.HISTORY_ROUNDED,
    ft.Icons.SETTINGS_ROUNDED,
)


@ft.component
def AppShell() -> Control:
    """Top-level shell.  Reads observable state; renders Onboarding,
    Results, or the active dashboard tab."""
    controller = ft.use_context(ControllerMethodsCtx)
    state = ft.use_context(AppStateCtx)

    # ── NavigationBar sync ─────────────────────────────────────────────
    # Attach NavigationBar to page.views[0] imperatively — the same
    # deliberate escape hatch used by KTV Player.  Re-runs whenever
    # selected_tab, has_accepted_terms, or search_active changes.
    def _sync_navigation_bar():
        from flet import context

        page = context.page
        if not page or not page.views:
            return

        # Hide nav bar during onboarding or results
        if not state.has_accepted_terms or state.search_active:
            if page.views[0].navigation_bar is not None:
                page.views[0].navigation_bar = None
                try:
                    page.update()
                except Exception:
                    pass
            return

        def _on_tab_change(e):
            idx = e.control.selected_index
            logger.info("Tab changed: %s (index %d)", _TAB_NAMES[idx], idx)
            controller.navigate_tab(idx)

        destinations = [
            ft.NavigationBarDestination(icon=icon, label=label)
            for icon, label in zip(_TAB_ICONS, _TAB_NAMES, strict=True)
        ]
        page.views[0].navigation_bar = ft.NavigationBar(
            destinations=destinations,
            selected_index=state.selected_tab,
            on_change=_on_tab_change,
            bgcolor=ft.Colors.SURFACE,
            indicator_color=ft.Colors.with_opacity(0.12, ft.Colors.PRIMARY),
            label_behavior=ft.NavigationBarLabelBehavior.ALWAYS_SHOW,
        )
        try:
            page.update()
        except Exception:
            pass

    ft.use_effect(
        _sync_navigation_bar,
        [state.selected_tab, state.has_accepted_terms, state.search_active],
    )

    # ── Screen branching ───────────────────────────────────────────────
    if not state.has_accepted_terms:
        from screens.onboarding_screen import OnboardingScreen

        screen = OnboardingScreen()

    elif state.search_active:
        from screens.results_screen import ResultsScreen

        screen = ResultsScreen()

    else:
        if state.selected_tab == 1:
            from screens.history_screen import HistoryScreen

            screen = HistoryScreen(key=ft.ValueKey("history"))

        elif state.selected_tab == 2:
            from screens.settings_screen import SettingsScreen

            screen = SettingsScreen(key=ft.ValueKey("settings"))

        else:
            from screens.home_screen import HomeScreen

            screen = HomeScreen(key=ft.ValueKey("home"))

    return ft.SafeArea(content=screen, expand=True)
