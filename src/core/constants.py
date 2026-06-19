"""Application constants — all storage keys."""

STORAGE_THEME = "theme"
STORAGE_HISTORY = "search_history"
STORAGE_SAFE_SEARCH = "safe_search"
STORAGE_REGION = "region"
STORAGE_MAX_RESULTS = "max_results"
STORAGE_ONBOARDING_DONE = "onboarding_done"
STORAGE_DEFAULT_TAB = "default_tab"
STORAGE_TIMELIMIT = "timelimit"
STORAGE_BACKEND = "backend"
STORAGE_PROXY = "proxy"
STORAGE_VERIFY_SSL = "verify_ssl"
STORAGE_THREADS = "threads"
STORAGE_PAGE = "page"
STORAGE_EXTRACT_FORMAT = "extract_format"
STORAGE_API_URL = "api_url"
STORAGE_SPAWN_API = "spawn_api"

BACKEND_OPTIONS_TEXT = [
    {"key": "auto", "label": "Auto (recommended)"},
    {"key": "duckduckgo", "label": "DuckDuckGo"},
    {"key": "google", "label": "Google"},
    {"key": "brave", "label": "Brave"},
    {"key": "bing", "label": "Bing"},
    {"key": "yahoo", "label": "Yahoo"},
    {"key": "yandex", "label": "Yandex"},
    {"key": "startpage", "label": "Startpage"},
    {"key": "mojeek", "label": "Mojeek"},
    {"key": "wikipedia", "label": "Wikipedia"},
    {"key": "grokipedia", "label": "Grokipedia"},
]

BACKEND_OPTIONS_IMAGES = [
    {"key": "auto", "label": "Auto (recommended)"},
    {"key": "duckduckgo", "label": "DuckDuckGo"},
    {"key": "bing", "label": "Bing"},
]

BACKEND_OPTIONS_NEWS = [
    {"key": "auto", "label": "Auto (recommended)"},
    {"key": "duckduckgo", "label": "DuckDuckGo"},
    {"key": "bing", "label": "Bing"},
    {"key": "yahoo", "label": "Yahoo"},
]

BACKEND_OPTIONS_VIDEOS = [
    {"key": "auto", "label": "Auto (recommended)"},
    {"key": "duckduckgo", "label": "DuckDuckGo"},
]

BACKEND_OPTIONS_BOOKS = [
    {"key": "auto", "label": "Auto (recommended)"},
    {"key": "annasarchive", "label": "Anna's Archive"},
]

TIMELIMIT_OPTIONS = [
    {"key": "", "label": "Any time"},
    {"key": "d", "label": "Past day"},
    {"key": "w", "label": "Past week"},
    {"key": "m", "label": "Past month"},
    {"key": "y", "label": "Past year"},
]

EXTRACT_FORMATS = [
    {"key": "text_markdown", "label": "Markdown"},
    {"key": "text_plain", "label": "Plain Text"},
    {"key": "text_rich", "label": "Rich Text"},
    {"key": "text", "label": "Raw HTML"},
    {"key": "content", "label": "Raw Bytes"},
]

REGIONS = [
    {"key": "wt-wt", "label": "All Regions"},
    {"key": "us-en", "label": "United States (English)"},
    {"key": "uk-en", "label": "United Kingdom (English)"},
    {"key": "de-de", "label": "Germany (Deutsch)"},
    {"key": "fr-fr", "label": "France (Français)"},
    {"key": "jp-jp", "label": "Japan (日本語)"},
    {"key": "br-pt", "label": "Brazil (Português)"},
    {"key": "in-en", "label": "India (English)"},
    {"key": "ca-en", "label": "Canada (English)"},
    {"key": "au-en", "label": "Australia (English)"},
    {"key": "ru-ru", "label": "Russia (Русский)"},
    {"key": "es-es", "label": "Spain (Español)"},
    {"key": "it-it", "label": "Italy (Italiano)"},
]

SAFE_SEARCH_OPTIONS = [
    {"key": "off", "label": "Off"},
    {"key": "moderate", "label": "Moderate"},
    {"key": "on", "label": "Strict"},
]

MAX_RESULTS_PRESETS = [
    {"key": 10, "label": "10"},
    {"key": 25, "label": "25"},
    {"key": 50, "label": "50"},
    {"key": 100, "label": "100"},
]
