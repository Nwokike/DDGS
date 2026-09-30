"""Android parity gate: every third-party import in src/ must be declared.

`flet build apk/aab` resolves ONLY [project].dependencies against
pypi.flet.dev. Dev-group packages (flet-cli -> qrcode, cookiecutter ->
python-slugify) import fine on desktop and crash on Android launch.
This test fails fast in CI instead.
"""

from __future__ import annotations

import ast
import pathlib
import re
import sys
import tomllib
from importlib import metadata

ROOT = pathlib.Path(__file__).resolve().parents[1]


def _declared_top_levels() -> set[str]:
    pp = tomllib.load(open(ROOT / "pyproject.toml", "rb"))
    names: set[str] = set()
    for dep in pp["project"]["dependencies"]:
        # Strip extras, version specifiers, and markers:
        # "kani[openai]>=1.10.0" -> "kani", "flet>=1.0.3" -> "flet".
        base = re.split(r"[ ;\[]", dep.strip())[0]
        base = re.split(r"[<>=!~]", base)[0].strip()
        names.add(base.lower().replace("-", "_"))
    return names


def _imports_of(path: pathlib.Path) -> set[str]:
    """Top-level module names imported by a file (ast-based, no docstrings)."""
    try:
        tree = ast.parse(path.read_text(encoding="utf-8"))
    except SyntaxError:
        return set()
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                names.add(alias.name.split(".")[0])
        elif isinstance(node, ast.ImportFrom):
            if node.module and node.level == 0:
                names.add(node.module.split(".")[0])
    return names


def test_imports_all_declared():
    declared = _declared_top_levels()
    try:
        dist_map = metadata.packages_distributions() or {}
    except Exception:
        dist_map = {}
    local = {p.name for p in (ROOT / "src").glob("*") if p.is_dir()}
    local |= {p.stem for p in (ROOT / "src").glob("*.py")}
    stdlib = sys.stdlib_module_names

    missing: set[str] = set()
    for path in sorted((ROOT / "src").rglob("*.py")):
        for mod in _imports_of(path):
            if mod in local or mod in stdlib or mod.startswith("_"):
                continue
            providers = {
                d.lower().replace("-", "_")
                for d in (dist_map.get(mod) or [])
            }
            if not (providers & declared) and mod.lower() not in declared:
                missing.add(
                    f"{path.relative_to(ROOT)}: {mod} "
                    f"(providers={sorted(providers) or 'none'})"
                )
    assert not missing, (
        "imports without a declared [project] dependency "
        "(these crash on Android):\n" + "\n".join(sorted(missing))
    )
