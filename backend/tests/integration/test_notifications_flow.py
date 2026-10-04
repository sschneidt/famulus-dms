"""Erinnerungen: taegliche Zusammenfassung in App, E-Mail und Push (Anforderungsdokument 4.5)."""
from datetime import date, timedelta

import httpx
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ec
from sqlalchemy import select, text

from homedms.config import get_settings
from homedms.core import mailer, notifications, webpush
from homedms.db import async_session_factory
from homedms.main import app
from homedms.models.ops import Notification, PushSubscription

from .helpers import API, bootstrap_and_login, pdf


class FakeSMTP:
    sent: list = []
    fail = False

    def __init__(self, host, port, timeout=None, **kw):
        pass

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def ehlo(self):
        pass

    def starttls(self, context=None):
        pass

    def login(self, user, password):
        assert password == "app-passwort"

    def send_message(self, msg):
        if FakeSMTP.fail:
            raise OSError("Verbindung abgelehnt")
        FakeSMTP.sent.append(msg)


def browser_keys() -> dict:
    key = ec.generate_private_key(ec.SECP256R1())
    public = key.public_key().public_bytes(serialization.Encoding.X962, serialization.PublicFormat.UncompressedPoint)
    return {"p256dh": webpush.b64url(public), "auth": webpush.b64url(b"0123456789abcdef")}


async def digests() -> int:
    async with async_session_factory() as db:
        created = await notifications.run_digests(db)
        await notifications.deliver_pending(db)
        return created


