"""Flet's three storage locations, resolved once.

`.flet/README.md` documents the contract: while `flet run` is active the
app's working directory is `storage/data` and the three locations are
exposed through FLET_APP_STORAGE_DATA / _CACHE / _TEMP, matching how a
packaged app behaves on a device. Off-device (plain `python`, tests) those
variables are absent, so we fall back to the same layout under the user's
home directory.

  data/  durable user state: settings, conversations, logs
  cache/ regenerable: search results and fetched pages. The OS may purge
         this directory on a device, so nothing here may be irreplaceable.
  temp/  scratch space, cleared at startup.
"""

from __future__ import annotations

import os
import shutil
from pathlib import Path

_APP_DIR_NAME = ".ddgs_ui"


def _resolve(env_var: str, folder: str) -> Path:
    env = os.getenv(env_var)
    base = Path(env) if env else Path.home() / _APP_DIR_NAME / folder
    try:
        base.mkdir(parents=True, exist_ok=True)
    except OSError:
        # A read-only or missing home must not stop the app from booting;
        # callers degrade to a no-op cache rather than crash.
        pass
    return base


def data_dir() -> Path:
    return _resolve("FLET_APP_STORAGE_DATA", "data")


def cache_dir() -> Path:
    return _resolve("FLET_APP_STORAGE_CACHE", "cache")


def temp_dir() -> Path:
    return _resolve("FLET_APP_STORAGE_TEMP", "temp")


def clear_temp() -> int:
    """Empty temp/ on startup. Returns how many entries were removed.

    Anything here is by definition disposable: in-flight scrape and
    download scratch from a previous run that did not exit cleanly.

    Never touched, because on Android this directory IS the cache dir
    (getTemporaryDirectory returns getCacheDir) and this wipe once
    deleted the runtime's CA file seconds after launch - every httpx
    client then died at construction on the missing SSL_CERT_FILE path:
      - whatever SSL_CERT_FILE / SSL_CERT_DIR point at,
      - *cacert.pem (the runtime's or certifi's extracted bundle),
      - engine_local*.py (the router's offline tier).
    """
    keep: set[str] = set()
    for key in ("SSL_CERT_FILE", "SSL_CERT_DIR"):
        value = os.environ.get(key)
        if value:
            keep.add(str(Path(value)))
    root = temp_dir()
    # Android: temp IS cache (getTemporaryDirectory == getCacheDir), so a
    # subdir here is a cache tier (cache/ddgs) - never rmtree it. On
    # desktop temp is its own dir and scratch subdirs are fair game.
    wipe_dirs = root.resolve() != cache_dir().resolve()
    removed = 0
    try:
        for child in root.iterdir():
            if (
                str(child) in keep
                or child.name.endswith("cacert.pem")
                or child.name.startswith("engine_local")
            ):
                continue
            try:
                if child.is_dir():
                    if not wipe_dirs:
                        continue
                    shutil.rmtree(child, ignore_errors=True)
                else:
                    child.unlink()
                removed += 1
            except OSError:
                continue
    except OSError:
        return removed
    return removed
