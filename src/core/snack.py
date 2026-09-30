"""Snack bars that can never strand the screen.

flet keeps SnackBars in the page's dialog stack, so a bar whose client-
side dismissal timer never fires (session teardown mid-show, a rebuild
that loses the timer) sits in the stack and swallows every tap - the
UI is frozen until something dismisses it. This helper shows the bar
AND schedules a local timer that closes that exact bar (never a dialog
opened on top of it) whatever the client does.

Every snack in the app goes through here; a bare `page.show_dialog(snack)`
is the bug this module exists to prevent.
"""

from __future__ import annotations

import asyncio
import logging

import flet as ft

logger = logging.getLogger(__name__)

# A little longer than flet's own 4s default so the client always wins
# the race; the client closing first is the normal path.
_BACKSTOP_S = 5.0


def show_snack(page: ft.Page, snack: ft.SnackBar) -> None:
    """Show a SnackBar with a guaranteed local dismissal backstop."""
    snack.open = True
    try:
        page.show_dialog(snack)
    except RuntimeError:
        # Already open (double tap): nothing to do.
        return

    async def _backstop() -> None:
        try:
            await asyncio.sleep(_BACKSTOP_S)
        except asyncio.CancelledError:
            return
        try:
            if not snack.open:
                return  # the client dismissed it on time - normal
            snack.open = False
            snack.update()
        except Exception:
            logger.debug("snack backstop could not close the bar", exc_info=True)

    try:
        page.run_task(_backstop)
    except Exception:
        # No running loop: the client-side duration is all we have.
        logger.debug("no task runner for the snack backstop", exc_info=True)
