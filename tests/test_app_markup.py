"""Guards for runtime-only control mistakes static checks can't see.

The first FAB attempt used `ft.Positioned`, which does not exist in flet
1.0.1 — imports and ruff passed, but the first render crashed main(). These
tests construct the exact markup shapes the app renders.
"""

from __future__ import annotations

import flet as ft


def test_fab_markup_constructs():
    # Mirrors app_shell.AppShell's Ask-AI FAB (native badge + own positioning).
    fab = ft.FloatingActionButton(
        icon=ft.Icons.AUTO_AWESOME_ROUNDED,
        bgcolor="#6750A4",
        badge="50",
        tooltip="Ask AI",
        right=16,
        bottom=96,
    )
    assert fab.badge == "50"
    assert fab.right == 16
    assert fab.bottom == 96


def test_stack_has_no_positioned():
    # flet 1.0.1 exposes no Positioned — layout props live on the controls.
    assert not hasattr(ft, "Positioned")
    stack = ft.Stack([ft.Container(width=10, height=10, right=4, bottom=4)], expand=True)
    assert len(stack.controls) == 1


def test_chat_stream_controls_construct():
    # Shapes used while streaming: markdown + throttle-replaced values.
    md = ft.Markdown("**stream** [1](https://example.com)", selectable=True)
    assert "example.com" in md.value
    field = ft.TextField(hint_text="Ask AI anything…", expand=True, min_lines=1, max_lines=4)
    assert field.max_lines == 4
