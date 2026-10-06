"""Sicherheit gegen echte DB: Einrichtungscode, Anmeldeschutz, Cookie-Sitzungen, Geraete, Zwei-Faktor."""
from datetime import datetime, timedelta, timezone

import httpx
import pyotp
from sqlalchemy import text

from homedms.cli import reset_two_factor
from homedms.core import setup_code
from homedms.db import async_session_factory
from homedms.main import app

from .helpers import API, bootstrap_and_login

COOKIE = {"X-HomeDMS-Session": "cookie", "User-Agent": "Mozilla/5.0 (iPhone; CPU iPhone OS 18_0) Safari/604.1"}


def client() -> httpx.AsyncClient:
    return httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="https://test")


async def test_einrichtung_nur_mit_code(clean_database, monkeypatch, tmp_path):
    from homedms.config import get_settings

    monkeypatch.setattr(get_settings(), "documents_path", str(tmp_path))
    async with client() as c:
        body = {"household_name": "F", "admin_email": "a@example.com", "admin_password": "admin-passwort",
                "admin_display_name": "A", "setup_code": "FALSCH"}
        r = await c.post(f"{API}/setup/bootstrap", json=body)
        assert r.status_code == 403 and "Einrichtungscode" in r.json()["detail"]
        code = setup_code.get_or_create()
        assert (tmp_path / ".einrichtungscode").read_text().strip() == code
        r = await c.post(f"{API}/setup/bootstrap", json={**body, "setup_code": code.lower()})
        assert r.status_code == 201
        assert not (tmp_path / ".einrichtungscode").exists()


async def test_anmeldeschutz_sperrt_nach_fehlversuchen(clean_database):
    async with client() as c:
        await bootstrap_and_login(c)
        login = {"email": "admin@example.com", "password": "falsch-falsch"}
        codes = [(await c.post(f"{API}/auth/login", json=login)).status_code for _ in range(6)]
        assert codes == [401, 401, 401, 401, 401, 429]
        r = await c.post(f"{API}/auth/login", json={**login, "password": "admin-passwort"})
        assert r.status_code == 429 and "Fehlversuche" in r.json()["detail"]  # auch das richtige Passwort wartet
        # nach Ablauf der Sperre klappt es und der Zaehler ist zurueckgesetzt
        async with async_session_factory() as db:
            await db.execute(text("UPDATE users SET locked_until = now() - interval '1 second'"))
            await db.commit()
        assert (await c.post(f"{API}/auth/login", json={**login, "password": "admin-passwort"})).status_code == 200
        async with async_session_factory() as db:
            assert await db.scalar(text("SELECT failed_logins FROM users")) == 0
        # unbekannte Adresse: gleiche Meldung wie falsches Passwort
        r = await c.post(f"{API}/auth/login", json={"email": "wer@example.com", "password": "egal-egal"})
        assert r.status_code == 401 and r.json()["detail"] == "E-Mail oder Passwort falsch"


async def test_cookie_sitzung_geraete_und_diebstahl(clean_database):
    async with client() as admin_client:
        await bootstrap_and_login(admin_client)
    async with client() as c:
        r = await c.post(f"{API}/auth/login", headers=COOKIE, json={"email": "admin@example.com", "password": "admin-passwort"})
        assert r.status_code == 200 and r.json()["refresh_token"] is None  # nur im Cookie
        cookie = r.headers["set-cookie"]
        assert "HttpOnly" in cookie and "SameSite=strict" in cookie and "Secure" in cookie and "Path=/api/v1/auth" in cookie
        access = {"Authorization": f"Bearer {r.json()['access_token']}"}
        first_refresh = c.cookies.get("homedms_refresh")

        r = await c.post(f"{API}/auth/refresh", headers=COOKIE)  # Cookie schickt httpx automatisch
        assert r.status_code == 200
        access = {"Authorization": f"Bearer {r.json()['access_token']}"}
        assert c.cookies.get("homedms_refresh") != first_refresh  # rotiert

        # zweites Geraet, dann Geraeteliste
        async with client() as other:
            r2 = await other.post(f"{API}/auth/login", json={"email": "admin@example.com", "password": "admin-passwort"},
                                  headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0) Chrome/130.0 Safari/537.36"})
            other_access = {"Authorization": f"Bearer {r2.json()['access_token']}"}
        sessions = (await c.get(f"{API}/auth/sessions", headers=access)).json()
        # aktuelles Geraet zuerst, dann nach letzter Nutzung (die Einrichtung lief per Skript)
        assert [s["device"] for s in sessions] == ["Safari auf iPhone", "Chrome auf Windows", "Skript"]
        assert sessions[0]["current"] is True and sessions[1]["current"] is False
        assert (await c.get(f"{API}/auth/me", headers=other_access)).status_code == 200
        # anderes Geraet abmelden -> dessen Zugang endet SOFORT (nicht erst nach 15 Min.)
        assert (await c.delete(f"{API}/auth/sessions/{sessions[1]['id']}", headers=access)).status_code == 204
        assert (await c.get(f"{API}/auth/me", headers=other_access)).status_code == 401
        assert len((await c.get(f"{API}/auth/sessions", headers=access)).json()) == 2
        assert (await c.delete(f"{API}/auth/sessions", headers=access)).status_code == 204  # ueberall sonst abmelden
        assert len((await c.get(f"{API}/auth/sessions", headers=access)).json()) == 1

        # Diebstahl: ein laengst ersetztes Refresh-Token taucht wieder auf -> ganze Sitzung beendet
        async with async_session_factory() as db:
            await db.execute(text("UPDATE refresh_tokens SET rotated_at = rotated_at - interval '5 minutes' WHERE rotated_at IS NOT NULL"))
            await db.commit()
        async with client() as thief:  # jemand hat das alte Cookie kopiert
            r = await thief.post(f"{API}/auth/refresh", json={"refresh_token": first_refresh})
        assert r.status_code == 401 and "Sicherheitsgründen" in r.json()["detail"]
        assert (await c.get(f"{API}/auth/me", headers=access)).status_code == 401


