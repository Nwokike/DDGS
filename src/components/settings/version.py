from __future__ import annotations

try:
    from importlib.metadata import version as _pkg_version

    _APP_VERSION: str = _pkg_version("ddgs-app")
except (ImportError, KeyError, OSError):
    import tomllib
    from pathlib import Path

    try:
        _pp = Path(__file__).resolve().parent.parent.parent.parent.parent / "pyproject.toml"
        with open(_pp, "rb") as f:
            _APP_VERSION = tomllib.load(f)["project"]["version"]
    except (ImportError, KeyError, OSError, tomllib.TOMLDecodeError):
        _APP_VERSION = "1.1.0"
