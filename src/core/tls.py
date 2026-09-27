"""Repair the TLS trust store before the first HTTP client exists.

On Android the Flet runtime exports SSL_CERT_FILE pointing at a path that
does not exist inside the app sandbox. httpx checks that variable first
(httpx/_config.py create_ssl_context) and hands it to
ssl.create_default_context(cafile=...) unverified, so every client
construction raised FileNotFoundError before a single socket was opened:
model catalog, router probes, gateway streaming and the license service
were dead on device while desktop, which ships no such variable, worked.

certifi and its cacert.pem already travel inside the APK (httpx requires
certifi), so repointing the variable at that bundle repairs every httpx
call in one place, with no per-call-site changes.
"""

from __future__ import annotations

import os


def ensure_ca_bundle() -> str:
    """Fix a broken SSL_CERT_FILE / SSL_CERT_DIR pair; report what happened.

    Valid or absent values are left alone: desktop behaviour is already
    correct there and a user/system override must keep winning. The return
    string is logged at startup so the next phone log proves which branch
    ran.
    """
    parts: list[str] = []

    cert_file = os.environ.get("SSL_CERT_FILE")
    if cert_file:
        if os.path.isfile(cert_file):
            parts.append("SSL_CERT_FILE kept (existing file)")
        else:
            pem = ""
            try:
                import certifi

                pem = certifi.where()
            except Exception:
                pem = ""
            if pem and os.path.isfile(pem):
                os.environ["SSL_CERT_FILE"] = pem
                parts.append(f"repaired SSL_CERT_FILE {cert_file!r} -> certifi bundle")
            else:
                parts.append(
                    f"SSL_CERT_FILE {cert_file!r} missing and no certifi bundle found"
                )
    else:
        parts.append("SSL_CERT_FILE unset (httpx uses certifi directly)")

    cert_dir = os.environ.get("SSL_CERT_DIR")
    if cert_dir:
        if os.path.isdir(cert_dir):
            parts.append("SSL_CERT_DIR kept")
        else:
            # httpx prefers SSL_CERT_FILE but falls through to this capath
            # when the file variable is absent; a dead path here raises the
            # same FileNotFoundError one layer down.
            del os.environ["SSL_CERT_DIR"]
            parts.append(f"dropped missing SSL_CERT_DIR {cert_dir!r}")

    return "; ".join(parts)
