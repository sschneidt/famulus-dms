"""Sicherheit ohne Datenbank: Zwei-Faktor-Codes, Anmeldeschutz, Zertifikate, HTTP-Seite, Kopfzeilen."""
import subprocess
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pyotp
import pytest
from cryptography import x509
from cryptography.hazmat.primitives import serialization
from fastapi import FastAPI
from fastapi.testclient import TestClient

from homedms.api.routes.auth import device_name
from homedms.cert_page import build_redirect_app
from homedms.config import get_settings
from homedms.core import login_guard, tls, totp
from homedms.models.tenant import User
from homedms.security_headers import SecurityHeadersMiddleware

# --- Zwei-Faktor ------------------------------------------------------------------------------


def test_totp_codes_gelten_einmal_und_mit_kleiner_uhrabweichung():
    secret = totp.new_secret()
    now = 1_800_000_000.0
    app = pyotp.TOTP(secret)
    step = totp.verify(secret, app.at(now), None, now=now)
    assert step == int(now // 30)
    assert totp.verify(secret, app.at(now), step, now=now) is None  # schon benutzt
    assert totp.verify(secret, app.at(now + 30), step, now=now) == step + 1  # Handy-Uhr 30 s vor
    assert totp.verify(secret, app.at(now - 90), None, now=now) is None  # zu alt
    assert totp.verify(secret, "12 34", None, now=now) is None
    assert totp.verify(secret, f"{app.at(now)[:3]} {app.at(now)[3:]}", None, now=now) == step  # Leerzeichen egal


def test_wiederherstellungscodes():
    codes, hashes = totp.new_recovery_codes()
    assert len(codes) == 10 and all(len(c) == 9 and c[4] == "-" for c in codes)
    assert codes[0] not in hashes  # nur Hashes gespeichert
    remaining = totp.use_recovery_code(hashes, codes[3].upper().replace("-", ""))
    assert remaining is not None and len(remaining) == 9
    assert totp.use_recovery_code(remaining, codes[3]) is None
    assert totp.use_recovery_code(None, codes[0]) is None


def test_qr_code_ist_svg():
    svg = totp.qr_svg(totp.provisioning_uri(totp.new_secret(), "a@example.com"))
    assert svg.startswith("<svg") and "</svg>" in svg


# --- Anmeldeschutz ----------------------------------------------------------------------------


def test_sperrzeit_waechst_und_ist_begrenzt():
    user = User(failed_logins=0, locked_until=None)
    minutes = []
    for _ in range(14):
        login_guard.record_failure(user)
        minutes.append(round((user.locked_until - datetime.now(timezone.utc)).total_seconds() / 60) if user.locked_until else 0)
    assert minutes[:4] == [0, 0, 0, 0]
    assert minutes[4:10] == [1, 2, 4, 8, 16, 32]
    assert max(minutes) == get_settings().login_max_lock_minutes
    with pytest.raises(Exception) as exc:
        login_guard.check_locked(user)
    assert exc.value.status_code == 429
    login_guard.record_success(user)
    assert user.failed_logins == 0 and user.locked_until is None
    login_guard.check_locked(user)


def test_zu_viele_versuche_von_einer_adresse():
    ip = "10.9.9.9"
    login_guard.reset_ip(ip)
    for _ in range(login_guard.IP_MAX_FAILURES):
        login_guard.check_ip(ip)
        login_guard.record_ip_failure(ip)
    with pytest.raises(Exception) as exc:
        login_guard.check_ip(ip)
    assert exc.value.status_code == 429
    login_guard.reset_ip(ip)


@pytest.mark.parametrize(("ua", "expected"), [
    ("Mozilla/5.0 (iPhone; CPU iPhone OS 18_0 like Mac OS X) AppleWebKit Version/18.0 Mobile Safari/604.1", "Safari auf iPhone"),
    ("Mozilla/5.0 (Linux; Android 14; Pixel 8) AppleWebKit Chrome/130.0 Mobile Safari/537.36", "Chrome auf Android"),
    ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit Chrome/130.0 Safari/537.36 Edg/130.0", "Edge auf Windows"),
    ("Mozilla/5.0 (Macintosh; Intel Mac OS X 14.5; rv:131.0) Gecko/20100101 Firefox/131.0", "Firefox auf Mac"),
    ("python-httpx/0.28", "Skript"),
    (None, "Unbekanntes Gerät"),
])
def test_geraetename(ua, expected):
    assert device_name(ua) == expected


# --- Zertifikate ------------------------------------------------------------------------------


def _openssl_verify(ca: Path, leaf_pem: bytes, tmp: Path) -> bool:
    leaf = tmp / "leaf.pem"
    leaf.write_bytes(leaf_pem)
    result = subprocess.run(["openssl", "verify", "-CAfile", str(ca), str(leaf)], capture_output=True, text=True)
    return result.returncode == 0


def test_zertifikat_deckt_heimnetz_ab_und_ca_kann_keine_fremden_seiten(tmp_path):
    files = tls.ensure_certificates(tmp_path / "tls", "nas,192.168.1.10,8.8.8.8,www.bank.de")
    assert {"nas", "192.168.1.10", "localhost", "127.0.0.1"} <= set(files.names)
    assert "8.8.8.8" not in files.names and "www.bank.de" not in files.names
    assert oct((tmp_path / "tls" / "ca.key").stat().st_mode)[-3:] == "600"
    leaf = files.cert.read_bytes().split(b"-----END CERTIFICATE-----")[0] + b"-----END CERTIFICATE-----\n"
    if subprocess.run(["which", "openssl"], capture_output=True).returncode == 0:
        assert _openssl_verify(files.ca_cert, leaf, tmp_path)
        # gestohlener CA-Schluessel: Zertifikat fuer eine Bank wird trotzdem abgelehnt
        ca = x509.load_pem_x509_certificate(files.ca_cert.read_bytes())
        key = serialization.load_pem_private_key((tmp_path / "tls" / "ca.key").read_bytes(), None)
        evil_dir = tmp_path / "evil"
        evil_dir.mkdir()
        tls._create_server_cert(evil_dir, ["www.bank.de"], ca, key)
        evil = (evil_dir / "server.crt").read_bytes().split(b"-----END CERTIFICATE-----")[0] + b"-----END CERTIFICATE-----\n"
        assert not _openssl_verify(files.ca_cert, evil, tmp_path)


def test_zertifikat_wird_nur_bei_bedarf_erneuert(tmp_path, monkeypatch):
    first = tls.ensure_certificates(tmp_path, "nas")
    cert_bytes = first.cert.read_bytes()
    again = tls.ensure_certificates(tmp_path, "nas")
    assert again.cert.read_bytes() == cert_bytes  # nichts zu tun
    with_new_ip = tls.ensure_certificates(tmp_path, "nas,192.168.178.20")
    assert "192.168.178.20" in with_new_ip.names and with_new_ip.fingerprint == first.fingerprint  # CA bleibt
    before = with_new_ip.cert.read_bytes()
    monkeypatch.setattr(tls, "RENEW_BEFORE", timedelta(days=400))  # "laeuft bald ab"
    renewed = tls.ensure_certificates(tmp_path, "nas,192.168.178.20")
    assert renewed.cert.read_bytes() != before and renewed.fingerprint == first.fingerprint
    info = tls.certificate_info(tmp_path)
    assert info["fingerprint"] == first.fingerprint and "nas" in info["names"]


# --- HTTP-Seite und Kopfzeilen --------------------------------------------------------------


def test_http_seite_leitet_um_und_hilft_beim_zertifikat(tmp_path):
    files = tls.ensure_certificates(tmp_path, "nas")
    client = TestClient(build_redirect_app(8443, files), base_url="http://nas:8000")
    r = client.get("/dokumente/5?x=1", follow_redirects=False)
    assert r.status_code == 308 and r.headers["location"] == "https://nas:8443/dokumente/5?x=1"
    assert client.get("/health").json() == {"status": "ok"}
    page = client.get("/zertifikat")
    assert page.status_code == 200 and files.fingerprint in page.text and "data:image/svg+xml" in page.text
    assert "https://nas:8443/" in page.text and "script" not in page.headers["content-security-policy"]
    ca = client.get("/homedms-ca.crt")
    assert ca.headers["content-type"] == "application/x-x509-ca-cert" and b"BEGIN CERTIFICATE" in ca.content
    assert b"PRIVATE" not in ca.content


def test_sicherheits_kopfzeilen():
    app = FastAPI()

    @app.get("/api/v1/x")
    async def x() -> dict:
        return {}

    app.add_middleware(SecurityHeadersMiddleware)
    r = TestClient(app).get("/api/v1/x")
    assert "default-src 'self'" in r.headers["content-security-policy"]
    assert r.headers["x-frame-options"] == "SAMEORIGIN" and r.headers["x-content-type-options"] == "nosniff"
    assert r.headers["cache-control"] == "no-store"
    assert "strict-transport-security" not in r.headers  # bewusst (Port 8000 bleibt HTTP fuer neue Geraete)


def test_api_doku_ist_aus():
    from homedms.main import app

    client = TestClient(app)
    assert client.get("/docs").status_code == 404 and client.get("/openapi.json").status_code == 404
