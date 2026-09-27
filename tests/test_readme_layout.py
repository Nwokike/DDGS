"""README layout rules (owner): 10 screenshots like KTV Player, zero
collapsible sections, capped widths so readers click to expand, and only
files that exist."""

from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
README = ROOT / "README.md"


def _text() -> str:
    return README.read_text(encoding="utf-8")


def test_readme_has_no_collapsible_sections():
    assert "<details>" not in _text(), "owner: nothing stays collapsed"


def test_readme_shows_exactly_ten_capped_screenshots():
    text = _text()
    shots = text.split("## Screenshots", 1)[1].split("## The Assistant", 1)[0]
    assert shots.count("<img") == 10, "KTV-style set of exactly 10"
    assert 'width="280"' in shots, "mobile shots capped like KTV"
    assert 'width="90%"' in shots, "desktop shots capped like KTV"
    for src in re.findall(r'src="(screenshots/[^"]+)"', shots):
        assert (ROOT / src).exists(), f"missing screenshot: {src}"


def test_repeated_old_shots_are_gone():
    """Replaced by the owner's new captures (home x2, assistant-overview
    desktop, old text results)."""
    text = _text()
    for gone in (
        "home_dark_mobile.png",
        "results_desktop.png",
    ):
        assert gone not in text, f"{gone} was a repetition and must stay out"
