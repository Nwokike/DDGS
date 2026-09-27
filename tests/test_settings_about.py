"""About section carries KTV Player's important rows (owner directive):

Contact developer, Rate 5 stars (dynamic subtitle per audience) and
More apps (Play developer page on store devices, GitHub on desktop).
"""

from __future__ import annotations

import sys
from pathlib import Path

import flet as ft

SRC = Path(__file__).resolve().parents[1] / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))


class _AndroidPage:
    platform = ft.PagePlatform.ANDROID
    theme_mode = ft.ThemeMode.DARK

    def run_task(self, handler, *args, **kwargs):
        pass


class _DesktopPage:
    platform = ft.PagePlatform.WINDOWS
    theme_mode = ft.ThemeMode.DARK

    def run_task(self, handler, *args, **kwargs):
        pass


def _texts(control):
    yield control
    for attr in ("content", "controls"):
        kid = getattr(control, attr, None)
        if kid is None:
            continue
        if isinstance(kid, list):
            for item in kid:
                yield from _texts(item)
        else:
            yield from _texts(kid)


def test_about_section_carries_the_ktv_rows():
    from components.settings.sections_about import build_about_section

    section = build_about_section(
        _AndroidPage(),
        "https://example.com/privacy",
        "https://example.com/terms",
    )
    values = {
        c.value
        for c in _texts(section)
        if isinstance(c, ft.Text) and isinstance(c.value, str)
    }
    assert "Contact developer" in values
    assert "Rate 5 stars" in values
    assert "More apps from Kiri" in values


def test_more_apps_url_and_subtitles_match_ktv_exactly():
    """KTV Player's contract, constants byte-for-byte: store devices get
    the shared Play developer listing, everything else the kiri.ng
    showcase; subtitles identical to KTV's."""
    from components.settings import sections_about as sa
    from core.constants import KIRI_APPS_PLAY_URL, KIRI_APPS_URL

    assert sa._more_apps_url(_AndroidPage()) == KIRI_APPS_PLAY_URL
    assert KIRI_APPS_PLAY_URL.endswith("id=5797833969564243342")
    assert sa._more_apps_url(_DesktopPage()) == KIRI_APPS_URL
    assert KIRI_APPS_URL == "https://kiri.ng/projects"

    assert sa._more_apps_subtitle(_AndroidPage()) == "All our apps on Google Play"
    assert (
        sa._more_apps_subtitle(_DesktopPage())
        == "Sherlock, DDGS, CollabShell and more"
    )


def test_rate_url_and_subtitles_stay_dynamic():
    from components.settings import sections_about as sa
    from services.update_service import PLAY_STORE_URL

    assert sa._rate_url(_AndroidPage()) == PLAY_STORE_URL
    assert sa._rate_subtitle(_AndroidPage()) == "Rate us on Google Play"
    assert sa._rate_url(_DesktopPage()) == sa.GITHUB_REPO_URL
    assert sa._rate_subtitle(_DesktopPage()) == "Star us on GitHub"
