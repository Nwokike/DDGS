"""use_search — wraps search/extract logic for components.

Provides a clean interface for triggering searches from UI components.
"""

from __future__ import annotations

import flet as ft

from contexts.controller_ctx import ControllerMethodsCtx


def use_search():
    """Returns (start_search, run_extract, cancel_search) callbacks.

    Usage inside a @ft.component::

        start, extract, cancel = use_search()
        start("query", "text")
        extract("https://example.com")
        cancel()
    """
    controller = ft.use_context(ControllerMethodsCtx)

    from flet import context as flet_context

    def _start(query: str, search_type: str = "text"):
        flet_context.page.run_task(controller.start_search, query, search_type)

    def _extract(url: str):
        flet_context.page.run_task(controller.run_extract, url)

    def _cancel():
        controller.cancel_search()

    return _start, _extract, _cancel
