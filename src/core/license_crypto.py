"""ECDSA P-256 verification for Kiri License entitlement tokens.

Pure standard library on purpose. The Worker signs with WebCrypto, and
reproducing that exactly in Python needs no third-party package:

  - the signature is **raw r||s** (64 bytes for P-256), not DER
  - the signed message is the **base64url payload string** as UTF-8 bytes,
    not the decoded JSON
  - the public key is a base64url **SPKI DER** blob

`cryptography` would do this too, but it is a Rust extension and the
main branch's Android build only pre-compiles wheels for primp and ddgs.
A missing wheel for that target would break the APK, so this stays stdlib.

Reference: kiri-license/src/token.js and src/entitlements.js.
"""

from __future__ import annotations

import base64
import hashlib
import json
import time
from typing import Any

# NIST P-256 / secp256r1 domain parameters.
_P = 0xFFFFFFFF00000001000000000000000000000000FFFFFFFFFFFFFFFFFFFFFFFF
_A = _P - 3
_B = 0x5AC635D8AA3A93E7B3EBBD55769886BC651D06B0CC53B0F63BCE3C3E27D2604B
_N = 0xFFFFFFFF00000000FFFFFFFFFFFFFFFFBCE6FAADA7179E84F3B9CAC2FC632551
_G = (
    0x6B17D1F2E12C4247F8BCE6E563A440F277037D812DEB33A0F4A13945D898C296,
    0x4FE342E2FE1A7F9B8EE7EB4A7C0F9E162BCE33576B315ECECBB6406837BF51F5,
)
_COORD_BYTES = 32


class TokenError(Exception):
    """The token is malformed, unsigned by us, or not valid here."""


def _b64url_decode(value: str) -> bytes:
    normalized = str(value).replace("-", "+").replace("_", "/")
    padded = normalized + "=" * ((4 - (len(normalized) % 4)) % 4)
    try:
        return base64.b64decode(padded)
    except (ValueError, TypeError) as exc:
        raise TokenError("invalid base64url") from exc


def _point_add(p, q):
    if p is None:
        return q
    if q is None:
        return p
    x1, y1 = p
    x2, y2 = q
    if x1 == x2 and (y1 + y2) % _P == 0:
        return None
    if p == q:
        lam = (3 * x1 * x1 + _A) * pow(2 * y1, -1, _P) % _P
    else:
        lam = (y2 - y1) * pow(x2 - x1, -1, _P) % _P
    x3 = (lam * lam - x1 - x2) % _P
    return (x3, (lam * (x1 - x3) - y1) % _P)


def _point_mul(k: int, point):
    result = None
    while k:
        if k & 1:
            result = _point_add(result, point)
        point = _point_add(point, point)
        k >>= 1
    return result


def _read_tlv(der: bytes, pos: int) -> tuple[int, int, int]:
    """Read one DER element: (tag, content_offset, content_length)."""
    if pos + 2 > len(der):
        raise TokenError("public key is truncated")
    tag = der[pos]
    first = der[pos + 1]
    if first < 0x80:
        return (tag, pos + 2, first)
    count = first & 0x7F
    if count == 0 or count > 4 or pos + 2 + count > len(der):
        raise TokenError("public key has an unusable length")
    length = int.from_bytes(der[pos + 2 : pos + 2 + count], "big")
    return (tag, pos + 2 + count, length)


def public_key_point(public_key_b64url: str) -> tuple[int, int]:
    """Parse a base64url SPKI DER public key into an affine point.

    Layout accepted (what `tools/generate-keys.mjs` exports):
        SEQUENCE
          SEQUENCE  AlgorithmIdentifier (ecPublicKey, prime256v1)
          BIT STRING  0x00 || 0x04 || X(32) || Y(32)
    Anything else raises rather than guessing.
    """
    der = _b64url_decode(public_key_b64url)
    try:
        tag, body, body_len = _read_tlv(der, 0)
        if tag != 0x30 or body + body_len > len(der):
            raise TokenError("public key is not a DER SEQUENCE")
        tag, _alg_body, alg_len = _read_tlv(der, body)
        if tag != 0x30:
            raise TokenError("public key has no algorithm identifier")
        # alg_len is the content length and its header is 2 bytes, so the
        # subjectPublicKey BIT STRING starts right after both.
        tag, bit_body, bit_len = _read_tlv(der, body + 2 + alg_len)
        if tag != 0x03:
            raise TokenError("public key has no subjectPublicKey")
        # BIT STRING content = 1 unused-bits byte + 0x04 + X(32) + Y(32).
        if bit_len != 2 + 2 * _COORD_BYTES:
            raise TokenError("public key point has the wrong length")
        if der[bit_body] != 0x00 or der[bit_body + 1] != 0x04:
            raise TokenError("public key point is not uncompressed")
        x = int.from_bytes(der[bit_body + 2 : bit_body + 34], "big")
        y = int.from_bytes(der[bit_body + 34 : bit_body + 66], "big")
    except IndexError as exc:
        raise TokenError("public key is truncated") from exc
    if not (0 < x < _P and 0 < y < _P):
        raise TokenError("public key coordinates are out of range")
    if (y * y - (x * x * x + _A * x + _B)) % _P != 0:
        raise TokenError("public key is not on the P-256 curve")
    return (x, y)


def _verify_signature(payload_b64url: str, signature: bytes, point) -> bool:
    if len(signature) != 2 * _COORD_BYTES:
        return False
    r = int.from_bytes(signature[:_COORD_BYTES], "big")
    s = int.from_bytes(signature[_COORD_BYTES:], "big")
    if not (1 <= r < _N and 1 <= s < _N):
        return False
    digest = hashlib.sha256(payload_b64url.encode("utf-8")).digest()
    z = int.from_bytes(digest, "big")
    try:
        w = pow(s, -1, _N)
    except ValueError:
        return False
    candidate = _point_add(_point_mul(z * w % _N, _G), _point_mul(r * w % _N, point))
    if candidate is None:
        return False
    return candidate[0] % _N == r


def verify_token(token: str, public_key_b64url: str) -> dict[str, Any]:
    """Verify signature and decode claims.

    Returns the claim dict. Raises TokenError when the token is not a
    well-formed, correctly signed v1 entitlement.
    """
    if not token or not isinstance(token, str):
        raise TokenError("empty token")
    parts = token.split(".")
    if len(parts) != 3 or parts[0] != "v1":
        raise TokenError("unsupported token format")
    payload_b64url, signature_b64url = parts[1], parts[2]
    if not payload_b64url or not signature_b64url:
        raise TokenError("empty token segment")
    signature = _b64url_decode(signature_b64url)
    if not _verify_signature(payload_b64url, signature, public_key_point(public_key_b64url)):
        raise TokenError("signature does not match")
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

    A valid signature only proves the Worker issued it. These checks stop
    a token for a different app, or one that has aged out, from unlocking
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

    `reason` is a short machine-ish string for logging, not user copy.
    """
    try:
        claims = verify_token(token, public_key_b64url)
    except TokenError as exc:
        return (False, f"invalid:{exc}")
    if not claims_are_valid(
        claims, app_id=app_id, issuer=issuer, now=now
    ):
        return (False, "claims_rejected")
    return (True, "ok")
