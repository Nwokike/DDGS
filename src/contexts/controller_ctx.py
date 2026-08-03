"""Controller callbacks context — exposes AppController methods to the
component tree.

``AppShell`` is rendered via ``page.render()`` with no positional args,
so AppController cannot pass callbacks as constructor parameters.  Instead,
AppController mounts a ``ControllerMethodsCtx`` provider before calling
``page.render()``.  Components read callbacks via
``ft.use_context(ControllerMethodsCtx)``.

All defaults are async/sync no-ops so the shell renders safely even
before the provider is mounted (e.g. inside unit tests).
"""

from collections.abc import Awaitable, Callable
from dataclasses import dataclass

import flet as ft


async def _noop_async() -> None:
    """No-op async default."""


async def _noop_search(_query: str, _search_type: str = "text") -> None:
    """No-op for start_search(query, search_type)."""


async def _noop_extract(_url: str) -> None:
    """No-op for run_extract(url)."""


def _noop_sync() -> None:
    """No-op sync default."""


def _noop_tab(_tab: int) -> None:
    """No-op for navigate_tab(tab_index)."""


async def _noop_setting(_key: str, _value) -> None:
    """No-op for save_setting(key, value)."""


async def _noop_async_str(_s: str = "") -> None:
    """No-op async with optional string."""


@dataclass
class ControllerMethods:
    """Subset of AppController methods exposed to the component tree.

    Mutable (not frozen) so AppController can build it incrementally.
    All defaults are real no-ops whose signatures match the AppController
    methods — important because use_context returns this dataclass and
    components await the callables directly.
    """

    start_search: Callable[[str, str], Awaitable[None]] = _noop_search
    run_extract: Callable[[str], Awaitable[None]] = _noop_extract
    cancel_search: Callable[[], None] = _noop_sync
    go_home: Callable[[], Awaitable[None]] = _noop_async
    navigate_tab: Callable[[int], None] = _noop_tab
    save: Callable[[str, object], None] = _noop_tab  # sync: save(key, value)
    save_async: Callable[[str, object], Awaitable[None]] = _noop_setting  # async version
    show_snack: Callable[[str, str], Awaitable[None]] = _noop_async_str


ControllerMethodsCtx = ft.create_context(ControllerMethods())

__all__ = ["ControllerMethods", "ControllerMethodsCtx"]
