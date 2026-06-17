"""Onboarding view — swipeable intro slides."""

from __future__ import annotations

from typing import Callable

import flet as ft

from core.theme import AppColors

ICON_SIZE = 64
ICON_CONTAINER_SIZE = 120


def build_onboarding_view(page: ft.Page, on_done: Callable, storage=None) -> ft.View:
    current_page = {"index": 0}
    indicator_row = ft.Ref[ft.Row]()
    slide_container = ft.Ref[ft.Container]()

    slides = [
        {
            "icon": ft.Icons.SEARCH_ROUNDED,
            "color": AppColors.PRIMARY,
            "title": "Search Across 14 Engines",
            "body": (
                "Web, images, videos, news, and books — all from one place. "
                "Powered by DuckDuckGo with Brave, Google, Bing, Yahoo, "
                "Yandex, Wikipedia, and more."
            ),
        },
        {
            "icon": ft.Icons.DOWNLOAD_ROUNDED,
            "color": AppColors.SECONDARY,
            "title": "Extract Any Page",
            "body": (
                "Pull content from any URL as Markdown, plain text, HTML, "
                "or raw data. Perfect for research and content gathering."
            ),
        },
        {
            "icon": ft.Icons.TUNE_ROUNDED,
            "color": AppColors.PRIMARY,
            "title": "Full Control",
            "body": (
                "Choose your backend, set time filters, safe search, proxy, "
                "thread count, and more. Everything is configurable."
            ),
        },
    ]

    def _build_slide(s: dict) -> ft.Column:
        return ft.Column(
            [
                ft.Container(height=80),
                ft.Container(
                    content=ft.Icon(s["icon"], size=ICON_SIZE, color=s["color"]),
                    width=ICON_CONTAINER_SIZE,
                    height=ICON_CONTAINER_SIZE,
                    border_radius=60,
                    bgcolor=ft.Colors.with_opacity(0.1, s["color"]),
                    alignment=ft.alignment.Alignment(0, 0),
                ),
                ft.Container(height=32),
                ft.Text(
                    s["title"],
                    size=24,
                    weight=ft.FontWeight.BOLD,
                    text_align=ft.TextAlign.CENTER,
                    color=ft.Colors.ON_SURFACE,
                ),
                ft.Container(height=12),
                ft.Text(
                    s["body"],
                    size=14,
                    color=ft.Colors.with_opacity(0.7, ft.Colors.ON_SURFACE),
                    text_align=ft.TextAlign.CENTER,
                ),
            ],
            horizontal_alignment=ft.CrossAxisAlignment.CENTER,
            spacing=0,
        )

    def _build_indicators() -> list[ft.Container]:
        dots = []
        for i in range(len(slides)):
            dots.append(
                ft.Container(
                    width=10 if i == current_page["index"] else 6,
                    height=6,
                    border_radius=3,
                    bgcolor=ft.Colors.PRIMARY
                    if i == current_page["index"]
                    else ft.Colors.with_opacity(0.2, ft.Colors.ON_SURFACE),
                    animate=ft.Animation(200, "easeOut"),
                )
            )
        return dots

    button_ref = ft.Ref[ft.Button]()

    def _update():
        is_last = current_page["index"] == len(slides) - 1
        if slide_container.current:
            slide_container.current.content = _build_slide(
                slides[current_page["index"]]
            )
        if indicator_row.current:
            indicator_row.current.controls = _build_indicators()
        if button_ref.current:
            button_ref.current.content = ft.Text(
                "Get Started" if is_last else "Next",
                size=14,
                weight=ft.FontWeight.W_600,
            )
            button_ref.current.icon = (
                ft.Icons.CHECK_ROUNDED if is_last else ft.Icons.ARROW_FORWARD_ROUNDED
            )
        page.update()

    def on_next(e):
        is_last = current_page["index"] == len(slides) - 1
        if is_last:
            page.run_task(_finish)
        else:
            current_page["index"] += 1
            _update()

    def on_prev(e=None):
        if current_page["index"] > 0:
            current_page["index"] -= 1
            _update()

    def on_swipe(e: ft.DragEndEvent):
        if e.primary_velocity is not None:
            if e.primary_velocity < -200:
                on_next(e)
            elif e.primary_velocity > 200:
                on_prev()

    def on_skip(e):
        page.run_task(_finish)

    async def _finish():
        if storage:
            await storage.set_onboarding_done(True)
        on_done()

    is_last = current_page["index"] == len(slides) - 1

    view = ft.View(
        route="/onboarding",
        controls=[
            ft.SafeArea(
                ft.Container(
                    content=ft.Column(
                        [
                            ft.Row(
                                [
                                    ft.TextButton(
                                        "Skip",
                                        on_click=on_skip,
                                        style=ft.ButtonStyle(
                                            color=ft.Colors.with_opacity(
                                                0.6, ft.Colors.ON_SURFACE
                                            )
                                        ),
                                    ),
                                ],
                                alignment=ft.MainAxisAlignment.END,
                            ),
                            ft.GestureDetector(
                                content=ft.Container(
                                    ref=slide_container,
                                    content=_build_slide(slides[0]),
                                    expand=True,
                                    padding=ft.Padding(32, 0, 32, 0),
                                ),
                                on_horizontal_drag_end=on_swipe,
                            ),
                            ft.Row(
                                ref=indicator_row,
                                controls=_build_indicators(),
                                alignment=ft.MainAxisAlignment.CENTER,
                                spacing=6,
                            ),
                            ft.Container(height=32),
                            ft.Container(
                                content=ft.Button(
                                    ref=button_ref,
                                    content=ft.Text(
                                        "Get Started" if is_last else "Next",
                                        size=14,
                                        weight=ft.FontWeight.W_600,
                                    ),
                                    icon=ft.Icons.ARROW_FORWARD_ROUNDED,
                                    on_click=on_next,
                                    width=200,
                                    height=48,
                                    style=ft.ButtonStyle(
                                        bgcolor=ft.Colors.PRIMARY,
                                        color=ft.Colors.WHITE,
                                        shape=ft.RoundedRectangleBorder(radius=24),
                                    ),
                                ),
                                alignment=ft.alignment.Alignment(0, 0),
                            ),
                            ft.Container(height=48),
                        ],
                        expand=True,
                        spacing=0,
                    ),
                    gradient=ft.LinearGradient(
                        begin=ft.alignment.Alignment(-1, -1),
                        end=ft.alignment.Alignment(1, 1),
                        colors=[
                            ft.Colors.SURFACE,
                            ft.Colors.with_opacity(0.08, ft.Colors.PRIMARY),
                        ],
                    ),
                    expand=True,
                ),
                expand=True,
            )
        ],
        padding=0,
        spacing=0,
    )

    return view
