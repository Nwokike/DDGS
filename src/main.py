"""DDGS - Dux Distributed Global Search.

Minimal entry point.  All business logic lives in AppController;
the declarative UI tree is mounted by page.render().
"""

from __future__ import annotations

import flet as ft

from core.tls import ensure_ca_bundle

# Runs before AppController, i.e. before any httpx client can exist: on
# Android the runtime ships SSL_CERT_FILE pointing at a missing path and
# httpx raises FileNotFoundError at construction. See core.tls.
_CA_STATUS = ensure_ca_bundle()


async def main(page: ft.Page):
    from app_controller import AppController

    controller = AppController(page)
    await controller.init()

    # Wire lifecycle hooks
    # Flet 1.0 exits without running atexit/buffered writes - flush
    # synchronously and stop the embedded Kiri router here. The disconnect
    # hook must stay synchronous too: the event loop is already closing by
    # then, so page.run_task would leave the coroutine un-awaited.
    def _flush(e=None):
        controller.storage.flush_now()

    page.on_disconnect = _flush
    page.on_view_pop = controller.on_view_pop
    page.on_close = controller.on_app_close


if __name__ == "__main__":
    import os

    from core.utils import logger

    logger.info("Starting DDGS on Python %s", __import__("sys").version)
    logger.info("TLS trust store: %s", _CA_STATUS)
    try:
        import primp

        logger.info("primp available: %s", getattr(primp, "__version__", "unknown"))
    except ImportError:
        logger.warning("primp not available")

    assets_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "assets")
    ft.run(main, assets_dir=assets_path)
