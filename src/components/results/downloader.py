from __future__ import annotations

import asyncio
import os
import time

import flet as ft

from core import tokens
from core.state import SearchResult, state
from core.theme import AppColors
from services.media_downloader import (
    DownloadCancelled,
    NotMediaError,
    download_media,
    ext_from_url,
    sanitize_filename,
)
from services.youtube import is_youtube_url, resolve_youtube


def _human_bytes(n: int) -> str:
    """Format a byte count as a human-readable string (e.g. '14.0 MB')."""
    size = float(n)
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if size < 1024 or unit == "TB":
            if unit == "B":
                return f"{int(size)} B"
            return f"{size:.1f} {unit}"
        size /= 1024
    return f"{size:.1f} PB"


async def launch_url(url: str, page: ft.Page | None = None):
    """Open a URL in the system browser. Works on mobile + desktop."""
    if not url:
        return
    try:
        await ft.UrlLauncher().launch_url(url)
    except (
        ValueError,
        TypeError,
        OSError,
        RuntimeError,
        ConnectionError,
        ImportError,
        KeyError,
        IndexError,
        AttributeError,
        TimeoutError,
    ):
        import webbrowser

        webbrowser.open(url)


async def _resolve_save_path(page: ft.Page, default_name: str) -> str | None:
    """Resolve destination file save path with native dialog across all platforms and auto-fallback."""
    file_picker = getattr(page, "file_picker", None)
    if not file_picker:
        file_picker = ft.FilePicker()
        page.services.append(file_picker)
        page.update()

    path: str | None = None
    try:
        path = await file_picker.save_file(
            dialog_title=f"Save {default_name}",
            file_name=default_name,
        )
    except (ValueError, TypeError, OSError, RuntimeError, AttributeError):
        path = None

    if not path:
        is_mobile = page.platform in (
            ft.PagePlatform.ANDROID,
            getattr(ft.PagePlatform, "ANDROID_TV", ft.PagePlatform.ANDROID),
            ft.PagePlatform.IOS,
        )
        if is_mobile:
            dl_dir = "/storage/emulated/0/Download"
            if not os.path.exists(dl_dir):
                dl_dir = os.path.join(os.path.expanduser("~"), "Downloads")
        else:
            dl_dir = os.path.join(os.path.expanduser("~"), "Downloads")

        os.makedirs(dl_dir, exist_ok=True)
        name_part, ext_part = os.path.splitext(default_name)
        counter = 1
        unique_name = default_name
        while os.path.exists(os.path.join(dl_dir, unique_name)):
            unique_name = f"{name_part} ({counter}){ext_part}"
            counter += 1
        path = os.path.join(dl_dir, unique_name)

    return path


def _show_feedback(page: ft.Page, title: str, message: str, is_error: bool = False):
    """Display a clear, prominent completion/error dialog on both mobile and desktop screens."""
    icon = ft.Icons.CHECK_CIRCLE_ROUNDED if not is_error else ft.Icons.ERROR_OUTLINED
    icon_color = AppColors.SUCCESS if not is_error else AppColors.ERROR
    dlg = ft.AlertDialog(
        modal=False,
        title=ft.Row(
            [
                ft.Icon(icon, color=icon_color, size=24),
                ft.Text(
                    title,
                    size=tokens.FONT_MD,
                    font_family="Outfit",
                    weight=ft.FontWeight.BOLD,
                ),
            ],
            spacing=tokens.SPACE_XS,
        ),
        content=ft.Text(
            message,
            size=tokens.FONT_SM,
            selectable=True,
            style=ft.TextStyle(height=1.4),
        ),
        actions=[
            ft.FilledButton(
                "OK",
                on_click=lambda e: page.pop_dialog(),
                style=ft.ButtonStyle(bgcolor=AppColors.PRIMARY, color=ft.Colors.WHITE),
            )
        ],
        actions_alignment=ft.MainAxisAlignment.END,
    )
    page.show_dialog(dlg)
    page.update()


