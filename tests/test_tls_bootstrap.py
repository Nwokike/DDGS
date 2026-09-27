"""The Android CA repair (second pass, the real root cause).

The runtime points SSL_CERT_FILE into the app CACHE dir, which IS the
temp dir on Android (getTemporaryDirectory -> getCacheDir) and which our
own clear_temp() empties seconds after launch. httpx reads the variable
at CLIENT construction, so every client raised FileNotFoundError
mid-startup: catalog, engine download, license service, both chat legs.
Desktop ships no such variable and tested clean. The repair pins the
variable to a staged copy under data/, which nothing wipes.
"""

from __future__ import annotations

import os
from pathlib import Path

from core.tls import ensure_ca_bundle


def _mount_storage(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("FLET_APP_STORAGE_DATA", str(tmp_path / "data"))
    monkeypatch.setenv("FLET_APP_STORAGE_CACHE", str(tmp_path / "cache"))
    monkeypatch.setenv("FLET_APP_STORAGE_TEMP", str(tmp_path / "temp"))


def test_broken_pointer_repoints_to_the_staged_data_copy(tmp_path, monkeypatch):
    _mount_storage(tmp_path, monkeypatch)
    monkeypatch.setenv("SSL_CERT_FILE", "/nonexistent/ca.pem")
    status = ensure_ca_bundle()

    import certifi

    staged = tmp_path / "data" / "ca" / "cacert.pem"
    assert os.environ["SSL_CERT_FILE"] == str(staged)
    assert staged.is_file() and staged.stat().st_size > 0
    assert staged.read_bytes() == Path(certifi.where()).read_bytes()
    assert "->" in status


def test_cache_dir_file_repoints_even_though_it_exists_today(tmp_path, monkeypatch):
    """The phone's exact failure: the file exists at boot (yesterday's
    log: 'kept (existing file)'), then clear_temp deletes it seconds
    later. Existence proves nothing when the path sits in a wiped dir."""
    _mount_storage(tmp_path, monkeypatch)
    cache = tmp_path / "cache"
    cache.mkdir()
    doomed = cache / "tmpabc123cacert.pem"
    doomed.write_text("x")
    monkeypatch.setenv("SSL_CERT_FILE", str(doomed))

    status = ensure_ca_bundle()
    assert os.environ["SSL_CERT_FILE"] == str(tmp_path / "data" / "ca" / "cacert.pem")
    assert "kept" not in status
    assert doomed.exists()  # the repair abandons it; clear_temp spares it too


def test_stable_file_outside_the_wipe_dirs_is_kept(tmp_path, monkeypatch):
    """A real user/system override outside temp/ and cache/ must win."""
    _mount_storage(tmp_path, monkeypatch)
    custom = tmp_path / "custom-ca.pem"
    custom.write_text("custom")
    monkeypatch.setenv("SSL_CERT_FILE", str(custom))
    status = ensure_ca_bundle()
    assert os.environ["SSL_CERT_FILE"] == str(custom)
    assert "kept" in status


def test_unset_variable_gets_pinned_to_the_staged_copy(tmp_path, monkeypatch):
    _mount_storage(tmp_path, monkeypatch)
    monkeypatch.delenv("SSL_CERT_FILE", raising=False)
    ensure_ca_bundle()
    assert os.environ["SSL_CERT_FILE"] == str(tmp_path / "data" / "ca" / "cacert.pem")


def test_missing_ssl_cert_dir_is_dropped(tmp_path, monkeypatch):
    _mount_storage(tmp_path, monkeypatch)
    monkeypatch.delenv("SSL_CERT_FILE", raising=False)
    monkeypatch.setenv("SSL_CERT_DIR", "/nonexistent/certs")
    ensure_ca_bundle()
    assert "SSL_CERT_DIR" not in os.environ


def test_valid_ssl_cert_dir_is_kept(tmp_path, monkeypatch):
    _mount_storage(tmp_path, monkeypatch)
    monkeypatch.delenv("SSL_CERT_FILE", raising=False)
    certs = tmp_path / "certs"
    certs.mkdir()
    monkeypatch.setenv("SSL_CERT_DIR", str(certs))
    ensure_ca_bundle()
    assert os.environ["SSL_CERT_DIR"] == str(certs)


def test_httpx_client_constructs_after_the_repair(tmp_path, monkeypatch):
    """The phone's exact failure line: client construction, before I/O."""
    import httpx

    _mount_storage(tmp_path, monkeypatch)
    monkeypatch.setenv("SSL_CERT_FILE", "/nonexistent/ca.pem")
    ensure_ca_bundle()
    client = httpx.AsyncClient(http2=False)  # raised FileNotFoundError before
    assert client is not None


def test_clear_temp_spares_ca_and_engine_cache(tmp_path, monkeypatch):
    """clear_temp once deleted the very file SSL_CERT_FILE pointed at
    (and would delete the engine offline tier with it, since Android's
    temp dir is the cache dir)."""
    monkeypatch.setenv("FLET_APP_STORAGE_TEMP", str(tmp_path / "temp"))
    temp = tmp_path / "temp"
    temp.mkdir(parents=True)

    junk = temp / "scrape.html"
    junk.write_text("scratch")
    runtime_ca = temp / "tmpabc123cacert.pem"
    runtime_ca.write_text("pem")
    engine = temp / "engine_local.py"
    engine.write_text("code")
    referred = temp / "runtime_ca.pem"
    referred.write_text("pem")
    monkeypatch.setenv("SSL_CERT_FILE", str(referred))

    from core.storage_paths import clear_temp

    removed = clear_temp()
    assert removed == 1, "only the unprotected scratch may go"
    assert not junk.exists()
    for survivor in (runtime_ca, engine, referred):
        assert survivor.exists(), f"clear_temp deleted {survivor.name}"
