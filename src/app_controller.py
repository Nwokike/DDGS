"""AppController — business logic extracted from the old monolithic main.py.

Following the KTV Player pattern: the controller owns services, loads
persisted state, exposes a subset of methods via ControllerMethodsCtx,
and mounts the declarative UI with ``page.render()``.
"""

from __future__ import annotations

import time

import flet as ft

from core.state import SearchProgress, state
from core.theme import AppTheme
from core.utils import (
    log_error,
    log_performance,
    log_search_event,
    logger,
    sanitize_url,
)
from services.ad_service import AdService
from services.search_service import SearchService
from services.storage_service import StorageService

LOG_TAG = "AppController"


class AppController:
    """Owns all services and business logic.  Mounts the declarative UI."""

    def __init__(self, page: ft.Page):
        self.page = page
        self.storage: StorageService | None = None
        self.search_service: SearchService | None = None
        self.ad_service: AdService | None = None
        self._current_search_tasks: dict[str, object] = {}

    async def init(self):
        """Initialize page, services, load persisted state, mount UI."""
        # ── Page setup ──
        self.page.title = "DDGS"
        self.page.favicon = "icon.png"
        self.page.fonts = {
            "Outfit": "https://fonts.googleapis.com/css2?family=Outfit:wght@300;400;500;600;700&display=swap"
        }
        self.page.theme = AppTheme.get_light_theme()
        self.page.dark_theme = AppTheme.get_dark_theme()
        self.page.theme.font_family = "Outfit"
        self.page.dark_theme.font_family = "Outfit"
        self.page.theme_mode = ft.ThemeMode.SYSTEM
        self.page.window.min_width = 360
        self.page.window.min_height = 600
        self.page.padding = 0
        self.page.spacing = 0

        # FilePicker service (singleton, registered once)
        file_picker = ft.FilePicker()
        self.page.services.append(file_picker)
        self.page.file_picker = file_picker

        # Global error handler
        def on_error(e):
            logger.error(f"[{LOG_TAG}] Page error: {e.data}")

        self.page.on_error = on_error

        # ── Services ──
        self.storage = StorageService(self.page)
        self.search_service = SearchService()

        self.ad_service = AdService(self.page)
        state.ad_service = self.ad_service
        await self.ad_service.gather_consent()
        await self.ad_service.preload_interstitial()

        # ── Load persisted settings ──
        await self._load_settings()

        # ── Mount declarative UI ──
        from app_shell import AppShell
        from contexts.controller_ctx import ControllerMethods, ControllerMethodsCtx

        methods = ControllerMethods(
            start_search=self.start_search,
            run_extract=self.run_extract,
            cancel_search=self.cancel_search,
            go_home=self.go_home,
            navigate_tab=self.navigate_tab,
            open_content_reader=self.open_content_reader,
            save=self.save,
            save_async=self.save_setting,
            show_snack=self.show_snack,
        )
        self.page.render(lambda: ControllerMethodsCtx(methods, lambda: AppShell()))
        # Store controller reference on page for access from plain functions
        self.page._ddgs_controller = self
        logger.info(f"[{LOG_TAG}] UI mounted")

    # ── Settings persistence ───────────────────────────────────────────

    async def _load_settings(self):
        """Load all persisted settings into the observable state."""
        storage = self.storage
        try:
            t = await storage.get_theme()
            self.page.theme_mode = {
                "dark": ft.ThemeMode.DARK,
                "system": ft.ThemeMode.SYSTEM,
                "light": ft.ThemeMode.LIGHT,
            }.get(t, ft.ThemeMode.SYSTEM)
            state.theme_mode = self.page.theme_mode

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
            state.has_accepted_terms = await storage.get_onboarding_done()

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

    def save(self, key: str, value):
        """Sync wrapper — schedules save_setting as a background task.

        Components call this from sync callbacks (on_click, on_change, etc.).
        """
        self.page.run_task(self.save_setting, key, value)

    async def save_setting(self, key: str, value):
        """Persist a single setting and update state.

        This is the unified setter exposed to components via context.
        """
        setter_map = {
            "theme": (self.storage.set_theme, "theme_mode"),
            "safe_search": (self.storage.set_safe_search, "safe_search"),
            "region": (self.storage.set_region, "region"),
            "max_results": (self.storage.set_max_results, "max_results"),
            "timelimit": (self.storage.set_timelimit, "timelimit"),
            "backend": (self.storage.set_backend, "backend"),
            "proxy": (self.storage.set_proxy, "proxy"),
            "verify_ssl": (self.storage.set_verify_ssl, "verify_ssl"),
            "threads": (self.storage.set_threads, "threads"),
            "extract_format": (self.storage.set_extract_format, "extract_format"),
            "api_url": (self.storage.set_api_url, "api_url"),
            "spawn_api": (self.storage.set_spawn_api, "spawn_api"),
            "default_tab": (self.storage.set_default_tab, "default_tab"),
            "video_quality": (self.storage.set_video_quality, "video_quality"),
            "onboarding_done": (self.storage.set_onboarding_done, "has_accepted_terms"),
        }

        if key == "theme":
            theme_map = {
                "dark": ft.ThemeMode.DARK,
                "system": ft.ThemeMode.SYSTEM,
                "light": ft.ThemeMode.LIGHT,
            }
            self.page.theme_mode = theme_map.get(value, ft.ThemeMode.SYSTEM)
            state.theme_mode = self.page.theme_mode

        if key in setter_map:
            setter, state_key = setter_map[key]
            await setter(value)
            setattr(state, state_key, value)

    # ── Navigation ─────────────────────────────────────────────────────

    def navigate_tab(self, tab_index: int):
        """Switch to a tab (0=Home, 1=History, 2=Settings)."""
        # Cancel any running search when navigating away
        self.cancel_search()
        state.selected_tab = tab_index
        state.search_active = False

    async def go_home(self):
        """Cancel search and return to home tab."""
        self.cancel_search()
        state.search_active = False
        state.selected_tab = 0

    def open_content_reader(self, url: str, content: str | None = None):
        """Push the full-screen content reader as a new View."""
        from screens.content_reader_screen import build_content_reader

        reader_view = build_content_reader(self.page, url, content)
        self.page.views.append(reader_view)
        self.page.update()

    def cancel_search(self):
        """Cancel all running search tasks."""
        for task in self._current_search_tasks.values():
            if hasattr(task, "done") and not task.done():
                self.search_service.cancel()
        self._current_search_tasks.clear()

    # ── Search ─────────────────────────────────────────────────────────

    async def start_search(self, query: str, search_type: str = "text"):
        """Execute a search and update state with progress/results."""
        if not query or not query.strip():
            return
        query = query.strip()

        if search_type == "extract":
            await self.run_extract(query)
            return

        # Cancel prior tasks
        self.cancel_search()

        state.current_query = query
        state.search_active = True
        log_search_event("search_start", query=query, search_type=search_type)

        async def _run_search():
            perf_start = time.perf_counter()
            progress = await self.search_service.search(
                search_type,
                query,
                on_progress=lambda p: self.page.run_task(self._refresh, p),
            )
            perf_elapsed = time.perf_counter() - perf_start
            log_performance(
                f"search_{search_type}",
                perf_elapsed,
                query=query,
                results=len(progress.results),
            )

            # Persist to history
            try:
                await self.storage.add_history(
                    {
                        "query": query,
                        "search_type": search_type,
                        "results_count": len(progress.results),
                        "timestamp": time.strftime("%Y-%m-%d %H:%M"),
                    }
                )
                state.search_history = await self.storage.get_history()
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

            await self._refresh(progress)

            if progress.error and "primp" in str(progress.error).lower():
                logger.critical(
                    f"[{LOG_TAG}] PRIMP_CRASH: {search_type} — {progress.error}"
                )

        # Show loading state immediately
        loading = SearchProgress(
            query=query, search_type=search_type, total_results=0, is_running=True
        )
        await self._refresh(loading)

        task = self.page.run_task(_run_search)
        self._current_search_tasks[search_type] = task

    async def run_extract(self, url: str):
        """Extract content from a URL and display results."""
        sanitized = sanitize_url(url)
        if not sanitized:
            await self.show_snack(
                "Invalid URL format. Please provide a valid web link.",
                "error",
            )
            return
        url = sanitized

        state.search_active = True
        progress = SearchProgress(query=url, search_type="extract", is_running=True)
        state.search_progress = progress
        state.extract_result = None

        # Show loading state
        await self._refresh(progress)

        result, error_msg = await self.search_service.extract_url(
            url, fmt=state.extract_format
        )
        progress.is_running = False
        progress.error = error_msg
        state.extract_result = result

        # Persist to history
        try:
            await self.storage.add_history(
                {
                    "query": url,
                    "search_type": "extract",
                    "results_count": 1 if result else 0,
                    "timestamp": time.strftime("%Y-%m-%d %H:%M"),
                }
            )
            state.search_history = await self.storage.get_history()
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

        await self._refresh(progress)

        if state.ad_service:
            await state.ad_service.show_interstitial()

    async def _refresh(self, progress: SearchProgress):
        """Update the observable state with new search progress.

        The ResultsScreen component subscribes to state.search_progress
        and re-renders automatically via use_context(AppStateCtx).
        """
        state.search_progress = progress

    # ── SnackBar ───────────────────────────────────────────────────────

    async def show_snack(self, message: str, level: str = "info"):
        """Show a SnackBar notification."""
        from core.theme import AppColors

        bg = {
            "error": AppColors.ERROR,
            "success": AppColors.SUCCESS,
            "warning": AppColors.WARNING,
        }.get(level, AppColors.PRIMARY)

        self.page.snack_bar = ft.SnackBar(
            ft.Text(message),
            bgcolor=bg,
        )
        self.page.snack_bar.open = True
        self.page.update()
