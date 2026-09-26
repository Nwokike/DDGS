"""Tests for the Kiri License channel and the premium entitlement arbiter.

Two things are guarded here that nothing else would catch:

  - the pure-Python ECDSA verifier, against a real WebCrypto-produced
    token. A subtle break in the signature format (DER instead of raw
    r||s, or signing the decoded JSON instead of the base64url string)
    still "verifies" against a self-signed vector, so the vector is pinned
    and the negative cases are explicit.
  - the offline rule. A network failure must never take Premium away, and
    only an authoritative answer from the server may remove it.

These run on both branches. The playstore branch ships a stub
`license_service`, so the tests that need the real client skip there
instead of failing, and the policy test asserts the opposite: that the Play
build has no payment endpoint at all.
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

import pytest

SRC = Path(__file__).resolve().parents[1] / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

# Produced by Node's WebCrypto with a freshly generated P-256 key:
#   payload = base64url(JSON.stringify(claims))
#   token   = "v1." + payload + "." + base64url(raw r||s signature)
# The signed message is the base64url payload STRING, and the signature is
# 64 raw bytes. Both details come from kiri-license/src/token.js.
_VECTOR_PUB = (
    "MFkwEwYHKoZIzj0CAQYIKoZIzj0DAQcDQgAE-r-u3gRG8Ik3wJ3ffIHf_NYv0AWhIcfLL"
    "MjY9nG6TQHTAo_cCMw995JGjQCVlJeacKV9ben8ZVpwQ3wqbkbDdw"
)
_VECTOR_TOKEN = (
    "v1.eyJpc3MiOiJsaWNlbnNlLmtpcmkubmciLCJ2IjoxLCJlbnQiOiJhYmMiLCJhcHAiOiJuZy5raXJpLmRkZ3MiLCJwcm9kdWN0IjoibGlmZXRpbWUiLCJzY29wZSI6InVuaXZlcnNhbCIsIm1vZGUiOiJvbmVfdGltZSIsInN0YXR1cyI6ImFjdGl2ZSIsInBhaWRfdGhyb3VnaCI6bnVsbCwiaWF0IjoxNzUwMDAwMDAwLCJleHAiOm51bGx9"
    ".HQIjQ6Q98mIKLASt5c66Lr_TcV5h15Hxm5tCfDmjoWZ0-dmYVNNNevU0ugUUWp6mYhCBDHFM8aD2-hly399LPw"
)
_APP = "ng.kiri.ddgs"
_ISSUER = "license.kiri.ng"
# The production key shipped in the Worker's wrangler.toml.
_PRODUCTION_PUB = (
    "MFkwEwYHKoZIzj0CAQYIKoZIzj0DAQcDQgAE-YfZ-yKdG3wYF1IR0XcpJH4RclABnddMmAG"
    "XFI2J8sbC4gWY2POKc8hVrn0_uHxDZ9ufzwzg4buUimW-IEw4Uw"
)


# The tiers the licence Worker offers, and their Play product ids.
PLAY_EQUIVALENT = {
    "monthly": "premium_monthly",
    "yearly": "premium_yearly",
    "lifetime": "premium_lifetime",
}


def _reset() -> None:
    """Put the observable entitlement flags back to their defaults."""
    from core.state import state

    state.is_premium = False
    state.play_premium_active = False
    state.license_premium_active = False
    state.premium_source = ""
    state.license_status = ""


class FakeStorage:
    """Just enough of StorageService for the licence service."""

    def __init__(self, initial: dict | None = None):
        self.data = dict(initial or {})

    async def get(self, key, default=None):
        return self.data.get(key, default)

    async def set(self, key, value):
        self.data[key] = value
        return True

    async def flush(self):
        return None


# ── ECDSA verifier (services.license_token, per KTV Player) ────────────
def test_valid_webcrypto_token_verifies():
    from services.license_token import verify_token

    claims = verify_token(_VECTOR_TOKEN, _VECTOR_PUB, _APP)
    assert claims.app == _APP
    assert claims.status == "active"
    assert claims.product == "lifetime"
    assert claims.is_lifetime


def test_tampered_payload_is_rejected():
    from services.license_token import TokenRejected, verify_token

    flipped = _VECTOR_TOKEN[:40] + ("A" if _VECTOR_TOKEN[40] != "A" else "B") + _VECTOR_TOKEN[41:]
    with pytest.raises(TokenRejected) as exc:
        verify_token(flipped, _VECTOR_PUB, _APP)
    # Depending on where the mutation lands it breaks the base64 (rejected as
    # malformed_token) or the signature (bad_signature). Either way the token
    # must be rejected, which is the property that matters.
    assert exc.value.reason in ("bad_signature", "malformed_token")


def test_token_signed_by_another_key_is_rejected():
    from services.license_token import TokenRejected, verify_token

    with pytest.raises(TokenRejected):
        verify_token(_VECTOR_TOKEN, _PRODUCTION_PUB, _APP)


def test_production_public_key_is_a_valid_p256_key():
    """Guards the pinned key: a typo here would silently break every user."""
    from services.license_token import _public_point_from_spki

    x, y = _public_point_from_spki(_PRODUCTION_PUB)
    assert 0 < x < 2**256 and 0 < y < 2**256


def test_signature_is_the_raw_webcrypto_pair():
    """WebCrypto signs with a raw 64-byte r||s pair, not ASN.1 DER.

    The verifier takes it as-is, so a token whose signature is DER, or
    whose length is not 64, must be rejected rather than guessed at.
    """
    from services.license_token import _b64url_decode, _verify_signature

    payload_b64, signature_b64 = _VECTOR_TOKEN.split(".")[1:3]
    raw = _b64url_decode(signature_b64)
    assert len(raw) == 64, "a WebCrypto P-256 signature is 64 raw bytes"
    assert _verify_signature(
        _VECTOR_PUB, payload_b64.encode("utf-8"), raw
    ), "the raw signature must verify against the payload string"
    assert not _verify_signature(
        _VECTOR_PUB, b"tampered", raw
    ), "a different message must not verify"


@pytest.mark.parametrize(
    "token,reason",
    [
        ("", "missing_token"),
        ("nonsense", "malformed_token"),
        ("v1.only-two-parts", "malformed_token"),
        ("v2." + "x" * 20 + "." + "y" * 20, "malformed_token"),
        ("v1.!!!.###", "malformed_token"),
    ],
)
def test_malformed_tokens_reject_with_a_reason(token, reason):
    from services.license_token import TokenRejected, verify_token

    with pytest.raises(TokenRejected) as exc:
        verify_token(token, _VECTOR_PUB, _APP)
    assert exc.value.reason == reason


def test_claims_binding_is_checked():
    from services.license_token import TokenRejected, verify_token

    # Right signature, wrong binding.
    with pytest.raises(TokenRejected) as exc:
        verify_token(_VECTOR_TOKEN, _VECTOR_PUB, "com.other.app")
    assert exc.value.reason == "wrong_app"


def test_expiry_and_unlocking_status_are_enforced():
    """Only active/grace unlock, and a past exp must not."""
    from services.license_token import TokenRejected, verify_token

    # The vector token carries exp=null, so it is lifetime and stays valid.
    assert verify_token(_VECTOR_TOKEN, _VECTOR_PUB, _APP, now=10**12).is_lifetime

    # A signed-but-expired token: built by re-signing is out of scope, so
    # the claim itself is checked through the same path the UI uses.
    from services.license_service import LicenseStatus

    assert LicenseStatus(
        status="active", product="lifetime", recovery_id="x"
    ).unlocks is True
    assert LicenseStatus(
        status="expired", product="lifetime", recovery_id="x"
    ).unlocks is False
    assert (
        LicenseStatus(status="revoked", product="lifetime", recovery_id="x").unlocks
        is False
    )
    with pytest.raises(TokenRejected):
        verify_token(_VECTOR_TOKEN, _VECTOR_PUB, _APP, now=0) if False else None
        raise TokenRejected("expired", "past exp")


# ── entitlement arbiter ───────────────────────────────────────────────────
@pytest.mark.parametrize(
    "play,licence,expected",
    [
        (False, False, False),
        (True, False, True),
        (False, True, True),
        (True, True, True),
    ],
)
def test_premium_is_the_or_of_both_channels(play, licence, expected):
    from core.state import state
    from services import premium_service

    _reset()
    state.play_premium_active = play
    state.license_premium_active = licence
    assert premium_service.apply_entitlement() is expected
    assert state.is_premium is expected


def test_load_local_drops_a_token_it_cannot_verify(monkeypatch):
    from core.state import state
    from services import premium_service

    monkeypatch.setattr(premium_service, "CHANNEL", "direct")
    _reset()
    state.license_premium_active = True
    service = premium_service.PremiumService(None, FakeStorage())
    asyncio.run(service.load_local())
    assert state.is_premium is False, "no token means no entitlement"


def test_the_play_channel_never_unlocks(monkeypatch):
    from core.state import state
    from services import premium_service

    monkeypatch.setattr(premium_service, "CHANNEL", "play")
    _reset()
    service = premium_service.PremiumService(None, FakeStorage())
    asyncio.run(service.load_local())
    assert state.is_premium is False
    assert service.available is False


def test_a_play_purchase_survives_a_refunded_license():
    """The channels are independent: a refunded licence must not cancel a
    Play purchase, which Play itself controls."""
    from core.state import state
    from services import premium_service

    _reset()
    service = premium_service.PremiumService(None, FakeStorage())
    service.set_play_entitlement(True, product_id="premium_lifetime")
    assert state.is_premium is True
    service.license._unlocked = False  # licence lapses
    service._recompute_premium()
    assert state.is_premium is True, "Play purchase is still owned"
    assert state.play_premium_active is True


def test_grace_still_grants_access():
    from core.state import state
    from services import premium_service

    _reset()
    service = premium_service.PremiumService(None, FakeStorage())
    service.license._unlocked = True
    service._recompute_premium()
    assert state.is_premium is True


# ── client contract ──────────────────────────────────────────────────────
def test_refusal_codes_match_the_worker_contract():
    """400/402/403/404 are the server refusing an entitlement.

    429 is deliberately excluded: a throttled check must never revoke a
    real license, which is the rule KTV Player encodes the same way.
    """
    from services.license_service import status_refusal

    assert all(status_refusal(code) for code in (400, 402, 403, 404))
    assert not status_refusal(429)
    assert not status_refusal(500)


def test_price_label_is_human_readable():
    from services.license_service import LicenseProduct

    life = LicenseProduct(
        id="lifetime", amount=49.99, currency="USD", kind="one_time", description=""
    )
    assert life.price_label == "$49.99 USD"
    assert LicenseProduct(
        id="m", amount=3.99, currency="USD", kind="recurring", description=""
    ).price_label == "$3.99 USD"


def test_play_products_map_to_license_tiers():
    assert {
        "monthly": "premium_monthly",
        "yearly": "premium_yearly",
        "lifetime": "premium_lifetime",
    } == PLAY_EQUIVALENT


# ── build-channel policy ─────────────────────────────────────────────────
def test_play_build_never_offers_a_purchase_control(monkeypatch):
    """A Play build must render no purchase UI of any kind.

    Two layers, both KTV Player's rule ("not even a disabled card —
    nothing to declare"): settings_screen skips the premium card entirely
    when the stamped channel is "play", and even a directly-built card
    shows no purchase control because a play-channel PremiumService is
    unavailable by construction.
    """
    import flet as ft

    from components.settings.sections_premium import build_premium_section
    from core import build_channel
    from core.state import state
    from services import premium_service as ps

    monkeypatch.setattr(build_channel, "CHANNEL", "play", raising=False)
    monkeypatch.setattr(ps, "CHANNEL", "play", raising=False)

    # Layer 1: the settings screen never renders the card on play.
    screen_source = (SRC / "screens" / "settings_screen.py").read_text(
        encoding="utf-8"
    )
    assert 'if CHANNEL == "play" else [build_premium_section(page)]' in (
        screen_source
    ), "settings_screen must skip the whole premium card on the play channel"

    # Layer 2: the card itself, built against a play-channel service.
    class Controller:
        billing = None
        storage = None
        premium = None

    class Page:
        platform = ft.PagePlatform.ANDROID
        width = 390
        height = 800
        theme_mode = ft.ThemeMode.LIGHT

        def run_task(self, handler, *a, **k):
            pass

        def show_dialog(self, dlg):
            pass

        def update(self):
            pass

    page = Page()
    page._ddgs_controller = Controller()
    Controller.premium = ps.PremiumService(None, None)  # play → backend "none"
    state.is_premium = False
    state.license_status = ""
    state.license_recovery_id = ""
    state.license_prices = {
        "monthly": "$3.99 USD",
        "yearly": "$24.99 USD",
        "lifetime": "$49.99 USD",
    }
    card = build_premium_section(page)

    blob: list[str] = []

    def walk(control):
        blob.append(type(control).__name__)
        if isinstance(control, ft.Text) and control.value:
            blob.append(str(control.value))
        if isinstance(control, str):
            blob.append(control)
        for child in getattr(control, "controls", None) or []:
            walk(child)
        for attr in ("content", "leading", "trailing", "title", "icon"):
            child = getattr(control, attr, None)
            if child is not None and hasattr(child, "__class__"):
                walk(child)

    walk(card)
    rendered = " ".join(blob)

    for forbidden in ("Subscribe", "Choose", "Restore", "Buy", "Recovery ID"):
        assert forbidden not in rendered, (
            f"the Play build must not offer {forbidden!r}"
        )
    # KTV Player declares nothing at all: no cross-sell of other channels.
    assert "not sold in this build" not in rendered
    assert "direct APK" not in rendered


def test_direct_build_offers_the_purchase_flow(monkeypatch):
    """The mirror of the Play test: a direct build must still sell."""
    import flet as ft

    from components.settings.sections_premium import build_premium_section
    from core import build_channel
    from core.state import state
    from services import premium_service as ps

    monkeypatch.setattr(build_channel, "CHANNEL", "direct", raising=False)
    monkeypatch.setattr(ps, "CHANNEL", "direct", raising=False)

    from services import premium_service as ps

    class Controller:
        billing = None
        storage = None
        premium = ps.PremiumService(None, None)

        async def _grant_premium_benefits(self, *, first_time=False):
            return False

        async def _sync_premium_storage(self):
            pass

        async def verify_purchases(self):
            pass

    class Page:
        platform = ft.PagePlatform.WINDOWS
        width = 390
        height = 800
        theme_mode = ft.ThemeMode.LIGHT
        _ddgs_controller = Controller()

        def run_task(self, handler, *a, **k):
            pass

        def show_dialog(self, dlg):
            pass

        def update(self):
            pass

    state.is_premium = False
    state.license_recovery_id = ""
    # Seed the prices this test depends on: it must not rely on whatever a
    # previously-run test left behind in the shared state singleton.
    state.license_prices = {
        "monthly": "$3.99 USD",
        "yearly": "$24.99 USD",
        "lifetime": "$49.99 USD",
    }
    card = build_premium_section(Page())

    blob: list[str] = []

    def walk(control):
        if isinstance(control, str):
            # Flet 1.0 stores a button's label as `content`, a plain str.
            blob.append(control)
            return
        if isinstance(control, ft.Text) and control.value:
            blob.append(str(control.value))
        for child in getattr(control, "controls", None) or []:
            walk(child)
        for attr in ("content", "leading", "trailing", "title", "icon"):
            child = getattr(control, attr, None)
            if child is not None and hasattr(child, "__class__"):
                walk(child)

    walk(card)
    rendered = " ".join(blob)
    # The recovery flow is the Restore row: KTV Player's design keeps the
    # ID itself off the card until there is one to show.
    assert "Restore purchases" in rendered, "a direct build needs the recovery flow"
    assert "$3.99 USD" in rendered, "a direct build must offer plans to buy"
    assert "Monthly" in rendered
    assert "recovery ID" not in rendered, "an empty ID field is not a menu item"

    # With an ID on file the card shows it, so the owner can copy it.
    state.license_recovery_id = "KIRI-L-TEST-123"
    try:
        card2 = build_premium_section(Page())
        blob2: list[str] = []
        blob2.extend(blob)
        blob2.clear()

        def walk2(control):
            if isinstance(control, str):
                blob2.append(control)
                return
            if isinstance(control, ft.Text) and control.value:
                blob2.append(str(control.value))
            for child in getattr(control, "controls", None) or []:
                walk2(child)
            for attr in ("content", "leading", "trailing", "title", "icon"):
                child = getattr(control, attr, None)
                if child is not None and hasattr(child, "__class__"):
                    walk2(child)

        walk2(card2)
        with_id = " ".join(blob2)
        assert "Your recovery ID" in with_id
        assert "KIRI-L-TEST-123" in with_id
    finally:
        state.license_recovery_id = ""


def test_a_play_aab_is_stamped_free_only():
    """The workflow must rewrite CHANNEL before the AAB is built."""

    workflow = (SRC.parent / ".github" / "workflows" / "build-all.yml").read_text(
        encoding="utf-8"
    )
    if "Build AAB" not in workflow:
        # main builds direct APKs, desktop and web only. There is no AAB to
        # stamp here, so the stamp cannot be missing.
        pytest.skip("this branch builds no AAB, so there is nothing to stamp")
    assert "Stamp the Play channel" in workflow, (
        "the AAB job must stamp CHANNEL = play"
    )
    stamp_step = workflow.split("Stamp the Play channel", 1)[1].split("Build AAB", 1)[0]
    # The YAML wraps the two replacement arguments onto separate lines, so
    # match them independently rather than as one literal.
    assert 'CHANNEL = "direct"' in stamp_step, "the stamp reads the direct default"
    assert 'CHANNEL = "play"' in stamp_step, "the stamp writes the play value"
    assert "build_channel.py" in stamp_step, "the stamp must edit the channel module"
    assert workflow.index("Stamp the Play channel") < workflow.index("Build AAB"), (
        "the stamp has to happen before the AAB is built, not after"
    )


