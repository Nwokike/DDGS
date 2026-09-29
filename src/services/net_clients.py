"""One home for "does the user's proxy apply to this call?" (audit A1).

`state.proxy` and `state.verify_ssl` used to reach search only, so
media downloads, the YouTube innertube client, update checks, license
checks and the live engine fetch all ignored a configured proxy. Every
NON-loopback HTTP path now grows its client kwargs from here.

Loopback router traffic (127.0.0.1 probes, the kani stream, the catalog
fetch) must never be proxied: a proxy cannot reach the user's own
machine, so applying the setting there would break the Assistant. Those
clients deliberately do not call this module.
"""

from __future__ import annotations

from typing import Any

from core.state import state


def primp_kwargs() -> dict[str, Any]:
    """proxy/verify additions for a primp AsyncClient, honoring settings.

    Empty dict when the user set nothing - primp then behaves exactly as
    before this module existed.
    """
    kwargs: dict[str, Any] = {}
    if state.proxy:
        kwargs["proxy"] = state.proxy
    if state.verify_ssl is False:
        kwargs["verify"] = False
    return kwargs


def httpx_proxy() -> str | None:
    """Proxy URL for public httpx calls, or None to go direct."""
    return state.proxy or None
