"""OnboardingScreen - swipe-through intro with privacy/terms agreement.

Converted from views/onboarding_view.py to declarative @ft.component.
Uses use_state for slide index and agreement checkbox; controller
callbacks via context for persistence and navigation.
"""

from __future__ import annotations

import flet as ft
from flet import Control

from contexts.app_state_ctx import AppStateCtx
from contexts.controller_ctx import ControllerMethodsCtx
from core.theme import AppColors

ICON_SIZE = 64
ICON_CONTAINER_SIZE = 120

_SLIDES = [
    {
        "icon": ft.Icons.SHIELD_ROUNDED,
        "color": AppColors.PRIMARY,
        "title": "100% Privacy-First",
        "body": (
            "No accounts, no tracking, no filter bubbles. "
            "Search 10 engines at once and get clean, "
            "unbiased results."
        ),
    },
    {
        "icon": ft.Icons.DOWNLOAD_ROUNDED,
        "color": AppColors.PRIMARY_LIGHT,
        "title": "Scrape Any Page",
        "body": (
            "Turn any link into text, Markdown, HTML or raw source. "
            "Read it clean, save it to your device, or feed it to "
            "your tools and AI agents."
        ),
    },
    {
        "icon": ft.Icons.ROCKET_LAUNCH_ROUNDED,
        "color": AppColors.ACCENT,
        "title": "Downloads & Filters",
        "body": (
            "Download videos in the quality you want, filter images "
            "and videos by size or duration, and choose your own "
            "search sources."
        ),
    },
    {
        "icon": ft.Icons.CHAT_BUBBLE_OUTLINE_ROUNDED,
        "color": AppColors.ACCENT,
        "title": "Assistant, Done Privately",
        "body": (
            "Turn on Assistant mode to get an Ask Assistant button. "
            "It searches and fetches pages for you, live. Queries go "
            "through your in-app Kiri router first: no history, no "
            "identity, no training. Manual search stays free."
        ),
    },
]


def _build_slide(s: dict) -> ft.Column:
    """Build a single onboarding slide content."""
    return ft.Column(
        [
            ft.Container(height=80),
            ft.Container(
                content=ft.Icon(s["icon"], size=ICON_SIZE, color=s["color"]),
                width=ICON_CONTAINER_SIZE,
                height=ICON_CONTAINER_SIZE,
                border_radius=ICON_CONTAINER_SIZE // 2,
                bgcolor=ft.Colors.with_opacity(0.1, s["color"]),
                alignment=ft.Alignment.CENTER,
            ),
            ft.Container(height=32),
            ft.Text(
                s["title"],
                size=24,
                weight="bold",
                text_align="center",
                font_family="Outfit",
            ),
            ft.Container(height=12),
            ft.Text(
                s["body"],
                size=14,
                color=ft.Colors.ON_SURFACE_VARIANT,
                text_align="center",
                font_family="Outfit",
                style=ft.TextStyle(height=1.4),
            ),
        ],
        horizontal_alignment="center",
        spacing=0,
    )


def _build_dots(active: int) -> list[ft.Control]:
    """Build dot indicators for the current slide."""
    dots = []
    for i in range(len(_SLIDES)):
        dots.append(
            ft.Container(
                width=10 if i == active else 6,
                height=6,
                border_radius=3,
                bgcolor=AppColors.PRIMARY
                if i == active
                else ft.Colors.with_opacity(0.2, ft.Colors.ON_SURFACE),
                animate=ft.Animation(200, "easeOut"),
            )
        )
    return dots


@ft.component
def OnboardingScreen() -> Control:
    """Swipeable onboarding with 3 slides, privacy/terms agreement."""
    state = ft.use_context(AppStateCtx)
    controller = ft.use_context(ControllerMethodsCtx)

    slide_index, set_slide_index = ft.use_state(0)
    agreed, set_agreed = ft.use_state(False)

    is_last = slide_index == len(_SLIDES) - 1

    def _on_swipe(e: ft.DragEndEvent):
        if e.primary_velocity is not None:
            if e.primary_velocity < -200 and slide_index < len(_SLIDES) - 1:
                set_slide_index(slide_index + 1)
            elif e.primary_velocity > 200 and slide_index > 0:
                set_slide_index(slide_index - 1)

    def _on_next(e):
        from flet import context as flet_context

        page = flet_context.page
        if is_last:
            if not agreed:
                snack = ft.SnackBar(
                    ft.Text(
                        "Accept the Privacy Policy & Terms of Service to continue."
                    ),
                    bgcolor=AppColors.ERROR,
                )
                snack.open = True
                page.show_dialog(snack)
                page.update()
                return
            page.run_task(_finish)
        else:
            set_slide_index(slide_index + 1)

    def _on_skip(e):
        from flet import context as flet_context

        flet_context.page.run_task(_finish)

    async def _finish():
        await controller.save_async("onboarding_done", True)
        state.has_accepted_terms = True

    return ft.Container(
        content=ft.Column(
            [
                # Skip button
                ft.Row(
                    [
                        ft.TextButton(
                            "Skip",
                            on_click=_on_skip,
                            style=ft.ButtonStyle(color=ft.Colors.ON_SURFACE_VARIANT),
                        ),
                    ],
                    alignment="end",
                ),
                # Swipeable slide
                ft.GestureDetector(
                    content=ft.Container(
                        content=_build_slide(_SLIDES[slide_index]),
                        expand=True,
                        padding=ft.Padding(32, 0, 32, 0),
                    ),
                    on_horizontal_drag_end=_on_swipe,
                ),
                # Dot indicators
                ft.Row(
                    controls=_build_dots(slide_index),
                    alignment="center",
                    spacing=6,
                ),
                ft.Container(height=20),
                # Agreement checkbox (visible on last slide)
                ft.Container(
                    content=ft.Row(
                        [
                            ft.Checkbox(
                                value=agreed,
                                on_change=lambda e: set_agreed(e.control.value),
                            ),
                            ft.Text(
                                "I agree to the ",
                                size=11,
                                font_family="Outfit",
                            ),
                            ft.TextButton(
                                "Privacy Policy",
                                style=ft.ButtonStyle(color=AppColors.PRIMARY),
                                action=ft.OpenUrl("https://kiri.ng/privacy"),
                            ),
                            ft.Text(
                                " & ",
                                size=11,
                                font_family="Outfit",
                            ),
                            ft.TextButton(
                                "Terms of Service",
                                style=ft.ButtonStyle(color=AppColors.PRIMARY),
                                action=ft.OpenUrl("https://kiri.ng/terms"),
                            ),
                        ],
                        alignment="center",
                        spacing=0,
                        wrap=True,
                    ),
                    visible=is_last,
                ),
                ft.Container(height=16),
                # Action button
                ft.Container(
                    content=ft.FilledButton(
                        "Get Started" if is_last else "Next",
                        icon=(
                            ft.Icons.CHECK_ROUNDED
                            if is_last
                            else ft.Icons.ARROW_FORWARD_ROUNDED
                        ),
                        on_click=_on_next,
                        width=200,
                        height=48,
                        style=ft.ButtonStyle(
                            bgcolor=AppColors.PRIMARY,
                            color=ft.Colors.WHITE,
                            shape=ft.RoundedRectangleBorder(radius=24),
                        ),
                    ),
                    alignment=ft.Alignment.CENTER,
                ),
                ft.Container(height=48),
            ],
            expand=True,
        ),
        padding=20,
        expand=True,
        bgcolor=ft.Colors.SURFACE,
    )
