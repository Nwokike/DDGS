"""Utility functions and logging."""

from __future__ import annotations

import logging
import os
import sys
import tempfile
import time
from collections.abc import Callable
from functools import wraps


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


def setup_logging():
    # Try different folders for log file
    storage_env = os.getenv("FLET_APP_STORAGE_DATA")
    log_dirs = [
        os.path.join(storage_env, "logs") if storage_env else None,
        os.path.join(os.path.expanduser("~"), ".ddgs_ui", "logs"),
        os.path.join(
            os.getenv("APPDATA") or os.path.expanduser("~"), ".ddgs_ui", "logs"
        )
        if os.name == "nt"
        else None,
        os.path.join(tempfile.gettempdir(), "ddgs_ui", "logs"),
        os.path.join(os.getcwd(), "logs"),
    ]

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

            # Writable folder found!
            file_handler = logging.FileHandler(log_file, encoding="utf-8")
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
