"""Utility functions and logging."""

from __future__ import annotations

import logging
import os
import sys
import time
from functools import wraps
from typing import Callable


LOG_DIR = os.path.join(os.path.expanduser("~"), ".duckduckgo_ui", "logs")
os.makedirs(LOG_DIR, exist_ok=True)

LOG_FILE = os.path.join(LOG_DIR, f"app_{time.strftime('%Y%m%d_%H%M%S')}.log")

logging.basicConfig(
    level=logging.DEBUG,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%H:%M:%S",
    handlers=[
        logging.FileHandler(LOG_FILE, encoding="utf-8"),
        logging.StreamHandler(sys.stdout),
    ],
)

logger = logging.getLogger("duckduckgo_ui")
logger.setLevel(logging.DEBUG)


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
        except Exception as e:
            elapsed = time.perf_counter() - start_time
            logger.exception(f"← {func.__name__} failed in {elapsed:.3f}s: {e}")
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
        except Exception as e:
            elapsed = time.perf_counter() - start_time
            logger.exception(f"← async {func.__name__} failed in {elapsed:.3f}s: {e}")
            raise

    return _wrapper


def log_search_event(event: str, **data):
    """Log search-related events with structured data."""
    log_data = {"event": event, **data}
    logger.info(f"SEARCH_EVENT: {log_data}")


def log_error(context: str, error: Exception, **extra):
    """Log errors with context."""
    logger.error(f"ERROR in {context}: {error}", extra=extra, exc_info=True)


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
        logger.error(f"DDGS_CALL_FAILED: {log_data}", exc_info=True)
    else:
        logger.debug(f"DDGS_CALL: {log_data}")
