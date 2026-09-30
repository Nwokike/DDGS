"""IDN display pins (utilization plan A6): punycode hosts read as
unicode everywhere a URL is SHOWN; clicks/copies keep the raw href."""

from __future__ import annotations

import sys
from pathlib import Path

SRC = Path(__file__).resolve().parents[1] / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))


def test_display_host_decodes_punycode():
    from core.utils import display_host

    assert display_host("xn--mnchen-3ya.de") == "münchen.de"
    assert display_host("plain.example") == "plain.example"
    # Invalid punycode must pass through, never raise in a render path.
    assert display_host("xn--") == "xn--"


def test_display_url_decodes_only_the_host():
    from core.utils import display_url

    url = "https://xn--mnchen-3ya.de/artikel?q=1#top"
    assert display_url(url) == "https://münchen.de/artikel?q=1#top"
    # Port and scheme survive the rewrite.
    assert (
        display_url("https://xn--mnchen-3ya.de:8443/x")
        == "https://münchen.de:8443/x"
    )
    # Plain URLs are byte-identical (zero render churn).
    plain = "https://kiri.ng/projects?x=1"
    assert display_url(plain) == plain
    # Non-web strings pass through untouched.
    assert display_url("mailto:hi@kiri.ng") == "mailto:hi@kiri.ng"


def test_chat_domain_chip_decodes():
    from screens.chat_screen import _domain

    assert _domain("https://xn--mnchen-3ya.de/page") == "münchen.de"
    assert _domain("https://www.kiri.ng/x") == "kiri.ng"
