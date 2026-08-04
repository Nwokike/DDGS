"""DDGS — Dux Distributed Global Search.

Minimal entry point.  All business logic lives in AppController;
the declarative UI tree is mounted by page.render().
"""

from __future__ import annotations

import flet as ft


async def main(page: ft.Page):
    from app_controller import AppController

    controller = AppController(page)
    await controller.init()

    # Wire lifecycle hooks
    page.on_view_pop = lambda e: controller.go_home()
    page.on_disconnect = lambda e: page.run_task(controller.storage.flush)


if __name__ == "__main__":
    import os

    from core.utils import logger

    logger.info("Starting DDGS on Python %s", __import__("sys").version)
    try:
        import primp

        logger.info("primp available: %s", getattr(primp, "__version__", "unknown"))
    except ImportError:
        logger.warning("primp not available")

    assets_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "assets")
    ft.run(main, assets_dir=assets_path)
