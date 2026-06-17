"""Onboarding view — first-run experience."""

from __future__ import annotations

from typing import Callable

import flet as ft

from core.theme import AppColors
from core.tokens import (
    FONT_SM,
    FONT_MD,
    FONT_LG,
    FONT_XXL,
    SPACING_XS,
    SPACING_MD,
    SPACING_XL,
    BORDER_RADIUS_LG,
    ICON_LG,
    ICON_XL,
)
from core.utils import logger
from services.storage_service import StorageService

LOG_TAG = "OnboardingView"


def build_onboarding_view(
    page: ft.Page, on_done: Callable, storage: StorageService
) -> ft.View:
    logger.info(f"[{LOG_TAG}] Building onboarding")

    async def finish(e):
        await storage.set_onboarding_done(True)
        logger.info(f"[{LOG_TAG}] Onboarding done")
        on_done()

    features = [
        (
            ft.Icons.TRAVEL_EXPLORE_ROUNDED,
            "Metasearch",
            "Search across 14 engines — DuckDuckGo, Google, Bing, Brave, Yahoo, Yandex, Wikipedia, and more.",
        ),
        (
            ft.Icons.IMAGE_ROUNDED,
            "Images & Videos",
            "Find images, videos, news, and books in one place.",
        ),
        (
            ft.Icons.DOWNLOAD_ROUNDED,
            "Page Extraction",
            "Extract any webpage as Markdown, plain text, HTML, or raw content.",
        ),
        (
            ft.Icons.TUNE_ROUNDED,
            "Full Control",
            "Backend selection, time filters, safe search, proxy, threads — everything configurable.",
        ),
    ]

    cards = []
    for icon, title, desc in features:
        cards.append(
            ft.Container(
                content=ft.Row(
                    controls=[
                        ft.Container(
                            content=ft.Icon(
                                icon, size=ICON_LG, color=AppColors.PRIMARY
                            ),
                            padding=ft.Padding(
                                left=SPACING_MD,
                                top=SPACING_MD,
                                right=SPACING_MD,
                                bottom=SPACING_MD,
                            ),
                            bgcolor=AppColors.PRIMARY_LIGHT,
                            border_radius=BORDER_RADIUS_LG,
                        ),
                        ft.Column(
                            controls=[
                                ft.Text(
                                    title, size=FONT_MD, weight=ft.FontWeight.W_600
                                ),
                                ft.Text(
                                    desc,
                                    size=FONT_SM,
                                    color=ft.Colors.ON_SURFACE_VARIANT,
                                ),
                            ],
                            spacing=SPACING_XS,
                            expand=True,
                        ),
                    ],
                    spacing=SPACING_MD,
                ),
                padding=ft.Padding(
                    left=SPACING_MD, top=SPACING_MD, right=SPACING_MD, bottom=SPACING_MD
                ),
                border_radius=BORDER_RADIUS_LG,
                bgcolor=AppColors.SURFACE,
            )
        )

    content = ft.SafeArea(
        content=ft.Column(
            controls=[
                ft.Container(expand=True),
                ft.Container(
                    content=ft.Column(
                        controls=[
                            ft.Icon(
                                ft.Icons.TRAVEL_EXPLORE_ROUNDED,
                                size=ICON_XL * 3,
                                color=AppColors.PRIMARY,
                            ),
                            ft.Text(
                                "DDGS",
                                size=FONT_XXL,
                                weight=ft.FontWeight.BOLD,
                                color=AppColors.PRIMARY,
                            ),
                            ft.Text(
                                "Dux Distributed Global Search",
                                size=FONT_LG,
                                color=ft.Colors.ON_SURFACE_VARIANT,
                            ),
                        ],
                        horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                        spacing=SPACING_XS,
                    ),
                    padding=ft.Padding(left=0, top=0, right=0, bottom=SPACING_XL),
                ),
                ft.Column(controls=cards, spacing=SPACING_MD),
                ft.Container(expand=True),
                ft.Container(
                    content=ft.FilledButton(
                        content=ft.Text(
                            "Get Started", size=FONT_LG, weight=ft.FontWeight.W_600
                        ),
                        on_click=finish,
                        style=ft.ButtonStyle(
                            shape=ft.RoundedRectangleBorder(radius=BORDER_RADIUS_LG),
                            padding=ft.Padding(
                                left=SPACING_XL * 2,
                                top=SPACING_MD,
                                right=SPACING_XL * 2,
                                bottom=SPACING_MD,
                            ),
                        ),
                    ),
                    padding=ft.Padding(left=0, top=0, right=0, bottom=SPACING_XL),
                    alignment=ft.alignment.Alignment(0, 0),
                ),
            ],
            horizontal_alignment=ft.CrossAxisAlignment.CENTER,
            spacing=SPACING_MD,
        )
    )

    return ft.View(
        route="/onboarding",
        controls=[content],
        padding=0,
        spacing=0,
        bgcolor=AppColors.BACKGROUND,
    )
