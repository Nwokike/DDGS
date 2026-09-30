"""Utility functions and logging."""

from __future__ import annotations

import logging
import os
import sys
import tempfile
import time
from collections.abc import Callable
from functools import wraps
from logging.handlers import RotatingFileHandler

# The log file used to grow without bound: one new file per run, kept
# forever. 2 MB x 3 backups per run plus a 14-day sweep keeps the logs
# directory useful for debugging without letting it fill the device.
LOG_MAX_BYTES = 2 * 1024 * 1024
LOG_BACKUP_COUNT = 3
LOG_RETENTION_DAYS = 14


def prune_old_logs(folder: str, days: int = LOG_RETENTION_DAYS) -> int:
    """Delete log files last written more than `days` ago. Returns count."""
    cutoff = time.time() - days * 86400
    removed = 0
    try:
        names = os.listdir(folder)
    except OSError:
        return 0
    for name in names:
        # RotatingFileHandler writes app_<ts>.log.1, .log.2 ... which do not
        # end in .log, so the sweep used to skip every rotated backup and
        # they accumulated forever. Match the run prefix instead.
        if not name.startswith("app_") or ".log" not in name:
            continue
        path = os.path.join(folder, name)
        try:
            if os.path.getmtime(path) < cutoff:
                os.remove(path)
                removed += 1
        except OSError:
            continue
    return removed


class InMemoryLogHandler(logging.Handler):
    def __init__(self, limit=200):
        super().__init__()
        self.limit = limit
        self.records = []

    def emit(self, record):
        try:
            msg = self.format(record)
            self.records.append(msg)
            if len(self.records) > self.limit:
                self.records.pop(0)
        except (
            ValueError,
            TypeError,
            OSError,
            RuntimeError,
            ConnectionError,
            ImportError,
        ):
            self.handleError(record)


in_memory_log_handler = InMemoryLogHandler()


def _log_dir_candidates() -> list[str]:
    """Where log files may live, best tier first.

    Per .flet/README the log home is data/ (durable app data - the phone
    already writes files/data/logs), resolved by the single storage
    resolver. Two emergency fallbacks remain for environments where
    data/ itself is unwritable; they are deliberately scratch-tier.
    """
    from core.storage_paths import data_dir

    return [
        str(data_dir() / "logs"),
        os.path.join(tempfile.gettempdir(), "ddgs_ui", "logs"),
        os.path.join(os.getcwd(), "logs"),
    ]


def setup_logging():
    log_dirs = _log_dir_candidates()

    file_handler = None
    log_file_path = None

    for folder in log_dirs:
        if not folder:
            continue
        try:
            os.makedirs(folder, exist_ok=True)
            log_file = os.path.join(folder, f"app_{time.strftime('%Y%m%d_%H%M%S')}.log")
            # Verify write access by writing a dummy file
            test_path = os.path.join(folder, ".test_write")
            with open(test_path, "w") as f:
                f.write("test")
            os.remove(test_path)

            prune_old_logs(folder)

            # Writable folder found!
            file_handler = RotatingFileHandler(
                log_file,
                maxBytes=LOG_MAX_BYTES,
                backupCount=LOG_BACKUP_COUNT,
                encoding="utf-8",
            )
            log_file_path = log_file
            break
        except (PermissionError, OSError):
            continue

    # Standard console handler
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(logging.INFO)
    console_handler.setFormatter(
        logging.Formatter(
            "%(asctime)s [%(name)s] %(levelname)s: %(message)s",
            datefmt="%H:%M:%S",
        )
    )

    # In-memory log handler formatter
    in_memory_log_handler.setLevel(logging.DEBUG)
    in_memory_log_handler.setFormatter(
        logging.Formatter(
            "%(asctime)s [%(name)s] %(levelname)s: %(message)s",
            datefmt="%H:%M:%S",
        )
    )

    # Root logging configuration
    root_handlers = [console_handler, in_memory_log_handler]
    if file_handler:
        file_handler.setLevel(logging.DEBUG)
        file_handler.setFormatter(
            logging.Formatter(
                "%(asctime)s [%(name)s] %(levelname)s: %(message)s",
                datefmt="%H:%M:%S",
            )
        )
        root_handlers.append(file_handler)

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
        datefmt="%H:%M:%S",
        handlers=root_handlers,
    )

    logger = logging.getLogger("ddgs_ui")
    logger.setLevel(logging.DEBUG)
    logger.propagate = False

    for h in root_handlers:
        logger.addHandler(h)

    if log_file_path:
        logger.info(f"Logging initialized. Log file: {log_file_path}")
    else:
        logger.warning(
            "Logging initialized. Console-only (no writable file path found)."
        )

    return logger


logger = setup_logging()


