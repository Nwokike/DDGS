"""Snack backstop pin: a stranded SnackBar must never keep the UI locked.

flet keeps SnackBars in the dialog stack, so a bar whose client-side
timer never fires swallows every tap. core.snack schedules a local
backstop that closes THAT bar - never a dialog opened on top of it.
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

SRC = Path(__file__).resolve().parents[1] / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

import flet as ft


def test_backstop_closes_the_bar_itself():
    from core import snack

    snack._BACKSTOP_S = 0.01  # shrink the wait for the test
    bar = ft.SnackBar(ft.Text("All chats deleted"), action="Undo")
    calls: list = []

    class _StrandedPage:
        """A page whose client-side dismissal never happens."""

        def show_dialog(self, dialog):
            calls.append(("show", dialog))

        def run_task(self, fn, *args):
            task = asyncio.ensure_future(fn())
            calls.append(("task", task))
            return task

        def pop_dialog(self):  # must never be reached by the backstop
            raise AssertionError("pop_dialog would close an unrelated dialog")

    async def go() -> None:
        page = _StrandedPage()
        snack.show_snack(page, bar)
        assert calls[0] == ("show", bar)
        task = next(c[1] for c in calls if c[0] == "task")
        await asyncio.wait_for(task, 1)

    asyncio.run(go())
    assert bar.open is False, "the backstop must close the stranded bar"


def test_every_snackbar_goes_through_the_helper():
    root = Path(__file__).resolve().parents[1] / "src"
    offenders = [
        str(p.relative_to(root))
        for p in root.rglob("*.py")
        if "show_dialog" in p.read_text(encoding="utf-8")
        and "SnackBar" in p.read_text(encoding="utf-8")
        and "show_snack(" not in p.read_text(encoding="utf-8")
        and p.name != "snack.py"
    ]
    assert not offenders, f"raw show_dialog(SnackBar) left in: {offenders}"
