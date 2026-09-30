"""Link-scheme guards (utilization plan A4).

Markdown link taps arrive from untrusted content (scraped pages, model
replies). The rules: only http(s) may be fetched in-app, only http(s)/
mailto may ever reach a launcher, and the guard runs AFTER urljoin -
because urljoin happily preserves foreign schemes like javascript:.
"""

from __future__ import annotations

import asyncio
import sys
import webbrowser
from pathlib import Path

SRC = Path(__file__).resolve().parents[1] / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))


def test_scheme_helpers():
    from core.utils import is_launchable_url, is_web_url

    assert is_web_url("https://a.example/x")
    assert is_web_url("HTTP://a.example")  # scheme case-insensitive
    assert not is_web_url("javascript:alert(1)")
    assert not is_web_url("file:///etc/passwd")
    assert not is_web_url("data:text/html,<script>")
    assert not is_web_url("ftp://a.example/f")
    assert not is_web_url("")
    assert not is_web_url(None)  # type: ignore[arg-type]

    assert is_launchable_url("mailto:hi@kiri.ng")
    assert is_launchable_url("https://a.example")
    assert not is_launchable_url("javascript:alert(1)")
    assert not is_launchable_url("file:///etc/passwd")


def test_urljoin_preserves_foreign_schemes_so_the_guard_is_post_resolve():
    from components.results.content_fetcher import _resolve_url

    resolved = _resolve_url("javascript:alert(1)", "https://host/page")
    assert resolved == "javascript:alert(1)", (
        "documents why the http(s) check must run after resolution"
    )


def test_launcher_never_opens_foreign_schemes(monkeypatch):
    from components.results.downloader import launch_url

    opened: list[str] = []
    monkeypatch.setattr(webbrowser, "open", lambda url: opened.append(url))

    asyncio.run(launch_url("javascript:alert(1)"))
    asyncio.run(launch_url("file:///etc/passwd"))
    asyncio.run(launch_url("data:text/html,x"))
    assert opened == [], opened

    asyncio.run(launch_url("https://kiri.ng"))
    asyncio.run(launch_url("mailto:hi@kiri.ng"))
    assert opened == ["https://kiri.ng", "mailto:hi@kiri.ng"], opened


class _Page:
    def __init__(self) -> None:
        self.tasks: list = []

    def run_task(self, fn, *args):
        self.tasks.append((fn, args))


def test_fetcher_link_tap_refuses_unresolved_foreign_schemes():
    from components.results.content_fetcher import _on_link_tap

    page = _Page()
    _on_link_tap(page, "javascript:alert(1)", "https://host/page")
    assert page.tasks == [], "a foreign scheme must never start a fetch"

    _on_link_tap(page, "https://ok.example/x")
    assert len(page.tasks) == 1, "http(s) links still fetch in-app"
