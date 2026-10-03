"""homedms/cli.py gegen echte DB: Nutzer auflisten, Passwort zuruecksetzen."""
import httpx

from homedms.cli import list_users, reset_password
from homedms.core import setup_code
from homedms.main import app

API = "/api/v1"


async def test_reset_password_allows_new_and_blocks_old_login(clean_database, capsys):
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        assert (await client.post(f"{API}/setup/bootstrap", json={
            "household_name": "Familie Test", "admin_email": "admin@example.com",
            "admin_password": "altes-passwort", "admin_display_name": "Admin", "setup_code": setup_code.get_or_create(),
        })).status_code == 201
        old_login = await client.post(f"{API}/auth/login", json={"email": "admin@example.com", "password": "altes-passwort"})
        old_refresh = old_login.json()["refresh_token"]

        assert await list_users() == 0
        out = capsys.readouterr().out
        assert "Familie Test" in out and "admin@example.com" in out and "admin" in out

        assert await reset_password("admin@example.com", "neues-passwort") == 0
        assert await reset_password("gibtsnicht@example.com", "egal-egal") == 1

        assert (await client.post(f"{API}/auth/login", json={"email": "admin@example.com", "password": "altes-passwort"})).status_code == 401
        assert (await client.post(f"{API}/auth/login", json={"email": "admin@example.com", "password": "neues-passwort"})).status_code == 200
        # bestehende Anmeldung (Refresh-Token) ist beendet
        assert (await client.post(f"{API}/auth/refresh", json={"refresh_token": old_refresh})).status_code == 401
