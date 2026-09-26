"""File operations for the DDGS AI agent.

Lets the agent do what the app does, on the user's behalf: save any page as
Markdown/HTML/text into Downloads/DDGS, download media (including YouTube via
the built-in resolver), and crawl a site saving every page it finds. Shared by
chat tools and the scheduled-scrape runner.
"""

from __future__ import annotations

import asyncio
import logging
import os
import re
import time
from urllib.parse import urljoin, urlparse

logger = logging.getLogger(__name__)

DIR_NAME = "DDGS"
MAX_CRAWL_PAGES = 8
FETCH_TIMEOUT = 25.0
DL_TIMEOUT = 180.0


def default_save_dir() -> str:
    """Downloads/DDGS on mobile, ~/Downloads/DDGS on desktop."""
    mobile_dl = "/storage/emulated/0/Download"
    if os.path.exists(mobile_dl):
        base = mobile_dl
    else:
        base = os.path.join(os.path.expanduser("~"), "Downloads")
    directory = os.path.join(base, DIR_NAME)
    os.makedirs(directory, exist_ok=True)
    return directory


def unique_path(directory: str, filename: str) -> str:
    name, ext = os.path.splitext(filename)
    candidate = os.path.join(directory, filename)
    counter = 1
    while os.path.exists(candidate):
        candidate = os.path.join(directory, f"{name} ({counter}){ext}")
        counter += 1
    return candidate


def _slug(url: str) -> str:
    host = urlparse(url).netloc.removeprefix("www.") or "page"
    slug = re.sub(r"[^A-Za-z0-9._-]+", "-", host).strip("-")[:48]
    stamp = time.strftime("%Y%m%d-%H%M%S")
    return f"{slug}-{stamp}" if slug else f"page-{stamp}"


def _write_text(path: str, text: str) -> None:
    with open(path, "w", encoding="utf-8") as f:
        f.write(text)


FORMAT_EXT = {
    "text_markdown": ".md",
    "text": ".html",
    "text_rich": ".html",
    "text_plain": ".txt",
    "content": ".bin",
}


async def save_page(url: str, fmt: str = "text_markdown", svc=None) -> str:
    """Extract one URL and write it to Downloads/DDGS. Returns the path."""
    if svc is None:
        from services.search_service import SearchService

        svc = SearchService()
    res, err = await asyncio.wait_for(svc.extract_url(url, fmt=fmt), FETCH_TIMEOUT)
    content = str((res or {}).get("content") or "")
    if not content.strip():
        raise RuntimeError(err or "page had no extractable content")
    ext = FORMAT_EXT.get(fmt, ".md")
    path = unique_path(default_save_dir(), _slug(url) + ext)
    await asyncio.to_thread(_write_text, path, content)
    logger.info("Agent saved page %s -> %s", url, path)
    return path


def extract_links(html: str, base: str, same_host: bool = True, limit: int = 200) -> list[str]:
    """Pull http(s) links out of raw HTML (lxml is already shipped via ddgs)."""
    from lxml import html as lxml_html

    try:
        tree = lxml_html.fromstring(html)
    except Exception as exc:
        logger.warning("link parse failed for %s: %r", base, exc)
        return []
    base_host = urlparse(base).netloc
    out: list[str] = []
    seen: set[str] = set()
    for href in tree.xpath("//a/@href"):
        try:
            u = urljoin(base, (href or "").strip())
        except ValueError:
            continue
        parsed = urlparse(u)
        if parsed.scheme not in ("http", "https"):
            continue
        if same_host and parsed.netloc != base_host:
            continue
        if u in seen:
            continue
        seen.add(u)
        out.append(u)
        if len(out) >= limit:
            break
    return out


async def scrape_site(
    url: str, max_pages: int = 5, fmt: str = "text_markdown", svc=None
) -> dict:
    """Crawl `url` + same-host links (cap `max_pages`) and save each page."""
    if svc is None:
        from services.search_service import SearchService

        svc = SearchService()
    max_pages = max(1, min(int(max_pages or 5), MAX_CRAWL_PAGES))
    raw, err = await asyncio.wait_for(svc.extract_url(url, fmt="text"), FETCH_TIMEOUT)
    if not raw:
        raise RuntimeError(err or "could not fetch site")
    links = [url]
    for candidate in extract_links(
        str(raw.get("content") or ""), url, same_host=True, limit=max_pages * 3
    ):
        if len(links) >= max_pages:
            break
        if candidate.rstrip("/") != url.rstrip("/"):
            links.append(candidate)
    saved: list[str] = []
    failed: list[str] = []
    for link in links:
        try:
            saved.append(await save_page(link, fmt=fmt, svc=svc))
        except Exception as exc:
            logger.info("crawl skip %s: %r", link, exc)
            failed.append(link)
    logger.info("Agent crawled %s: %d saved, %d failed", url, len(saved), len(failed))
    return {
        "url": url,
        "pages_attempted": len(links),
        "saved": saved,
        "failed": failed,
    }


async def download_media(url: str, quality: str = "best", svc=None) -> str:
    """Download a video (YouTube resolved) or image/direct media to Downloads/DDGS."""
    from services.media_downloader import download_media as _dl
    from services.media_downloader import ext_from_url
    from services.youtube.format_parser import is_youtube_url

    ext = "bin"
    if is_youtube_url(url):
        from services.youtube.innertube_client import resolve_youtube

        stream = await asyncio.wait_for(
            resolve_youtube(url, preferred_quality=quality or "best"), FETCH_TIMEOUT * 2
        )
        if not stream:
            raise RuntimeError("could not resolve the YouTube video")
        url = stream.url
        ext = stream.ext or "mp4"
        # The quality lands in the file name (and in the tool's outcome
        # line), so a 1080p request that honestly downgraded to a muxed
        # 360p stream says so instead of hiding it.
        stem = f"youtube-{stream.quality_label or 'video'}-{int(time.time()) % 100000}"
    else:
        ext = ext_from_url(url, "mp4")
        stem = f"media-{int(time.time()) % 100000}"
    dest = unique_path(default_save_dir(), f"{stem}.{ext}")
    written = await asyncio.wait_for(
        _dl(url, dest, referer=None, expect_media=False), DL_TIMEOUT
    )
    if written <= 0:
        raise RuntimeError("download produced no data")
    logger.info("Agent downloaded %s -> %s (%d bytes)", url, dest, written)
    return dest
