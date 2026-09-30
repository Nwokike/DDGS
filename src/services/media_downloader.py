"""Media downloader - streams video/image bytes with ``primp`` (no new deps).

Uses ``primp``'s async client with browser impersonation so it can fetch from
sites that otherwise block automated requests (the same approach used to pull
from animepahe-style hosts). Falls back gracefully when a URL is not actually a
media file.
"""

from __future__ import annotations

import asyncio
import logging
import os
import urllib.parse

import primp

from services.net_clients import primp_kwargs
from slugify import slugify

logger = logging.getLogger(__name__)

DEFAULT_IMPERSONATE = "chrome_153"
_CHUNK = 1 << 16  # 64 KiB


class NotMediaError(Exception):
    """Raised when a download attempt returned a non-media (e.g. HTML) response."""


class DownloadCancelled(Exception):
    """Raised when the user cancels an in-progress download."""


def sanitize_filename(name: str, ext: str) -> str:
    """Build a safe file name from a title + extension (plan D8).

    python-slugify transliterates unicode through text-unidecode, so an
    international title becomes readable ASCII on every filesystem
    instead of whatever the old character-class regex left behind.
    """
    slug = slugify(
        name or "download",
        max_length=64,
        word_boundary=True,
        save_order=True,
    )
    if not slug:
        slug = "download"
    if not ext.startswith("."):
        ext = "." + ext
    return f"{slug}{ext}"


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
    # One fresh-profile retry on an anti-bot block (audit A2): the pinned
    # chrome_153 ages out of credibility while "random" tracks current
    # releases. Only the pre-flight GET can retry - once writing starts,
    # a failure is terminal (the cleanup below owns the partial file).
    profiles = [impersonate]
    if impersonate != "random":
        profiles.append("random")
    for profile in profiles:
        try:
            async with primp.AsyncClient(
                impersonate=profile,
                follow_redirects=True,
                timeout=timeout,
                connect_timeout=10.0,
                **primp_kwargs(),
            ) as client:
                r = await client.get(
                    url,
                    headers=headers or None,
                    stream=True,
                    follow_redirects=True,
                )
                r.raise_for_status()

                ctype = (r.headers.get("content-type") or "").lower()
                if expect_media and ctype.startswith("text/html"):
                    raise NotMediaError(
                        f"Response is not a media file (content-type: {ctype or 'unknown'})"
                    )

                total = _safe_int(r.headers.get("content-length"))
                completed = False
                try:
                    f = await asyncio.to_thread(open, dest, "wb")
                    try:
                        async for chunk in r.aiter_bytes(chunk_size):
                            if not chunk:
                                continue
                            if cancel_event is not None and cancel_event.is_set():
                                raise DownloadCancelled()
                            await asyncio.to_thread(f.write, chunk)
                            written += len(chunk)
                            if on_progress is not None:
                                on_progress(written, total)
                    finally:
                        await asyncio.to_thread(f.close)
                    completed = True
                except BaseException:
                    # Every failure, not just a cancel: a network drop mid-transfer
                    # or a full disk used to leave a truncated file behind while the
                    # UI reported the download failed. Nothing half-written is worth
                    # keeping.
                    if not completed:
                        try:
                            os.remove(dest)
                        except OSError:
                            pass
                    raise
            # Success: the file is fully written and closed. Return HERE -
            # falling through used to loop to the next profile, download
            # the file a second time, and then raise "the download was
            # refused" as if nothing had been saved (the return lived as
            # dead code after the loop's raise).
            logger.info("Downloaded %d bytes to %s", written, dest)
            return written
        except primp.StatusError as exc:
            # primp errors are NOT builtins (PrimpError, not OSError), so
            # they used to escape every caller's handler: map them to plain
            # RuntimeError with honest text instead of a repr.
            code = getattr(exc, "status_code", 0)
            if code in (403, 429) and profile != profiles[-1]:
                logger.info(
                    "HTTP %d on a fresh download; retrying with profile %r",
                    code,
                    profile,
                )
                continue
            raise RuntimeError(
                f"the server refused the download (HTTP {code})"
            ) from exc
        except primp.TimeoutError as exc:
            raise RuntimeError("the download timed out") from exc
        except primp.PrimpError as exc:
            raise RuntimeError(f"download failed: {exc}") from exc
    raise RuntimeError("the download was refused")  # profiles exhausted


def _safe_int(value) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None
