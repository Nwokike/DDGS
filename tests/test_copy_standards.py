"""Copy standards the owner set for the app.

The rule: no em-dash (or en-dash) anywhere in the app's words. Enforced
over every string constant in src/ (UI copy, docstrings, logs, model
prompts) and over comments. The vendored Kiri router is third-party code
and exempt, like it is from ruff.
"""

from __future__ import annotations

import ast
import sys
from pathlib import Path

SRC = Path(__file__).resolve().parents[1] / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

VENDORED = SRC / "services" / "router" / "run.py"


def _app_files() -> list[Path]:
    return [p for p in sorted(SRC.rglob("*.py")) if p != VENDORED]


def _offending_strings() -> list[str]:
    offenders: list[str] = []
    for path in _app_files():
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if (
                isinstance(node, ast.Constant)
                and isinstance(node.value, str)
                and ("—" in node.value or "–" in node.value)
            ):
                offenders.append(f"{path.relative_to(SRC)}:{node.lineno}")
    return offenders


def test_no_em_dash_in_any_string():
    """Every string constant in src/ is em-dash free."""
    offenders = _offending_strings()
    assert not offenders, "em/en-dash in strings: " + ", ".join(offenders)


def test_no_em_dash_in_comments_or_code_lines():
    """The sweep is total: no line of app source carries the mark either."""
    offenders: list[str] = []
    for path in _app_files():
        for lineno, line in enumerate(
            path.read_text(encoding="utf-8").splitlines(), 1
        ):
            if "—" in line or "–" in line:
                offenders.append(f"{path.relative_to(SRC)}:{lineno}")
    assert not offenders, "em/en-dash in source lines: " + ", ".join(offenders)


def test_current_version_has_a_changelog_entry():
    """The up-to-date dialog renders notes_for(_APP_VERSION): a version bump
    with no entry would show the wrong release's notes (KTV's guard)."""
    from components.settings.version import _APP_VERSION
    from core.changelog import CHANGELOG, notes_for

    assert _APP_VERSION in CHANGELOG, "add an entry when bumping the version"
    assert notes_for(_APP_VERSION)


def test_font_floor_holds_everywhere():
    """No user-facing text below 11pt: the token floor and no raw literals
    sneaking under it."""
    import re

    from core.tokens import FONT_XS

    assert FONT_XS >= 11, "the smallest token IS the floor"
    offenders = []
    for path in _app_files():
        for lineno, line in enumerate(
            path.read_text(encoding="utf-8").splitlines(), 1
        ):
            if re.search(r"\bsize=9\b|\bsize=10\b", line):
                offenders.append(f"{path.relative_to(SRC)}:{lineno}")
    assert not offenders, "sub-11px font literals: " + ", ".join(offenders)


def test_no_banned_glyphs_in_any_string():
    """No emoji in product chrome: the pictographs and warning marks are
    replaced by icons and plain words."""
    banned = "📄⚠⏹⏳🎉"
    offenders = []
    for path in _app_files():
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if (
                isinstance(node, ast.Constant)
                and isinstance(node.value, str)
                and any(ch in node.value for ch in banned)
            ):
                offenders.append(f"{path.relative_to(SRC)}:{node.lineno}")
    assert not offenders, "banned glyphs in strings: " + ", ".join(offenders)
