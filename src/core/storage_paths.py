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
    """
    root = temp_dir()
    removed = 0
    try:
        for child in root.iterdir():
            try:
                if child.is_dir():
                    shutil.rmtree(child, ignore_errors=True)
                else:
                    child.unlink()
                removed += 1
            except OSError:
                continue
    except OSError:
        return removed
    return removed