def log_function_call(func: Callable) -> Callable:
    """Decorator to log function calls with args and return values."""

    @wraps(func)
    def _wrapper(*args, **kwargs):
        args_repr = [repr(a) for a in args[1:]] if args else []
        kwargs_repr = [f"{k}={v!r}" for k, v in kwargs.items()]
        signature = ", ".join(args_repr + kwargs_repr)
        logger.debug(f"→ {func.__name__}({signature})")
        start_time = time.perf_counter()
        try:
            result = func(*args, **kwargs)
            elapsed = time.perf_counter() - start_time
            logger.debug(
                f"← {func.__name__} completed in {elapsed:.3f}s: {type(result).__name__}"
            )
            return result
        except (
            ValueError,
            TypeError,
            OSError,
            RuntimeError,
            ConnectionError,
            ImportError,
        ) as e:
            elapsed = time.perf_counter() - start_time
            logger.exception(f"← {func.__name__} failed in {elapsed:.3f}s: {e}")  # noqa: TRY401
            raise

    return _wrapper


def log_async_function_call(func: Callable) -> Callable:
    """Decorator to log async function calls."""

    @wraps(func)
    async def _wrapper(*args, **kwargs):
        args_repr = [repr(a) for a in args[1:]] if args else []
        kwargs_repr = [f"{k}={v!r}" for k, v in kwargs.items()]
        signature = ", ".join(args_repr + kwargs_repr)
        logger.debug(f"→ async {func.__name__}({signature})")
        start_time = time.perf_counter()
        try:
            result = await func(*args, **kwargs)
            elapsed = time.perf_counter() - start_time
            logger.debug(
                f"← async {func.__name__} completed in {elapsed:.3f}s: {type(result).__name__}"
            )
            return result
        except (
            ValueError,
            TypeError,
            OSError,
            RuntimeError,
            ConnectionError,
            ImportError,
        ) as e:
            elapsed = time.perf_counter() - start_time
            logger.exception(f"← async {func.__name__} failed in {elapsed:.3f}s: {e}")  # noqa: TRY401
            raise

    return _wrapper


def log_search_event(event: str, **data):
    """Log search-related events with structured data."""
    log_data = {"event": event, **data}
    logger.info(f"SEARCH_EVENT: {log_data}")


def log_error(context: str, error: Exception, **extra):
    """Log errors with context."""
    logger.error(f"ERROR in {context}: {error}", extra=extra)


def log_performance(operation: str, duration: float, **metrics):
    """Log performance metrics."""
    logger.info(f"PERF: {operation} took {duration:.3f}s | {metrics}")


def log_ddgs_call(
    method: str,
    query: str,
    params: dict,
    result_count: int | None = None,
    error: Exception | None = None,
):
    """Log DDGS API calls for debugging primp issues."""
    log_data = {
        "method": method,
        "query": query,
        "params": params,
        "result_count": result_count,
    }
    if error:
        log_data["error"] = str(error)
        log_data["error_type"] = type(error).__name__
        logger.error(f"DDGS_CALL_FAILED: {log_data}")
    else:
        logger.debug(f"DDGS_CALL: {log_data}")


def is_web_url(url: str) -> bool:
    """True for http(s) only - the schemes an in-app fetch may perform.

    Link taps in Markdown views arrive from untrusted content (scraped
    pages, model replies), so `javascript:`, `file:`, `data:` and friends
    must never reach a fetch or a launcher.
    """
    return isinstance(url, str) and url.lower().startswith(("http://", "https://"))


def resolve_url(base_url: str, link: str) -> str | None:
    """Resolve a tapped link against the page it came from.

    Returns the absolute http(s) URL to fetch, or None for anything that
    must never be fetched (empty, fragment, mailto, `javascript:`). The
    scheme guard runs AFTER urljoin: urljoin keeps foreign schemes
    (`javascript:alert(1)` survives it), so resolving first is what makes
    relative links (`../`, `?q`, `./path`) work and guarding second is
    what keeps them safe. One resolver for every surface - extract card,
    preview sheet, reader - so they can never disagree again.
    """
    import urllib.parse

    if not link or link.startswith(("#", "mailto:")):
        return None
    resolved = link
    if not is_web_url(link):
        if not base_url:
            return None
        resolved = urllib.parse.urljoin(base_url, link)
    if not is_web_url(resolved):
        return None
    return resolved


