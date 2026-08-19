from __future__ import annotations

# Resolve the app version, degrading gracefully so this import never fails.
# Priority: installed package metadata → pyproject.toml → hard fallback.
# Each stage is independently guarded so a failure at one stage cannot mask
# the next (and so _APP_VERSION is always a non-empty string).
_APP_VERSION = ""

try:
    from importlib.metadata import version as _pkg_version

    _APP_VERSION = _pkg_version("ddgs-app")
except Exception:  # metadata may be absent in a source checkout
    _APP_VERSION = ""

if not _APP_VERSION:
    try:
        import tomllib
        from pathlib import Path

        _pp = Path(__file__).resolve().parent.parent.parent.parent / "pyproject.toml"
        with open(_pp, "rb") as f:
            _APP_VERSION = tomllib.load(f)["project"]["version"]
    except Exception:  # file missing or unparseable, fall through
        _APP_VERSION = ""

if not _APP_VERSION:
    _APP_VERSION = "1.2.1"
