"""Offline verification of Kiri License entitlement tokens.

The Worker (license.kiri.ng) signs ``v1.<b64url payload>.<b64url signature>``
with ECDSA P-256 / SHA-256 via WebCrypto, which emits a **raw r‖s** (IEEE
P1363, 64-byte) signature over the ASCII bytes of the payload segment.

Verification is pure Python (P-256 ECDSA over SHA-256), tested against
tokens signed by the Worker's own ``token.js`` — no crypto dependency, so
there is no wheel to resolve for Android and nothing to cross-compile.

Trust model (see kiri-license/docs/client-integration.md): the Worker is
authoritative whenever the app is online. The token is a signed cache that
keeps premium working offline, so a valid signature plus the claim checks
below are what unlock the app — never a bare client-side flag.
"""

from __future__ import annotations

import base64
import hashlib
import json
import logging
import time
from dataclasses import dataclass

logger = logging.getLogger(__name__)


# NIST P-256 (secp256r1) domain parameters.
_P = 0xFFFFFFFF00000001000000000000000000000000FFFFFFFFFFFFFFFFFFFFFFFF
_A = _P - 3
_B = 0x5AC635D8AA3A93E7B3EBBD55769886BC651D06B0CC53B0F63BCE3C3E27D2604B
_GX = 0x6B17D1F2E12C4247F8BCE6E563A440F277037D812DEB33A0F4A13945D898C296
_GY = 0x4FE342E2FE1A7F9B8EE7EB4A7C0F9E162BCE33576B315ECECBB6406837BF51F5
_N = 0xFFFFFFFF00000000FFFFFFFFFFFFFFFFBCE6FAADA7179E84F3B9CAC2FC632551

ISSUER = "license.kiri.ng"
_UNLOCKING_STATUSES = ("active", "grace")


class TokenRejected(Exception):
    """The token is not a valid entitlement for this app."""

    def __init__(self, reason: str, detail: str = ""):
        super().__init__(f"{reason}{': ' + detail if detail else ''}")
        self.reason = reason
        self.detail = detail


@dataclass(frozen=True)
class LicenseClaims:
    """The verified payload of an entitlement token."""

    ent: str
    app: str
    product: str
    scope: str
    mode: str
    status: str
    paid_through: int | None
    issued_at: int
    expires_at: int | None

    @property
    def is_lifetime(self) -> bool:
        return self.expires_at is None


def _b64url_decode(value: str) -> bytes:
    if not isinstance(value, str):
        raise TypeError("base64url value must be text")
    padded = value + "=" * ((-len(value)) % 4)
    return base64.b64decode(padded, altchars=b"-_", validate=True)


def _point_add(p1, p2):
    """Add two points on P-256 in affine coordinates; None is infinity."""
    if p1 is None:
        return p2
    if p2 is None:
        return p1
    x1, y1 = p1
    x2, y2 = p2
    if x1 == x2 and (y1 + y2) % _P == 0:
        return None
    if p1 == p2:
        lam = (3 * x1 * x1 + _A) * pow(2 * y1, -1, _P) % _P
    else:
        lam = (y2 - y1) * pow(x2 - x1, -1, _P) % _P
    x3 = (lam * lam - x1 - x2) % _P
    y3 = (lam * (x1 - x3) - y1) % _P
    return x3, y3


def _public_point_from_spki(public_key: str) -> tuple[int, int]:
    """Pull the uncompressed public point out of a base64url SPKI blob."""
    if not isinstance(public_key, str):
        raise TokenRejected("bad_public_key", "public key must be text")
    try:
        der = _b64url_decode(public_key)
    except Exception as ex:  # binascii.Error, ValueError, TypeError
        raise TokenRejected("bad_public_key", "not valid base64url") from ex
    if len(der) < 65 or der[-65] != 0x04:
        raise TokenRejected("bad_public_key", "not a P-256 SPKI public key")
    x = int.from_bytes(der[-64:-32], "big")
    y = int.from_bytes(der[-32:], "big")
    if (y * y - (x * x * x + _A * x + _B)) % _P != 0:
        raise TokenRejected("bad_public_key", "point is not on the curve")
    return x, y


