"""use_debounce — debounces a value change with configurable delay.

Adapted from KTV Player's hooks/use_debounce.py.
"""

from __future__ import annotations

import asyncio

import flet as ft


def use_debounce(value, delay_ms: int = 250):
    """Returns a debounced version of `value`.

    The returned value only updates after `delay_ms` milliseconds of
    inactivity.  Useful for search-as-you-type, slider debouncing, etc.
    """
    debounced, set_debounced = ft.use_state(value)
    timer_ref = ft.use_ref(None)
    value_ref = ft.use_ref(value)

    value_ref.current = value

    def _cleanup():
        if timer_ref.current is not None:
            timer_ref.current.cancel()

    def _on_change(_):
        if timer_ref.current is not None:
            timer_ref.current.cancel()

        async def _delayed_update():
            await asyncio.sleep(delay_ms / 1000)
            set_debounced(value_ref.current)
            timer_ref.current = None

        from flet import context as flet_context

        page = flet_context.page
        if page:
            timer_ref.current = page.run_task(_delayed_update)

    ft.use_effect(_on_change, [value], cleanup=_cleanup)

    return debounced
