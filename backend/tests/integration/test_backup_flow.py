"""Datenbanksicherung aus der Anwendung mit echtem pg_dump gegen die Test-Datenbank."""
import httpx
import pytest

from homedms.config import get_settings
from homedms.core import backup
from homedms.core.security import hash_password
from homedms.db import async_session_factory
from homedms.main import app
from homedms.models.tenant import User, UserRole

from .helpers import API, bootstrap_and_login

pytestmark = pytest.mark.skipif(not backup.available(), reason="NICHT GEPRUEFT: pg_dump ist nicht installiert (postgresql-client)")


async def test_sicherung_anlegen_laden_loeschen(clean_database, monkeypatch, tmp_path):
    monkeypatch.setattr(get_settings(), "documents_path", str(tmp_path / "documents"))
    monkeypatch.setattr(get_settings(), "backup_path", str(tmp_path / "backups"))
    monkeypatch.setattr(get_settings(), "backup_keep", 2)

    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        auth = await bootstrap_and_login(client)

        r = await client.get(f"{API}/system/backups", headers=auth)
        assert r.status_code == 200 and r.json()["available"] is True and r.json()["items"] == []

        r = await client.post(f"{API}/system/backups", headers=auth)
        assert r.status_code == 201, r.text
        items = r.json()["items"]
        assert len(items) == 1 and items[0]["size"] > 1024

        # Herunterladen: ein echter PostgreSQL-Abzug im Format "custom" beginnt mit "PGDMP"
        name = items[0]["name"]
        r = await client.get(f"{API}/system/backups/{name}", headers=auth)
        assert r.status_code == 200 and r.content.startswith(b"PGDMP")

        # Mehr als "keep" bleiben nicht erhalten
        for stamp in ("a", "b"):
            (tmp_path / "backups" / f"homedms-0.0.{stamp}-x.dump").write_bytes(b"x" * 2000)
        r = await client.post(f"{API}/system/backups", headers=auth)
        assert r.status_code == 201 and len(r.json()["items"]) == 2

        name = r.json()["items"][0]["name"]
        r = await client.delete(f"{API}/system/backups/{name}", headers=auth)
        assert r.status_code == 200 and name not in [i["name"] for i in r.json()["items"]]
        assert (await client.delete(f"{API}/system/backups/{name}", headers=auth)).status_code == 404
        assert (await client.get(f"{API}/system/backups/..%2Fgeheim.dump", headers=auth)).status_code == 404


async def test_sicherung_nur_fuer_admins(clean_database, monkeypatch, tmp_path):
    monkeypatch.setattr(get_settings(), "documents_path", str(tmp_path / "documents"))
    monkeypatch.setattr(get_settings(), "backup_path", str(tmp_path / "backups"))

    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        auth = await bootstrap_and_login(client)
        # ohne Anmeldung
        assert (await client.get(f"{API}/system/backups")).status_code == 401
        assert (await client.post(f"{API}/system/backups")).status_code == 401

        # normales Haushaltsmitglied: kein Zugriff, und es entsteht keine Sicherung
        async with async_session_factory() as db:
            db.add(User(tenant_id=(await client.get(f"{API}/auth/me", headers=auth)).json()["tenant_id"],
                        email="anna@example.com", password_hash=hash_password("geheim-123"),
                        display_name="Anna", role=UserRole.member, notification_channels={}))
            await db.commit()
        token = (await client.post(f"{API}/auth/login", json={
            "email": "anna@example.com", "password": "geheim-123"})).json()["access_token"]
        anna = {"Authorization": f"Bearer {token}"}
        assert (await client.get(f"{API}/system/backups", headers=anna)).status_code == 403
        assert (await client.post(f"{API}/system/backups", headers=anna)).status_code == 403
        assert backup.list_backups() == []

        # Gegenprobe: der Admin darf
        assert (await client.get(f"{API}/system/backups", headers=auth)).status_code == 200