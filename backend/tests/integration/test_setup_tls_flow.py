"""Ersteinrichtung mit Name/Adresse des Servers: Das HTTPS-Zertifikat wird mit ihnen neu ausgestellt."""
import httpx

from homedms.config import get_settings
from homedms.core import setup_code, tls
from homedms.main import app

from .helpers import API


def payload(**extra) -> dict:
    return {
        "household_name": "Familie Test", "admin_email": "admin@example.com", "admin_password": "admin-passwort",
        "admin_display_name": "Admin", "setup_code": setup_code.get_or_create(), **extra,
    }


async def test_netzwerkname_kommt_ins_zertifikat(clean_database, monkeypatch, tmp_path):
    settings = get_settings()
    monkeypatch.setattr(settings, "documents_path", str(tmp_path / "documents"))
    monkeypatch.setattr(settings, "tls_dir", str(tmp_path / "tls"))
    monkeypatch.setattr(settings, "tls_mode", "auto")
    monkeypatch.setattr(tls, "RELOAD_HOOKS", [])
    monkeypatch.setattr(tls, "UNCOVERED", set())
    monkeypatch.setattr(tls, "CURRENT", tls.ensure_certificates(tmp_path / "tls"))
    reloaded = []
    tls.RELOAD_HOOKS.append(reloaded.append)

    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        status = (await client.get(f"{API}/setup/status")).json()
        assert status["bootstrapped"] is False and status["tls"] is True
        assert "192.168.7.7" not in status["tls_names"]

        # Eine Adresse von aussen wird abgelehnt - und es entsteht kein halber Haushalt
        r = await client.post(f"{API}/setup/bootstrap", json=payload(network_names="192.168.7.7, example.com"))
        assert r.status_code == 422 and "example.com" in r.json()["detail"], r.text
        assert (await client.get(f"{API}/setup/status")).json()["bootstrapped"] is False
        assert reloaded == [] and tls.saved_names(tmp_path / "tls") == []

        # Eine eingefuegte Browser-Adresse reicht
        r = await client.post(f"{API}/setup/bootstrap", json=payload(network_names="https://192.168.7.7:8443/, nas.local"))
        assert r.status_code == 201, r.text
        body = r.json()
        assert {"192.168.7.7", "nas.local"} <= set(body["tls_names"]) and body["tls_ca_replaced"] is False
        assert len(reloaded) == 1  # der laufende Server hat das neue Zertifikat bekommen

        status = (await client.get(f"{API}/setup/status")).json()
        assert status["bootstrapped"] is True and "192.168.7.7" in status["tls_names"]


async def test_ohne_angabe_bleibt_das_zertifikat_unveraendert(clean_database, monkeypatch, tmp_path):
    settings = get_settings()
    monkeypatch.setattr(settings, "documents_path", str(tmp_path / "documents"))
    monkeypatch.setattr(settings, "tls_dir", str(tmp_path / "tls"))
    monkeypatch.setattr(tls, "RELOAD_HOOKS", [])
    before = tls.ensure_certificates(tmp_path / "tls")
    monkeypatch.setattr(tls, "CURRENT", before)

    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        r = await client.post(f"{API}/setup/bootstrap", json=payload())
        assert r.status_code == 201, r.text
        assert tls.CURRENT is before and r.json()["tls_ca_replaced"] is False


async def test_ohne_eigene_zertifizierungsstelle_wird_die_angabe_ignoriert(clean_database, monkeypatch, tmp_path):
    """TLS_MODE=off (Reverse Proxy): tls.CURRENT ist leer, die Einrichtung geht trotzdem durch."""
    settings = get_settings()
    monkeypatch.setattr(settings, "documents_path", str(tmp_path / "documents"))
    monkeypatch.setattr(settings, "tls_dir", str(tmp_path / "tls"))
    monkeypatch.setattr(tls, "CURRENT", None)

    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        r = await client.post(f"{API}/setup/bootstrap", json=payload(network_names="192.168.7.7"))
        assert r.status_code == 201, r.text
        assert r.json()["tls_names"] == [] and not (tmp_path / "tls").exists()
