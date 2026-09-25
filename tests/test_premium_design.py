"""The Premium card is a menu, not a form — KTV Player's shape.

The user's complaint was that the card "listed every option there": email,
name, phone and a recovery field sitting in the middle of Settings as a
permanent block. KTV Player collects nothing until you ask to buy, and this
module asserts exactly that.
"""

from __future__ import annotations

import inspect
import sys
from pathlib import Path

import flet as ft

SRC = Path(__file__).resolve().parents[1] / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))


class _Page:
    platform = ft.PagePlatform.WINDOWS
    width = 900
    height = 800
    theme_mode = ft.ThemeMode.LIGHT

    def __init__(self, controller):
        self._ddgs_controller = controller
        self.dialogs: list = []
        self.tasks = []

    def show_dialog(self, dlg):
        self.dialogs.append(dlg)

    def pop_dialog(self):
        if self.dialogs:
            self.dialogs.pop()

    def run_task(self, handler, *args, **kwargs):
        self.tasks.append((handler, args))

    def update(self):
        pass

    @property
    def services(self):
        return []


class _Controller:
    billing = None
    storage = None

    def __init__(self, premium):
        self.premium = premium

    async def _grant_premium_benefits(self):
        return False

    async def _sync_premium_storage(self):
        pass

    async def verify_purchases(self):
        pass


class _Premium:
    """Stands in for PremiumService; only `available` matters to the card."""

    available = True


def _build(monkeypatch, *, premium=True, prices=None, recovery="", is_premium=False):
    from components.settings import sections_premium as mod
    from core import build_channel
    from core.state import state
    from services import premium_service as ps

    monkeypatch.setattr(build_channel, "CHANNEL", "direct", raising=False)
    monkeypatch.setattr(ps, "CHANNEL", "direct", raising=False)
    # Never let a leftover price from another test decide this one's rows.
    monkeypatch.setattr(mod, "_prices_attempted", True, raising=False)
    # And never let a leftover verdict decide the headline.
    monkeypatch.setattr(state, "is_premium", is_premium, raising=False)
    monkeypatch.setattr(state, "license_premium_active", is_premium, raising=False)
    monkeypatch.setattr(
        state, "license_status", "active" if is_premium else "", raising=False
    )
    monkeypatch.setattr(
        state, "premium_source", "license:Direct" if is_premium else "", raising=False
    )
    monkeypatch.setattr(state, "license_recovery_id", recovery, raising=False)
    monkeypatch.setattr(state, "license_prices", prices or {}, raising=False)
    page = _Page(_Controller(_Premium() if premium else None))
    return mod, page, mod.build_premium_section(page)


def _collect(control, texts, fields):
    if isinstance(control, str):
        texts.append(control)
        return
    if isinstance(control, ft.TextField):
        fields.append(control)
    if isinstance(control, ft.Text) and control.value:
        texts.append(str(control.value))
    for child in getattr(control, "controls", None) or []:
        _collect(child, texts, fields)
    for attr in ("content", "leading", "trailing", "title", "icon"):
        kid = getattr(control, attr, None)
        if kid is None or isinstance(kid, (int, float, bool)):
            continue
        if isinstance(kid, str):
            # Flet 1.0 stores a button's label as `content`, a plain str.
            texts.append(kid)
        else:
            _collect(kid, texts, fields)


def _walk_controls(control, found):
    found.append(control)
    for child in getattr(control, "controls", None) or []:
        _walk_controls(child, found)
    for attr in ("content", "leading", "trailing", "title"):
        kid = getattr(control, attr, None)
        if kid is not None and not isinstance(kid, (str, int, float, bool)):
            _walk_controls(kid, found)


def test_the_card_carries_no_form_of_its_own(monkeypatch):
    """Email/name/phone/recovery were a permanent block in Settings."""
    _, _, card = _build(monkeypatch, prices={"monthly": "$3.99 USD"})
    texts: list = []
    fields: list = []
    _collect(card, texts, fields)
    assert not fields, f"{len(fields)} text field(s) are rendered before anyone asks"
    rendered = " ".join(texts)
    # Every plan is one row with its price; nothing else is pre-opened.
    for label in ("Monthly", "Yearly", "Lifetime", "Restore purchases"):
        assert label in rendered, f"{label} must be a row on the card"


