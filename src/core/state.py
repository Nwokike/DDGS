"""Application state — @ft.observable singleton for reactive component tree.

Following the KTV Player pattern: plain attribute mutations auto-notify
subscribed components via use_context(AppStateCtx).  SearchProgress and
SearchResult are plain dataclasses — they are stored *inside* AppState
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
    results: list[SearchResult] = field(default_factory=list)


@ft.observable
class AppState:
    """Global reactive state — every field mutation triggers re-render
    in components that read it via use_context(AppStateCtx)."""

    def __init__(self):
        # ── Navigation ──
        self.selected_tab: int = 0          # 0=Home, 1=History, 2=Settings
        self.search_active: bool = False     # Results screen visible
        self.has_accepted_terms: bool = False

        # ── Search settings ──
        self.safe_search: str = "moderate"
        self.region: str = "wt-wt"
        self.max_results: int = 20
        self.timelimit: str = ""
        self.backend: str = "auto"
        self.page: int = 1

        # ── Connection ──
        self.proxy: str = ""
        self.verify_ssl: bool = True
        self.threads: int = 0

        # ── Extraction ──
        self.extract_format: str = "text_markdown"

        # ── Advanced ──
        self.api_url: str = ""
        self.spawn_api: bool = False

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

        # ── Services (set by AppController) ──
        self.ad_service = None

    def reset(self):
        """Reset transient search state (for testing)."""
        self.search_active = False
        self.current_query = ""
        self.search_progress = None
        self.last_results = {}
        self.extract_result = None


state = AppState()