async def test_passwortwechsel_behaelt_dieses_geraet(clean_database):
    async with client() as c:
        auth = await bootstrap_and_login(c)
        other = (await c.post(f"{API}/auth/login", json={"email": "admin@example.com", "password": "admin-passwort"})).json()
        r = await c.put(f"{API}/auth/password", headers=auth,
                        json={"current_password": "admin-passwort", "new_password": "ganz-neues-passwort"})
        assert r.status_code == 204
        assert (await c.get(f"{API}/auth/me", headers=auth)).status_code == 200
        assert (await c.get(f"{API}/auth/me", headers={"Authorization": f"Bearer {other['access_token']}"})).status_code == 401
        assert (await c.post(f"{API}/auth/refresh", json={"refresh_token": other["refresh_token"]})).status_code == 401


async def test_zwei_faktor(clean_database, monkeypatch):
    async with client() as c:
        auth = await bootstrap_and_login(c)
        assert (await c.get(f"{API}/auth/2fa", headers=auth)).json() == {"enabled": False, "recovery_codes_left": 0}
        assert (await c.post(f"{API}/auth/2fa/setup", headers=auth, json={"password": "falsch"})).status_code == 400
        setup = (await c.post(f"{API}/auth/2fa/setup", headers=auth, json={"password": "admin-passwort"})).json()
        assert setup["uri"].startswith("otpauth://totp/Famulus%20DMS:admin%40example.com") and "<svg" in setup["qr_svg"]
        app_totp = pyotp.TOTP(setup["secret"])
        assert (await c.post(f"{API}/auth/2fa/enable", headers=auth, json={"code": "000000"})).status_code == 400
        r = await c.post(f"{API}/auth/2fa/enable", headers=auth, json={"code": app_totp.now()})
        assert r.status_code == 200
        recovery = r.json()["recovery_codes"]
        assert len(recovery) == 10 and len(set(recovery)) == 10
        assert (await c.get(f"{API}/auth/me", headers=auth)).json()["two_factor_enabled"] is True

        # Anmelden: Passwort -> challenge -> Code
        login = {"email": "admin@example.com", "password": "admin-passwort"}
        r = await c.post(f"{API}/auth/login", json=login)
        assert r.json()["two_factor_required"] is True and r.json()["access_token"] == ""
        challenge = r.json()["challenge"]
        assert (await c.post(f"{API}/auth/login/2fa", json={"challenge": challenge, "code": "123456"})).status_code == 401
        # derselbe Code wie bei der Einrichtung zaehlt nicht zweimal - der naechste schon
        future = app_totp.at(datetime.now(timezone.utc) + timedelta(seconds=30))
        r = await c.post(f"{API}/auth/login/2fa", json={"challenge": challenge, "code": future})
        assert r.status_code == 200 and r.json()["access_token"]
        assert (await c.post(f"{API}/auth/login/2fa", json={"challenge": challenge, "code": future})).status_code == 401

        # Wiederherstellungscode: einmal nutzbar
        challenge = (await c.post(f"{API}/auth/login", json=login)).json()["challenge"]
        r = await c.post(f"{API}/auth/login/2fa", json={"challenge": challenge, "code": recovery[0].upper()})
        assert r.status_code == 200 and "noch 9" in r.json()["notice"]
        challenge = (await c.post(f"{API}/auth/login", json=login)).json()["challenge"]
        assert (await c.post(f"{API}/auth/login/2fa", json={"challenge": challenge, "code": recovery[0]})).status_code == 401
        # abgelaufene/gefaelschte challenge
        assert (await c.post(f"{API}/auth/login/2fa", json={"challenge": "x.y.z", "code": "123456"})).status_code == 401
        assert (await c.post(f"{API}/auth/login/2fa", json={"challenge": auth["Authorization"][7:], "code": "123456"})).status_code == 401

        # Admin setzt 2FA eines Mitglieds zurueck (Handy verloren); eigenes geht nur selbst
        await c.post(f"{API}/users", headers=auth, json={"email": "kind@example.com", "display_name": "Kind", "password": "kinder-passwort"})
        kind_login = await c.post(f"{API}/auth/login", json={"email": "kind@example.com", "password": "kinder-passwort"})
        kind = {"Authorization": f"Bearer {kind_login.json()['access_token']}"}
        kind_setup = (await c.post(f"{API}/auth/2fa/setup", headers=kind, json={"password": "kinder-passwort"})).json()
        await c.post(f"{API}/auth/2fa/enable", headers=kind, json={"code": pyotp.TOTP(kind_setup["secret"]).now()})
        users = {u["email"]: u for u in (await c.get(f"{API}/users", headers=auth)).json()}
        assert users["kind@example.com"]["two_factor_enabled"] is True
        r = await c.patch(f"{API}/users/{users['kind@example.com']['id']}", headers=auth, json={"reset_two_factor": True})
        assert r.status_code == 200 and r.json()["two_factor_enabled"] is False
        assert (await c.get(f"{API}/auth/me", headers=kind)).status_code == 401  # abgemeldet
        assert (await c.patch(f"{API}/users/{users['admin@example.com']['id']}", headers=auth,
                              json={"reset_two_factor": True})).status_code == 409

        # einziger Admin hat Handy verloren -> Verwaltungsbefehl auf dem Server
        assert await reset_two_factor("admin@example.com") == 0
        r = await c.post(f"{API}/auth/login", json=login)
        assert r.json()["two_factor_required"] is False and r.json()["access_token"]
