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

    # ── Ask-AI FAB (AI mode ON, hidden while chat is open) ─────────────
    content = ft.SafeArea(content=screen, expand=True)
    if (
        not state.has_accepted_terms
        or state.chat_open
        or not state.ai_mode_enabled
    ):
        return content

    from flet import context as flet_context

    from components.wallet import show_wallet_dialog
    from core import tokens as _t
    from core.theme import AppColors

    def _on_fab(e):
        page = flet_context.page
        ctrl = getattr(page, "_ddgs_controller", None) if page else None
        if not ctrl:
            return
        if state.credits_remaining <= 0:
            show_wallet_dialog(page)
        else:
            ctrl.open_chat()

    credits = state.credits_remaining
    fab_color = AppColors.PRIMARY if credits > 0 else ft.Colors.with_opacity(
        0.4, ft.Colors.ON_SURFACE
    )
    badge_color = (
        AppColors.SUCCESS
        if credits > 20
        else AppColors.WARNING
        if credits >= 5
        else AppColors.ERROR
    )
    fab = ft.FloatingActionButton(
        icon=ft.Icons.AUTO_AWESOME_ROUNDED,
        bgcolor=fab_color,
        tooltip="Ask AI" if credits > 0 else "Out of AI credits — tap for options",
        on_click=_on_fab,
    )
    badge = ft.Container(
        content=ft.Text(
            str(credits),
            size=9,
            weight=ft.FontWeight.W_700,
            color=ft.Colors.WHITE,
        ),
        padding=ft.Padding(5, 1, 5, 1),
        border_radius=_t.RADIUS_PILL,
        bgcolor=badge_color,
        border=ft.Border.all(1.5, ft.Colors.SURFACE),
    )
    return ft.Stack(
        [
            content,
            ft.Positioned(
                right=16,
                bottom=96,
                content=ft.Stack(
                    [
                        fab,
                        ft.Positioned(top=-6, right=-4, content=badge),
                    ]
                ),
            ),
        ],
        expand=True,
    )
