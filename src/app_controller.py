"""AppController — business logic extracted from the old monolithic main.py.

Following the KTV Player pattern: the controller owns services, loads
persisted state, exposes a subset of methods via ControllerMethodsCtx,
and mounts the declarative UI with ``page.render()``.
"""

from __future__ import annotations

import time

import flet as ft

from core.constants import COST_OVERVIEW, PREMIUM_DAILY_CREDITS
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
from services.cache_service import cache_service
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

        # URL launching (persistent service — transient UrlLauncher has no
        # channel on mobile; this is the registered singleton)
        self.url_launcher = ft.UrlLauncher()
        self.page.services.append(self.url_launcher)
        self.page.url_launcher = self.url_launcher

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
        # Set for one call by refresh_search() to bypass a cache hit.
        self._skip_cache_once = False

        self.ad_service = AdService(self.page)
        self.update_service = UpdateService()
        state.ad_service = self.ad_service

        # ── Play Billing ────────────────────────────────────────────────
        # Not wired, and not a dependency either. The Play Console behind
        # this package has no Google Payments merchant profile, so there is
        # nothing to sell and nothing to test — KTV Player ships the same
        # way, and core/build_channel.py records the policy. Keeping the
        # package in `project.dependencies` also put a library that no
        # index serves into every platform's build, so one missing package
        # took all three down at once. `verify_purchases` and
        # `_on_purchase_updated` stay: both already return when billing is
        # None, so restoring Play Billing is this import block again.
        self.billing = None
        # ── Premium. Built here, not in a task: verify_purchases is
        # scheduled before _init_premium runs, and it reads this attribute.
        from services import premium_service

        self.premium = premium_service.PremiumService(self.page, self.storage)

        # ── Load persisted settings FIRST — the premium/ad-free flag must
        # be known before consent + preload decide whether to request ads ──
        await self._load_settings()
        await self.ad_service.gather_consent()
        await self.ad_service.preload_interstitial()

        # Scheduled crawls run while the app is open
        self.page.run_task(self._scrape_scheduler)
        # Attach to the router and snapshot the active models for the picker
        self.page.run_task(self._refresh_ai_catalog)
        # Watchdog keeps the router's live status honest for the picker.
        self.page.run_task(self._router_watchdog)
        # Cache maintenance + temp cleanup are best-effort housekeeping.
        self.page.run_task(self._cache_maintenance)
        # Premium: trust the stored token first so an offline launch still
        # works, then ask the licence service for the authoritative answer.
        self.page.run_task(self._init_premium)

        # ── Mount declarative UI ──
        from app_shell import AppShell
        from contexts.controller_ctx import ControllerMethods, ControllerMethodsCtx

        methods = ControllerMethods(
            start_search=self.start_search,
            refresh_search=self.refresh_search,
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

    async def _load_license_prices(self) -> None:
        """Fill state.license_prices from the Worker's catalog.

        Without this the Premium card shows "Choose" and no number, so a
        user is asked to commit before they know what they are committing
        to. Best effort: a missing price leaves the card on a neutral label
        rather than failing the section.
        """
        if self.premium is None or not self.premium.available:
            return
        try:
            products = await self.premium.kiri_catalog(force=True)
        except Exception as exc:
            logger.debug("license prices unavailable: %s", exc)
            return
        prices = {
            product.id: product.price_label
            for product in products
            if product.id and product.amount
        }
        if prices:
            state.license_prices = prices

    async def _init_premium(self) -> None:
        """Resolve Premium at startup from both channels.

        The stored token is verified first so a user who launches offline
        keeps what they paid for; only then do we ask the Worker, which is
        the only thing allowed to take it away. Both steps re-derive the
        flag, so a stale one can never survive either check.
        """
        try:
            was_premium = state.is_premium
            await self.premium.load_local()
            await self._load_license_prices()
            if state.is_premium and not was_premium:
                # Entitlement was proven after credits were initialised, so
                # bring a fresh day up to the premium cap now.
                await self._grant_premium_benefits()
            await self._sync_premium_storage()
            # Network round-trip: after the first frame, never on boot.
            await self.premium.reconcile()
            if state.is_premium and not was_premium:
                await self._grant_premium_benefits()
            await self._sync_premium_storage()
        except Exception:
            logger.exception("premium init failed")

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
        # Re-check the licence on resume, as the client contract asks. A
        # failure here changes nothing, so a flaky network is harmless.
        if state.is_online:
            try:
                await self.premium.reconcile()
                await self._sync_premium_storage()
            except Exception as exc:
                logger.debug("licence refresh on resume skipped: %s", exc)

    # ── Settings persistence ───────────────────────────────────────────

    async def _load_settings(self):
        """Load all persisted settings into the observable state."""
        storage = self.storage
        try:
            await storage.initialize()
            if state.credit_service:
                # Entitlement is resolved below, from the channel flags
                # rather than the persisted flag. The daily reset reads the
                # premium cap, so on a first launch (no licence record yet)
                # this uses the free cap and _init_premium tops up once the
                # licence is proven.
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
            state.ai_model = await storage.get_ai_model()
            try:
                import json as _json2

                legacy_history = _json2.loads(
                    await storage.get_assistant_history() or "[]"
                )
            except Exception:
                legacy_history = []
            await self._init_conversations(legacy_history)
            # The persisted flag is a cache from a previous run, not proof.
            # premium_service recomputes the OR from the channel flags in
            # _init_premium; trusting it here would let a stale true survive
            # with no licence token and no Play purchase.
            state.is_premium = False
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

    def _setter_map(self) -> dict:
        """key -> (storage setter coroutine, state attribute name)."""
        return {
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
            "ai_model": (self.storage.set_ai_model, "ai_model"),
            # Was never registered before 2.0 — Clear History was a silent no-op.
            "history": (self.storage.set_history, "search_history"),
        }

    def save(self, key: str, value):
        """Sync wrapper: apply to state now, persist in the background.

        Components call this from sync callbacks (on_click, on_change, etc.).
        State is updated synchronously so the control the user just touched
        repaints on that tap; the storage write is scheduled and awaited
        separately. Previously state only changed after the async write, so
        picking an Assistant model appeared to do nothing.
        """
        self._apply_state(key, value)
        self.page.run_task(self.save_setting, key, value)

    def _apply_state(self, key: str, value) -> None:
        entry = self._setter_map().get(key)
        if not entry:
            return
        state_key = entry[1]
        if key == "theme":
            theme_map = {
                "dark": ft.ThemeMode.DARK,
                "system": ft.ThemeMode.SYSTEM,
                "light": ft.ThemeMode.LIGHT,
            }
            self.page.theme_mode = theme_map.get(value, ft.ThemeMode.SYSTEM)
            state.theme_mode = self.page.theme_mode
            return
        setattr(state, state_key, value)

    async def save_setting(self, key: str, value):
        """Persist a single setting and update state.

        This is the unified setter exposed to components via context.
        """
        entry = self._setter_map().get(key)
        if not entry:
            return
        setter, state_key = entry
        await setter(value)
        if key != "theme":
            # theme is applied by _apply_state as a ThemeMode enum; assigning
            # the raw "dark"/"light" string here used to clobber it.
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
        """Cancel all running search tasks.

        The task itself is cancelled, not only flagged: a network call
        inside to_thread keeps running otherwise, so the loading screen
        stayed up until the engine timed out. The flag is still set
        because the thread checks it between pages.
        """
        self.search_service.cancel()
        for task in list(self._current_search_tasks.values()):
            if hasattr(task, "done") and not task.done():
                task.cancel()
        self._current_search_tasks.clear()
        # Publish a stopped state so the Results screen stops showing its
        # spinner; nothing else was going to update it.
        progress = getattr(state, "search_progress", None)
        if progress is not None and progress.is_running:
            progress.is_running = False
            progress.is_cancelled = True
            progress.error = None
            try:
                self.page.update()
            except Exception:
                pass

    # ── Search ─────────────────────────────────────────────────────────

    async def _init_conversations(self, legacy_history: list[dict]) -> None:
        """Load chat history, migrating the old flat list exactly once.

        Disk work is off the UI thread: this runs during init, before the
        first paint, and scanning the conversation directory must not delay
        the app appearing.
        """
        import asyncio

        from services import conversation_service as conversations

        try:
            rows = await asyncio.to_thread(conversations.list_conversations)
            if not rows and legacy_history:
                migrated = await asyncio.to_thread(
                    conversations.migrate_legacy_history, legacy_history
                )
                if migrated:
                    await conversations.clear_legacy_history(self.storage)
                    rows = await asyncio.to_thread(conversations.list_conversations)
                    await self.show_snack(
                        "Your previous Assistant chat is now in Chat history",
                        "info",
                    )
            # Re-open the chat the user was last in, not merely the newest.
            remembered = ""
            if self.storage is not None:
                try:
                    remembered = await self.storage.get_active_conversation()
                except Exception:
                    remembered = ""
            known = {r["id"] for r in rows}
            state.active_conversation = (
                remembered
                if remembered and remembered in known
                else (rows[0]["id"] if rows else conversations.new_conversation_id())
            )
            # The messages are deliberately NOT loaded here. ChatSession
            # reads the active conversation itself when it opens; caching a
            # second copy on observable state was one more owner for the
            # transcript and one more thing that could disagree with disk.
        except Exception:
            logger.exception("conversation history init failed")
            state.active_conversation = conversations.new_conversation_id()

    def is_search_running(self, search_type: str) -> bool:
        """True while a live search for this type is still in flight.

        The Results screen needs this: the cached progress on screen has
        is_running=False, so without it the banner claimed the results were
        merely "saved" for the whole background wait instead of admitting
        they were being refreshed.
        """
        task = self._current_search_tasks.get(search_type)
        return task is not None and not getattr(task, "done", lambda: True)()

    def _cache_filters(self) -> dict[str, str]:
        """Every input that changes the result set, folded into the key.

        The key used to carry only region, safe search, time limit and
        backend, so changing Max Results, any image or video filter, or the
        result page served a list produced under the previous settings
        while the banner still said "saved results". The window is snapped
        at the START of a search and reused when the result is stored, so a
        setting changed mid-search cannot file old results under new keys.
        """
        return {
            "region": state.region,
            "safesearch": state.safe_search,
            "timelimit": state.timelimit or "",
            "backend": state.backend,
            "max_results": str(state.max_results),
            "page": str(state.page),
            "proxy": "1" if state.proxy else "",
            "verify_ssl": str(bool(state.verify_ssl)),
            "threads": str(state.threads),
            # Image filters
            "image_size": state.image_size,
            "image_color": state.image_color,
            "image_type": state.image_type,
            "image_layout": state.image_layout,
            "image_license": state.image_license,
            # Video filters
            "video_quality": state.video_quality,
            "search_resolution": state.search_resolution,
            "search_duration": state.search_duration,
            "search_license": state.search_license,
        }

    def _cached_progress(
        self,
        query: str,
        search_type: str,
        filters: dict[str, str] | None = None,
    ) -> SearchProgress | None:
        """Build a finished SearchProgress from cache, or None on a miss.

        Synchronous on purpose: it is one small JSON read and the caller is
        already on a task, so there is nothing to await. `filters` is passed
        in by a search that already snapshotted them, so a setting changed
        mid-search cannot shift the key underneath it.
        """
        try:
            results = cache_service.get_cached_search(
                query, search_type, **(filters or self._cache_filters())
            )
        except Exception as exc:
            logger.warning("search cache read failed: %s", exc)
            return None
        if not results:
            return None
        return SearchProgress(
            query=query,
            search_type=search_type,
            total_results=len(results),
            loaded_results=len(results),
            is_running=False,
            results=results,
        )

    async def refresh_search(self, query: str, search_type: str = "text"):
        """Re-run a search, ignoring and repopulating the cache."""
        self._skip_cache_once = True
        try:
            await self.start_search(query, search_type)
        finally:
            self._skip_cache_once = False

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
        # waiting for the ~15s engine timeout. A cached result set beats the
        # offline card, because "no internet" is useless when the answer is
        # already on disk.
        if not state.is_online:
            if self.connectivity is not None:
                try:
                    result = await self.connectivity.get_connectivity()
                    state.is_online = ft.ConnectivityType.NONE not in result
                except Exception:
                    pass
            if not state.is_online:
                cached = self._cached_progress(query, search_type)
                if cached is not None:
                    self.cancel_search()
                    state.current_query = query
                    state.search_active = True
                    state.results_from_cache = True
                    # The overview belongs to the previous query. This
                    # branch returned before the reset further down, so a
                    # stale overview was rendered above the new results.
                    state.ai_overview = None
                    state.ai_overview_expanded = False
                    await self._refresh(cached)
                    return
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

        # Snapshotted once, used for both the cached render and the store,
        # so a filter changed while the request is in flight cannot make the
        # two disagree about which configuration these results belong to.
        cache_filters = self._cache_filters()

        # Fresh-enough results are shown immediately while the live search
        # runs underneath and replaces them (stale-while-revalidate). The
        # user gets an answer in milliseconds and still ends up current.
        if not self._skip_cache_once:
            cached = self._cached_progress(query, search_type, cache_filters)
            if cached is not None:
                state.results_from_cache = True
                state.current_query = query
                state.search_active = True
                await self._refresh(cached)

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

            # The live result supersedes whatever the cache showed.
            state.results_from_cache = False

            if getattr(progress, "is_cancelled", False):
                # A canceled search produced a truncation, not a result.
                # Caching it would overwrite a good list, writing history
                # would log a search the user abandoned, and the interstitial
                # would charge attention for it.
                logger.info("search canceled; not caching or logging it")
                progress.is_running = False
                await self._refresh(progress)
                return

            # Cache a clean result set so re-running this exact search is
            # instant. A failed or empty search is not worth remembering.
            if progress.results and not progress.error:
                try:
                    await cache_service.store_search(
                        query,
                        search_type,
                        progress.results,
                        **cache_filters,
                    )
                except Exception as exc:
                    logger.warning("search cache write failed: %s", exc)

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

            # Google-style AI overview over the results (free, router-first)
            if (
                state.ai_mode_enabled
                and search_type in ("text", "news")
                and progress.results
                and not progress.error
            ):
                self.page.run_task(self.run_ai_overview, query, progress.results)

        # Show loading state immediately
        # Show loading state immediately, unless a cached set is already on
        # screen and the live run is about to replace it.
        if state.results_from_cache:
            cached = self._cached_progress(query, search_type, cache_filters)
            if cached is not None:
                await self._refresh(cached)
            else:
                state.results_from_cache = False
        if not state.results_from_cache:
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
            await ai_service.stream_chat(
                messages, COST_OVERVIEW, on_token, model=state.ai_model
            )
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

    def open_assistant_results(self, results: list, kind: str) -> None:
        """Surface the assistant's findings in the real Results screen —
        side-effect free: no history write, no overview re-fire, no ad."""
        from core.state import SearchProgress

        search_type = {
            "web": "text",
            "images": "images",
            "videos": "videos",
            "news": "news",
            "books": "books",
        }.get(kind, "text")
        state.search_progress = SearchProgress(
            query="Assistant results",
            search_type=search_type,
            results=list(results),
            total_results=len(results),
            is_running=False,
        )
        state.last_results[search_type] = list(results)
        state.search_active = True
        state.ai_overview = None
        try:
            self.page.update()
        except Exception:
            pass

    def open_chat(self, ctx: dict | None = None) -> None:
        """Open the full-screen agentic chat (FAB entry)."""
        from screens.chat_screen import open_chat_view

        open_chat_view(self.page, ctx)

    def on_view_pop(self, e=None) -> None:
        """Back/gesture pop.

        Leaving the Assistant minimizes it: the session is retained and the
        FAB becomes a restore button, so the conversation is never lost to
        an accidental back. Anything else goes home as before.
        """
        if state.chat_open:
            state.chat_open = False
            state.chat_minimized = True
            session = getattr(self.page, "_chat_session", None)
            if session is not None:
                try:
                    session._persist_history()
                except Exception:
                    pass
            try:
                self.page.update()
            except Exception:
                pass
            return
        self.go_home()

    # ── Premium (Play Billing and/or Kiri License) ───────────────────────

    async def _grant_premium_benefits(self) -> bool:
        """Top up to the premium credit cap once, on the first activation."""
        first_time = not state.is_premium
        if (
            first_time
            and state.credit_service
            and state.credits_remaining < PREMIUM_DAILY_CREDITS
        ):
            await state.credit_service.add_credits(
                PREMIUM_DAILY_CREDITS - state.credits_remaining
            )
        return first_time

    async def _sync_premium_storage(self) -> None:
        if self.storage:
            try:
                await self.storage.set_is_premium(bool(state.is_premium))
            except Exception as exc:
                logger.warning("premium flag save failed: %s", exc)

    async def activate_premium(self, product_id: str) -> None:
        """Play Billing purchase: grant through the entitlement arbiter.

        This no longer latches a permanent local boolean. The Play channel
        sets its own flag and the arbiter resolves the OR with the license
        channel, so a license-only user is unaffected and either channel can
        be withdrawn.
        """

        if not str(product_id).startswith("premium"):
            return
        was_premium = state.is_premium
        self.premium.set_play_entitlement(True, product_id=product_id)
        first_time = await self._grant_premium_benefits()
        await self._sync_premium_storage()
        if first_time and not was_premium:
            await self.show_snack(
                "Premium active. Ads off, 200 assistant credits/day.", "success"
            )

    async def verify_purchases(self) -> None:  # client-side re-check; server-side
        # verification (Play Developer API on your backend) is the Play-review
        # gate and is tracked as an infra task — the client never trusts the
        # local flag beyond what Play itself reports.
        """Re-check owned products on launch — never trust the local flag alone."""

        billing = getattr(self, "billing", None)
        if billing is None:
            return
        try:
            result = await billing.query_past_purchases()
            owned = [p.product_id for p in (getattr(result, "purchases", None) or [])]
            found = next(
                (pid for pid in owned if str(pid).startswith("premium")), None
            )
            was_premium = state.is_premium
            self.premium.set_play_entitlement(
                bool(found), product_id=str(found or "")
            )
            if found and not was_premium:
                await self._grant_premium_benefits()
            await self._sync_premium_storage()
        except Exception as exc:
            # A failed re-check must never revoke a working entitlement.
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

    async def _refresh_ai_catalog(self):
        """Snapshot the router's active models (fills the model picker)."""
        from services import ai_service

        try:
            await ai_service.refresh_catalog()
        except Exception:
            logger.exception("AI catalog snapshot failed")

    async def _router_watchdog(self) -> None:
        """Poll router health so the model picker can report the truth.

        Only reports liveness; the model catalog has its own 5-minute
        refresh. A single failed tick must never kill the watchdog, and the
        status is only written when it actually changes so the observable
        does not trigger a repaint every 3 seconds.
        """
        import asyncio

        from services import ai_service

        while True:
            try:
                status, port = await ai_service.probe_router()
                changed = (
                    state.ai_router_status != status
                    or state.ai_router_port != port
                )
                if changed:
                    state.ai_router_status = status
                    state.ai_router_port = port
                    logger.info("router status: %s (port %s)", status, port)
                    # An open Assistant shows the router state in its header
                    # pill, and that pill is a static control, so nudge it.
                    session = getattr(self.page, "_chat_session", None)
                    if state.chat_open and session is not None:
                        try:
                            session.refresh_model_chip()
                        except Exception:
                            pass
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                logger.debug("router watchdog tick failed: %s", exc)
            await asyncio.sleep(3)

    async def _cache_maintenance(self) -> None:
        """Clear temp/ once, then prune the cache every 30 minutes."""
        import asyncio

        from core.storage_paths import clear_temp

        try:
            removed = clear_temp()
            if removed:
                logger.info("cleared %d temp entries at startup", removed)
            stats = await cache_service.prune()
            if stats["removed"]:
                logger.info(
                    "cache pruned at startup: %d entries, %.1f KB",
                    stats["removed"],
                    stats["freed"] / 1024,
                )
        except Exception:
            logger.exception("cache maintenance failed")

        while True:
            await asyncio.sleep(30 * 60)
            try:
                await cache_service.prune()
            except asyncio.CancelledError:
                raise
            except Exception:
                logger.exception("cache prune failed")

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
                if int(now // 60) % 5 == 0:
                    # Keep picker hints (latency / rate limits) fresh
                    from services import ai_service as _ai

                    await _ai.refresh_catalog()
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
        """Synchronous exit hook: stop the turn, flush storage, stop the router.

        The turn is stopped FIRST, while the loop is still alive. Left
        running, it throws once during render and again while settling
        credits, and the conversation is never written — which is exactly
        the destroyed-session cascade in the crash log.
        """
        from services import ai_service

        session = getattr(self.page, "_chat_session", None)
        if session is not None:
            try:
                session.shutdown()
            except Exception:
                logger.debug("assistant shutdown failed")
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
