"""AppState context — component-facing adapter over the observable state.

Components read state via ``ft.use_context(AppStateCtx)`` which returns
the module-level ``state`` singleton.  Mutations to ``state`` fields
auto-notify all subscribed components (batched by the Flet scheduler).
"""

import flet as ft

from core.state import state

AppStateCtx = ft.create_context(state)

__all__ = ["AppStateCtx", "state"]
