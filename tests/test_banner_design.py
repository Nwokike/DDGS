"""Banner space pinned to Sherlock's exact contract (owner directive):

* full width on every screen (outer Row stretcher + expand=True glass),
* the native 320x50 ad centered inside the glass,
* no SPONSORED tag anywhere (Sherlock removed it on purpose),
* premium and desktop stay zero-size.
"""

from __future__ import annotations

import ast
import sys
from pathlib import Path

import flet as ft

SRC = Path(__file__).resolve().parents[1] / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))


class _MobilePage:
    platform = ft.PagePlatform.ANDROID
    theme_mode = ft.ThemeMode.DARK
    width = 400
    height = 800


class _DesktopPage:
    platform = ft.PagePlatform.WINDOWS
    theme_mode = ft.ThemeMode.DARK
    width = 1200
    height = 800


def _walk(control):
    yield control
    for attr in ("content", "controls"):
        kid = getattr(control, attr, None)
        if kid is None:
            continue
        if isinstance(kid, list):
            for item in kid:
                yield from _walk(item)
        else:
            yield from _walk(kid)


def test_banner_is_sherlocks_stretcher():
    from core import tokens
    from core.styles import build_banner_ad

    row = build_banner_ad(_MobilePage(), unit_id="ca-app-pub-test/banner")
    assert isinstance(row, ft.Row), "the outer Row is what forces full width"
    assert row.alignment == ft.MainAxisAlignment.CENTER
    assert len(row.controls) == 1

    (glass,) = row.controls
    assert isinstance(glass, ft.Container)
    assert glass.expand is True, "expand=True stretches the glass edge to edge"
    assert glass.margin is None, "no side margins: the old inset broke width"
    assert glass.padding == tokens.SPACE_SM
    assert glass.border_radius == tokens.RADIUS_LG

    inner = glass.content
    assert isinstance(inner, ft.Column)
    assert inner.horizontal_alignment == ft.CrossAxisAlignment.CENTER
    assert inner.tight is True
    assert len(inner.controls) == 1

    (pin,) = inner.controls
    assert isinstance(pin, ft.Container)
    assert (pin.width, pin.height) == (320, 50), "the native ad stays pinned"
    assert pin.content is not None, "the ad control is missing from the pin"


def test_banner_contains_no_label_text():
    from core.styles import build_banner_ad

    row = build_banner_ad(_MobilePage(), unit_id="ca-app-pub-test/banner")
    texts = [c for c in _walk(row) if isinstance(c, ft.Text)]
    assert texts == [], "the SPONSORED tag is gone by design (Sherlock)"


def test_sponsored_label_exists_nowhere_under_src():
    """The literal label must not exist as a string anywhere in the app."""
    for path in sorted(SRC.rglob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if (
                isinstance(node, ast.Constant)
                and isinstance(node.value, str)
                and node.value.strip() == "SPONSORED"
            ):
                raise AssertionError(
                    f"{path.relative_to(SRC)}:{node.lineno} carries the "
                    "banned SPONSORED label"
                )


def test_premium_banner_is_zero_size(monkeypatch):
    from core.state import state
    from core.styles import build_banner_ad

    monkeypatch.setattr(state, "is_premium", True)
    ctrl = build_banner_ad(_MobilePage(), unit_id="ca-app-pub-test/banner")
    assert ctrl.width == 0
    assert ctrl.height == 0


def test_desktop_banner_is_zero_size():
    from core.styles import build_banner_ad

    ctrl = build_banner_ad(_DesktopPage(), unit_id="ca-app-pub-test/banner")
    assert ctrl.width == 0
    assert ctrl.height == 0
