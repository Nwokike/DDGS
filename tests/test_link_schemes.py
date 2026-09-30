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
    from core.utils import resolve_url

    assert (
        resolve_url("https://host/page", "javascript:alert(1)") is None
    ), "urljoin alone would keep the scheme; the guard must run after"


def test_resolve_url_is_the_one_resolver_for_every_surface():
    from core.utils import resolve_url

    base = "https://host/dir/page"
    assert resolve_url(base, "https://other.example/x") == "https://other.example/x"
    assert resolve_url(base, "other") == "https://host/dir/other"
    assert resolve_url(base, "../up") == "https://host/up"
    assert resolve_url(base, "?q=1") == "https://host/dir/page?q=1"
    assert resolve_url(base, "/root") == "https://host/root"
    # Never-fetchable inputs resolve to None instead of raising.
    assert resolve_url(base, "#section") is None
    assert resolve_url(base, "mailto:hi@kiri.ng") is None
    assert resolve_url(base, "javascript:alert(1)") is None
    assert resolve_url(base, "") is None
    assert resolve_url("", "relative") is None


def test_fetch_nav_debounces_and_keeps_its_own_stack():
    from core.utils import FetchNav

    nav = FetchNav(debounce=60.0)  # a huge window: the next tap is always too soon
    assert nav.allow_tap(), "the first tap passes"
    assert not nav.allow_tap(), "a rapid second tap is swallowed"

    stack_nav = FetchNav(debounce=0.0)
    assert not stack_nav.can_back
    stack_nav.push("https://a.example")
    stack_nav.push("https://a.example")  # consecutive duplicate: ignored
    assert stack_nav.can_back
    stack_nav.push("https://b.example")
    assert stack_nav.pop() == "https://b.example"
    assert stack_nav.pop() == "https://a.example"
    assert stack_nav.pop() is None

    capped = FetchNav(max_depth=2, debounce=0.0)
    for u in ("https://1.example", "https://2.example", "https://3.example"):
        capped.push(u)
    assert capped.pop() == "https://3.example"
    assert capped.pop() == "https://2.example", "the oldest page fell off"
    assert capped.pop() is None


class _Page:
    def __init__(self) -> None:
        self.tasks: list = []

    def run_task(self, fn, *args):
        self.tasks.append((fn, args))


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
