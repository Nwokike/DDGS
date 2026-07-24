"""Media downloader — streams video/image bytes with ``primp`` (no new deps).

Uses ``primp``'s async client with browser impersonation so it can fetch from
sites that otherwise block automated requests (the same approach used to pull
from animepahe-style hosts). Falls back gracefully when a URL is not actually a
media file.
"""

from __future__ import annotations

import asyncio
import logging
import os
import re
import urllib.parse

import primp

logger = logging.getLogger(__name__)

DEFAULT_IMPERSONATE = "chrome_146"
_CHUNK = 1 << 16  # 64 KiB


class NotMediaError(Exception):
    """Raised when a download attempt returned a non-media (e.g. HTML) response."""


class DownloadCancelled(Exception):
    """Raised when the user cancels an in-progress download."""


def sanitize_filename(name: str, ext: str) -> str:
    """Build a safe file name from a title + extension."""
    if not name:
        name = "download"
    name = re.sub(r'[\\/:*?"<>|\r\n\t]+', "_", name).strip().strip(".")
    if not name:
        name = "download"
    # Drop an existing trailing extension (e.g. "My Clip.mp4") so we don't
    # end up with "My Clip.mp4.mp4".
    if "." in name:
        head, _, tail = name.rpartition(".")
        if 1 <= len(tail) <= 5 and tail.isalnum():
            name = head
    if not ext.startswith("."):
        ext = "." + ext
    return f"{name}{ext}"


def ext_from_url(url: str, default: str = "bin") -> str:
    """Extract a file extension from a URL path, or return ``default``."""
    try:
        path = urllib.parse.urlparse(url).path
    except (ValueError, TypeError, OSError, RuntimeError, ConnectionError, ImportError):
        path = ""
    last = path.rsplit("/", 1)[-1]
    if "." in last:
        ext = last.rsplit(".", 1)[-1].lower()
        if 1 <= len(ext) <= 5:
            return ext
    return default


async def download_media(
    url: str,
    dest: str,
    *,
    impersonate: str = DEFAULT_IMPERSONATE,
    timeout: float = 60.0,
    referer: str | None = None,
    expect_media: bool = False,
    chunk_size: int = _CHUNK,
    cancel_event: asyncio.Event | None = None,
    on_progress=None,
) -> int:
    """Stream ``url`` to ``dest`` and return bytes written.

    Uses ``primp`` (browser impersonation + redirects). If ``expect_media`` is
    True and the response is HTML, raises ``NotMediaError`` so the caller can
    fall back gracefully. ``on_progress(written, total)`` is called as chunks
    are written (``total`` is ``None`` when the size is unknown). If
    ``cancel_event`` is set mid-download, raises ``DownloadCancelled`` after
    removing the partial file.
    """
    headers = {}
    if referer:
        headers["Referer"] = referer

    written = 0
    async with primp.AsyncClient(
        impersonate=impersonate, follow_redirects=True, timeout=timeout
    ) as client:
        r = await client.get(
            url, headers=headers or None, stream=True, follow_redirects=True
        )
        r.raise_for_status()

        ctype = (r.headers.get("content-type") or "").lower()
        if expect_media and ctype.startswith("text/html"):
            raise NotMediaError(
                f"Response is not a media file (content-type: {ctype or 'unknown'})"
            )

        total = _safe_int(r.headers.get("content-length"))
        try:
            with open(dest, "wb") as f:
                async for chunk in r.aiter_bytes(chunk_size):
                    if not chunk:
                        continue
                    if cancel_event is not None and cancel_event.is_set():
                        raise DownloadCancelled()
                    f.write(chunk)
                    written += len(chunk)
                    if on_progress is not None:
                        on_progress(written, total)
        except DownloadCancelled:
            # Remove the partial file so we don't leave a broken download behind.
            try:
                os.remove(dest)
            except OSError:
                pass
            raise

    logger.info("Downloaded %d bytes to %s", written, dest)
    return written


def _safe_int(value) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None
