"""Flet API verification against the INSTALLED flet in .venv.

Two bugs escaped construction tests and only exploded in Dart:

- ``SafeArea(top=True)``: ``top`` binds through the MRO to
  ``LayoutControl.top`` (a Number / double? on the Dart side), so a bool
  value crashed every Assistant open with "type 'bool' is not a subtype
  of type 'double?'" (owner-reproduced on desktop). SafeArea's own field
  is ``avoid_intrusions_top``, default True.
- ``ft.Colors.WARNING``: the constant does not exist in flet 1.0.1 (the
  name is ORANGE), so ``ui.notice(level="warning")`` raised AttributeError.

Both classes are now swept: every ft.<Enum>.TOKEN referenced in src/
must exist on the installed class, and every CONSTRUCTED control tree
may never carry a bool on a field whose declared type does not allow
bool (Python accepts it because bool subclasses int; Dart does not).
"""

from __future__ import annotations

import asyncio
import re
import sys
import types
import typing
from pathlib import Path

import flet as ft

SRC = Path(__file__).resolve().parents[1] / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

_ENUMS = (
    "Colors",
    "Icons",
    "ScrollMode",
    "PagePlatform",
    "MainAxisAlignment",
    "CrossAxisAlignment",
    "TextAlign",
    "FontWeight",
    "Brightness",
    "BorderStyle",
)


def test_every_referenced_flet_enum_token_exists():
    offenders = []
    for path in sorted(SRC.rglob("*.py")):
        text = path.read_text(encoding="utf-8")
        for cls in _ENUMS:
            for name in sorted(set(re.findall(rf"ft\.{cls}\.([A-Za-z0-9_]+)", text))):
                if not hasattr(getattr(ft, cls), name):
                    offenders.append(f"{path.name}: ft.{cls}.{name}")
    assert not offenders, f"missing flet enum tokens: {offenders}"


def test_safearea_never_gets_the_layout_top_kwarg():
    """SafeArea(top=...) would land on LayoutControl.top: Number (double?).
    The real field, avoid_intrusions_top, already defaults to True."""
    source = (SRC / "screens" / "chat_screen.py").read_text(encoding="utf-8")
    assert "ft.SafeArea(" in source, "the chat view keeps its SafeArea"
    assert re.search(r"ft\.SafeArea\(\s*top=", source) is None, (
        "SafeArea(top=) binds to LayoutControl.top (Number): bool there "
        "crashes Dart with 'bool is not a subtype of double?'"
    )


# ── bool-on-Number sweep over constructed trees ──────────────────────────

_HINTS: dict[type, dict] = {}


def _hints(cls: type) -> dict:
    if cls not in _HINTS:
        try:
            _HINTS[cls] = typing.get_type_hints(cls)
        except Exception:
            _HINTS[cls] = {}
    return _HINTS[cls]


def _allows_bool(ann: object) -> bool:
    stack = [ann]
    while stack:
        a = stack.pop()
        if a is bool or a is typing.Any:
            return True
        if "bool" in str(a):  # exotic aliases, Annotated[bool | int, ...]
            return True
        origin = typing.get_origin(a)
        if origin is typing.Union or isinstance(a, types.UnionType):
            stack.extend(typing.get_args(a))
    return False


def _iter_controls(root):
    seen: set[int] = set()
    stack = [root]
    while stack:
        ctrl = stack.pop()
        if not isinstance(ctrl, ft.Control) or id(ctrl) in seen:
            continue
        seen.add(id(ctrl))
        yield ctrl
        for name in dir(ctrl):
            if name.startswith("_"):
                continue
            try:
                value = getattr(ctrl, name)
            except Exception:
                value = None
            if isinstance(value, ft.Control):
                stack.append(value)
            elif isinstance(value, (list, tuple)):
                stack.extend(v for v in value if isinstance(v, ft.Control))


def _assert_no_bool_on_number(root) -> None:
    offenders = []
    for ctrl in _iter_controls(root):
        for name, ann in _hints(type(ctrl)).items():
            try:
                value = getattr(ctrl, name)
            except Exception:
                value = None
            if type(value) is bool and not _allows_bool(ann):
                offenders.append(
                    f"{type(ctrl).__name__}.{name}=True on declared type {ann}"
                )
    assert not offenders, f"bool landed on a Number prop: {offenders}"


def _chat_stub(platform=ft.PagePlatform.ANDROID):
    from screens.chat_screen import ChatSession

    class Controller:
        billing = None
        storage = None

        async def _grant_premium_benefits(self, *, first_time=False):
            return False

        async def _sync_premium_storage(self):
            pass

        async def verify_purchases(self):
            pass

    class Page:
        width = 393
        height = 852
        theme_mode = ft.ThemeMode.DARK

        def __init__(self):
            self.dialogs = []
            self.views = []
            self._ddgs_controller = Controller()
            self.scheduled = []

        def run_task(self, handler, *args, **kwargs):
            if not asyncio.iscoroutinefunction(handler):
                raise TypeError("handler must be a coroutine function")
            self.scheduled.append(handler.__name__)

        def run_thread(self, handler, *args, **kwargs):
            self.scheduled.append(getattr(handler, "__name__", "thread"))

        def show_dialog(self, dlg):
            self.dialogs.append(dlg)

        def pop_dialog(self):
            pass

        def update(self):
            pass

    Page.platform = platform
    return ChatSession, Page


def test_chat_view_carries_no_bool_on_number_props(tmp_path, monkeypatch):
    """The Assistant view end to end: header, SafeArea, transcript, composer."""
    monkeypatch.setenv("FLET_APP_STORAGE_DATA", str(tmp_path / "data"))
    ChatSession, Page = _chat_stub()
    session = ChatSession(Page())
    session.turns = []
    session._render()
    _assert_no_bool_on_number(session.view)


def test_notice_and_banner_carry_no_bool_on_number_props():
    from core.styles import build_banner_ad
    from core.ui import notice

    class MobilePage:
        platform = ft.PagePlatform.ANDROID
        theme_mode = ft.ThemeMode.DARK

    _assert_no_bool_on_number(notice("receipt text", level="warning"))
    _assert_no_bool_on_number(
        build_banner_ad(MobilePage(), unit_id="ca-app-pub-test/banner")
    )