class FetchNav:
    """Per-surface back stack + tap pacing for fetched pages.

    One instance per surface (Reader view, preview sheet) instead of the
    old module-global list, so two open surfaces can never bleed history
    into each other. Rapid taps are debounced: a second link press inside
    `debounce` seconds is ignored instead of stacking duplicate fetches.
    """

    __slots__ = ("_stack", "_last_tap", "_depth", "_debounce")

    def __init__(self, max_depth: int = 25, debounce: float = 0.3) -> None:
        self._stack: list[str] = []
        self._last_tap = 0.0
        self._depth = max_depth
        self._debounce = debounce

    def push(self, url: str) -> None:
        """Remember the page we are leaving (no consecutive duplicates)."""
        if url and (not self._stack or self._stack[-1] != url):
            self._stack.append(url)
            if len(self._stack) > self._depth:
                self._stack.pop(0)

    def pop(self) -> str | None:
        return self._stack.pop() if self._stack else None

    @property
    def can_back(self) -> bool:
        return bool(self._stack)

    def clear(self) -> None:
        self._stack.clear()

    def allow_tap(self) -> bool:
        """Debounce gate: True at most once per `debounce` seconds."""
        now = time.monotonic()
        if now - self._last_tap < self._debounce:
            return False
        self._last_tap = now
        return True


async def set_extract_format(page, fmt: str) -> None:
    """One writer for the extract format: observable state + persistence.

    Every format switcher (extract card, preview sheet, reader) calls
    this instead of hand-rolling state assignment and storage writes, so
    the setting can never diverge between surfaces again.
    """
    from core.state import state

    state.extract_format = fmt
    ctrl = getattr(page, "_ddgs_controller", None)
    try:
        if ctrl and ctrl.storage:
            await ctrl.save_setting("extract_format", fmt)
    except Exception:
        pass


def is_launchable_url(url: str) -> bool:
    """True for schemes the system browser/mail handler may be opened with."""
    return is_web_url(url) or (
        isinstance(url, str) and url.lower().startswith("mailto:")
    )


def display_host(host: str) -> str:
    """Decode a punycode host for humans: xn--mnchen-3ya -> münchen.

    Clicks, copies and requests keep the raw host - only display text
    changes. Invalid punycode passes through untouched.
    """
    import idna

    try:
        return idna.decode(host, uts46=True, display=True)
    except Exception:
        return host


def display_url(url: str) -> str:
    """Pretty-print a result URL with its host decoded for display."""
    import urllib.parse

    if not is_web_url(url):
        return url
    parsed = urllib.parse.urlsplit(url)
    host = parsed.hostname
    if not host:
        return url
    pretty = display_host(host)
    if pretty == host:
        return url
    netloc = pretty
    if parsed.username:
        netloc = f"{parsed.username}:{parsed.password or ''}@{netloc}"
    if parsed.port:
        netloc = f"{netloc}:{parsed.port}"
    return urllib.parse.urlunsplit(
        (parsed.scheme, netloc, parsed.path, parsed.query, parsed.fragment)
    )


def sanitize_url(url: str) -> str | None:
    """Validate and sanitize URL. Prepend https:// if it looks like a domain name.
    Return None if completely invalid (e.g. contains spaces or no dots).
    """
    import urllib.parse

    url = url.strip()
    if not url:
        return None

    # Check if there are spaces (not a valid URL)
    if " " in url:
        return None

    parsed = urllib.parse.urlparse(url)

    # If it lacks a scheme, check if it has a dot and looks like a domain/host
    if not parsed.scheme:
        if "." in url:
            url = "https://" + url
            parsed = urllib.parse.urlparse(url)
        else:
            return None

    if not parsed.netloc:
        return None

    return url


# ── Error classification ─────────────────────────────────────────────────
# Centralizes the offline/server/rate-limit keyword matching that was
# previously duplicated (and slightly different) across the results and
# reader components.  Components call classify_error() instead of matching
# strings themselves.

# Sentinel set by the fail-fast search path when the device is known to be
# offline *before* any network request is attempted.  Checked before keyword
# matching so the offline UI is unambiguous.
ERR_NO_INTERNET = "ddgs:no_internet"

# Order matters: rate-limit is checked first so a throttled response is not
# misread as an offline error.
_RATE_LIMIT_KEYWORDS = (
    "rate limit",
    "rate-limit",
    "ratelimit",
    "too many requests",
    "429",
    "418",
)

_OFFLINE_KEYWORDS = (
    "dns",
    "connect",
    "network",
    "offline",
    "unreachable",
    "timed out",
    "timeout",
    "refused",
    "no internet",
)

_SERVER_ERROR_KEYWORDS = (
    "500",
    "502",
    "503",
    "504",
    "server error",
)


def classify_error(error: str | None) -> str:
    """Classify a search/network error string into a UI category.

    Returns one of ``"offline"``, ``"server"``, ``"rate_limit"``, or
    ``"other"``.  An empty/None error classifies as ``"other"``.
    """
    if not error:
        return "other"
    err = str(error)
    if err == ERR_NO_INTERNET:
        return "offline"
    err_l = err.lower()
    if any(kw in err_l for kw in _RATE_LIMIT_KEYWORDS):
        return "rate_limit"
    if any(kw in err_l for kw in _OFFLINE_KEYWORDS):
        return "offline"
    if any(kw in err_l for kw in _SERVER_ERROR_KEYWORDS):
        return "server"
    return "other"
