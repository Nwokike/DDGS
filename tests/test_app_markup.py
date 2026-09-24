"""Guards for runtime-only control mistakes static checks can't see.

The first FAB attempt used `ft.Positioned`, which does not exist in flet
1.0.1 — imports and ruff passed, but the first render crashed main(). The
picker then shipped `ft.SearchBar(hint_text=...)`, which does not exist
either (the real prop is `bar_hint_text`) and crashed when Settings was
opened. These tests construct the exact markup shapes the app renders.
"""

from __future__ import annotations

import flet as ft


def test_fab_markup_constructs():
    # Mirrors app_shell's Ask Assistant FAB: CollabShell recipe, no badge.
    fab = ft.FloatingActionButton(
        icon=ft.Icons.CHAT_BUBBLE_ROUNDED,
        foreground_color=ft.Colors.WHITE,
        bgcolor="#B33A1D",
        mini=True,
        tooltip="Ask Assistant",
    )
    assert fab.badge is None
    assert fab.mini is True
    # flet 1.0 spells the icon colour foreground_color; icon_color is invalid
    # on FloatingActionButton and raises TypeError at construction.
    assert "icon_color" not in ft.FloatingActionButton.__dataclass_fields__


def test_stack_has_no_positioned():
    # flet 1.0.1 exposes no Positioned — layout props live on the controls.
    assert not hasattr(ft, "Positioned")
    stack = ft.Stack(
        [ft.Container(width=10, height=10, right=4, bottom=4)], expand=True
    )
    assert len(stack.controls) == 1


def test_chat_stream_controls_construct():
    # Shapes used while streaming: markdown + throttle-replaced values.
    md = ft.Markdown("**stream** [1](https://example.com)", selectable=True)
    assert "example.com" in md.value
    field = ft.TextField(
        hint_text="Ask the assistant…", expand=True, min_lines=1, max_lines=4
    )
    assert field.max_lines == 4


def test_model_picker_filter_uses_real_searchbar_prop():
    # SearchBar(hint_text=...) was a TypeError at runtime; bar_hint_text is real.
    fields = ft.SearchBar.__dataclass_fields__
    assert "bar_hint_text" in fields
    assert "hint_text" not in fields
    assert "dense" not in fields
    bar = ft.SearchBar(
        bar_hint_text="Filter models",
        bar_leading=ft.Icon(ft.Icons.SEARCH_ROUNDED, size=18),
        on_change=lambda e: None,
    )
    assert bar.bar_hint_text == "Filter models"


def test_settings_switch_uses_primary_and_keeps_its_subtitle():
    # Sherlock standard: every switch carries active_color=PRIMARY.
    sw = ft.Switch(value=True, active_color="#B33A1D", on_change=lambda e: None)
    assert sw.active_color == "#B33A1D"
    assert "active_color" in ft.Switch.__dataclass_fields__


def test_no_badge_used_anywhere_in_assistant_ui():
    # ft.Badge with no bgcolor renders as a red block over the FAB; the app
    # now carries counts in its own explicitly coloured chips.
    from pathlib import Path

    src = Path(__file__).resolve().parents[1] / "src"
    offenders = [
        str(p.relative_to(src))
        for p in src.rglob("*.py")
        if "ft.Badge(" in p.read_text(encoding="utf-8")
    ]
    assert not offenders, f"ft.Badge reintroduced in: {offenders}"


def test_every_icons_name_resolves_in_installed_flet():
    # A missing icon name does not raise; it renders a blank glyph.
    import ast
    from pathlib import Path

    src = Path(__file__).resolve().parents[1] / "src"
    missing: list[str] = []
    for path in src.rglob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if (
                isinstance(node, ast.Attribute)
                and isinstance(node.value, ast.Attribute)
                and isinstance(node.value.value, ast.Name)
                and node.value.value.id == "ft"
                and node.value.attr == "Icons"
                and getattr(ft.Icons, node.attr, "MISSING") == "MISSING"
            ):
                missing.append(f"{path.name}:{node.lineno} {node.attr}")
    assert not missing, f"unknown icons: {missing}"
