"""Application state - @ft.observable singleton for reactive component tree.

Following the KTV Player pattern: plain attribute mutations auto-notify
subscribed components via use_context(AppStateCtx).  SearchProgress and
SearchResult are plain dataclasses - they are stored *inside* AppState
and swapped as whole objects (not mutated in-place) so the observable
notify fires on the parent field assignment.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import flet as ft


@dataclass
class SearchResult:
    title: str
    url: str
    snippet: str
    search_type: str = "text"
    thumbnail: str | None = None
    image_url: str | None = None
    width: int | None = None
    height: int | None = None
    source: str | None = None
    duration: str | None = None
    embed_url: str | None = None
    publisher: str | None = None
    views: int | None = None
    published: str | None = None
    date: str | None = None
    raw_data: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self):
        raw = self.raw_data
        if not self.publisher and raw.get("publisher"):
            self.publisher = raw["publisher"]
        if not self.views and raw.get("statistics"):
            try:
                self.views = int(raw["statistics"].get("viewCount", 0))
            except (ValueError, AttributeError):
                pass


@dataclass
class SearchProgress:
    query: str
    search_type: str = "text"
    total_results: int = 0
    loaded_results: int = 0
    is_running: bool = False
    is_cancelled: bool = False
    error: str | None = None
    # True only when the engine explicitly rate-limited (e.g. DDGS 429/418 on
    # video search). Drives the dedicated rate-limit box; other errors
    # (offline, primp crash, unavailable) must NOT be mislabeled as
    # rate-limited.
    is_rate_limited: bool = False
    results: list[SearchResult] = field(default_factory=list)


@dataclass
class AiOverview:
    """Google-style AI overview for the current text/news result set.

    Whole-object swaps only (observable notify fires on AppState assignment).
    """

    query: str = ""
    text: str = ""
    related: list[str] = field(default_factory=list)
    sources: list[dict] = field(default_factory=list)  # {title, url}
    is_running: bool = False
    is_done: bool = False
    error: str | None = None  # credits | unavailable | midstream


@ft.observable
class AppState:
    """Global reactive state - every field mutation triggers re-render
    in components that read it via use_context(AppStateCtx)."""

    def __init__(self):
        # ── Navigation ──
        self.selected_tab: int = 0  # 0=Home, 1=History, 2=Settings
        self.search_active: bool = False  # Results screen visible
        self.has_accepted_terms: bool = False
        self.update_available: bool = False
        self.update_data: dict | None = None

        # ── Search settings ──
        self.safe_search: str = "moderate"
        self.region: str = "wt-wt"
        self.max_results: int = 20
        self.timelimit: str = ""
        self.backend: str = "auto"
        self.page: int = 1
        # Per-category filters ("" = no filter; ddgs 9.16 pass-through params)
        self.image_size: str = ""
        self.image_color: str = ""
        self.image_type: str = ""
        self.image_layout: str = ""
        self.image_license: str = ""
        self.search_resolution: str = ""
        self.search_duration: str = ""
        self.search_license: str = ""

        # ── Connection ──
        self.proxy: str = ""
        self.verify_ssl: bool = True
        self.threads: int = 0
        # Live connectivity, driven by the native ft.Connectivity service
        # (AppController). True until proven otherwise so a slow probe never
        # shows a spurious offline banner.
        self.is_online: bool = True

        # ── Extraction ──
        self.extract_format: str = "text_markdown"

        # ── UI ──
        self.default_tab: str = "text"
        self.video_quality: str = "best"
        self.theme_mode: ft.ThemeMode = ft.ThemeMode.SYSTEM

        # ── Search runtime ──
        self.current_query: str = ""
        self.search_progress: SearchProgress | None = None
        self.last_results: dict[str, list[SearchResult]] = {}
        self.extract_result: dict | None = None

        # ── History ──
        self.search_history: list[dict] = []

        # ── Ad tracking ──
        self.last_interstitial_ts: float = 0.0  # central 90s gap guard

        # ── AI mode (DDGS 2.0) - chat via the Ask Assistant FAB ──
        self.ai_mode_enabled: bool = True
        self.ai_model: str = "auto"  # router model preference; auto rotates free models
        self.credits_remaining: int = 50  # corrected by CreditService.initialize()
        self.is_premium: bool = False
        # Which channel granted Premium, and whether each says yes. The
        # is_premium flag above is derived from these by
        # services/premium_service, so a refund can actually take it back.
        self.play_premium_active: bool = False
        self.license_premium_active: bool = False
        self.premium_source: str = ""
        self.license_status: str = ""
        self.license_product: str = ""
        self.license_recovery_id: str = ""
        # Live prices pulled from the Worker's /catalog so the Premium card
        # never asks anyone to pay an amount it has not shown them.
        # product_id -> "USD 3.99"
        self.license_prices: dict = {}
        self.ad_cooldown_end: float = 0.0
        self.chat_open: bool = False
        # True when the Assistant is retained but another screen is on top.
        # The FAB becomes a restore button in this state.
        self.chat_minimized: bool = False
        self.ai_overview: AiOverview | None = None
        self.ai_overview_expanded: bool = False
        self.scheduled_scrapes: list = []  # [{url, interval_min, next_run, last_run, pages_saved}]
        # Router lifecycle, mirroring LM Router's gateway states so the
        # model picker can say what is actually happening.
        self.ai_router_status: str = "starting"  # starting|ready|stopped|unavailable
        self.ai_router_port: int | None = None
        # True while the results on screen came from the cache and a live
        # search is still running behind them.
        self.results_from_cache: bool = False
        # Conversations (chat history): summary rows + the active id.
        self.active_conversation: str = ""

        # ── Services (set by AppController) ──
        self.ad_service = None
        self.credit_service = None

    def reset(self):
        """Reset transient search state (for testing)."""
        self.search_active = False
        self.current_query = ""
        self.search_progress = None
        self.last_results = {}
        self.extract_result = None
        self.is_online = True


state = AppState()
