"""Settings carries exactly three banners in the owner's positions:

1. after Assistant (before Premium),
2. after search results (before search source),
3. before About.
"""

from __future__ import annotations

from pathlib import Path

SRC = Path(__file__).resolve().parents[1] / "src"


def test_settings_has_exactly_three_banners_in_owner_order():
    body = (SRC / "screens" / "settings_screen.py").read_text(encoding="utf-8")
    body = body.split("sections = ft.Column(")[1]
    assert body.count("build_banner_ad(page)") == 3, (
        "Settings must carry exactly three banners (owner directive)"
    )

    pos = 0
    for marker in (
        "build_ai_section(",
        "build_banner_ad(page)",
        "build_premium_section(page)",
        "build_search_rules_section(",
        "build_banner_ad(page)",
        "build_backends_section(",
        "build_storage_section(",
        "build_banner_ad(page)",
        "build_about_section(",
    ):
        idx = body.index(marker, pos)
        pos = idx + 1
