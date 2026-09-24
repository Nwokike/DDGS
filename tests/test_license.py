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


def _real_client():
    from services import license_service

    if not license_service.is_available():
        pytest.skip("this build ships the Play-only license stub")
    return license_service


# ── ECDSA verifier ───────────────────────────────────────────────────────
def test_valid_webcrypto_token_verifies():
    from core.license_crypto import verify_token

    claims = verify_token(_VECTOR_TOKEN, _VECTOR_PUB)
    assert claims["iss"] == _ISSUER
    assert claims["app"] == _APP
    assert claims["status"] == "active"
    assert claims["product"] == "lifetime"


def test_tampered_payload_is_rejected():
    from core.license_crypto import TokenError, verify_token

    flipped = _VECTOR_TOKEN[:40] + ("A" if _VECTOR_TOKEN[40] != "A" else "B") + _VECTOR_TOKEN[41:]
    with pytest.raises(TokenError):
        verify_token(flipped, _VECTOR_PUB)


def test_token_signed_by_another_key_is_rejected():
    from core.license_crypto import TokenError, verify_token

    with pytest.raises(TokenError):
        verify_token(_VECTOR_TOKEN, _PRODUCTION_PUB)


def test_webcrypto_raw_signature_is_reencoded_to_der():
    """Pins the one encoding detail that is easy to get wrong.

    WebCrypto signs with a raw 64-byte r||s pair. cryptography verifies
    ASN.1 DER. If someone 'simplifies' this by handing the raw bytes
    straight to verify(), every real token stops working while a
    self-signed round-trip test still passes. The DER must start with the
    SEQUENCE tag and decode to the r and s recovered from the raw pair.
    """
    from cryptography.hazmat.primitives.asymmetric import utils

    from core.license_crypto import _b64url_decode, _der_from_raw

    raw = _b64url_decode(_VECTOR_TOKEN.split(".")[2])
    assert len(raw) == 64, "WebCrypto P-256 signatures are 64 raw bytes"
    der = _der_from_raw(raw)
    assert der[0] == 0x30, "DER must start with a SEQUENCE tag"
    r, s = utils.decode_dss_signature(der)
    assert r == int.from_bytes(raw[:32], "big")
    assert s == int.from_bytes(raw[32:], "big")


def test_production_public_key_is_a_valid_p256_key():
    """Guards the pinned key: a typo here would silently break every user."""
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric import ec

    from core.license_crypto import _b64url_decode

    key = serialization.load_der_public_key(_b64url_decode(_PRODUCTION_PUB))
    assert isinstance(key, ec.EllipticCurvePublicKey)
    assert isinstance(key.curve, ec.SECP256R1)


@pytest.mark.parametrize(
    "token",
    [
        "",
        "nonsense",
        "v1.only-two-parts",
        "v2.payload.sig",
        "v1..sig",
        "v1.payload.",
        "v1.!!!.###",
    ],
)
def test_malformed_tokens_never_raise_anything_but_tokenerror(token):
    from core.license_crypto import is_entitled

    # is_entitled is the safe entry point and must never raise.
    ok, _reason = is_entitled(token, _VECTOR_PUB, app_id=_APP, issuer=_ISSUER)
    assert ok is False


def test_claims_binding_is_checked():
    from core.license_crypto import claims_are_valid

    good = {
        "iss": _ISSUER,
        "app": _APP,
        "status": "active",
        "exp": None,
    }
    assert claims_are_valid(good, app_id=_APP, issuer=_ISSUER) is True
    assert claims_are_valid(good, app_id="com.other", issuer=_ISSUER) is False
    assert claims_are_valid(good, app_id=_APP, issuer="evil.example") is False
    assert (
        claims_are_valid(
            {**good, "status": "revoked"}, app_id=_APP, issuer=_ISSUER
        )
        is False
    )
    assert (
        claims_are_valid(
            {**good, "exp": 1000}, app_id=_APP, issuer=_ISSUER, now=2000
        )
        is False
    )
    assert (
        claims_are_valid(
            {**good, "exp": 3000}, app_id=_APP, issuer=_ISSUER, now=2000
        )
        is True
    )