async def _download_media(page: ft.Page, result: SearchResult, search_type: str):
    file_picker = getattr(page, "file_picker", None)
    if not file_picker:
        file_picker = ft.FilePicker()
        page.services.append(file_picker)
        page.update()

    is_image = search_type == "images"
    is_video = search_type == "videos"

    if is_image:
        media_url = result.image_url or result.url
        ext = ext_from_url(media_url, "jpg")
    elif is_video:
        media_url = result.url
        ext = "mp4"
        if is_youtube_url(media_url):
            try:
                stream = await resolve_youtube(
                    media_url,
                    preferred_quality=getattr(state, "video_quality", "best") or "best",
                )
                if stream:
                    media_url = stream.url
                    ext = stream.ext
            except (
                ValueError,
                TypeError,
                OSError,
                RuntimeError,
                ConnectionError,
                ImportError,
            ) as _ex:
                __import__("logging").getLogger("app").debug(f"Ignored: {_ex}")
    else:
        media_url = result.url
        ext = ext_from_url(media_url, "html")

    default_name = sanitize_filename(result.title or "download", ext)

    path = await _resolve_save_path(page, default_name)
    if not path:
        return

    prog_bar = ft.ProgressBar(
        color=AppColors.PRIMARY,
        bgcolor=ft.Colors.with_opacity(0.12, AppColors.PRIMARY),
    )
    prog_text = ft.Text(
        "Starting download…",
        size=tokens.FONT_XS,
        color=ft.Colors.ON_SURFACE_VARIANT,
    )
    cancel_event = asyncio.Event()

    def _cancel():
        cancel_event.set()
        page.pop_dialog()

    dlg = ft.AlertDialog(
        modal=True,
        title=ft.Text(
            f"Downloading {default_name}",
            size=tokens.FONT_SM,
            font_family="Outfit",
        ),
        content=ft.Column(
            [
                prog_bar,
                prog_text,
                ft.Row(
                    [ft.TextButton("Cancel", on_click=lambda e: _cancel())],
                    alignment=ft.MainAxisAlignment.END,
                ),
            ],
            spacing=tokens.SPACE_SM,
            tight=True,
        ),
    )

    page.show_dialog(dlg)
    page.update()

    written = 0
    last_update = 0.0

    def _on_progress(w, total=None):
        nonlocal written, last_update
        written = w
        if total:
            prog_bar.value = min(w / total, 1.0)
            prog_text.value = f"{_human_bytes(w)} / {_human_bytes(total)}"
        else:
            prog_text.value = f"{_human_bytes(w)} downloaded"
        now = time.monotonic()
        if now - last_update >= 0.2:
            last_update = now
            page.update()

    try:
        if is_video:
            await download_media(
                media_url,
                path,
                referer=result.url,
                expect_media=True,
                cancel_event=cancel_event,
                on_progress=_on_progress,
            )
        else:
            await download_media(
                media_url,
                path,
                referer=result.url,
                cancel_event=cancel_event,
                on_progress=_on_progress,
            )
        page.pop_dialog()
        page.update()
        if getattr(state, "ad_service", None):
            try:
                await state.ad_service.show_interstitial()
            except (
                ValueError,
                TypeError,
                OSError,
                RuntimeError,
                ConnectionError,
                ImportError,
                AttributeError,
            ) as _ex:
                __import__("logging").getLogger("app").debug(
                    f"Ad display ignored: {_ex}"
                )
        _show_feedback(
            page,
            "Download Complete",
            f"File successfully saved to:\n\n{path}",
            is_error=False,
        )
    except NotMediaError:
        page.pop_dialog()
        page.update()
        _show_feedback(
            page,
            "Download Unavailable",
            "Can't download this source directly — open in browser instead.",
            is_error=True,
        )
    except DownloadCancelled:
        page.pop_dialog()
        page.update()
        _show_feedback(
            page, "Download Cancelled", "Download was cancelled.", is_error=True
        )
    except (
        ValueError,
        TypeError,
        OSError,
        RuntimeError,
        ConnectionError,
        ImportError,
    ) as ex:
        page.pop_dialog()
        page.update()
        _show_feedback(
            page, "Download Failed", f"Failed to download: {ex}", is_error=True
        )


async def _save_text_content(page: ft.Page, text: str, default_name: str):
    path = await _resolve_save_path(page, default_name)
    if path:
        try:
            await asyncio.to_thread(
                lambda: (
                    __import__("pathlib").Path(path).write_text(text, encoding="utf-8")
                )
            )
            _show_feedback(
                page,
                "File Saved",
                f"File successfully saved to:\n\n{path}",
                is_error=False,
            )
        except (
            ValueError,
            TypeError,
            OSError,
            RuntimeError,
            ConnectionError,
            ImportError,
        ) as ex:
            _show_feedback(
                page, "Save Failed", f"Failed to save file: {ex}", is_error=True
            )


async def _save_bytes_content(page: ft.Page, data: bytes, default_name: str):
    path = await _resolve_save_path(page, default_name)
    if path:
        try:
            await asyncio.to_thread(
                lambda: __import__("pathlib").Path(path).write_bytes(data)
            )
            _show_feedback(
                page,
                "File Saved",
                f"File successfully saved to:\n\n{path}",
                is_error=False,
            )
        except (
            ValueError,
            TypeError,
            OSError,
            RuntimeError,
            ConnectionError,
            ImportError,
        ) as ex:
            _show_feedback(
                page, "Save Failed", f"Failed to save file: {ex}", is_error=True
            )
