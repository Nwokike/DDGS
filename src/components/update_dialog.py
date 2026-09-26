"""Update dialog - two modes, one honest destination per channel.

Modes (KTV Player's shape):
- Update available: server release notes with launch buttons. The play
  channel offers Google Play only (Play safe-link policy: a store build
  never points at another store). A direct build offers the GitHub release
  only: the Play edition is a different feature set, so an update dialog
  must not migrate the user across channels.
- Up to date: the installed version plus a live re-check. Nothing is
  fabricated: the dialog never announces a version the feed did not.

Delivery is deliberately browser-based: URLs launch externally; there is
no in-app download or install.
"""

from __future__ import annotations

import asyncio

import flet as ft

from components.results.downloader import launch_url
from core.build_channel import CHANNEL
from core.theme import AppColors


def _dismiss(page: ft.Page, e=None) -> None:
    try:
        page.pop_dialog()
    except Exception:
        pass


def _show_up_to_date(page: ft.Page) -> None:
    """The 'You're up to date' mode: installed version, bundled changelog,
    live re-check (KTV Player's second mode)."""
    from components.settings.version import _APP_VERSION as version
    from core.changelog import notes_for

    async def _recheck() -> None:
        from services.update_service import UpdateService

        _dismiss(page)
        try:
            result = await UpdateService().check_for_update()
        except Exception:
            result = None
        if result:
            from core.state import state

            state.update_available = True
            state.update_data = result
            show_update_dialog(page, result)
            return
        try:
            page.show_dialog(
                ft.SnackBar(ft.Text(f"You're up to date on v{version}"))
            )
        except Exception:
            pass

    notes = notes_for(version)
    body_controls: list[ft.Control] = [
        ft.Text(f"Latest version · v{version}", size=13),
    ]
    if notes:
        body_controls.extend(
            [
                ft.Text("What's New:", size=13, weight=ft.FontWeight.W_600),
                ft.Markdown(
                    notes,
                    selectable=True,
                    extension_set=ft.MarkdownExtensionSet.GITHUB_WEB,
                ),
            ]
        )
    dlg = ft.AlertDialog(
        title=ft.Row(
            [
                ft.Icon(ft.Icons.VERIFIED_ROUNDED, color=AppColors.PRIMARY, size=24),
                ft.Text(
                    "You're up to date",
                    size=14,
                    weight=ft.FontWeight.BOLD,
                    font_family="Outfit",
                ),
            ],
            spacing=8,
        ),
        content=ft.Container(
            content=ft.Column(
                body_controls,
                spacing=8,
                tight=True,
                scroll=ft.ScrollMode.AUTO,
            ),
            width=360,
        ),
        actions=[
            ft.OutlinedButton(
                content=ft.Text("Check for Updates", font_family="Outfit"),
                icon=ft.Icons.SYNC_ROUNDED,
                on_click=lambda e: page.run_task(_recheck),
            ),
            ft.TextButton("Close", on_click=lambda e: _dismiss(page)),
        ],
        actions_alignment=ft.MainAxisAlignment.END,
    )
    page.show_dialog(dlg)


def show_update_dialog(page: ft.Page, update_data: dict | None) -> None:
    if not page:
        return
    if not update_data:
        _show_up_to_date(page)
        return
    update_data = dict(update_data)
    is_mandatory = bool(update_data.get("mandatory", False))
    is_announcement = update_data.get("type") == "announcement"
    title_text = update_data.get(
        "title",
        "Announcement"
        if is_announcement
        else f"New Version {update_data.get('version', '')} Available!",
    )
    release_notes = update_data.get("release_notes", "")
    github_url = update_data.get("github_url", "")
    playstore_url = update_data.get("playstore_url", "")
    action_url = update_data.get("action_url") or github_url
    is_android = page.platform == ft.PagePlatform.ANDROID

    def _dismiss_self(e):
        _dismiss(page, e)

    actions: list[ft.Control] = []
    if is_announcement:
        if action_url:
            actions.append(
                ft.FilledButton(
                    content=ft.Text(
                        "Learn More", weight=ft.FontWeight.W_600, color=ft.Colors.WHITE
                    ),
                    icon=ft.Icons.OPEN_IN_NEW_ROUNDED,
                    action=ft.OpenUrl(action_url),
                    on_click=_dismiss_self,
                )
            )
    elif CHANNEL == "play":
        # Play safe-link policy: the store is the only destination inside a
        # Play-distributed build. No GitHub button, no feature notes.
        if playstore_url:
            actions.append(
                ft.FilledButton(
                    content=ft.Text(
                        "Google Play",
                        weight=ft.FontWeight.W_600,
                        color=ft.Colors.WHITE,
                    ),
                    icon=ft.Icons.SHOP_ROUNDED,
                    action=ft.OpenUrl(playstore_url),
                    on_click=_dismiss_self,
                )
            )
    else:
        # Direct build: GitHub is the only path that keeps this build's
        # feature set.
        if github_url:
            actions.append(
                ft.FilledButton(
                    content=ft.Text(
                        "Direct APK (GitHub)" if is_android else "Download from GitHub",
                        weight=ft.FontWeight.W_600,
                        color=ft.Colors.WHITE,
                    ),
                    icon=ft.Icons.DOWNLOAD_ROUNDED,
                    action=ft.OpenUrl(github_url),
                    on_click=_dismiss_self,
                )
            )
    if not is_mandatory:
        actions.append(
            ft.TextButton(
                "Later",
                on_click=_dismiss_self,
                style=ft.ButtonStyle(
                    color=ft.Colors.with_opacity(0.5, ft.Colors.ON_SURFACE)
                ),
            )
        )
    content_controls: list[ft.Control] = []
    if not is_announcement and update_data.get("version"):
        content_controls.append(
            ft.Text(
                f"Version {update_data['version']} is now available.",
                size=12,
                color=ft.Colors.ON_SURFACE,
                weight=ft.FontWeight.W_500,
            )
        )
        content_controls.append(ft.Container(height=8))
    if release_notes:
        if not is_announcement:
            content_controls.extend(
                [
                    ft.Text(
                        "What's New:",
                        size=12,
                        weight=ft.FontWeight.W_600,
                        color=AppColors.PRIMARY,
                    ),
                    ft.Container(height=4),
                ]
            )
        content_controls.append(
            ft.Markdown(
                release_notes,
                selectable=True,
                extension_set=ft.MarkdownExtensionSet.GITHUB_WEB,
                on_tap_link=lambda e: asyncio.create_task(
                    launch_url(e.data, page)
                ),
            )
        )
    icon_data = (
        ft.Icons.CAMPAIGN_ROUNDED if is_announcement else ft.Icons.ROCKET_LAUNCH_ROUNDED
    )
    icon_color = AppColors.ACCENT if is_announcement else AppColors.PRIMARY
    dlg = ft.AlertDialog(
        modal=is_mandatory,
        title=ft.Row(
            [
                ft.Icon(icon_data, color=icon_color, size=24),
                ft.Text(
                    title_text,
                    size=14,
                    weight=ft.FontWeight.BOLD,
                    font_family="Outfit",
                    expand=True,
                ),
            ],
            spacing=8,
        ),
        content=ft.Container(
            content=ft.Column(
                controls=content_controls,
                tight=True,
                spacing=0,
                scroll=ft.ScrollMode.AUTO,
            ),
            width=360,
        ),
        actions=actions,
        actions_alignment=ft.MainAxisAlignment.END,
    )
    page.show_dialog(dlg)
