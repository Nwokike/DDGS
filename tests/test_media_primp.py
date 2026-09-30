"""primp hardening pins (utilization plan A2).

primp's errors are NOT builtin (`PrimpError`, not `OSError`), so they
used to escape every caller's handler. download_media now maps them to
plain RuntimeError, and an anti-bot 403/429 gets ONE retry on a fresh
"profile random" profile before the status is reported honestly.
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path
from typing import ClassVar

import pytest

SRC = Path(__file__).resolve().parents[1] / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))


class _FakeStatus(Exception):
    def __init__(self, code: int) -> None:
        super().__init__(f"HTTP {code}")
        self.status_code = code


class _FakeTimeout(Exception):
    pass


class _FakeResponse:
    def __init__(self, content_type: str = "video/mp4") -> None:
        self.headers = {"content-type": content_type, "content-length": "0"}
        self.status_code = 200

    def raise_for_status(self) -> None:
        return None

    async def aiter_bytes(self, _n: int):  # pragma: no cover - not reached
        return
        yield b""


class _FakeClient:
    """One construction per profile; behavior chosen by construction order."""

    plans: ClassVar[list] = []
    built: ClassVar[list] = []

    def __init__(self, **kwargs) -> None:
        self.kwargs = kwargs
        type(self).built.append(kwargs.get("impersonate"))

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False

    async def get(self, *args, **kwargs):
        plan = type(self).plans.pop(0)
        if isinstance(plan, Exception):
            raise plan
        return plan


def _install(monkeypatch, plans: list) -> list:
    import primp

    _FakeClient.plans = list(plans)
    _FakeClient.built = []
    monkeypatch.setattr(primp, "AsyncClient", _FakeClient)
    monkeypatch.setattr(primp, "StatusError", _FakeStatus)
    monkeypatch.setattr(primp, "TimeoutError", _FakeTimeout)
    return _FakeClient.built


def test_403_retries_once_on_a_fresh_profile_then_maps_the_status(
    monkeypatch, tmp_path
):
    from services import media_downloader as md

    built = _install(monkeypatch, [_FakeStatus(403), _FakeStatus(404)])
    dest = tmp_path / "clip.mp4"
    with pytest.raises(RuntimeError, match="HTTP 404"):
        asyncio.run(md.download_media("https://host/x.mp4", str(dest)))
    assert built == [md.DEFAULT_IMPERSONATE, "random"], built


def test_non_retryable_status_fails_on_the_first_profile(monkeypatch, tmp_path):
    from services import media_downloader as md

    built = _install(monkeypatch, [_FakeStatus(404)])
    with pytest.raises(RuntimeError, match="HTTP 404"):
        asyncio.run(md.download_media("https://host/x.mp4", str(tmp_path / "a.mp4")))
    assert built == [md.DEFAULT_IMPERSONATE], built


def test_timeout_maps_to_plain_text(monkeypatch, tmp_path):
    from services import media_downloader as md

    _install(monkeypatch, [_FakeTimeout("read timeout")])
    with pytest.raises(RuntimeError, match="timed out"):
        asyncio.run(md.download_media("https://host/x.mp4", str(tmp_path / "b.mp4")))


def test_html_answer_still_raises_not_media_before_any_retry(monkeypatch, tmp_path):
    from services import media_downloader as md

    _install(monkeypatch, [_FakeResponse("text/html")])
    with pytest.raises(md.NotMediaError):
        asyncio.run(
            md.download_media(
                "https://host/page", str(tmp_path / "c.bin"), expect_media=True
            )
        )


def test_sanitize_filename_slugs_unicode_and_caps_length():
    from services.media_downloader import sanitize_filename

    # International titles transliterate to ASCII (plan D8).
    assert sanitize_filename("Résumé ünter", "pdf") == "resume-unter.pdf"
    assert sanitize_filename("", "mp4") == "download.mp4"
    # Separators collapse to hyphens, existing extensions don't double.
    assert sanitize_filename("My Clip: best/of?", ".mp4") == "my-clip-best-of.mp4"
    assert len(sanitize_filename("A" * 200, "mp4")) == 64 + 4


def test_real_client_accepts_connect_timeout():
    import primp

    async def go():
        async with primp.AsyncClient(connect_timeout=10.0):
            pass

    asyncio.run(go())  # construction only - no request is made