def test_tapping_a_plan_opens_the_checkout_dialog(monkeypatch):
    _mod, page, card = _build(monkeypatch, prices={"monthly": "$3.99 USD"})
    controls: list = []
    _walk_controls(card, controls)
    buy = next(
        c
        for c in controls
        if isinstance(c, ft.FilledButton) and str(getattr(c, "content", "")) == "$3.99 USD"
    )
    buy.on_click(None)
    assert page.dialogs, "the plan button must open something"
    dialog = page.dialogs[-1]
    assert isinstance(dialog, ft.AlertDialog)
    assert "Unlock DDGS Premium" in str(dialog.title.value)

    texts: list = []
    fields: list = []
    _collect(dialog, texts, fields)
    labels = [f.label for f in fields]
    assert labels[0] == "Email for your receipt", "email is the one required field"
    assert "Name (optional)" in labels
    assert "Phone (optional)" in labels

    # Continue must be wired to an async checkout, not a no-op.
    cont = next(
        a
        for a in dialog.actions
        if isinstance(a, ft.FilledButton) and str(getattr(a, "content", "")) == "Continue"
    )
    assert cont.on_click is not None
    cont.on_click(None)
    handler, args = page.tasks[-1]
    assert handler.__name__ == "_checkout"
    assert args[0] == "monthly"


def test_the_restore_row_opens_a_dialog_prefilled_with_the_saved_id(monkeypatch):
    _, page, card = _build(
        monkeypatch,
        prices={"monthly": "$3.99 USD"},
        recovery="KIRI-L-ABC123",
    )
    controls: list = []
    _walk_controls(card, controls)
    restore = next(
        c
        for c in controls
        if isinstance(c, ft.OutlinedButton) and str(getattr(c, "content", "")) == "Restore"
    )
    restore.on_click(None)
    dialog = page.dialogs[-1]
    assert isinstance(dialog, ft.AlertDialog)
    assert "Restore your license" in str(dialog.title.value)
    texts: list = []
    fields: list = []
    _collect(dialog, texts, fields)
    assert fields[0].value == "KIRI-L-ABC123", "no re-typing after a purchase"


def test_the_recovery_id_row_only_exists_when_there_is_one(monkeypatch):
    _, _, without = _build(monkeypatch, prices={"monthly": "$3.99 USD"})
    t: list = []
    f: list = []
    _collect(without, t, f)
    assert "Your recovery ID" not in " ".join(t)

    _, _, with_id = _build(
        monkeypatch, prices={"monthly": "$3.99 USD"}, recovery="KIRI-L-ABC123"
    )
    t2: list = []
    _collect(with_id, t2, f)
    assert "Your recovery ID" in " ".join(t2)


def test_an_empty_catalog_says_so_instead_of_hiding_the_plans(monkeypatch):
    _, _, card = _build(monkeypatch, prices=None)
    texts: list = []
    fields: list = []
    _collect(card, texts, fields)
    rendered = " ".join(texts)
    assert "Unlock options unavailable" in rendered
    assert "Could not reach the license service" in rendered
    # The rows are still there, offering a neutral label rather than a
    # number the app does not have.
    assert "Choose" in rendered


def test_a_premium_holder_sees_no_price_rows(monkeypatch):
    _, _, card = _build(
        monkeypatch,
        prices={"monthly": "$3.99 USD"},
        is_premium=True,
    )
    texts: list = []
    fields: list = []
    _collect(card, texts, fields)
    rendered = " ".join(texts)
    assert "Premium active" in rendered
    assert "Monthly" not in rendered, "a buyer is not sold what they own"
    assert "Restore purchases" in rendered


def test_the_buyer_is_sent_to_restore_not_to_a_status_check():
    """`/status` never returns a token, so it can confirm a payment and
    still leave Premium off. Only `/restore` issues the token."""
    source = (SRC / "components" / "settings" / "sections_premium.py").read_text(
        encoding="utf-8"
    )
    assert "_check_status" not in source, (
        "the dead end KTV Player does not have: /status issues no token"
    )
    assert "then tap Restore." in source
    # ...and the restore path really does go through the token-issuing call.
    from services import license_service

    sig = inspect.signature(license_service.KiriLicenseService.restore)
    assert sig.parameters["recovery_id"].kind is inspect.Parameter.POSITIONAL_OR_KEYWORD
    body = inspect.getsource(license_service.KiriLicenseService.restore)
    assert '"/restore"' in body
    assert "issue_token=True" in body
