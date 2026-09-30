"""Tests for unified AppHeader and live version chip across screens (Sherlock & KTV Player parity)."""

from __future__ import annotations

import sys
from pathlib import Path

import flet as ft

SRC = Path(__file__).resolve().parents[1] / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from components.app_header import AppHeader, _build_version_chip
from components.settings.version import _APP_VERSION
from core.state import state


def _texts(control):
    yield control
    for attr in ("content", "controls", "actions"):
        kid = getattr(control, attr, None)
        if kid is None:
            continue
        if isinstance(kid, list):
            for item in kid:
                yield from _texts(item)
        else:
            yield from _texts(kid)


class _FakePage:
    def __init__(self) -> None:
        self.theme_mode = ft.ThemeMode.DARK
        self.dialog = None
        self.platform = ft.PagePlatform.ANDROID

    def show_dialog(self, dialog):
        self.dialog = dialog

    def pop_dialog(self):
        self.dialog = None

    def update(self):
        pass


def test_version_chip_default_state():
    """Normally shows v{_APP_VERSION} pill with What's New tooltip."""
    state.update_available = False
    state.update_data = None
    page = _FakePage()

    chip = _build_version_chip(page)
    assert isinstance(chip, ft.Container)
    assert chip.tooltip == "What's New - version & changelog"

    text_controls = [c for c in _texts(chip) if isinstance(c, ft.Text)]
    assert len(text_controls) == 1
    assert text_controls[0].value == f"v{_APP_VERSION}"
    assert text_controls[0].value == "v2.1.0"


def test_version_chip_update_available_state():
    """When update_available is True, morphs into 'Update: {version} Available!' with dot."""
    state.update_available = True
    state.update_data = {
        "version": "2.2.0",
        "build_number": 12,
        "type": "update",
    }
    page = _FakePage()

    chip = _build_version_chip(page)
    assert isinstance(chip, ft.Container)
    assert chip.tooltip == "New update available - tap to view"
    assert chip.border is not None

    text_values = [
        c.value for c in _texts(chip) if isinstance(c, ft.Text) and c.value
    ]
    assert any("Update: 2.2.0 Available!" in v for v in text_values)

    # Announcement type shows "News"
    state.update_data = {
        "version": "2.2.0",
        "build_number": 12,
        "type": "announcement",
    }
    chip_ann = _build_version_chip(page)
    text_values_ann = [
        c.value for c in _texts(chip_ann) if isinstance(c, ft.Text) and c.value
    ]
    assert any("News" in v for v in text_values_ann)

    # Cleanup
    state.update_available = False
    state.update_data = None


def test_version_chip_click_opens_dialog():
    """Clicking the chip opens update dialog."""
    from components import update_dialog

    state.update_available = False
    page = _FakePage()
    chip = _build_version_chip(page)

    opened = []
    def _fake_show(p, data=None):
        opened.append(True)

    original_show = update_dialog.show_update_dialog
    update_dialog.show_update_dialog = _fake_show
    try:
        chip.on_click()
        assert len(opened) == 1
    finally:
        update_dialog.show_update_dialog = original_show


def test_show_update_dialog_default_args():
    """show_update_dialog with no update_data automatically checks state."""
    from components.update_dialog import show_update_dialog

    page = _FakePage()
    state.update_available = False
    state.update_data = None

    # Should open up-to-date dialog without error
    show_update_dialog(page)
    assert page.dialog is not None

    # When update available, should show update dialog
    state.update_available = True
    state.update_data = {
        "version": "2.2.0",
        "build_number": 12,
        "type": "update",
        "release_notes": "Great features",
    }
    show_update_dialog(page)
    assert page.dialog is not None
    # Cleanup
    state.update_available = False
    state.update_data = None


def test_app_header_rendering():
    """AppHeader renders brand/back on left, version chip on right."""
    page = _FakePage()

    # Brand mode (Home)
    header_home = AppHeader(page, title="DDGS")
    assert isinstance(header_home, ft.Container)
    values = [c.value for c in _texts(header_home) if isinstance(c, ft.Text)]
    assert "DDGS" in values
    assert f"v{_APP_VERSION}" in values

    # Navigation mode (History / Settings)
    header_nav = AppHeader(
        page,
        title="Settings",
        subtitle="Preferences",
        show_back=True,
        on_back=lambda: None,
        show_settings=False,
    )
    nav_values = [c.value for c in _texts(header_nav) if isinstance(c, ft.Text)]
    assert "Settings" in nav_values
    assert "Preferences" in nav_values
    assert f"v{_APP_VERSION}" in nav_values


def test_every_screen_mounts_version_chip():
    """Grep-level verification: all screens include AppHeader or _build_version_chip."""
    root = Path(__file__).resolve().parents[1] / "src" / "screens"

    home = (root / "home_screen.py").read_text(encoding="utf-8")
    assert "AppHeader" in home

    history = (root / "history_screen.py").read_text(encoding="utf-8")
    assert "AppHeader" in history

    settings = (root / "settings_screen.py").read_text(encoding="utf-8")
    assert "AppHeader" in settings

    chat = (root / "chat_screen.py").read_text(encoding="utf-8")
    assert "_build_version_chip" in chat

    results = (root / "results_screen.py").read_text(encoding="utf-8")
    assert "_build_version_chip" in results

    reader = (root / "content_reader_screen.py").read_text(encoding="utf-8")
    assert "_build_version_chip" in reader
