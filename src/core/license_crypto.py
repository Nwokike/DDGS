"""ECDSA P-256 verification for Kiri License entitlement tokens.

Uses `cryptography` rather than hand-rolled curve arithmetic. The Worker
signs with WebCrypto, and the one non-obvious detail is the signature
encoding: WebCrypto emits a **raw 64-byte r||s** pair, while
`cryptography` verifies **ASN.1 DER**. The raw pair is split and re-encoded
here. Everything else is the library's job.

The other detail that matters is what gets signed: the **base64url payload
string** as UTF-8 bytes, not the decoded JSON. That is what
kiri-license/src/token.js passes to `crypto.subtle.sign`, so that is what
we verify against.

Reference: kiri-license/src/token.js.
"""

from __future__ import annotations

import base64
import json
import time
from typing import Any

# Flet publishes Android and iOS wheels for cryptography on its own index
# (pypi.flet.dev), so this import works on every platform we ship, including
# the direct APK. No fallback or platform guard is needed.
from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec, utils

# WebCrypto's raw P-256 signature is r and s, 32 bytes each, big-endian.
_RAW_SIG_LEN = 64
_COORD_LEN = 32


class TokenError(Exception):
    """The token is malformed, unsigned by us, or not valid here."""


def _b64url_decode(value: str) -> bytes:
    normalized = str(value).replace("-", "+").replace("_", "/")
    padded = normalized + "=" * ((4 - (len(normalized) % 4)) % 4)
    try:
        return base64.b64decode(padded)
    except (ValueError, TypeError) as exc:
        raise TokenError("invalid base64url") from exc


def _public_key(public_key_b64url: str) -> ec.EllipticCurvePublicKey:
    """Load a base64url SPKI DER public key as a P-256 verifying key."""
    der = _b64url_decode(public_key_b64url)
    try:
        key = serialization.load_der_public_key(der)
    except Exception as exc:  # cryptography raises several unrelated types
        raise TokenError("public key is not a readable SPKI DER key") from exc
    if not isinstance(key, ec.EllipticCurvePublicKey) or not isinstance(
        key.curve, ec.SECP256R1
    ):
        raise TokenError("public key is not ECDSA P-256")
    return key


def _der_from_raw(signature: bytes) -> bytes:
    """Convert WebCrypto's raw r||s into the DER that cryptography wants."""
    if len(signature) != _RAW_SIG_LEN:
        raise TokenError("signature is not a raw 64-byte P-256 pair")
    r = int.from_bytes(signature[:_COORD_LEN], "big")
    s = int.from_bytes(signature[_COORD_LEN:], "big")
    return utils.encode_dss_signature(r, s)


def verify_token(token: str, public_key_b64url: str) -> dict[str, Any]:
    """Verify the signature and return the decoded claims.

    Raises TokenError when the token is not a well-formed, correctly signed
    v1 entitlement. This is the only thing standing between a pasted
    string and Premium, so it fails closed on every ambiguity.
    """
    if not token or not isinstance(token, str):
        raise TokenError("empty token")
    parts = token.split(".")
    if len(parts) != 3 or parts[0] != "v1":
        raise TokenError("unsupported token format")
    payload_b64url, signature_b64url = parts[1], parts[2]
    if not payload_b64url or not signature_b64url:
        raise TokenError("empty token segment")

    key = _public_key(public_key_b64url)
    der_signature = _der_from_raw(_b64url_decode(signature_b64url))
    try:
        key.verify(
            der_signature,
            payload_b64url.encode("utf-8"),
            ec.ECDSA(hashes.SHA256()),
        )
    except InvalidSignature as exc:
        raise TokenError("signature does not match") from exc

    try:
        claims = json.loads(_b64url_decode(payload_b64url).decode("utf-8"))
    except (ValueError, UnicodeDecodeError) as exc:
        raise TokenError("payload is not valid JSON") from exc
    if not isinstance(claims, dict):
        raise TokenError("payload is not an object")
    return claims


def claims_are_valid(
    claims: dict[str, Any],
    *,
    app_id: str,
    issuer: str,
    now: float | None = None,
) -> bool:
    """Check the binding claims, not the signature.

    A valid signature only proves the Worker issued the token. These checks
    stop a token for another app, or one that has aged out, from unlocking
    anything here.
    """
    if not isinstance(claims, dict):
        return False
    if claims.get("iss") != issuer:
        return False
    if claims.get("app") != app_id:
        return False
    if claims.get("status") not in ("active", "grace"):
        return False
    expires = claims.get("exp")
    if not isinstance(expires, (int, float)):
        return True
    return (now if now is not None else time.time()) < float(expires)


def is_entitled(
    token: str,
    public_key_b64url: str,
    *,
    app_id: str,
    issuer: str,
    now: float | None = None,
) -> tuple[bool, str]:
    """Offline check: (entitled, reason). Never raises.

    `reason` is a short string for logs, not user copy.
    """
    try:
        claims = verify_token(token, public_key_b64url)
    except TokenError as exc:
        return (False, f"invalid:{exc}")
    if not claims_are_valid(claims, app_id=app_id, issuer=issuer, now=now):
        return (False, "claims_rejected")
    return (True, "ok")
