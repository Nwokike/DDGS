"""Pin SSL_CERT_FILE to a CA bundle this app's own cleanup cannot delete.

Android hands the process SSL_CERT_FILE pointing into the app CACHE
directory (the runtime extracts a CA file there; certifi inside the
zipped site-packages does the same through importlib.resources.as_file).
On Android the cache directory IS the temporary directory (PathProvider
getTemporaryDirectory returns getCacheDir), and clear_temp() empties it
seconds after launch, so the path the environment advertises stops
existing mid-session. httpx checks SSL_CERT_FILE FIRST and passes it to
ssl.create_default_context(cafile=...) at CLIENT CONSTRUCTION
(httpx/_config.py line 35), so every client raised FileNotFoundError
before any I/O: model catalog, engine download, license service, both
chat legs. Desktop ships no such variable, which is why it tested clean.

KTV Player survives because it never wipes its cache at startup; LM
Router survives because its clients pass trust_env=False and never read
the variable. DDGS reads it (httpx default) AND wipes it, so the repair
belongs here: stage certifi's bundle under the DATA dir (never
cache-cleared, never OS-trimmed) and point the variable at it before the
first client exists. The status string is logged at startup, so the
phone log proves which branch ran.
"""

from __future__ import annotations

import os
from pathlib import Path


def _inside_wipe_dirs(path: str) -> bool:
    """True when the path sits in temp/ or cache/: directories this app
    clears at startup and Android may trim at any time."""
    try:
        from core.storage_paths import cache_dir, temp_dir

        p = Path(path)
        return p.is_relative_to(temp_dir()) or p.is_relative_to(cache_dir())
    except (OSError, ValueError, AttributeError):
        return False


def _stable_bundle() -> str:
    """Stage certifi's CA file under data/ and return its path ("" if not)."""
    try:
        import certifi

        src = Path(certifi.where())
        if not src.is_file():
            return ""
        from core.storage_paths import data_dir

        target_dir = data_dir() / "ca"
        target = target_dir / "cacert.pem"
        if not target.is_file() or target.stat().st_size == 0:
            target_dir.mkdir(parents=True, exist_ok=True)
            target.write_bytes(src.read_bytes())
        return str(target)
    except (OSError, ValueError, ImportError, AttributeError):
        return ""


def ensure_ca_bundle() -> str:
    """Point SSL_CERT_FILE at the staged bundle; report what happened.

    A valid file OUTSIDE temp/ and cache/ is a real user or system
    override and keeps winning. Anything inside the wipe directories -
    even a file that exists right now, because our own clear_temp kills
    it two seconds later - is replaced by the staged copy. The return
    string is logged at startup so the phone log proves the repair.
    """
    parts: list[str] = []
    stable = _stable_bundle()
    cert_file = os.environ.get("SSL_CERT_FILE")

    if stable:
        if cert_file and os.path.isfile(cert_file) and not _inside_wipe_dirs(cert_file):
            parts.append("SSL_CERT_FILE kept (stable existing file)")
        else:
            os.environ["SSL_CERT_FILE"] = stable
            if cert_file:
                parts.append(f"SSL_CERT_FILE {cert_file!r} -> {stable}")
            else:
                parts.append(f"SSL_CERT_FILE -> {stable}")
    elif cert_file and not os.path.isfile(cert_file):
        # Cannot stage a bundle (never in a real build): drop the dead
        # pointer so httpx falls through to its own certifi lookup.
        os.environ.pop("SSL_CERT_FILE", None)
        parts.append(f"dropped missing SSL_CERT_FILE {cert_file!r}")
    elif cert_file:
        parts.append("SSL_CERT_FILE kept (existing file)")
    else:
        parts.append("SSL_CERT_FILE unset (httpx uses certifi directly)")

    cert_dir = os.environ.get("SSL_CERT_DIR")
    if cert_dir:
        if os.path.isdir(cert_dir):
            parts.append("SSL_CERT_DIR kept")
        else:
            os.environ.pop("SSL_CERT_DIR", None)
            parts.append(f"dropped missing SSL_CERT_DIR {cert_dir!r}")

    return "; ".join(parts)
