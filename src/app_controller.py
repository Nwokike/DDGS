"""AppController — business logic extracted from the old monolithic main.py.

Following the KTV Player pattern: the controller owns services, loads
persisted state, exposes a subset of methods via ControllerMethodsCtx,
and mounts the declarative UI with ``page.render()``.
"""

from __future__ import annotations

import time

import flet as ft

from core.constants import COST_CHAT, PREMIUM_DAILY_CREDITS
from core.state import AiOverview, SearchProgress, state
from core.theme import AppTheme
from core.utils import (
    ERR_NO_INTERNET,
    log_error,
    log_performance,
    log_search_event,
    logger,
    sanitize_url,
)
from services.ad_service import AdService
from services.credit_service import init_credit_service
from services.search_service import SearchService
from services.storage_service import StorageService
from services.update_service import UpdateService

LOG_TAG = "AppController"


class AppController:
    """Owns all services and business logic.  Mounts the declarative UI."""

    def __init__(self, page: ft.Page):
        self.page = page
        self.storage: StorageService | None = None
        self.search_service: SearchService | None = None
        self.ad_service: AdService | None = None
        self.connectivity: ft.Connectivity | None = None
        self.update_service: UpdateService | None = None
        self._current_search_tasks: dict[str, object] = {}

    async def init(self):
        """Initialize page, services, load persisted state, mount UI."""
        # ── Page setup ──
        self.page.title = "DDGS"
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

        # ── Connectivity service (native OS listener) ──
        # Drives state.is_online: probed once at startup, then on every OS
        # change and on app resume.  See _on_connectivity_change,
        # _init_connectivity, and _on_lifecycle_change.
        connectivity = ft.Connectivity()
        self.connectivity = connectivity
        self.page.services.append(connectivity)
        connectivity.on_change = self._on_connectivity_change
        self.page.on_app_lifecycle_state_change = self._on_lifecycle_change
        self.page.run_task(self._init_connectivity)

        # ── Services ──
        self.storage = StorageService(self.page)
        state.credit_service = init_credit_service(self.storage)
        self.search_service = SearchService()

        self.ad_service = AdService(self.page)
        self.update_service = UpdateService()
        state.ad_service = self.ad_service

        # ── Billing (Android only; flet-billing wraps Play Billing) ──
        self.billing = None
        if self.page.platform == ft.PagePlatform.ANDROID:
            try:
                from flet_billing import Billing

                # Construction auto-registers the service (flet 1.0.1).
                self.billing = Billing(
                    on_purchase_updated=self._on_purchase_updated,
                    on_error=lambda e: logger.error("billing error: %s", e.message),
                )
                self.page.run_task(self.verify_purchases)
            except Exception as exc:
                logger.warning("billing unavailable: %s", exc)
        # ── Load persisted settings FIRST — the premium/ad-free flag must
        # be known before consent + preload decide whether to request ads ──
        await self._load_settings()
        await self.ad_service.gather_consent()
        await self.ad_service.preload_interstitial()

        # Scheduled crawls run while the app is open
        self.page.run_task(self._scrape_scheduler)

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
        self.page.run_task(self.check_for_updates)

    async def check_for_updates(self):
        if not self.update_service:
            return
        data = await self.update_service.check_for_update()
        if data:
            state.update_available = True
            state.update_data = data
            try:
                self.page.update()
            except Exception:
                pass
            if data.get("mandatory"):
                self.open_update_dialog()

    def open_update_dialog(self):
        if state.update_available and state.update_data:
            from components.update_dialog import show_update_dialog

            show_update_dialog(self.page, state.update_data)
        logger.info(f"[{LOG_TAG}] UI mounted")

    # ── Connectivity ───────────────────────────────────────────────────────
    async def _init_connectivity(self):
        """Set state.is_online from an initial connectivity probe at startup."""
        try:
            result = await self.connectivity.get_connectivity()
            state.is_online = ft.ConnectivityType.NONE not in result
        except Exception:
            state.is_online = True

    def _on_connectivity_change(self, e):
        """Flip state.is_online on an OS-level connectivity change and notify."""
        try:
            types = getattr(e, "connectivity", None) or [e.data]
        except Exception:
            types = [ft.ConnectivityType.NONE]
        was_online = state.is_online
        state.is_online = ft.ConnectivityType.NONE not in types
        if was_online and not state.is_online:
            logger.warning("Connectivity lost")
            self.page.run_task(self.show_snack, "You're offline.", "warning")
        elif not was_online and state.is_online:
            logger.info("Connectivity restored")
            self.page.run_task(self.show_snack, "You're back online.", "info")

    async def _on_lifecycle_change(self, e: ft.AppLifecycleStateChangeEvent):
        """Flush storage when backgrounded; re-probe connectivity when foregrounded."""
        if e.state in (
            ft.AppLifecycleState.HIDE,
            ft.AppLifecycleState.PAUSE,
            ft.AppLifecycleState.DETACH,
        ):
            if self.storage:
                try:
                    await self.storage.flush()
                except Exception as exc:
                    logger.warning("Lifecycle storage flush failed: %s", exc)
            return
        if e.state not in (ft.AppLifecycleState.RESUME, ft.AppLifecycleState.SHOW):
            return
        try:
            result = await self.connectivity.get_connectivity()
            state.is_online = ft.ConnectivityType.NONE not in result
        except Exception as exc:
            logger.warning("Lifecycle connectivity probe failed: %s", exc)

    # ── Settings persistence ───────────────────────────────────────────

    async def _load_settings(self):
        """Load all persisted settings into the observable state."""
        storage = self.storage
        try:
            await storage.initialize()
            if state.credit_service:
                state.credits_remaining = await state.credit_service.initialize()
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
            state.image_size = await storage.get_image_size()
            state.image_color = await storage.get_image_color()
            state.image_type = await storage.get_image_type()
            state.image_layout = await storage.get_image_layout()
            state.image_license = await storage.get_image_license()
            state.search_resolution = await storage.get_search_resolution()
            state.search_duration = await storage.get_search_duration()
            state.search_license = await storage.get_search_license()
            state.proxy = await storage.get_proxy()
            state.verify_ssl = await storage.get_verify_ssl()
            state.threads = await storage.get_threads()
            state.extract_format = await storage.get_extract_format()
            state.default_tab = await storage.get_default_tab()
            state.video_quality = await storage.get_video_quality()
            state.search_history = await storage.get_history() or []
            state.has_accepted_terms = await storage.get_onboarding_done()
            state.ai_mode_enabled = await storage.get_ai_mode()
            state.is_premium = await storage.get_is_premium()
            import json as _json

            try:
                state.scheduled_scrapes = _json.loads(
                    await storage.get_scheduled_scrapes() or "[]"
                )
            except Exception:
                state.scheduled_scrapes = []

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
            "image_size": (self.storage.set_image_size, "image_size"),
            "image_color": (self.storage.set_image_color, "image_color"),
            "image_type": (self.storage.set_image_type, "image_type"),
            "image_layout": (self.storage.set_image_layout, "image_layout"),
            "image_license": (self.storage.set_image_license, "image_license"),
            "search_resolution": (
                self.storage.set_search_resolution,
                "search_resolution",
            ),
            "search_duration": (self.storage.set_search_duration, "search_duration"),
            "search_license": (self.storage.set_search_license, "search_license"),
            "proxy": (self.storage.set_proxy, "proxy"),
            "verify_ssl": (self.storage.set_verify_ssl, "verify_ssl"),
            "threads": (self.storage.set_threads, "threads"),
            "extract_format": (self.storage.set_extract_format, "extract_format"),
            "default_tab": (self.storage.set_default_tab, "default_tab"),
            "video_quality": (self.storage.set_video_quality, "video_quality"),
            "onboarding_done": (self.storage.set_onboarding_done, "has_accepted_terms"),
            "ai_mode": (self.storage.set_ai_mode, "ai_mode_enabled"),
            # Was never registered before 2.0 — Clear History was a silent no-op.
            "history": (self.storage.set_history, "search_history"),
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

        # Fail fast when offline: re-probe once in case the connection just
        # came back, then surface the offline card immediately instead of
        # waiting for the ~15s engine timeout.
        if not state.is_online:
            if self.connectivity is not None:
                try:
                    result = await self.connectivity.get_connectivity()
                    state.is_online = ft.ConnectivityType.NONE not in result
                except Exception:
                    pass
            if not state.is_online:
                progress = SearchProgress(
                    query=query,
                    search_type=search_type,
                    total_results=0,
                    is_running=False,
                    error=ERR_NO_INTERNET,
                )
                state.current_query = query
                state.search_active = True
                await self._refresh(progress)
                return

        # Cancel prior tasks
        self.cancel_search()

        state.current_query = query
        state.search_active = True
        state.ai_overview = None
        state.ai_overview_expanded = False
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
                await self.storage.flush()
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

            # Interstitial on every search (Sherlock-parity frequency);
            # the 90s minimum gap is enforced centrally in AdService.
            state.search_count += 1
            if not state.is_premium and state.ad_service:
                await state.ad_service.show_interstitial()

            if progress.error and "primp" in str(progress.error).lower():
                logger.critical(
                    f"[{LOG_TAG}] PRIMP_CRASH: {search_type} — {progress.error}"
                )

            # Google-style AI overview over the results (1 credit, router-first)
            if (
                state.ai_mode_enabled
                and search_type in ("text", "news")
                and progress.results
                and not progress.error
            ):
                self.page.run_task(self.run_ai_overview, query, progress.results)

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
            await self.storage.flush()
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

        if not state.is_premium and state.ad_service:
            await state.ad_service.show_interstitial()

    async def _refresh(self, progress: SearchProgress):
        """Update the observable state with new search progress.

        The ResultsScreen component subscribes to state.search_progress
        and re-renders automatically via use_context(AppStateCtx).
        """
        state.search_progress = progress

    # ── AI chat (Ask-AI FAB) ──────────────────────────────────────────────

    async def run_ai_overview(self, query: str, results) -> None:
        """Passive Google-style summary above normal text/news results."""
        from dataclasses import replace

        from services import ai_service

        sources = [
            {"title": r.title, "url": r.url, "snippet": r.snippet} for r in results[:8]
        ]
        overview = AiOverview(
            query=query,
            sources=[{"title": s["title"], "url": s["url"], "thumb": getattr(r, "thumbnail", "") or ""} for r, s in zip(results[:8], sources)],
            is_running=True,
        )
        state.ai_overview = overview
        buffer = {"text": "", "last": 0.0}

        def on_token(token: str) -> None:
            buffer["text"] += token
            now = time.monotonic()
            if now - buffer["last"] >= 0.2:
                buffer["last"] = now
                state.ai_overview = replace(overview, text=buffer["text"])

        messages = ai_service.build_overview_messages(query, sources)
        try:
            await ai_service.stream_chat(messages, COST_CHAT, on_token)
            clean, related = ai_service.parse_related(buffer["text"])
            state.ai_overview = replace(
                overview,
                text=ai_service.link_citations(clean, [s["url"] for s in sources]),
                related=related,
                is_running=False,
                is_done=True,
            )
        except ai_service.NotEnoughCredits:
            state.ai_overview = replace(overview, is_running=False, error="credits")
        except ai_service.AIMidStream:
            state.ai_overview = replace(
                overview, text=buffer["text"], is_running=False, error="midstream"
            )
        except ai_service.AIUnavailable:
            state.ai_overview = replace(overview, is_running=False, error="unavailable")
        except Exception as exc:
            log_error(f"[{LOG_TAG}] AI overview", exc, query=query)
            state.ai_overview = replace(overview, is_running=False, error="unavailable")

    def open_chat(self, ctx: dict | None = None) -> None:
        """Open the full-screen agentic chat (FAB entry)."""
        from screens.chat_screen import open_chat_view

        open_chat_view(self.page, ctx)

    def on_view_pop(self, e=None) -> None:
        """Back/gesture pop: leaving chat only clears its flag; else go home."""
        if state.chat_open:
            state.chat_open = False
            try:
                self.page.update()
            except Exception:
                pass
            return
        self.go_home()

    # ── Premium (flet-billing, mobile-only) ───────────────────────────────

    async def activate_premium(self, product_id: str) -> None:
        """Grant the premium entitlement (server verification lands with the
        gateway endpoint; interim re-check is verify_purchases each launch)."""
        if not str(product_id).startswith("premium"):
            return
        first_time = not state.is_premium
        state.is_premium = True
        if self.storage:
            await self.storage.set_is_premium(True)
        if state.credit_service and state.credits_remaining < PREMIUM_DAILY_CREDITS:
            await state.credit_service.add_credits(
                PREMIUM_DAILY_CREDITS - state.credits_remaining
            )
        if first_time:
            await self.show_snack(
                "Premium active — ads off, 200 AI credits/day.", "success"
            )

    async def verify_purchases(self) -> None:
        """Re-check owned products on launch — never trust the local flag alone."""
        billing = getattr(self, "billing", None)
        if billing is None:
            return
        try:
            result = await billing.query_past_purchases()
            owned = [p.product_id for p in (getattr(result, "purchases", None) or [])]
            for pid in owned:
                if str(pid).startswith("premium"):
                    await self.activate_premium(pid)
                    break
        except Exception as exc:
            logger.debug("purchase re-check skipped: %s", exc)

    async def _on_purchase_updated(self, e) -> None:
        """flet-billing event: verify → deliver → acknowledge (3-day rule)."""
        try:
            from flet_billing import PurchaseStatus
        except ImportError:
            return
        for p in e.purchases:
            if p.status in (PurchaseStatus.PURCHASED, PurchaseStatus.RESTORED):
                await self.activate_premium(p.product_id)
                if (
                    getattr(p, "pending_complete_purchase", False)
                    and p.purchase_id
                    and self.billing is not None
                ):
                    try:
                        await self.billing.complete_purchase(p.purchase_id)
                    except Exception as exc:
                        logger.warning("complete_purchase failed: %s", exc)
            elif p.status == PurchaseStatus.ERROR:
                logger.error("purchase error: %s", getattr(p, "error", None))
            elif p.status == PurchaseStatus.CANCELED:
                logger.info("purchase canceled: %s", p.product_id)

    async def _scrape_scheduler(self):
        """Run due scheduled crawls every 60s while the app is open."""
        import asyncio

        from services import agent_files
        from services.chat_agent import _persist_schedule, _svc

        while True:
            try:
                now = time.time()
                due = [
                    t for t in state.scheduled_scrapes if (t.get("next_run") or 0) <= now
                ]
                for task in due:
                    url = task.get("url") or ""
                    try:
                        report = await agent_files.scrape_site(
                            url, max_pages=5, fmt="text_markdown", svc=_svc()
                        )
                        task["pages_saved"] = len(report.get("saved") or [])
                    except Exception as exc:
                        logger.warning("scheduled crawl failed for %s: %r", url, exc)
                        task["pages_saved"] = 0
                    task["last_run"] = now
                    task["next_run"] = now + max(
                        15, int(task.get("interval_minutes") or 60)
                    ) * 60
                if due:
                    await _persist_schedule()
                    logger.info("scheduled crawls completed: %d", len(due))
            except asyncio.CancelledError:
                raise
            except Exception:
                logger.exception("scrape scheduler tick failed")
            await asyncio.sleep(60)

    async def cancel_scheduled_scrape(self, url: str) -> None:
        """Remove a scheduled crawl (settings UI)."""
        from services.chat_agent import _persist_schedule

        state.scheduled_scrapes = [
            t for t in state.scheduled_scrapes if t.get("url") != url
        ]
        await _persist_schedule()

    def on_app_close(self, e=None) -> None:
        """Synchronous exit hook: flush storage + stop the embedded router."""
        from services import ai_service

        if self.storage:
            self.storage.flush_now()
        ai_service.shutdown()

    # ── SnackBar ───────────────────────────────────────────────────────

    async def show_snack(self, message: str, level: str = "info"):
        """Show a SnackBar notification."""
        from core.theme import AppColors

        bg = {
            "error": AppColors.ERROR,
            "success": AppColors.SUCCESS,
            "warning": AppColors.WARNING,
        }.get(level, AppColors.PRIMARY)

        snack = ft.SnackBar(ft.Text(message), bgcolor=bg)
        snack.open = True
        self.page.show_dialog(snack)
        self.page.update()
