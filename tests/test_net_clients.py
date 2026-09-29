"""Proxy rule pins (utilization plan A1): one home for "does the user's
proxy apply here?" - primp paths share primp_kwargs(), public httpx paths
share httpx_proxy(), and loopback router traffic never proxies."""

from __future__ import annotations

import sys
from pathlib import Path

SRC = Path(__file__).resolve().parents[1] / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))


def test_primp_kwargs_reflect_the_settings():
    from core.state import state
    from services.net_clients import primp_kwargs

    old_proxy, old_ssl = state.proxy, state.verify_ssl
    try:
        state.proxy = ""
        state.verify_ssl = True
        assert primp_kwargs() == {}, "unset settings must change nothing"

        state.proxy = "http://127.0.0.1:8888"
        assert primp_kwargs() == {"proxy": "http://127.0.0.1:8888"}

        state.verify_ssl = False
        assert primp_kwargs() == {
            "proxy": "http://127.0.0.1:8888",
            "verify": False,
        }
    finally:
        state.proxy, state.verify_ssl = old_proxy, old_ssl


def test_httpx_proxy_passthrough():
    from core.state import state
    from services.net_clients import httpx_proxy

    old = state.proxy
    try:
        state.proxy = ""
        assert httpx_proxy() is None
        state.proxy = "http://proxy.example:3128"
        assert httpx_proxy() == "http://proxy.example:3128"
    finally:
        state.proxy = old


def test_every_non_loopback_path_grows_its_client_from_the_shared_home():
    root = Path(__file__).resolve().parents[1]
    proxied = {
        "services/media_downloader.py": "primp_kwargs()",
        "services/search_service.py": "primp_kwargs()",
        "services/youtube/innertube_client.py": "primp_kwargs()",
        "services/engine.py": "httpx_proxy()",
        "services/license_service.py": "httpx_proxy()",
        "services/update_service.py": "httpx_proxy()",
    }
    for rel, needle in proxied.items():
        source = (root / "src" / rel).read_text(encoding="utf-8")
        assert needle in source, f"{rel} must honor the proxy setting"

    # Loopback router traffic must NOT be proxied: a proxy cannot reach
    # the user's own machine, so these clients stay direct.
    for rel in ("services/ai_service.py", "services/reasoning.py"):
        source = (root / "src" / rel).read_text(encoding="utf-8")
        assert "net_clients" not in source, f"{rel} is loopback-only"