async def test_erinnerungen(clean_database, monkeypatch, tmp_path):
    monkeypatch.setattr(get_settings(), "documents_path", str(tmp_path))
    monkeypatch.setattr(mailer.smtplib, "SMTP", FakeSMTP)
    FakeSMTP.sent, FakeSMTP.fail = [], False
    pushed: list = []
    push_mode = {"value": "ok"}

    async def fake_push(vapid, endpoint, keys, message, subject, client=None):
        if push_mode["value"] == "gone":
            raise webpush.PushGone()
        webpush.encrypt(b"probe", keys["p256dh"], keys["auth"])
        pushed.append((endpoint, message, subject))

    monkeypatch.setattr(webpush, "send", fake_push)
    today = notifications.local_now().date()

    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        admin = await bootstrap_and_login(client)
        r = await client.post(f"{API}/users", headers=admin, json={
            "email": "anna@example.com", "display_name": "Anna", "password": "start-passwort"})
        assert r.status_code == 201, r.text
        token = (await client.post(f"{API}/auth/login", json={
            "email": "anna@example.com", "password": "start-passwort"})).json()["access_token"]
        anna = {"Authorization": f"Bearer {token}"}

        async def upload(auth, name):
            r = await client.post(f"{API}/documents", headers=auth, files={"file": (name, pdf(name), "application/pdf")})
            assert r.status_code == 201, r.text
            return r.json()["id"]

        async def termin(auth, doc, due: date, note: str, lead=30):
            r = await client.post(f"{API}/documents/{doc}/wiedervorlagen", headers=auth, json={
                "due_date": due.isoformat(), "note": note, "reminder_lead_days": lead})
            assert r.status_code == 201, r.text
            return r.json()["id"]

        kfz = await upload(admin, "kfz.pdf")
        strom = await upload(anna, "strom.pdf")
        kuendigung = await termin(admin, kfz, today + timedelta(days=7), "Kündigungsfrist")
        await termin(admin, kfz, today + timedelta(days=40), "Später")
        await termin(anna, strom, today - timedelta(days=2), "Zahlungsfrist")

        # --- Einstellungen: Standard E-Mail an, Push aus; E-Mail-Versand noch nicht eingerichtet ----
        s = (await client.get(f"{API}/notifications/settings", headers=admin)).json()
        assert s["email"] is True and s["push"] is False and s["digest_hour"] == 7
        assert s["email_available"] is False and len(webpush.b64url_decode(s["push_public_key"])) == 65
        for auth in (admin, anna):
            r = await client.patch(f"{API}/notifications/settings", headers=auth, json={"digest_hour": 0})
            assert r.status_code == 200 and r.json()["digest_hour"] == 0
        assert (await client.patch(f"{API}/notifications/settings", headers=anna, json={"digest_hour": 24})).status_code == 422

        # --- E-Mail-Versand: nur Admin; Passwort wird nie zurueckgegeben -------------------------
        mail = {"host": "smtp.example.com", "port": 587, "security": "starttls", "username": "haus@example.com",
                "password": "app-passwort", "sender": "haus@example.com", "app_url": "https://nas:8443/"}
        assert (await client.put(f"{API}/tenant/mail", headers=anna, json=mail)).status_code == 403
        r = await client.put(f"{API}/tenant/mail", headers=admin, json=mail)
        assert r.status_code == 200, r.text
        assert r.json()["password_set"] is True and "password" not in r.json() and r.json()["app_url"] == "https://nas:8443"
        async with async_session_factory() as db:
            stored = (await db.execute(text("SELECT mail_settings->>'password' FROM tenants"))).scalar()
        assert stored and "app-passwort" not in stored
        r = await client.put(f"{API}/tenant/mail", headers=admin, json={**mail, "password": None})
        assert r.json()["password_set"] is True  # leer gelassen = behalten

        r = await client.post(f"{API}/notifications/test", headers=anna, json={"channel": "email"})
        assert r.json() == {"ok": True, "message": "Test-E-Mail an anna@example.com verschickt."}
        assert FakeSMTP.sent.pop()["To"] == "anna@example.com"

        # --- Push: nur bekannte Push-Dienste, Schluessel muessen passen ------------------------------
        r = await client.post(f"{API}/notifications/push-subscriptions", headers=admin,
                              json={"endpoint": "https://evil.example.com/x", "keys": browser_keys()})
        assert r.status_code == 422
        endpoint = "https://fcm.googleapis.com/fcm/send/geraet-1"
        r = await client.post(f"{API}/notifications/push-subscriptions", headers={**admin, "User-Agent": "Mozilla/5.0 (Linux; Android 14) Chrome/130"},
                              json={"endpoint": endpoint, "keys": browser_keys()})
        assert r.status_code == 201, r.text
        assert r.json()["push"] is True and r.json()["push_devices"][0]["name"] == "Chrome auf Android"
        r = await client.post(f"{API}/notifications/test", headers=admin, json={"channel": "push"})
        assert r.json()["ok"] is True and pushed.pop()[2] == "mailto:admin@example.com"
        r = await client.post(f"{API}/notifications/test", headers=anna, json={"channel": "push"})
        assert r.json() == {"ok": False, "message": "Auf keinem Gerät ist Push eingeschaltet"}

        # --- Tageszusammenfassung -------------------------------------------------------------------
        assert await digests() == 2
        mails = {m["To"]: m for m in FakeSMTP.sent}
        assert set(mails) == {"admin@example.com", "anna@example.com"}
        admin_mail = mails["admin@example.com"].get_body(("plain",)).get_content()
        assert mails["admin@example.com"]["Subject"] == "HomeDMS: 1 demnächst"
        assert "Kündigungsfrist – kfz.pdf: in 7 Tagen fällig" in admin_mail and f"https://nas:8443/dokumente/{kfz}" in admin_mail
        assert "Später" not in admin_mail
        assert "Zahlungsfrist – strom.pdf: seit 2 Tagen überfällig" in mails["anna@example.com"].get_body(("plain",)).get_content()
        (endpoint_sent, message, _), = pushed
        assert endpoint_sent == endpoint and message["url"] == "/termine" and "Kündigungsfrist" in message["body"]

        inbox = (await client.get(f"{API}/notifications", headers=admin)).json()
        assert inbox["unread"] == 1
        item = inbox["items"][0]
        assert item["title"] == "Kündigungsfrist" and item["url"] == f"/dokumente/{kfz}"
        assert item["body"].startswith("kfz.pdf: in 7 Tagen fällig")
        anna_inbox = (await client.get(f"{API}/notifications", headers=anna)).json()
        assert [i["title"] for i in anna_inbox["items"]] == ["Zahlungsfrist"]

        # Gleicher Tag: keine zweite Zusammenfassung; gelesen markieren
        FakeSMTP.sent.clear()
        assert await digests() == 0 and FakeSMTP.sent == []
        assert (await client.post(f"{API}/notifications/{item['id']}/read", headers=anna)).status_code == 404
        assert (await client.post(f"{API}/notifications/{item['id']}/read", headers=admin)).status_code == 204
        assert (await client.get(f"{API}/notifications", headers=admin)).json()["unread"] == 0
        assert (await client.post(f"{API}/notifications/read-all", headers=anna)).status_code == 204
        assert (await client.get(f"{API}/notifications", headers=anna)).json()["unread"] == 0

        # --- Naechster Tag: dieselbe Stufe nicht noch einmal; neuer Termin -> Stufen von vorn -------
        async def next_day():
            async with async_session_factory() as db:
                await db.execute(text("UPDATE users SET last_digest_on = last_digest_on - 1"))
                await db.commit()

        await next_day()
        assert await digests() == 0
        r = await client.patch(f"{API}/wiedervorlagen/{kuendigung}", headers=admin,
                               json={"due_date": (today + timedelta(days=1)).isoformat()})
        assert r.status_code == 200
        FakeSMTP.fail = True  # Mailserver gerade weg: Push klappt, E-Mail wartet
        await next_day()
        assert await digests() == 1
        async with async_session_factory() as db:
            waiting = (await db.execute(select(Notification).where(
                Notification.channel == "email", Notification.status == "pending"))).scalars().all()
        assert len(waiting) == 1 and waiting[0].attempts == 1 and "nicht erreichbar" in waiting[0].error
        assert "morgen fällig" in pushed.pop()[1]["body"]
        r = await client.get(f"{API}/system/diagnostics", headers=admin)
        check = next(c for c in r.json()["components"] if c["key"] == "notifications")
        assert check["status"] == "error" and "nicht erreichbar" in check["hint"]

        FakeSMTP.fail = False  # naechster Lauf: E-Mail geht raus, keine neue Zusammenfassung
        assert await digests() == 0
        assert [m["Subject"] for m in FakeSMTP.sent] == ["HomeDMS: 1 demnächst"]
        check = next(c for c in (await client.get(f"{API}/system/diagnostics", headers=admin)).json()["components"]
                     if c["key"] == "notifications")
        assert check["status"] == "ok"

        # --- Geraet hat Push abbestellt: Abo verschwindet, Push wird ausgeschaltet ----------------------
        push_mode["value"] = "gone"
        r = await client.post(f"{API}/notifications/test", headers=admin, json={"channel": "push"})
        assert r.json()["ok"] is False
        async with async_session_factory() as db:
            assert (await db.execute(select(PushSubscription))).scalars().all() == []

        # Abo wieder anlegen und selbst entfernen
        push_mode["value"] = "ok"
        r = await client.post(f"{API}/notifications/push-subscriptions", headers=admin,
                              json={"endpoint": endpoint, "keys": browser_keys()})
        device = r.json()["push_devices"][0]["id"]
        assert (await client.delete(f"{API}/notifications/push-subscriptions/{device}", headers=anna)).status_code == 404
        r = await client.delete(f"{API}/notifications/push-subscriptions/{device}", headers=admin)
        assert r.status_code == 200 and r.json()["push"] is False and r.json()["push_devices"] == []

        # E-Mail-Versand entfernen
        r = await client.delete(f"{API}/tenant/mail", headers=admin)
        assert r.json()["configured"] is False