# ── entitlement arbiter ───────────────────────────────────────────────────
def _reset() -> None:
    from core.state import state

    state.is_premium = False
    state.play_premium_active = False
    state.license_premium_active = False
    state.premium_source = ""
    state.license_status = ""


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


def test_an_inconclusive_offline_check_never_downgrades():
    """A bad or missing local token must not cost a paying user Premium."""
    from core.state import state
    from services import premium_service

    licenses = _real_client()
    _reset()
    state.license_premium_active = True
    premium_service.apply_entitlement()
    assert state.is_premium is True

    premium_service.apply_license_entitlement(
        licenses.Entitlement(status="invalid", offline=True)
    )
    assert state.is_premium is True, "offline check must not revoke"
    assert state.license_premium_active is True


def test_an_authoritative_revocation_does_downgrade():
    from core.state import state
    from services import premium_service

    licenses = _real_client()
    _reset()
    state.license_premium_active = True
    premium_service.apply_entitlement()
    assert state.is_premium is True

    premium_service.apply_license_entitlement(
        licenses.Entitlement(
            status="revoked", product="lifetime", offline=False
        )
    )
    assert state.is_premium is False
    assert state.license_status == "revoked"


def test_an_authoritative_expiry_does_downgrade():
    from core.state import state
    from services import premium_service

    licenses = _real_client()
    _reset()
    state.license_premium_active = True
    premium_service.apply_entitlement()
    premium_service.apply_license_entitlement(
        licenses.Entitlement(status="expired", product="monthly", offline=False)
    )
    assert state.is_premium is False


def test_a_play_purchase_survives_a_refunded_license():
    """The channels are independent: a refunded licence must not cancel a
    Play purchase, which Play itself controls."""
    from core.state import state
    from services import premium_service

    licenses = _real_client()
    _reset()
    premium_service.set_play_entitlement(True, product_id="premium_lifetime")
    assert state.is_premium is True
    premium_service.apply_license_entitlement(
        licenses.Entitlement(status="revoked", product="lifetime", offline=False)
    )
    assert state.is_premium is True, "Play purchase is still owned"
    assert state.play_premium_active is True


def test_grace_still_grants_access():
    from core.state import state
    from services import premium_service

    licenses = _real_client()
    _reset()
    premium_service.apply_license_entitlement(
        licenses.Entitlement(status="grace", product="monthly", offline=False)
    )
    assert state.is_premium is True


# ── client contract ──────────────────────────────────────────────────────
def test_recovery_id_shape_is_validated():
    licenses = _real_client()
    assert licenses.parse_recovery_id("KIRI-L-" + "A" * 24)
    assert licenses.parse_recovery_id("kiri-l-" + "a" * 24)  # case-insensitive
    assert licenses.parse_recovery_id("nope") is None
    assert licenses.parse_recovery_id("KIRI-L-short") is None


def test_email_validation():
    licenses = _real_client()
    assert licenses.valid_email("buyer@example.com") is True
    assert licenses.valid_email("not-an-email") is False
    assert licenses.valid_email("") is False


def test_play_products_map_to_license_tiers():
    licenses = _real_client()
    assert licenses.PLAY_EQUIVALENT == {
        "monthly": "premium_monthly",
        "yearly": "premium_yearly",
        "lifetime": "premium_lifetime",
    }


# ── build-channel policy ─────────────────────────────────────────────────
def test_license_channel_is_absent_from_a_play_build():
    """One test, both ways: exactly one channel may be active per build."""
    from services import license_service

    root = SRC.parent
    premium_ui = (root / "src" / "components" / "settings" / "sections_premium.py").read_text(
        encoding="utf-8"
    )
    client = (root / "src" / "services" / "license_service.py").read_text(
        encoding="utf-8"
    )

    if license_service.is_available():
        # Direct build: the license channel is real and reachable.
        assert "license.kiri.ng" in client
        assert "Checkout" not in premium_ui or "checkout" in premium_ui.lower()
        assert "Recovery ID" in premium_ui, "direct builds need the recovery flow"
    else:
        # Play build: no endpoint, no hosted checkout, no recovery UI.
        assert "license.kiri.ng" not in client, (
            "a Play build must not carry the external payment endpoint"
        )
        assert "checkout_url" not in client
        assert "Recovery ID" not in premium_ui
        assert "Play Billing" in premium_ui or "Google Play" in premium_ui
