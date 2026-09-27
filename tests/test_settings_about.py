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
    assert "More apps" in values


def test_more_apps_url_follows_the_rate_row_split():
    from components.settings import sections_about as sa

    # Store devices get the Play developer page (both Kiri listings share
    # this id); desktop gets the GitHub profile.
    assert sa._more_apps_url(_AndroidPage()) == sa.PLAY_DEV_URL
    assert sa._more_apps_url(_DesktopPage()) == "https://github.com/Nwokike"


def test_rate_url_and_subtitles_stay_dynamic():
    from components.settings import sections_about as sa
    from services.update_service import PLAY_STORE_URL

    assert sa._rate_url(_AndroidPage()) == PLAY_STORE_URL
    assert sa._rate_subtitle(_AndroidPage()) == "Rate us on Google Play"
    assert sa._rate_url(_DesktopPage()) == sa.GITHUB_REPO_URL
    assert sa._rate_subtitle(_DesktopPage()) == "Star us on GitHub"
