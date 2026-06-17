"""Global application state — mirrors every DDGS parameter."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class SearchResult:
    """Unified search result across all search types."""

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


@dataclass
class SearchProgress:
    """Progress tracking for searches."""

    query: str
    search_type: str = "text"
    total_results: int = 0
    loaded_results: int = 0
    is_running: bool = False
    is_cancelled: bool = False
    error: str | None = None
    results: list[SearchResult] = field(default_factory=list)


class AppState:
    """Singleton — mirrors every DDGS configuration option."""

    def __init__(self):
        # Search settings
        self.safe_search: str = "moderate"
        self.region: str = "wt-wt"
        self.max_results: int = 20
        self.timelimit: str = ""
        self.backend: str = "auto"
        self.page: int = 1

        # Connection settings
        self.proxy: str = ""
        self.verify_ssl: bool = True
        self.threads: int = 0

        # Extract settings
        self.extract_format: str = "text_markdown"

        # Advanced (DHT network)
        self.api_url: str = ""
        self.spawn_api: bool = False

        # UI state
        self.default_tab: str = "text"
        self.current_query: str = ""
        self.search_history: list[dict] = []
        self.search_progress: SearchProgress | None = None
        self.last_results: dict[str, list[SearchResult]] = {}
        self.extract_result: dict | None = None


state = AppState()
