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
STORAGE_VIDEO_QUALITY = "video_quality"
STORAGE_IMAGE_SIZE = "image_size"
STORAGE_IMAGE_COLOR = "image_color"
STORAGE_IMAGE_TYPE = "image_type"
STORAGE_IMAGE_LAYOUT = "image_layout"
STORAGE_IMAGE_LICENSE = "image_license"
STORAGE_SEARCH_RESOLUTION = "search_resolution"
STORAGE_SEARCH_DURATION = "search_duration"
STORAGE_SEARCH_LICENSE = "search_license"
STORAGE_SCHEDULED_SCRAPES = "scheduled_scrapes"
STORAGE_AI_MODEL = "ai_model"
STORAGE_ASSISTANT_HISTORY = "assistant_history"
STORAGE_ACTIVE_CONVERSATION = "active_conversation"

# Kiri License (direct/web channel). Deliberately separate from
# STORAGE_IS_PREMIUM, which is the *resolved* entitlement written by
# whichever channel granted it, so either can be revoked independently.
STORAGE_LICENSE_RECOVERY_ID = "license_recovery_id"
STORAGE_LICENSE_TOKEN = "license_token"
STORAGE_LICENSE_STATUS = "license_status"
STORAGE_LICENSE_PRODUCT = "license_product"
STORAGE_LICENSE_PAID_THROUGH = "license_paid_through"
STORAGE_LICENSE_EMAIL = "license_email"
STORAGE_LICENSE_NAME = "license_name"
STORAGE_LICENSE_PHONE = "license_phone"

# ── Kiri License (external checkout for every surface Play cannot bill) ──
KIRI_LICENSE_BASE_URL = "https://license.kiri.ng"
KIRI_LICENSE_PUBLIC_KEY = (
    "MFkwEwYHKoZIzj0CAQYIKoZIzj0DAQcDQgAE-YfZ-yKdG3wYF1IR0XcpJH4RclAB"
    "nddMmAGXFI2J8sbC4gWY2POKc8hVrn0_uHxDZ9ufzwzg4buUimW-IEw4Uw"
)
# Stable app identifier sent to the Worker. The same value is used for
# checkout, restore and status — a temporary install id would orphan
# purchases on reinstall.
KIRI_LICENSE_APP_ID = "ng.kiri.ddgs"
KIRI_LICENSE_TIMEOUT = 15.0

BACKEND_OPTIONS_TEXT = [
    {"key": "auto", "label": "Auto (recommended)"},
    {"key": "duckduckgo", "label": "DuckDuckGo"},
    {"key": "google", "label": "Google"},
    {"key": "brave", "label": "Brave"},
    {"key": "yahoo", "label": "Yahoo"},
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

# ddgs 9.16 image/video search filters. Values mirror ddgs/cli.py choices;
# "" means "don't send the param" (engine default = no filtering).
IMAGE_SIZE_OPTIONS = [
    {"key": "", "label": "Any size"},
    {"key": "Small", "label": "Small"},
    {"key": "Medium", "label": "Medium"},
    {"key": "Large", "label": "Large"},
    {"key": "Wallpaper", "label": "Wallpaper"},
]

IMAGE_COLOR_OPTIONS = [
    {"key": "", "label": "Any color"},
    {"key": "Monochrome", "label": "Monochrome"},
    {"key": "Red", "label": "Red"},
    {"key": "Orange", "label": "Orange"},
    {"key": "Yellow", "label": "Yellow"},
    {"key": "Green", "label": "Green"},
    {"key": "Blue", "label": "Blue"},
    {"key": "Purple", "label": "Purple"},
    {"key": "Pink", "label": "Pink"},
    {"key": "Brown", "label": "Brown"},
    {"key": "Black", "label": "Black"},
    {"key": "Gray", "label": "Gray"},
    {"key": "Teal", "label": "Teal"},
    {"key": "White", "label": "White"},
]

IMAGE_TYPE_OPTIONS = [
    {"key": "", "label": "Any type"},
    {"key": "photo", "label": "Photo"},
    {"key": "clipart", "label": "Clipart"},
    {"key": "gif", "label": "GIF"},
    {"key": "transparent", "label": "Transparent"},
    {"key": "line", "label": "Line drawing"},
]

IMAGE_LAYOUT_OPTIONS = [
    {"key": "", "label": "Any layout"},
    {"key": "Square", "label": "Square"},
    {"key": "Tall", "label": "Tall"},
    {"key": "Wide", "label": "Wide"},
]

IMAGE_LICENSE_OPTIONS = [
    {"key": "", "label": "Any license"},
    {"key": "Public", "label": "Public"},
    {"key": "Share", "label": "Share"},
    {"key": "ShareCommercially", "label": "Share commercially"},
    {"key": "Modify", "label": "Modify"},
    {"key": "ModifyCommercially", "label": "Modify commercially"},
]

VIDEO_RESOLUTION_OPTIONS = [
    {"key": "", "label": "Any resolution"},
    {"key": "high", "label": "High"},
    {"key": "standart", "label": "Standard"},
]

VIDEO_DURATION_OPTIONS = [
    {"key": "", "label": "Any duration"},
    {"key": "short", "label": "Short (<4 min)"},
    {"key": "medium", "label": "Medium (4-20 min)"},
    {"key": "long", "label": "Long (>20 min)"},
]

VIDEO_LICENSE_OPTIONS = [
    {"key": "", "label": "Any license"},
    {"key": "creativeCommon", "label": "Creative Commons"},
    {"key": "youtube", "label": "YouTube license"},
]

# ── AI mode (DDGS 2.0) ───────────────────────────────────────────────────
DAILY_FREE_CREDITS = 50
PREMIUM_DAILY_CREDITS = 200
COST_STEP = 1  # one Assistant step = one model call
COST_OVERVIEW = 0  # passive search overview is free
COST_SUMMARY = 0  # passive page summary is free
AD_TOPUP_CREDITS = 2
AD_TOPUP_COOLDOWN_SEC = 30.0
AGENT_MAX_ITERS = 6  # model calls per turn (worst case AGENT_MAX_ITERS * COST_STEP)
AGENT_MAX_TOOLS = 10  # tool calls per turn
AGENT_TIMEOUT_S = 240  # wall-clock per turn
TOOL_OUTPUT_CAP = 2000  # chars of tool output re-sent per loop
AGENT_HISTORY_MESSAGES = 6


def credit_word(count: int) -> str:
    """Price copy that cannot go plural-blind: 1 credit, 3 credits.

    Every sentence quoting a credit price runs through here, so changing
    COST_STEP cannot leave "1 credits" behind in one place and "2 credit"
    in another.
    """
    return f"{count} credit" if count == 1 else f"{count} credits"

STORAGE_AI_MODE = "ai_mode_enabled"
STORAGE_IS_PREMIUM = "is_premium"
STORAGE_CREDITS = "ddgs_credits"
STORAGE_LAST_RESET = "ddgs_last_reset"

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

VIDEO_QUALITY_OPTIONS = [
    {"key": "best", "label": "Best available"},
    {"key": "1080p", "label": "1080p"},
    {"key": "720p", "label": "720p"},
    {"key": "480p", "label": "480p"},
    {"key": "360p", "label": "360p"},
]
