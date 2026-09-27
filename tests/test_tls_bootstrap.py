"""The Android CA repair (Phase 5 phone fix).

Before this fix every httpx client on device raised FileNotFoundError at
construction because the runtime exported SSL_CERT_FILE at a path that does
not exist in the app sandbox: model catalog, router probes, gateway
streaming and the license service were all dead while desktop worked.
"""

from __future__ import annotations

import os

from core.tls import ensure_ca_bundle


def test_broken_ssl_cert_file_is_repointed_to_certifi(monkeypatch):
    import certifi

    monkeypatch.setenv("SSL_CERT_FILE", "/nonexistent/ca.pem")
    status = ensure_ca_bundle()
    assert os.environ["SSL_CERT_FILE"] == certifi.where()
    assert "repaired" in status


def test_valid_ssl_cert_file_is_kept(monkeypatch, tmp_path):
    good = tmp_path / "ca.pem"
    good.write_bytes(b"x")
    monkeypatch.setenv("SSL_CERT_FILE", str(good))
    status = ensure_ca_bundle()
    assert os.environ["SSL_CERT_FILE"] == str(good)
    assert "kept" in status


def test_unset_ssl_cert_file_stays_unset(monkeypatch):
    monkeypatch.delenv("SSL_CERT_FILE", raising=False)
    status = ensure_ca_bundle()
    assert "SSL_CERT_FILE" not in os.environ
    assert "unset" in status


def test_missing_ssl_cert_dir_is_dropped(monkeypatch):
    monkeypatch.setenv("SSL_CERT_FILE", "/nonexistent/ca.pem")
    monkeypatch.setenv("SSL_CERT_DIR", "/nonexistent/certs")
    ensure_ca_bundle()
    assert "SSL_CERT_DIR" not in os.environ


def test_valid_ssl_cert_dir_is_kept(monkeypatch, tmp_path):
    certs = tmp_path / "certs"
    certs.mkdir()
    monkeypatch.setenv("SSL_CERT_DIR", str(certs))
    ensure_ca_bundle()
    assert os.environ["SSL_CERT_DIR"] == str(certs)


def test_httpx_client_constructs_after_repair(monkeypatch):
    """The phone's exact failure: construction, before any network I/O.

    httpx checks SSL_CERT_FILE first and passes it to
    ssl.create_default_context(cafile=...); with the runtime's dead path
    that raised FileNotFoundError. After the repair the same construction
    must succeed.
    """
    import httpx

    monkeypatch.setenv("SSL_CERT_FILE", "/nonexistent/ca.pem")
    ensure_ca_bundle()
    client = httpx.AsyncClient(http2=False)  # would raise before the fix
    assert client is not None
