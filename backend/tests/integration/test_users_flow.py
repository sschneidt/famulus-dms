"""Benutzerverwaltung gegen echte DB: Mitglieder anlegen, Rollen, Passwoerter, deaktivieren."""
import httpx

from homedms.main import app

from .helpers import API, bootstrap_and_login


async def login(client: httpx.AsyncClient, email: str, password: str) -> httpx.Response:
    return await client.post(f"{API}/auth/login", json={"email": email, "password": password})


def bearer(r: httpx.Response) -> dict:
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


async def test_benutzerverwaltung(clean_database):
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        admin = await bootstrap_and_login(client)
        me = (await client.get(f"{API}/auth/me", headers=admin)).json()

        # --- Mitglied anlegen; E-Mail eindeutig (Gross-/Kleinschreibung egal) -------------------
        r = await client.post(f"{API}/users", headers=admin, json={
            "email": "Anna@Example.com", "display_name": "Anna", "password": "start-passwort"})
        assert r.status_code == 201, r.text
        anna = r.json()
        assert anna["role"] == "member" and anna["is_active"] is True
        r = await client.post(f"{API}/users", headers=admin, json={
            "email": "anna@example.com", "display_name": "Doppelt", "password": "start-passwort"})
        assert r.status_code == 409
        assert (await client.post(f"{API}/users", headers=admin, json={
            "email": "kurz@example.com", "display_name": "K", "password": "kurz"})).status_code == 422

        # Anmelden mit anderer Schreibweise; Mitglied darf nicht verwalten, aber die Liste sehen
        member = bearer(await login(client, "anna@example.com", "start-passwort"))
        users = (await client.get(f"{API}/users", headers=member)).json()
        assert {u["display_name"] for u in users} == {"Admin", "Anna"}
        assert (await client.post(f"{API}/users", headers=member, json={
            "email": "x@example.com", "display_name": "X", "password": "start-passwort"})).status_code == 403
        assert (await client.patch(f"{API}/users/{me['id']}", headers=member, json={"role": "member"})).status_code == 403

        # --- eigenes Passwort aendern ----------------------------------------------------------
        r = await client.put(f"{API}/auth/password", headers=member,
                             json={"current_password": "falsch-falsch", "new_password": "neues-passwort"})
        assert r.status_code == 400
        r = await client.put(f"{API}/auth/password", headers=member,
                             json={"current_password": "start-passwort", "new_password": "neues-passwort"})
        assert r.status_code == 204
        assert (await login(client, "anna@example.com", "start-passwort")).status_code == 401
        refresh = (await login(client, "anna@example.com", "neues-passwort")).json()["refresh_token"]

        # --- Admin setzt Passwort zurueck -> alte Anmeldungen ungueltig --------------------------
        r = await client.put(f"{API}/users/{anna['id']}/password", headers=admin, json={"password": "vom-admin-gesetzt"})
        assert r.status_code == 204
        assert (await client.post(f"{API}/auth/refresh", json={"refresh_token": refresh})).status_code == 401
        member = bearer(await login(client, "anna@example.com", "vom-admin-gesetzt"))

        # --- Rollen: zweiter Admin; der letzte Admin bleibt geschuetzt ---------------------------
        assert (await client.patch(f"{API}/users/{me['id']}", headers=admin, json={"role": "member"})).status_code == 409
        assert (await client.patch(f"{API}/users/{me['id']}", headers=admin, json={"is_active": False})).status_code == 409
        r = await client.patch(f"{API}/users/{anna['id']}", headers=admin, json={"role": "admin", "display_name": "Anna M."})
        assert r.json()["role"] == "admin" and r.json()["display_name"] == "Anna M."
        r = await client.patch(f"{API}/users/{me['id']}", headers=member, json={"role": "member"})  # Anna stuft Admin herab
        assert r.status_code == 200
        assert (await client.patch(f"{API}/users/{anna['id']}", headers=member, json={"role": "member"})).status_code == 409
        r = await client.patch(f"{API}/users/{me['id']}", headers=member, json={"role": "admin"})
        assert r.status_code == 200

        # --- deaktivieren: sofort ausgesperrt, Daten bleiben; wieder aktivierbar ----------------
        r = await client.patch(f"{API}/users/{anna['id']}", headers=admin, json={"is_active": False})
        assert r.status_code == 200 and r.json()["is_active"] is False
        assert (await client.get(f"{API}/auth/me", headers=member)).status_code == 401
        r = await login(client, "anna@example.com", "vom-admin-gesetzt")
        assert r.status_code == 401 and "deaktiviert" in r.json()["detail"]
        r = await client.patch(f"{API}/users/{anna['id']}", headers=admin, json={"is_active": True})
        assert r.json()["is_active"] is True
        assert (await login(client, "anna@example.com", "vom-admin-gesetzt")).status_code == 200

        # fremde/unbekannte Nutzer
        unknown = "00000000-0000-0000-0000-000000000000"
        assert (await client.patch(f"{API}/users/{unknown}", headers=admin, json={"role": "admin"})).status_code == 404
