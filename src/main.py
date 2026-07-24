from __future__ import annotations

import time

import flet as ft

from core.state import SearchProgress, state
from core.theme import AppTheme
from core.utils import log_error, log_performance, log_search_event, logger
from services.ad_service import AdService
from services.search_service import _DDGS_AVAILABLE, SearchService
from services.storage_service import StorageService

LOG_TAG = "Main"


async def main(page: ft.Page):
    page.title = "DDGS"
    page.favicon = "icon.png"

    page.fonts = {
        "Outfit": "https://fonts.googleapis.com/css2?family=Outfit:wght@300;400;500;600;700&display=swap"
    }
    page.theme = AppTheme.get_light_theme()
    page.dark_theme = AppTheme.get_dark_theme()
    page.theme.font_family = "Outfit"
    page.dark_theme.font_family = "Outfit"
    page.theme_mode = ft.ThemeMode.SYSTEM
    page.window.min_width = 360
    page.window.min_height = 600
    page.padding = 0
    page.spacing = 0

    file_picker = ft.FilePicker()
    page.services.append(file_picker)
    page.file_picker = file_picker

    logger.info(f"[{LOG_TAG}] Starting DDGS UI. DDGS available: {_DDGS_AVAILABLE}")

    def on_error(e):
        logger.error(f"[{LOG_TAG}] Page error: {e.data}")

    page.on_error = on_error

    storage = StorageService(page)
    search_service = SearchService()

    ad_service = AdService(page)
    state.ad_service = ad_service
    page.run_task(ad_service.preload_interstitial)

    try:
        t = await storage.get_theme()
        page.theme_mode = {
            "dark": ft.ThemeMode.DARK,
            "system": ft.ThemeMode.SYSTEM,
            "light": ft.ThemeMode.LIGHT,
        }.get(t, ft.ThemeMode.SYSTEM)
        state.theme_mode = page.theme_mode

        state.safe_search = await storage.get_safe_search()
        state.region = await storage.get_region()
        state.max_results = await storage.get_max_results()
        state.timelimit = await storage.get_timelimit()
        state.backend = await storage.get_backend()
        state.page = await storage.get_page()
        state.proxy = await storage.get_proxy()
        state.verify_ssl = await storage.get_verify_ssl()
        state.threads = await storage.get_threads()
        state.extract_format = await storage.get_extract_format()
        state.api_url = await storage.get_api_url()
        state.spawn_api = await storage.get_spawn_api()
        state.default_tab = await storage.get_default_tab()
        state.video_quality = await storage.get_video_quality()
        state.search_history = await storage.get_history() or []

        logger.info(f"[{LOG_TAG}] Settings loaded")
    except (
        ValueError,
        TypeError,
        OSError,
        RuntimeError,
        ConnectionError,
        ImportError,
        KeyError,
        IndexError,
        AttributeError,
    ) as e:
        log_error(f"[{LOG_TAG}] Settings load", e)

    async def navigate(route: str):
        page.route = route
        await route_change()

    from core.theme import AppColors

    def navigate_sync(route: str):
        page.run_task(navigate, route)

    current_search_tasks: dict[str, object] = {}

    routes = ["/home", "/history", "/settings"]

    def _build_nav_bar(active_route: str) -> ft.NavigationBar | None:
        if active_route == "/onboarding":
            return None
        r_active = "/home" if active_route in ("/", "") else active_route
        selected_index = 0
        if r_active == "/history":
            selected_index = 1
        elif r_active == "/settings":
            selected_index = 2

        new_nav_bar = ft.NavigationBar(
            selected_index=selected_index,
            destinations=[
                ft.NavigationBarDestination(
                    icon=ft.Icons.HOME_OUTLINED,
                    selected_icon=ft.Icons.HOME_ROUNDED,
                    label="Home",
                ),
                ft.NavigationBarDestination(
                    icon=ft.Icons.HISTORY_OUTLINED,
                    selected_icon=ft.Icons.HISTORY_ROUNDED,
                    label="History",
                ),
                ft.NavigationBarDestination(
                    icon=ft.Icons.SETTINGS_OUTLINED,
                    selected_icon=ft.Icons.SETTINGS_ROUNDED,
                    label="Settings",
                ),
            ],
            bgcolor=ft.Colors.SURFACE,
            indicator_color=ft.Colors.with_opacity(0.12, AppColors.PRIMARY),
            label_behavior=ft.NavigationBarLabelBehavior.ALWAYS_SHOW,
        )

        def on_nav_change(e):
            for task in current_search_tasks.values():
                if hasattr(task, "done") and not task.done():
                    search_service.cancel()
            current_search_tasks.clear()
            page.run_task(navigate, routes[e.control.selected_index])

        new_nav_bar.on_change = on_nav_change
        return new_nav_bar

    async def run_extract(url: str):
        from core.utils import sanitize_url

        sanitized = sanitize_url(url)
        if not sanitized:
            page.snack_bar = ft.SnackBar(
                ft.Text("Invalid URL format. Please provide a valid web link."),
                bgcolor=AppColors.ERROR,
            )
            page.snack_bar.open = True
            page.update()
            return
        url = sanitized

        progress = SearchProgress(query=url, search_type="extract", is_running=True)
        state.search_progress = progress
        from views.results import build_results_view

        def show_view(extract_result=None):
            page.views.clear()
            v = build_results_view(
                page,
                progress,
                navigate_sync,
                lambda q: page.run_task(run_extract, q),
                lambda: page.run_task(cancel_and_go_home),
                extract_result=extract_result,
            )
            page.views.append(v)
            nb = _build_nav_bar(page.route)
            if nb:
                v.navigation_bar = nb
            page.update()

        show_view()
        result, error_msg = await search_service.extract_url(
            url, fmt=state.extract_format
        )
        progress.is_running = False
        progress.error = error_msg
        state.extract_result = result

        try:
            await storage.add_history(
                {
                    "query": url,
                    "search_type": "extract",
                    "results_count": 1 if result else 0,
                    "timestamp": time.strftime("%Y-%m-%d %H:%M"),
                }
            )
            state.search_history = await storage.get_history()
        except (
            ValueError,
            TypeError,
            OSError,
            RuntimeError,
            ConnectionError,
            ImportError,
            KeyError,
            IndexError,
            AttributeError,
        ) as ex:
            logger.warning(f"Extract history save failed: {ex}")

        show_view(result)

        if state.ad_service:
            await state.ad_service.show_interstitial()

    async def start_search(query: str, search_type: str = "text"):
        if not query or not query.strip():
            return
        query = query.strip()

        if search_type == "extract":
            await run_extract(query)
            return

        nonlocal current_search_tasks
        for task in current_search_tasks.values():
            if hasattr(task, "done") and not task.done():
                search_service.cancel()
        current_search_tasks.clear()

        state.current_query = query
        log_search_event("search_start", query=query, search_type=search_type)

        async def run_search():
            perf_start = time.perf_counter()
            progress = await search_service.search(
                search_type, query, on_progress=lambda p: page.run_task(_refresh, p)
            )
            perf_elapsed = time.perf_counter() - perf_start
            log_performance(
                f"search_{search_type}",
                perf_elapsed,
                query=query,
                results=len(progress.results),
            )

            try:
                await storage.add_history(
                    {
                        "query": query,
                        "search_type": search_type,
                        "results_count": len(progress.results),
                        "timestamp": time.strftime("%Y-%m-%d %H:%M"),
                    }
                )
                state.search_history = await storage.get_history()
            except (
                ValueError,
                TypeError,
                OSError,
                RuntimeError,
                ConnectionError,
                ImportError,
                KeyError,
                IndexError,
                AttributeError,
            ) as ex:
                logger.warning(f"Search history save failed: {ex}")

            await _refresh(progress)

            if progress.error and "primp" in str(progress.error).lower():
                logger.critical(
                    f"[{LOG_TAG}] PRIMP_CRASH: {search_type} \u2014 {progress.error}"
                )

        async def _refresh(progress: SearchProgress):
            page.views.clear()
            from views.results import build_results_view

            v = build_results_view(
                page,
                progress,
                navigate_sync,
                lambda q, st=None: page.run_task(
                    start_search, q, st or progress.search_type
                ),
                lambda: page.run_task(cancel_and_go_home),
            )
            page.views.append(v)
            nb = _build_nav_bar(page.route)
            if nb:
                v.navigation_bar = nb
            page.update()

        loading = SearchProgress(
            query=query, search_type=search_type, total_results=0, is_running=True
        )
        await _refresh(loading)
        task = page.run_task(run_search)
        current_search_tasks[search_type] = task

    async def cancel_and_go_home():
        search_service.cancel()
        current_search_tasks.clear()
        await navigate("/home")

    async def route_change(e=None):
        nonlocal current_search_tasks
        route = page.route

        onb = await storage.get_onboarding_done()
        if not onb and route != "/onboarding":
            await navigate("/onboarding")
            return

        page.views.clear()

        if route in ("/home", "/"):
            from views.home import build_home_view

            v = build_home_view(
                page,
                navigate_sync,
                storage,
                lambda q, t: page.run_task(start_search, q, t),
            )
            page.views.append(v)
        elif route == "/history":
            from views.history_view import build_history_view

            v = build_history_view(
                page,
                navigate_sync,
                lambda q, t="text": page.run_task(start_search, q, t),
                storage,
            )
            page.views.append(v)
        elif route == "/settings":
            from views.settings import build_settings_view

            v = build_settings_view(page, navigate_sync, storage)
            page.views.append(v)
        elif route == "/onboarding":
            from views.onboarding_view import build_onboarding_view

            v = build_onboarding_view(page, lambda: navigate_sync("/home"), storage)
            page.views.append(v)
        else:
            from views.home_view import build_home_view

            v = build_home_view(
                page,
                navigate_sync,
                storage,
                lambda q, t: page.run_task(start_search, q, t),
            )
            page.views.append(v)

        if page.views:
            nb = _build_nav_bar(route)
            if nb:
                page.views[-1].navigation_bar = nb
        page.update()

    async def view_pop(e):
        for task in current_search_tasks.values():
            if hasattr(task, "done") and not task.done():
                search_service.cancel()
        current_search_tasks.clear()
        page.views.pop()
        if page.views:
            page.route = page.views[-1].route
        page.update()

    page.on_route_change = route_change
    page.on_view_pop = view_pop
    page.on_disconnect = lambda e: page.run_task(storage.flush)

    logger.info(f"[{LOG_TAG}] Initialized. Navigating home.")
    await navigate("/home")


if __name__ == "__main__":
    logger.info(f"[{LOG_TAG}] Starting DDGS UI on Python {__import__('sys').version}")
    try:
        import primp

        logger.info(
            f"[{LOG_TAG}] primp available: {getattr(primp, '__version__', 'unknown')}"
        )
    except ImportError:
        logger.warning(f"[{LOG_TAG}] primp not available")
    import os

    assets_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "assets")
    ft.run(main, assets_dir=assets_path)
