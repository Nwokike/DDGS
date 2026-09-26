"""Version discipline: pyproject is the single source of truth.

Mirrors the CI gate (both workflows) hermetically: workflow defaults, app
fallbacks and the User-Agent must all agree with pyproject, and
version.json may only ever be HELD BACK (never ahead) until the Play AAB
upload lands.
"""

from __future__ import annotations

import json
import re
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _pyproject() -> tuple[str, str]:
    with open(ROOT / "pyproject.toml", "rb") as fh:
        pp = tomllib.load(fh)
    return pp["project"]["version"], str(pp["tool"]["flet"]["build_number"])


def test_workflow_defaults_and_fallbacks_match_pyproject():
    version, build = _pyproject()
    text = (ROOT / ".github" / "workflows" / "build-all.yml").read_text(
        encoding="utf-8"
    )
    defaults = re.findall(r'^\s+default: "([^"]+)"', text, re.MULTILINE)
    assert defaults == [version, build], f"workflow input defaults {defaults}"
    fallbacks = re.findall(r"\|\| '([^']+)'", text)
    assert fallbacks == [version, build], f"workflow env fallbacks {fallbacks}"


def test_app_fallbacks_end_at_pyproject():
    """The literal fallbacks only bite when pyproject is unreadable - which
    is exactly when they must be right."""
    version, build = _pyproject()

    def literals(path: Path, name: str, cast=str):
        hits = re.findall(
            rf'{name} = ("[^"]+"|\d+)', path.read_text(encoding="utf-8")
        )
        return [cast(h.strip('"')) for h in hits]

    v_fall = literals(ROOT / "src/components/settings/version.py", "_APP_VERSION")
    assert v_fall and v_fall[-1] == version, v_fall
    u_fall = literals(ROOT / "src/services/update_service.py", "_APP_VERSION")
    assert u_fall and u_fall[-1] == version, u_fall
    b_fall = literals(ROOT / "src/services/update_service.py", "_APP_BUILD", int)
    assert b_fall and b_fall[-1] == int(build), b_fall


def test_user_agent_carries_the_app_version():
    import sys

    version, _ = _pyproject()
    sys.path.insert(0, str(ROOT / "src"))
    from services.ai_service import USER_AGENT

    assert USER_AGENT == f"DDGSApp/{version}", USER_AGENT


def test_version_json_is_never_ahead():
    """The feed may lag (the owner's hold until the Play AAB ships) but can
    never point at an app version that does not exist."""
    version, _ = _pyproject()

    def vt(s: str):
        return tuple(int(x) for x in s.split("."))

    with open(ROOT / "version.json", encoding="utf-8") as fh:
        feed = json.load(fh)
    assert vt(feed["version"]) <= vt(version), (
        f"version.json {feed['version']} is ahead of pyproject {version}"
    )


def test_ci_gate_is_present_in_the_workflow():
    text = (ROOT / ".github" / "workflows" / "build-all.yml").read_text(
        encoding="utf-8"
    )
    assert "NOTICE: version.json held back" in text, "the CI gate must exist"
    assert "Version consistency" in text