def _ecdsa_verify(public_point, message: bytes, signature: bytes) -> bool:
    if len(signature) != 64:
        return False
    r = int.from_bytes(signature[:32], "big")
    s = int.from_bytes(signature[32:], "big")
    if not (1 <= r < _N and 1 <= s < _N):
        return False
    digest = hashlib.sha256(message).digest()
    e = int.from_bytes(digest, "big")
    w = pow(s, -1, _N)
    u1 = e * w % _N
    u2 = r * w % _N
    point = _point_add(
        _point_add(_scale((_GX, _GY), u1), _scale(public_point, u2)), None
    )
    if point is None:
        return False
    return point[0] % _N == r


def _scale(point, scalar: int):
    """k * P on P-256, using double-and-add."""
    if scalar % _N == 0 or point is None:
        return None
    result = None
    addend = point
    k = scalar
    while k:
        if k & 1:
            result = _point_add(result, addend)
        addend = _point_add(addend, addend)
        k >>= 1
    return result


def _verify_signature(public_key: str, message: bytes, signature: bytes) -> bool:
    """Verify the Worker's raw r‖s signature (P-256 ECDSA over SHA-256)."""
    if len(signature) != 64:
        return False
    return _ecdsa_verify(_public_point_from_spki(public_key), message, signature)


def verify_token(
    token: str,
    public_key: str,
    app_id: str,
    *,
    now: float | None = None,
) -> LicenseClaims:
    """Verify a Kiri License token and return its claims.

    Raises TokenRejected with a machine-readable ``reason`` so the UI can say
    what went wrong (expired, revoked, not this app, bad signature) instead
    of a generic failure.
    """
    if not token:
        raise TokenRejected("missing_token")
    parts = token.split(".")
    if len(parts) != 3 or parts[0] != "v1":
        raise TokenRejected("malformed_token")

    _, payload_b64, signature_b64 = parts
    try:
        signature = _b64url_decode(signature_b64)
        claims_raw = json.loads(_b64url_decode(payload_b64).decode("utf-8"))
    except (ValueError, UnicodeDecodeError) as ex:
        raise TokenRejected("malformed_token", str(ex)) from ex
    if not isinstance(claims_raw, dict):
        raise TokenRejected("malformed_token", "payload is not an object")

    # WebCrypto signs the ASCII bytes of the base64url payload segment, not
    # the decoded JSON — matching that is what makes the signature verify.
    if not _verify_signature(public_key, payload_b64.encode("utf-8"), signature):
        raise TokenRejected("bad_signature")

    # Every numeric claim is validated here: a signed token carrying a
    # string or non-finite `exp` must be rejected as malformed, not raise
    # a ValueError/OverflowError into the settings handler.
    try:
        issued_at_raw = claims_raw.get("iat")
        expires_raw = claims_raw.get("exp")
        if issued_at_raw is not None and type(issued_at_raw) is not int:
            raise ValueError("iat must be an integer")
        if expires_raw is not None and type(expires_raw) is not int:
            raise ValueError("exp must be an integer or null")
    except ValueError as ex:
        raise TokenRejected("malformed_claims", str(ex)) from ex

    if claims_raw.get("iss") != ISSUER:
        raise TokenRejected("bad_issuer", str(claims_raw.get("iss")))
    if claims_raw.get("app") != app_id:
        raise TokenRejected("wrong_app", str(claims_raw.get("app")))
    if claims_raw.get("v") != 1:
        raise TokenRejected("unsupported_version", str(claims_raw.get("v")))

    status = str(claims_raw.get("status") or "")
    if status not in _UNLOCKING_STATUSES:
        raise TokenRejected(status or "unknown_status", "not an active license")

    expires_at = claims_raw.get("exp")
    current = time.time() if now is None else now
    if expires_at is not None and int(expires_at) <= current:
        raise TokenRejected("expired", str(expires_at))

    return LicenseClaims(
        ent=str(claims_raw.get("ent") or ""),
        app=str(claims_raw.get("app") or ""),
        product=str(claims_raw.get("product") or ""),
        scope=str(claims_raw.get("scope") or ""),
        mode=str(claims_raw.get("mode") or ""),
        status=status,
        paid_through=claims_raw.get("paid_through"),
        issued_at=int(claims_raw.get("iat") or 0),
        expires_at=None if expires_at is None else int(expires_at),
    )
